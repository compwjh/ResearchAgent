import sqlite3
from datetime import datetime, timezone

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.chat.application.conversation_service import compose_chat_prompt


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
        assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
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
