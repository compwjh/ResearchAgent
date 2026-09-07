"""Spec015 Task08: 旧知识库物理文件的离线集成回归。

测试使用临时 papers.json/论文原件和内存 Qdrant 替身，不依赖公网、Ollama
或项目 data 目录；重点验证旧 ``file_name`` 记录与 Spec015 新命名记录隔离。
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf
from fastapi.testclient import TestClient
from qdrant_client import models

from backend.app.api import routes_kb as routes
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import retrieve as retrieve_module
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.main import app


class FakeQdrant:
    """只实现本轮检索、重建、删除所需的 Qdrant 接口。"""

    def __init__(self, points=()):
        self.points = list(points)
        self.upserted = []
        self.deleted_paper_ids = []

    def collection_exists(self, _name):
        return True

    def query_points(self, **_kwargs):
        return SimpleNamespace(points=list(self.points))

    def upsert(self, *, points, **_kwargs):
        self.upserted.extend(points)

    def delete(self, *, points_selector, **_kwargs):
        # 服务删除通过 FilterSelector，记录调用即可；路由断言 paper_id。
        self.deleted_paper_ids.append(points_selector)


def _write_pdf(path: Path, text: str = "Legacy KB retrieval compatibility. ") -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text * 12)
    document.save(str(path))
    document.close()


def _legacy_record(paper_id="legacy-001", file_name="shared.pdf"):
    return {
        "paper_id": paper_id,
        "file_name": file_name,
        "status": "indexed",
        "page_count": 1,
        "chunk_count": 1,
        "uploaded_at": "2026-09-01T10:00:00",
    }


def _new_record(paper_id="new-001"):
    return {
        "paper_id": paper_id,
        "file_name": "shared.pdf",
        "stored_name": "2025-CCS-shared.pdf",
        "status": "indexed",
        "page_count": 1,
        "chunk_count": 1,
        "title": "A newly imported paper",
    }


def _configure_store(tmp_path, records):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    meta_path = tmp_path / "papers.json"
    meta_path.write_text(json.dumps(records), encoding="utf-8")
    return papers_dir, meta_path


def _store_patches(papers_dir, meta_path):
    return (
        patch.object(store_module, "KB_PAPERS_DIR", papers_dir),
        patch.object(store_module, "KB_META_PATH", meta_path),
        patch.object(routes, "KB_PAPERS_DIR", papers_dir),
    )


def _enter_patches(patches):
    for item in patches:
        item.start()


def _exit_patches(patches):
    for item in reversed(patches):
        item.stop()


def test_legacy_record_is_listed_and_ask_reads_legacy_qdrant_hit(tmp_path):
    papers_dir, meta_path = _configure_store(tmp_path, [_legacy_record()])
    _write_pdf(papers_dir / "legacy-001.pdf")
    point = SimpleNamespace(
        id="legacy-point",
        score=0.9,
        payload={
            "paper_id": "legacy-001",
            "file_name": "shared.pdf",
            "page": 1,
            "chunk_index": 0,
            "text": "Legacy KB retrieval compatibility content.",
        },
    )
    fake_qdrant = FakeQdrant([point])
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        client = TestClient(app)
        listed = client.get("/api/kb/papers")
        assert listed.status_code == 200
        assert listed.json()["papers"][0]["paper_id"] == "legacy-001"
        assert listed.json()["papers"][0]["file_name"] == "shared.pdf"

        chat_run = SimpleNamespace(
            events=[{"type": "token", "content": "旧论文回答"}],
            result=SimpleNamespace(),
            route="mock",
        )
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1]]), \
             patch.object(retrieve_module, "encode_sparse", return_value=Mock()), \
             patch.object(
                 retrieve_module,
                 "rerank_hits",
                 return_value=SimpleNamespace(
                     hits=[retrieve_module._to_hit(point)],
                     used=False,
                     degraded=True,
                     reason="disabled",
                     elapsed_ms=0.0,
                     scores_by_original_index=None,
                 ),
             ), \
             patch.object(
                 routes,
                 "hybrid_search",
                 side_effect=lambda question, **kwargs: retrieve_module.hybrid_search(
                     question, client=fake_qdrant, **kwargs
                 ),
             ), \
             patch.object(routes, "get_available_models", return_value=["qwen3.5:9b"]), \
             patch.object(routes, "run_chat", return_value=chat_run), \
             patch.object(routes, "record_ollama_generation"), \
             patch.object(routes, "flush"):
            asked = client.post(
                "/api/kb/ask",
                json={"question": "旧论文讲了什么？", "model": "qwen3.5:9b"},
            )
        assert asked.status_code == 200
        assert "legacy-001" in asked.text
        assert "shared.pdf" in asked.text
        assert "旧论文回答" in asked.text
    finally:
        _exit_patches(patches)


def test_reindex_uses_legacy_physical_path_and_real_pdf_with_fake_qdrant(tmp_path):
    record = _legacy_record()
    papers_dir, meta_path = _configure_store(tmp_path, [record])
    legacy_path = papers_dir / "legacy-001.pdf"
    _write_pdf(legacy_path)
    fake_qdrant = FakeQdrant()
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        with patch.object(index_module, "embed_texts", side_effect=lambda texts: [[0.1, 0.2]] * len(texts)), \
             patch.object(
                 index_module,
                 "encode_sparse",
                 return_value=models.SparseVector(indices=[1], values=[1.0]),
             ):
            result = index_module.index_paper_chunker(
                record, legacy_path, "v1", client=fake_qdrant, meta_path=meta_path
            )
        assert result["paper_id"] == "legacy-001"
        assert result["chunkers"]["v1"]["status"] == "indexed", result["chunkers"]["v1"].get("error")
        assert fake_qdrant.upserted
        assert all(point.payload["paper_id"] == "legacy-001" for point in fake_qdrant.upserted)

        client = TestClient(app)
        with patch.object(routes, "submit_index_task", return_value=True) as submit, \
             patch.object(routes, "update_chunker_state"):
            response = client.post("/api/kb/papers/legacy-001/reindex", json={"chunker": "v1"})
        assert response.status_code == 200
        assert submit.call_count == 1
        assert response.json()["submitted"] == {"v1": True}
    finally:
        _exit_patches(patches)


def test_missing_legacy_file_returns_404_without_submitting_reindex(tmp_path):
    papers_dir, meta_path = _configure_store(tmp_path, [_legacy_record()])
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        with patch.object(routes, "submit_index_task") as submit:
            response = TestClient(app).post(
                "/api/kb/papers/legacy-001/reindex", json={"chunker": "all"}
            )
        assert response.status_code == 404
        assert "原件" in response.json()["detail"]
        submit.assert_not_called()
    finally:
        _exit_patches(patches)


def test_corrupt_legacy_metadata_degrades_to_empty_list(tmp_path):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    meta_path = tmp_path / "papers.json"
    meta_path.write_text('{"broken":', encoding="utf-8")
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        response = TestClient(app).get("/api/kb/papers")
        assert response.status_code == 200
        assert response.json() == {"papers": []}
    finally:
        _exit_patches(patches)


def test_deleting_legacy_same_name_does_not_remove_new_record(tmp_path):
    records = [_legacy_record(), _new_record()]
    papers_dir, meta_path = _configure_store(tmp_path, records)
    old_path = papers_dir / "legacy-001.pdf"
    new_path = papers_dir / "2025-CCS-shared.pdf"
    _write_pdf(old_path, "old paper ")
    _write_pdf(new_path, "new paper ")
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        fake_qdrant = FakeQdrant()
        with patch.object(routes, "delete_paper", side_effect=lambda paper_id: fake_qdrant.deleted_paper_ids.append(paper_id)):
            response = TestClient(app).delete("/api/kb/papers/legacy-001")
        assert response.status_code == 200
        assert response.json() == {"deleted": True, "vectors_removed": True}
        assert fake_qdrant.deleted_paper_ids == ["legacy-001"]
        assert not old_path.exists()
        assert new_path.exists()
        remaining = store_module.load_papers(meta_path)
        assert [item["paper_id"] for item in remaining] == ["new-001"]
    finally:
        _exit_patches(patches)
