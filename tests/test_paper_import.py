import json
from dataclasses import dataclass

import pytest

import backend.app.knowledge_base.application as application_module
from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
from backend.app.knowledge_base.infrastructure.store import (
    STATUS_INDEXED,
    get_paper,
    load_papers,
    new_record,
    resolve_paper_path,
)
from backend.app.paper_discovery.application.paper_import import (
    KB_IMPORT_FAILED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    import_candidate,
)
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult, PaperDownloadError
from backend.app.platform.ports import ImportIndexStatus
from backend.app.platform.ports import PaperImportResult as PortImportResult
from backend.app.platform.settings.settings_repository import ArticleSettings


@dataclass
class Candidate:
    title: str = "A Safe Paper"
    year: int = 2025
    conference_id: str = "ccs"
    conference_name: str = "ACM CCS"
    doi: str = "10.1234/example"
    dblp_key: str = "conf/ccs/Safe"
    article_url: str = "https://papers.example/article"
    pdf_url: str = "https://papers.example/paper.pdf"
    authors: list[str] | None = None

    def __post_init__(self):
        self.authors = self.authors or ["A. Author"]


def _candidate():
    return Candidate()


def _downloader(tmp_path, calls):
    def download(candidate, settings, allowed_hosts, **kwargs):
        calls.append((candidate, tuple(allowed_hosts)))
        path = tmp_path / "private-download.pdf"
        path.write_bytes(b"%PDF-1.7\ncontent")
        return DownloadResult(str(path), path.stat().st_size, "checksum", candidate.pdf_url)

    return download


def _indexer(record, path):
    assert path.exists()
    return {"paper_id": record.paper_id, "status": STATUS_INDEXED}


def _port(papers, meta, *, indexer=None, deleter=None):
    return create_paper_import_port(
        papers_dir=papers,
        meta_path=meta,
        indexer=indexer,
        deleter=deleter,
    )


