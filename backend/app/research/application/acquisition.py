"""Spec029 candidate-confirmation bridge.

This module owns only the seam between Research selections and the existing
paper-import batch service.  It never downloads a file, parses a PDF, or
creates a knowledge-base document itself.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Any

from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchServiceError,
    SEARCH_EXPIRED,
    SEARCH_NOT_FOUND,
)
from backend.app.research.domain.models import (
    AcquisitionApproval,
    AcquisitionEvent,
    ResearchDocumentLink,
)


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class ResearchAcquisitionError(ValueError):
    """Stable error at the Research↔paper-import boundary."""

    _STATUS = {
        "TASK_NOT_FOUND": 404,
        "SELECTION_NOT_READY": 409,
        "SELECTION_VERSION_STALE": 409,
        "ACQUISITION_CONFLICT": 409,
        "SEARCH_NOT_FOUND": 400,
        "PAPER_IMPORT_FAILED": 424,
        "BATCH_NOT_FOUND": 404,
    }

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        self.code = code
        self.http_status = int(status or self._STATUS.get(code, 400))
        self.message = message
        super().__init__(message)


class ResearchAcquisitionService:
    """Confirm a frozen Research selection and project existing batch state."""

    def __init__(
        self,
        store: Any,
        batch_service: Any,
        search_refresher: Any = None,
    ) -> None:
        self.store = store
        self.batch_service = batch_service
        # 可选：按原 query 重跑检索、为过期/缺失的快照生成新句柄。由路由层注入，
        # 便于测试隔离；未注入时保持「过期即失败」的历史行为。
        self.search_refresher = search_refresher if callable(search_refresher) else None

    def _create_batch(
        self,
        task_id: str,
        search_id: str,
        paper_ids: list[str],
        idempotency_key: str,
        candidate_values: list[Any],
    ) -> tuple[Any, str]:
        """建一次导入批次；快照过期/缺失时按需刷新句柄后重试一次。

        搜索快照带 TTL（默认 7 天），研究任务从检索到用户确认常常跨天，隔天点
        「确认并开始导入」会撞上 ``SEARCH_EXPIRED``。此时按原 query 重跑一次检索
        即可拿到新句柄：``candidate_id`` 是内容派生的，同一批论文会以同样的 ID
        出现在新快照里，因此刷新不会改变用户看到的选集。
        """
        try:
            return (
                self.batch_service.create_batch(
                    search_id,
                    paper_ids,
                    idempotency_key=idempotency_key,
                    candidates=candidate_values or None,
                    auto_run=True,
                ),
                search_id,
            )
        except PaperImportBatchServiceError as error:
            if getattr(error, "code", None) not in {SEARCH_EXPIRED, SEARCH_NOT_FOUND}:
                raise
            if self.search_refresher is None:
                raise
            refreshed = self.search_refresher(search_id, paper_ids)
            if not refreshed or refreshed == search_id:
                raise
            # 把新句柄写回选集行，后续确认/重试直接用它，不必再刷新一次。
            for paper_id in paper_ids:
                with suppress(Exception):
                    self.store.update_selection_source(task_id, paper_id, refreshed)
            return (
                self.batch_service.create_batch(
                    refreshed,
                    paper_ids,
                    idempotency_key=idempotency_key,
                    candidates=candidate_values or None,
                    auto_run=True,
                ),
                refreshed,
            )

    def _task_search_id(self, task_id: str) -> str | None:
        """Read the durable server-owned handle for a Research task."""
        getter = getattr(self.store, "get_task_search_id", None)
        if callable(getter):
            value = getter(task_id)
            value = str(value or "").strip()
            return value or None
        # Keep small in-memory store doubles useful while requiring a task
        # object (rather than trusting a candidate/client payload) as fallback.
        task_getter = getattr(self.store, "get_task", None)
        if callable(task_getter):
            try:
                task = task_getter(task_id)
            except TypeError:
                task = None
            value = _value(task, "search_id")
            value = str(value or "").strip()
            return value or None
        return None

    def _selection(self, task_id: str, selection_version: int, paper_ids: Iterable[str]) -> list[str]:
        current_version = int(self.store.get_selection_version(task_id))
        if current_version < 1:
            raise ResearchAcquisitionError("SELECTION_NOT_READY", "研究任务尚无可确认的论文选集")
        if int(selection_version) != current_version:
            raise ResearchAcquisitionError("SELECTION_VERSION_STALE", "论文选集已变化，请刷新后重新确认")
        selected = {str(item.catalog_paper_id) for item in self.store.list_selections(task_id)}
        requested: list[str] = []
        seen: set[str] = set()
        for value in paper_ids:
            paper_id = str(value).strip()
            if paper_id and paper_id not in seen:
                requested.append(paper_id)
                seen.add(paper_id)
        if not requested or any(value not in selected for value in requested):
            raise ResearchAcquisitionError("ACQUISITION_CONFLICT", "确认清单必须来自当前论文选集")
        return requested

    def _selection_sources(self, task_id: str) -> dict[str, str]:
        """候选 ID -> 产出它的那次检索的 search_id。

        一个研究任务可扇出多个 search worker，各自持有不同的 server 快照句柄，而
        ``research_tasks.search_id`` 只保留第一个。若导入桥一律拿任务级句柄去解析
        候选，凡是「选集来自后出发的 worker」就必然 ``CANDIDATE_NOT_FOUND``。
        因此按选集行记录的来源快照分组建批次；旧数据（无来源）回落任务级句柄。
        """
        fallback = self._task_search_id(task_id)
        sources: dict[str, str] = {}
        for item in self.store.list_selections(task_id):
            paper_id = str(_value(item, "catalog_paper_id", "") or "").strip()
            if not paper_id:
                continue
            source = _value(item, "source_search_id")
            source = str(source).strip() if source else ""
            if not source:
                source = fallback or ""
            if source:
                sources[paper_id] = source
        return sources

    def confirm(
        self,
        task_id: str,
        *,
        selection_version: int,
        paper_ids: Iterable[str],
        idempotency_key: str,
        search_id: str | None = None,
        candidates: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        requested = self._selection(task_id, selection_version, paper_ids)
        if not idempotency_key or not str(idempotency_key).strip():
            raise ResearchAcquisitionError("ACQUISITION_CONFLICT", "idempotency_key 不能为空")
        durable_search_id = self._task_search_id(task_id)
        if not durable_search_id:
            raise ResearchAcquisitionError("SEARCH_NOT_FOUND", "研究任务尚未绑定服务端搜索快照")
        # Group the confirmed list by the search snapshot each candidate came
        # from.  The client envelope stays a compatibility echo: only server
        # handles recorded on the selection rows (or the task's durable handle)
        # are ever used to build batches.
        sources = self._selection_sources(task_id)
        grouped: dict[str, list[str]] = {}
        for paper_id in requested:
            group_search_id = sources.get(paper_id) or durable_search_id
            grouped.setdefault(group_search_id, []).append(paper_id)
        if search_id is not None:
            client_search_id = str(search_id).strip()
            if client_search_id and client_search_id != durable_search_id and client_search_id not in grouped:
                raise ResearchAcquisitionError("ACQUISITION_CONFLICT", "搜索快照与研究任务不匹配")
        existing = self.store.get_acquisition_approval(task_id, selection_version)
        if existing is not None:
            if existing.paper_ids != requested:
                raise ResearchAcquisitionError("ACQUISITION_CONFLICT", "该选集版本已用另一份清单确认")
            if existing.batch_id:
                return self.status(task_id, approval=existing)
            approval = existing
        else:
            try:
                approval = self.store.create_acquisition_approval(
                    AcquisitionApproval(
                        task_id=task_id,
                        selection_version=int(selection_version),
                        paper_ids=requested,
                        status="confirmed",
                        idempotency_key=str(idempotency_key),
                    )
                )
            except ValueError as error:
                raise ResearchAcquisitionError("ACQUISITION_CONFLICT", str(error)) from error
            if approval.batch_id:
                return self.status(task_id, approval=approval)

        candidate_values = list(candidates or ())
        batches: list[Any] = []
        batch_ids: list[str] = []
        for index, (group_search_id, group_paper_ids) in enumerate(sorted(grouped.items())):
            try:
                batch, _ = self._create_batch(
                    task_id,
                    group_search_id,
                    group_paper_ids,
                    idempotency_key=f"{idempotency_key}#{index}",
                    candidate_values=candidate_values,
                )
            except PaperImportBatchServiceError as error:
                self.store.update_acquisition_approval(task_id, selection_version, status="failed")
                raise ResearchAcquisitionError("PAPER_IMPORT_FAILED", error.message, status=424) from error
            except Exception as error:
                self.store.update_acquisition_approval(task_id, selection_version, status="failed")
                raise ResearchAcquisitionError("PAPER_IMPORT_FAILED", "论文导入批次创建失败", status=424) from error
            batch_id = str(_value(batch, "batch_id", ""))
            if not batch_id:
                raise ResearchAcquisitionError("PAPER_IMPORT_FAILED", "论文导入批次未返回 batch_id", status=424)
            batches.append(batch)
            batch_ids.append(batch_id)
        status = self._aggregate_status(batches)
        self.store.update_acquisition_approval(
            task_id,
            selection_version,
            status=status,
            batch_id=batch_ids[0],
            batch_ids_json=json.dumps(batch_ids, ensure_ascii=False),
        )
        self._sync(task_id, batch_ids, requested)
        return self.status(task_id)

    @staticmethod
    def _aggregate_status(batches: Iterable[Any]) -> str:
        """Collapse per-batch statuses into one approval status."""
        values = [
            str(_value(batch, "status", _value(batch, "state", "queued")) or "queued")
            for batch in batches
        ]
        if not values:
            return "queued"
        if all(value in {"completed", "existing"} for value in values):
            return "completed"
        if any(value == "failed" for value in values):
            return "failed"
        if any(value in {"running", "partial"} for value in values):
            return "running"
        return values[0]

    def _sync(self, task_id: str, batch_ids: Iterable[str] | str, paper_ids: Iterable[str] | None = None) -> dict[str, Any]:
        """Project one or more import batches onto Research document links.

        A selection can span several search snapshots, so confirmation may have
        created one batch per snapshot.  Items from every batch are merged; the
        returned ``batch_id`` is the primary (first) batch for compatibility.
        """
        ids: list[str] = [str(value) for value in ([batch_ids] if isinstance(batch_ids, str) else batch_ids) if value]
        if not ids:
            raise ResearchAcquisitionError("BATCH_NOT_FOUND", "导入批次不存在")
        allowed = set(str(value) for value in (paper_ids or ()))
        batches: list[Any] = []
        items: list[Any] = []
        for batch_id in ids:
            result = self.batch_service.get_status(batch_id)
            batch = result.get("batch") if isinstance(result, Mapping) else None
            batch_items = result.get("items", ()) if isinstance(result, Mapping) else ()
            if batch is None:
                continue
            batches.append(batch)
            for item in batch_items:
                catalog_id = str(_value(item, "candidate_id", ""))
                if not catalog_id or (allowed and catalog_id not in allowed):
                    continue
                status = str(_value(item, "status", _value(item, "state", "queued")))
                error_code = _value(item, "error_code")
                self.store.upsert_document_link(
                    ResearchDocumentLink(
                        task_id=task_id,
                        catalog_paper_id=catalog_id,
                        document_id=_value(item, "paper_id"),
                        import_item_id=_value(item, "item_id"),
                        status=status,
                        error_code=error_code,
                    )
                )
                self.store.append_acquisition_event(
                    AcquisitionEvent(
                        task_id=task_id,
                        paper_id=catalog_id,
                        phase="import",
                        status=status,
                        error_code=error_code,
                        batch_id=batch_id,
                        import_item_id=_value(item, "item_id"),
                    )
                )
                items.append(item)
        if not batches:
            raise ResearchAcquisitionError("BATCH_NOT_FOUND", "导入批次不存在")
        approval = self.store.get_acquisition_approval(task_id)
        if approval is not None and set(approval.batch_ids()) & set(ids):
            self.store.update_acquisition_approval(
                task_id, approval.selection_version, status=self._aggregate_status(batches)
            )
        return {
            "research_task_id": task_id,
            "batch_id": ids[0],
            "batch_ids": ids,
            "status": self._aggregate_status(batches),
            "selection_version": approval.selection_version if approval is not None else None,
            "approval_status": approval.status if approval is not None else None,
            "items": items,
            "links": [item.to_dict() for item in self.store.list_document_links(task_id)],
            "events": [item.to_dict() for item in self.store.list_acquisition_events(task_id)],
        }

    def status(self, task_id: str, *, approval: AcquisitionApproval | None = None) -> dict[str, Any]:
        current = approval or self.store.get_acquisition_approval(task_id)
        if current is None:
            raise ResearchAcquisitionError("BATCH_NOT_FOUND", "研究任务尚未确认全文获取")
        if not current.batch_id:
            return {
                "research_task_id": task_id,
                "batch_id": None,
                "status": current.status,
                "selection_version": current.selection_version,
                "approval_status": current.status,
                "items": [],
                "links": [item.to_dict() for item in self.store.list_document_links(task_id)],
                "events": [item.to_dict() for item in self.store.list_acquisition_events(task_id)],
            }
        return self._sync(task_id, current.batch_ids(), current.paper_ids)


__all__ = ["ResearchAcquisitionError", "ResearchAcquisitionService"]
