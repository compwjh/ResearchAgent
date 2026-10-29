"""Spec030 evidence-report generation and read-only export boundary.

This module consumes the canonical projection produced by
``EvidenceMatrixService``.  It does not retrieve papers or inspect documents;
all facts and locators must already be present in that projection.
"""

from __future__ import annotations

import html as html_module
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.evidence_upgrade import EvidenceUpgradeService
from backend.app.research.application.report_quality import (
    ReportQualityContext,
    ReportQualityError,
    validate_report_content,
)
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

    def __init__(
        self, message: str = "", *, code: str = "REPORT_SCHEMA_INVALID", existing_report: Any = None,
    ) -> None:
        super().__init__(message or code, code=code)
        self.http_status = self._STATUS.get(code, 409)
        self.existing_report = existing_report


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


_SOURCE_LEVEL_LABELS = {
    "catalog": "目录元数据",
    "abstract": "摘要",
    "fulltext": "全文",
}

_REPORT_TEXT_ENTITIES = str.maketrans({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    "[": "&#91;", "]": "&#93;", "\\": "&#92;", "`": "&#96;",
    "*": "&#42;", "_": "&#95;", "{": "&#123;", "}": "&#125;",
    "#": "&#35;", "+": "&#43;",
    "-": "&#45;", ".": "&#46;", "!": "&#33;", "|": "&#124;",
    "~": "&#126;", "=": "&#61;", ":": "&#58;",
    "'": "&#x27;", '"': "&quot;",
})


def _plain_report_text(value: str) -> str:
    """Encode dynamic report text so Markdown syntax remains literal text."""
    return value.translate(_REPORT_TEXT_ENTITIES)


def _render_structured_report_html(markdown: str) -> str:
    """Render structured output without interpreting model text as markup.

    The shared renderer escapes the Markdown source for HTML. Removing that
    one escaping layer restores the entities emitted by ``_plain_report_text``;
    encoded angle brackets remain text entities. Citation syntax is left raw
    only where this module generated it from validated Evidence IDs.
    """
    return html_module.unescape(render_markdown_html(markdown))


def _report_content_evidence_ids(content: Mapping[str, Any]) -> list[str]:
    ordered: list[str] = []
    for analysis in content["paper_analyses"]:
        for field in ("method", "findings", "limitations"):
            block = analysis[field]
            if block["status"] == "supported":
                ordered.extend(str(value).strip() for value in block["evidence_ids"])
    for key in ("cross_paper_comparisons", "synthesis_findings", "research_gaps"):
        for item in content[key]:
            ordered.extend(str(value).strip() for value in item["evidence_ids"])
    return list(dict.fromkeys(ordered))


