import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import backend.app.knowledge_base.infrastructure.store as store_module
import backend.app.paper_discovery.application.paper_import as paper_import_module
from backend.app.knowledge_base.application import create_immutable_document, create_paper_import_port
from backend.app.knowledge_base.infrastructure.store import (
    MetadataStoreError,
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
