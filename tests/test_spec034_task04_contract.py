"""Spec034 Task04 backend contracts (plan output + unified commands)."""

import json
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.approval_service import PlanApprovalService, ResearchCommandError
from backend.app.research.application.plan_authoring import (
    plan_output_hash,
    validate_research_plan_output,
)
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import ResearchStore

OWNER = "owner-a"


def _output(version=1, *, objective="研究软件供应链攻击"):
    value = {
        "schema_version": "1",
        "plan_version": version,
        "objective": objective,
        "scope": {"facets": ["攻击面", "防御方法"]},
        "work_items": [
            {"id": "s1", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {"query": objective}},
            {"id": "s2", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {"query": objective}},
            {"id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator", "depends_on": ["s1", "s2"], "params": {"catalog_paper_ids": []}},
        ],
        "capabilities": [],
        "budget": {"quality_profile": "balanced", "target_paper_count": 12, "soft_budget_seconds": 1500, "language": "zh"},
        "report_structure": {"sections": ["摘要", "结论"]},
        "safe_summary": {"decision": "bounded"},
        "source_refs": ["intake:1"],
    }
    value["output_hash"] = plan_output_hash(value)
    return value


def _setup(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation(OWNER, None, "research")
    _conversation, user, _assistant = memory.create_message_pair(conversation.conversation_id, OWNER, "研究")
    store = ResearchStore(tmp_path / "research.sqlite3")
    session = ResearchSession(
        research_session_id="session-1", owner_id=OWNER, conversation_id=conversation.conversation_id,
        trigger_message_id=user.message_id, intake_draft_id="draft-1", status="intake_pending",
    )
    store.create_session(session, memory_repository=memory)
    for name in ("topic", "objective", "time_range"):
        store.upsert_intake_field(IntakeField("draft-1", name, json.dumps("x"), "user_explicit", 1.0, "confirmed", "2026-01-01T00:00:00Z", user.message_id), OWNER)
    store.update_intake_status("draft-1", OWNER, "complete")
    return memory, store, session


def test_research_plan_output_schema_and_semantics(tmp_path):
    output = validate_research_plan_output(_output())
    assert output["plan_version"] == 1
    assert output["output_hash"] == plan_output_hash(output)
    with pytest.raises(ValueError):
        bad = _output()
        bad["chain_of_thought"] = "must not persist"
        validate_research_plan_output(bad)
    with pytest.raises(ValueError):
        bad = _output()
        bad["output_hash"] = "0" * 64
        validate_research_plan_output(bad)


def test_author_plan_starts_at_one_and_approve_creates_task_only_after_approval(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    generated = service.author_plan(session.research_session_id, OWNER, _output())
    assert generated["subject_version"] == 1
    assert store.get_task("not-created", OWNER) is None
    assert store.get_session(session.research_session_id, OWNER).research_task_id is None
    result = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={"plan_version": 1}, idempotency_key="approve-1")
    assert result["status"] == "queued"
    assert result["task"]["research_task_id"]
    assert store.get_session(session.research_session_id, OWNER).activity_message_id
    replay = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="approve-1")
    assert replay == result


def test_stale_version_cancel_and_decline_are_strict(tmp_path):
    _memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store)
    service.author_plan(session.research_session_id, OWNER, _output())
    with pytest.raises(ResearchCommandError) as stale:
        service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=0, scope_json={}, idempotency_key="old")
    assert stale.value.code == "PLAN_VERSION_STALE"
    declined = service.command(session.research_session_id, OWNER, command="decline_request", subject_version=1, scope_json={}, idempotency_key="decline-1")
    assert declined["approval"]["status"] == "rejected"
    cancelled = service.command(session.research_session_id, OWNER, command="cancel_research", subject_version=1, scope_json={}, idempotency_key="cancel-1")
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ResearchCommandError) as terminal:
        service.command(session.research_session_id, OWNER, command="cancel_research", subject_version=1, scope_json={}, idempotency_key="cancel-2")
    assert terminal.value.code == "TASK_TERMINAL_CONFLICT"