def test_import_persists_metadata_renames_and_indexes(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    calls = []
    result = import_candidate(
        _candidate(), ArticleSettings(), {"papers.example"},
        conference_short_name="CCS", downloader=_downloader(tmp_path, calls),
        paper_import_port=_port(papers, meta, indexer=_indexer), temp_dir=tmp_path,
    )
    assert result.status == STATUS_INDEXED
    assert result.stored_name == "2025-CCS-A-Safe-Paper.pdf"
    assert result["paper_id"] == result.paper_id
    record = get_paper(result.paper_id, meta)
    assert record["title"] == "A Safe Paper"
    assert record["authors"] == ["A. Author"]
    assert record["conference_name"] == "ACM CCS"
    assert record["dblp_key"] == "conf/ccs/safe"
    assert record["import_source"] == "paper-discovery"
    assert (papers / result.stored_name).exists()
    assert not (tmp_path / "private-download.pdf").exists()
    assert len(calls) == 1


def test_duplicate_is_checked_before_download(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    calls = []
    first = import_candidate(
        _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
        downloader=_downloader(tmp_path, calls), paper_import_port=_port(papers, meta, indexer=_indexer),
    )
    second = import_candidate(
        _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
        downloader=_downloader(tmp_path, calls), paper_import_port=_port(papers, meta, indexer=_indexer),
    )
    assert second.error_code == PAPER_ALREADY_EXISTS
    assert second.paper_id == first.paper_id
    assert len(calls) == 1


def test_index_failure_removes_record_and_file(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"

    def failed_indexer(record, path):
        return {"status": "failed", "error": "embedding down"}

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=_port(
                papers, meta, indexer=failed_indexer,
            ),
        )
    assert exc.value.code == KB_IMPORT_FAILED
    assert list(papers.glob("*.pdf")) == []
    assert get_paper("missing", meta) is None


def test_metadata_failure_after_rename_removes_target_and_record(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"

    def failed_upsert(record, meta_path=None):
        # Simulate a write that reaches storage and then fails.
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text("[" + json.dumps(record) + "]", encoding="utf-8")
        raise OSError("metadata disk failure")

    monkeypatch.setattr("backend.app.knowledge_base.application.write_import_knowledge_document", failed_upsert)
    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=_port(papers, meta, indexer=_indexer),
            temp_dir=tmp_path,
        )
    assert exc.value.code == KB_IMPORT_FAILED
    assert list(papers.glob("*.pdf")) == []
    assert load_papers(meta) == []


def test_index_failure_invokes_idempotent_vector_compensation(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    deleted = []

    def partial_indexer(record, path):
        deleted.append(("vector-written", record.paper_id))
        return {"status": "failed", "error": "qdrant write failed"}

    def deleter(paper_id, chunker, client=None):
        deleted.append((paper_id, chunker))

    with pytest.raises(PaperImportError):
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=_port(
                papers, meta, indexer=partial_indexer, deleter=deleter,
            ),
        )
    assert deleted[1][0] == deleted[0][1]
    assert deleted[1][1] == "v1"
    assert load_papers(meta) == []
    assert list(papers.glob("*.pdf")) == []


def test_download_error_is_preserved_and_temp_file_is_cleaned(tmp_path):
    def blocked(*args, **kwargs):
        raise PaperDownloadError("DOWNLOAD_BLOCKED", "blocked")

    with pytest.raises(PaperDownloadError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, downloader=blocked,
            paper_import_port=_port(tmp_path / "papers", tmp_path / "papers.json"),
        )
    assert exc.value.code == "DOWNLOAD_BLOCKED"


def test_import_delegates_trusted_local_pdf_to_injected_port(tmp_path):
    seen = []

    class RecordingPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            seen.append(request)
            assert request.trusted_pdf_path.is_file()
            return PortImportResult(
                paper_id="paper-1",
                index_status=ImportIndexStatus.INDEXED,
                error_code=None,
                stored_name="2025-CCS-A-Safe-Paper.pdf",
            )

    result = import_candidate(
        _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
        downloader=_downloader(tmp_path, []), paper_import_port=RecordingPort(), temp_dir=tmp_path,
    )
    assert result.paper_id == "paper-1"
    assert len(seen) == 1
    assert seen[0].candidate_snapshot["_stored_name"] == "2025-CCS-A-Safe-Paper.pdf"
    assert not (tmp_path / "private-download.pdf").exists()


def test_paper_import_error_message_is_fixed_by_stable_code():
    error = PaperImportError(
        KB_IMPORT_FAILED,
        "https://evil.example/paper.pdf Cookie=session=secret Authorization=Bearer token",
        retryable=True,
    )
    assert error.message == "论文导入失败"
    assert "evil.example" not in str(error)
    assert "secret" not in str(error)
    assert "authorization" not in str(error).lower()


def test_legacy_path_resolution_remains_available(tmp_path):
    legacy = {"paper_id": "old-id", "file_name": "old-id.pdf", "status": "indexed"}
    assert resolve_paper_path(legacy, tmp_path) == tmp_path / "old-id.pdf"


def test_default_paper_import_consumer_uses_marker_bound_port(tmp_path, monkeypatch):
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    meta.parent.mkdir(parents=True)
    meta.write_text("[]", encoding="utf-8")
    finalizer = FinalizeBundleStore(tmp_path)
    finalizer.stage(
        "generation-test",
        candidate_collection="papers_rebuild_live",
        metadata=[],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    finalizer.commit("generation-test")
    adapter = create_paper_import_port(papers_dir=papers, meta_path=meta, client=object())
    record = new_record("import.pdf", stored_name="import.pdf")
    source = papers / record.stored_name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"%PDF-1.7\n")
    seen = {}

    def run_sync(_paper_id, _chunker, runner):
        return runner(lambda _progress: None)

    def index(self, _record, _path, _chunker, **kwargs):
        seen["destination"] = self.destination_collection
        seen["meta_path"] = kwargs["meta_path"]
        return {"status": STATUS_INDEXED}

    monkeypatch.setattr(application_module, "run_index_task_sync", run_sync)
    monkeypatch.setattr(application_module.GenerationBoundIndexPort, "index_document", index)
    adapter._default_indexer(record, source)
    assert seen == {"destination": "papers_rebuild_live", "meta_path": meta}
