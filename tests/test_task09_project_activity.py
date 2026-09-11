from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.memory.repository import MemoryRepository, encode_cursor


def _set_project_time(repo, project_id, value):
    with repo.transaction() as db:
        db.execute("UPDATE projects SET updated_at=? WHERE project_id=?", (value, project_id))


def _set_conversation_time(repo, conversation_id, value, status=None):
    with repo.transaction() as db:
        if status is None:
            db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (value, conversation_id))
        else:
            db.execute("UPDATE conversations SET updated_at=?, status=? WHERE conversation_id=?", (value, status, conversation_id))


def test_project_activity_projection_includes_only_non_deleted_conversations_and_is_owner_scoped(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    no_conversations = repo.create_project("owner-a", "No conversations")
    active = repo.create_project("owner-a", "Active")
    archived = repo.create_project("owner-a", "Archived")
    deleted_only = repo.create_project("owner-a", "Deleted only")
    foreign = repo.create_project("owner-b", "Foreign")

    _set_project_time(repo, no_conversations.project_id, "2026-01-01T00:00:01+00:00")
    _set_project_time(repo, active.project_id, "2026-01-01T00:00:02+00:00")
    _set_project_time(repo, archived.project_id, "2026-01-01T00:00:03+00:00")
    _set_project_time(repo, deleted_only.project_id, "2026-01-01T00:00:04+00:00")
    _set_project_time(repo, foreign.project_id, "2026-01-01T00:00:05+00:00")

    active_conversation = repo.create_conversation("owner-a", active.project_id)
    archived_conversation = repo.create_conversation("owner-a", archived.project_id)
    deleted_conversation = repo.create_conversation("owner-a", deleted_only.project_id)
    _set_conversation_time(repo, active_conversation.conversation_id, "2026-01-01T00:01:00+00:00")
    _set_conversation_time(repo, archived_conversation.conversation_id, "2026-01-01T00:02:00+00:00", "archived")
    _set_conversation_time(repo, deleted_conversation.conversation_id, "2026-01-01T00:03:00+00:00", "deleted")

    items, cursor = repo.list_projects("owner-a")
    assert cursor is None
    by_name = {item.name: item for item in items}
    assert set(by_name) == {"No conversations", "Active", "Archived", "Deleted only"}
    assert by_name["No conversations"].last_activity_at == datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert by_name["Active"].last_activity_at == datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    assert by_name["Archived"].last_activity_at == datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
    assert by_name["Deleted only"].last_activity_at == datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc)
    assert "Foreign" not in by_name


def test_project_activity_pagination_uses_same_keyset_and_rejects_legacy_cursor(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    projects = [repo.create_project("owner-a", f"P{index}") for index in range(5)]
    same_time = "2026-02-01T00:00:00+00:00"
    for project in projects:
        _set_project_time(repo, project.project_id, same_time)

    all_ids = sorted((project.project_id for project in projects), reverse=True)
    page_ids = []
    cursor = None
    while True:
        page, cursor = repo.list_projects("owner-a", cursor, limit=2)
        page_ids.extend(project.project_id for project in page)
        if cursor is None:
            break
    assert page_ids == all_ids
    assert len(page_ids) == len(set(page_ids))

    with pytest.raises(ValueError, match="invalid cursor"):
        repo.list_projects("owner-a", encode_cursor("projects", same_time, all_ids[-1]), limit=2)


def test_project_list_activity_query_is_single_sql_projection(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    _set_conversation_time(repo, conversation.conversation_id, "2026-03-01T00:00:00+00:00")

    calls = 0
    original_connection = repo.connection

    def counted_connection():
        nonlocal calls
        calls += 1
        return original_connection()

    monkeypatch.setattr(repo, "connection", counted_connection)
    items, _ = repo.list_projects("owner-a")
    assert [item.project_id for item in items] == [project.project_id]
    assert calls == 1


def test_projects_api_payload_always_contains_last_activity_at(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    with patch("backend.app.memory.repository.default_database_path", return_value=database_path):
        client = TestClient(app)
        created = client.post("/api/projects", json={"name": "API project"})
        assert created.status_code == 201
        project = created.json()
        assert {
            "project_id", "owner_id", "name", "instructions", "status",
            "created_at", "updated_at", "last_activity_at",
        } == set(project)
        assert project["last_activity_at"] == project["updated_at"]

        repo = MemoryRepository(database_path)
        conversation = repo.create_conversation("local-user", project["project_id"])
        project_updated_at = project["updated_at"]
        project_time = datetime.fromisoformat(project_updated_at)
        older_conversation_time = (project_time - timedelta(seconds=1)).isoformat()
        _set_conversation_time(repo, conversation.conversation_id, older_conversation_time)
        project_wins = client.get("/api/projects?limit=1")
        assert project_wins.status_code == 200
        assert project_wins.json()["projects"][0]["last_activity_at"] == project_updated_at

        newer_conversation_time = (project_time + timedelta(seconds=1)).isoformat()
        _set_conversation_time(repo, conversation.conversation_id, newer_conversation_time)
        listed = client.get("/api/projects?limit=1")
        assert listed.status_code == 200
        payload = listed.json()["projects"][0]
        assert payload["last_activity_at"] == newer_conversation_time
