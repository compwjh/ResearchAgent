"""Spec034 Task04: safe Planner output and plan authoring contracts.

The authoring boundary accepts only a structured, auditable plan.  It never
stores model reasoning, prompts, URLs, shell/Python instructions, or executes a
Tool.  Registry authorization is intentionally performed by the approval
service after this schema/semantic validation.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.research.domain.plan_validator import validate_plan

RESEARCH_PLAN_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "plan_version", "output_hash", "objective", "scope",
        "work_items", "capabilities", "budget", "report_structure", "safe_summary", "source_refs",
    ],
    "properties": {
        "schema_version": {"type": "string", "minLength": 1, "maxLength": 32},
        "plan_version": {"type": "integer", "minimum": 1},
        "output_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "objective": {"type": "string", "minLength": 1, "maxLength": 4000},
        "scope": {"type": "object"},
        "work_items": {"type": "array", "maxItems": 32},
        "capabilities": {"type": "array", "maxItems": 32},
        "budget": {"type": "object"},
        "report_structure": {"type": ["object", "array"]},
        "safe_summary": {"type": "object"},
        "source_refs": {"type": "array", "maxItems": 64},
    },
}

_FORBIDDEN_KEYS = frozenset({
    "cot", "chain_of_thought", "hidden_prompt", "system_prompt", "prompt", "url",
    "password", "api_key", "authorization", "token", "cookie", "credential", "credentials",
})
_URL_RE = re.compile(r"(?:https?://|ftp://|www\.|localhost(?::\d+)?(?:/|$)|(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:/|$))", re.IGNORECASE)
_SAFE_DIAGNOSTIC_CLASSIFICATIONS = frozenset({
    "forbidden_key", "url_value", "credential_pattern", "size_limit", "depth_limit", "shape_invalid",
})
_SAFE_DIAGNOSTIC_FIELDS = frozenset({
    "schema_version", "plan_version", "output_hash", "objective", "scope", "work_items",
    "capabilities", "budget", "report_structure", "safe_summary", "source_refs", "decision",
    "notes", "constraints", "degraded", "id", "task_type", "role", "depends_on", "params",
    "catalog_paper_ids", "relevance_threshold", "facets", "language", "query", "source",
    "sources", "source_ids", "years", "from_year", "to_year", "limit", "max_results",
    "target_paper_count", "minimum_paper_count", "work_item_id", "research_task_id",
    "research_session_id", "owner_id", "candidate_id", "catalog_paper_id", "paper_id",
    "candidate_ids", "catalog_evidence", "kept", "keep", "relevance_score", "reason",
    "evidence_refs", "title", "abstract", "keywords", "summary", "year", "source_id",
    "source_kinds", "publication_year", "coverage", "gaps", "recommendations", "bounded_replan",
    "report_version", "sections", "citation_manifest", "artifact_ids", "evidence_matrix",
    "report_content", "heading", "citation_ref", "paper_ids", "claim_id", "dimension_id",
    "statement", "confidence", "status", "topic", "evidence_ids", "evidence_level", "stance",
    "quote_digest", "locator", "catalog_snapshot_id", "abstract_ref", "abstract_digest",
    "cells", "claims", "evidence", "label", "definition", "display_order", "missing_reason",
    "skill", "name", "version", "enabled", "tools", "source_ref", "content_hash", "tool_name",
    "allowed_params", "required_params", "parameters", "properties", "type", "enum", "items",
    "description", "format", "citations", "title_only", "metadata_only", "verified",
})


class ResearchPlanOutput(BaseModel):
    """Pydantic transport model for a validated Planner hand-off."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=32)
    plan_version: int = Field(ge=1)
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective: str = Field(min_length=1, max_length=4000)
    scope: dict[str, Any]
    work_items: list[dict[str, Any]] = Field(max_length=32)
    capabilities: list[dict[str, Any]] = Field(max_length=32)
    budget: dict[str, Any]
    report_structure: dict[str, Any] | list[Any]
    safe_summary: dict[str, Any]
    source_refs: list[str] = Field(max_length=64)

    @field_validator("objective")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("objective must not be blank")
        return value.strip()


