import hashlib
import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import backend.app.knowledge_base.application as application_module
from backend.app.knowledge_base.application import (
    KnowledgeDocumentMigrationError,
    create_immutable_document,
    create_paper_import_port,
)
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure.document_read import DocumentSourceReader
from backend.app.platform.ports import PaperImportRequest

PDF_ONE = b"%PDF-1.7\nimmutable-one"
PDF_TWO = b"%PDF-1.7\nimmutable-two"


def _create_from_fork(meta: str, papers: str, queue) -> None:
    try:
        result = create_immutable_document(
            "forked.pdf",
            "application/pdf",
            PDF_ONE,
            meta_path=Path(meta),
            papers_dir=Path(papers),
        )
        queue.put((result["document"]["document_id"], result["deduplicated"], None))
    except Exception as error:  # pragma: no cover - assertion reports child failure
        queue.put((None, None, repr(error)))


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "papers.json", tmp_path / "papers"


def test_legacy_save_upload_rejects_same_id_overwrite(tmp_path):
    papers = tmp_path / "papers"
    first_id, first_path = store_module.save_upload(
        "same.pdf", PDF_ONE, papers_dir=papers, paper_id="caller-id"
    )

    with pytest.raises(store_module.MetadataStoreError) as error:
        store_module.save_upload(
            "same.pdf", PDF_TWO, papers_dir=papers, paper_id=first_id
        )

    assert error.value.code == "SOURCE_ID_CONFLICT"
    assert first_path.read_bytes() == PDF_ONE


