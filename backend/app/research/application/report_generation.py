"""Spec030 evidence-report generation and read-only export boundary.

This module consumes the canonical projection produced by
``EvidenceMatrixService``.  It does not retrieve papers or inspect documents;
all facts and locators must already be present in that projection.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.evidence_upgrade import EvidenceUpgradeService
from backend.app.research.application.report_synthesis import (
    ReportSynthesisError,
    ReportSynthesizer,
    _safe_text_input,
    render_markdown_html,
)
from backend.app.research.domain.models import ResearchReport


class EvidenceReportError(ReportSynthesisError):
    """Stable errors for the Spec030 report API."""

    _STATUS = {
        "TASK_NOT_FOUND": 404,
        "REPORT_NOT_READY": 409,
        "REPORT_SCHEMA_INVALID": 400,
        "CITATION_MANIFEST_INVALID": 400,
        "FORMAT_SEMANTIC_MISMATCH": 500,
        "REPORT_VERSION_CONFLICT": 409,
    }

    def __init__(self, message: str = "", *, code: str = "REPORT_SCHEMA_INVALID") -> None:
        super().__init__(message or code, code=code)
        self.http_status = self._STATUS.get(code, 409)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 240:
        raise EvidenceReportError(f"invalid {field}")
    return value.strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_citations(report_id: str, claims: list[dict], evidence: list[dict]) -> dict:
    evidence_by_id = {_clean_id(item.get("evidence_id"), "evidence_id"): item for item in evidence}
    if len(evidence_by_id) != len(evidence):
        raise EvidenceReportError("duplicate evidence_id", code="CITATION_MANIFEST_INVALID")
    claim_by_id = {_clean_id(item.get("claim_id"), "claim_id"): item for item in claims}
    if len(claim_by_id) != len(claims):
        raise EvidenceReportError("duplicate claim_id")
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for claim_id in sorted(claim_by_id):
        claim = claim_by_id[claim_id]
        ids = claim.get("evidence_ids") or []
        if not isinstance(ids, list):
            raise EvidenceReportError("claim evidence_ids must be a list")
        for evidence_id in ids:
            evidence_id = _clean_id(evidence_id, "evidence_id")
            item = evidence_by_id.get(evidence_id)
            if item is None or item.get("claim_id") != claim_id:
                raise EvidenceReportError("claim references missing evidence", code="CITATION_MANIFEST_INVALID")
            if item.get("status") != "available":
                continue
            paper_id = _clean_id(item.get("paper_id"), "paper_id")
            key = (claim_id, evidence_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "citation_no": len(citations) + 1,
                "paper_id": paper_id,
                "evidence_ids": [evidence_id],
                "claim_ids": [claim_id],
            })
    return {"manifest_version": 1, "report_id": report_id, "citations": citations}


def _validate_matrix(matrix: Mapping[str, Any]) -> tuple[list[dict], list[dict], list[dict], list[dict], list[str]]:
    if matrix.get("schema_version") != "evidence-report-v1":
        raise EvidenceReportError("matrix schema version is unsupported")
    claims = matrix.get("claims")
    evidence = matrix.get("evidence")
    dimensions = matrix.get("dimensions")
    cells = matrix.get("cells")
    if not all(isinstance(value, list) for value in (claims, evidence, dimensions, cells)):
        raise EvidenceReportError("matrix projection is incomplete")
    claims = [dict(item) for item in claims if isinstance(item, Mapping)]
    evidence = [dict(item) for item in evidence if isinstance(item, Mapping)]
    dimensions = [dict(item) for item in dimensions if isinstance(item, Mapping)]
    cells = [dict(item) for item in cells if isinstance(item, Mapping)]
    if len(claims) != len(matrix["claims"]) or len(evidence) != len(matrix["evidence"]):
        raise EvidenceReportError("matrix item is not an object")
    task_id = _clean_id(matrix.get("task_id", matrix.get("research_task_id")), "task_id")
    version = int(matrix.get("plan_version") or 0)
    if version < 1:
        raise EvidenceReportError("invalid plan_version")
    claim_ids = {_clean_id(item.get("claim_id"), "claim_id") for item in claims}
    evidence_by_id: dict[str, dict] = {}
    for item in evidence:
        evidence_id = _clean_id(item.get("evidence_id"), "evidence_id")
        if evidence_id in evidence_by_id:
            raise EvidenceReportError("duplicate evidence_id")
        if _clean_id(item.get("claim_id"), "claim_id") not in claim_ids:
            raise EvidenceReportError("evidence has no owning claim", code="CITATION_MANIFEST_INVALID")
        if _clean_id(item.get("task_id", item.get("research_task_id")), "task_id") != task_id:
            raise EvidenceReportError("evidence task mismatch")
        if item.get("status") not in {"available", "unavailable", "revalidation_required"}:
            raise EvidenceReportError("invalid evidence status")
        evidence_by_id[evidence_id] = item
    for claim in claims:
        claim_id = _clean_id(claim.get("claim_id"), "claim_id")
        if _clean_id(claim.get("task_id", claim.get("research_task_id")), "task_id") != task_id:
            raise EvidenceReportError("claim task mismatch")
        ids = claim.get("evidence_ids") or []
        if not isinstance(ids, list) or len(set(ids)) != len(ids):
            raise EvidenceReportError("claim evidence_ids must be unique")
        if not ids and claim.get("status") != "unresolved":
            raise EvidenceReportError("evidence-free claim must be unresolved")
        for evidence_id in ids:
            item = evidence_by_id.get(_clean_id(evidence_id, "evidence_id"))
            if item is None or item.get("claim_id") != claim_id:
                raise EvidenceReportError("claim references missing evidence", code="CITATION_MANIFEST_INVALID")
    dimension_ids = {_clean_id(item.get("dimension_id", item.get("id")), "dimension_id") for item in dimensions}
    cell_keys: set[tuple[str, str, str]] = set()
    for cell in cells:
        key = (_clean_id(cell.get("claim_id"), "claim_id"), _clean_id(cell.get("paper_id"), "paper_id"), _clean_id(cell.get("dimension_id"), "dimension_id"))
        if key in cell_keys or key[0] not in claim_ids or key[2] not in dimension_ids:
            raise EvidenceReportError("invalid comparison cell")
        cell_keys.add(key)
        ids = cell.get("evidence_ids") or []
        if not isinstance(ids, list):
            raise EvidenceReportError("cell evidence_ids must be a list")
        if cell.get("relation") == "missing":
            if ids or not cell.get("missing_reason"):
                raise EvidenceReportError("missing cell requires a reason")
        elif cell.get("relation") not in {"supports", "contradicts", "contextual"}:
            raise EvidenceReportError("invalid cell relation")
        for evidence_id in ids:
            item = evidence_by_id.get(_clean_id(evidence_id, "evidence_id"))
            if item is None or item.get("status") != "available" or item.get("claim_id") != key[0] or item.get("paper_id") != key[1]:
                raise EvidenceReportError("cell references invalid evidence", code="CITATION_MANIFEST_INVALID")
    limitations = matrix.get("limitations") or []
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise EvidenceReportError("limitations must be a list")
    clean_limitations = [item.strip() for item in limitations if item.strip()]
    for claim in claims:
        if not claim.get("evidence_ids") and claim.get("status") == "unresolved":
            clean_limitations.append(f"{claim['claim_id']}: no available evidence.")
    if any(item.get("status") == "available" and item.get("evidence_level") == "catalog" for item in evidence):
        clean_limitations.append("Catalog-only evidence is descriptive and does not establish method or result claims.")
    if any(item.get("status") != "available" for item in evidence):
        clean_limitations.append("Some evidence is unavailable or requires revalidation.")
    return claims, evidence, dimensions, cells, list(dict.fromkeys(clean_limitations))


def render_evidence_report(matrix: Mapping[str, Any], *, report_id: str, report_version: int, title: str = "深度研究报告") -> dict[str, Any]:
    """Build canonical report JSON plus deterministic Markdown/HTML views."""
    title = _safe_text_input(title, "title", default="深度研究报告")
    claims, evidence, dimensions, cells, limitations = _validate_matrix(matrix)
    task_id = _clean_id(matrix.get("task_id", matrix.get("research_task_id")), "task_id")
    manifest = _build_citations(report_id, claims, evidence)
    citation_by_evidence = {
        evidence_id: citation["citation_no"]
        for citation in manifest["citations"]
        for evidence_id in citation["evidence_ids"]
    }
    claim_lines: list[str] = []
    for claim in sorted(claims, key=lambda item: item["claim_id"]):
        refs = [citation_by_evidence[eid] for eid in claim.get("evidence_ids", []) if eid in citation_by_evidence]
        suffix = " ".join(f"[{number}]" for number in refs) or "（暂无可用证据）"
        claim_lines.extend([f"### {claim.get('topic') or claim['claim_id']}", "", f"{claim['statement']} {suffix}", ""])
    cell_lines: list[str] = []
    for cell in sorted(cells, key=lambda item: (item["claim_id"], item["paper_id"], item["dimension_id"])):
        refs = " ".join(f"[{citation_by_evidence[eid]}]" for eid in cell.get("evidence_ids", []) if eid in citation_by_evidence)
        detail = cell.get("summary") or cell.get("missing_reason") or ""
        cell_lines.append(f"- {cell['claim_id']} / {cell['paper_id']} / {cell['dimension_id']}：{cell['relation']} {detail} {refs}".rstrip())
    lines = [f"# {title}", "", "## 研究结论", ""] + claim_lines
    lines += ["## 跨论文比较", ""] + (cell_lines or ["- 暂无可比较单元格。", ""])
    lines += ["", "## 局限", ""] + [f"- {item}" for item in limitations]
    if not limitations:
        lines.append("- 未发现结构化覆盖缺口。")
    lines += ["", "## 引用清单", ""]
    lines += [f"- [{item['citation_no']}] `{item['paper_id']}`：`{', '.join(item['evidence_ids'])}`" for item in manifest["citations"]]
    markdown = "\n".join(lines).strip() + "\n"
    status = "partial" if limitations or not manifest["citations"] else "completed"
    report = {
        "schema_version": "evidence-report-v1", "report_id": report_id,
        "task_id": task_id, "research_task_id": task_id,
        "plan_version": int(matrix["plan_version"]), "report_version": int(report_version),
        "status": status, "claims": claims, "evidence": evidence,
        "dimensions": dimensions, "cells": cells,
        "citation_manifest": manifest, "limitations": limitations,
    }
    return {"report": report, "markdown": markdown, "html": render_markdown_html(markdown)}


class ReportGenerationService:
    """Generate and persist one immutable report version from a matrix."""

    def __init__(self, store: Any):
        self.store = store

    def generate(
        self, research_task_id: str, owner_id: str, *, plan_version: int | None = None,
        report_version: int | None = None, title: str = "深度研究报告",
    ) -> dict[str, Any]:
        task = self.store.get_task(research_task_id, owner_id)
        if task is None:
            raise EvidenceReportError("research task not found", code="TASK_NOT_FOUND")
        # An explicit report action must re-check any previously upgraded
        # full-text locator against the current KB manifest/generation.  This
        # only projects existing EvidenceUpgrade state; it does not reopen a
        # task, create an AgentRun, or introduce a second report path.
        if callable(getattr(self.store, "list_evidence_upgrades", None)):
            try:
                EvidenceUpgradeService(self.store).revalidate(research_task_id)
            except Exception as error:
                raise EvidenceReportError("full-text evidence validation failed", code="REPORT_NOT_READY") from error
        matrix = EvidenceMatrixService(self.store).read_matrix(research_task_id, owner_id, plan_version=plan_version)
        version = int(report_version or self.store.next_report_version(research_task_id, owner_id))
        if version < 1:
            raise EvidenceReportError("report_version must be positive")
        # Stable identity makes retries auditable while the task/version
        # uniqueness constraint keeps an existing report immutable.
        report_id = f"report-{research_task_id}-v{version}"
        built = ReportSynthesizer().synthesize_evidence_report(
            matrix, report_id=report_id, report_version=version, title=title,
        )
        encoded = _json(built["report"])
        model = ResearchReport(
            report_id=report_id, research_task_id=research_task_id,
            plan_version=int(matrix["plan_version"]), report_version=version,
            status=built["report"]["status"], markdown=built["markdown"], html=built["html"],
            report_json=encoded, limitations_json=_json(built["report"]["limitations"]), created_at=_utcnow(),
        )
        try:
            saved = self.store.save_research_report(model, owner_id=owner_id)
        except Exception as exc:
            if getattr(exc, "code", None) == "REPORT_VERSION_CONFLICT":
                raise EvidenceReportError("report version already exists", code="REPORT_VERSION_CONFLICT") from exc
            raise EvidenceReportError("report persistence failed") from exc
        built["report_record"] = saved.to_dict() if hasattr(saved, "to_dict") else saved
        return built

    def read(self, research_task_id: str, owner_id: str, *, report_version: int | None = None, format: str = "json") -> Any:
        report = self.store.get_research_report(research_task_id, owner_id, report_version=report_version)
        if report is None:
            raise EvidenceReportError("report is not ready", code="REPORT_NOT_READY")
        if format == "json":
            return json.loads(report.report_json)
        if format == "markdown":
            return report.markdown
        if format == "html":
            return report.html
        raise EvidenceReportError("unsupported report format", code="FORMAT_SEMANTIC_MISMATCH")


EvidenceReportGenerator = ReportGenerationService
EvidenceReportService = ReportGenerationService
ReportGenerator = ReportGenerationService

__all__ = [
    "EvidenceReportError", "ReportGenerationService", "EvidenceReportGenerator",
    "EvidenceReportService", "ReportGenerator",
    "render_evidence_report",
]
