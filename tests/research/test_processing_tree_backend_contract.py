"""Task07 processing-tree migration and ResearchEvent projector contracts."""

import json
import sqlite3
import uuid

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.processing_projector import ProcessingStepProjector
from backend.app.research.application.research_service import ResearchService
from backend.app.research.domain.models import ResearchSession, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _id() -> str:
    return uuid.uuid4().hex


def _memory(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = repo.create_conversation_messages("owner-a", "goal", None, "model", "normal")
    return repo, conversation, user, assistant


def _task(store, conversation_id):
    task = ResearchTask(_id(), "owner-a", conversation_id, "goal", "zh", "balanced", False, 2, 60, "draft", 1, "now", "now")
    store.create_task(task)
    return task


def test_processing_v2_migration_is_additive_and_indexes_are_partial(tmp_path):
    repo, _conversation, _user, assistant = _memory(tmp_path)
    with repo.connection() as db:
        db.execute(
            "INSERT INTO processing_steps(step_id,message_id,kind,logical_sequence,label,status,summary,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("legacy", assistant.message_id, "legacy", 0, "Legacy", "completed", "kept", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00"),
        )
    reopened = MemoryRepository(repo.database_path)
    step = reopened.list_processing_steps(assistant.message_id, "owner-a")[0]
    assert step.step_id == "legacy" and step.schema_version == 1 and step.parent_step_id is None
    assert step.node_type == "operation" and step.node_key is None
    with sqlite3.connect(repo.database_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(processing_steps)")}
        indexes = {row[1] for row in db.execute("PRAGMA index_list(processing_steps)")}
    assert {"parent_step_id", "node_type", "node_key", "display_order", "detail_json", "source_event_id", "research_session_id", "schema_version"} <= columns
    assert {"uq_steps_message_node_key", "uq_steps_source_event_id"} <= indexes


def test_processing_tree_rejects_cross_message_or_cycle_and_allows_three_levels(tmp_path):
    repo, _conversation, _user, assistant = _memory(tmp_path)
    _other_conversation, _other_user, other_assistant = repo.create_conversation_messages("owner-a", "other", None, "model", "normal")
    root = repo.create_processing_step(assistant.message_id, "phase", "running", node_key="root", node_type="phase")
    child = repo.create_processing_step(assistant.message_id, "agent", "running", parent_step_id=root.step_id, node_key="child", node_type="agent")
    leaf = repo.create_processing_step(assistant.message_id, "tool", "completed", parent_step_id=child.step_id, node_key="leaf", node_type="tool")
    assert [root.node_type, child.node_type, leaf.node_type] == ["phase", "agent", "tool"]
    with pytest.raises(ValueError, match="three levels"):
        repo.create_processing_step(assistant.message_id, "tool", "running", parent_step_id=leaf.step_id, node_key="too-deep", node_type="tool")
    with pytest.raises(ValueError, match="belong to message"):
        repo.create_processing_step(assistant.message_id, "tool", "running", parent_step_id=repo.create_processing_step(other_assistant.message_id, "phase", "running", node_key="other", node_type="phase").step_id, node_key="cross", node_type="tool")

    with repo.transaction() as db:
        db.execute("UPDATE processing_steps SET parent_step_id=? WHERE step_id=?", (child.step_id, root.step_id))
    with pytest.raises(ValueError, match="cycle"):
        repo.create_processing_step(assistant.message_id, "new", "running", parent_step_id=root.step_id, node_key="cycle-probe")

    legacy_root = repo.create_processing_step(assistant.message_id, "legacy", "completed", node_key="legacy-root", node_type="operation")
    with pytest.raises(ValueError, match="node type"):
        repo.create_processing_step(assistant.message_id, "agent", "running", parent_step_id=legacy_root.step_id, node_key="strict-agent", node_type="agent", strict_tree=True)
    strict_root = repo.create_processing_step(assistant.message_id, "strict-phase", "running", node_key="strict-phase", node_type="phase", strict_tree=True)
    strict_agent = repo.create_processing_step(assistant.message_id, "strict-agent-2", "running", parent_step_id=strict_root.step_id, node_key="strict-agent-2", node_type="agent", strict_tree=True)
    strict_leaf = repo.create_processing_step(assistant.message_id, "strict-tool", "completed", parent_step_id=strict_agent.step_id, node_key="strict-tool", node_type="tool", strict_tree=True)
    assert strict_leaf.node_type == "tool"


def test_research_event_projector_is_idempotent_parent_first_and_terminal_safe(tmp_path):
    memory, conversation, _user, assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    phase = store.append_event(task.research_task_id, "task", {"node_key": "phase", "node_type": "phase", "status": "running", "label": "Research"})
    worker = store.append_event(task.research_task_id, "worker", {"node_key": "worker", "node_type": "agent", "parent_node_key": "phase", "status": "running", "work_item_id": "w1"})
    done = store.append_event(task.research_task_id, "worker", {"node_key": "worker", "node_type": "agent", "parent_node_key": "phase", "status": "completed", "summary": "done", "work_item_id": "w1"})
    late = store.append_event(task.research_task_id, "worker", {"node_key": "worker", "node_type": "agent", "parent_node_key": "phase", "status": "running", "work_item_id": "w1"})
    projector = ProcessingStepProjector(store, memory)
    projected = projector.project_events(task.research_task_id, assistant.message_id, "owner-a", [worker, phase, done, late])
    replayed = projector.project_events(task.research_task_id, assistant.message_id, "owner-a", [late, done, worker, phase])
    steps = memory.list_processing_steps(assistant.message_id, "owner-a")
    worker_step = next(step for step in steps if step.node_key == "worker")
    assert [step.node_key for step in projected[:2]] == ["phase", "worker"]
    assert replayed and len(steps) == 2
    assert worker_step.status == "completed" and worker_step.source_event_id == done.source_event_id
    assert projector.as_sse_upsert(worker_step)["step"]["parent_step_id"] == next(step for step in steps if step.node_key == "phase").step_id


def test_projection_failure_is_retryable_and_cleared_after_replay(tmp_path):
    memory, conversation, _user, assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    bad = store.append_event(task.research_task_id, "worker", {"node_key": "orphan", "parent_node_key": "missing", "status": "running"})
    projector = ProcessingStepProjector(store, memory)
    with pytest.raises(ValueError, match="parent"):
        projector.project_events(task.research_task_id, assistant.message_id, "owner-a", [bad])
    retry = store.list_projection_retries(task.research_task_id)
    assert retry and retry[0]["error_code"] == "TRACE_PROJECTION_FAILED" and retry[0]["pending"] == 1

    parent = store.append_event(task.research_task_id, "task", {"node_key": "missing", "node_type": "phase", "status": "completed"})
    # The original orphan event is still invalid in sequence order; a caller
    # must replay a corrected persisted event, never fabricate a new event ID.
    corrected = {
        "research_task_id": task.research_task_id,
        "event_seq": bad.event_seq,
        "event_type": bad.event_type,
        "safe_payload_json": json.dumps({"node_key": "orphan", "parent_node_key": "missing", "status": "completed"}),
    }
    projector.project_events(task.research_task_id, assistant.message_id, "owner-a", [parent, corrected])
    assert not store.list_projection_retries(task.research_task_id)


def test_bound_session_rejects_cross_conversation_and_invalid_tree_types(tmp_path):
    memory, conversation, user, assistant = _memory(tmp_path)
    other_conversation, _other_user, other_assistant = memory.create_conversation_messages("owner-a", "other", None, "model", "normal")
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    activity = memory.create_activity_message(conversation.conversation_id, "owner-a", "activity", activity_idempotency_key="research-activity:test")
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=activity.message_id)
    store.create_session(session, memory_repository=memory)
    projector = ProcessingStepProjector(store, memory)
    event = store.append_event(task.research_task_id, "task", {"node_key": "phase", "node_type": "phase", "status": "running"})
    projector.project_event(activity.message_id, "owner-a", event, research_session_id=session.research_session_id)
    with pytest.raises(PermissionError):
        projector.project_event(other_assistant.message_id, "owner-a", event, research_session_id=session.research_session_id)
    bad = store.append_event(task.research_task_id, "worker", {"node_key": "bad", "node_type": "tool", "parent_node_key": "phase", "status": "running"})
    with pytest.raises(ValueError, match="node type"):
        projector.project_events(task.research_task_id, activity.message_id, "owner-a", [event, bad], research_session_id=session.research_session_id)
    assert [step.node_key for step in memory.list_processing_steps(activity.message_id, "owner-a")] == ["phase"]
    invalid_parent = store.append_event(task.research_task_id, "task", {"node_key": "invalid-parent", "node_type": "operation", "status": "running"})
    with pytest.raises(ValueError, match="node type"):
        projector.project_events(task.research_task_id, activity.message_id, "owner-a", [invalid_parent], research_session_id=session.research_session_id)
    assert other_conversation.conversation_id != conversation.conversation_id


