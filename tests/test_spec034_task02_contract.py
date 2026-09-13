"""Task02 contract tests: durable schema, state transitions and v2 projection.

These tests intentionally avoid the future intake/orchestrator implementation;
they freeze only the storage seams consumed by Tasks03+.
"""

import json
import sqlite3
import uuid

import pytest

from backend.app.api.routes_research import ResearchSessionCommandRequest
from backend.app.memory.repository import MemoryRepository
from backend.app.research.domain.models import (
    AgentRun,
    ResearchEvent,
    ResearchNotification,
    ResearchSession,
    ResearchTask,
)
from backend.app.research.domain.state_machine import (
    InvalidStateTransition,
    transition_agent_run,
    transition_session,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _id() -> str:
    return uuid.uuid4().hex


def _session(tmp_path, owner="owner-a", conversation_id=None):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _assistant = memory.create_conversation_messages(owner, "research", None, "m", "normal")
    session = ResearchSession(_id(), owner, conversation_id or conversation.conversation_id, user.message_id, _id(), "intake_pending")
    return memory, session


def test_research_schema_v2_is_idempotent_and_has_active_guard(tmp_path):
    path = tmp_path / "research.sqlite3"
    ResearchStore(path)
    ResearchStore(path)
    with sqlite3.connect(path) as db:
        # Task04 adds an explicit v3 migration while preserving Task02's v2 data.
        assert db.execute("SELECT version FROM schema_meta").fetchone()[0] == 3
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"research_sessions", "research_intake_drafts", "research_approval_requests", "research_agent_runs", "research_artifacts", "research_notifications"} <= tables
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='uq_research_sessions_active'").fetchone()


def test_session_active_conflict_and_owner_isolation(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, first = _session(tmp_path)
    store.create_session(first, memory_repository=memory)
    second = ResearchSession(_id(), "owner-a", first.conversation_id, first.trigger_message_id, _id(), "intake_pending")
    with pytest.raises(Exception) as error:
        store.create_session(second, memory_repository=memory)
    assert getattr(error.value, "code", None) == "RESEARCH_SESSION_ACTIVE_CONFLICT"
    assert store.get_session(first.research_session_id, "owner-b") is None


def test_session_creation_fails_closed_and_draft_ids_must_match(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, session = _session(tmp_path)
    store.create_session(session, memory_repository=memory)
    with pytest.raises(ValueError, match="memory repository"):
        store.create_session(session)
    from backend.app.research.domain.models import ResearchIntakeDraft
    with pytest.raises(ValueError, match="draft"):
        store.create_session(session, ResearchIntakeDraft(_id(), _id()), memory_repository=memory)


def test_session_task_binding_is_checked_inside_store_transaction(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, session = _session(tmp_path)
    missing_task_session = ResearchSession(
        _id(), "owner-a", session.conversation_id, session.trigger_message_id, _id(),
        "intake_pending", research_task_id="missing-task",
    )
    with pytest.raises(Exception) as missing:
        store.create_session(missing_task_session, memory_repository=memory)
    assert getattr(missing.value, "code", None) == "TASK_NOT_FOUND"
    other_task = ResearchTask(
        _id(), "owner-a", "other-conversation", "goal", "zh", "balanced", False,
        1, 10, "draft", 1, "", "",
    )
    store.create_task(other_task)
    cross_session = ResearchSession(
        _id(), "owner-a", session.conversation_id, session.trigger_message_id, _id(),
        "intake_pending", research_task_id=other_task.research_task_id,
    )
    with pytest.raises(Exception) as cross:
        store.create_session(cross_session, memory_repository=memory)
    assert getattr(cross.value, "code", None) == "TASK_NOT_FOUND"


def test_state_machines_reject_terminal_rewind():
    assert transition_session("intake_pending", "plan_generating") == "plan_generating"
    assert transition_agent_run("queued", "running") == "running"
    with pytest.raises(InvalidStateTransition):
        transition_session("completed", "running")
    with pytest.raises(InvalidStateTransition):
        transition_agent_run("limit_reached", "running")


def test_processing_v2_is_idempotent_and_limits_tree_depth(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, _user, assistant = repo.create_conversation_messages("owner-a", "q", None, "m", "normal")
    phase = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="phase", source_event_id="research-event:t:1", kind="phase", status="running", node_type="phase")
    agent = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="agent", source_event_id="research-event:t:2", kind="agent", status="running", parent_step_id=phase.step_id, node_type="agent")
    tool = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="tool", source_event_id="research-event:t:3", kind="tool", status="completed", parent_step_id=agent.step_id, node_type="tool")
    assert repo.project_research_event_step(assistant.message_id, "owner-a", node_key="tool", source_event_id="research-event:t:3", kind="tool", status="completed", parent_step_id=agent.step_id, node_type="tool").step_id == tool.step_id
    with pytest.raises(ValueError, match="three levels"):
        repo.project_research_event_step(assistant.message_id, "owner-a", node_key="too-deep", source_event_id="research-event:t:4", kind="tool", status="running", parent_step_id=tool.step_id)
    assert len(repo.list_processing_steps(assistant.message_id, "owner-a")) == 3
    assert conversation.conversation_id


def test_processing_v2_allows_multiple_siblings_and_notification_idempotency(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    _conversation, _user, assistant = repo.create_conversation_messages("owner-a", "q", None, "m", "normal")
    parent = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="agent", source_event_id="research-event:t:1", kind="agent", status="running", node_type="agent")
    first = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="tool-a", source_event_id="research-event:t:2", kind="tool", status="completed", parent_step_id=parent.step_id, node_type="tool")
    second = repo.project_research_event_step(assistant.message_id, "owner-a", node_key="tool-b", source_event_id="research-event:t:3", kind="tool", status="completed", parent_step_id=parent.step_id, node_type="tool")
    assert first.step_id != second.step_id


