"""PDF active-feature safety and single-document publication guards."""

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import migration as migration_module
from backend.app.knowledge_base.infrastructure import provenance as provenance_module
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.parse import extract_pdf_provenance
from backend.app.knowledge_base.infrastructure.store import STATUS_FAILED, STATUS_PARTIAL


class _Client:
    def collection_exists(self, _name):
        return True

    def delete(self, **_kwargs):
        return None

    def upsert(self, **_kwargs):
        return None


def _pdf(tmp_path: Path, action: str | None = None, *, catalog_key: str | None = None) -> Path:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "passive PDF safety fixture")
    if action is not None:
        catalog = document.pdf_catalog()
        document.xref_set_key(catalog, catalog_key or "OpenAction", action)
    path = tmp_path / "fixture.pdf"
    document.save(path)
    document.close()
    return path


def _raw_pdf_with_open_action(tmp_path: Path, action: bytes) -> Path:
    """Build a tiny valid PDF while preserving duplicate dictionary keys."""
    content = b"BT /F1 12 Tf 72 720 Td (fixture) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /OpenAction " + action + b" >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources 4 0 R /Contents 5 0 R >>",
        b"<< /Font << /F1 6 0 R >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref_offset = len(payload)
    payload += b"xref\n0 7\n0000000000 65535 f \n"
    payload += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    payload += b"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n"
    payload += str(xref_offset).encode() + b"\n%%EOF\n"
    path = tmp_path / "raw-action.pdf"
    path.write_bytes(payload)
    return path


@pytest.mark.parametrize(
    "action",
    [
        "<< /S /JavaScript /JS (ignored) >>",
        "<< /S /Launch /F (ignored) >>",
        "<< /S /GoToR /D [4 0 R /Fit] >>",
        "<< /S /SubmitForm /F (ignored) >>",
        "<< /S /ImportData /F (ignored) >>",
    ],
)
def test_pdf_active_actions_are_passively_rejected(tmp_path: Path, action: str) -> None:
    result = extract_pdf_provenance(_pdf(tmp_path, action))
    assert result.status == "partial"
    assert result.error == "HOSTILE_FEATURES_NOT_EXECUTED"


def test_pdf_indirect_goto_fit_and_bare_array_are_safe(tmp_path: Path) -> None:
    direct = _pdf(tmp_path, "[4 0 R /Fit]")
    assert extract_pdf_provenance(direct).status == "ready"

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "indirect destination")
    destination = document.get_new_xref()
    document.update_object(destination, "[4 0 R /Fit]")
    document.xref_set_key(document.pdf_catalog(), "OpenAction", f"{destination} 0 R")
    indirect = tmp_path / "indirect.pdf"
    document.save(indirect)
    document.close()
    assert extract_pdf_provenance(indirect).status == "ready"


def test_pdf_literal_destination_cannot_impersonate_a_typed_action(tmp_path: Path) -> None:
    result = extract_pdf_provenance(
        _pdf(tmp_path, "<< /Type /Action /S /GoTo /D (literal /S /GoTo /D [4 0 R /Fit]) >>")
    )
    assert result.status == "partial"
    assert result.error == "HOSTILE_FEATURES_NOT_EXECUTED"


@pytest.mark.parametrize("generation", [999, 65535])
def test_pdf_page_destination_generation_must_be_zero(tmp_path: Path, generation: int) -> None:
    result = extract_pdf_provenance(_pdf(tmp_path, f"[4 {generation} R /Fit]"))
    assert result.status == "partial"
    assert result.error == "HOSTILE_FEATURES_NOT_EXECUTED"


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        (b"<< /Type /Action /S /GoTo /D (unsafe) /D [3 0 R /Fit] >>", "ready"),
        (b"<< /Type /Action /S /GoTo /D [3 0 R /Fit] /D (unsafe) >>", "partial"),
    ],
)
def test_pdf_duplicate_destination_uses_final_dictionary_value(
    tmp_path: Path, action: bytes, expected_status: str
) -> None:
    result = extract_pdf_provenance(_raw_pdf_with_open_action(tmp_path, action))
    assert result.status == expected_status
    if expected_status == "partial":
        assert result.error == "HOSTILE_FEATURES_NOT_EXECUTED"


