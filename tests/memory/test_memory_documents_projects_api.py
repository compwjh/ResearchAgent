"""GET /api/memory-documents/projects 契约（TDD）。

用户裁决：只展示 active 项目、所有 active 项目一次性全部列出、已删除项目不展示、
``projects/`` 下无项目记录的孤儿 md 不展示。既有 GET/PUT /api/memory-documents
契约（含 _memory_document_context 的 active 校验与 OCC revision）保持冻结。
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app.api.routes_conversations import _MEMORY_DOCUMENT_EXCERPT_CHARS
from backend.app.main import app
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.bootstrap import override_provider


def _write_project_md(memory_dir, project_id: str, content: str):
    projects_dir = memory_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{project_id}.md").write_text(content, encoding="utf-8")


def test_lists_all_active_projects_and_excludes_deleted_archived_and_orphans(
    tmp_path, _isolate_default_memory_dir
):
    memory_dir = _isolate_default_memory_dir
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    p1 = repo.create_project(OWNER_ID, "项目甲")
    p2 = repo.create_project(OWNER_ID, "项目乙")
    p3 = repo.create_project(OWNER_ID, "项目丙（无 md）")
    deleted = repo.create_project(OWNER_ID, "已删除项目")
    repo.update_project(deleted.project_id, OWNER_ID, status="deleted")
    archived = repo.create_project(OWNER_ID, "归档项目")
    repo.update_project(archived.project_id, OWNER_ID, status="archived")

    content_a = "- 甲的一条记忆\n- 甲的第二条记忆\n"
    content_b = ""
    _write_project_md(memory_dir, p1.project_id, content_a)
    _write_project_md(memory_dir, p2.project_id, content_b)
    _write_project_md(memory_dir, deleted.project_id, "- 已删除项目不该出现\n")
    _write_project_md(memory_dir, archived.project_id, "- 归档项目不该出现\n")
    # 孤儿 md：磁盘上有文件，但 projects 表里没有对应记录。
    (memory_dir / "projects" / "proj-alpha.md").write_text("孤儿甲", encoding="utf-8")
    (memory_dir / "projects" / "proj-beta.md").write_text("孤儿乙", encoding="utf-8")

    with override_provider("memory_repository", repo):
        response = TestClient(app).get("/api/memory-documents/projects")

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list), "响应体必须是数组"
    ids = [item["project_id"] for item in body]
    assert set(ids) == {p1.project_id, p2.project_id, p3.project_id}
    assert deleted.project_id not in ids
    assert archived.project_id not in ids
    assert "proj-alpha" not in str(body) and "proj-beta" not in str(body)

    by_id = {item["project_id"]: item for item in body}
    expected_fields = {
        "project_id", "project_name", "document", "content_excerpt",
        "content_length", "revision", "updated_at",
    }
    for item in body:
        assert set(item) == expected_fields

    a = by_id[p1.project_id]
    assert a["project_name"] == "项目甲"
    assert a["document"] == f"projects/{p1.project_id}.md"
    assert a["content_excerpt"] == content_a
    assert a["content_length"] == len(content_a)
    assert a["revision"] == hashlib.sha256(content_a.encode("utf-8")).hexdigest()
    assert a["updated_at"]

    b = by_id[p2.project_id]
    assert b["content_excerpt"] == ""
    assert b["content_length"] == 0
    assert b["revision"] == hashlib.sha256(b"").hexdigest()

    # active 但没有 md 文件的项目仍应列出（缺失文件 = 空文档，spec-038 契约）。
    c = by_id[p3.project_id]
    assert c["content_length"] == 0
    assert c["revision"] == hashlib.sha256(b"").hexdigest()


def test_long_content_excerpt_is_a_bounded_prefix(tmp_path, _isolate_default_memory_dir):
    memory_dir = _isolate_default_memory_dir
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project(OWNER_ID, "长记忆项目")
    content = "界" * 300
    _write_project_md(memory_dir, project.project_id, content)

    with override_provider("memory_repository", repo):
        body = TestClient(app).get("/api/memory-documents/projects").json()

    item = next(entry for entry in body if entry["project_id"] == project.project_id)
    assert item["content_length"] == 300, "content_length 必须是全文长度，不是截断后长度"
    assert 0 < len(item["content_excerpt"]) < 300
    # LOW-3：把常量改成 1 或 299 不再能全绿；上限必须被逐字锁定。
    assert len(item["content_excerpt"]) == _MEMORY_DOCUMENT_EXCERPT_CHARS
    assert content.startswith(item["content_excerpt"]), "excerpt 必须是正文前缀"


def test_exactly_excerpt_limit_chars_is_not_truncated(tmp_path, _isolate_default_memory_dir):
    """LOW-3 边界：正文恰好等于上限时不截断、不补省略符。"""
    memory_dir = _isolate_default_memory_dir
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project(OWNER_ID, "恰好上限项目")
    content = "界" * _MEMORY_DOCUMENT_EXCERPT_CHARS
    _write_project_md(memory_dir, project.project_id, content)

    with override_provider("memory_repository", repo):
        body = TestClient(app).get("/api/memory-documents/projects").json()

    item = next(entry for entry in body if entry["project_id"] == project.project_id)
    assert len(content) == _MEMORY_DOCUMENT_EXCERPT_CHARS
    assert item["content_length"] == _MEMORY_DOCUMENT_EXCERPT_CHARS
    assert len(item["content_excerpt"]) == _MEMORY_DOCUMENT_EXCERPT_CHARS
    assert item["content_excerpt"] == content


def test_one_unreadable_project_is_degraded_without_hiding_other_projects(
    tmp_path, _isolate_default_memory_dir
):
    """MEDIUM-1：单个 md 损坏不得把整表打成 503，其余 active 项目仍全量可见。"""
    memory_dir = _isolate_default_memory_dir
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    good_a = repo.create_project(OWNER_ID, "正常项目甲")
    bad = repo.create_project(OWNER_ID, "损坏文档项目")
    good_b = repo.create_project(OWNER_ID, "正常项目乙")
    _write_project_md(memory_dir, good_a.project_id, "- 甲正常\n")
    _write_project_md(memory_dir, good_b.project_id, "- 乙正常\n")
    # 非法 UTF-8：read_document 的 _strict_read_path 抛 MemoryDocumentUnavailableError。
    (memory_dir / "projects" / f"{bad.project_id}.md").write_bytes(b"\xff\xfe\x80")

    with override_provider("memory_repository", repo):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/memory-documents/projects"
        )

    assert response.status_code == 200, response.text
    body = response.json()
    by_id = {item["project_id"]: item for item in body}
    assert set(by_id) == {good_a.project_id, bad.project_id, good_b.project_id}
    assert by_id[good_a.project_id]["content_excerpt"] == "- 甲正常\n"
    assert by_id[good_b.project_id]["content_excerpt"] == "- 乙正常\n"
    failed = by_id[bad.project_id]
    assert failed["available"] is False
    assert failed["error"] == "MEMORY_DOCUMENT_UNAVAILABLE"
    assert failed["content_excerpt"] == ""


def test_project_with_null_updated_at_is_listed_with_null(
    tmp_path, _isolate_default_memory_dir, monkeypatch
):
    """MEDIUM-1 第二触发条件：历史 NULL 行不得让 isoformat() 抛 AttributeError。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    null_row = repo.create_project(OWNER_ID, "历史无更新时间项目")
    normal = repo.create_project(OWNER_ID, "正常项目")
    # 当前 schema 的 projects.updated_at 有 NOT NULL 约束，历史 NULL 行只可能来自旧库；
    # 用只读投影构造等价输入，仍走真实 endpoint / 真实 MarkdownMemoryStore。
    monkeypatch.setattr(
        repo, "list_active_projects",
        lambda owner_id: [replace(null_row, updated_at=None), normal],
    )

    with override_provider("memory_repository", repo):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/memory-documents/projects"
        )

    assert response.status_code == 200, response.text
    by_id = {item["project_id"]: item for item in response.json()}
    assert set(by_id) == {null_row.project_id, normal.project_id}
    assert by_id[null_row.project_id]["updated_at"] is None
    assert by_id[normal.project_id]["updated_at"]


def test_listing_returns_stable_503_when_repository_unavailable():
    """回归 #11：端点内新增的外部依赖调用必须纳入 try/except，保持 503 稳定错误体。"""

    class FailingRepository:
        def list_active_projects(self, owner_id):
            raise RuntimeError("db unavailable")

    with override_provider("memory_repository", FailingRepository()):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/memory-documents/projects"
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MEMORY_DOCUMENT_UNAVAILABLE"


def test_existing_single_document_active_guard_is_not_relaxed(
    tmp_path, _isolate_default_memory_dir
):
    """新接口不得放宽 _memory_document_context 的 active 校验（spec-038 冻结合同）。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    archived = repo.create_project(OWNER_ID, "归档项目")
    repo.update_project(archived.project_id, OWNER_ID, status="archived")

    with override_provider("memory_repository", repo):
        response = TestClient(app).get(
            "/api/memory-documents",
            params={"scope": "project", "project_id": archived.project_id},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROJECT_NOT_ACTIVE"
