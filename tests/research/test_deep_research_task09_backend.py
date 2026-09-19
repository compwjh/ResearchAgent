"""Spec034 Task09 backend contracts: legacy adapter and precise cleanup."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.api import routes_research
from backend.app.memory.repository import MemoryRepository
from backend.app.platform.bootstrap import override_provider
from backend.app.research.infrastructure.research_store import LegacyCleanupError, ResearchStore


def _legacy(store: ResearchStore, task_id: str, owner: str, status: str = "completed") -> None:
    with store._connect() as db:
        db.execute(
            "INSERT INTO research_tasks(research_task_id,owner_id,project_id,conversation_id,goal,language,quality_profile,review_plan_first,target_paper_count,soft_budget_seconds,status,current_plan_version,last_event_seq,created_at,updated_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, owner, None, "", "legacy", "zh", "balanced", 0, 1, 1, status, 1, 0, "2020", "2020", "2020" if status in {"completed", "failed", "cancelled", "partial", "interrupted"} else None),
        )


def _verified_cross_snapshot() -> dict:
    return {"sessions": 1, "catalog": 2, "kb": 3}


def test_legacy_cleanup_dry_run_identifies_children_and_execute_is_exact(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "legacy-1", "owner-a")
    with store._connect() as db:
        db.execute("INSERT INTO research_plans VALUES('legacy-1',1,'rule','x','[]','proposed','2020')")
        db.execute("INSERT INTO research_events VALUES('legacy-1',1,'task','{}','2020')")
        db.execute("INSERT INTO research_paper_selections VALUES('legacy-1','paper-1',0,'[]','catalog','2020')")
        db.execute("INSERT INTO preliminary_reports VALUES('report-1','legacy-1',1,'preliminary','# report','{}','2020')")
    plan = store.dry_run_legacy_cleanup("owner-a", external_snapshot=_verified_cross_snapshot)
    assert plan["target_task_ids"] == ["legacy-1"]
    target = plan["targets"][0]
    assert target["children"]["research_plans"] == ["1"]
    assert target["children"]["research_events"] == ["1"]
    assert target["child_count"] == 4
    result = store.execute_legacy_cleanup(
        "owner-a", confirm=True, dry_run_id=plan["cleanup_id"], external_snapshot=_verified_cross_snapshot,
    )
    assert result["deleted"]["research_tasks"] == 1
    assert store.get_task("legacy-1", "owner-a") is None
    with sqlite3.connect(tmp_path / "research.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM research_legacy_cleanup_audits WHERE mode='execute'").fetchone()[0] == 1


def test_cleanup_preserves_bound_task_and_owner_isolation(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "a", "owner-a")
    _legacy(store, "b", "owner-b")
    with store._connect() as db:
        db.execute(
            "INSERT INTO research_sessions(research_session_id,owner_id,conversation_id,trigger_message_id,intake_draft_id,research_task_id,current_plan_version,status,unread_state_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("session-a", "owner-a", "conversation-a", "message-a", "draft-a", "a", 0, "completed", "{}", "2020", "2020"),
        )
    report = store.dry_run_legacy_cleanup("owner-a")
    assert report["target_task_ids"] == []
    assert report["protected_counts"]["bound_tasks"] == 1
    with pytest.raises(LegacyCleanupError) as no_match:
        store.execute_legacy_cleanup("owner-a", confirm=True, dry_run_id=report["cleanup_id"])
    assert no_match.value.code == "LEGACY_CLEANUP_NO_MATCH"
    assert store.get_task("a", "owner-a") is not None
    assert store.get_task("b", "owner-b") is not None


def test_cleanup_aborts_all_targets_when_any_legacy_task_is_active(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "done", "owner-a", "completed")
    _legacy(store, "active", "owner-a", "running")
    report = store.dry_run_legacy_cleanup("owner-a")
    assert report["target_task_ids"] == ["done"]
    assert report["validation_errors"][0]["code"] == "LEGACY_CLEANUP_ACTIVE_RESEARCH"
    with pytest.raises(LegacyCleanupError) as error:
        store.execute_legacy_cleanup("owner-a", confirm=True, dry_run_id=report["cleanup_id"])
    assert error.value.code == "LEGACY_CLEANUP_ACTIVE_RESEARCH"
    assert store.get_task("done", "owner-a") is not None
    assert store.get_task("active", "owner-a") is not None


def test_task09_audit_table_is_added_to_an_existing_v3_database(tmp_path):
    path = tmp_path / "research.sqlite3"
    ResearchStore(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE research_legacy_cleanup_audits")
    ResearchStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_legacy_cleanup_audits'"
        ).fetchone() == (1,)


def test_old_post_is_an_intake_adapter_and_does_not_create_task(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    conversation = memory.create_conversation("local-user", None, "old title")
    payload = routes_research.ResearchTaskCreateRequest(goal="软件供应链攻击", conversation_id=conversation.conversation_id)
    with override_provider("memory_repository", memory), override_provider("research_store", store):
        result = routes_research.create_research_task(payload)
    assert result["research_session_id"]
    assert result["intake"]["status"] == "intake"
    assert result["intake"]["missing"] == ["objective", "time_range"]
    assert store.list_tasks("local-user")[0] == []
    assert memory.get_conversation(conversation.conversation_id, "local-user").title == "old title"


def test_execute_requires_matching_dry_run_and_cross_store_audit(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "legacy", "owner-a")
    with pytest.raises(LegacyCleanupError) as missing:
        store.execute_legacy_cleanup("owner-a", confirm=True)
    assert missing.value.code == "LEGACY_CLEANUP_DRY_RUN_REQUIRED"
    dry = store.dry_run_legacy_cleanup("owner-a", external_snapshot=lambda: {"sessions": 1, "catalog": 2, "kb": 3})
    report = store.execute_legacy_cleanup(
        "owner-a", confirm=True, dry_run_id=dry["cleanup_id"],
        external_snapshot=lambda: {"sessions": 1, "catalog": 2, "kb": 3},
    )
    assert report["cross_store"]["unchanged"] is True
    assert report["cross_store"]["before"] == report["cross_store"]["after"]
    assert report["cross_store"]["status"] == "unchanged"


def test_execute_rolls_back_when_cross_store_changes_and_audits_before_after(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "legacy", "owner-a")
    with store._connect() as db:
        db.execute("INSERT INTO research_plans VALUES('legacy',1,'rule','x','[]','proposed','2020')")
    snapshots = iter(
        (
            {"sessions": 1, "catalog": 2, "kb": 3},  # dry-run
            {"sessions": 1, "catalog": 2, "kb": 3},  # execute before
            {"sessions": 1, "catalog": 9, "kb": 3},  # execute after
        )
    )
    dry = store.dry_run_legacy_cleanup("owner-a", external_snapshot=lambda: next(snapshots))
    with pytest.raises(LegacyCleanupError) as changed:
        store.execute_legacy_cleanup(
            "owner-a", confirm=True, dry_run_id=dry["cleanup_id"],
            external_snapshot=lambda: next(snapshots),
        )
    assert changed.value.code == "LEGACY_CLEANUP_CROSS_STORE_CHANGED"
    assert store.get_task("legacy", "owner-a") is not None
    with store._connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM research_plans WHERE research_task_id='legacy'"
        ).fetchone()[0] == 1
    audit = [item for item in store.list_legacy_cleanup_audits("owner-a") if item["mode"] == "execute"][-1]
    assert audit["status"] == "aborted"
    assert audit["error_code"] == "LEGACY_CLEANUP_CROSS_STORE_CHANGED"
    assert audit["before"]["target_task_ids"] == ["legacy"]
    assert audit["after"]["target_task_ids"] == ["legacy"]
    assert audit["cross_store"]["before"]["catalog"] == 2
    assert audit["cross_store"]["after"]["catalog"] == 9
    assert audit["cross_store"]["unchanged"] is False
    assert audit["cross_store"]["status"] == "changed"


def test_execute_rolls_back_when_cross_store_is_unverified_and_audits_state(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "legacy", "owner-a")

    def unverified_snapshot():
        return {"sessions": 1, "catalog": 2, "kb": 3, "status": "unverified", "reason": "provider unavailable"}

    dry = store.dry_run_legacy_cleanup("owner-a", external_snapshot=unverified_snapshot)
    with pytest.raises(LegacyCleanupError) as unverified:
        store.execute_legacy_cleanup(
            "owner-a", confirm=True, dry_run_id=dry["cleanup_id"], external_snapshot=unverified_snapshot,
        )
    assert unverified.value.code == "LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED"
    assert store.get_task("legacy", "owner-a") is not None
    audit = [item for item in store.list_legacy_cleanup_audits("owner-a") if item["mode"] == "execute"][-1]
    assert audit["status"] == "aborted"
    assert audit["error_code"] == "LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED"
    assert audit["before"]["target_task_ids"] == ["legacy"]
    assert audit["after"]["target_task_ids"] == ["legacy"]
    assert audit["cross_store"]["before"]["status"] == "unverified"
    assert audit["cross_store"]["after"]["status"] == "unverified"
    assert audit["cross_store"]["unchanged"] is False
    assert audit["cross_store"]["status"] == "unverified"


def test_execute_rejects_changed_target_after_dry_run(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "legacy", "owner-a")
    dry = store.dry_run_legacy_cleanup("owner-a")
    with store._connect() as db:
        db.execute("INSERT INTO research_events VALUES('legacy',1,'task','{}','2020')")
    with pytest.raises(LegacyCleanupError) as changed:
        store.execute_legacy_cleanup("owner-a", confirm=True, dry_run_id=dry["cleanup_id"])
    assert changed.value.code == "LEGACY_CLEANUP_TARGET_CHANGED"
    assert store.get_task("legacy", "owner-a") is not None


def test_session_create_is_idempotent_under_concurrent_retries(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    conversation = memory.create_conversation("local-user", None, "chat")
    payload = routes_research.ResearchSessionCreateRequest(
        conversation_id=conversation.conversation_id, idempotency_key="stable-create-1",
        intake={"topic": "供应链"},
    )
    with override_provider("memory_repository", memory), override_provider("research_store", store), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(routes_research.create_research_session, [payload] * 4))
    assert len({item["research_session_id"] for item in results}) == 1
    messages, _ = memory.list_messages(conversation.conversation_id, "local-user", limit=20)
    assert sum(item.role == "user" for item in messages) == 1
    assert sum(item.role == "assistant" for item in messages) == 1


def test_trigger_message_is_a_stable_idempotency_identity(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    conversation = memory.create_conversation("local-user", None, "chat")
    _conversation, trigger, _assistant = memory.create_message_pair(
        conversation.conversation_id, "local-user", "请做深度研究：供应链"
    )
    payload = routes_research.ResearchSessionCreateRequest(
        conversation_id=conversation.conversation_id, trigger_message_id=trigger.message_id,
        intake={"topic": "供应链"},
    )
    with override_provider("memory_repository", memory), override_provider("research_store", store):
        first = routes_research.create_research_session(payload)
        replay = routes_research.create_research_session(payload)
    assert replay == first
    assert len(store.list_sessions("local-user")) == 1


def test_project_is_materialized_and_explicit_mismatch_fails_closed(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    project_a = memory.create_project("local-user", "A")
    project_b = memory.create_project("local-user", "B")
    conversation = memory.create_conversation("local-user", project_a.project_id, "chat")
    with override_provider("memory_repository", memory), override_provider("research_store", store):
        mismatch = routes_research.create_research_session(routes_research.ResearchSessionCreateRequest(
            conversation_id=conversation.conversation_id, project_id=project_b.project_id,
            intake={"topic": "供应链"},
        ))
    assert mismatch.status_code == 409
    assert mismatch.body and b"PROJECT_MISMATCH" in mismatch.body
    assert store.list_sessions("local-user") == []


def test_session_list_returns_status_aware_keyset_cursor(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    payloads = []
    for topic in ("一", "二", "三"):
        conversation = memory.create_conversation("local-user", None, "chat")
        payloads.append(routes_research.ResearchSessionCreateRequest(
            conversation_id=conversation.conversation_id, intake={"topic": topic},
        ))
    with override_provider("memory_repository", memory), override_provider("research_store", store):
        for payload in payloads:
            routes_research.create_research_session(payload)
        first = routes_research.list_research_sessions(limit=2)
        assert first["next_cursor"]
        second = routes_research.list_research_sessions(limit=2, cursor=first["next_cursor"])
        ids = [item["research_session_id"] for item in first["research_sessions"] + second["research_sessions"]]
        assert len(ids) == len(set(ids)) == 3


def test_terminal_task_reconciles_stale_queued_session_projection(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _legacy(store, "task-terminal", "owner-a", "partial")
    with store._connect() as db:
        db.execute(
            "INSERT INTO research_sessions(research_session_id,owner_id,conversation_id,trigger_message_id,intake_draft_id,research_task_id,current_plan_version,status,unread_state_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("session-stale", "owner-a", "conversation-a", "message-a", "draft-a", "task-terminal", 1, "queued", "{}", "2020", "2020"),
        )
    repaired = store.reconcile_session_status("session-stale", "owner-a", "partial")
    assert repaired.status == "partial"
    # Repeated GET/recovery calls are idempotent and never rewrite a terminal state.
    assert store.reconcile_session_status("session-stale", "owner-a", "completed").status == "partial"
def test_session_list_project_filter_cursor_anchors_to_last_visible_row(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    project = memory.create_project("local-user", "Research")
    payloads = []
    for index in range(5):
        conversation = memory.create_conversation(
            "local-user", project.project_id if index != 1 else None, f"chat-{index}"
        )
        payloads.append(routes_research.ResearchSessionCreateRequest(
            conversation_id=conversation.conversation_id, intake={"topic": str(index)},
        ))
    with override_provider("memory_repository", memory), override_provider("research_store", store):
        for payload in payloads:
            routes_research.create_research_session(payload)
        first = routes_research.list_research_sessions(project_id=project.project_id, limit=2)
        second = routes_research.list_research_sessions(project_id=project.project_id, limit=2, cursor=first["next_cursor"])
    ids = [item["research_session_id"] for page in (first, second) for item in page["research_sessions"]]
    assert len(ids) == len(set(ids)) == 4
    assert second["next_cursor"] is None
