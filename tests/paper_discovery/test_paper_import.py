import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.app.knowledge_base.application as application_module
from backend.app.knowledge_base import application as kb_application
from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure import tasks as tasks_module
from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore
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
from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BrowserManagerError,
)
from backend.app.paper_discovery.application.paper_import import (
    KB_IMPORT_FAILED,
    KB_STORAGE_LOCKED,
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
    # Explicit temp_dir belongs to the caller, so the orchestration layer
    # retains the downloader path even after a successful import.
    assert (tmp_path / "private-download.pdf").exists()
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


def test_index_failure_retains_owned_resources_for_cleanup_pending(tmp_path):
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
    assert exc.value.cleanup_status == "cleanup_pending"
    stored = list(papers.glob("*.pdf"))
    assert len(stored) == 1
    records = load_papers(meta)
    assert len(records) == 1
    assert get_paper(records[0]["document_id"], meta) is not None


def test_metadata_failure_after_create_retains_orphan_and_removes_record(tmp_path, monkeypatch):
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
    # Failed source cleanup is fail-closed: the create seam never unlinks by
    # pathname. Compensation/maintenance can identify and reclaim this
    # orphan later without risking a replacement owned by another writer.
    assert len(list(papers.glob("*.pdf"))) == 1
    assert load_papers(meta) == []


def test_index_failure_invokes_vector_compensation_and_retains_unknown_resources(tmp_path):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    deleted = []

    def partial_indexer(record, path):
        deleted.append(("vector-written", record.paper_id))
        return {"status": "failed", "error": "qdrant write failed"}

    def deleter(paper_id, chunker, client=None):
        deleted.append((paper_id, chunker))

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=_port(
                papers, meta, indexer=partial_indexer, deleter=deleter,
            ),
        )
    assert deleted[1][0] == deleted[0][1]
    assert deleted[1][1] == "v1"
    assert exc.value.cleanup_status == "cleanup_pending"
    assert len(load_papers(meta)) == 1
    assert len(list(papers.glob("*.pdf"))) == 1


def test_download_error_is_preserved_and_temp_file_is_cleaned(tmp_path):
    def blocked(*args, **kwargs):
        raise PaperDownloadError("DOWNLOAD_BLOCKED", "blocked")

    with pytest.raises(PaperDownloadError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, downloader=blocked,
            paper_import_port=_port(tmp_path / "papers", tmp_path / "papers.json"),
        )
    assert exc.value.code == "DOWNLOAD_BLOCKED"


def test_browser_session_expiry_crosses_import_boundary_without_kb_import(tmp_path):
    imported = []

    class RecordingPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            imported.append(request)

    def expired_downloader(*_args, **_kwargs):
        raise BrowserManagerError(
            BROWSER_SESSION_EXPIRED,
            "https://evil.example Cookie=session=secret",
            retryable=True,
        )

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"},
            downloader=expired_downloader, paper_import_port=RecordingPort(), temp_dir=tmp_path,
        )

    assert exc.value.code == BROWSER_SESSION_EXPIRED
    assert exc.value.error_code == BROWSER_SESSION_EXPIRED
    assert exc.value.message == "受控登录会话已过期，请重新登录"
    assert "evil.example" not in str(exc.value)
    assert "secret" not in str(exc.value)
    assert imported == []


def test_import_boundary_rechecks_expiry_before_port_write(tmp_path):
    imported = []
    now = [100.0]

    class ExpiringSession:
        def download_pdf(self, _candidate, _settings, _allowed_hosts, **_kwargs):
            path = tmp_path / "expired-session.pdf"
            path.write_bytes(b"%PDF-1.7\ncontent")
            now[0] = 106.0
            return DownloadResult(str(path), path.stat().st_size, "checksum", "https://dl.acm.org/paper.pdf")

        @contextmanager
        def import_boundary(self):
            if now[0] >= 105.0:
                raise BrowserManagerError(
                    BROWSER_SESSION_EXPIRED,
                    "expired session details must not cross the import boundary",
                )
            yield self

    class RecordingPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, request):
            imported.append(request)

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"},
            downloader=ExpiringSession().download_pdf,
            paper_import_port=RecordingPort(), temp_dir=tmp_path,
        )

    assert exc.value.code == BROWSER_SESSION_EXPIRED
    assert imported == []


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
    # An explicit temp_dir is caller-owned; paper discovery never removes its
    # downloaded files or parent directory by pathname.
    assert (tmp_path / "private-download.pdf").exists()


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

# ---------------------------------------------------------------------------
# BUG-02（spec-020 Task03）：导入路径须与上传对齐，v1 建完后异步提交 v2。
# ---------------------------------------------------------------------------

def _port_default(papers, meta):
    papers = Path(papers)
    meta = Path(meta)
    root = meta.parent.parent.parent
    live_root = root / "data" / "kb"
    live_root.mkdir(parents=True, exist_ok=True)
    live_meta = live_root / "papers.json"
    if not live_meta.exists():
        live_meta.write_text("[]", encoding="utf-8")
    finalizer = FinalizeBundleStore(root)
    if not (live_root / "index-generation.json").exists():
        finalizer.stage(
            "test-generation",
            candidate_collection="papers_rebuild_test",
            metadata=[],
            manifests={},
            collection_fingerprint="a" * 64,
        )
        finalizer.commit("test-generation")
    return create_paper_import_port(papers_dir=papers, meta_path=meta)


