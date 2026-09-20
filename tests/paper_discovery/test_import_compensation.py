import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import backend.app.knowledge_base.application as application_module
import backend.app.knowledge_base.infrastructure.store as store_module
import backend.app.paper_discovery.application.paper_import as paper_import_module
from backend.app.knowledge_base.application import (
    KnowledgeDocumentMigrationError,
    create_immutable_document,
    create_paper_import_port,
)
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
from backend.app.knowledge_base.infrastructure.store import (
    STATUS_INDEXING,
    MetadataStoreError,
    PaperRecord,
    compensate_import_resource,
    get_paper,
)
from backend.app.paper_discovery.application.paper_import import (
    _cleanup_attempt_root,
    _cleanup_download,
    import_candidate,
)
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult
from backend.app.platform.ports import PaperImportRequest
from backend.app.platform.settings.settings_repository import ArticleSettings

PDF = b"%PDF-1.7\ncompensation-fixture"


def _capability(tmp_path, *, owner="owner-a", token="token-a"):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    created = create_immutable_document(
        "paper.pdf",
        "application/pdf",
        source_path=source,
        owner=owner,
        token=token,
        meta_path=meta,
        papers_dir=papers,
    )
    return papers, meta, source, created["resource_capability"]


def _generation_capability(tmp_path):
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True)
    meta.write_text("[]", encoding="utf-8")
    FinalizeBundleStore(root).stage(
        "generation-one",
        candidate_collection="papers_rebuild_one",
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("generation-one")
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda _record, _path: {"status": "indexed"},
    )
    result = port.import_paper(PaperImportRequest(
        {"title": "Bound", "year": 2026, "conference_id": "ccs", "doi": "10/bound"},
        source,
    ))
    assert result.resource_capability is not None
    return root, meta, papers, source, port, result.resource_capability


def test_compensation_is_fail_closed_for_same_owner_and_token(tmp_path):
    papers, meta, _source, capability = _capability(tmp_path)

    assert compensate_import_resource(capability, meta, papers) == "cleanup_pending"
    assert compensate_import_resource(capability, meta, papers) == "cleanup_pending"
    assert get_paper(capability.document_id, meta) is not None
    assert (papers / capability.stored_name).read_bytes() == PDF


def test_compensation_replacement_after_fd_check_is_retained(tmp_path, monkeypatch):
    papers, meta, _source, capability = _capability(tmp_path)
    target = papers / capability.stored_name
    original_fstat = store_module.os.fstat
    calls = 0

    def replace_after_check(descriptor):
        nonlocal calls
        result = original_fstat(descriptor)
        calls += 1
        if calls == 1:
            target.unlink()
            target.write_bytes(b"replacement")
        return result

    monkeypatch.setattr(store_module.os, "fstat", replace_after_check)
    assert compensate_import_resource(capability, meta, papers) == "cleanup_pending"
    assert target.read_bytes() == b"replacement"
    assert get_paper(capability.document_id, meta) is not None


def test_compensation_rejects_different_owner_or_token_and_keeps_source(tmp_path):
    papers, meta, _source, capability = _capability(tmp_path)

    for forged in (
        replace(capability, owner="other-owner"),
        replace(capability, token="other-token"),
        replace(capability, source_sha256=hashlib.sha256(b"other").hexdigest()),
    ):
        with pytest.raises(MetadataStoreError) as exc:
            compensate_import_resource(forged, meta, papers)
        assert exc.value.code == "COMPENSATION_DENIED"
    assert (papers / capability.stored_name).read_bytes() == PDF
    assert get_paper(capability.document_id, meta) is not None


@pytest.mark.parametrize("destination", [None, "papers_rebuild_two"])
def test_compensation_rejects_destination_collection_tampering(tmp_path, destination):
    _root, meta, papers, _source, _port, capability = _generation_capability(tmp_path)
    forged = replace(capability, destination_collection=destination)

    with pytest.raises(MetadataStoreError) as exc:
        compensate_import_resource(forged, meta, papers)

    assert exc.value.code == "COMPENSATION_DENIED"
    assert (papers / capability.stored_name).read_bytes() == PDF
    assert get_paper(capability.document_id, meta) is not None


def test_index_failure_with_unknown_vector_delete_is_cleanup_pending(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)

    def failed_indexer(_record, _path):
        return {"status": "failed"}

    def unknown_deleter(*_args, **_kwargs):
        raise OSError("vector result unknown")

    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=failed_indexer,
        deleter=unknown_deleter,
    )
    result = port.import_paper(PaperImportRequest(
        {"title": "Pending", "year": 2026, "conference_id": "ccs", "doi": "10/pending", "_stored_name": "paper.pdf"},
        source,
    ))

    assert result.cleanup_status == "cleanup_pending"
    assert result.paper_id
    assert result.resource_capability is not None
    assert (papers / result.resource_capability.stored_name).exists()
    assert get_paper(result.paper_id, meta) is not None


