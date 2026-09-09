import hashlib
import threading
from pathlib import Path

import pytest

import backend.app.knowledge_base.infrastructure.manifest_store as manifest_store_module
from backend.app.knowledge_base.infrastructure.document_read import (
    DocumentReadError,
    DocumentSourceReader,
    validate_source_bytes,
)
from backend.app.knowledge_base.infrastructure.inspection import (
    InspectionError,
    build_inspection_manifest,
)
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.markdown import extract_markdown_provenance
from backend.app.knowledge_base.infrastructure.migration import (
    build_import_knowledge_document,
    write_import_knowledge_document,
)
from backend.app.knowledge_base.infrastructure.provenance import build_source_provenance_bundle
from backend.app.knowledge_base.infrastructure.store import new_record


def _pdf_document(tmp_path: Path, document_id: str = "doc-1") -> tuple[Path, Path, dict]:
    papers = tmp_path / "papers"
    papers.mkdir()
    source = tmp_path / "download.pdf"
    content = b"%PDF-1.7\nfixture-source"
    source.write_bytes(content)
    record = new_record("display.pdf", stored_name="doc-1.pdf")
    record.paper_id = document_id
    target = papers / "doc-1.pdf"
    target.write_bytes(content)
    document = build_import_knowledge_document(record, target)
    meta = tmp_path / "papers.json"
    write_import_knowledge_document(document, meta)
    return meta, papers, document


def _markdown_manifest(tmp_path: Path):
    source = "# Heading\n\nA small paragraph.\n".encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()
    provenance = extract_markdown_provenance(source, document_id="md-1", source_sha256=digest)
    bundle = build_source_provenance_bundle(provenance, chunker="markdown-block-v1")
    document = {"document_id": "md-1", "source_sha256": digest}
    payloads = []
    for chunk in bundle.chunks:
        payloads.append({
            **chunk,
            "document_id": "md-1",
            "chunker": "v1",
            "source_sha256": digest,
            "is_citation": False,
        })
    return build_inspection_manifest(document, bundle, payloads)


def test_source_reader_head_range_etag_and_path_validation(tmp_path):
    meta, papers, document = _pdf_document(tmp_path)
    reader = DocumentSourceReader(meta_path=meta, papers_dir=papers)

    head = reader.head(document["document_id"])
    assert head.etag == f'"sha256:{document["source_sha256"]}"'
    full = reader.read(document["document_id"])
    assert full.status == 200
    assert full.headers["Content-Length"] == str(len(full.body))
    assert full.headers["ETag"] == head.etag

    ranged = reader.read(document["document_id"], range_header="bytes=0-3")
    assert ranged.status == 206
    assert ranged.body == b"%PDF"
    assert ranged.headers["Content-Range"] == f"bytes 0-3/{len(full.body)}"

    head_response = reader.read(document["document_id"], range_header="bytes=0-3", head_only=True)
    assert head_response.body == b""
    assert head_response.headers["Content-Length"] == "4"
    assert reader.read(document["document_id"], if_none_match=head.etag).status == 304
    with pytest.raises(DocumentReadError) as error:
        reader.read(document["document_id"], range_header="bytes=0-1,3-4")
    assert error.value.code == "INVALID_RANGE"
    with pytest.raises(DocumentReadError) as error:
        reader.read("../escape")
    assert error.value.code == "INVALID_DOCUMENT_ID"


def test_source_validation_accepts_pdf_and_utf8_markdown_only():
    validate_source_bytes(b"%PDF-1.7\n", "application/pdf")
    validate_source_bytes("# UTF-8 文档\n".encode("utf-8"), "text/markdown")
    with pytest.raises(DocumentReadError) as error:
        validate_source_bytes(b"not a pdf", "application/pdf")
    assert error.value.code == "INVALID_PDF"
    with pytest.raises(DocumentReadError) as error:
        validate_source_bytes(b"\xff", "text/markdown")
    assert error.value.code == "INVALID_UTF8"
    with pytest.raises(DocumentReadError) as error:
        validate_source_bytes(b"# bad\x00markdown", "text/markdown")
    assert error.value.code == "INVALID_ENCODING"
    with pytest.raises(DocumentReadError) as error:
        validate_source_bytes(b"x", "text/plain")
    assert error.value.code == "SOURCE_MEDIA_TYPE_UNSUPPORTED"


