"""搜索快照过期/缺失时，确认导入应先刷新句柄再重试。

搜索快照带 TTL，研究任务从检索到用户确认常常跨天，隔天点「确认并开始导入」会撞上
SEARCH_EXPIRED。刷新是「把原有候选原样重新冻结成新会话」，不重跑检索，因此用户看到
的选集逐条不变。
"""

from pathlib import Path

import pytest

from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchServiceError,
)
from backend.app.paper_discovery.domain.paper_import_batch import PaperImportBatch, PaperImportItem
from backend.app.research.application.acquisition import (
    ResearchAcquisitionError,
    ResearchAcquisitionService,
)
from backend.app.research.domain.models import ResearchPaperSelection, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore


def _task(store: ResearchStore, task_id: str = "task-refresh") -> None:
    store.create_task(ResearchTask(
        research_task_id=task_id, owner_id="owner", conversation_id="conversation",
        goal="goal", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=60, status="planning", current_plan_version=1,
        created_at="", updated_at="",
    ))


def _selections(store: ResearchStore, task_id: str = "task-refresh") -> None:
    store.replace_selections(task_id, [
        ResearchPaperSelection(task_id, "paper-a", 1.0, "[]", "catalog", "", source_search_id="search-old"),
        ResearchPaperSelection(task_id, "paper-b", 0.9, "[]", "catalog", "", source_search_id="search-old"),
    ])


class _ExpiringThenOkBatch:
    """第一次建批次抛「快照已过期」，之后成功；记录收到的 search_id。"""

    def __init__(self, fail_codes=("SEARCH_EXPIRED",)):
        self.calls: list[str] = []
        self._fail_codes = list(fail_codes)
        self._failures = 0

    def create_batch(self, search_id, candidate_ids=(), **_kwargs):
        self.calls.append(search_id)
        if self._failures < len(self._fail_codes):
            code = self._fail_codes[self._failures]
            self._failures += 1
            raise PaperImportBatchServiceError(code, "搜索会话已过期" if code == "SEARCH_EXPIRED" else "搜索会话不存在")
        return PaperImportBatch("batch-1", search_id, status="queued")

    def get_status(self, batch_id):
        return {
            "batch": PaperImportBatch("batch-1", self.calls[-1], status="queued").to_dict(),
            "items": [
                PaperImportItem("item-a", "batch-1", "paper-a", status="queued").to_dict(),
                PaperImportItem("item-b", "batch-1", "paper-b", status="queued").to_dict(),
            ],
        }


def test_expired_snapshot_is_refreshed_then_batch_created(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-refresh", "search-fallback")
    _selections(store)
    batch = _ExpiringThenOkBatch()
    service = ResearchAcquisitionService(store, batch, lambda _sid, _ids: "search-fresh")

    result = service.confirm(
        "task-refresh", selection_version=1, paper_ids=["paper-a", "paper-b"],
        idempotency_key="request-1",
    )

    # 先用来源快照，失败后换成刷新得到的句柄重试。
    assert batch.calls == ["search-old", "search-fresh"]
    assert result["status"] in {"queued", "running"}
    assert result["approval_status"] in {"queued", "running"}


def test_refreshed_search_id_is_written_back_to_selections(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-refresh", "search-fallback")
    _selections(store)
    service = ResearchAcquisitionService(store, _ExpiringThenOkBatch(), lambda _sid, _ids: "search-fresh")

    service.confirm(
        "task-refresh", selection_version=1, paper_ids=["paper-a", "paper-b"],
        idempotency_key="request-1",
    )

    sources = {item.catalog_paper_id: item.source_search_id for item in store.list_selections("task-refresh")}
    assert sources == {"paper-a": "search-fresh", "paper-b": "search-fresh"}


def test_without_refresher_expired_snapshot_still_fails(tmp_path: Path):
    """未注入刷新器时保持历史行为：过期即失败，不静默吞掉。"""
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-refresh", "search-old")
    _selections(store)
    service = ResearchAcquisitionService(store, _ExpiringThenOkBatch())

    with pytest.raises(ResearchAcquisitionError) as excinfo:
        service.confirm(
            "task-refresh", selection_version=1, paper_ids=["paper-a", "paper-b"],
            idempotency_key="request-1",
        )

    assert excinfo.value.code == "PAPER_IMPORT_FAILED"
    assert "过期" in excinfo.value.message


def test_refresher_returning_none_keeps_original_error(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-refresh", "search-old")
    _selections(store)
    service = ResearchAcquisitionService(store, _ExpiringThenOkBatch(), lambda _sid, _ids: None)

    with pytest.raises(ResearchAcquisitionError) as excinfo:
        service.confirm(
            "task-refresh", selection_version=1, paper_ids=["paper-a", "paper-b"],
            idempotency_key="request-1",
        )

    assert excinfo.value.code == "PAPER_IMPORT_FAILED"


def test_non_expiry_errors_are_not_retried(tmp_path: Path):
    """只有过期/缺失才刷新；其它错误（如候选不存在）不应重试。"""
    store = ResearchStore(tmp_path / "research.sqlite3")
    _task(store)
    store.set_task_search_id("task-refresh", "search-old")
    _selections(store)
    batch = _ExpiringThenOkBatch(fail_codes=("CANDIDATE_NOT_FOUND",))
    refreshed = []
    service = ResearchAcquisitionService(
        store, batch, lambda _sid, _ids: refreshed.append(_sid) or "search-fresh"
    )

    with pytest.raises(ResearchAcquisitionError):
        service.confirm(
            "task-refresh", selection_version=1, paper_ids=["paper-a", "paper-b"],
            idempotency_key="request-1",
        )

    assert batch.calls == ["search-old"]
    assert refreshed == []
