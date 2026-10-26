"""Contract tests for the fixed Markdown memory-document and pending seams."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.memory.markdown_store import (
    MarkdownMemoryStore,
    MemoryDocumentConflictError,
    MemoryDocumentPathError,
    MemoryDocumentTooLargeError,
    MemoryDocumentUnavailableError,
    PendingChangedError,
    PendingIdConflictError,
)


def _revision(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_document_read_missing_is_empty_hash_without_creating_file(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")

    document = store.read_document(scope="global", project_id=None)

    assert document == {
        "scope": "global",
        "project_id": None,
        "document": "MEMORY.md",
        "content": "",
        "revision": _revision(""),
    }
    assert not (tmp_path / "memory" / "MEMORY.md").exists()


def test_document_write_preserves_raw_unicode_and_uses_revision_cas(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    empty_revision = _revision("")

    written = store.write_document(
        scope="global", project_id=None, content="  前后空白\n不归一化", revision=empty_revision
    )

    assert written["content"] == "  前后空白\n不归一化"
    assert written["revision"] == _revision(written["content"])
    assert store.read_document(scope="global", project_id=None)["content"] == written["content"]
    with pytest.raises(MemoryDocumentConflictError) as conflict:
        store.write_document(scope="global", project_id=None, content="new", revision=empty_revision)
    assert conflict.value.current_content == written["content"]
    assert conflict.value.current_revision == written["revision"]


def test_document_write_enforces_unicode_codepoint_limit(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    revision = _revision("")

    store.write_document(scope="global", project_id=None, content="界" * 65536, revision=revision)
    with pytest.raises(MemoryDocumentTooLargeError):
        store.write_document(scope="global", project_id=None, content="界" * 65537, revision=_revision("界" * 65536))


def test_document_project_path_rejects_symlink_outside_projects(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.projects_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    (store.projects_dir / "project-a.md").symlink_to(outside)

    with pytest.raises(ValueError):
        store.read_document(scope="project", project_id="project-a")


def test_document_project_path_rejects_symlinked_projects_root(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    outside = tmp_path / "outside"
    outside.mkdir()
    store.memory_dir.mkdir(parents=True)
    (store.memory_dir / "projects").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        store.read_document(scope="project", project_id="project-a")


def test_document_global_symlink_outside_root_rejected_for_read_and_write(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.memory_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("外部原文", encoding="utf-8")
    store.memory_path.symlink_to(outside)

    with pytest.raises(MemoryDocumentPathError):
        store.read_document(scope="global", project_id=None)
    with pytest.raises(MemoryDocumentPathError):
        store.write_document(
            scope="global",
            project_id=None,
            content="不得越界",
            revision=_revision("外部原文"),
        )
    assert outside.read_text(encoding="utf-8") == "外部原文"


def test_memory_document_api_rejects_global_symlink_without_touching_target(tmp_path: Path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("外部原文", encoding="utf-8")
    (memory_dir / "MEMORY.md").symlink_to(outside)

    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"), patch(
        "backend.app.memory.markdown_store.MEMORY_DIR", memory_dir
    ):
        client = TestClient(app)
        read_response = client.get("/api/memory-documents?scope=global")
        write_response = client.put(
            "/api/memory-documents?scope=global",
            json={"content": "不得越界", "revision": _revision("外部原文")},
        )

    assert read_response.status_code == write_response.status_code == 400
    assert read_response.json()["detail"]["code"] == "MEMORY_DOCUMENT_PATH_INVALID"
    assert write_response.json()["detail"]["code"] == "MEMORY_DOCUMENT_PATH_INVALID"
    assert outside.read_text(encoding="utf-8") == "外部原文"


def test_document_path_lock_uses_canonical_absolute_path(tmp_path: Path):
    from backend.app.memory import markdown_store

    relative = tmp_path / "memory" / ".." / "memory" / "MEMORY.md"
    canonical = tmp_path / "memory" / "MEMORY.md"
    assert markdown_store._lock_for(relative) is markdown_store._lock_for(canonical)


def test_pending_explicit_id_is_stable_idempotent_and_conflict_safe(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")

    first = store.add_pending(content="待确认", project_id="project-a", item_id="item-1")
    second = store.add_pending(content="待确认", project_id="project-a", item_id="item-1")
    assert first == second == "item-1"
    assert len(store.list_pending()) == 1
    with pytest.raises(PendingIdConflictError):
        store.add_pending(content="不同内容", project_id="project-a", item_id="item-1")
    with pytest.raises(ValueError):
        store.add_pending(content="x", item_id="bad/id")


def test_resolve_pending_append_failure_retains_item_and_ignore_consumes_only_pending(tmp_path: Path, monkeypatch):
    store = MarkdownMemoryStore(tmp_path / "memory")
    item_id = store.add_pending(content="待确认", item_id="item-1")

    def fail_append(**_kwargs):
        raise OSError("append failed")

    monkeypatch.setattr(store, "append_memory", fail_append)
    with pytest.raises(OSError):
        store.resolve_pending(item_id, scope="global", project_id=None)
    assert [item.item_id for item in store.list_pending()] == [item_id]

    store.resolve_pending(item_id, scope="global", project_id=None, decision="ignore")
    assert store.list_pending() == []
    assert not store.memory_path.exists()


def test_resolve_pending_decode_failure_retains_pending_and_target(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.memory_dir.mkdir(parents=True)
    original = b"\xff"
    store.memory_path.write_bytes(original)
    item_id = store.add_pending(content="不得覆盖旧文件", item_id="item-1")

    with pytest.raises(MemoryDocumentUnavailableError):
        store.resolve_pending(item_id, scope="global", project_id=None)

    assert store.memory_path.read_bytes() == original
    assert [item.item_id for item in store.list_pending()] == [item_id]


def test_resolve_pending_rejects_global_symlink_without_consuming_pending(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.memory_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("外部原文", encoding="utf-8")
    store.memory_path.symlink_to(outside)
    item_id = store.add_pending(content="不得越界", item_id="item-1")

    with pytest.raises(MemoryDocumentPathError):
        store.resolve_pending(item_id, scope="global", project_id=None)

    assert outside.read_text(encoding="utf-8") == "外部原文"
    assert [item.item_id for item in store.list_pending()] == [item_id]


def test_resolve_pending_rejects_changed_project_and_append_is_idempotent(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    item_id = store.add_pending(content="同一条", project_id="project-a", item_id="item-1")

    with pytest.raises(PendingChangedError):
        store.resolve_pending(item_id, scope="project", project_id="project-b")
    store.resolve_pending(item_id, scope="project", project_id="project-a")
    store.append_memory(scope="project", project_id="project-a", content="同一条")
    assert store.read_project("project-a").count("同一条") == 1


def test_document_strict_read_maps_decode_and_io_failures(tmp_path: Path, monkeypatch):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.memory_dir.mkdir(parents=True)
    store.memory_path.write_bytes(b"\xff")
    with pytest.raises(MemoryDocumentUnavailableError):
        store.read_document(scope="global", project_id=None)

    monkeypatch.setattr(Path, "read_bytes", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(MemoryDocumentUnavailableError):
        store.read_document(scope="global", project_id=None)


def test_memory_document_invalid_json_is_stable_bad_request(tmp_path: Path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        response = TestClient(app).put(
            "/api/memory-documents?scope=global",
            content=b'{"content":',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_MEMORY_DOCUMENT_REQUEST"
