import sqlite3
import time

import pytest

from backend.app.chat.application.conversation_service import (
    MemoryEvolutionService,
    MemoryEvolutionWorker,
    compose_chat_prompt,
)
from backend.app.memory.repository import MemoryRepository


def test_sqlite_memory_schema_is_idempotent_and_isolated(tmp_path):
    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    repo.initialize()
    repo.initialize()
    assert repo.connection().execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    project = repo.create_project("owner-a", "Demo")
    assert project.owner_id == "owner-a"
    assert repo.get_project(project.project_id, "owner-b") is None


def test_memory_and_message_pagination_and_project_isolation(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id, title="A")
    for index in range(4):
        repo.create_message(conversation.conversation_id, "owner-a", "user", f"message-{index}", status="completed")
    batch, cursor = repo.list_messages(conversation.conversation_id, "owner-a", target_chars=15)
    assert batch[0].content == "message-3"
    assert len(batch) < 4
    assert cursor
    memory = repo.create_memory(
        owner_id="owner-a", scope="project", project_id=project.project_id,
        category="project_rule", statement="Answer with the conclusion first.",
        source_kind="explicit", confidence=0.99,
    )
    assert repo.list_memories("owner-b", project.project_id) == []
    assert repo.list_memories("owner-a", project.project_id)[0].memory_id == memory.memory_id


def test_processing_step_and_evidence_are_persisted(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id)
    message = repo.create_message(conversation.conversation_id, "owner-a", "assistant", "ok")
    repo.create_processing_step(message.message_id, "memory_classification", "completed", "classified")
    memory = repo.create_memory(
        "owner-a", "project", project.project_id, "project_rule", "Rule", "explicit", 1.0
    )
    repo.create_memory_evidence(memory.memory_id, conversation.conversation_id, message.message_id, "user_statement", "Rule")
    assert repo.list_processing_steps(message.message_id, "owner-a")[0].summary == "classified"
    assert repo.list_memory_evidence(memory.memory_id, "owner-a")[0].excerpt == "Rule"


