"""Spec029 candidate-confirmation bridge.

This module owns only the seam between Research selections and the existing
paper-import batch service.  It never downloads a file, parses a PDF, or
creates a knowledge-base document itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchServiceError,
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

    def __init__(self, store: Any, batch_service: Any) -> None:
        self.store = store
        self.batch_service = batch_service

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
        if not search_id and candidate_values:
            search_id = _value(candidate_values[0], "search_id")
        if not search_id:
            self.store.update_acquisition_approval(task_id, selection_version, status="failed")
            raise ResearchAcquisitionError("SEARCH_NOT_FOUND", "确认导入需要服务端搜索快照")
        try:
            batch = self.batch_service.create_batch(
                search_id,
                requested,
                idempotency_key=str(idempotency_key),
                candidates=candidate_values or None,
                auto_run=True,
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
        self.store.update_acquisition_approval(
            task_id, selection_version, status=str(_value(batch, "status", "queued")), batch_id=batch_id,
        )
        self._sync(task_id, batch_id, requested)
        return self.status(task_id)

    def _sync(self, task_id: str, batch_id: str, paper_ids: Iterable[str] | None = None) -> dict[str, Any]:
        result = self.batch_service.get_status(batch_id)
        batch = result.get("batch") if isinstance(result, Mapping) else None
        items = result.get("items", ()) if isinstance(result, Mapping) else ()
        if batch is None:
            raise ResearchAcquisitionError("BATCH_NOT_FOUND", "导入批次不存在")
        allowed = set(str(value) for value in (paper_ids or ()))
        for item in items:
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
        approval = self.store.get_acquisition_approval(task_id)
        if approval is not None and approval.batch_id == batch_id:
            self.store.update_acquisition_approval(task_id, approval.selection_version, status=str(_value(batch, "status", "queued")))
        return {
            "research_task_id": task_id,
            "batch_id": batch_id,
            "status": str(_value(batch, "status", _value(batch, "state", "queued"))),
            "selection_version": approval.selection_version if approval is not None else None,
            "approval_status": approval.status if approval is not None else None,
            "items": list(items),
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
        return self._sync(task_id, current.batch_id, current.paper_ids)


__all__ = ["ResearchAcquisitionError", "ResearchAcquisitionService"]
