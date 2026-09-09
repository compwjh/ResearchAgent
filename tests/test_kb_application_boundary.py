from pathlib import Path

import pytest

from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.knowledge_base.infrastructure.migration import migrate_papers_json
from backend.app.knowledge_base.infrastructure.store import (
    STATUS_INDEXED,
    get_paper,
    new_record,
    remove_paper,
    update_chunker_state,
    upsert_paper,
)
from backend.app.platform.ports import PaperImportRequest


def test_import_boundary_uses_create_exclusive_source_and_keeps_discovery_outside_kb(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    source = tmp_path / "download.pdf"
    source.write_bytes(b"new-source")
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda record, path: {"paper_id": record.paper_id, "status": STATUS_INDEXED},
    )
    result = port.import_paper(PaperImportRequest(
        candidate_snapshot={"title": "A", "year": 2026, "conference_id": "ccs", "doi": "10.1/a", "_stored_name": "A.pdf"},
        trusted_pdf_path=source,
    ))
    assert result.paper_id
    assert result.stored_name == "A.pdf"
    assert not source.exists()
    assert (papers / "A.pdf").read_bytes() == b"new-source"
    record = get_paper(result.paper_id, meta)
    assert record["status"] == STATUS_INDEXED
    assert record["schema_version"] == "knowledge-document-v1"
    assert record["migration_version"] == "018-document-v1"
    assert record["document_id"] == result.paper_id
    assert record["source_sha256"]
    assert record["source_immutable"] is True
    assert record["indexed_source_sha256"] is None
    assert record["source_hash_state"] == "legacy_unknown"
    assert record["chunkers"]["v1"]["status"] == "indexing"
    assert record["chunkers"]["v2"]["status"] == "pending"


def test_import_boundary_never_overwrites_existing_basename(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "same.pdf").write_bytes(b"original")
    source = tmp_path / "download.pdf"
    source.write_bytes(b"new")
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=tmp_path / "papers.json",
        indexer=lambda record, path: {"status": STATUS_INDEXED},
    )
    result = port.import_paper(PaperImportRequest(
        candidate_snapshot={"title": "B", "year": 2026, "conference_id": "ccs", "_stored_name": "same.pdf"},
        trusted_pdf_path=source,
    ))
    assert result.stored_name == "same-2.pdf"
    assert (papers / "same.pdf").read_bytes() == b"original"
    assert (papers / "same-2.pdf").read_bytes() == b"new"


def test_paper_discovery_orchestration_only_imports_the_port(tmp_path):
    source = Path("backend/app/paper_discovery/application/paper_import.py").read_text(encoding="utf-8")
    assert "knowledge_base.infrastructure" not in source
    assert "PaperImportPort" in source


def test_corrupt_metadata_blocks_import_without_replacing_bytes(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    meta.write_bytes(b"{broken")
    source = tmp_path / "download.pdf"
    source.write_bytes(b"source")
    port = create_paper_import_port(papers_dir=papers, meta_path=meta)
    from backend.app.knowledge_base.infrastructure.store import MetadataStoreError

    with pytest.raises(MetadataStoreError) as error:
        port.import_paper(PaperImportRequest(
            candidate_snapshot={"title": "broken", "year": 2026, "conference_id": "ccs"},
            trusted_pdf_path=source,
        ))
    assert error.value.code == "METADATA_INVALID"
    assert meta.read_bytes() == b"{broken"
    assert source.exists()


def test_find_existing_legacy_record_returns_nonempty_paper_id(tmp_path):
    meta = tmp_path / "papers.json"
    meta.write_text(
        '[{"paper_id":"legacy-1","file_name":"legacy.pdf","status":"indexed",'
        '"title":"legacy","year":2025,"conference_id":"ccs"}]',
        encoding="utf-8",
    )
    port = create_paper_import_port(papers_dir=tmp_path / "papers", meta_path=meta)
    result = port.find_existing({"title": "legacy", "year": 2025, "conference_id": "ccs"})
    assert result is not None
    assert result.paper_id == "legacy-1"


def test_canonical_identity_dedup_status_and_delete_preserve_schema(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    source = papers / "doc-1.pdf"
    source.write_bytes(b"source")
    meta = tmp_path / "papers.json"
    meta.write_text(
        '[{"paper_id":"doc-1","file_name":"doc.pdf","status":"indexed",'
        '"page_count":1,"chunk_count":1,"uploaded_at":"2026-01-01T00:00:00",'
        '"title":"same","authors":[],"year":2026,"conference_id":"ccs"}]',
        encoding="utf-8",
    )
    migrate_papers_json(meta, papers)
    port = create_paper_import_port(papers_dir=papers, meta_path=meta, indexer=lambda *_: {"status": STATUS_INDEXED})
    duplicate = port.find_existing({"title": "same", "year": 2026, "conference_id": "ccs"})
    assert duplicate is not None
    assert duplicate.paper_id == "doc-1"
    update_chunker_state("doc-1", "v1", status="indexed", meta_path=meta)
    legacy_update = new_record("doc.pdf", uploaded_at="2026-01-01T00:00:00+00:00", stored_name="doc-1.pdf")
    legacy_update.paper_id = "doc-1"
    legacy_update.status = "indexed"
    upsert_paper(legacy_update, meta)
    updated = get_paper("doc-1", meta)
    assert updated["schema_version"] == "knowledge-document-v1"
    assert updated["document_id"] == "doc-1"
    assert updated["source_sha256"] is not None
    assert updated["indexed_source_sha256"] is None
    assert updated["title"] == "same"
    assert "paper_id" not in updated
    assert remove_paper("doc-1", meta, papers)
    assert not source.exists()