@pytest.mark.parametrize(
    "action",
    [
        "<< /Type /Action /S /GoTo /D [4 0 R /Fit] /Next 9 0 R >>",
        "<< /Type /Action /S /GoTo /D [4 0 R /Fit] /Unknown /Value >>",
        "<< /Type /Action /S /GoTo /D [99 0 R /Fit] >>",
        "[4 0 R /XYZ 0 0 1]",
    ],
)
def test_pdf_unknown_navigation_shapes_never_become_ready(tmp_path: Path, action: str) -> None:
    result = extract_pdf_provenance(_pdf(tmp_path, action))
    assert result.status in {"partial", "failed"}
    assert result.status != "ready"


def test_pdf_cycle_and_oversized_action_fail_closed(tmp_path: Path) -> None:
    cycle_document = pymupdf.open()
    cycle_document.new_page().insert_text((72, 72), "cycle")
    cycle_xref = cycle_document.get_new_xref()
    cycle_document.update_object(cycle_xref, f"<< /Type /Action /S /GoTo /D {cycle_xref} 0 R >>")
    cycle_document.xref_set_key(cycle_document.pdf_catalog(), "OpenAction", f"{cycle_xref} 0 R")
    cycle_path = tmp_path / "cycle.pdf"
    cycle_document.save(cycle_path)
    cycle_document.close()
    cycle = extract_pdf_provenance(cycle_path)
    assert cycle.status == "failed"
    assert cycle.error == "PDF_PROVENANCE_UNAVAILABLE"

    large_document = pymupdf.open()
    large_document.new_page().insert_text((72, 72), "large")
    large_xref = large_document.get_new_xref()
    large_document.update_object(
        large_xref,
        "<< /Type /Action /S /GoTo /D [4 0 R /Fit] /Unknown ("
        + "x" * 20_000
        + ") >>",
    )
    large_document.xref_set_key(large_document.pdf_catalog(), "OpenAction", f"{large_xref} 0 R")
    large_path = tmp_path / "large.pdf"
    large_document.save(large_path)
    large_document.close()
    large = extract_pdf_provenance(large_path)
    assert large.status == "failed"
    assert large.error == "PDF_PROVENANCE_UNAVAILABLE"


def test_pdf_form_and_embedded_features_remain_hostile(tmp_path: Path) -> None:
    form = extract_pdf_provenance(_pdf(tmp_path, "<< /Fields [] >>", catalog_key="AcroForm"))
    assert form.status == "partial"
    embedded = extract_pdf_provenance(
        _pdf(tmp_path, "<< /EmbeddedFiles << /Names [] >> >>", catalog_key="Names")
    )
    assert embedded.status == "partial"


def _generation_document(tmp_path: Path, content: bytes, name: str = "document.md"):
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    result = application.create_uploaded_document(name, "text/markdown", content, meta_path=meta, papers_dir=papers)
    document = result["document"]
    FinalizeBundleStore(tmp_path).stage(
        "publication-test",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="c" * 64,
    )
    FinalizeBundleStore(tmp_path).commit("publication-test")
    return document, meta, papers


