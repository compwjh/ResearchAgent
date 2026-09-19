import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app.knowledge_base.infrastructure.migration import (
    MIGRATION_INPUT_INVALID,
    MIGRATION_VERSION,
    SOURCE_MISSING,
    KnowledgeDocumentMigrationError,
    migrate_papers_json,
)
from backend.app.knowledge_base.infrastructure.store import (
    MetadataStoreError,
    get_paper,
    resolve_paper_path,
    save_papers,
)


def _legacy(paper_id="paper-1", *, stored_name=None, uploaded_at=None):
    return {
        "paper_id": paper_id,
        "file_name": "paper.md" if stored_name and stored_name.endswith(".md") else "paper.pdf",
        "status": "indexed",
        "page_count": 2,
        "chunk_count": 3,
        "uploaded_at": uploaded_at or datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
        "error": None,
        "chunkers": {"v1": {"status": "indexed", "chunk_count": 3, "progress": 100, "error": None}},
        "title": "A paper",
        "authors": ["Author"],
        "year": 2026,
        "conference_id": "ccs",
        "conference_name": "ACM CCS",
        "doi": "10.1234/example",
        "dblp_key": "conf/ccs/example",
        "source_url": "https://example.invalid/paper",
        "import_source": "fixture",
        **({"stored_name": stored_name} if stored_name else {}),
    }


def _write_legacy(tmp_path, records):
    meta = tmp_path / "papers.json"
    meta.write_text(json.dumps(records), encoding="utf-8")
    return meta