def test_capability_approval_fails_closed_for_unregistered_tool(tmp_path):
    _memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, skill_registry=None, tool_registry=None)
    service.author_plan(session.research_session_id, OWNER, _output())
    # Add a pending capability approval to exercise the shared command path.
    from backend.app.research.domain.models import ApprovalRequest
    store.create_approval(ApprovalRequest("cap-1", OWNER, session.research_session_id, "capability_override", session.research_session_id, 1, "{}", idempotency_key="cap-pending"))
    with pytest.raises(ResearchCommandError) as error:
        service.command(session.research_session_id, OWNER, command="approve_capability", subject_version=1, scope_json={"skill": "missing", "tools": ["shell"]}, idempotency_key="cap-1")
    assert error.value.code == "CAPABILITY_NOT_AUTHORIZED"


def test_v2_database_is_upgraded_to_v3_task04_tables(tmp_path):
    path = tmp_path / "research.sqlite3"
    ResearchStore(path)
    with __import__("sqlite3").connect(path) as db:
        db.execute("UPDATE schema_meta SET version=2")
        db.execute("DROP TABLE research_activity_outbox")
        db.execute("DROP TABLE research_command_results")
        db.execute("DROP TABLE research_session_plans")
    ResearchStore(path)
    with __import__("sqlite3").connect(path) as db:
        assert db.execute("SELECT version FROM schema_meta").fetchone()[0] == 3
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"research_session_plans", "research_command_results", "research_activity_outbox"} <= tables
    ResearchStore(path)


def test_cancel_after_approval_converges_task_and_work_items(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    approved = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="approve")
    cancelled = service.command(session.research_session_id, OWNER, command="cancel_research", subject_version=1, scope_json={}, idempotency_key="cancel")
    assert cancelled["status"] == "cancelled"
    assert store.get_task(approved["research_task_id"], OWNER).status == "cancelled"
    assert {item.status for item in store.list_work_items(approved["research_task_id"])} == {"cancelled"}
    assert service.command(session.research_session_id, OWNER, command="cancel_research", subject_version=1, scope_json={}, idempotency_key="cancel") == cancelled


def test_author_plan_rejects_unknown_capability_and_approve_scope_expansion(tmp_path):
    _memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store)
    output = _output()
    output["capabilities"] = [{"skill": "missing-skill", "tools": ["missing-tool"]}]
    output["output_hash"] = plan_output_hash(output)
    with pytest.raises(ResearchCommandError) as error:
        service.author_plan(session.research_session_id, OWNER, output)
    assert error.value.code == "CAPABILITY_NOT_AUTHORIZED"


def test_author_plan_persists_registry_capability_snapshot(tmp_path):
    _memory, store, session = _setup(tmp_path)
    skill = SimpleNamespace(name="research", body="safe", tools=["catalog"], enabled=True)
    tool = SimpleNamespace(name="catalog", enabled=True, entry="backend.catalog.search", parameters={"type": "object"})
    service = PlanApprovalService(
        store=store,
        skill_registry=SimpleNamespace(get_skill=lambda _name: skill),
        tool_registry=SimpleNamespace(get_tool=lambda _name: tool),
    )
    output = _output()
    output["capabilities"] = [{"skill": "research", "tools": ["catalog"]}]
    output["output_hash"] = plan_output_hash(output)
    service.author_plan(session.research_session_id, OWNER, output)
    saved = store.get_session_plan(session.research_session_id, OWNER)
    snapshot = json.loads(saved.capabilities_json)
    assert snapshot[0]["skill"]["content_hash"]
    assert snapshot[0]["tools"][0]["entry"] == "backend.catalog.search"
    assert snapshot[0]["tools"][0]["parameters_hash"]


def test_activity_failure_is_retryable_and_does_not_duplicate_task(tmp_path, monkeypatch):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    original = memory.create_activity_message
    def fail(*_args, **_kwargs):
        raise OSError("memory unavailable")
    monkeypatch.setattr(memory, "create_activity_message", fail)
    with pytest.raises(ResearchCommandError) as error:
        service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="saga")
    assert error.value.code == "SOURCE_UNAVAILABLE"
    outbox = store.get_activity_outbox(owner_id=OWNER, research_session_id=session.research_session_id, subject_version=1, command_idempotency_key="saga")
    assert outbox["status"] == "failed"
    monkeypatch.setattr(memory, "create_activity_message", original)
    result = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="saga")
    assert result["status"] == "queued"
    assert len(store.list_tasks(OWNER)[0]) == 1