def test_legacy_save_upload_keeps_replacement_after_write_failure(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    original_fsync = store_module.os.fsync
    calls = 0

    def fail_after_replacing_target(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            original_fsync(descriptor)
            target = papers / "caller-id.pdf"
            target.unlink()
            target.write_bytes(b"caller-owned replacement")
            raise OSError("directory durability failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", fail_after_replacing_target)
    with pytest.raises(OSError):
        store_module.save_upload(
            "same.pdf", PDF_ONE, papers_dir=papers, paper_id="caller-id"
        )

    assert (papers / "caller-id.pdf").read_bytes() == b"caller-owned replacement"


def test_legacy_save_upload_keeps_replacement_after_cleanup_fstat(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    target = papers / "caller-id.pdf"
    original_fstat = store_module.os.fstat
    original_fsync = store_module.os.fsync
    fstat_calls = 0
    fsync_calls = 0

    def replace_after_cleanup_check(descriptor):
        nonlocal fstat_calls
        result = original_fstat(descriptor)
        fstat_calls += 1
        # Call 1 records the O_EXCL-created inode. Call 2 is the cleanup
        # helper's ownership check; replacement occurs immediately after it.
        if fstat_calls == 2:
            target.unlink()
            target.write_bytes(b"caller-owned replacement")
        return result

    def fail_directory_fsync(descriptor):
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("directory durability failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fstat", replace_after_cleanup_check)
    monkeypatch.setattr(store_module.os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError):
        store_module.save_upload(
            "same.pdf", PDF_ONE, papers_dir=papers, paper_id="caller-id"
        )

    assert target.read_bytes() == b"caller-owned replacement"
    assert fstat_calls == 2


def test_create_seam_keeps_replacement_after_cleanup_fstat(tmp_path, monkeypatch):
    meta, papers = _paths(tmp_path)
    original_fstat = application_module.os.fstat
    fstat_calls = 0

    def replace_after_cleanup_check(descriptor):
        nonlocal fstat_calls
        result = original_fstat(descriptor)
        fstat_calls += 1
        # The first call records the source token. The second is the failed
        # metadata cleanup probe, after which the directory entry is replaced.
        if fstat_calls == 2:
            target = next(papers.glob("*.pdf"))
            target.unlink()
            target.write_bytes(b"caller-owned replacement")
        return result

    def fail_metadata_write(*_args, **_kwargs):
        raise OSError("metadata disk failure")

    monkeypatch.setattr(application_module.os, "fstat", replace_after_cleanup_check)
    monkeypatch.setattr(application_module, "write_import_knowledge_document", fail_metadata_write)

    with pytest.raises(OSError):
        create_immutable_document(
            "same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers
        )

    targets = list(papers.glob("*.pdf"))
    assert len(targets) == 1
    assert targets[0].read_bytes() == b"caller-owned replacement"
    assert fstat_calls == 2


def test_create_seam_rejects_different_immutable_lock_domains(tmp_path):
    meta = tmp_path / "metadata" / "papers.json"
    papers = tmp_path / "sources" / "papers"

    with pytest.raises(KnowledgeDocumentMigrationError) as error:
        create_immutable_document(
            "same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers
        )

    assert error.value.code == "IMMUTABLE_LOCK_DOMAIN_MISMATCH"
    assert not meta.exists()
    assert not papers.exists()


def test_create_seam_deduplicates_hash_media_and_keeps_etag_source_consistent(tmp_path):
    meta, papers = _paths(tmp_path)
    first = create_immutable_document(
        "same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers
    )
    second = create_immutable_document(
        "renamed.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers
    )

    assert second["deduplicated"] is True
    assert second["document"]["document_id"] == first["document"]["document_id"]
    document = first["document"]
    assert document["source_sha256"] == hashlib.sha256(PDF_ONE).hexdigest()
    head = DocumentSourceReader(meta_path=meta, papers_dir=papers).head(document["document_id"])
    assert head.etag == f'"sha256:{document["source_sha256"]}"'


def test_create_seam_same_name_different_bytes_gets_new_server_id(tmp_path):
    meta, papers = _paths(tmp_path)
    first = create_immutable_document(
        "same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers
    )
    second = create_immutable_document(
        "same.pdf", "application/pdf", PDF_TWO, meta_path=meta, papers_dir=papers
    )

    assert second["deduplicated"] is False
    assert second["document"]["document_id"] != first["document"]["document_id"]
    assert second["document"]["stored_name"] != first["document"]["stored_name"]
    assert (papers / first["document"]["stored_name"]).read_bytes() == PDF_ONE
    assert (papers / second["document"]["stored_name"]).read_bytes() == PDF_TWO
    records = json.loads(meta.read_text(encoding="utf-8"))
    assert len(records) == 2


def test_create_seam_concurrent_same_source_has_one_winner(tmp_path):
    meta, papers = _paths(tmp_path)

    def create(_index):
        return create_immutable_document(
            "concurrent.pdf", "application/pdf", PDF_ONE,
            meta_path=meta, papers_dir=papers,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(create, range(8)))

    ids = {item["document"]["document_id"] for item in results}
    assert ids == {results[0]["document"]["document_id"]}
    assert sum(not item["deduplicated"] for item in results) == 1
    records = json.loads(meta.read_text(encoding="utf-8"))
    assert len(records) == 1
    record = records[0]
    assert record["source_sha256"] == hashlib.sha256(PDF_ONE).hexdigest()
    assert (papers / record["stored_name"]).read_bytes() == PDF_ONE


def test_create_seam_concurrent_forked_processes_have_one_canonical_and_no_orphan(tmp_path):
    meta, papers = _paths(tmp_path)
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    workers = [
        context.Process(target=_create_from_fork, args=(str(meta), str(papers), queue))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=10) for _ in workers]
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    assert all(error is None for _, _, error in results)
    assert len({document_id for document_id, _, _ in results}) == 1
    assert sum(not deduplicated for _, deduplicated, _ in results) == 1
    records = json.loads(meta.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert [path.name for path in papers.glob("*.pdf")] == [records[0]["stored_name"]]


def test_create_seam_does_not_unlink_preexisting_dangling_symlink_on_exclusive_failure(tmp_path, monkeypatch):
    meta, papers = _paths(tmp_path)
    papers.mkdir()
    target = papers / "same.pdf"
    target.symlink_to("missing-source.pdf")

    # A dangling symlink is invisible to Path.exists(), but O_EXCL must still
    # reject it and the failed create must not remove it.
    monkeypatch.setattr(application_module, "_unique_server_name", lambda *_args: "same.pdf")
    with pytest.raises(FileExistsError):
        create_immutable_document("same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers)

    assert target.is_symlink()
    assert not meta.exists()


def test_create_seam_does_not_unlink_preexisting_file_on_exclusive_failure(tmp_path, monkeypatch):
    meta, papers = _paths(tmp_path)
    papers.mkdir()
    target = papers / "same.pdf"
    target.write_bytes(b"caller-owned source")
    monkeypatch.setattr(application_module, "_unique_server_name", lambda *_args: "same.pdf")

    with pytest.raises(FileExistsError):
        create_immutable_document("same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers)

    assert target.read_bytes() == b"caller-owned source"


def test_create_seam_cleanup_keeps_replaced_target_after_metadata_failure(tmp_path, monkeypatch):
    meta, papers = _paths(tmp_path)

    def unexpected_lstat(_path):
        pytest.fail("ownership cleanup must not use lstat followed by unlink")

    monkeypatch.setattr(Path, "lstat", unexpected_lstat)

    def fail_after_replace(document, meta_path):
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps([document]), encoding="utf-8")
        path = papers / document["stored_name"]
        path.unlink()
        path.write_bytes(b"caller-owned replacement")
        raise OSError("metadata disk failure")

    monkeypatch.setattr(application_module, "write_import_knowledge_document", fail_after_replace)

    with pytest.raises(OSError):
        create_immutable_document("same.pdf", "application/pdf", PDF_ONE, meta_path=meta, papers_dir=papers)

    targets = list(papers.glob("*.pdf"))
    assert len(targets) == 1
    assert targets[0].read_bytes() == b"caller-owned replacement"


def test_paper_import_adapter_uses_hash_media_seam_across_candidate_identities(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    first_source.write_bytes(PDF_ONE)
    second_source.write_bytes(PDF_ONE)
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda record, path: {"status": "indexed"},
    )

    first = port.import_paper(PaperImportRequest(
        {"title": "First", "year": 2026, "conference_id": "ccs", "doi": "10.1/first", "_stored_name": "paper.pdf"},
        first_source,
    ))
    second = port.import_paper(PaperImportRequest(
        {"title": "Second", "year": 2026, "conference_id": "ccs", "doi": "10.1/second", "_stored_name": "other.pdf"},
        second_source,
    ))

    assert second.existing is True
    assert second.paper_id == first.paper_id
    assert len(json.loads(meta.read_text(encoding="utf-8"))) == 1


def test_paper_import_adapter_same_name_different_bytes_keeps_both_sources(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    first_source.write_bytes(PDF_ONE)
    second_source.write_bytes(PDF_TWO)
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda record, path: {"status": "indexed"},
    )

    first = port.import_paper(PaperImportRequest(
        {"title": "First", "year": 2026, "conference_id": "ccs", "doi": "10.1/first", "_stored_name": "paper.pdf"},
        first_source,
    ))
    second = port.import_paper(PaperImportRequest(
        {"title": "Second", "year": 2026, "conference_id": "ccs", "doi": "10.1/second", "_stored_name": "paper.pdf"},
        second_source,
    ))

    assert first.paper_id != second.paper_id
    assert second.stored_name == "paper-2.pdf"
    assert (papers / first.stored_name).read_bytes() == PDF_ONE
    assert (papers / second.stored_name).read_bytes() == PDF_TWO