def _make_record(meta, name="paper.pdf"):
    record = new_record(name)
    record.status = STATUS_INDEXING
    upsert_paper(record, meta)
    FinalizeBundleStore(Path(meta).parent.parent.parent).refresh_live_digests()
    return record


def test_default_indexer_submits_v2_after_v1(tmp_path):
    """v1 同步建完后必须异步提交 v2，使 v2 状态不再恒 pending。"""
    papers = tmp_path / "data" / "kb" / "papers"
    papers.mkdir(parents=True)
    meta = tmp_path / "data" / "kb" / "papers.json"
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
    papers = tmp_path / "data" / "kb" / "papers"
    papers.mkdir(parents=True)
    meta = tmp_path / "data" / "kb" / "papers.json"
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
             patch.object(
                 kb_application.GenerationBoundIndexPort,
                 "index_document",
                 side_effect=RuntimeError("27B 模型不可用"),
             ):
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
    papers = tmp_path / "data" / "kb" / "papers"
    meta = tmp_path / "data" / "kb" / "papers.json"
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


# ---------------------------------------------------------------------------
# spec-021 Task03：KB 存储被另一个实例独占 → KB_STORAGE_LOCKED（窄匹配，固定文案）。
# ---------------------------------------------------------------------------


def test_storage_locked_runtime_error_maps_to_kb_storage_locked(tmp_path):
    """假 port 在导入时抛存储占用 RuntimeError → KB_STORAGE_LOCKED，且文案固定。"""
    class LockedPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, _request):
            raise RuntimeError(
                "Storage folder data/kb/qdrant is already accessed by another instance of Qdrant client"
            )

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=LockedPort(), temp_dir=tmp_path,
        )
    assert exc.value.code == KB_STORAGE_LOCKED
    assert exc.value.message == "知识库存储被另一个实例占用，请关闭其他服务实例后重试"
    # 异常原文（含路径）绝不得进入 error_code / message。
    assert "qdrant" not in str(exc.value)
    assert "data/kb" not in exc.value.message


def test_generic_runtime_error_still_maps_to_kb_import_failed(tmp_path):
    """窄匹配：非存储占用的 RuntimeError 仍回落 KB_IMPORT_FAILED（不得一刀切）。"""
    class BoomPort:
        def find_existing(self, _snapshot):
            return None

        def existing_names(self):
            return set()

        def import_paper(self, _request):
            raise RuntimeError("unrelated runtime failure")

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []), paper_import_port=BoomPort(), temp_dir=tmp_path,
        )
    assert exc.value.code == KB_IMPORT_FAILED


def test_storage_locked_via_injected_indexer_maps_to_kb_storage_locked(tmp_path):
    """假 indexer 在 KB 适配器内抛存储占用 RuntimeError → 适配器窄匹配后上抛 → KB_STORAGE_LOCKED。"""
    def locked_indexer(_record, _path):
        raise RuntimeError("data/kb/qdrant is already accessed by another instance of Qdrant client")

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []),
            paper_import_port=_port(tmp_path / "papers", tmp_path / "papers.json", indexer=locked_indexer),
            temp_dir=tmp_path,
        )
    assert exc.value.code == KB_STORAGE_LOCKED


def test_storage_locked_returned_in_index_result_maps_to_kb_storage_locked(tmp_path):
    """索引器**不抛异常**、只把存储占用原因放进结果映射时，也必须映射到 KB_STORAGE_LOCKED。

    真实链路（本机 Qdrant 被另一个实例占用）里，KB 适配器把索引失败收敛成一句裸的
    ``RuntimeError("index failed")``，索引器给的原因只留在结果里。此前上层再也认不出
    这是存储争用，被吞成不可行动的 KB_INDEX_FAILED，用户只看到「请稍后重建索引」。
    """
    def locked_result_indexer(_record, _path):
        return {
            "status": "failed",
            "error": "索引失败：Storage folder data/kb/qdrant is already accessed "
                     "by another instance of Qdrant client",
        }

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []),
            paper_import_port=_port(tmp_path / "papers", tmp_path / "papers.json",
                                    indexer=locked_result_indexer),
            temp_dir=tmp_path,
        )
    assert exc.value.code == KB_STORAGE_LOCKED
    assert exc.value.message == "知识库存储被另一个实例占用，请关闭其他服务实例后重试"
    # 含路径的索引器原文绝不得进入 error_code / message。
    assert "qdrant" not in str(exc.value)
    assert "data/kb" not in exc.value.message


def test_unrelated_index_result_failure_is_not_treated_as_storage_locked(tmp_path):
    """窄匹配仍成立：结果里的失败原因与存储争用无关时，不得误报 KB_STORAGE_LOCKED。"""
    def broken_indexer(_record, _path):
        return {"status": "failed", "error": "索引失败：embedding 超时"}

    with pytest.raises(PaperImportError) as exc:
        import_candidate(
            _candidate(), ArticleSettings(), {"papers.example"}, conference_short_name="CCS",
            downloader=_downloader(tmp_path, []),
            paper_import_port=_port(tmp_path / "papers", tmp_path / "papers.json",
                                    indexer=broken_indexer),
            temp_dir=tmp_path,
        )
    assert exc.value.code != KB_STORAGE_LOCKED
    assert "另一个实例" not in exc.value.message
