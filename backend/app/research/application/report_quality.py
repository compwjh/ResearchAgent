"""Pure, bounded validation for Spec030 research report content.

This module validates one model-produced ``report_content`` candidate against a
server-built context.  It does not call a model, read storage, render a report,
or make semantic claims.  Callers should build the context from the current
approved selection and ``EvidenceMatrixService.read_matrix`` projection.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from backend.app.research.application.evidence_matrix import (
    EvidenceMatrixError,
    EvidenceMatrixService,
)

REPORT_CONTENT_SCHEMA_VERSION = "research-report-content-v1"
QUALITY_SCHEMA_VERSION = "report-quality-v1"
CJK_COUNT_METHOD = "report-quality-v1"
MIN_CJK_COUNT = 1500
MAX_REPORT_BYTES = 512 * 1024
_SAFE_FIELD_PATH = re.compile(r"^[a-z][a-z0-9_]*(?:\[\])?(?:\.[a-z][a-z0-9_]*(?:\[\])?)*$")

_CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x3134F),
    (0x31350, 0x323AF),
)


class ReportQualityError(ValueError):
    """A stable schema or server-context validation error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "REPORT_SCHEMA_INVALID",
        field_path: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.field_path = (
            field_path
            if isinstance(field_path, str)
            and len(field_path) <= 256
            and _SAFE_FIELD_PATH.fullmatch(field_path)
            else None
        )
        super().__init__(message)


@dataclass
class ReportQualityContext:
    """Trusted task context required to validate a candidate.

    ``selected_paper_ids`` must come from the current task's approved selection.
    ``evidence_matrix`` should be the current-plan projection returned by
    ``EvidenceMatrixService.read_matrix``. ``evidence_upgrades`` is the matching
    task's persisted EvidenceUpgrade set, used to independently bind fulltext
    references to task/document/chunk provenance.
    """

    task_id: str
    plan_version: int
    selected_paper_ids: Sequence[str]
    evidence_matrix: Mapping[str, Any]
    evidence_upgrades: Sequence[Any]


@dataclass(frozen=True)
class ReportQualityValidation:
    """Deterministic structural result; it does not certify semantic truth."""

    status: str
    cjk_count: int
    paper_count: int
    comparison_count: int
    supported_finding_count: int
    invalid_evidence_count: int
    failure_codes: tuple[str, ...]
    revision_count: int = 0
    schema_version: str = QUALITY_SCHEMA_VERSION
    count_method: str = CJK_COUNT_METHOD

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "cjk_count": self.cjk_count,
            "count_method": self.count_method,
            "paper_count": self.paper_count,
            "comparison_count": self.comparison_count,
            "supported_finding_count": self.supported_finding_count,
            "invalid_evidence_count": self.invalid_evidence_count,
            "failure_codes": list(self.failure_codes),
            "revision_count": self.revision_count,
        }


@dataclass(frozen=True)
class _EvidenceInfo:
    paper_id: str
    claim_id: str
    evidence_level: str
    eligible: bool
    stance: str


class _UpgradeLookup:
    def __init__(self, upgrades: Mapping[str, Any]) -> None:
        self._upgrades = upgrades

    def get_evidence_upgrade(self, claim_id: str) -> Any:
        return self._upgrades.get(claim_id)


def _fail(
    message: str,
    *,
    code: str = "REPORT_SCHEMA_INVALID",
    field_path: str | None = None,
) -> None:
    raise ReportQualityError(message, code=code, field_path=field_path)


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return converted
    _fail(f"{field} must be an object", field_path=field)


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        _fail(f"{field} must be a non-empty string of at most 200 characters", field_path=field)
    return value.strip()