def _render_validated_report_content(
    content: Mapping[str, Any],
    *,
    report_id: str,
    report_version: int,
    context: ReportQualityContext,
    title: str,
) -> dict[str, Any]:
    try:
        quality = validate_report_content(content, context)
    except ReportQualityError as error:
        raise EvidenceReportError(str(error), code="REPORT_SCHEMA_INVALID") from error
    if quality.status != "pass":
        raise EvidenceReportError("report content failed machine quality validation", code="REPORT_SCHEMA_INVALID")

    matrix = context.evidence_matrix
    evidence_records = matrix.get("evidence", [])
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for raw in evidence_records:
        if isinstance(raw, Mapping):
            item = dict(raw)
        elif callable(getattr(raw, "to_dict", None)):
            item = raw.to_dict()
        else:
            raise EvidenceReportError("validated evidence projection is malformed")
        evidence_id = _clean_id(item.get("evidence_id"), "evidence_id")
        evidence_by_id[evidence_id] = item

    evidence_ids = _report_content_evidence_ids(content)
    citation_by_evidence: dict[str, int] = {}
    citations: list[dict[str, Any]] = []
    for evidence_id in evidence_ids:
        item = evidence_by_id.get(evidence_id)
        if item is None or item.get("status") != "available":
            raise EvidenceReportError("report content references invalid evidence", code="CITATION_MANIFEST_INVALID")
        level = item.get("evidence_level")
        if level not in _SOURCE_LEVEL_LABELS:
            raise EvidenceReportError("report content references an invalid evidence level", code="CITATION_MANIFEST_INVALID")
        number = len(citations) + 1
        citation_by_evidence[evidence_id] = number
        citations.append({
            "citation_no": number,
            "paper_id": _clean_id(item.get("paper_id"), "paper_id"),
            "evidence_ids": [evidence_id],
            "claim_ids": [_clean_id(item.get("claim_id"), "claim_id")],
            "source_level": level,
        })

    def citation_suffix(ids: Sequence[str]) -> str:
        return " ".join(f"[{citation_by_evidence[str(value).strip()]}]" for value in ids)

    dimension_labels: dict[str, str] = {}
    for raw in matrix.get("dimensions", []):
        item = dict(raw) if isinstance(raw, Mapping) else raw.to_dict()
        dimension_id = _clean_id(item.get("dimension_id", item.get("id")), "dimension_id")
        label = item.get("label")
        raw_label = " ".join(label.split()) if isinstance(label, str) and label.strip() else dimension_id
        dimension_labels[dimension_id] = _plain_report_text(raw_label)

    lines = [f"# {_plain_report_text(title)}", "", "## 研究问题", "", _plain_report_text(content["research_question"]["text"]), ""]
    lines.extend(["## 证据范围", "", _plain_report_text(content["evidence_scope"]["text"]), "", "## 逐篇分析", ""])
    status_labels = {"not_stated": "来源未说明", "unavailable": "来源不可用"}
    field_labels = {"method": "方法", "findings": "发现", "limitations": "局限"}
    for index, analysis in enumerate(content["paper_analyses"], start=1):
        lines.extend([f"### 论文 {index}", ""])
        for field in ("method", "findings", "limitations"):
            block = analysis[field]
            body = _plain_report_text(block["text"]) if block["status"] == "supported" else status_labels[block["status"]]
            refs = citation_suffix(block["evidence_ids"])
            suffix = f" {refs}" if refs else ""
            lines.append(f"- {field_labels[field]}：{body}{suffix}")
        lines.append("")

    lines.extend(["## 跨论文比较", ""])
    for item in content["cross_paper_comparisons"]:
        dimension = dimension_labels[item["dimension_id"]]
        lines.append(f"### {dimension}")
        lines.append(f"{_plain_report_text(item['statement'])} {citation_suffix(item['evidence_ids'])}")
        lines.append("")

    lines.extend(["## 综合发现", ""])
    for item in content["synthesis_findings"]:
        lines.append(f"- {_plain_report_text(item['statement'])} {citation_suffix(item['evidence_ids'])}")
    lines.extend(["", "## 研究缺口", ""])
    for item in content["research_gaps"]:
        refs = citation_suffix(item["evidence_ids"])
        suffix = f" {refs}" if refs else ""
        lines.append(f"- {_plain_report_text(item['statement'])}{suffix}")

    lines.extend(["", "## 引用清单", ""])
    lines.extend(
        f"- [{item['citation_no']}] {_plain_report_text(item['paper_id'])}（来源级别：{_SOURCE_LEVEL_LABELS[item['source_level']]}；Evidence ID：{_plain_report_text(item['evidence_ids'][0])}）"
        for item in citations
    )
    markdown = "\n".join(lines).strip() + "\n"
    manifest = {"manifest_version": 1, "report_id": report_id, "citations": citations}
    report = {
        "report_id": report_id,
        "report_version": report_version,
        "plan_version": context.plan_version,
        "report_content": dict(content),
        "quality_validation": quality.to_dict(),
        "citation_manifest": manifest,
    }
    return {"report": report, "markdown": markdown, "html": _render_structured_report_html(markdown)}


