import hashlib
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.app.api import routes_kb
from backend.app.knowledge_base.application import InspectionManifest, create_uploaded_document
from backend.app.main import app


def test_upload_markdown_creates_canonical_immutable_record(tmp_path: Path):
    result = create_uploaded_document(
        "readme.md", "text/markdown", b"\xef\xbb\xbf# Heading\r\n", meta_path=tmp_path / "papers.json", papers_dir=tmp_path / "papers"
    )
    document = result["document"]
    assert document["schema_version"] == "knowledge-document-v1"
    assert document["page_count"] is None
    assert document["source_sha256"] == hashlib.sha256(b"\xef\xbb\xbf# Heading\r\n").hexdigest()
    assert (tmp_path / "papers" / document["stored_name"]).read_bytes() == b"\xef\xbb\xbf# Heading\r\n"


def test_upload_same_hash_deduplicates_without_replacing_source(tmp_path: Path):
    kwargs = {"meta_path": tmp_path / "papers.json", "papers_dir": tmp_path / "papers"}
    first = create_uploaded_document("a.md", "text/markdown", b"# same\n", **kwargs)
    second = create_uploaded_document("other.md", "text/markdown", b"# same\n", **kwargs)
    assert second["deduplicated"] is True
    assert second["document"]["document_id"] == first["document"]["document_id"]
    assert len(list((tmp_path / "papers").iterdir())) == 1


