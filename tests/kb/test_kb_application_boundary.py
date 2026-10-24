import hashlib
import json
from pathlib import Path

import pytest

import backend.app.knowledge_base.application as application_module
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.application import (
    create_paper_import_port,
    create_uploaded_document,
    get_document_project,
    set_document_project,
)
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.migration import migrate_papers_json
from backend.app.knowledge_base.infrastructure.store import (
    STATUS_INDEXED,
    get_paper,
    new_record,
    remove_paper,
    update_chunker_state,
    upsert_paper,
)
from backend.app.platform.ports import ImportIndexStatus, PaperImportRequest


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
    # The direct adapter receives a caller-owned path.  Downloader lifecycle
    # cleanup belongs to import_candidate, so the adapter must not unlink it.
    assert source.read_bytes() == b"new-source"
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


def test_default_paper_import_publishes_canonical_manifest_and_hash(tmp_path, monkeypatch):
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    existing = create_uploaded_document(
        "existing.md",
        "text/markdown",
        b"# existing\n",
        meta_path=meta,
        papers_dir=papers,
    )["document"]
    set_document_project(
        existing["document_id"],
        "project-a",
        meta_path=meta,
        papers_dir=papers,
        owner_id="owner-a",
    )
    existing_before = next(
        item for item in json.loads(meta.read_text(encoding="utf-8"))
        if item["document_id"] == existing["document_id"]
    )
    FinalizeBundleStore(root).stage(
        "paper-import-generation",
        candidate_collection="papers_rebuild_live",
        metadata=[existing_before],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("paper-import-generation")

    source = tmp_path / "download.pdf"
    source.write_bytes(Path("docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf").read_bytes())

    class Client:
        def collection_exists(self, _name):
            return True

        def delete(self, **_kwargs):
            return None

        def upsert(self, **kwargs):
            self.points = kwargs["points"]

    client = Client()
    monkeypatch.setattr(index_module, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(index_module, "encode_sparse", lambda _text: {"indices": [1], "values": [1.0]})
    monkeypatch.setattr(
        application_module,
        "run_index_task_sync",
        lambda _paper_id, _chunker, runner: runner(lambda _progress: None),
    )
    submitted = []
    monkeypatch.setattr(
        application_module,
        "submit_index_task",
        lambda *args, **kwargs: submitted.append((args, kwargs)) or True,
    )

    application_module.submit_document_reindex(
        existing["document_id"],
        "v1",
        meta_path=meta,
        papers_dir=papers,
        client=client,
        destination_collection="papers_rebuild_live",
    )
    submitted[0][0][2](lambda _progress: None)
    existing_manifest_before = InspectionManifestStore(meta.parent).read(
        existing["document_id"], "v1"
    ).to_dict()
    existing_after_reindex = next(
        item for item in json.loads(meta.read_text(encoding="utf-8"))
        if item["document_id"] == existing["document_id"]
    )

    port = create_paper_import_port(papers_dir=papers, meta_path=meta, client=client)
    result = port.import_paper(
        PaperImportRequest(
            {
                "title": "Canonical import",
                "year": 2026,
                "conference_id": "ccs",
                "conference_name": "ACM CCS",
                "doi": "10.1234/canonical",
                "_stored_name": "canonical.pdf",
            },
            source,
            attempt_owner="owner-a",
            attempt_token="token-a",
        )
    )

    assert result.index_status == ImportIndexStatus.INDEXED
    assert result.resource_capability is not None
    assert result.resource_capability.owner == "owner-a"
    assert result.resource_capability.destination_collection == "papers_rebuild_live"
    document = next(item for item in json.loads(meta.read_text(encoding="utf-8")) if item["document_id"] == result.paper_id)
    source_hash = hashlib.sha256((papers / document["stored_name"]).read_bytes()).hexdigest()
    assert document["schema_version"] == "knowledge-document-v1"
    assert document["document_id"] == result.paper_id
    assert document["source_sha256"] == source_hash
    assert document["indexed_source_sha256"] == source_hash
    assert document["source_hash_state"] == "verified"
    assert document["chunkers"]["v1"]["status"] in {"indexed", "partial"}

    manifest = InspectionManifestStore(meta.parent).read(result.paper_id, "v1").to_dict()
    assert manifest["document_id"] == result.paper_id
    assert manifest["source_sha256"] == source_hash
    assert manifest["indexed_source_sha256"] == source_hash
    assert manifest["status"] in {"ready", "partial"}
    assert client.points[0].payload["document_id"] == result.paper_id
    assert client.points[0].payload["source_sha256"] == source_hash

    marker = FinalizeBundleStore(root).require_generation()
    assert marker["run_id"] == "paper-import-generation"
    assert marker["alias_target"] == "papers_rebuild_live"
    records = json.loads(meta.read_text(encoding="utf-8"))
    assert next(item for item in records if item["document_id"] == existing["document_id"]) == existing_after_reindex
    assert InspectionManifestStore(meta.parent).read(existing["document_id"], "v1").to_dict() == existing_manifest_before
    assert get_document_project(existing["document_id"], meta_path=meta, owner_id="owner-a") == "project-a"


def test_legacy_index_record_without_source_hash_stays_unverified(tmp_path, monkeypatch):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    papers.mkdir()
    source = papers / "legacy.pdf"
    source.write_bytes(Path("docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf").read_bytes())
    meta.write_text(
        json.dumps(
            [{
                "paper_id": "legacy-paper",
                "file_name": "legacy.pdf",
                "stored_name": "legacy.pdf",
                "uploaded_at": "2026-01-01T00:00:00+00:00",
                "status": "indexing",
            }]
        ),
        encoding="utf-8",
    )

    class Client:
        def collection_exists(self, _name):
            return True

        def delete(self, **_kwargs):
            return None

        def upsert(self, **_kwargs):
            return None

    monkeypatch.setattr(index_module, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(index_module, "encode_sparse", lambda _text: {"indices": [1], "values": [1.0]})

    result = index_module.index_paper_chunker(
        {"paper_id": "legacy-paper", "file_name": "legacy.pdf", "uploaded_at": "2026-01-01T00:00:00+00:00"},
        source,
        client=Client(),
        meta_path=meta,
        destination_collection="papers_rebuild_legacy",
    )

    stored = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert result["status"] == "indexed"
    assert stored.get("indexed_source_sha256") is None
    assert stored.get("source_hash_state") in {None, "legacy_unknown"}
    with pytest.raises(ManifestStoreError):
        InspectionManifestStore(meta.parent).read("legacy-paper", "v1")