def test_migration_preserves_identity_metadata_hash_and_backup(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    source = papers / "paper-1.pdf"
    source.write_bytes(b"pdf-source")
    meta = _write_legacy(tmp_path, [_legacy()])

    result = migrate_papers_json(meta, papers)
    value = json.loads(meta.read_text(encoding="utf-8"))
    record = value[0]
    assert result["migration_version"] == MIGRATION_VERSION
    assert record["document_id"] == "paper-1"
    assert record["source_sha256"] == hashlib.sha256(b"pdf-source").hexdigest()
    assert record["indexed_source_sha256"] is None
    assert record["source_hash_state"] == "legacy_unknown"
    assert record["source_immutable"] is True
    assert record["title"] == "A paper"
    backup = tmp_path / "papers.json.pre-018-document-v1.bak"
    assert backup.read_text(encoding="utf-8")
    assert (backup.stat().st_mode & 0o222) == 0


def test_missing_source_is_retained_as_preflight_failure(tmp_path):
    meta = _write_legacy(tmp_path, [_legacy("missing")])
    result = migrate_papers_json(meta, tmp_path / "papers")
    record = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert result["source_missing_count"] == 1
    assert record["document_id"] == "missing"
    assert record["source_sha256"] is None
    assert record["error"] == SOURCE_MISSING
    assert record["status"] == "failed"


def test_markdown_keeps_markdown_basename_and_null_page_count(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "md-1.md").write_bytes(b"# hello\n")
    meta = _write_legacy(tmp_path, [_legacy("md-1", stored_name="md-1.md")])
    migrate_papers_json(meta, papers)
    record = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert record["media_type"] == "text/markdown"
    assert record["stored_name"] == "md-1.md"
    assert record["page_count"] is None


def test_migration_is_idempotent_and_does_not_rewrite_canonical(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "paper-1.pdf").write_bytes(b"source")
    meta = _write_legacy(tmp_path, [_legacy()])
    migrate_papers_json(meta, papers)
    first = meta.read_bytes()
    result = migrate_papers_json(meta, papers)
    assert result["already_migrated"] is True
    assert meta.read_bytes() == first


@pytest.mark.parametrize(
    "records",
    [
        [{"paper_id": "one", "file_name": "one.pdf", "uploaded_at": "not-a-date"}],
        [{"paper_id": "one", "file_name": "one.pdf", "uploaded_at": "2026-01-01T00:00:00+00:00"}, {"paper_id": "one", "file_name": "two.pdf", "uploaded_at": "2026-01-01T00:00:00+00:00"}],
        [{"paper_id": "../escape", "file_name": "x.pdf", "uploaded_at": "2026-01-01T00:00:00+00:00"}],
    ],
)
def test_invalid_records_fail_closed_without_overwriting(tmp_path, records):
    meta = _write_legacy(tmp_path, records)
    before = meta.read_bytes()
    with pytest.raises(KnowledgeDocumentMigrationError) as error:
        migrate_papers_json(meta, tmp_path / "papers")
    assert error.value.code == MIGRATION_INPUT_INVALID
    assert meta.read_bytes() == before
    assert not (tmp_path / "papers.json.pre-018-document-v1.bak").exists()


def test_corrupt_json_is_not_treated_as_empty_database(tmp_path):
    meta = tmp_path / "papers.json"
    meta.write_bytes(b"not-json")
    with pytest.raises(KnowledgeDocumentMigrationError) as error:
        migrate_papers_json(meta, tmp_path / "papers")
    assert error.value.code == MIGRATION_INPUT_INVALID
    assert meta.read_bytes() == b"not-json"


def test_corrupt_json_blocks_store_save_without_replacing_bytes(tmp_path):
    meta = tmp_path / "papers.json"
    meta.write_bytes(b"not-json")
    with pytest.raises(MetadataStoreError) as error:
        save_papers([], meta)
    assert error.value.code == "METADATA_INVALID"
    assert meta.read_bytes() == b"not-json"


def test_interrupted_replace_keeps_original_and_backup(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "paper-1.pdf").write_bytes(b"source")
    meta = _write_legacy(tmp_path, [_legacy()])
    original = meta.read_bytes()
    import backend.app.knowledge_base.infrastructure.migration as migration

    real_replace = migration.os.replace
    calls = []

    def fail_output_replace(source, target):
        calls.append((source, target))
        if len(calls) == 2:
            raise OSError("interrupted metadata replace")
        return real_replace(source, target)

    monkeypatch.setattr(migration.os, "replace", fail_output_replace)
    with pytest.raises(KnowledgeDocumentMigrationError):
        migrate_papers_json(meta, papers)
    assert meta.read_bytes() == original
    assert (tmp_path / "papers.json.pre-018-document-v1.bak").read_bytes() == original


def test_post_replace_directory_fsync_failure_rolls_back_and_retry_is_deterministic(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "paper-1.pdf").write_bytes(b"source")
    meta = _write_legacy(tmp_path, [_legacy()])
    original = meta.read_bytes()
    import backend.app.knowledge_base.infrastructure.migration as migration

    real_fsync = migration._fsync_directory
    calls = []

    def fail_output_fsync(directory):
        calls.append(directory)
        if len(calls) == 2:
            raise OSError("directory durability failure")
        return real_fsync(directory)

    monkeypatch.setattr(migration, "_fsync_directory", fail_output_fsync)
    with pytest.raises(KnowledgeDocumentMigrationError):
        migrate_papers_json(meta, papers)
    assert meta.read_bytes() == original
    assert (tmp_path / "papers.json.pre-018-document-v1.bak").read_bytes() == original

    monkeypatch.setattr(migration, "_fsync_directory", real_fsync)
    result = migrate_papers_json(meta, papers)
    assert result["already_migrated"] is False
    assert json.loads(meta.read_text(encoding="utf-8"))[0]["document_id"] == "paper-1"


def test_missing_input_requires_explicit_first_initialization(tmp_path):
    meta = tmp_path / "papers.json"
    with pytest.raises(KnowledgeDocumentMigrationError):
        migrate_papers_json(meta, tmp_path / "papers")
    result = migrate_papers_json(meta, tmp_path / "papers", allow_missing=True)
    assert result["record_count"] == 0
    assert json.loads(meta.read_text(encoding="utf-8")) == []


def test_migrated_records_validate_against_frozen_schema(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "paper-1.pdf").write_bytes(b"source")
    meta = _write_legacy(tmp_path, [_legacy()])
    migrate_papers_json(meta, papers)
    schema_path = Path(__file__).resolve().parents[2] / "docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(json.loads(meta.read_text(encoding="utf-8"))[0])) == []


def test_store_identity_reads_canonical_document_id(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "paper-1.pdf").write_bytes(b"source")
    meta = _write_legacy(tmp_path, [_legacy()])
    migrate_papers_json(meta, papers)
    record = get_paper("paper-1", meta)
    assert record["document_id"] == "paper-1"
    assert resolve_paper_path(record, papers) == papers / "paper-1.pdf"


def test_naive_legacy_timestamp_is_deterministically_frozen_as_utc(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "naive.pdf").write_bytes(b"source")
    meta = _write_legacy(
        tmp_path,
        [_legacy("naive", uploaded_at="2026-01-01T00:00:00")],
    )
    migrate_papers_json(meta, papers)
    first = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert first["created_at"] == "2026-01-01T00:00:00+00:00"
    migrate_papers_json(meta, papers)
    assert json.loads(meta.read_text(encoding="utf-8"))[0]["created_at"] == first["created_at"]
