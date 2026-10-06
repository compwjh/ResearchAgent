import json
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.knowledge_base.application import (
    KnowledgeDocumentMigrationError,
    create_uploaded_document,
)
from backend.app.knowledge_base.infrastructure.migration import (
    MIGRATION_INPUT_INVALID,
    build_uploaded_knowledge_document,
    migrate_papers_json,
    write_import_knowledge_document,
)
from backend.app.knowledge_base.infrastructure.store import (
    AUTO_REQUEUED_CHUNKERS,
    CHUNKER_V1,
    CHUNKER_V2,
    is_chunker_auto_requeued,
    load_papers,
    mark_chunker_auto_requeued,
)

MARKED_AT = "2026-10-06T13:28:30+00:00"


def _candidate(tmp_path: Path) -> tuple[dict, Path, Path]:
    papers = tmp_path / "papers"
    papers.mkdir()
    source = papers / "seed.md"
    source.write_bytes(b"# seed\n")
    meta = tmp_path / "papers.json"
    document = build_uploaded_knowledge_document(
        document_id="seed-document",
        file_name="seed.md",
        stored_name="seed.md",
        media_type="text/markdown",
        source_path=source,
    )
    return document, meta, papers


@pytest.mark.parametrize(
    ("file_name", "media_type", "content"),
    [
        ("new.md", "text/markdown", b"# new markdown\n"),
        ("new.pdf", "application/pdf", b"%PDF-1.7\nnew pdf\n"),
    ],
)
def test_existing_auto_requeue_marker_does_not_block_new_upload(
    tmp_path: Path,
    file_name: str,
    media_type: str,
    content: bytes,
):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    existing = create_uploaded_document(
        "existing.md",
        "text/markdown",
        b"# existing\n",
        meta_path=meta,
        papers_dir=papers,
    )
    mark_chunker_auto_requeued(existing["document"]["document_id"], CHUNKER_V2, meta)

    created = create_uploaded_document(
        file_name,
        media_type,
        content,
        meta_path=meta,
        papers_dir=papers,
    )

    assert created["deduplicated"] is False
    records = json.loads(meta.read_text(encoding="utf-8"))
    marked = next(item for item in records if item["document_id"] == existing["document"]["document_id"])
    assert set(marked[AUTO_REQUEUED_CHUNKERS]) == {CHUNKER_V2}
    assert datetime.fromisoformat(marked[AUTO_REQUEUED_CHUNKERS][CHUNKER_V2]).tzinfo is not None
    assert len(records) == 2


@pytest.mark.parametrize(
    "markers",
    [
        {CHUNKER_V1: MARKED_AT, CHUNKER_V2: MARKED_AT},
        {CHUNKER_V1: MARKED_AT},
        {"v3": MARKED_AT},
        {CHUNKER_V1: "not-a-date"},
        {CHUNKER_V1: 123},
        [],
        "not-a-map",
    ],
    ids=["both-chunkers", "one-chunker", "unknown-chunker", "bad-timestamp", "bad-value-type", "list", "string"],
)
def test_auto_requeue_marker_schema_is_strict(tmp_path: Path, markers):
    document, meta, _papers = _candidate(tmp_path)
    document[AUTO_REQUEUED_CHUNKERS] = markers

    if isinstance(markers, dict) and set(markers) <= {CHUNKER_V1, CHUNKER_V2} and all(
        isinstance(value, str) and value == MARKED_AT for value in markers.values()
    ):
        persisted = write_import_knowledge_document(document, meta)
        assert persisted[AUTO_REQUEUED_CHUNKERS] == markers
    else:
        with pytest.raises(KnowledgeDocumentMigrationError) as error:
            write_import_knowledge_document(document, meta)
        assert error.value.code == MIGRATION_INPUT_INVALID
        assert not meta.exists()


def test_legacy_migration_preserves_valid_auto_requeue_marker(tmp_path: Path):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "legacy.md").write_bytes(b"# legacy\n")
    meta = tmp_path / "papers.json"
    meta.write_text(
        json.dumps(
            [
                {
                    "paper_id": "legacy-document",
                    "file_name": "legacy.md",
                    "stored_name": "legacy.md",
                    "status": "indexed",
                    "page_count": 0,
                    "chunk_count": 1,
                    "uploaded_at": MARKED_AT,
                    "error": None,
                    "chunkers": {"v1": {"status": "indexed", "chunk_count": 1, "progress": 100, "error": None}},
                    AUTO_REQUEUED_CHUNKERS: {CHUNKER_V1: MARKED_AT},
                }
            ]
        ),
        encoding="utf-8",
    )

    migrate_papers_json(meta, papers)

    record = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert record[AUTO_REQUEUED_CHUNKERS] == {CHUNKER_V1: MARKED_AT}


def test_auto_requeue_marker_is_per_chunker_and_restart_idempotent(tmp_path: Path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    document = create_uploaded_document(
        "retry.md",
        "text/markdown",
        b"# retry\n",
        meta_path=meta,
        papers_dir=papers,
    )["document"]
    document_id = document["document_id"]

    mark_chunker_auto_requeued(document_id, CHUNKER_V1, meta)
    first = next(item for item in load_papers(meta) if item["document_id"] == document_id)
    first_marker = first[AUTO_REQUEUED_CHUNKERS][CHUNKER_V1]
    mark_chunker_auto_requeued(document_id, CHUNKER_V1, meta)
    mark_chunker_auto_requeued(document_id, CHUNKER_V2, meta)
    second = next(item for item in load_papers(meta) if item["document_id"] == document_id)

    assert set(second[AUTO_REQUEUED_CHUNKERS]) == {CHUNKER_V1, CHUNKER_V2}
    assert datetime.fromisoformat(first_marker).tzinfo is not None
    assert is_chunker_auto_requeued(document_id, CHUNKER_V1, meta)
    assert is_chunker_auto_requeued(document_id, CHUNKER_V2, meta)