def _text(value: Any, field: str, *, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or len(value) < minimum or len(value) > maximum:
        _fail(f"{field} length must be between {minimum} and {maximum}", field_path=field)
    if minimum and not value.strip():
        _fail(f"{field} must not be blank", field_path=field)
    return value


def _object(value: Any, field: str, required: set[str]) -> Mapping[str, Any]:
    item = _as_mapping(value, field)
    if set(item) != required:
        _fail(f"{field} fields must be exactly {sorted(required)}", field_path=field)
    return item


def _array(value: Any, field: str, *, minimum: int, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail(f"{field} must contain {minimum}..{maximum} items", field_path=field)
    return value


def _id_array(value: Any, field: str, *, minimum: int, maximum: int) -> list[str]:
    items = _array(value, field, minimum=minimum, maximum=maximum)
    ids = [_id(item, field) for item in items]
    if len(set(ids)) != len(ids):
        _fail(f"{field} values must be unique", field_path=field)
    return ids


def _record_task_and_plan(item: Mapping[str, Any], task_id: str, plan_version: int, field: str) -> None:
    record_task = item.get("task_id", item.get("research_task_id"))
    if _id(record_task, f"{field}.task_id") != task_id:
        _fail(f"{field} task_id mismatch")
    if (
        item.get("task_id") is not None
        and item.get("research_task_id") is not None
        and _id(item["research_task_id"], f"{field}.research_task_id") != task_id
    ):
        _fail(f"{field} research_task_id mismatch")
    version = item.get("plan_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != plan_version:
        _fail(f"{field} plan_version mismatch")


def _context_evidence(context: ReportQualityContext) -> tuple[dict[str, _EvidenceInfo], set[str], set[str]]:
    task_id = _id(context.task_id, "context.task_id")
    if isinstance(context.plan_version, bool) or not isinstance(context.plan_version, int) or context.plan_version < 1:
        _fail("context.plan_version must be a positive integer")
    plan_version = context.plan_version
    selected = _id_array(context.selected_paper_ids, "selected_paper_ids", minimum=1, maximum=64)
    selected_set = set(selected)

    matrix = _as_mapping(context.evidence_matrix, "evidence_matrix")
    if matrix.get("schema_version") != "evidence-report-v1":
        _fail("evidence_matrix schema_version is unsupported")
    _record_task_and_plan(matrix, task_id, plan_version, "evidence_matrix")
    for field in ("claims", "evidence", "dimensions", "cells"):
        if not isinstance(matrix.get(field), list):
            _fail(f"evidence_matrix.{field} must be a list")

    claims: dict[str, Mapping[str, Any]] = {}
    for raw in matrix["claims"]:
        item = _as_mapping(raw, "evidence_matrix.claim")
        claim_id = _id(item.get("claim_id"), "claim_id")
        if claim_id in claims:
            _fail("duplicate claim_id in evidence_matrix")
        _record_task_and_plan(item, task_id, plan_version, "claim")
        evidence_ids = item.get("evidence_ids") or []
        if not isinstance(evidence_ids, list):
            _fail("claim.evidence_ids must be a list")
        normalized_ids = [_id(value, "claim.evidence_id") for value in evidence_ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            _fail("claim.evidence_ids must be unique")
        claims[claim_id] = item

    upgrades: dict[str, Any] = {}
    if not isinstance(context.evidence_upgrades, Sequence) or isinstance(context.evidence_upgrades, (str, bytes)):
        _fail("evidence_upgrades must be a list")
    for raw in context.evidence_upgrades:
        item = _as_mapping(raw, "evidence_upgrade")
        claim_id = _id(item.get("claim_id"), "evidence_upgrade.claim_id")
        if claim_id in upgrades:
            _fail("duplicate evidence_upgrade claim_id")
        upgrades[claim_id] = SimpleNamespace(**dict(item))

    evidence: dict[str, _EvidenceInfo] = {}
    for raw in matrix["evidence"]:
        item = _as_mapping(raw, "evidence_matrix.evidence")
        evidence_id = _id(item.get("evidence_id"), "evidence_id")
        if evidence_id in evidence:
            _fail("duplicate evidence_id in evidence_matrix")
        _record_task_and_plan(item, task_id, plan_version, "evidence")
        claim_id = _id(item.get("claim_id"), "evidence.claim_id")
        if claim_id not in claims:
            _fail("evidence has no current-plan claim")
        paper_id = _id(item.get("paper_id"), "evidence.paper_id")
        if paper_id not in selected_set:
            _fail("evidence paper_id is outside the approved selection")
        if not isinstance(item.get("evidence_level"), str) or item["evidence_level"] not in {"catalog", "abstract", "fulltext"}:
            _fail("evidence_level is invalid")
        if not isinstance(item.get("status"), str):
            _fail("evidence.status is invalid")
        try:
            parsed = EvidenceMatrixService._evidence(item, task_id, plan_version)
        except EvidenceMatrixError as error:
            _fail(f"invalid evidence locator or source level: {error.message}")
        upgrade = upgrades.get(parsed.claim_id)
        fulltext_valid = True
        if parsed.evidence_level == "fulltext":
            fulltext_valid = bool(
                upgrade is not None
                and getattr(upgrade, "task_id", None) == task_id
                and getattr(upgrade, "to_level", None) == "fulltext"
                and EvidenceMatrixService(_UpgradeLookup(upgrades))._fulltext_upgrade_matches(parsed)
            )
        evidence[evidence_id] = _EvidenceInfo(
            paper_id=paper_id,
            claim_id=claim_id,
            evidence_level=parsed.evidence_level,
            eligible=parsed.status == "available" and fulltext_valid,
            stance=parsed.stance,
        )

    for claim_id, claim in claims.items():
        for evidence_id in claim.get("evidence_ids") or []:
            evidence_item = evidence.get(_id(evidence_id, "claim.evidence_id"))
            if evidence_item is None or evidence_item.claim_id != claim_id:
                _fail("claim references missing or misattributed evidence")

    dimensions: set[str] = set()
    for raw in matrix["dimensions"]:
        item = _as_mapping(raw, "evidence_matrix.dimension")
        _record_task_and_plan(item, task_id, plan_version, "dimension")
        dimension_id = _id(item.get("dimension_id", item.get("id")), "dimension_id")
        if item.get("dimension_id") is not None and item.get("id") is not None and _id(item["id"], "dimension.id") != dimension_id:
            _fail("dimension identifiers disagree")
        if dimension_id in dimensions:
            _fail("duplicate dimension_id in evidence_matrix")
        dimensions.add(dimension_id)

    # A read_matrix projection owns full cell validation. Check its task/plan
    # envelope here as a guard against mixing current and stale projections.
    for raw in matrix["cells"]:
        item = _as_mapping(raw, "evidence_matrix.cell")
        _record_task_and_plan(item, task_id, plan_version, "cell")

    return evidence, selected_set, dimensions


def _strip_code_blocks(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    fence: tuple[str, int] | None = None
    for line in lines:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        marker = stripped[:3]
        if fence is None and indent <= 3 and marker in {"```", "~~~"}:
            run = len(stripped) - len(stripped.lstrip(marker[0]))
            fence = (marker[0], run)
            continue
        if fence is not None:
            char, width = fence
            close_run = len(stripped) - len(stripped.lstrip(char))
            if indent <= 3 and close_run >= width and stripped[close_run:].strip() == "":
                fence = None
            continue
        if line.startswith("\t") or line.startswith("    "):
            continue
        output.append(line)
    return "\n".join(output)


def _strip_non_body_markup(text: str) -> str:
    text = _strip_code_blocks(text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(
        r"(?is)<h[1-6]\b[^>]*>\s*(?:references?|bibliography|appendix|参考文献|附录)\s*</h[1-6]\s*>.*$",
        " ",
        text,
    )
    text = re.sub(r"(?is)<(script|style|pre|code|a|h[1-6])\b[^>]*>.*?</\1\s*>", " ", text)
    lines = text.splitlines()
    filtered: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        setext_heading = (
            index + 1 < len(lines)
            and re.fullmatch(r"\s{0,3}(?:=+|-{3,})\s*", lines[index + 1]) is not None
        )
        if setext_heading:
            title = stripped.casefold()
            if any(term in title for term in ("reference", "bibliography", "appendix", "参考文献", "附录")):
                break
            continue
        if re.fullmatch(r"(?:=+|-{3,})", stripped):
            continue
        if re.match(r"(?i)^\s{0,3}\[[^\]]+\]:\s*\S+", line):
            continue
        heading = re.match(r"^\s{0,3}#{1,6}\s*(.*?)\s*#*\s*$", line)
        if heading:
            heading_text = heading.group(1).casefold()
            if any(term in heading_text for term in ("reference", "bibliography", "appendix", "参考文献", "附录")):
                break
            continue
        if index + 1 < len(lines) and re.fullmatch(r"\s{0,3}(?:=+|-{3,})\s*", lines[index + 1]):
            continue
        filtered.append(line)
    text = "\n".join(filtered)
    text = re.sub(r"(`+)[^\n]*?\1", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]+\]\[[^\]]*\]", " ", text)
    text = re.sub(r"\[[^\]\n]{1,200}\]", " ", text)
    text = re.sub(r"(?i)\bhttps?://\S+", " ", text)
    text = re.sub(r"<[^>]*>", " ", text)
    return text


def _is_cjk(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in _CJK_RANGES)


def _body_texts(report_content: Mapping[str, Any]) -> list[str]:
    texts: list[str] = []
    question = report_content.get("research_question")
    if isinstance(question, Mapping) and isinstance(question.get("text"), str):
        texts.append(question["text"])
    scope = report_content.get("evidence_scope")
    if isinstance(scope, Mapping) and isinstance(scope.get("text"), str):
        texts.append(scope["text"])
    for analysis in report_content.get("paper_analyses", []) if isinstance(report_content.get("paper_analyses"), list) else []:
        if not isinstance(analysis, Mapping):
            continue
        for key in ("method", "findings", "limitations"):
            block = analysis.get(key)
            if isinstance(block, Mapping) and block.get("status") == "supported" and isinstance(block.get("text"), str):
                texts.append(block["text"])
    for group in ("cross_paper_comparisons", "synthesis_findings", "research_gaps"):
        entries = report_content.get(group, [])
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, Mapping) and isinstance(item.get("statement"), str):
                    texts.append(item["statement"])
    return texts


def count_report_content_cjk(report_content: Mapping[str, Any]) -> int:
    """Count contract CJK code points in structured body fields only.

    Headings, reference markers, Markdown/HTML link markup and link targets,
    markup tags, and fenced/inline/indented code are excluded before counting.
    """
    if not isinstance(report_content, Mapping):
        return 0
    count = 0
    for body in _body_texts(report_content):
        visible_text = _strip_non_body_markup(body)
        count += sum(1 for character in visible_text if _is_cjk(ord(character)))
    return count


def _validate_report_shape(report_content: Any) -> Mapping[str, Any]:
    if not isinstance(report_content, Mapping):
        _fail("report_content must be an object", field_path="report_content")
    try:
        encoded = json.dumps(report_content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        _fail(f"report_content must be UTF-8 JSON: {error}", field_path="report_content")
    if len(encoded) > MAX_REPORT_BYTES:
        _fail("report_content exceeds 512 KiB", field_path="report_content")

    required = {
        "schema_version", "research_question", "evidence_scope", "paper_analyses",
        "cross_paper_comparisons", "synthesis_findings", "research_gaps",
    }
    if set(report_content) != required:
        _fail("report_content fields do not match the versioned schema", field_path="report_content")
    if report_content.get("schema_version") != REPORT_CONTENT_SCHEMA_VERSION:
        _fail("report_content schema_version is unsupported", field_path="report_content.schema_version")

    question = _object(report_content.get("research_question"), "research_question", {"text"})
    _text(question.get("text"), "research_question.text", minimum=1, maximum=2000)
    scope = _object(report_content.get("evidence_scope"), "evidence_scope", {"text", "paper_ids"})
    _text(scope.get("text"), "evidence_scope.text", minimum=1, maximum=4000)
    _id_array(scope.get("paper_ids"), "evidence_scope.paper_ids", minimum=5, maximum=64)

    analyses = _array(report_content.get("paper_analyses"), "paper_analyses", minimum=5, maximum=64)
    analysis_ids: set[str] = set()
    for raw in analyses:
        item = _object(raw, "paper_analyses[]", {"paper_id", "method", "findings", "limitations"})
        paper_id = _id(item.get("paper_id"), "paper_analyses[].paper_id")
        if paper_id in analysis_ids:
            _fail("paper_analysis.paper_id values must be unique", field_path="paper_analyses[].paper_id")
        analysis_ids.add(paper_id)
        for field in ("method", "findings", "limitations"):
            block_path = f"paper_analyses[].{field}"
            block = _object(item.get(field), block_path, {"status", "text", "evidence_ids"})
            status = block.get("status")
            if not isinstance(status, str) or status not in {"supported", "not_stated", "unavailable"}:
                _fail(f"paper_analysis.{field}.status is invalid", field_path=f"{block_path}.status")
            text = _text(block.get("text"), f"{block_path}.text", minimum=0, maximum=4000)
            evidence_ids = _id_array(block.get("evidence_ids"), f"{block_path}.evidence_ids", minimum=0, maximum=32)
            if status == "supported":
                if not text.strip() or not evidence_ids:
                    _fail(f"supported {field} requires text and evidence_ids", field_path=f"{block_path}.evidence_ids")
            elif text != "" or evidence_ids:
                _fail(f"{status} {field} must have empty text and evidence_ids", field_path=f"{block_path}.text")
        if not any(item[field]["status"] == "supported" for field in ("method", "findings", "limitations")):
            _fail("each paper_analysis requires at least one supported block", field_path="paper_analyses[].method.status")

    comparisons = _array(report_content.get("cross_paper_comparisons"), "cross_paper_comparisons", minimum=1, maximum=16)
    for raw in comparisons:
        item = _object(raw, "cross_paper_comparisons[]", {"dimension_id", "paper_ids", "statement", "evidence_ids"})
        _id(item.get("dimension_id"), "cross_paper_comparisons[].dimension_id")
        _id_array(item.get("paper_ids"), "cross_paper_comparisons[].paper_ids", minimum=2, maximum=64)
        _text(item.get("statement"), "cross_paper_comparisons[].statement", minimum=1, maximum=3000)
        _id_array(item.get("evidence_ids"), "cross_paper_comparisons[].evidence_ids", minimum=2, maximum=32)

    findings = _array(report_content.get("synthesis_findings"), "synthesis_findings", minimum=3, maximum=16)
    finding_ids: set[str] = set()
    for raw in findings:
        item = _object(raw, "synthesis_findings[]", {"finding_id", "statement", "paper_ids", "evidence_ids"})
        finding_id = _id(item.get("finding_id"), "synthesis_findings[].finding_id")
        if finding_id in finding_ids:
            _fail("finding_id values must be unique", field_path="synthesis_findings[].finding_id")
        finding_ids.add(finding_id)
        _text(item.get("statement"), "synthesis_findings[].statement", minimum=1, maximum=3000)
        _id_array(item.get("paper_ids"), "synthesis_findings[].paper_ids", minimum=2, maximum=64)
        _id_array(item.get("evidence_ids"), "synthesis_findings[].evidence_ids", minimum=2, maximum=32)

    gaps = _array(report_content.get("research_gaps"), "research_gaps", minimum=0, maximum=32)
    for raw in gaps:
        item = _object(raw, "research_gaps[]", {"statement", "evidence_ids"})
        _text(item.get("statement"), "research_gaps[].statement", minimum=1, maximum=2000)
        _id_array(item.get("evidence_ids"), "research_gaps[].evidence_ids", minimum=0, maximum=32)
    return report_content


def _reference_papers(
    ids: Sequence[str], evidence: Mapping[str, _EvidenceInfo], declared_papers: set[str], invalid_ids: set[str]
) -> tuple[set[str], bool]:
    mapped: set[str] = set()
    all_valid = True
    for evidence_id in ids:
        item = evidence.get(evidence_id)
        if item is None or not item.eligible or item.paper_id not in declared_papers:
            invalid_ids.add(evidence_id)
            all_valid = False
            continue
        mapped.add(item.paper_id)
    return mapped, all_valid


def validate_report_content(
    report_content: Any,
    context: ReportQualityContext,
    *,
    revision_count: int = 0,
) -> ReportQualityValidation:
    """Validate bounds, current-task refs, coverage counts, and CJK threshold.

    Invalid candidate references fail closed and are counted in the result.
    Malformed content or a malformed/stale server context raises
    ``ReportQualityError``. A ``pass`` means only that machine-checkable
    structure, provenance, coverage, and count gates passed; it is not a manual
    semantic-quality verdict.
    """
    if isinstance(revision_count, bool) or not isinstance(revision_count, int) or not 0 <= revision_count <= 2:
        _fail("revision_count must be between 0 and 2")
    content = _validate_report_shape(report_content)
    if not isinstance(context, ReportQualityContext):
        _fail("context must be a ReportQualityContext")
    evidence, selected_papers, dimensions = _context_evidence(context)

    invalid_evidence_ids: set[str] = set()
    failure_codes: list[str] = []
    invalid_selection = False
    evidence_scope_ids = set(_id_array(content["evidence_scope"]["paper_ids"], "evidence_scope.paper_ids", minimum=5, maximum=64))
    if not evidence_scope_ids.issubset(selected_papers):
        invalid_selection = True

    paper_count = 0
    for raw in content["paper_analyses"]:
        paper_id = _id(raw["paper_id"], "paper_analysis.paper_id")
        supported_blocks = [raw[field] for field in ("method", "findings", "limitations") if raw[field]["status"] == "supported"]
        refs_valid = True
        if paper_id not in selected_papers or paper_id not in evidence_scope_ids:
            invalid_selection = True
            refs_valid = False
        for block in supported_blocks:
            mapped, all_refs_valid = _reference_papers(block["evidence_ids"], evidence, {paper_id}, invalid_evidence_ids)
            if not all_refs_valid or len(mapped) != 1 or mapped != {paper_id}:
                refs_valid = False
        if refs_valid:
            paper_count += 1

    comparison_count = 0
    for item in content["cross_paper_comparisons"]:
        declared = set(item["paper_ids"])
        if not declared.issubset(selected_papers):
            invalid_selection = True
        dimension_valid = item["dimension_id"] in dimensions
        mapped, all_refs_valid = _reference_papers(item["evidence_ids"], evidence, declared & selected_papers, invalid_evidence_ids)
        if all_refs_valid and dimension_valid and declared.issubset(selected_papers) and len(mapped) >= 2:
            comparison_count += 1
        elif not dimension_valid and "INVALID_DIMENSION_REFERENCE" not in failure_codes:
            failure_codes.append("INVALID_DIMENSION_REFERENCE")

    supported_finding_count = 0
    for item in content["synthesis_findings"]:
        declared = set(item["paper_ids"])
        if not declared.issubset(selected_papers):
            invalid_selection = True
        mapped, all_refs_valid = _reference_papers(item["evidence_ids"], evidence, declared & selected_papers, invalid_evidence_ids)
        if all_refs_valid and declared.issubset(selected_papers) and len(mapped) >= 2:
            supported_finding_count += 1

    for item in content["research_gaps"]:
        _reference_papers(item["evidence_ids"], evidence, selected_papers, invalid_evidence_ids)

    if invalid_selection:
        failure_codes.append("INVALID_PAPER_SELECTION")
    if invalid_evidence_ids:
        failure_codes.append("INVALID_EVIDENCE_REFERENCE")
    if paper_count < 5:
        failure_codes.append("INSUFFICIENT_PAPERS")
    if comparison_count < 1:
        failure_codes.append("INSUFFICIENT_COMPARISONS")
    if supported_finding_count < 3:
        failure_codes.append("INSUFFICIENT_SUPPORTED_FINDINGS")

    cjk_count = count_report_content_cjk(content)
    if cjk_count < MIN_CJK_COUNT:
        failure_codes.append("CJK_COUNT_BELOW_MINIMUM")
    # Keep codes unique and ordered by the checks above for stable persistence.
    stable_codes = tuple(dict.fromkeys(failure_codes))
    return ReportQualityValidation(
        status="pass" if not stable_codes else "fail",
        cjk_count=cjk_count,
        paper_count=paper_count,
        comparison_count=comparison_count,
        supported_finding_count=supported_finding_count,
        invalid_evidence_count=len(invalid_evidence_ids),
        failure_codes=stable_codes,
        revision_count=revision_count,
    )


__all__ = [
    "CJK_COUNT_METHOD",
    "MAX_REPORT_BYTES",
    "MIN_CJK_COUNT",
    "QUALITY_SCHEMA_VERSION",
    "REPORT_CONTENT_SCHEMA_VERSION",
    "ReportQualityContext",
    "ReportQualityError",
    "ReportQualityValidation",
    "count_report_content_cjk",
    "validate_report_content",
]