class PlanOutputInvalid(ValueError):
    code = "AGENT_OUTPUT_INVALID"

    def __init__(
        self,
        message: str,
        *,
        safety_classification: str | None = None,
        safe_field_path: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.safety_classification = (
            safety_classification
            if safety_classification in _SAFE_DIAGNOSTIC_CLASSIFICATIONS
            else None
        )
        self.safe_field_path = tuple(
            part for part in safe_field_path
            if part in _SAFE_DIAGNOSTIC_FIELDS or part == "unknown" or part == "[]"
        )


def _safe_diagnostic_segment(key: Any) -> str:
    normalized = str(key).casefold().replace("-", "_")
    return normalized if normalized in _SAFE_DIAGNOSTIC_FIELDS else "unknown"


def is_safe_scope_diagnostic_path(path: str) -> bool:
    """Check a generated output path against the same static schema-name allowlist."""
    if not isinstance(path, str) or len(path) > 256:
        return False
    parts = path.split(".")
    return (
        bool(parts)
        and parts[0] == "output"
        and all(part in _SAFE_DIAGNOSTIC_FIELDS or part in {"unknown", "[]"} for part in parts[1:])
    )


def _canonical_without_hash(payload: dict[str, Any]) -> bytes:
    value = {key: item for key, item in payload.items() if key != "output_hash"}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def plan_output_hash(payload: dict[str, Any]) -> str:
    """Return the deterministic hash used by the output contract."""
    return hashlib.sha256(_canonical_without_hash(payload)).hexdigest()


def _walk_safe(value: Any, *, depth: int = 0, safe_path: tuple[str, ...] = ()) -> None:
    if depth > 6:
        raise PlanOutputInvalid(
            "plan nesting exceeds limit",
            safety_classification="depth_limit",
            safe_field_path=safe_path,
        )
    if isinstance(value, dict):
        if len(value) > 64:
            raise PlanOutputInvalid(
                "plan object has too many fields",
                safety_classification="size_limit",
                safe_field_path=safe_path,
            )
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            child_path = (*safe_path, _safe_diagnostic_segment(key))
            if normalized in _FORBIDDEN_KEYS or any(token in normalized for token in ("prompt", "cot", "chainofthought", "chain_of_thought", "url")):
                raise PlanOutputInvalid(
                    "reasoning fields are not allowed",
                    safety_classification="forbidden_key",
                    safe_field_path=child_path,
                )
            if any(token in normalized for token in ("shell", "python", "code", "exec", "eval")):
                raise PlanOutputInvalid(
                    "executable capability is not allowed",
                    safety_classification="forbidden_key",
                    safe_field_path=child_path,
                )
            _walk_safe(child, depth=depth + 1, safe_path=child_path)
    elif isinstance(value, list):
        if len(value) > 64:
            raise PlanOutputInvalid(
                "plan list is too large",
                safety_classification="size_limit",
                safe_field_path=safe_path,
            )
        for child in value:
            _walk_safe(child, depth=depth + 1, safe_path=(*safe_path, "[]"))
    elif isinstance(value, str):
        lowered = value.casefold()
        if len(value) > 4000:
            raise PlanOutputInvalid(
                "unsafe or oversized plan value",
                safety_classification="size_limit",
                safe_field_path=safe_path,
            )
        if _URL_RE.search(value):
            raise PlanOutputInvalid(
                "unsafe or oversized plan value",
                safety_classification="url_value",
                safe_field_path=safe_path,
            )
        if any(marker in lowered for marker in ("authorization:", "bearer ", "api_key=", "password=", "cookie:", "token=")):
            raise PlanOutputInvalid(
                "unsafe or oversized plan value",
                safety_classification="credential_pattern",
                safe_field_path=safe_path,
            )


def validate_safe_scope(value: Any) -> None:
    """Apply the plan's recursive safety policy to command scope payloads."""
    if not isinstance(value, dict):
        raise PlanOutputInvalid(
            "scope_json must be a finite object",
            safety_classification="shape_invalid",
        )
    if len(value) > 32:
        raise PlanOutputInvalid(
            "scope_json must be a finite object",
            safety_classification="size_limit",
        )
    _walk_safe(value)


def _validate_bounded_sections(output: ResearchPlanOutput) -> None:
    sections = {
        "scope": (output.scope, {"facets", "sources", "time_range", "exclusions", "language", "depth", "constraints"}),
        "budget": (output.budget, {"quality_profile", "target_paper_count", "soft_budget_seconds", "model_loops", "tool_calls", "seconds", "resource_limits", "max_extensions", "language"}),
        "safe_summary": (output.safe_summary, {"decision", "notes", "constraints", "degraded"}),
    }
    for name, (value, allowed) in sections.items():
        if len(value) > 16 or any(str(key) not in allowed for key in value):
            raise PlanOutputInvalid(f"{name} schema is out of bounds")
    report = output.report_structure
    if isinstance(report, dict):
        if len(report) > 16 or any(str(key) not in {"sections", "format", "citations", "language", "title"} for key in report):
            raise PlanOutputInvalid("report_structure schema is out of bounds")
    elif len(report) > 16:
        raise PlanOutputInvalid("report_structure is too large")


def validate_research_plan_output(payload: Any, *, expected_version: int | None = None) -> dict[str, Any]:
    """Validate JSON Schema plus plan DAG/authorization-safe semantics.

    The returned dictionary is a detached normalized copy and may safely be
    serialized for persistence.  It contains no CoT by construction.
    """
    if not isinstance(payload, dict):
        raise PlanOutputInvalid("plan output must be an object")
    _walk_safe(payload)
    try:
        output = ResearchPlanOutput.model_validate(payload)
    except ValidationError as exc:
        raise PlanOutputInvalid("plan output schema validation failed") from exc
    if expected_version is not None and output.plan_version != expected_version:
        raise PlanOutputInvalid("plan version does not match subject")
    _validate_bounded_sections(output)
    if output.source_refs and any(not isinstance(ref, str) or not ref.strip() for ref in output.source_refs):
        raise PlanOutputInvalid("source_refs must contain non-empty IDs")
    if plan_output_hash(payload) != output.output_hash:
        raise PlanOutputInvalid("output_hash does not match normalized output")
    work_items = []
    ids: set[str] = set()
    for raw in output.work_items:
        if not isinstance(raw, dict):
            raise PlanOutputInvalid("work item must be an object")
        item = dict(raw)
        if "id" not in item or "task_type" not in item or "role" not in item:
            raise PlanOutputInvalid("work item requires id, task_type and role")
        item_id = item["id"]
        if not isinstance(item_id, str) or not item_id.strip() or item_id in ids:
            raise PlanOutputInvalid("work item IDs must be non-empty and unique")
        ids.add(item_id)
        item.setdefault("depends_on", [])
        item.setdefault("params", {})
        if not isinstance(item["depends_on"], list) or any(dep not in ids | {candidate.get("id") for candidate in output.work_items if isinstance(candidate, dict) and isinstance(candidate.get("id"), str)} for dep in item["depends_on"]):
            raise PlanOutputInvalid("work item dependency must reference an existing ID")
        work_items.append(item)
    by_id = {item["id"]: item for item in work_items}
    memo: dict[str, int] = {}
    visiting: set[str] = set()
    def depth(item_id: str) -> int:
        if item_id in visiting:
            raise PlanOutputInvalid("work item dependency cycle")
        if item_id in memo:
            return memo[item_id]
        visiting.add(item_id)
        deps = by_id[item_id].get("depends_on", [])
        value = 1 + max((depth(dep) for dep in deps), default=0)
        visiting.remove(item_id)
        memo[item_id] = value
        return value
    if any(depth(item_id) > 3 for item_id in by_id):
        raise PlanOutputInvalid("work item DAG depth exceeds three levels")
    ok, error_code = validate_plan({"work_items": work_items})
    if not ok:
        raise PlanOutputInvalid(error_code or "PLAN_VALIDATION_FAILED")
    normalized = output.model_dump(mode="json")
    normalized["work_items"] = work_items
    return normalized


__all__ = [
    "RESEARCH_PLAN_OUTPUT_SCHEMA",
    "ResearchPlanOutput",
    "PlanOutputInvalid",
    "plan_output_hash",
    "validate_research_plan_output",
    "validate_safe_scope",
]

# Descriptive aliases keep the contract discoverable to callers that use the
# ``Schema``/``validate_*`` naming convention from the other capabilities.
RESEARCH_PLAN_SCHEMA = RESEARCH_PLAN_OUTPUT_SCHEMA
ResearchPlanOutputSchema = ResearchPlanOutput
validate_plan_output = validate_research_plan_output
