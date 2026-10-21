"""Spec015 Task08: 旧知识库物理文件的离线集成回归。

测试使用临时 papers.json/论文原件和内存 Qdrant 替身，不依赖公网、Ollama
或项目 data 目录；重点验证旧 ``file_name`` 记录与 Spec015 新命名记录隔离。
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf
from fastapi.testclient import TestClient
from qdrant_client import models

from backend.app.api import routes_kb as routes
from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import retrieve as retrieve_module
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
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
    page.insert_textbox((72, 72, 540, 200), "\n".join([text * 3] * 4))
    # Canonical publication now requires a proven-safe active-feature scan;
    # make this generated PDF use the same passive local destination shape as
    # the Spec018 safety fixtures instead of relying on parser fallback.
    document.xref_set_key(document.pdf_catalog(), "OpenAction", "[4 0 R /Fit]")
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


def _canonical_record(paper_id="legacy-001", stored_name="legacy-001.pdf"):
    """Build the minimum v1 document record needed by canonical APIs."""
    return {
        "schema_version": "knowledge-document-v1",
        "migration_version": "018-document-v1",
        "document_id": paper_id,
        "file_name": "shared.pdf",
        "stored_name": stored_name,
        "media_type": "application/pdf",
        "source_immutable": True,
        "source_sha256": None,
        "indexed_source_sha256": None,
        "source_hash_state": "legacy_unknown",
        "status": "indexed",
        "created_at": "2026-09-01T10:00:00+00:00",
        "page_count": 1,
        "chunk_count": 0,
        "chunkers": {
            "v1": {"status": "indexed", "chunk_count": 0, "progress": 100, "error": None},
            "v2": {"status": "pending", "chunk_count": 0, "progress": 0, "error": None},
        },
        "error": None,
    }


def _commit_generation(tmp_path, records):
    """Publish the marker used by generation-bound application seams."""
    FinalizeBundleStore(tmp_path).stage(
        "legacy-migration-generation",
        candidate_collection="papers_rebuild_live",
        metadata=records,
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(tmp_path).commit("legacy-migration-generation")


def _configure_store(tmp_path, records):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    meta_path = tmp_path / "papers.json"
    meta_path.write_text(json.dumps(records), encoding="utf-8")
    return papers_dir, meta_path


def _configure_canonical_store(tmp_path, records):
    """Build the same ``data/kb`` layout used by generation-bound storage."""
    live_root = tmp_path / "data" / "kb"
    papers_dir = live_root / "papers"
    papers_dir.mkdir(parents=True)
    meta_path = live_root / "papers.json"
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


def test_reindex_uses_canonical_application_and_route_with_fake_qdrant(tmp_path):
    record = _canonical_record()
    papers_dir, meta_path = _configure_canonical_store(tmp_path, [record])
    legacy_path = papers_dir / "legacy-001.pdf"
    _write_pdf(legacy_path)
    record["source_sha256"] = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    store_module.save_papers([record], meta_path)
    _commit_generation(tmp_path, [record])
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
                record,
                legacy_path,
                "v1",
                client=fake_qdrant,
                meta_path=meta_path,
                destination_collection="papers_rebuild_live",
            )
        assert result["document_id"] == "legacy-001"
        assert result["chunkers"]["v1"]["status"] == "indexed", result["chunkers"]["v1"].get("error")
        assert fake_qdrant.upserted
        assert all(point.payload["paper_id"] == "legacy-001" for point in fake_qdrant.upserted)

        client = TestClient(app)
        with patch.object(routes, "load_papers_strict", return_value=[record]), \
             patch.object(routes, "_require_generation", return_value=None), \
             patch.object(
                 routes,
                 "submit_document_reindex",
                 return_value={"task_id": "migration-task", "submitted": {"v1": True}},
             ) as submit:
            response = client.post(
                "/api/kb/documents/legacy-001/reindex", json={"chunker": "v1"}
            )
        assert response.status_code == 202
        submit.assert_called_once_with("legacy-001", "v1")
        assert response.json()["status"] == "queued"
    finally:
        _exit_patches(patches)


def test_missing_canonical_file_returns_404_without_legacy_helper(tmp_path):
    record = _canonical_record()
    papers_dir, meta_path = _configure_store(tmp_path, [record])
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        with patch.object(routes, "load_papers_strict", return_value=[record]), \
             patch.object(routes, "_require_generation", return_value=None), \
             patch.object(
                 routes,
                 "submit_document_reindex",
                 side_effect=lambda document_id, chunker: application.submit_document_reindex(
                     document_id,
                     chunker,
                     meta_path=meta_path,
                     papers_dir=papers_dir,
                 ),
             ) as submit:
            response = TestClient(app).post(
                "/api/kb/documents/legacy-001/reindex", json={"chunker": "all"}
            )
        assert response.status_code == 404
        assert response.json()["error_code"] == "SOURCE_NOT_FOUND"
        submit.assert_called_once_with("legacy-001", "all")
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


def test_canonical_delete_does_not_remove_legacy_same_name_record(tmp_path):
    canonical = _canonical_record("new-001", "2025-CCS-shared.pdf")
    records = [_legacy_record(), canonical]
    papers_dir, meta_path = _configure_store(tmp_path, records)
    old_path = papers_dir / "legacy-001.pdf"
    new_path = papers_dir / "2025-CCS-shared.pdf"
    _write_pdf(old_path, "old paper ")
    _write_pdf(new_path, "new paper ")
    canonical["source_sha256"] = hashlib.sha256(new_path.read_bytes()).hexdigest()
    store_module.save_papers(records, meta_path)
    _commit_generation(tmp_path, records)
    patches = _store_patches(papers_dir, meta_path)
    _enter_patches(patches)
    try:
        with patch.object(application.GenerationBoundIndexPort, "delete_document", return_value=None), \
             patch.object(
                 routes,
                 "delete_document",
                 side_effect=lambda document_id: application.delete_document(
                     document_id,
                     meta_path=meta_path,
                     papers_dir=papers_dir,
                     manifest_root=tmp_path / "data" / "kb",
                     destination_collection="papers_rebuild_live",
                 ),
             ) as delete:
            response = TestClient(app).delete("/api/kb/documents/new-001")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        delete.assert_called_once_with("new-001")
        assert old_path.exists()
        assert not new_path.exists()
        remaining = store_module.load_papers(meta_path)
        assert [item["paper_id"] for item in remaining] == ["legacy-001"]
    finally:
        _exit_patches(patches)