def render_report_payload(
    payload: Mapping[str, Any],
    *,
    report_id: str,
    report_version: int,
    context: ReportQualityContext | None,
    title: str = "深度研究报告",
) -> dict[str, Any]:
    """Render validated report_content-v1, or preserve legacy matrix rendering.

    Structured content is rejected unless all machine gates pass. Its Markdown
    is the sole body source for HTML, whose text escaping is delegated to the
    existing fixed renderer. A legacy ``evidence-report-v1`` matrix continues
    through ``render_evidence_report`` unchanged.
    """
    if not isinstance(payload, Mapping):
        raise EvidenceReportError("report payload must be an object")
    report_id = _clean_id(report_id, "report_id")
    if isinstance(report_version, bool) or not isinstance(report_version, int) or report_version < 1:
        raise EvidenceReportError("report_version must be positive")
    title = _safe_text_input(title, "title", default="深度研究报告")

    if "report_content" in payload:
        content = payload["report_content"]
    elif payload.get("schema_version") == "research-report-content-v1":
        content = payload
    elif payload.get("schema_version") == "evidence-report-v1":
        return render_evidence_report(payload, report_id=report_id, report_version=report_version, title=title)
    else:
        raise EvidenceReportError("report payload schema is unsupported")

    if context is None:
        raise EvidenceReportError("report content requires validated task context")
    return _render_validated_report_content(
        content,
        report_id=report_id,
        report_version=report_version,
        context=context,
        title=title,
    )