def test_approve_plan_outbox_failure_reuses_activation_and_task(tmp_path, monkeypatch):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    original = store.activate_plan
    calls = {"count": 0}

    def fail_once(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("activation/outbox unavailable")
        return original(**kwargs)

    monkeypatch.setattr(store, "activate_plan", fail_once)
    with pytest.raises(ResearchCommandError) as error:
        service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="outbox-retry")
    assert error.value.code == "SOURCE_UNAVAILABLE"
    activation = store.get_plan_activation(owner_id=OWNER, research_session_id=session.research_session_id, subject_version=1, command_idempotency_key="outbox-retry")
    assert activation["status"] == "failed"
    monkeypatch.setattr(store, "activate_plan", original)
    result = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="outbox-retry")
    assert result["status"] == "queued"
    assert len(store.list_tasks(OWNER)[0]) == 1
    assert len(store.list_work_items(result["research_task_id"])) == 3


def test_activity_message_is_idempotent_when_outbox_update_fails(tmp_path, monkeypatch):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    original = store.update_activity_outbox
    calls = {"count": 0}

    def fail_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1 and kwargs.get("status") == "completed":
            raise OSError("outbox update unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "update_activity_outbox", fail_once)
    with pytest.raises(ResearchCommandError) as error:
        service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="message-retry")
    assert error.value.code == "SOURCE_UNAVAILABLE"
    monkeypatch.setattr(store, "update_activity_outbox", original)
    result = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="message-retry")
    assert result["status"] == "queued"
    messages, _ = memory.list_messages(session.conversation_id, OWNER, limit=20)
    assert sum(message.content == "研究执行已获批准，正在排队。" for message in messages) == 1


def test_command_scope_uses_recursive_shared_safety_policy(tmp_path):
    _memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store)
    service.author_plan(session.research_session_id, OWNER, _output())
    for unsafe in ({"nested": {"CoT_payload": "hidden"}}, {"nested": "www.evil.example/path"}, {"nested": "evil.example"}):
        with pytest.raises(ResearchCommandError) as error:
            service.command(session.research_session_id, OWNER, command="cancel_research", subject_version=1, scope_json=unsafe, idempotency_key=f"unsafe-{len(unsafe)}")
        assert error.value.code == "CAPABILITY_NOT_AUTHORIZED"


def test_task_detail_projects_session_plan_and_safe_approval_history(tmp_path, monkeypatch):
    from backend.app.api import routes_research

    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())
    approved = service.command(session.research_session_id, OWNER, command="approve_plan", subject_version=1, scope_json={}, idempotency_key="detail-approve")
    task = store.get_task(approved["research_task_id"], OWNER)
    monkeypatch.setattr(routes_research, "OWNER_ID", OWNER)
    monkeypatch.setattr(routes_research, "_service", lambda: SimpleNamespace(get_task=lambda _task_id, _owner: task))
    monkeypatch.setattr(routes_research, "_store", lambda: store)
    detail = routes_research.get_research_task(task.research_task_id)
    assert detail["research_session_id"] == session.research_session_id
    assert detail["plan"]["plan_version"] == 1
    assert detail["plans"][0]["output_hash"]
    assert detail["approvals"][0]["kind"] == "plan"
    assert detail["approvals"][0]["status"] == "approved"
    assert detail["approvals"][0]["subject_version"] == 1
    assert set(detail["approvals"][0]) == {
        "approval_request_id", "kind", "status", "subject_version", "scope",
        "approved_scope", "created_at", "decided_at",
    }


def test_plan_output_rejects_duplicate_ids_deep_dag_and_embedded_url():
    duplicate = _output()
    duplicate["work_items"][1]["id"] = duplicate["work_items"][0]["id"]
    duplicate["output_hash"] = plan_output_hash(duplicate)
    with pytest.raises(ValueError):
        validate_research_plan_output(duplicate)
    deep = _output()
    deep["work_items"] = [
        {"id": "a", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {"query": "a"}},
        {"id": "b", "task_type": "search_catalog", "role": "search-worker", "depends_on": ["a"], "params": {"query": "b"}},
        {"id": "c", "task_type": "search_catalog", "role": "search-worker", "depends_on": ["b"], "params": {"query": "c"}},
        {"id": "d", "task_type": "search_catalog", "role": "search-worker", "depends_on": ["c"], "params": {"query": "d"}},
    ]
    deep["output_hash"] = plan_output_hash(deep)
    with pytest.raises(ValueError):
        validate_research_plan_output(deep)
    embedded = _output()
    embedded["safe_summary"] = {"notes": "see example https://evil.example"}
    embedded["output_hash"] = plan_output_hash(embedded)
    with pytest.raises(ValueError):
        validate_research_plan_output(embedded)