def test_cleanup_download_retains_preexisting_path(tmp_path):
    path = tmp_path / "preexisting.pdf"
    path.write_bytes(PDF)
    download = DownloadResult(str(path), len(PDF), "checksum", "https://papers.example/paper.pdf")

    _cleanup_download(download, attempt_root=tmp_path, preexisting_paths=(path,))

    assert path.read_bytes() == PDF


def test_cleanup_download_never_unlinks_single_path_after_identity_check(tmp_path, monkeypatch):
    path = tmp_path / "attempt" / "download.pdf"
    path.parent.mkdir()
    path.write_bytes(PDF)
    download = DownloadResult(str(path), len(PDF), "checksum", "https://papers.example/paper.pdf")

    def fail_if_path_unlink_called(*_args, **_kwargs):
        raise AssertionError("single-file cleanup must not unlink by pathname")

    monkeypatch.setattr(paper_import_module.Path, "unlink", fail_if_path_unlink_called)
    assert _cleanup_download(download, attempt_root=path.parent, file_token=None) == "cleanup_pending"
    assert path.read_bytes() == PDF


def test_cleanup_download_retains_replacement_path(tmp_path, monkeypatch):
    path = tmp_path / "attempt" / "download.pdf"
    path.parent.mkdir()
    path.write_bytes(PDF)
    download = DownloadResult(str(path), len(PDF), "checksum", "https://papers.example/paper.pdf")
    replacement = b"replacement"

    def replace_before_legacy_cleanup(*_args, **_kwargs):
        path.write_bytes(replacement)

    monkeypatch.setattr(paper_import_module.Path, "unlink", replace_before_legacy_cleanup)
    assert _cleanup_download(download, attempt_root=path.parent, file_token=None) == "cleanup_pending"
    assert path.read_bytes() == PDF


def test_compensation_ledger_flushes_file_and_directory(tmp_path, monkeypatch):
    ledger_path = tmp_path / "papers.json.paper-import-compensation.json"
    fsync_calls = []
    original_fsync = store_module.os.fsync

    def record_fsync(descriptor):
        fsync_calls.append(descriptor)
        return original_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", record_fsync)
    store_module._write_compensation_ledger(ledger_path, {"token": {"status": "created"}})

    assert len(fsync_calls) >= 2
    assert ledger_path.exists()


def test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it(tmp_path):
    seen: list[Path] = []

    def downloader(_candidate, _settings, _allowed_hosts, *, temp_dir=None, **_kwargs):
        assert temp_dir is not None
        root = Path(temp_dir)
        seen.append(root)
        path = root / "download.pdf"
        path.write_bytes(PDF)
        return DownloadResult(str(path), len(PDF), hashlib.sha256(PDF).hexdigest(), "https://papers.example/paper.pdf")

    class Port:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, _request):
            return {"paper_id": "paper-1", "status": "indexed", "stored_name": "paper.pdf"}

    caller_root = tmp_path / "caller-downloads"
    caller_root.mkdir()
    result = import_candidate(
        {"title": "Private", "year": 2026, "conference_id": "ccs", "doi": "10/private"},
        ArticleSettings(article_download_dir=str(caller_root)),
        {"papers.example"},
        downloader=downloader,
        paper_import_port=Port(),
    )

    assert result.paper_id == "paper-1"
    assert len(seen) == 1
    assert seen[0].parent == caller_root
    assert not seen[0].exists()
    assert caller_root.exists()


def test_import_with_explicit_temp_dir_retains_downloader_file_and_root(tmp_path):
    caller_root = tmp_path / "caller-downloads"
    caller_root.mkdir()
    path = caller_root / "download.pdf"

    def downloader(_candidate, _settings, _allowed_hosts, *, temp_dir=None, **_kwargs):
        assert Path(temp_dir) == caller_root
        path.write_bytes(PDF)
        return DownloadResult(str(path), len(PDF), "checksum", "https://papers.example/paper.pdf")

    class Port:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, _request):
            return {"paper_id": "paper-2", "status": "indexed", "stored_name": "paper.pdf"}

    result = import_candidate(
        {"title": "Explicit", "year": 2026, "conference_id": "ccs", "doi": "10/explicit"},
        ArticleSettings(),
        {"papers.example"},
        downloader=downloader,
        paper_import_port=Port(),
        temp_dir=caller_root,
    )

    assert result.paper_id == "paper-2"
    assert caller_root.exists()
    assert path.read_bytes() == PDF


def test_cleanup_attempt_root_does_not_follow_replaced_root_symlink(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    root = tmp_path / "attempt"
    root.symlink_to(external, target_is_directory=True)

    _cleanup_attempt_root(root)

    assert root.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_paper_import_capability_captures_generation_collection(tmp_path):
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True)
    meta.write_text("[]", encoding="utf-8")
    FinalizeBundleStore(root).stage(
        "generation-one",
        candidate_collection="papers_rebuild_one",
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("generation-one")

    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda _record, _path: {"status": "indexed"},
    )
    result = port.import_paper(PaperImportRequest(
        {"title": "Bound", "year": 2026, "conference_id": "ccs", "doi": "10/bound"},
        source,
    ))

    assert result.resource_capability is not None
    assert result.resource_capability.destination_collection == "papers_rebuild_one"


