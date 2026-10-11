"""Pure validation for the internal ``evidence-report-v1`` matrix contract.

The natural-language synthesizer, restart hydration and matrix persistence all
consume the same server-owned snapshot.  Keeping this validator independent
of orchestration and storage makes the acceptance boundary single-source and
side-effect free: it only returns a validated projection or raises the
existing ``EvidenceMatrixError`` without rewriting model output or creating
evidence.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from backend.app.research.application.evidence_matrix import EvidenceMatrixError

MATRIX_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,240}$")
_MATRIX_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_MATRIX_DIMENSION_KEYS = frozenset({"dimension_id", "label", "definition", "display_order"})
_MATRIX_CLAIM_KEYS = frozenset({"claim_id", "topic", "statement", "confidence", "status", "evidence_ids"})
_MATRIX_EVIDENCE_KEYS = frozenset({
    "evidence_id", "claim_id", "paper_id", "evidence_level", "stance", "status", "locator",
})
_MATRIX_EVIDENCE_OPTIONAL_KEYS = frozenset({"quote_digest"})
_MATRIX_CELL_KEYS = frozenset({"claim_id", "paper_id", "dimension_id", "relation", "evidence_ids"})
_MATRIX_CELL_OPTIONAL_KEYS = frozenset({"summary", "missing_reason"})
MATRIX_MAX_ITEMS = 64


def _matrix_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or MATRIX_ID_RE.fullmatch(value.strip()) is None:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 无效")
    return value.strip()


def _matrix_text(value: Any, field: str, *, required: bool = True, max_chars: int = 4000) -> str:
    if not isinstance(value, str):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 无效")
    text = value.strip()
    if required and not text:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 无效")
    if len(text) > max_chars:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 过长")
    lowered = text.casefold()
    if any(marker in lowered for marker in ("http://", "https://", "ftp://", "www.", "<script", "javascript:")):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", f"{field} 含不安全内容")
    return text


def validate_synthesis_matrix_payload(
    payload: Any,
    context: Mapping[str, Any],
    *,
    plan_version: int | None = None,
) -> dict[str, Any]:
    """Validate a matrix against server-owned dimensions and frozen snapshots.

    ``plan_version`` is supplied by the orchestrator when validating the
    persistence path.  Runtime and restart hydration omit it and use the
    server-provided value in ``context``.  No caller-provided model field is
    repaired: the returned mapping is a validated projection only, while
    callers that persist the original model envelope must keep their existing
    hash and immutability rules.
    """
    if not isinstance(payload, Mapping) or not isinstance(context, Mapping):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix payload/context 无效")
    expected_plan_version = context.get("plan_version") if plan_version is None else plan_version
    if isinstance(expected_plan_version, bool) or not isinstance(expected_plan_version, int):
        raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix plan_version context 无效")
    if payload.get("schema_version") != "evidence-report-v1":
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix schema_version 无效")
    if isinstance(payload.get("plan_version"), bool) or payload.get("plan_version") != expected_plan_version:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix plan_version 不匹配")
    if context.get("schema_version") != "evidence-report-v1" or context.get("plan_version") != expected_plan_version:
        raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix context 不匹配")

    dimensions = context.get("dimensions")
    supplied_dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions or supplied_dimensions != dimensions:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix dimensions 不得偏离已批准范围")
    for dimension in dimensions:
        if not isinstance(dimension, Mapping) or set(dimension) != _MATRIX_DIMENSION_KEYS:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix dimension 合同无效")
        _matrix_id(dimension.get("dimension_id"), "dimension_id")
        _matrix_text(dimension.get("label"), "dimension label", max_chars=500)
        _matrix_text(dimension.get("definition"), "dimension definition", max_chars=2000)
        order = dimension.get("display_order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "dimension order 无效")

    raw_candidates = context.get("candidates")
    raw_allowed = context.get("allowed_paper_ids")
    if not isinstance(raw_candidates, list) or not isinstance(raw_allowed, list) or not raw_candidates:
        raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix snapshot context 缺失")
    allowed_ids = {_matrix_id(value, "allowed_paper_id") for value in raw_allowed}
    snapshots: dict[str, Mapping[str, Any]] = {}
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping):
            raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix snapshot context 无效")
        paper_id = _matrix_id(candidate.get("paper_id"), "paper_id")
        if paper_id in snapshots:
            raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix snapshot candidate 重复")
        snapshot_id = _matrix_id(candidate.get("catalog_snapshot_id"), "catalog_snapshot_id")
        _matrix_text(candidate.get("title"), "snapshot title", max_chars=8000)
        abstract = candidate.get("abstract")
        if abstract is not None:
            _matrix_text(abstract, "snapshot abstract", required=False, max_chars=8000)
        digest = candidate.get("abstract_digest")
        if digest is not None and (
            not isinstance(digest, str) or _MATRIX_HASH_RE.fullmatch(digest.lower()) is None
        ):
            raise EvidenceMatrixError("MATRIX_NOT_READY", "snapshot abstract digest 无效")
        if isinstance(abstract, str) and abstract.strip():
            expected = hashlib.sha256(abstract.encode("utf-8")).hexdigest()
            if digest != expected:
                raise EvidenceMatrixError("MATRIX_NOT_READY", "snapshot abstract digest 不匹配")
        abstract_ref = candidate.get("abstract_ref", f"catalog:{paper_id}")
        if abstract_ref != f"catalog:{paper_id}":
            raise EvidenceMatrixError("MATRIX_NOT_READY", "snapshot abstract ref 不匹配")
        snapshots[paper_id] = {
            "paper_id": paper_id,
            "catalog_snapshot_id": snapshot_id,
            "title": candidate.get("title"),
            "abstract": abstract,
            "abstract_digest": digest,
            "abstract_ref": abstract_ref,
        }
    if set(snapshots) != allowed_ids:
        raise EvidenceMatrixError("MATRIX_NOT_READY", "matrix snapshot allowlist 不完整")

    expected_top = {"schema_version", "plan_version", "dimensions", "claims", "evidence", "cells"}
    if set(payload) != expected_top:
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix 顶层字段无效")
    raw_claims = payload.get("claims")
    raw_evidence = payload.get("evidence")
    raw_cells = payload.get("cells")
    if not isinstance(raw_claims, list) or not isinstance(raw_evidence, list) or not isinstance(raw_cells, list):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claims/evidence/cells 无效")
    if (
        len(raw_claims) > MATRIX_MAX_ITEMS
        or len(raw_evidence) > MATRIX_MAX_ITEMS
        or len(raw_cells) > MATRIX_MAX_ITEMS
    ):
        raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix 列表过长")

    claims: dict[str, Mapping[str, Any]] = {}
    for raw in raw_claims:
        if not isinstance(raw, Mapping) or set(raw) != _MATRIX_CLAIM_KEYS:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claim 合同无效")
        claim_id = _matrix_id(raw.get("claim_id"), "claim_id")
        if claim_id in claims:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claim 重复")
        _matrix_text(raw.get("topic"), "claim topic", max_chars=1000)
        _matrix_text(raw.get("statement"), "claim statement", max_chars=4000)
        if (
            not isinstance(raw.get("confidence"), str)
            or raw.get("confidence") not in {"low", "medium", "high"}
            or not isinstance(raw.get("status"), str)
            or raw.get("status") not in {"supported", "contested", "unresolved"}
        ):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claim 枚举无效")
        evidence_ids = raw.get("evidence_ids")
        if not isinstance(evidence_ids, list) or any(not isinstance(value, str) for value in evidence_ids):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claim evidence_ids 无效")
        clean_evidence_ids = [_matrix_id(value, "claim evidence_id") for value in evidence_ids]
        if len(set(clean_evidence_ids)) != len(clean_evidence_ids):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix claim evidence_ids 重复")
        if raw.get("status") != "unresolved" and not clean_evidence_ids:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "有结论的 claim 必须有 evidence")
        claims[claim_id] = {**raw, "claim_id": claim_id, "evidence_ids": clean_evidence_ids}

    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    supported_claim = False
    for raw in raw_evidence:
        if not isinstance(raw, Mapping) or not set(raw).issubset(_MATRIX_EVIDENCE_KEYS | _MATRIX_EVIDENCE_OPTIONAL_KEYS) or not _MATRIX_EVIDENCE_KEYS.issubset(raw):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix evidence 合同无效")
        evidence_id = _matrix_id(raw.get("evidence_id"), "evidence_id")
        if evidence_id in evidence_by_id:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix evidence 重复")
        claim_id = _matrix_id(raw.get("claim_id"), "evidence claim_id")
        paper_id = _matrix_id(raw.get("paper_id"), "evidence paper_id")
        if claim_id not in claims or paper_id not in snapshots:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix evidence 归属无效")
        level = raw.get("evidence_level")
        stance = raw.get("stance")
        status = raw.get("status")
        if (
            not isinstance(level, str)
            or level not in {"catalog", "abstract"}
            or not isinstance(stance, str)
            or stance not in {"supports", "contradicts", "contextual"}
            or not isinstance(status, str)
            or status != "available"
        ):
            raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "matrix evidence level/stance/status 无效")
        if level == "catalog" and stance != "contextual":
            raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "catalog evidence 只能作为 contextual")
        _matrix_text(raw.get("quote_digest", ""), "evidence quote_digest", required=False, max_chars=4000)
        locator = raw.get("locator")
        if not isinstance(locator, Mapping):
            raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "matrix evidence locator 无效")
        snapshot = snapshots[paper_id]
        if locator.get("catalog_snapshot_id") != snapshot["catalog_snapshot_id"]:
            raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "matrix evidence snapshot 不匹配")
        if level == "catalog":
            if set(locator) != {"catalog_snapshot_id"}:
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "catalog locator 字段无效")
        else:
            if set(locator) != {"catalog_snapshot_id", "abstract_ref", "abstract_digest"}:
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "abstract locator 字段无效")
            abstract = snapshot.get("abstract")
            digest = snapshot.get("abstract_digest")
            if not isinstance(abstract, str) or not abstract.strip() or not isinstance(digest, str):
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "abstract snapshot 缺失")
            if locator.get("abstract_ref") != f"catalog:{paper_id}" or locator.get("abstract_digest") != digest:
                raise EvidenceMatrixError("EVIDENCE_LOCATOR_INVALID", "abstract locator 不匹配")
        evidence_by_id[evidence_id] = {**raw, "evidence_id": evidence_id}
        if stance == "supports" and any(
            claim.get("claim_id") == claim_id and claim.get("status") == "supported" for claim in claims.values()
        ):
            supported_claim = True

    for claim in claims.values():
        for evidence_id in claim["evidence_ids"]:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None or evidence["claim_id"] != claim["claim_id"]:
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "claim 引用的 evidence 不匹配")
        if claim["status"] == "supported" and not any(
            evidence_by_id[evidence_id]["stance"] == "supports" for evidence_id in claim["evidence_ids"]
        ):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "supported claim 缺少支持性 evidence")
    if not supported_claim:
        raise EvidenceMatrixError("EVIDENCE_INSUFFICIENT", "matrix 缺少可验证 supported claim")

    dimension_ids = {item["dimension_id"] for item in dimensions}
    for raw in raw_cells:
        if not isinstance(raw, Mapping) or not set(raw).issubset(_MATRIX_CELL_KEYS | _MATRIX_CELL_OPTIONAL_KEYS) or not _MATRIX_CELL_KEYS.issubset(raw):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix cell 合同无效")
        claim_id = _matrix_id(raw.get("claim_id"), "cell claim_id")
        paper_id = _matrix_id(raw.get("paper_id"), "cell paper_id")
        dimension_id = _matrix_id(raw.get("dimension_id"), "cell dimension_id")
        relation = raw.get("relation")
        evidence_ids = raw.get("evidence_ids")
        if claim_id not in claims or paper_id not in snapshots or dimension_id not in dimension_ids:
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix cell 归属无效")
        if (
            not isinstance(relation, str)
            or relation not in {"supports", "contradicts", "contextual", "missing"}
            or not isinstance(evidence_ids, list)
        ):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix cell relation/evidence_ids 无效")
        if any(not isinstance(value, str) for value in evidence_ids):
            raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "matrix cell evidence_ids 无效")
        if relation == "missing":
            if evidence_ids or not isinstance(raw.get("missing_reason"), str) or not raw["missing_reason"].strip():
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "missing cell 必须说明原因且无 evidence")
        else:
            if not evidence_ids:
                raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "非 missing cell 必须有 evidence")
            for evidence_id in evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None or evidence["claim_id"] != claim_id or evidence["paper_id"] != paper_id or evidence["stance"] != relation:
                    raise EvidenceMatrixError("REPORT_SCHEMA_INVALID", "cell evidence 不匹配")
        _matrix_text(raw.get("summary", ""), "cell summary", required=False, max_chars=4000)
        if raw.get("missing_reason") is not None:
            _matrix_text(raw.get("missing_reason"), "cell missing_reason", required=False, max_chars=1000)

    return {
        "schema_version": "evidence-report-v1",
        "plan_version": int(expected_plan_version),
        "dimensions": [dict(item) for item in dimensions],
        "claims": [dict(item) for item in claims.values()],
        "evidence": [dict(item) for item in evidence_by_id.values()],
        "cells": [dict(item) for item in raw_cells],
    }


__all__ = ["MATRIX_ID_RE", "MATRIX_MAX_ITEMS", "validate_synthesis_matrix_payload"]
