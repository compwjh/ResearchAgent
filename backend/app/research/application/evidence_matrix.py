"""Claim/evidence matrix application boundary for Spec030 Task03.

The service validates a client/model proposal before it reaches the existing
ResearchStore.  It consumes only catalog selections and the Spec029
EvidenceUpgrade provenance; retrieval and document acquisition remain owned by
their existing services.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from backend.app.research.domain.models import (
    ClaimEvidence,
    ComparisonDimension,
    PaperComparisonCell,
    ResearchClaim,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEVELS = {"catalog", "abstract", "fulltext"}
_STANCES = {"supports", "contradicts", "contextual"}
_EVIDENCE_STATUS = {"available", "unavailable", "revalidation_required"}
_CLAIM_STATUS = {"supported", "contested", "unresolved"}
_CONFIDENCE = {"low", "medium", "high"}
_RELATIONS = _STANCES | {"missing"}


class EvidenceMatrixError(ValueError):
    _STATUS = {
        "TASK_NOT_FOUND": 404,
        "MATRIX_NOT_READY": 409,
        "EVIDENCE_INSUFFICIENT": 409,
        "REPORT_SCHEMA_INVALID": 400,
        "EVIDENCE_LOCATOR_INVALID": 400,
    }

    def __init__(self, code: str, message: str, *, status: int | None = None):
        self.code = code
        self.http_status = int(status or self._STATUS.get(code, 409))
        self.message = message
        super().__init__(message)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return converted
    return {}


def _text(value: Any, field: str, *, required: bool = True, max_chars: int = 4000) -> str:
    result = str(value or "").strip()
    if required and (not result or len(result) > max_chars):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 无效")
    return result


class EvidenceMatrixService:
    def __init__(self, store: Any):
        self.store = store

    def _task(self, task_id: str, owner_id: str):
        task = self.store.get_task(task_id, owner_id)
        if task is None:
            raise EvidenceMatrixError("TASK_NOT_FOUND", "研究任务不存在")
        return task

    @staticmethod
    def _claim(raw: Any, task_id: str, plan_version: int) -> ResearchClaim:
        item = _mapping(raw)
        claim = ResearchClaim(
            claim_id=_text(item.get("claim_id"), "claim_id", max_chars=200),
            task_id=task_id,
            topic=_text(item.get("topic"), "topic", max_chars=1000),
            statement=_text(item.get("statement"), "statement", max_chars=4000),
            confidence=str(item.get("confidence") or "").strip(),
            status=str(item.get("status") or "").strip(),
            plan_version=plan_version,
            evidence_ids=[str(value).strip() for value in item.get("evidence_ids", []) or []],
        )
        if claim.confidence not in _CONFIDENCE or claim.status not in _CLAIM_STATUS:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "claim confidence/status 无效")
        if len(set(claim.evidence_ids or [])) != len(claim.evidence_ids or []):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "claim evidence_ids 必须唯一")
        if not claim.evidence_ids and claim.status != "unresolved":
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "无证据 Claim 必须为 unresolved")
        return claim

    @staticmethod
    def _evidence(raw: Any, task_id: str, plan_version: int) -> ClaimEvidence:
        item = _mapping(raw)
        locator = item.get("locator")
        if not isinstance(locator, Mapping):
            raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "Evidence locator 无效")
        evidence = ClaimEvidence(
            evidence_id=_text(item.get("evidence_id"), "evidence_id", max_chars=200),
            claim_id=_text(item.get("claim_id"), "claim_id", max_chars=200),
            task_id=task_id,
            paper_id=_text(item.get("paper_id"), "paper_id", max_chars=200),
            evidence_level=str(item.get("evidence_level") or "").strip(),
            stance=str(item.get("stance") or "").strip(),
            status=str(item.get("status") or "").strip(),
            quote_digest=str(item.get("quote_digest") or "").strip().lower(),
            locator=dict(locator), plan_version=plan_version,
        )
        if evidence.evidence_level not in _LEVELS or evidence.stance not in _STANCES or evidence.status not in _EVIDENCE_STATUS:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "Evidence 枚举无效")
        if evidence.evidence_level == "catalog":
            if not str(locator.get("catalog_snapshot_id") or "").strip():
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "catalog Evidence 缺少 catalog_snapshot_id")
        elif evidence.evidence_level == "abstract":
            if not str(locator.get("abstract_ref") or locator.get("source_ref") or "").strip() or not _SHA256.fullmatch(str(locator.get("abstract_digest") or "").lower()):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "abstract Evidence 定位不完整")
        else:
            required = ("document_id", "chunk_ids", "page", "page_end", "source_sha256", "manifest_generation", "manifest_fingerprint", "chunker")
            if any(not locator.get(name) for name in required):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext Evidence 定位不完整")
            if not isinstance(locator["chunk_ids"], list) or not locator["chunk_ids"] or len(set(map(str, locator["chunk_ids"]))) != len(locator["chunk_ids"]):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext chunk_ids 无效")
            page, page_end = locator["page"], locator["page_end"]
            if isinstance(page, bool) or not isinstance(page, int) or page < 1 or isinstance(page_end, bool) or not isinstance(page_end, int) or page_end < page:
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext 页码无效")
            if not _SHA256.fullmatch(str(locator["source_sha256"]).lower()) or not _SHA256.fullmatch(str(locator["manifest_fingerprint"]).lower()):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext provenance hash 无效")
            if str(locator["chunker"]) not in {"v1", "v2"} or not _SHA256.fullmatch(evidence.quote_digest):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext quote_digest/chunker 无效")
        return evidence

    @staticmethod
    def _dimension(raw: Any, task_id: str, plan_version: int, default_order: int) -> ComparisonDimension:
        item = _mapping(raw)
        dimension_id = item.get("dimension_id", item.get("id"))
        order = item.get("display_order", item.get("order", default_order))
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "dimension order 无效")
        return ComparisonDimension(
            dimension_id=_text(dimension_id, "dimension_id", max_chars=200), task_id=task_id,
            label=_text(item.get("label"), "label", max_chars=500), definition=_text(item.get("definition"), "definition", max_chars=2000),
            display_order=order, plan_version=plan_version,
        )

    @staticmethod
    def _cell(raw: Any, task_id: str, plan_version: int) -> PaperComparisonCell:
        item = _mapping(raw)
        ids = [str(value).strip() for value in item.get("evidence_ids", []) or []]
        return PaperComparisonCell(
            claim_id=_text(item.get("claim_id"), "claim_id", max_chars=200), paper_id=_text(item.get("paper_id"), "paper_id", max_chars=200),
            dimension_id=_text(item.get("dimension_id"), "dimension_id", max_chars=200), relation=str(item.get("relation") or "").strip(),
            summary=_text(item.get("summary"), "summary", required=False, max_chars=4000), evidence_ids=ids,
            task_id=task_id, plan_version=plan_version, missing_reason=_text(item.get("missing_reason"), "missing_reason", required=False, max_chars=1000) or None,
        )

    def build_matrix(self, task_id: str, owner_id: str, *, plan_version: int | None = None,
                     dimensions: Sequence[Any] | None = None, claims: Sequence[Any] | None = None,
                     evidence: Sequence[Any] | None = None, cells: Sequence[Any] | None = None) -> dict:
        task = self._task(task_id, owner_id)
        version = int(plan_version or task.current_plan_version or 1)
        if version < 1 or version > int(task.current_plan_version or version):
            raise EvidenceMatrixError("MATRIX_NOT_READY", "研究计划版本尚未准备完成")
        raw_claims = list(claims) if claims is not None else list(self.store.list_claims(task_id, plan_version=version))
        raw_evidence = list(evidence) if evidence is not None else list(self.store.list_claim_evidence(task_id, plan_version=version))
        parsed_claims = [self._claim(item.to_dict() if isinstance(item, ResearchClaim) else item, task_id, version) for item in raw_claims]
        parsed_evidence = [self._evidence(item.to_dict() if isinstance(item, ClaimEvidence) else item, task_id, version) for item in raw_evidence]
        parsed_dimensions = [self._dimension(item, task_id, version, i) for i, item in enumerate(dimensions or [])]
        if not parsed_dimensions:
            parsed_dimensions = list(self.store.list_comparison_dimensions(task_id, plan_version=version))
        if not parsed_claims or not parsed_dimensions:
            raise EvidenceMatrixError("EVIDENCE_INSUFFICIENT", "Claim 或比较维度尚未准备完成")
        claims_by_id = {item.claim_id: item for item in parsed_claims}
        evidence_by_id = {item.evidence_id: item for item in parsed_evidence}
        if len(claims_by_id) != len(parsed_claims) or len(evidence_by_id) != len(parsed_evidence):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "Claim/Evidence ID 重复")
        selections = self.store.list_selections(task_id)
        paper_ids = [str(item.catalog_paper_id) for item in selections]
        if not paper_ids:
            paper_ids = sorted({item.paper_id for item in parsed_evidence})
        selected = set(paper_ids)
        for item in parsed_evidence:
            if item.task_id != task_id or item.plan_version != version or item.claim_id not in claims_by_id or item.paper_id not in selected:
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "Evidence 的任务、版本、Claim 或 Paper 不匹配")
            if item.evidence_level == "fulltext":
                upgrade = self.store.get_evidence_upgrade(item.claim_id)
                locator = item.locator or {}
                if upgrade is None or upgrade.status != "upgraded" or upgrade.document_id != locator.get("document_id"):
                    raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext Evidence 必须复用已验证的 EvidenceUpgrade")
                if upgrade.source_sha256 != locator.get("source_sha256") or upgrade.manifest_generation != locator.get("manifest_generation") or upgrade.manifest_fingerprint != locator.get("manifest_fingerprint") or upgrade.chunker != locator.get("chunker"):
                    raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext Evidence provenance 与 EvidenceUpgrade 不一致")
                if not set(map(str, locator.get("chunk_ids", []))).issubset(set(map(str, upgrade.chunk_ids))):
                    raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "fulltext Evidence chunk 不在 EvidenceUpgrade 中")
        for claim in parsed_claims:
            if claim.task_id != task_id or claim.plan_version != version:
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "Claim 的任务或版本不匹配")
            if any(evidence_by_id.get(eid) is None or evidence_by_id[eid].claim_id != claim.claim_id for eid in claim.evidence_ids or []):
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "Claim 引用了不存在或错误归属的 Evidence")
        dimension_ids = {item.dimension_id for item in parsed_dimensions}
        if len(dimension_ids) != len(parsed_dimensions):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "dimension_id 重复")
        requested_cells = [item if isinstance(item, PaperComparisonCell) else self._cell(item, task_id, version) for item in (cells or [])]
        cells_by_key: dict[tuple[str, str, str], PaperComparisonCell] = {}
        for cell in requested_cells:
            key = (cell.claim_id, cell.paper_id, cell.dimension_id)
            if key in cells_by_key or cell.relation not in _RELATIONS or cell.claim_id not in claims_by_id or cell.paper_id not in selected or cell.dimension_id not in dimension_ids:
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "比较单元格关系或归属无效")
            if cell.relation == "missing":
                if cell.evidence_ids or not cell.missing_reason:
                    raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "missing 单元格必须为空且说明原因")
            else:
                if not cell.evidence_ids or any(evidence_by_id.get(eid) is None or evidence_by_id[eid].claim_id != cell.claim_id or evidence_by_id[eid].paper_id != cell.paper_id or evidence_by_id[eid].status != "available" or evidence_by_id[eid].stance != cell.relation for eid in cell.evidence_ids):
                    raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "单元格 Evidence 不匹配")
            cells_by_key[key] = cell
        # Missing/derived cells are explicit coverage gaps; no textual fact is guessed.
        output_cells: list[PaperComparisonCell] = []
        limitations: list[str] = []
        for claim in parsed_claims:
            for paper_id in paper_ids:
                for dimension in parsed_dimensions:
                    key = (claim.claim_id, paper_id, dimension.dimension_id)
                    if key in cells_by_key:
                        cell = cells_by_key[key]
                    else:
                        valid = [item for item in parsed_evidence if item.claim_id == claim.claim_id and item.paper_id == paper_id and item.status == "available"]
                        relation = next((stance for stance in ("contradicts", "supports", "contextual") if any(item.stance == stance for item in valid)), "missing")
                        ids = [item.evidence_id for item in valid if item.stance == relation] if relation != "missing" else []
                        cell = PaperComparisonCell(claim.claim_id, paper_id, dimension.dimension_id, relation, "", ids, task_id, version, None if relation != "missing" else "No available evidence locator.")
                    output_cells.append(cell)
                    if cell.relation == "missing":
                        limitations.append(f"{claim.claim_id}/{paper_id}/{dimension.dimension_id}: {cell.missing_reason}")
        # All validation has completed before any matrix rows are replaced.
        for item in parsed_claims:
            self.store.save_claim(item)
        for item in parsed_evidence:
            self.store.save_claim_evidence(item)
        self.store.replace_comparison_dimensions(task_id, version, parsed_dimensions)
        self.store.replace_comparison_cells(task_id, version, output_cells)
        return self._projection(task_id, version, parsed_claims, parsed_evidence, parsed_dimensions, output_cells, limitations)

    def read_matrix(self, task_id: str, owner_id: str, *, plan_version: int | None = None) -> dict:
        task = self._task(task_id, owner_id)
        version = int(plan_version or task.current_plan_version or 1)
        claims = self.store.list_claims(task_id, plan_version=version)
        evidence = self.store.list_claim_evidence(task_id, plan_version=version)
        dimensions = self.store.list_comparison_dimensions(task_id, plan_version=version)
        cells = self.store.list_comparison_cells(task_id, plan_version=version)
        if not claims or not dimensions:
            raise EvidenceMatrixError("MATRIX_NOT_READY", "证据矩阵尚未准备完成")
        limitations = [f"{c.claim_id}/{c.paper_id}/{c.dimension_id}: {c.missing_reason}" for c in cells if c.relation == "missing" and c.missing_reason]
        unavailable = {item.evidence_id for item in evidence if item.status != "available"}
        stale_fulltext = {
            item.evidence_id
            for item in evidence
            if item.status == "available" and item.evidence_level == "fulltext" and not self._fulltext_upgrade_matches(item)
        }
        if stale_fulltext:
            limitations.append("当前存在未经当前 EvidenceUpgrade 证明的全文 Evidence，相关单元格已降级。")
            evidence = [
                type(item)(**{**item.__dict__, "status": "revalidation_required"})
                if item.evidence_id in stale_fulltext else item
                for item in evidence
            ]
            unavailable.update(stale_fulltext)
        if unavailable:
            limitations.append("当前存在不可用或需复核的 Evidence，相关单元格已降级。")
            cells = [PaperComparisonCell(**{**item.__dict__, "relation": "missing", "evidence_ids": [], "missing_reason": "Evidence is unavailable or requires revalidation."}) if set(item.evidence_ids or []) & unavailable else item for item in cells]
        return self._projection(task_id, version, claims, evidence, dimensions, cells, limitations)

    def _fulltext_upgrade_matches(self, evidence: ClaimEvidence) -> bool:
        """Keep report projections fail-closed after an upgrade is revalidated."""
        upgrade = self.store.get_evidence_upgrade(evidence.claim_id)
        locator = evidence.locator or {}
        if upgrade is None or upgrade.status != "upgraded" or upgrade.document_id != locator.get("document_id"):
            return False
        if (
            upgrade.source_sha256 != locator.get("source_sha256")
            or upgrade.manifest_generation != locator.get("manifest_generation")
            or upgrade.manifest_fingerprint != locator.get("manifest_fingerprint")
            or upgrade.chunker != locator.get("chunker")
        ):
            return False
        return set(map(str, locator.get("chunk_ids", []))).issubset(set(map(str, upgrade.chunk_ids)))

    @staticmethod
    def _projection(task_id, version, claims, evidence, dimensions, cells, limitations):
        return {
            "schema_version": "evidence-report-v1", "research_task_id": task_id, "task_id": task_id,
            "plan_version": int(version), "claims": [item.to_dict() for item in claims],
            "evidence": [item.to_dict() for item in evidence], "dimensions": [item.to_dict() for item in dimensions],
            "cells": [item.to_dict() for item in cells], "limitations": list(dict.fromkeys(limitations)),
        }


__all__ = ["EvidenceMatrixError", "EvidenceMatrixService"]