def test_global_memory_scopes_and_recall_priority(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    global_memory = repo.create_memory(
        "owner-a", "global", None, "user_preference", "Use concise answers", "explicit", 0.99
    )
    project_memory = repo.create_memory(
        "owner-a", "project", project.project_id, "project_rule", "Use the project vocabulary", "manual", 1.0
    )
    assert [m.memory_id for m in repo.list_memories("owner-a", scope="global")] == [global_memory.memory_id]
    assert [m.memory_id for m in repo.list_recall_memories("owner-a", project.project_id)] == [
        global_memory.memory_id,
        project_memory.memory_id,
    ]
    assert repo.list_recall_memories("owner-b", project.project_id) == []


def test_memory_edit_is_versioned_and_undo_delete_restores(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    memory = repo.create_memory("owner-a", "global", None, "user_preference", "Old", "manual", 1.0)
    edited = repo.update_memory(memory.memory_id, "owner-a", statement="New")
    assert edited.memory_id != memory.memory_id
    assert edited.supersedes_id == memory.memory_id
    assert repo.get_memory(memory.memory_id, "owner-a").status == "superseded"
    assert repo.delete_memory(edited.memory_id, "owner-a") is True
    assert repo.list_memories("owner-a", scope="global") == []
    restored = repo.undo_memory(edited.memory_id, "owner-a")
    assert restored.status == "active"


def test_project_delete_cascades_project_data_but_keeps_global(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id)
    project_memory = repo.create_memory("owner-a", "project", project.project_id, "project_rule", "P", "manual", 1.0)
    global_memory = repo.create_memory("owner-a", "global", None, "stable_fact", "G", "manual", 1.0)
    repo.create_message(conversation.conversation_id, "owner-a", "user", "hello", status="completed")
    assert repo.delete_project(project.project_id, "owner-a") is True
    assert repo.get_conversation(conversation.conversation_id, "owner-a") is None
    assert repo.get_memory(project_memory.memory_id, "owner-a") is None
    assert repo.get_memory(global_memory.memory_id, "owner-a") is not None


def test_prompt_keeps_project_instructions_above_scoped_memory(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo", instructions="Use the project terminology")
    global_memory = repo.create_memory("owner-a", "global", None, "user_preference", "Be concise", "manual", 1.0)
    project_memory = repo.create_memory("owner-a", "project", project.project_id, "project_rule", "Use examples", "manual", 1.0)
    prompt = compose_chat_prompt("Question", [], [project_memory, global_memory], project.instructions)
    assert prompt.index("项目明确指令") < prompt.index("用户全局记忆") < prompt.index("当前项目记忆") < prompt.index("用户当前问题")


def _make_v1_database(path):
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_version VALUES (1, '2026-01-01T00:00:00+00:00');
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, instructions TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner_id, name));
        CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE, title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active', memory_history_policy TEXT NOT NULL DEFAULT 'from_binding', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE messages(message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE, owner_id TEXT NOT NULL, parent_message_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, model TEXT, mode TEXT, created_at TEXT NOT NULL, completed_at TEXT);
        CREATE TABLE memories(memory_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL, project_id TEXT REFERENCES projects(project_id) ON DELETE CASCADE, category TEXT NOT NULL, statement TEXT NOT NULL, source_kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', confidence REAL NOT NULL, supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_used_at TEXT, CHECK ((scope='project' AND project_id IS NOT NULL) OR (scope='global' AND project_id IS NULL)));
        CREATE TABLE memory_evidence(memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE, conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL, message_id TEXT, evidence_type TEXT NOT NULL, excerpt TEXT);
        CREATE TABLE processing_steps(step_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE, kind TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL, summary TEXT, started_at TEXT NOT NULL, completed_at TEXT);
        INSERT INTO projects VALUES ('p1', 'owner-a', 'P1', NULL, 'active', '2026-01-01', '2026-01-01');
        INSERT INTO conversations VALUES ('c1', 'owner-a', 'p1', 'C1', 'active', 'from_binding', '2026-01-01', '2026-01-01');
        INSERT INTO messages VALUES ('m1', 'c1', 'owner-a', NULL, 'user', 'hello', 'completed', NULL, NULL, '2026-01-01', '2026-01-01');
        INSERT INTO memories VALUES ('g1', 'owner-a', 'global', NULL, 'user_preference', 'keep concise', 'manual', 'active', 1.0, NULL, '2026-01-01', '2026-01-01', NULL);
        INSERT INTO memory_evidence VALUES ('g1', 'c1', 'm1', 'manual', 'hello');
        """
    )
    db.commit()
    db.close()


def test_v1_database_is_migrated_atomically_and_message_evidence_is_nullable(tmp_path):
    path = tmp_path / "v1.sqlite3"
    _make_v1_database(path)
    repo = MemoryRepository(path)
    with repo.connection() as db:
        assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7
        assert db.execute("SELECT count(*) FROM conversations").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
        columns = {row["name"] for row in db.execute("PRAGMA table_info(conversations)")}
        assert {"memory_binding_at", "memory_binding_message_id"} <= columns
        foreign_keys = db.execute("PRAGMA foreign_key_list(memory_evidence)").fetchall()
        assert any(row["table"] == "messages" and row["on_delete"] == "SET NULL" for row in foreign_keys)
    assert repo.delete_project("p1", "owner-a") is True
    assert repo.list_memory_evidence("g1", "owner-a")[0].message_id is None


def test_v1_migration_failure_rolls_back_and_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "v1-failure.sqlite3"
    _make_v1_database(path)

    def fail_migration(_connection):
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(MemoryRepository, "_migrate_v1_to_v2", staticmethod(fail_migration))
    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 1
    assert "memory_binding_at" not in {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
    db.close()


def test_project_move_requires_confirmation_and_filters_from_binding_history(tmp_path):
    repo = MemoryRepository(tmp_path / "move.sqlite3")
    p1 = repo.create_project("owner-a", "P1")
    p2 = repo.create_project("owner-a", "P2")
    conversation = repo.create_conversation("owner-a", p1.project_id)
    old = repo.create_message(conversation.conversation_id, "owner-a", "user", "P1 secret", status="completed")
    project_memory = repo.create_memory("owner-a", "project", p1.project_id, "project_rule", "P1 only", "manual", 1.0)
    repo.create_memory_evidence(project_memory.memory_id, conversation.conversation_id, old.message_id, "manual", "P1 secret")
    with pytest.raises(ValueError, match="confirmation"):
        repo.update_conversation(conversation.conversation_id, "owner-a", project_id=p2.project_id)
    moved = repo.update_conversation(conversation.conversation_id, "owner-a", project_id=p2.project_id, confirm_move=True)
    assert moved.project_id == p2.project_id and moved.memory_binding_at is not None
    assert repo.list_memory_evidence(project_memory.memory_id, "owner-a")[0].conversation_id is None
    assert [message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")] == []
    repo.create_message(conversation.conversation_id, "owner-a", "user", "P2 new", status="completed")
    assert old.message_id not in {message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")}
    included = repo.update_conversation(conversation.conversation_id, "owner-a", memory_history_policy="include_prior_history", confirm_move=True)
    assert {message.content for message in repo.list_context_messages(conversation.conversation_id, "owner-a")} == {"P1 secret", "P2 new"}
    assert included.memory_history_policy == "include_prior_history"


def test_memory_evidence_rejects_cross_project_but_allows_global(tmp_path):
    repo = MemoryRepository(tmp_path / "evidence-scope.sqlite3")
    p1 = repo.create_project("owner-a", "P1")
    p2 = repo.create_project("owner-a", "P2")
    c1 = repo.create_conversation("owner-a", p1.project_id)
    c2 = repo.create_conversation("owner-a", p2.project_id)
    m2 = repo.create_message(c2.conversation_id, "owner-a", "user", "P2", status="completed")
    project_memory = repo.create_memory("owner-a", "project", p1.project_id, "project_rule", "P1 rule", "manual", 1.0)
    with pytest.raises(ValueError, match="project mismatch"):
        repo.create_memory_evidence(project_memory.memory_id, c2.conversation_id, m2.message_id, "manual", "P2")
    global_memory = repo.create_memory("owner-a", "global", None, "user_preference", "global rule", "manual", 1.0)
    repo.create_memory_evidence(global_memory.memory_id, c2.conversation_id, m2.message_id, "manual", "P2")
    with pytest.raises(LookupError, match="message not found"):
        repo.create_memory_evidence(project_memory.memory_id, c1.conversation_id, m2.message_id, "manual", "wrong message")


def test_unbinding_keeps_cutoff_and_allows_only_later_unbound_history(tmp_path):
    repo = MemoryRepository(tmp_path / "unbind.sqlite3")
    project = repo.create_project("owner-a", "P1")
    conversation = repo.create_conversation("owner-a", project.project_id)
    old = repo.create_message(conversation.conversation_id, "owner-a", "user", "project context", status="completed")
    unbound = repo.update_conversation(conversation.conversation_id, "owner-a", project_id=None, confirm_move=True)
    assert unbound.project_id is None and unbound.memory_binding_at is not None
    assert repo.list_context_messages(conversation.conversation_id, "owner-a") == []
    later = repo.create_message(conversation.conversation_id, "owner-a", "user", "unbound question", status="completed")
    context_ids = {message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")}
    assert context_ids == {later.message_id} and old.message_id not in context_ids


def test_raw_events_are_append_only_and_duplicate_trigger_is_idempotent(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    conversation = repo.create_conversation("owner-a")
    event = repo.append_raw_event("owner-a", conversation.conversation_id, "explicit_memory", {"statement": "结论优先"}, idempotency_key="m1")
    duplicate = repo.append_raw_event("owner-a", conversation.conversation_id, "explicit_memory", {"statement": "changed"}, idempotency_key="m1")
    assert duplicate.event_id == event.event_id
    assert repo.list_raw_events(conversation.conversation_id, "owner-a")[0].payload["statement"] == "结论优先"
    with pytest.raises(AttributeError):
        repo.update_raw_event(event.event_id, "owner-a", payload={})


def test_evolution_checkpoint_restarts_and_retries_without_duplicate_summary(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    conversation = repo.create_conversation("owner-a")
    for index in range(5):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": f"event-{index}"}, idempotency_key=f"e{index}")
    service = MemoryEvolutionService(repo, batch_size=2, summary_budget_chars=80)
    with pytest.raises(RuntimeError, match="injected"):
        service.process_session(conversation.conversation_id, "owner-a", trigger="context_pressure", fail_after_batches=1)
    failed = repo.get_evolution_checkpoint(conversation.conversation_id, "owner-a", "summarize")
    assert failed.status == "failed" and failed.batch_index == 1 and failed.attempts == 1
    restarted = MemoryRepository(tmp_path / "evolution.sqlite3")
    result = MemoryEvolutionService(restarted, batch_size=2, summary_budget_chars=80).process_session(conversation.conversation_id, "owner-a", trigger="retry")
    assert result.status == "completed"
    assert restarted.get_evolution_checkpoint(conversation.conversation_id, "owner-a", "summarize").attempts == 2
    summaries = restarted.list_conversation_summaries(conversation.conversation_id, "owner-a")
    assert len(summaries) == 1 and len(summaries[0].summary_text) <= 80


def test_evolution_session_mutex_and_candidate_promotion_require_evidence(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    service = MemoryEvolutionService(repo, batch_size=10)
    assert service.try_session_lock(conversation.conversation_id) is True
    assert service.try_session_lock(conversation.conversation_id) is False
    service.release_session_lock(conversation.conversation_id)
    candidate = repo.create_memory("owner-a", "project", project.project_id, "project_rule", "候选", "repeated", 0.7, status="candidate")
    with pytest.raises(ValueError, match="evidence"):
        repo.promote_memory(candidate.memory_id, "owner-a")
    repo.append_raw_event("owner-a", conversation.conversation_id, "user_correction", {"replacement": "候选"}, idempotency_key="correction-1")
    repo.create_memory_evidence(candidate.memory_id, conversation.conversation_id, None, "user_statement", "候选")
    promoted = repo.promote_memory(candidate.memory_id, "owner-a")
    assert promoted.status == "active" and promoted.scope == "project"


def test_evolution_scope_isolation_conflict_supersedes_and_budgeted_recall(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    p1 = repo.create_project("owner-a", "P1")
    p2 = repo.create_project("owner-a", "P2")
    c1 = repo.create_conversation("owner-a", p1.project_id)
    repo.append_raw_event("owner-a", c1.conversation_id, "user_message", {"content": "数据库偏好"}, idempotency_key="s1")
    MemoryEvolutionService(repo, batch_size=10, summary_budget_chars=40).process_session(c1.conversation_id, "owner-a", trigger="idle")
    repo.create_memory("owner-a", "global", None, "user_preference", "全局", "manual", 1.0)
    project_memory = repo.create_memory("owner-a", "project", p1.project_id, "project_rule", "项目规则", "manual", 1.0)
    recall = repo.list_recall_context("owner-a", p1.project_id, char_budget=20)
    assert recall["memories"] and all(len(item.statement) <= 1000 for item in recall["memories"])
    assert repo.list_recall_context("owner-a", p2.project_id, char_budget=200)["summaries"] == []
    edited = repo.update_memory(project_memory.memory_id, "owner-a", statement="新项目规则")
    assert edited.supersedes_id == project_memory.memory_id
    assert repo.get_memory(project_memory.memory_id, "owner-a").status == "superseded"


def test_correction_candidate_uses_superseded_chain_only_when_promoted(tmp_path):
    repo = MemoryRepository(tmp_path / "correction.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    previous = repo.create_memory("owner-a", "project", project.project_id, "project_rule", "旧规则", "manual", 1.0)
    repo.append_raw_event("owner-a", conversation.conversation_id, "user_correction", {"replacement": "新规则"}, message_id=None, idempotency_key="correction")
    service = MemoryEvolutionService(repo, batch_size=10)
    service.process_session(conversation.conversation_id, "owner-a", trigger="user_correction")
    candidate = next(item for item in repo.list_memories("owner-a", project.project_id, scope="project", status="candidate") if item.statement == "新规则")
    assert candidate.supersedes_id == previous.memory_id
    assert repo.get_memory(previous.memory_id, "owner-a").status == "active"
    repo.promote_memory(candidate.memory_id, "owner-a")
    assert repo.get_memory(previous.memory_id, "owner-a").status == "superseded"


def test_v3_malformed_table_fails_closed_at_startup(tmp_path):
    path = tmp_path / "malformed-v3.sqlite3"
    repo = MemoryRepository(path)
    with repo.transaction() as db:
        db.execute("DROP TABLE raw_events")
        db.execute("CREATE TABLE raw_events(event_id TEXT PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)


def test_raw_event_message_and_cursor_must_belong_to_same_conversation(tmp_path):
    repo = MemoryRepository(tmp_path / "raw-scope.sqlite3")
    first = repo.create_conversation("owner-a")
    second = repo.create_conversation("owner-a")
    message = repo.create_message(second.conversation_id, "owner-a", "user", "second", status="completed")
    event = repo.append_raw_event("owner-a", second.conversation_id, "user_message", {"content": "second"}, message_id=message.message_id, idempotency_key="second")
    with pytest.raises(ValueError, match="conversation"):
        repo.append_raw_event("owner-a", first.conversation_id, "user_message", {"content": "wrong"}, message_id=message.message_id)
    with pytest.raises(ValueError, match="cursor"):
        repo.list_raw_events(first.conversation_id, "owner-a", after=event.event_id)


def test_stale_running_checkpoint_is_taken_over_and_resumes(tmp_path):
    path = tmp_path / "stale.sqlite3"
    repo = MemoryRepository(path)
    conversation = repo.create_conversation("owner-a")
    for index in range(3):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": str(index)}, idempotency_key=str(index))
    checkpoint, claimed = repo.claim_evolution_checkpoint(conversation.conversation_id, "owner-a", total_batches=2, idempotency_key="crashed")
    assert claimed
    repo.save_evolution_progress(checkpoint.checkpoint_id, "owner-a", cursor=None, batch_index=1, state={"mapped": ["done"], "input_event_count": 3})
    with repo.transaction() as db:
        db.execute("UPDATE evolution_checkpoints SET updated_at=? WHERE checkpoint_id=?", ("2020-01-01T00:00:00+00:00", checkpoint.checkpoint_id))
    restarted = MemoryRepository(path)
    resumed = MemoryEvolutionService(restarted, batch_size=2).process_session(conversation.conversation_id, "owner-a", trigger="retry")
    assert resumed.status == "completed" and resumed.attempts == 2 and resumed.batch_index == 2


def test_evolution_worker_consumes_more_than_1000_events_and_recovers(tmp_path):
    repo = MemoryRepository(tmp_path / "many-events.sqlite3")
    conversation = repo.create_conversation("owner-a")
    for index in range(1001):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": f"e{index}"}, idempotency_key=f"e{index}")
    worker = MemoryEvolutionWorker(repo, owner_id="owner-a", poll_interval=0.01).start()
    worker.enqueue_session(conversation.conversation_id)
    deadline = time.monotonic() + 5
    checkpoint = None
    while time.monotonic() < deadline:
        checkpoint = repo.get_evolution_checkpoint(conversation.conversation_id, "owner-a")
        if checkpoint and checkpoint.status == "completed":
            break
        time.sleep(0.01)
    worker.stop()
    assert checkpoint and checkpoint.status == "completed" and checkpoint.state["input_event_count"] == 1001
    all_events = repo.list_raw_events(conversation.conversation_id, "owner-a", limit=5000)
    assert checkpoint.state["input_last_event_id"] == all_events[-1].event_id
    assert repo.list_conversation_summaries(conversation.conversation_id, "owner-a")[0].source_event_id == checkpoint.state["input_last_event_id"]


def test_candidate_and_evidence_are_atomic(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path / "candidate-atomic.sqlite3")
    project = repo.create_project("owner-a", "P")
    def fail_evidence(*_args):
        raise RuntimeError("evidence failure")
    monkeypatch.setattr(repo, "_insert_memory_evidence", fail_evidence)
    with pytest.raises(RuntimeError, match="evidence failure"):
        repo.create_memory("owner-a", "project", project.project_id, "project_rule", "atomic", "repeated", 0.7, status="candidate", evidence=(None, None, "manual", "atomic"))
    assert repo.list_memories("owner-a", project.project_id, scope="project", status="candidate") == []


def test_summary_recall_without_match_is_empty(tmp_path):
    repo = MemoryRepository(tmp_path / "summary-match.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    repo.upsert_conversation_summary("owner-a", conversation.conversation_id, "关于数据库索引的摘要")
    assert repo.list_recall_summaries("owner-a", project.project_id, query="完全不相关", budget_chars=1000) == []
