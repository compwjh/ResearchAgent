from datetime import datetime, timezone

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