def test_research_event_boundary_filters_sensitive_payload_and_retry_detail_is_stable(tmp_path):
    memory, conversation, _user, _assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    event = store.append_event(task.research_task_id, "task", {
        "status": "running", "prompt": "hidden", "credential": "secret",
        "summary": "Authorization: Bearer abc token=xyz secret: nope password=hush cookie=abc https://private.invalid/path", "node_type": "phase",
    })
    payload = json.loads(event.safe_payload_json)
    assert "prompt" not in payload and "credential" not in payload
    assert "abc" not in payload["summary"] and "xyz" not in payload["summary"]
    assert "[REDACTED]" in payload["summary"] and "https://" not in payload["summary"]
    retry = store.mark_projection_retry(task.research_task_id, event.event_seq, "private exception details")
    assert retry["error_code"] == "TRACE_PROJECTION_FAILED"
    assert retry["last_error"] == "TRACE_PROJECTION_FAILED"


def test_store_replay_paginates_past_1000_events(tmp_path):
    memory, conversation, _user, _assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    for index in range(1001):
        store.append_event(task.research_task_id, "task", {"status": "running", "node_type": "phase", "node_key": f"phase:{index}"})
    replayed = store.replay_persisted_events(task.research_task_id)
    assert len(replayed) == 1001 and replayed[-1].event_seq == 1001


