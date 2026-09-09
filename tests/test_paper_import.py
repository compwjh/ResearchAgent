import json
import time
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from backend.app.knowledge_base import application as kb_application
from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure import tasks as tasks_module
from backend.app.knowledge_base.infrastructure.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    get_paper,
    load_papers,
    new_record,
    resolve_paper_path,
    upsert_paper,
)
from backend.app.paper_discovery.application.paper_import import (
    KB_IMPORT_FAILED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    import_candidate,
)
from backend.app.paper_discovery.infrastructure.paper_download import DownloadResult, PaperDownloadError
from backend.app.platform.ports import (
    ImportIndexStatus,
    PaperImportRequest,
)
from backend.app.platform.ports import (
    PaperImportResult as PortImportResult,
)
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
        meta_path.write_text("[" + json.dumps(record.to_dict()) + "]", encoding="utf-8")
        raise OSError("metadata disk failure")

    monkeypatch.setattr("backend.app.knowledge_base.application.upsert_paper", failed_upsert)
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


# ---------------------------------------------------------------------------
# BUG-02（spec-020 Task03）：导入路径须与上传对齐，v1 建完后异步提交 v2。
# ---------------------------------------------------------------------------

def _port_default(papers, meta):
    return create_paper_import_port(papers_dir=papers, meta_path=meta)


def _make_record(meta, name="paper.pdf"):
    record = new_record(name)
    record.status = STATUS_INDEXING
    upsert_paper(record, meta)
    return record


def test_default_indexer_submits_v2_after_v1(tmp_path):
    """v1 同步建完后必须异步提交 v2，使 v2 状态不再恒 pending。"""
    papers = tmp_path / "papers"
    papers.mkdir()
    meta = tmp_path / "papers.json"
    path = papers / "paper.pdf"
    path.write_bytes(b"%PDF-1.7\ncontent")
    adapter = _port_default(papers, meta)
    record = _make_record(meta)

    writes = []
    real_update = kb_application.update_chunker_state
    kb_application.update_chunker_state = lambda *a, **k: (writes.append((a, k)), {"status": "indexing"})[1]
    try:
        with patch.object(kb_application, "run_index_task_sync", return_value={"status": STATUS_INDEXED}) as mock_sync, \
             patch.object(kb_application, "submit_index_task", return_value=True) as mock_submit:
            result = adapter._default_indexer(record, path)
    finally:
        kb_application.update_chunker_state = real_update

    mock_sync.assert_called_once()
    assert mock_sync.call_args.args[1] == CHUNKER_V1
    mock_submit.assert_called_once()
    assert mock_submit.call_args.args[1] == CHUNKER_V2
    # 导入返回的是 v1 结果，v2 在后台跑，不阻塞。
    assert result == {"status": STATUS_INDEXED}
    # update_chunker_state(paper_id, chunker, status=..., ...)：chunker 为位置参数。
    indexing_v2 = [
        (a, k) for (a, k) in writes
        if k.get("status") == STATUS_INDEXING and len(a) >= 2 and a[1] == CHUNKER_V2
    ]
    assert indexing_v2, "提交 v2 前必须把状态置为 indexing"


def test_v2_failure_does_not_fail_import(tmp_path):
    """v2 索引失败不得把导入判定为失败；v2 状态须真实置 failed 并带原因。"""
    papers = tmp_path / "papers"
    papers.mkdir()
    meta = tmp_path / "papers.json"
    path = papers / "paper.pdf"
    path.write_bytes(b"%PDF-1.7\ncontent")
    adapter = _port_default(papers, meta)
    record = _make_record(meta)

    writes = []
    real_update = store_module.update_chunker_state
    # 捕获 _guarded_run 在后台线程内对 v2 的 failed 回写（不拘持久化）。
    store_module.update_chunker_state = lambda *a, **k: (writes.append(k), {"status": "indexing"})[1]
    try:
        with patch.object(kb_application, "run_index_task_sync", return_value={"status": STATUS_INDEXED}), \
             patch.object(kb_application, "index_paper_chunker", side_effect=RuntimeError("27B 模型不可用")):
            result = adapter._default_indexer(record, path)
            time.sleep(1.0)  # 等待 v2 后台任务在单线程池内执行并失败
    finally:
        store_module.update_chunker_state = real_update
        tasks_module.shutdown(wait=False)

    assert result == {"status": STATUS_INDEXED}, "v2 失败不得影响导入成功"
    failed = [w for w in writes if w.get("status") == STATUS_FAILED]
    assert failed, "v2 失败后状态必须置 failed"
    assert any(w.get("error") for w in failed), "v2 失败必须带原因"


def test_import_paper_submits_v2_with_default_indexer(tmp_path):
    """默认索引器（未经注入）下，import_paper 也须提交 v2 且返回成功。"""
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\ncontent")

    adapter = _port_default(papers, meta)
    snapshot = {
        "title": "A Safe Paper", "year": 2025, "conference_id": "ccs",
        "conference_name": "ACM CCS", "doi": "10.1234/example",
        "dblp_key": "conf/ccs/Safe", "article_url": "https://papers.example/article",
        "authors": ["A. Author"], "_stored_name": "2025-CCS-A-Safe-Paper.pdf",
    }
    with patch.object(kb_application, "run_index_task_sync", return_value={"status": STATUS_INDEXED}) as mock_sync, \
         patch.object(kb_application, "submit_index_task", return_value=True) as mock_submit:
        result = adapter.import_paper(PaperImportRequest(snapshot, source))

    assert result.index_status == ImportIndexStatus.INDEXED
    mock_sync.assert_called_once()
    assert mock_sync.call_args.args[1] == CHUNKER_V1
    mock_submit.assert_called_once()
    assert mock_submit.call_args.args[1] == CHUNKER_V2