class ReportGenerationService:
    """Generate and persist one immutable report version from a matrix."""

    def __init__(self, store: Any):
        self.store = store

    @staticmethod
    def _report_request_key(value: Any) -> str:
        try:
            return str(UUID(value))
        except (ValueError, TypeError, AttributeError) as error:
            raise EvidenceReportError("Idempotency-Key must be a UUID") from error

    @staticmethod
    def _report_generation_payload(report: Any) -> dict[str, Any]:
        try:
            payload = json.loads(report.report_json or "{}")
        except (TypeError, ValueError, AttributeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _validated_report_candidates(self, research_task_id: str, plan_version: int) -> list[dict[str, Any]]:
        """Reuse only the frozen synthesizer selection matching durable selections."""
        list_selections = getattr(self.store, "list_selections", None)
        list_work_items = getattr(self.store, "list_work_items", None)
        if not callable(list_selections) or not callable(list_work_items):
            raise EvidenceReportError("validated matrix candidates are unavailable", code="REPORT_NOT_READY")
        try:
            selected_ids = {
                str(item.catalog_paper_id).strip()
                for item in list_selections(research_task_id)
                if isinstance(getattr(item, "catalog_paper_id", None), str)
                and item.catalog_paper_id.strip()
            }
            work_items = list(list_work_items(research_task_id, plan_version=plan_version))
        except Exception as error:
            raise EvidenceReportError("validated matrix candidates are unavailable", code="REPORT_NOT_READY") from error
        if not selected_ids or len(selected_ids) > 20:
            raise EvidenceReportError("validated matrix candidates are unavailable", code="REPORT_NOT_READY")

        for item in reversed(work_items):
            if (
                getattr(item, "task_type", None) != "synthesize_preliminary_report"
                or getattr(item, "role", None) != "synthesizer"
                or getattr(item, "research_task_id", None) != research_task_id
                or getattr(item, "plan_version", None) != plan_version
            ):
                continue
            candidates = getattr(item, "input_params", {}).get("validated_candidates")
            if not isinstance(candidates, list) or not candidates or len(candidates) > 20:
                continue
            copied: list[dict[str, Any]] = []
            candidate_ids: list[str] = []
            valid = True
            for raw in candidates:
                if not isinstance(raw, Mapping):
                    valid = False
                    break
                candidate_id = raw.get("candidate_id", raw.get("catalog_paper_id"))
                evidence_refs = raw.get("evidence_refs")
                if (
                    not isinstance(candidate_id, str)
                    or not candidate_id.strip()
                    or not isinstance(evidence_refs, list)
                    or len(evidence_refs) > 80
                    or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 240 for ref in evidence_refs)
                ):
                    valid = False
                    break
                candidate = dict(raw)
                candidate["candidate_id"] = candidate_id.strip()
                candidate["evidence_refs"] = list(dict.fromkeys(ref.strip() for ref in evidence_refs))
                copied.append(candidate)
                candidate_ids.append(candidate_id.strip())
            if valid and len(set(candidate_ids)) == len(candidate_ids) and set(candidate_ids) == selected_ids:
                return copied
        raise EvidenceReportError("validated matrix candidates are unavailable", code="REPORT_NOT_READY")

    def _same_title_active_reservation(
        self, research_task_id: str, owner_id: str, *, plan_version: int, title: str,
    ) -> Any | None:
        reports_reader = getattr(self.store, "list_research_reports", None)
        reservation_reader = getattr(self.store, "get_report_generation_reservation", None)
        if not callable(reports_reader) or not callable(reservation_reader):
            return None
        for report in reversed(reports_reader(research_task_id, owner_id)):
            if getattr(report, "status", None) != "generating" or getattr(report, "plan_version", None) != plan_version:
                continue
            payload = self._report_generation_payload(report)
            generation = payload.get("generation") if isinstance(payload, dict) else None
            request_key = generation.get("request_key") if isinstance(generation, dict) else None
            if not isinstance(request_key, str):
                continue
            reservation = reservation_reader(research_task_id, owner_id, request_key=request_key)
            if reservation is not None and reservation.work_item.input_params.get("report_title") == title:
                return reservation
        return None

    def _active_report_generation(self, research_task_id: str, owner_id: str, *, plan_version: int) -> Any | None:
        reports_reader = getattr(self.store, "list_research_reports", None)
        if not callable(reports_reader):
            return None
        return next((
            report for report in reversed(reports_reader(research_task_id, owner_id))
            if getattr(report, "status", None) == "generating"
            and getattr(report, "plan_version", None) == plan_version
        ), None)

    def reserve_session_generation(
        self,
        research_task_id: str,
        owner_id: str,
        *,
        plan_version: int | None = None,
        report_version: int | None = None,
        title: str = "深度研究报告",
        request_key: str | None = None,
    ) -> Any:
        """Atomically reserve an async report-only run for an existing Session Task."""
        key_was_omitted = request_key is None
        title = title.strip() if isinstance(title, str) else ""
        if not title or len(title) > 200:
            raise EvidenceReportError("report title is invalid")
        task = self.store.get_task(research_task_id, owner_id)
        if task is None:
            raise EvidenceReportError("research task not found", code="TASK_NOT_FOUND")
        if task.status not in {"completed", "partial", "failed", "interrupted", "cancelled"}:
            raise EvidenceReportError("report-only generation requires a terminal research task", code="REPORT_NOT_READY")
        session_reader = getattr(self.store, "get_session_by_task", None)
        session = session_reader(research_task_id, owner_id) if callable(session_reader) else None
        if session is None or session.owner_id != owner_id:
            raise EvidenceReportError("report-only generation requires an owned research session", code="REPORT_NOT_READY")

        version = int(plan_version or task.current_plan_version)
        if version < 1 or version != int(task.current_plan_version):
            raise EvidenceReportError("report generation requires the current plan version", code="REPORT_VERSION_CONFLICT")
        plan_reader = getattr(self.store, "get_plan", None)
        plan = plan_reader(research_task_id, version) if callable(plan_reader) else None
        if plan is None or plan.status not in {"active", "completed"}:
            raise EvidenceReportError("report generation plan is unavailable", code="REPORT_VERSION_CONFLICT")

        request_payload = {
            "plan_version": version,
            "title": title,
            "schema_version": "report-quality-v1",
        }
        key: str | None = None
        if request_key is not None:
            key = self._report_request_key(request_key)
            reservation_reader = getattr(self.store, "get_report_generation_reservation", None)
            existing = reservation_reader(research_task_id, owner_id, request_key=key) if callable(reservation_reader) else None
            if existing is not None:
                return self._reserve_from_store(
                    research_task_id, owner_id, plan_version=version, request_key=key,
                    request_payload=request_payload, report_version=report_version,
                )
        else:
            joined = self._same_title_active_reservation(
                research_task_id, owner_id, plan_version=version, title=title,
            )
            if joined is not None:
                payload = self._report_generation_payload(joined.report)
                generation = payload.get("generation") if isinstance(payload, dict) else None
                active_key = generation.get("request_key") if isinstance(generation, dict) else None
                if isinstance(active_key, str):
                    return self._reserve_from_store(
                        research_task_id, owner_id, plan_version=version, request_key=active_key,
                        request_payload=request_payload, report_version=report_version,
                    )
            key = str(uuid4())

        active_report = self._active_report_generation(
            research_task_id, owner_id, plan_version=version,
        )
        if active_report is not None:
            raise EvidenceReportError(
                "a report version is already generating",
                code="REPORT_GENERATION_IN_PROGRESS",
                existing_report=active_report,
            )

        try:
            matrix = EvidenceMatrixService(self.store).read_matrix(
                research_task_id, owner_id, plan_version=version,
            )
        except EvidenceReportError:
            raise
        except Exception as error:
            code = "REPORT_NOT_READY" if getattr(error, "code", None) == "MATRIX_NOT_READY" else "REPORT_NOT_READY"
            raise EvidenceReportError("report matrix is not ready", code=code) from error
        if (
            not isinstance(matrix, Mapping)
            or matrix.get("task_id", matrix.get("research_task_id")) != research_task_id
            or matrix.get("plan_version") != version
        ):
            raise EvidenceReportError("report matrix context is unavailable", code="REPORT_NOT_READY")
        candidates = self._validated_report_candidates(research_task_id, version)
        allowlist = [
            {"citation_ref": ref, "candidate_id": candidate["candidate_id"]}
            for candidate in candidates for ref in candidate["evidence_refs"]
        ]
        try:
            return self._reserve_from_store(
                research_task_id,
                owner_id,
                plan_version=version,
                request_key=key,
                request_payload=request_payload,
                work_item_input={
                    "validated_candidates": candidates,
                    "citation_allowlist": allowlist,
                    "report_title": title,
                },
                report_version=report_version,
            )
        except EvidenceReportError as error:
            # If two no-header requests race before either can observe the
            # other's active row, join the winner only when its stored title
            # and current plan match this request.
            if not key_was_omitted or error.code != "REPORT_GENERATION_IN_PROGRESS":
                raise
            joined = self._same_title_active_reservation(
                research_task_id, owner_id, plan_version=version, title=title,
            )
            if joined is None:
                raise
            payload = self._report_generation_payload(joined.report)
            generation = payload.get("generation") if isinstance(payload, dict) else None
            active_key = generation.get("request_key") if isinstance(generation, dict) else None
            if not isinstance(active_key, str):
                raise
            return self._reserve_from_store(
                research_task_id, owner_id, plan_version=version, request_key=active_key,
                request_payload=request_payload, report_version=report_version,
            )

    def _reserve_from_store(
        self,
        research_task_id: str,
        owner_id: str,
        *,
        plan_version: int,
        request_key: str,
        request_payload: Mapping[str, Any],
        work_item_input: Mapping[str, Any] | None = None,
        report_version: int | None = None,
    ) -> Any:
        try:
            return self.store.reserve_report_generation(
                research_task_id,
                owner_id,
                plan_version=plan_version,
                request_key=request_key,
                request_payload=request_payload,
                work_item_input=work_item_input,
                report_version=report_version,
            )
        except Exception as error:
            code = getattr(error, "code", None)
            if code in {"REPORT_GENERATION_IN_PROGRESS", "REPORT_IDEMPOTENCY_KEY_REUSED", "REPORT_VERSION_CONFLICT"}:
                raise EvidenceReportError(
                    str(error), code=code, existing_report=getattr(error, "existing_report", None),
                ) from error
            if isinstance(error, ValueError):
                raise EvidenceReportError("report reservation input is invalid") from error
            raise

    @staticmethod
    def submission_projection(reservation: Any) -> dict[str, Any]:
        report = reservation.report
        payload = ReportGenerationService._report_generation_payload(report)
        generation = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
        quality = payload.get("quality_validation") if isinstance(payload.get("quality_validation"), dict) else {}
        failure_codes = quality.get("failure_codes", [])
        if not isinstance(failure_codes, list):
            failure_codes = []
        state_codes = payload.get("reason_codes", [])
        if not isinstance(state_codes, list):
            state_codes = []
        fallback_code = generation.get("fallback_reason_code")
        reason_codes = list(dict.fromkeys(
            [code for code in failure_codes if isinstance(code, str) and code.isascii() and len(code) <= 80]
            + [code for code in state_codes if isinstance(code, str) and code.isascii() and len(code) <= 80]
            + ([fallback_code] if isinstance(fallback_code, str) and fallback_code.isascii() and len(fallback_code) <= 80 else [])
        ))
        quality_status = quality.get("status")
        if quality_status not in {"pending", "pass", "fail", "unvalidated"}:
            quality_status = "pending" if report.status == "generating" else "unvalidated"
        limitations = []
        try:
            decoded = json.loads(report.limitations_json or "[]")
            limitations = decoded if isinstance(decoded, list) else []
        except (TypeError, ValueError):
            pass
        return {
            "report_id": report.report_id,
            "research_task_id": report.research_task_id,
            "plan_version": report.plan_version,
            "report_version": report.report_version,
            "status": report.status,
            "limitations": limitations,
            "quality_status": quality_status,
            "published": generation.get("published") is True,
            "reason_codes": reason_codes,
            "report_url": f"/api/research-tasks/{report.research_task_id}/reports/{report.report_version}?format=json",
        }

    def generate(
        self, research_task_id: str, owner_id: str, *, plan_version: int | None = None,
        report_version: int | None = None, title: str = "深度研究报告",
        additional_limitations: Iterable[str] | None = None,
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
        extra_limitations = [
            item.strip()
            for item in (additional_limitations or ())
            if isinstance(item, str) and item.strip()
        ]
        if extra_limitations:
            matrix = dict(matrix)
            matrix["limitations"] = list(dict.fromkeys([
                *(matrix.get("limitations") or []),
                *extra_limitations,
            ]))
        version = int(report_version or self.store.next_report_version(research_task_id, owner_id))
        if version < 1:
            raise EvidenceReportError("report_version must be positive")
        # Stable identity makes retries auditable while the task/version
        # uniqueness constraint keeps an existing report immutable.
        report_id = f"report-{research_task_id}-v{version}"
        built = ReportSynthesizer().synthesize_evidence_report(
            matrix, report_id=report_id, report_version=version, title=title,
        )
        session_reader = getattr(self.store, "get_session_by_task", None)
        session = session_reader(research_task_id, owner_id) if callable(session_reader) else None
        if session is None:
            legacy_report = dict(built["report"])
            legacy_report["status"] = "draft"
            legacy_report["published"] = False
            legacy_report["quality_validation"] = {"status": "unvalidated", "failure_codes": []}
            legacy_report["generation"] = {
                "report_version": version,
                "plan_version": int(matrix["plan_version"]),
                "path": "matrix_api",
                "output_disposition": "not_run",
                "published": False,
            }
            built["report"] = legacy_report
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
    "render_evidence_report", "render_report_payload",
]