def test_notification_idempotency_checks_payload_before_sequence(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, session = _session(tmp_path)
    store.create_session(session, memory_repository=memory)
    task = ResearchTask(_id(), "owner-a", session.conversation_id, "goal", "zh", "balanced", False, 12, 1500, "draft", 1, "", "")
    store.create_task(task)
    other_task = ResearchTask(_id(), "owner-a", session.conversation_id, "other goal", "zh", "balanced", False, 12, 1500, "draft", 1, "", "")
    store.create_task(other_task)
    store.update_session_links(session.research_session_id, "owner-a", research_task_id=task.research_task_id)
    original = ResearchNotification(_id(), "owner-a", "completed", "unread", 1, 0, '{"ok": true}', "n1", session.research_session_id, task.research_task_id)
    saved = store.create_notification(original)
    replay = store.create_notification(ResearchNotification(_id(), "owner-a", "completed", "unread", 1, 99, '{"ok":true}', "n1", session.research_session_id, task.research_task_id))
    assert replay.notification_id == saved.notification_id
    with pytest.raises(Exception) as error:
        store.create_notification(ResearchNotification(_id(), "owner-a", "completed", "unread", 1, 0, '{"ok": false}', "n1", session.research_session_id, task.research_task_id))
    assert getattr(error.value, "code", None) == "NOTIFICATION_IDEMPOTENCY_CONFLICT"
    with pytest.raises(ValueError, match="task/session"):
        store.create_notification(ResearchNotification(_id(), "owner-a", "completed", "unread", 1, 0, '{"ok": true}', "n2", session.research_session_id, other_task.research_task_id))
    with pytest.raises(Exception) as kind_conflict:
        store.create_notification(ResearchNotification(_id(), "owner-a", "failed", "unread", 1, 0, '{"ok": true}', "n1", session.research_session_id, task.research_task_id))
    assert getattr(kind_conflict.value, "code", None) == "NOTIFICATION_IDEMPOTENCY_CONFLICT"


def test_agent_run_bindings_fail_closed_for_unbound_non_planner_and_unknown_parent(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, session = _session(tmp_path)
    store.create_session(session, memory_repository=memory)
    worker = AgentRun(
        _id(), session.research_session_id, 1, "search_worker", "catalog", "1",
        "hash", "model", "medium", "[]", research_task_id=None,
    )
    with pytest.raises(ValueError, match="planner"):
        store.create_agent_run(worker, owner_id="owner-a")
    bound_worker = AgentRun(
        _id(), session.research_session_id, 1, "search_worker", "catalog", "1",
        "hash", "model", "medium", "[]", research_task_id="unapproved-task",
        work_item_id="unapproved-work-item",
    )
    with pytest.raises(ValueError, match="unapproved session"):
        store.create_agent_run(bound_worker, owner_id="owner-a")
    planner = AgentRun(
        _id(), session.research_session_id, 1, "planner", "planner", "1",
        "hash", "model", "medium", "[]",
    )
    store.create_agent_run(planner, owner_id="owner-a")
    unknown_parent = AgentRun(
        _id(), session.research_session_id, 2, "planner", "planner", "1",
        "hash", "model", "medium", "[]", continued_from_agent_run_id=_id(),
    )
    with pytest.raises(ValueError, match="continued run"):
        store.create_agent_run(unknown_parent, owner_id="owner-a")


def test_command_schema_has_fixed_literals_and_bounded_safe_scope():
    request = ResearchSessionCommandRequest(
        command="approve_plan", subject_version=1, scope_json={"max_results": 2}, idempotency_key="k"
    )
    assert request.command == "approve_plan"
    with pytest.raises(ValueError):
        ResearchSessionCommandRequest(command="shell", subject_version=1, idempotency_key="k")
    with pytest.raises(ValueError):
        ResearchSessionCommandRequest(
            command="approve_plan", subject_version=1,
            scope_json={"url": "https://example.invalid"}, idempotency_key="k",
        )


def test_replay_seam_orders_parent_before_out_of_order_events(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    _conversation, _user, assistant = repo.create_conversation_messages("owner-a", "q", None, "m", "normal")
    steps = repo.replay_processing_steps(assistant.message_id, "owner-a", [
        {"event_seq": 2, "research_task_id": "task", "source_event_id": "research-event:task:2", "node_key": "tool", "parent_node_key": "phase", "kind": "tool", "node_type": "tool", "status": "completed"},
        {"event_seq": 1, "research_task_id": "task", "source_event_id": "research-event:task:1", "node_key": "phase", "kind": "phase", "node_type": "phase", "status": "completed"},
    ])
    assert [step.node_key for step in steps] == ["phase", "tool"]
    assert steps[1].parent_step_id == steps[0].step_id
    with pytest.raises(ValueError, match="not canonical"):
        repo.replay_processing_steps(assistant.message_id, "owner-a", [
            {"event_seq": 1, "research_task_id": "task", "source_event_id": "custom:task:1", "node_key": "phase", "kind": "phase"},
        ])
    with pytest.raises(ValueError, match="not canonical"):
        repo.replay_processing_steps(assistant.message_id, "owner-a", [
            {"event_seq": 1, "research_task_id": "task", "safe_payload_json": json.dumps({"source_event_id": "custom:task:1"}), "node_key": "phase", "kind": "phase"},
        ])
    with pytest.raises(ValueError, match="multiple research tasks"):
        repo.replay_processing_steps(assistant.message_id, "owner-a", [
            {"event_seq": 1, "research_task_id": "task", "node_key": "phase", "kind": "phase"},
            {"event_seq": 2, "research_task_id": "other-task", "node_key": "tool", "kind": "tool"},
        ])


def test_research_store_replay_is_parent_first_and_tracks_projector_retry(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    memory, session = _session(tmp_path)
    store.create_session(session, memory_repository=memory)
    task_id = _id()
    store.create_task(ResearchTask(task_id, "owner-a", session.conversation_id, "goal", "zh", "balanced", False, 1, 10, "draft", 1, "", ""))
    events = [
        ResearchEvent(task_id, 2, "worker", json.dumps({"node_key": "tool", "parent_node_key": "phase"}), ""),
        ResearchEvent(task_id, 1, "plan", json.dumps({"node_key": "phase"}), ""),
    ]
    store.mark_projection_retry(task_id, 1, "temporary")
    ordered = store.replay_persisted_events(task_id, events, projector=lambda _event: None)
    assert [event.event_seq for event in ordered] == [1, 2]
    assert store.list_projection_retries(task_id, pending_only=False)[0]["pending"] == 0

    def fail_on_second(event):
        if event.event_seq == 2:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        store.replay_persisted_events(task_id, events, projector=fail_on_second)
    retry = {item["source_event_id"]: item for item in store.list_projection_retries(task_id, pending_only=False)}
    assert retry[f"research-event:{task_id}:2"]["attempts"] == 1
    with pytest.raises(ValueError, match="not canonical"):
        store.replay_persisted_events(task_id, [
            ResearchEvent(task_id, 1, "plan", json.dumps({"source_event_id": "custom:1"}), ""),
        ])