def test_background_start_drains_pending_projection_without_new_event(tmp_path, monkeypatch):
    memory, conversation, user, _assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    activity = memory.create_activity_message(conversation.conversation_id, "owner-a", "activity", activity_idempotency_key="research-activity:drain")
    session = ResearchSession(_id(), "owner-a", conversation.conversation_id, user.message_id, _id(), "running", research_task_id=task.research_task_id, activity_message_id=activity.message_id)
    store.create_session(session, memory_repository=memory)
    event = store.append_event(task.research_task_id, "task", {"node_key": "phase:research", "node_type": "phase", "status": "running"})
    projector = ProcessingStepProjector(store, memory)
    original = memory.project_research_event_step

    def fail_once(*args, **kwargs):
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(memory, "project_research_event_step", fail_once)
    with pytest.raises(RuntimeError):
        projector.project_event(activity.message_id, "owner-a", event, research_session_id=session.research_session_id)
    store.mark_projection_retry(task.research_task_id, event.event_seq, "private provider detail")
    monkeypatch.setattr(memory, "project_research_event_step", original)

    class Executor:
        def submit(self, *_args):
            return None

    service = ResearchService(store=store, memory_repository=memory, executor=Executor())
    assert service.start(task.research_task_id, "owner-a") is True
    assert not store.list_projection_retries(task.research_task_id)
    assert not memory.list_processing_projection_retries(pending_only=True)


def test_unbound_legacy_model_event_uses_broad_replay_path(tmp_path):
    memory, conversation, _user, assistant = _memory(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = _task(store, conversation.conversation_id)
    legacy = store.append_event(task.research_task_id, "model", {"status": "completed", "summary": "legacy"})
    steps = ProcessingStepProjector(store, memory).project_events(
        task.research_task_id, assistant.message_id, "owner-a", [legacy]
    )
    assert len(steps) == 1 and steps[0].node_type == "skill"
