import hashlib
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api import routes_kb
from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
from backend.app.main import app


def _fixture(tmp_path: Path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    result = application.create_uploaded_document(
        "reindex.md", "text/markdown", b"# reindex\n", meta_path=meta, papers_dir=papers
    )
    return result["document"], meta, papers


def _generation_fixture(tmp_path: Path):
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    result = application.create_uploaded_document(
        "reindex.md", "text/markdown", b"# reindex\n", meta_path=meta, papers_dir=papers
    )
    document = result["document"]
    finalizer = FinalizeBundleStore(tmp_path)
    finalizer.stage(
        "generation-test",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    finalizer.commit("generation-test")
    return document, meta, papers


def test_reindex_reads_immutable_source_and_never_writes_source(tmp_path):
    document, meta, papers = _generation_fixture(tmp_path)
    source = papers / document["stored_name"]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    captured = []

    def capture_submit(document_id, chunker, runner):
        captured.append((document_id, chunker, runner))
        return True

    with patch.object(application, "submit_index_task", side_effect=capture_submit), patch.object(
        application.GenerationBoundIndexPort, "index_document", return_value={}
    ) as indexer:
        result = application.submit_document_reindex(
            document["document_id"], "v1", meta_path=meta, papers_dir=papers,
            destination_collection="papers_rebuild_live",
        )
        captured[0][2](lambda _progress: None)

    assert result["submitted"] == {"v1": True}
    assert captured and captured[0][0] == document["document_id"]
    assert indexer.call_args.kwargs["meta_path"] == meta
    assert application.GenerationBoundIndexPort("papers_rebuild_live").destination_collection == "papers_rebuild_live"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert source.exists()


def test_reindex_generation_mismatch_keeps_api_gate(tmp_path):
    client = TestClient(app)
    document = {"schema_version": "knowledge-document-v1", "document_id": "doc-1"}
    gate = routes_kb._document_error(409, "INDEX_REBUILD_REQUIRED", "rebuild", document_id="doc-1")
    with patch.object(routes_kb, "load_papers_strict", return_value=[document]), patch.object(
        routes_kb, "_require_generation", return_value=gate
    ), patch.object(routes_kb, "submit_document_reindex", side_effect=AssertionError("gate must run first")):
        response = client.post("/api/kb/documents/doc-1/reindex", json={"chunker": "v1"})
    assert response.status_code == 409
    assert response.json()["error_code"] == "INDEX_REBUILD_REQUIRED"


def test_reindex_partial_submission_is_stable_conflict(tmp_path):
    document, meta, papers = _generation_fixture(tmp_path)
    with patch.object(application, "submit_index_task", side_effect=[True, False]):
        result = application.submit_document_reindex(
            document["document_id"], "all", meta_path=meta, papers_dir=papers,
            destination_collection="papers_rebuild_live",
        )
    assert result["submitted"] == {"v1": True, "v2": False}


def test_successful_reindex_keeps_generation_marker_metadata_hash_valid(tmp_path, monkeypatch):
    document, meta, papers = _generation_fixture(tmp_path)
    captured = []

    class Client:
        def collection_exists(self, _name):
            return False

        def create_collection(self, **_kwargs):
            return None

        def upsert(self, **_kwargs):
            return None

    monkeypatch.setattr(application.GenerationBoundIndexPort, "index_document", index_module.GenerationBoundIndexPort.index_document)
    monkeypatch.setattr(application, "submit_index_task", lambda *args: captured.append(args) or True)
    monkeypatch.setattr(index_module, "extract_pages_normalized", lambda _path: [(1, "x" * 120)])
    monkeypatch.setattr(index_module, "build_chunks_v1", lambda _pages: [index_module.Chunk("x" * 120, 1, 0)])
    monkeypatch.setattr(index_module, "embed_texts", lambda _texts: [[0.1, 0.2]])
    monkeypatch.setattr(index_module, "encode_sparse", lambda _text: {"indices": [1], "values": [1.0]})

    application.submit_document_reindex(
        document["document_id"], "v1", meta_path=meta, papers_dir=papers,
        client=Client(), destination_collection="papers_rebuild_live",
    )
    captured[0][2](lambda _progress: None)
    marker = FinalizeBundleStore(tmp_path).require_generation()
    assert marker["alias_target"] == "papers_rebuild_live"
