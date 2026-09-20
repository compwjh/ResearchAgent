"""回归测试：catalog async-search 批量导入回退（search_sessions 恒空）。

现象：catalog async-search 只把检索上下文写进 search_jobs / search_results，
从不写 search_sessions。批量导入执行路径（run_batch → _snapshots_for →
_server_snapshot）此前在 get_search_session 返回 None 时直接抛 SEARCH_NOT_FOUND，
导致批量导入 100% 失败。

本文件构造「search_jobs 有数据、search_sessions 为空」的场景，断言批量导入能
正确回退到 job 解析并解析候选，而不是误报 SEARCH_NOT_FOUND。同时锁定回退分支的
错误语义（job 不存在 → SEARCH_NOT_FOUND；job 未就绪 → SEARCH_NOT_READY）。
"""

import pytest

from backend.app.paper_discovery.application.paper_import import PaperImportResult
from backend.app.paper_discovery.application.paper_import_batch_service import (
    SEARCH_NOT_FOUND,
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.paper_discovery.domain.paper_import_batch import ITEM_COMPLETED
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import (
    PaperImportBatchStore,
)


def _raw_snapshot(catalog_paper_id: str, title: str) -> dict:
    """search_results 表中存储的 snapshot_json（含 catalog_paper_id，无 candidate_id）。"""
    return {
        "catalog_paper_id": catalog_paper_id,
        "title": title,
        "pdf_url": f"https://papers.example/{catalog_paper_id}.pdf",
        "article_url": f"https://papers.example/{catalog_paper_id}",
        "dblp_key": f"conf/ccs/{catalog_paper_id}",
        "year": 2025,
        "conference_id": "ccs",
    }


class _CatalogDiscoveryStore:
    """模拟 catalog async-search 的检索存储：sessions 恒空，jobs/results 有数据。

    job_status / expires_at / job_exists 可由测试覆盖以触发不同回退语义。
    """

    def __init__(self, search_id, raw_snapshots, job_status="completed", expires_at="2099-01-01T00:00:00Z"):
        self.search_id = search_id
        self.raw_snapshots = raw_snapshots
        self.job_status = job_status
        self.expires_at = expires_at
        self.job_exists = True

    def get_search_session(self, search_id):
        # catalog async-search：session 永远不写这张表。
        return None

    def get_search_job(self, search_id):
        if not self.job_exists or search_id != self.search_id:
            return None

        class _Job:
            search_id = self.search_id
            status = self.job_status
            expires_at = self.expires_at

        return _Job()

    def get_search_results(self, search_id):
        if search_id != self.search_id:
            return []

        class _Result:
            pass

        out = []
        for raw in self.raw_snapshots:
            result = _Result()
            result.search_id = search_id
            result.catalog_paper_id = raw["catalog_paper_id"]
            result.snapshot = dict(raw)
            out.append(result)
        return out


class _JobSession:
    """路由层在 create_batch 时传入的 job（作为 search_session），其 expires_at 落地。"""

    def __init__(self, search_id, expires_at="2099-01-01T00:00:00Z"):
        self.search_id = search_id
        self.expires_at = expires_at


def _service(tmp_path, discovery_store, importer):
    return PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        discovery_store=discovery_store,
        importer=importer,
        max_workers=3,
    )


def _candidates(raw_snapshots, search_id):
    """模拟路由层 _paper_server_snapshot 回退后返回的候选（已 setdefault candidate_id/search_id）。"""
    return [
        {**raw, "candidate_id": raw["catalog_paper_id"], "search_id": search_id}
        for raw in raw_snapshots
    ]