def test_inspection_manifest_uses_real_payloads_without_index_writes(tmp_path):
    manifest = _markdown_manifest(tmp_path)
    value = manifest.to_dict()
    assert value["schema_version"] == "inspection-manifest-v1"
    assert value["chunker"] == "v1"
    assert value["status"] in {"ready", "partial"}
    assert value["chunks"]
    assert value["anchors"]
    assert value["indexed_source_sha256"] == value["source_sha256"]


def test_inspection_rejects_legacy_payload_without_source_hash(tmp_path):
    source = b"# Heading\n"
    digest = hashlib.sha256(source).hexdigest()
    provenance = extract_markdown_provenance(source, document_id="md-2", source_sha256=digest)
    bundle = build_source_provenance_bundle(provenance, chunker="markdown-block-v1")
    with pytest.raises(InspectionError) as error:
        build_inspection_manifest(
            {"document_id": "md-2", "source_sha256": digest},
            bundle,
            [{**bundle.chunks[0], "document_id": "md-2", "chunker": "v1"}],
        )
    assert error.value.code == "INDEX_REBUILD_REQUIRED"


def test_manifest_claim_is_single_owner_and_tombstone_blocks_read(tmp_path):
    manifest = _markdown_manifest(tmp_path)
    store = InspectionManifestStore(tmp_path / "data" / "kb")
    store.write(manifest)
    assert store.read("md-1", "v1").document_id == "md-1"
    claim = store.claim("md-1", "v1", "worker-a")
    with pytest.raises(ManifestStoreError) as error:
        store.claim("md-1", "v1", "worker-b")
    assert error.value.code == "MANIFEST_CLAIMED"
    store.release(claim)
    store.tombstone("md-1", "v1", reason="deleted", owner="worker-a")
    with pytest.raises(ManifestStoreError) as error:
        store.read("md-1", "v1")
    assert error.value.code == "MANIFEST_TOMBSTONED"


def test_finalize_bundle_is_idempotent_and_marker_is_last(tmp_path, monkeypatch):
    manifest = _markdown_manifest(tmp_path)
    finalizer = FinalizeBundleStore(tmp_path)
    with pytest.raises(ManifestStoreError) as error:
        finalizer.require_generation()
    assert error.value.code == "INDEX_REBUILD_REQUIRED"
    with pytest.raises(ManifestStoreError) as error:
        finalizer.require_generation(finalize_pending=True)
    assert error.value.code == "INDEX_FINALIZE_REQUIRED"
    bundle = finalizer.stage(
        "run-1",
        candidate_collection="papers_rebuild_run-1",
        metadata=[{"document_id": "md-1", "source_sha256": manifest.to_dict()["source_sha256"]}],
        manifests={("md-1", "v1"): manifest},
        collection_fingerprint="a" * 64,
    )
    assert not (tmp_path / "data/kb/index-generation.json").exists()
    marker = finalizer.commit("run-1")
    assert marker["schema_version"] == "index-generation-v1"
    assert finalizer.require_generation()["run_id"] == "run-1"
    original_atomic_bytes = manifest_store_module._atomic_bytes
    writes = []

    def track_write(path, payload):
        writes.append(Path(path))
        return original_atomic_bytes(path, payload)

    monkeypatch.setattr(manifest_store_module, "_atomic_bytes", track_write)
    assert finalizer.commit("run-1")["alias_target"] == "papers_rebuild_run-1"
    assert writes == []
    assert (tmp_path / "data/kb/manifests/md-1/v1.json").exists()
    assert bundle["bundle_sha256"]


def test_manifest_claim_concurrent_winner(tmp_path):
    store = InspectionManifestStore(tmp_path / "data" / "kb")
    results = []

    def claim(index):
        try:
            results.append(store.claim("doc-1", "v1", f"worker-{index}"))
        except ManifestStoreError as error:
            results.append(error.code)

    threads = [threading.Thread(target=claim, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(isinstance(item, str) is False for item in results) == 1