def test_documents_list_has_cursor_and_etag():
    client = TestClient(app)
    records = [
        {"schema_version": "knowledge-document-v1", "document_id": "d1", "file_name": "a.md", "status": "pending", "chunkers": {}},
        {"schema_version": "knowledge-document-v1", "document_id": "d2", "file_name": "b.md", "status": "pending", "chunkers": {}},
    ]
    with patch.object(routes_kb, "load_papers_strict", return_value=records):
        response = client.get("/api/kb/documents?limit=1")
        assert response.status_code == 200
        assert response.json()["next_cursor"]
        cached = client.get("/api/kb/documents?limit=1", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304


def test_upload_route_returns_stable_unsupported_media_error():
    client = TestClient(app)
    response = client.post("/api/kb/documents/upload", files={"file": ("note.txt", b"x", "text/plain")})
    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_rejects_extension_and_mime_mismatch():
    client = TestClient(app)
    response = client.post(
        "/api/kb/documents/upload",
        files={"file": ("note.md", b"# note\n", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "application/pdf; charset=binary", "application/x-pdf", "application/octet-stream", ""],
)
def test_upload_accepts_common_pdf_mime_variants_when_magic_is_valid(content_type):
    client = TestClient(app)
    record = {
        "document_id": "pdf-variant",
        "media_type": "application/pdf",
        "file_name": "variant.pdf",
        "source_sha256": "a" * 64,
        "status": "pending",
        "chunkers": {},
    }
    with patch.object(
        routes_kb,
        "create_uploaded_document",
        return_value={"document": record, "task_id": None},
    ) as create:
        response = client.post(
            "/api/kb/documents/upload",
            files={"file": ("variant.pdf", b"%PDF-1.7\nvalid", content_type)},
        )
    assert response.status_code == 201
    create.assert_called_once_with("variant.pdf", "application/pdf", b"%PDF-1.7\nvalid")


def test_upload_rejects_non_pdf_mime_even_when_pdf_magic_is_present():
    client = TestClient(app)
    response = client.post(
        "/api/kb/documents/upload",
        files={"file": ("variant.pdf", b"%PDF-1.7\nvalid", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_source_route_forwards_range_and_head_headers():
    client = TestClient(app)
    source = type("Source", (), {"status": 206, "body": b"abc", "headers": {"ETag": '"sha256:x"', "Content-Range": "bytes 0-2/3"}})()
    with patch.object(routes_kb, "read_document_source", return_value=source):
        response = client.get("/api/kb/documents/d1/source", headers={"Range": "bytes=0-2"})
        head = client.head("/api/kb/documents/d1/source")
    assert response.status_code == 206
    assert response.content == b"abc"
    assert head.status_code == 206
    assert head.content == b""


def test_inspection_without_generation_is_explicit_rebuild_gate():
    client = TestClient(app)
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    # The real fixture may contain a completed generation marker after the
    # production rebuild.  Isolate this test's pre-generation contract at the
    # route boundary instead of mutating the shared runtime state.
    generation_gate = JSONResponse(
        status_code=409,
        content={"error_code": "INDEX_REBUILD_REQUIRED"},
    )
    with patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=generation_gate
    ):
        response = client.get("/api/kb/documents/d1/inspection")
    assert response.status_code == 409
    assert response.json()["error_code"] == "INDEX_REBUILD_REQUIRED"


def test_inspection_unknown_document_precedes_generation_gate():
    client = TestClient(app)
    with patch.object(routes_kb, "load_papers_strict", return_value=[]):
        response = client.get("/api/kb/documents/unknown/inspection")
    assert response.status_code == 404
    assert response.json()["error_code"] == "DOCUMENT_NOT_FOUND"


def test_inspection_building_has_stable_task_and_retry_contract(tmp_path: Path):
    client = TestClient(app)
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    with patch.object(routes_kb, "KB_DIR", tmp_path), patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=None
    ), patch.object(routes_kb.InspectionManifestStore, "read", side_effect=routes_kb.ManifestStoreError("MANIFEST_NOT_FOUND", status=404)):
        response = client.get("/api/kb/documents/d1/inspection")
    body = response.json()
    assert response.status_code == 202
    assert body["task_id"] and body["status"] == "building" and body["progress"] == 0
    assert response.headers["retry-after"] == "2"
    assert (tmp_path / "manifests" / "d1" / "v1.claim").is_file()


def test_inspection_ready_pages_all_arrays_and_supports_etag():
    client = TestClient(app)
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    manifest = InspectionManifest(
        {
            "document_id": "d1",
            "chunker": "v1",
            "mapping_algorithm_version": "source-anchor-v2",
            "blocks": [{"ordinal": i} for i in range(3)],
            "chunks": [{"chunk_index": i} for i in range(3)],
            "anchors": [{"chunk_index": i} for i in range(3)],
        }
    )
    with patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=None
    ), patch.object(routes_kb.InspectionManifestStore, "read", return_value=manifest):
        response = client.get("/api/kb/documents/d1/inspection?page_size=2")
        cached = client.get(
            "/api/kb/documents/d1/inspection?page_size=2",
            headers={"If-None-Match": response.headers["etag"]},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == {"blocks": 3, "chunks": 3, "anchors": 3}
    assert len(body["blocks"]) == len(body["chunks"]) == len(body["anchors"]) == 2
    assert body["next_cursor"]
    assert cached.status_code == 304


def test_inspection_legacy_mapping_version_is_rebuild_gate():
    client = TestClient(app)
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    with patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=None
    ), patch.object(
        routes_kb.InspectionManifestStore,
        "read",
        side_effect=routes_kb.ManifestStoreError("MANIFEST_MAPPING_VERSION_MISMATCH", status=409),
    ):
        response = client.get("/api/kb/documents/d1/inspection")
    assert response.status_code == 409
    assert response.json()["error_code"] == "INDEX_REBUILD_REQUIRED"
    assert response.json()["details"]["cause"] == "MAPPING_VERSION_MISMATCH"


def test_reindex_invalid_body_is_unified_400():
    client = TestClient(app)
    with patch.object(routes_kb, "_require_generation", return_value=None):
        response = client.post("/api/kb/documents/d1/reindex", json={"chunker": "bad"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_CHUNKER"


def test_reindex_non_object_body_is_unified_400():
    client = TestClient(app)
    response = client.post("/api/kb/documents/d1/reindex", json=["v1"])
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"
    assert "detail" not in response.json()


def test_upload_missing_file_is_unified_400():
    client = TestClient(app)
    response = client.post("/api/kb/documents/upload")
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"
    assert "detail" not in response.json()


def test_reindex_running_conflict_is_stable_409():
    client = TestClient(app)
    result = {"task_id": "task-1", "submitted": {"v1": False}}
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    with patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=None
    ), patch.object(
        routes_kb, "submit_document_reindex", return_value=result
    ):
        response = client.post("/api/kb/documents/d1/reindex", json={"chunker": "v1"})
    assert response.status_code == 409
    assert response.json()["error_code"] == "INDEX_ALREADY_RUNNING"


def test_reindex_source_hash_conflict_is_stable_409():
    client = TestClient(app)
    record = {"schema_version": "knowledge-document-v1", "document_id": "d1"}
    with patch.object(routes_kb, "load_papers_strict", return_value=[record]), patch.object(
        routes_kb, "_require_generation", return_value=None
    ), patch.object(
        routes_kb,
        "submit_document_reindex",
        side_effect=routes_kb.KnowledgeDocumentMigrationError("SOURCE_HASH_MISMATCH"),
    ):
        response = client.post("/api/kb/documents/d1/reindex", json={"chunker": "v1"})
    assert response.status_code == 409
    assert response.json()["error_code"] == "SOURCE_HASH_MISMATCH"


def test_reindex_unknown_document_precedes_generation_gate():
    client = TestClient(app)
    with patch.object(routes_kb, "load_papers_strict", return_value=[]), patch.object(
        routes_kb, "_require_generation", side_effect=AssertionError("generation gate must not run")
    ):
        response = client.post("/api/kb/documents/unknown/reindex", json={"chunker": "v1"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "DOCUMENT_NOT_FOUND"


def test_delete_pending_has_retry_location_and_details():
    client = TestClient(app)
    result = {"document_id": "d1", "status": "DELETE_PENDING", "tombstoned": True}
    with patch.object(routes_kb, "delete_document", return_value=result):
        response = client.delete("/api/kb/documents/d1")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "10"
    assert response.headers["location"] == "/api/kb/documents/d1"
    assert response.json()["details"]["retry_after_seconds"] == 10


def test_legacy_routes_only_forward_to_canonical_document_routes():
    """Compatibility routes must not regain the retired write pipeline."""
    upload_source = inspect.getsource(routes_kb.upload_kb_paper)
    reindex_source = inspect.getsource(routes_kb.reindex_kb_paper)
    delete_source = inspect.getsource(routes_kb.delete_kb_paper)
    forbidden = (
        "save_upload",
        "upsert_paper",
        "index_paper_chunker",
        "run_index_task_sync",
        "_submit_index_task",
        "delete_paper",
    )
    assert not any(name in upload_source for name in forbidden)
    assert not any(name in reindex_source for name in forbidden)
    assert not any(name in delete_source for name in forbidden)

    sentinel = object()
    with patch.object(routes_kb, "upload_document", return_value=sentinel) as upload:
        assert __import__("asyncio").run(routes_kb.upload_kb_paper(None, None)) is sentinel
        upload.assert_called_once_with(None, None)
    with patch.object(routes_kb, "reindex_document_route", return_value=sentinel) as reindex:
        assert routes_kb.reindex_kb_paper("doc-1", None, {"chunker": "v1"}) is sentinel
        reindex.assert_called_once_with("doc-1", None, {"chunker": "v1"})
    with patch.object(routes_kb, "delete_document_route", return_value=sentinel) as delete:
        assert routes_kb.delete_kb_paper("doc-1", None) is sentinel
        delete.assert_called_once_with("doc-1", None)