def test_default_deleter_uses_creation_generation_after_marker_drift(tmp_path, monkeypatch):
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True)
    meta.write_text("[]", encoding="utf-8")
    FinalizeBundleStore(root).stage(
        "generation-one",
        candidate_collection="papers_rebuild_one",
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("generation-one")
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    port = create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=lambda _record, _path: {"status": "indexed"},
    )
    result = port.import_paper(PaperImportRequest(
        {"title": "Drift", "year": 2026, "conference_id": "ccs", "doi": "10/drift"},
        source,
    ))
    capability = result.resource_capability
    assert capability is not None

    seen: list[str] = []

    def delete(self, _paper_id, _chunker):
        seen.append(self.destination_collection)

    monkeypatch.setattr(application_module.GenerationBoundIndexPort, "delete_document", delete)
    monkeypatch.setattr(
        application_module,
        "_active_generation_collection",
        lambda _meta, *, allow_stale_metadata=False: "papers_rebuild_two",
    )
    port._default_deleter(result.paper_id, capability=capability)

    assert seen == ["papers_rebuild_one"]


def test_default_indexer_uses_creation_generation_after_marker_drift(tmp_path, monkeypatch):
    _root, meta, papers, _source, port, capability = _generation_capability(tmp_path)
    record = PaperRecord(
        paper_id=capability.document_id,
        file_name=capability.stored_name,
        stored_name=capability.stored_name,
    )
    seen: list[str] = []

    def index(self, *_args, **_kwargs):
        seen.append(self.destination_collection)
        return {"status": "indexed"}

    monkeypatch.setattr(application_module.GenerationBoundIndexPort, "index_document", index)
    monkeypatch.setattr(
        application_module,
        "run_index_task_sync",
        lambda _paper_id, _chunker, runner: runner(lambda _progress: None),
    )
    monkeypatch.setattr(
        application_module,
        "submit_index_task",
        lambda _paper_id, _chunker, runner: runner(lambda _progress: None) or True,
    )
    monkeypatch.setattr(
        application_module,
        "_active_generation_collection",
        lambda _meta, *, allow_stale_metadata=False: "papers_rebuild_two",
    )

    port._default_indexer(
        record,
        papers / capability.stored_name,
        capability=capability,
    )

    assert seen == ["papers_rebuild_one", "papers_rebuild_one"]


def test_default_indexer_and_deleter_fail_closed_for_unbound_capability(tmp_path):
    _root, meta, papers, _source, port, capability = _generation_capability(tmp_path)
    missing_binding = replace(capability, destination_collection=None)
    record = PaperRecord(
        paper_id=capability.document_id,
        file_name=capability.stored_name,
        stored_name=capability.stored_name,
    )

    for action in (
        lambda: port._default_indexer(record, papers / capability.stored_name, capability=missing_binding),
        lambda: port._default_deleter(capability.document_id, capability=missing_binding),
    ):
        with pytest.raises(KnowledgeDocumentMigrationError) as exc:
            action()
        assert exc.value.code == "COMPENSATION_CAPABILITY_INVALID"


def test_import_generation_drift_never_marks_document_indexed(tmp_path, monkeypatch):
    root = tmp_path / "project"
    meta = root / "data" / "kb" / "papers.json"
    papers = root / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True)
    meta.write_text("[]", encoding="utf-8")
    FinalizeBundleStore(root).stage(
        "generation-one",
        candidate_collection="papers_rebuild_one",
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    FinalizeBundleStore(root).commit("generation-one")
    source = tmp_path / "drift.pdf"
    source.write_bytes(PDF)
    current = {"collection": "papers_rebuild_one"}

    def active_generation(_meta, *, allow_stale_metadata=False):
        return current["collection"]

    def indexer(_record, _path):
        current["collection"] = "papers_rebuild_two"
        return {"status": "indexed"}

    monkeypatch.setattr(application_module, "_active_generation_collection", active_generation)
    port = create_paper_import_port(papers_dir=papers, meta_path=meta, indexer=indexer)
    result = port.import_paper(PaperImportRequest(
        {"title": "Drift", "year": 2026, "conference_id": "ccs", "doi": "10/drift"},
        source,
    ))

    assert result.index_status.value == "failed"
    assert result.error_code.value == "KB_IMPORT_FAILED"
    assert result.cleanup_status == "cleanup_pending"
    assert result.paper_id
    record = get_paper(result.paper_id, meta)
    assert record is not None
    assert record["status"] == STATUS_INDEXING
    assert record["status"] != "indexed"


def test_default_paper_import_without_generation_marker_fails_before_create(tmp_path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    port = create_paper_import_port(papers_dir=papers, meta_path=meta)

    result = port.import_paper(PaperImportRequest(
        {"title": "No marker", "year": 2026, "conference_id": "ccs", "doi": "10/no-marker"},
        source,
    ))

    assert result.index_status.value == "failed"
    assert result.error_code.value == "KB_IMPORT_FAILED"
    assert not papers.exists()
    assert not meta.exists()