def _patch_embeddings(monkeypatch):
    monkeypatch.setattr(index_module, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(index_module, "encode_sparse", lambda _text: {"indices": [1], "values": [1.0]})


def test_partial_manifest_publishes_partial_metadata_and_hash(monkeypatch, tmp_path: Path) -> None:
    source = Path("docs/sdd/fixtures/spec-018/pdf-hostile-features.pdf").read_bytes()
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    document = application.create_uploaded_document("hostile.pdf", "application/pdf", source, meta_path=meta, papers_dir=papers)["document"]
    FinalizeBundleStore(tmp_path).stage(
        "partial-test",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="d" * 64,
    )
    FinalizeBundleStore(tmp_path).commit("partial-test")
    _patch_embeddings(monkeypatch)

    result = index_module.index_paper_chunker(
        document,
        papers / document["stored_name"],
        client=_Client(),
        meta_path=meta,
        destination_collection="papers_rebuild_live",
    )
    stored = json.loads(meta.read_text())[0]
    manifest = InspectionManifestStore(meta.parent).read(document["document_id"], "v1").to_dict()
    assert result["status"] == STATUS_PARTIAL
    assert stored["status"] == STATUS_PARTIAL
    assert stored["chunkers"]["v1"]["status"] == STATUS_PARTIAL
    assert stored["indexed_source_sha256"] == document["source_sha256"]
    assert stored["source_hash_state"] == "verified"
    assert manifest["status"] == "partial"
    assert manifest["error"] == "HOSTILE_FEATURES_NOT_EXECUTED"


def test_v2_publication_does_not_override_v1_compatibility_state(monkeypatch, tmp_path: Path) -> None:
    document, meta, papers = _generation_document(tmp_path, ("# title\n\n" + "indexed text " * 20).encode())
    _patch_embeddings(monkeypatch)
    monkeypatch.setattr(index_module, "build_chunks_v2", lambda _pages, **_kwargs: ([index_module.Chunk("v2 text", None, 0)], False))
    monkeypatch.setattr(provenance_module, "build_chunks_v2", lambda _pages, **_kwargs: ([index_module.Chunk("v2 text", None, 0)], False))
    first = index_module.index_paper_chunker(document, papers / document["stored_name"], client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    assert first["status"] == "indexed"
    second = index_module.index_paper_chunker(document, papers / document["stored_name"], chunker="v2", client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    stored = json.loads(meta.read_text())[0]
    assert second["status"] == "indexed"
    assert stored["status"] == "indexed"
    assert stored["chunkers"]["v1"]["status"] == "indexed"
    assert stored["chunkers"]["v2"]["status"] == STATUS_PARTIAL
    assert stored["indexed_source_sha256"] == document["source_sha256"]


def test_manifest_write_failure_never_publishes_verified_metadata(monkeypatch, tmp_path: Path) -> None:
    document, meta, papers = _generation_document(tmp_path, ("# title\n\n" + "indexed text " * 20).encode())
    _patch_embeddings(monkeypatch)

    def fail_write(_self, _manifest):
        raise ManifestStoreError("ATOMIC_WRITE_FAILED", status=503)

    monkeypatch.setattr(InspectionManifestStore, "write", fail_write)
    result = index_module.index_paper_chunker(document, papers / document["stored_name"], client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    stored = json.loads(meta.read_text())[0]
    assert result["status"] == STATUS_FAILED
    assert stored["status"] == STATUS_FAILED
    assert stored["indexed_source_sha256"] is None
    assert stored["source_hash_state"] == "legacy_unknown"
    with pytest.raises(ManifestStoreError) as raised:
        FinalizeBundleStore(tmp_path).require_generation()
    assert raised.value.code == "INDEX_FINALIZE_REQUIRED"


def test_metadata_write_failure_leaves_generation_fail_closed(monkeypatch, tmp_path: Path) -> None:
    document, meta, papers = _generation_document(tmp_path, ("# title\n\n" + "indexed text " * 20).encode())
    _patch_embeddings(monkeypatch)
    original_atomic = migration_module._atomic_bytes

    def fail_metadata(path, payload, **kwargs):
        if Path(path).resolve() == meta.resolve():
            raise migration_module.KnowledgeDocumentMigrationError(migration_module.MIGRATION_WRITE_FAILED)
        return original_atomic(path, payload, **kwargs)

    monkeypatch.setattr(migration_module, "_atomic_bytes", fail_metadata)
    result = index_module.index_paper_chunker(document, papers / document["stored_name"], client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    stored = json.loads(meta.read_text())[0]
    assert result["status"] == "indexing"
    assert stored["indexed_source_sha256"] is None
    with pytest.raises(ManifestStoreError) as raised:
        FinalizeBundleStore(tmp_path).require_generation()
    assert raised.value.code == "INDEX_FINALIZE_REQUIRED"


def test_generation_refresh_failure_marks_controlled_failure(monkeypatch, tmp_path: Path) -> None:
    document, meta, papers = _generation_document(tmp_path, ("# title\n\n" + "indexed text " * 20).encode())
    _patch_embeddings(monkeypatch)
    original_refresh = index_module.FinalizeBundleStore.refresh_live_digests
    calls = {"count": 0}

    def fail_after_initial(self, **kwargs):
        calls["count"] += 1
        if calls["count"] <= 1:
            return original_refresh(self, **kwargs)
        raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503)

    monkeypatch.setattr(index_module.FinalizeBundleStore, "refresh_live_digests", fail_after_initial)
    result = index_module.index_paper_chunker(document, papers / document["stored_name"], client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    stored = json.loads(meta.read_text())[0]
    assert result["status"] == STATUS_FAILED
    assert stored["status"] == STATUS_FAILED
    assert stored["chunkers"]["v1"]["error"] == "INDEX_FINALIZE_REQUIRED"
    with pytest.raises(ManifestStoreError) as raised:
        FinalizeBundleStore(tmp_path).require_generation()
    assert raised.value.code == "INDEX_FINALIZE_REQUIRED"


def test_source_change_after_vector_write_is_not_verified(monkeypatch, tmp_path: Path) -> None:
    document, meta, papers = _generation_document(tmp_path, ("# title\n\n" + "indexed text " * 20).encode())
    _patch_embeddings(monkeypatch)
    source = papers / document["stored_name"]
    original_upsert = index_module.upsert_chunks

    def mutate_source(*args, **kwargs):
        source.write_bytes(source.read_bytes() + b"changed")
        return len(args[2])

    monkeypatch.setattr(index_module, "upsert_chunks", mutate_source)
    result = index_module.index_paper_chunker(document, source, client=_Client(), meta_path=meta, destination_collection="papers_rebuild_live")
    stored = json.loads(meta.read_text())[0]
    assert result["status"] == STATUS_FAILED
    assert stored["status"] == STATUS_FAILED
    assert stored["chunkers"]["v1"]["error"] == "SOURCE_HASH_MISMATCH"
    assert stored["indexed_source_sha256"] == document["source_sha256"]
    assert stored["source_hash_state"] == "mismatch"
    with pytest.raises(ManifestStoreError) as raised:
        FinalizeBundleStore(tmp_path).require_generation()
    assert raised.value.code == "INDEX_FINALIZE_REQUIRED"
    monkeypatch.setattr(index_module, "upsert_chunks", original_upsert)


def test_parse_source_hash_mismatch_is_normalized_and_published_fail_closed(monkeypatch, tmp_path: Path) -> None:
    source = _pdf(tmp_path)
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    document = application.create_uploaded_document(
        "mismatch.pdf", "application/pdf", source.read_bytes(), meta_path=meta, papers_dir=papers
    )["document"]
    FinalizeBundleStore(tmp_path).stage(
        "parse-mismatch",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="e" * 64,
    )
    FinalizeBundleStore(tmp_path).commit("parse-mismatch")
    _patch_embeddings(monkeypatch)
    stored_path = papers / document["stored_name"]
    stored_path.write_bytes(stored_path.read_bytes() + b"changed")

    result = index_module.index_paper_chunker(
        document,
        stored_path,
        client=_Client(),
        meta_path=meta,
        destination_collection="papers_rebuild_live",
    )
    stored = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert result["status"] == STATUS_FAILED
    assert stored["status"] == STATUS_FAILED
    assert stored["chunkers"]["v1"]["error"] == "SOURCE_HASH_MISMATCH"
    assert stored["source_hash_state"] == "mismatch"
    assert stored["indexed_source_sha256"] == document["source_sha256"]
    with pytest.raises(ManifestStoreError) as raised:
        FinalizeBundleStore(tmp_path).require_generation()
    assert raised.value.code == "INDEX_FINALIZE_REQUIRED"
