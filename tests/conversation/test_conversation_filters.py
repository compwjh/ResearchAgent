from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.memory.repository import MemoryRepository


def _set_conversation(repo, conversation_id, updated_at, status=None):
    with repo.transaction() as db:
        if status is None:
            db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (updated_at, conversation_id))
        else:
            db.execute("UPDATE conversations SET updated_at=?, status=? WHERE conversation_id=?", (updated_at, status, conversation_id))


def test_global_archived_filter_includes_bound_and_unbound_conversations(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")
    bound_archived = repo.create_conversation("owner-a", project.project_id, title="bound archived")
    unbound_archived = repo.create_conversation("owner-a", title="unbound archived")
    deleted = repo.create_conversation("owner-a", project.project_id, title="deleted")
    _set_conversation(repo, bound_archived.conversation_id, "2026-05-01T00:03:00+00:00", "archived")
    _set_conversation(repo, unbound_archived.conversation_id, "2026-05-01T00:02:00+00:00", "archived")
    _set_conversation(repo, deleted.conversation_id, "2026-05-01T00:04:00+00:00", "deleted")

    items, _ = repo.list_conversations("owner-a", status="archived")
    assert [item.conversation_id for item in items] == [bound_archived.conversation_id, unbound_archived.conversation_id]
    assert all(item.status == "archived" for item in items)


def test_unbound_only_filters_all_statuses_and_combines_with_status(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")
    unbound_active = repo.create_conversation("owner-a", title="unbound active")
    unbound_archived = repo.create_conversation("owner-a", title="unbound archived")
    bound_active = repo.create_conversation("owner-a", project.project_id, title="bound active")
    _set_conversation(repo, unbound_active.conversation_id, "2026-05-02T00:03:00+00:00", "active")
    _set_conversation(repo, unbound_archived.conversation_id, "2026-05-02T00:02:00+00:00", "archived")
    _set_conversation(repo, bound_active.conversation_id, "2026-05-02T00:04:00+00:00", "active")

    items, _ = repo.list_conversations("owner-a", unbound_only=True)
    assert {item.conversation_id for item in items} == {unbound_active.conversation_id, unbound_archived.conversation_id}
    active_items, _ = repo.list_conversations("owner-a", status="active", unbound_only=True)
    assert [item.conversation_id for item in active_items] == [unbound_active.conversation_id]

    with pytest.raises(ValueError, match="unbound_only"):
        repo.list_conversations("owner-a", project_id=project.project_id, unbound_only=True)
    with pytest.raises(ValueError, match="invalid conversation status"):
        repo.list_conversations("owner-a", status="deleted")


def test_conversation_status_keyset_pagination_is_filter_scoped(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversations = [repo.create_conversation("owner-a", title=f"C{index}") for index in range(5)]
    for index, conversation in enumerate(conversations):
        _set_conversation(repo, conversation.conversation_id, f"2026-05-03T00:0{index}:00+00:00", "archived")

    seen = []
    cursor = None
    archived_cursor = None
    while True:
        page, cursor = repo.list_conversations("owner-a", cursor=cursor, limit=2, status="archived")
        if archived_cursor is None:
            archived_cursor = cursor
        seen.extend(item.conversation_id for item in page)
        if cursor is None:
            break
    # Timestamps are increasing, so the API order is newest first.
    expected = [conversations[index].conversation_id for index in range(4, -1, -1)]
    assert seen == expected
    assert len(seen) == len(set(seen))

    with pytest.raises(ValueError, match="invalid cursor"):
        repo.list_conversations("owner-a", cursor=archived_cursor, limit=2, unbound_only=True)


def test_conversation_cursor_rejects_project_and_default_scope_swaps(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project_a = repo.create_project("owner-a", "A")
    project_b = repo.create_project("owner-a", "B")
    default_conversations = [repo.create_conversation("owner-a") for _ in range(2)]
    project_a_conversations = [repo.create_conversation("owner-a", project_a.project_id) for _ in range(2)]
    project_b_conversation = repo.create_conversation("owner-a", project_b.project_id)
    for index, conversation in enumerate(default_conversations + project_a_conversations + [project_b_conversation]):
        _set_conversation(repo, conversation.conversation_id, f"2026-05-05T00:0{index}:00+00:00")

    _, default_cursor = repo.list_conversations("owner-a", limit=1)
    _, project_cursor = repo.list_conversations("owner-a", project_id=project_a.project_id, limit=1)
    assert default_cursor and project_cursor
    with pytest.raises(ValueError, match="invalid cursor"):
        repo.list_conversations("owner-a", project_id=project_a.project_id, cursor=default_cursor, limit=1)
    with pytest.raises(ValueError, match="invalid cursor"):
        repo.list_conversations("owner-a", cursor=project_cursor, limit=1)
    with pytest.raises(ValueError, match="invalid cursor"):
        repo.list_conversations("owner-a", project_id=project_b.project_id, cursor=project_cursor, limit=1)


def test_conversation_filter_api_has_stable_validation_and_global_archive_view(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    with patch("backend.app.memory.repository.default_database_path", return_value=database_path):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        repo = MemoryRepository(database_path)
        bound = repo.create_conversation("local-user", project_id, title="bound")
        unbound = repo.create_conversation("local-user", title="unbound")
        _set_conversation(repo, bound.conversation_id, "2026-05-04T00:02:00+00:00", "archived")
        _set_conversation(repo, unbound.conversation_id, "2026-05-04T00:01:00+00:00", "archived")

        response = client.get("/api/conversations?status=archived")
        assert response.status_code == 200
        assert {item["conversation_id"] for item in response.json()["conversations"]} == {bound.conversation_id, unbound.conversation_id}

        response = client.get("/api/conversations?unbound_only=true")
        assert response.status_code == 200
        assert {item["conversation_id"] for item in response.json()["conversations"]} == {unbound.conversation_id}

        invalid = client.get("/api/conversations?status=deleted")
        assert invalid.status_code == 400
        assert invalid.json()["detail"]["code"] == "INVALID_CONVERSATION_FILTER"
        conflict = client.get(f"/api/conversations?project_id={project_id}&unbound_only=true")
        assert conflict.status_code == 400
        assert conflict.json()["detail"]["code"] == "INVALID_CONVERSATION_FILTER"