def test_batch_import_falls_back_to_catalog_search_results(tmp_path):
    """search_jobs 有数据、search_sessions 为空时，批量导入应回退解析而非抛 SEARCH_NOT_FOUND。"""
    search_id = "c7fc1a77e12c4bfba340a1eb237dccbf"
    raw = [_raw_snapshot("cp-1", "Paper One"), _raw_snapshot("cp-2", "Paper Two")]
    store = _CatalogDiscoveryStore(search_id, raw)

    imported = []

    def importer(candidate, *_args):
        imported.append(candidate["candidate_id"])
        return PaperImportResult(f"paper-{candidate['candidate_id']}", None, "indexed")

    service = _service(tmp_path, store, importer)
    candidates = _candidates(raw, search_id)
    # create_batch 传入 job 作为 search_session（与真实路由层一致），run_batch 不传。
    batch = service.create_batch(
        search_id,
        [c["candidate_id"] for c in candidates],
        search_session=_JobSession(search_id),
        candidates=candidates,
    )

    # 关键：run_batch 不传 search_session（与真实后台路径一致），必须由 _server_snapshot 回退解析。
    result = service.run_batch(batch.batch_id, candidates=candidates)

    assert result.status == "completed"
    items = {it.candidate_id: it for it in service.store.get_items(batch.batch_id)}
    assert items["cp-1"].status == ITEM_COMPLETED
    assert items["cp-2"].status == ITEM_COMPLETED
    assert set(imported) == {"cp-1", "cp-2"}


def _clear_item_snapshots(store, batch_id):
    """清空批次 item 的持久化快照，强制 _snapshots_for 走会话重建路径。"""
    import sqlite3

    connection = sqlite3.connect(store.database_path)
    try:
        with connection:
            connection.execute(
                "UPDATE paper_import_items SET snapshot_json=NULL, snapshot_hash=NULL WHERE batch_id=?",
                (batch_id,),
            )
    finally:
        connection.close()


def test_batch_import_fallback_raises_search_not_found_when_job_missing(tmp_path):
    """回退分支下若 search_jobs 也无该 search_id，仍应抛 SEARCH_NOT_FOUND（不静默吞掉）。"""
    search_id = "missing-job-id"
    raw = [_raw_snapshot("cp-1", "Paper One")]
    store = _CatalogDiscoveryStore(search_id, raw)
    store.job_exists = False

    def importer(candidate, *_args):
        return PaperImportResult("paper-x", None, "indexed")

    service = _service(tmp_path, store, importer)
    candidates = _candidates(raw, search_id)
    batch = service.create_batch(
        search_id,
        [c["candidate_id"] for c in candidates],
        search_session=_JobSession(search_id),
        candidates=candidates,
    )
    # Force the rebuild path by removing durable snapshots; otherwise the batch
    # is self-consistent and skips the session gate (spec-035 Bug1).
    _clear_item_snapshots(service.store, batch.batch_id)

    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.run_batch(batch.batch_id, candidates=candidates)
    assert exc.value.code == SEARCH_NOT_FOUND


def test_batch_import_fallback_raises_search_not_ready_when_job_incomplete(tmp_path):
    """回退分支下若 job.status 不在 {completed,partial,failed}，应抛 SEARCH_NOT_READY。"""
    search_id = "pending-job-id"
    raw = [_raw_snapshot("cp-1", "Paper One")]
    store = _CatalogDiscoveryStore(search_id, raw, job_status="pending")

    def importer(candidate, *_args):
        return PaperImportResult("paper-x", None, "indexed")

    service = _service(tmp_path, store, importer)
    candidates = _candidates(raw, search_id)
    batch = service.create_batch(
        search_id,
        [c["candidate_id"] for c in candidates],
        search_session=_JobSession(search_id),
        candidates=candidates,
    )
    # spec-035：快照完整时批次自洽，job 未就绪也应成功（不再受会话门禁约束）。
    result = service.run_batch(batch.batch_id, candidates=candidates)
    assert result.status == "completed"

    # 仅当快照缺失需要重建时，job 未就绪才报 SEARCH_NOT_READY（保留原门禁语义）。
    batch2 = service.create_batch(
        search_id,
        [c["candidate_id"] for c in candidates],
        search_session=_JobSession(search_id),
        candidates=candidates,
    )
    _clear_item_snapshots(service.store, batch2.batch_id)

    with pytest.raises(PaperImportBatchServiceError) as exc:
        service.run_batch(batch2.batch_id, candidates=candidates)
    # 错误码字符串照抄路由层 _PAPER_BATCH_ERROR_STATUS（"SEARCH_NOT_READY"）。
    assert exc.value.code == "SEARCH_NOT_READY"
