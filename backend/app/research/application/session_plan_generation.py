"""Generate the first Session plan from a completed Intake.

The conversation Intake coordinator intentionally stops at the durable Intake
boundary.  This module is the small, idempotent seam that turns a completed
draft into the versioned plan/approval contract owned by ``PlanApprovalService``.
It uses the existing deterministic ``Planner`` for the first plan; research
execution still waits for the user's approval.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from backend.app.research.application.plan_authoring import plan_output_hash
from backend.app.research.application.planner import Planner
from backend.app.research.domain.contracts import (
    DEFAULT_TARGET_PAPER_COUNT,
    TARGET_PAPER_COUNT_RANGE,
)

_DEFAULT_CAPABILITIES = (
    {"skill": "usenix-catalog-orchestration", "tools": ["search_paper_catalog", "fetch_paper_detail"]},
    {"skill": "research-paper-evaluation", "tools": []},
    {"skill": "research-coverage-review", "tools": []},
    {"skill": "research-report-synthesis", "tools": []},
)

# 契约 2.6：4 块计划字段改由 Intake 的 4 个简单字符串枚举 profile 驱动。
# 所有取值都先过白名单，未知 / 恶意文本一律回落到原有硬编码默认值——既保证
# 老会话结果逐字不变，也避免 custom 输入把 URL 字符串带进 plan 触发护栏。
# 注意 plan_authoring._validate_bounded_sections 对 budget / report_structure /
# safe_summary 有严格「键名」白名单，因此只改已有键的「值」，绝不新增键名。
_CAPABILITY_PROFILE_INDICES = {
    "full": (0, 1, 2, 3),
    "search_eval": (0, 1, 3),
    "catalog_only": (0,),
}
_BUDGET_PROFILE_SECONDS = {"fast": 600, "balanced": 1500, "deep": 3600}
_REPORT_PROFILE_SECTIONS = {
    "standard": ["研究问题", "方法与来源", "主要发现", "局限与后续工作"],
    "deep": ["研究问题", "方法与来源", "证据评估", "主要发现", "讨论", "局限与后续工作", "附录"],
    "brief": ["核心发现", "结论"],
}
_OUTPUT_FORMATS = frozenset({"markdown", "html"})
_CITATION_STYLES = frozenset({"inline", "footnotes", "title_only"})
_LEGACY_DECISION = "已根据确认的 Intake 生成首版计划，等待用户批准"
_LEGACY_NOTES = "首版计划使用确定性 Planner；批准后才会创建 ResearchTask 并执行搜索。"
_DEGRADATION_TEXT = {
    "balanced": (_LEGACY_DECISION, _LEGACY_NOTES),
    "conservative": (
        "保守降级：已根据确认的 Intake 生成首版计划，等待用户批准",
        "保守策略：来源不足时优先缩减研究范围，不降低证据门槛；批准后才会创建 ResearchTask 并执行搜索。",
    ),
    "flexible": (
        "弹性降级：已根据确认的 Intake 生成首版计划，等待用户批准",
        "弹性策略：来源不足时允许替换等价来源继续推进；批准后才会创建 ResearchTask 并执行搜索。",
    ),
}


def _enum_or_default(value: Any, allowed, default: str) -> str:
    """Whitelist one Intake enum value; unknown values fall back to the default."""
    return value if isinstance(value, str) and value in allowed else default

# Supported counts are bounded to the number of digits needed by the public
# 1..20 contract.  Longer tokens deliberately become an unresolved marker and
# follow the existing clarification path instead of reaching ``int()``.
_COUNT_NUMBER = r"(?P<count>[+-]?\d{1,2})"
_COUNT_CONTEXT = r"(?=\s*(?:篇(?:\s*(?:论文|方法|候选))?|papers?\b|[，,。；;.]|$))"
_COUNT_PATTERNS = (
    (
        "max",
        re.compile(
            rf"(?:max(?:imum)?[_ -]?paper[_ -]?count|最多|至多|不超过|上限(?:为|是)?|at\s+most|no\s+more\s+than)"
            rf"\s*[:：=]?\s*(?:(?:需要|要)\s*)?(?:选择|选取|选|保留|为|是|select(?:ing)?|choose)?\s*{_COUNT_NUMBER}{_COUNT_CONTEXT}",
            re.IGNORECASE,
        ),
    ),
    (
        "min",
        re.compile(
            rf"(?:min(?:imum)?[_ -]?paper[_ -]?count|至少|不少于|最少|下限(?:为|是)?|at\s+least|no\s+fewer\s+than)"
            rf"\s*[:：=]?\s*(?:(?:需要|要)\s*)?(?:选择|选取|选|保留|比较|为|是|select(?:ing)?|choose)?\s*{_COUNT_NUMBER}{_COUNT_CONTEXT}",
            re.IGNORECASE,
        ),
    ),
    (
        "target",
        re.compile(
            rf"(?:target[_ -]?paper[_ -]?count|目标(?:论文)?(?:数|数量|篇数))"
            rf"\s*[:：=]?\s*(?:为|是)?\s*{_COUNT_NUMBER}{_COUNT_CONTEXT}",
            re.IGNORECASE,
        ),
    ),
)
_COUNT_WORD_VALUE = (
    r"(?:[零〇一二三四五六七八九十百千万两几多少若干数]+(?:来|多)?|"
    r"a\s+(?:few|couple(?:\s+of)?)|"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"few|several|some|many|any))"
)
_COUNT_QUANTITY_VALUE = rf"(?:[+-]?\d+|{_COUNT_WORD_VALUE})"
_COUNT_QUANTITY_MARKER = (
    r"(?:最多|至多|不超过|上限|至少|不少于|最少|下限|"
    r"at\s+most|no\s+more\s+than|at\s+least|no\s+fewer\s+than)"
    r"(?=\s*[:：=]?\s*(?:(?:需要|要)\s*)?(?:(?:选择|选取|选|保留|比较|为|是|select(?:ing)?|choose)\s*)?"
    rf"{_COUNT_QUANTITY_VALUE}\s*(?:篇(?:\s*(?:论文|方法|候选))?|论文|papers?\b))"
)
_COUNT_MARKER_RE = re.compile(
    r"(?:max(?:imum)?[_ -]?paper[_ -]?count|min(?:imum)?[_ -]?paper[_ -]?count|"
    r"target[_ -]?paper[_ -]?count|paper_count_constraint|目标(?:论文)?(?:数|数量|篇数)|"
    rf"{_COUNT_QUANTITY_MARKER})",
    re.IGNORECASE,
)


def _decode(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _constraint_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(value)
    return [encoded] if encoded.strip() else []


def extract_paper_count_constraints(text: str) -> list[str]:
    """Extract explicit paper-count language into the existing constraints list.

    The returned values are deliberately plain, bounded strings so Intake can
    persist them without adding a public field.  An unparseable count marker is
    retained as a clarification marker; it must never silently fall back to the
    quality-profile default.
    """
    text = (text or "").strip()
    matches: list[tuple[int, str, int, int]] = []
    for kind, pattern in _COUNT_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), kind, int(match.group("count")), match.end()))
    values: list[str] = []
    for _start, kind, count, _end in sorted(matches, key=lambda item: item[0]):
        value = f"{kind}_paper_count:{count}"
        if value not in values:
            values.append(value)
    unresolved = any(
        not any(start <= marker.start() < end for start, _kind, _count, end in matches)
        for marker in _COUNT_MARKER_RE.finditer(text)
    )
    if unresolved and "paper_count_constraint:unparsed" not in values:
        values.append("paper_count_constraint:unparsed")
    return values


def resolve_paper_count_constraints(value: Any, default: int = DEFAULT_TARGET_PAPER_COUNT) -> dict[str, Any]:
    """Resolve count constraints without confusing a minimum with a maximum."""
    low, high = TARGET_PAPER_COUNT_RANGE
    max_values: list[int] = []
    min_values: list[int] = []
    target_values: list[int] = []
    has_marker = False
    unresolved = False
    for item in _constraint_values(value):
        matches = []
        for kind, pattern in _COUNT_PATTERNS:
            matches.extend((kind, match) for match in pattern.finditer(item))
        markers = list(_COUNT_MARKER_RE.finditer(item))
        if markers:
            has_marker = True
        if not matches and markers:
            unresolved = True
        for kind, match in matches:
            count = int(match.group("count"))
            if kind == "max":
                max_values.append(count)
            elif kind == "min":
                min_values.append(count)
            else:
                target_values.append(count)
    reason = None
    if any(count < low or count > high for count in (*max_values, *min_values, *target_values)):
        reason = "paper count is outside the supported range"
    elif unresolved:
        reason = "paper count constraint is not parseable"
    elif len(set(target_values)) > 1:
        reason = "target paper counts conflict"
    maximum = min(max_values) if max_values else None
    minimum = max(min_values) if min_values else None
    target = target_values[0] if target_values else None
    if reason is None and minimum is not None and maximum is not None and minimum > maximum:
        reason = "minimum paper count exceeds maximum"
    if reason is None and target is not None and minimum is not None and target < minimum:
        reason = "target paper count is below minimum"
    if reason is None and target is not None and maximum is not None and target > maximum:
        reason = "target paper count exceeds maximum"
    try:
        fallback = max(low, min(int(default), high))
    except (TypeError, ValueError):
        fallback = DEFAULT_TARGET_PAPER_COUNT
    if target is not None:
        resolved = target
    else:
        # A maximum is a hard cap, not an implicit target.  Start from the
        # profile default and clamp it to any explicit bounds.
        resolved = fallback
        if minimum is not None:
            resolved = max(resolved, minimum)
        if maximum is not None:
            resolved = min(resolved, maximum)
    return {
        "valid": reason is None,
        "has_count_constraint": has_marker,
        "reason": reason,
        "max_count": maximum,
        "min_count": minimum,
        "target_count": target,
        "resolved_count": resolved,
    }


def _target_count(value: Any, default: int = DEFAULT_TARGET_PAPER_COUNT) -> int:
    resolution = resolve_paper_count_constraints(value, default=default)
    if not resolution["valid"]:
        raise ValueError(f"paper count constraints require clarification: {resolution['reason']}")
    return int(resolution["resolved_count"])


def build_session_plan_output(store, session, owner_id: str) -> dict[str, Any]:
    """Build a safe, hash-complete ``ResearchPlanOutput`` from Intake fields."""
    fields = {
        item.field_name: _decode(item.value_json)
        for item in store.list_intake_fields(session.intake_draft_id, owner_id)
    }
    topic = str(fields.get("topic") or "").strip()
    objective = str(fields.get("objective") or topic).strip()
    time_range = fields.get("time_range") if isinstance(fields.get("time_range"), dict) else {}
    language = str(fields.get("language") or "zh").strip() or "zh"
    sources = fields.get("sources") if isinstance(fields.get("sources"), list) else ["usenix"]
    sources = [str(item).strip() for item in sources if str(item).strip()][:16] or ["usenix"]
    depth = str(fields.get("depth") or "balanced").strip() or "balanced"
    constraints = fields.get("constraints")
    if isinstance(constraints, str):
        constraints = [constraints] if constraints.strip() else []
    if not isinstance(constraints, list):
        constraints = []
    constraints = [str(item).strip() for item in constraints if str(item).strip()][:32]
    target = _target_count(constraints)
    quality_profile = depth if depth in {"speed", "balanced", "quality"} else "balanced"
    draft = Planner().build_plan(
        goal=objective or "深度研究",
        query_topic=topic or None,
        quality_profile=quality_profile,
        target_paper_count=target,
        language=language,
        source_ids=sources,
        scope=time_range,
    )
    work_items = [dict(item) for item in draft.work_items]
    # Session plan output is capped at three dependency levels.  Keep the
    # coverage check visible, but let synthesis depend directly on evaluation;
    # the runtime can still use the coverage node without creating a fourth
    # level in the public plan contract.
    for item in work_items:
        if item.get("task_type") == "synthesize_preliminary_report":
            item["depends_on"] = [
                dependency for dependency in item.get("depends_on", []) if dependency != "c1"
            ] or ["e1"]
    capability_profile = _enum_or_default(
        fields.get("capability_profile"), _CAPABILITY_PROFILE_INDICES, "full"
    )
    budget_profile = _enum_or_default(
        fields.get("budget_profile"), _BUDGET_PROFILE_SECONDS, "balanced"
    )
    report_profile = _enum_or_default(
        fields.get("report_profile"), _REPORT_PROFILE_SECTIONS, "standard"
    )
    degradation_policy = _enum_or_default(
        fields.get("degradation_policy"), _DEGRADATION_TEXT, "balanced"
    )
    report_format = _enum_or_default(fields.get("output"), _OUTPUT_FORMATS, "markdown")
    citation_style = _enum_or_default(fields.get("citations"), _CITATION_STYLES, "inline")
    selected_capabilities = [
        dict(_DEFAULT_CAPABILITIES[index])
        for index in _CAPABILITY_PROFILE_INDICES[capability_profile]
    ]
    decision, notes = _DEGRADATION_TEXT[degradation_policy]

    payload: dict[str, Any] = {
        "schema_version": "session-plan-v1",
        "plan_version": int(session.current_plan_version or 0) + 1,
        "objective": objective or topic or "深度研究",
        "scope": {
            "facets": list(draft.facets),
            "sources": sources,
            "time_range": {"from": time_range.get("from"), "to": time_range.get("to")},
            "language": language,
            "depth": depth,
            "constraints": constraints,
        },
        "work_items": work_items,
        "capabilities": selected_capabilities,
        "budget": {
            "quality_profile": quality_profile,
            "target_paper_count": draft.target_paper_count,
            "soft_budget_seconds": _BUDGET_PROFILE_SECONDS[budget_profile],
            "language": language,
        },
        "report_structure": {
            "sections": list(_REPORT_PROFILE_SECTIONS[report_profile]),
            "format": report_format,
            "citations": citation_style,
            "language": language,
            "title": "深度研究报告",
        },
        "safe_summary": {
            "decision": decision,
            "notes": notes,
            "constraints": constraints,
            "degraded": [],
        },
        "source_refs": sources,
    }
    payload["output_hash"] = plan_output_hash(payload)
    return payload


def ensure_session_plan(
    store,
    session,
    owner_id: str,
    author_plan: Callable[[str, str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the existing plan or author one exactly once when Intake is complete."""
    existing = store.get_session_plan(session.research_session_id, owner_id)
    if existing is not None:
        approvals = store.list_approvals(session.research_session_id, owner_id, subject_version=existing.version)
        approval = next((item.to_dict() for item in approvals if item.kind == "plan"), None)
        return {
            "research_session_id": session.research_session_id,
            "status": store.get_session(session.research_session_id, owner_id).status,
            "subject_version": existing.version,
            "plan": existing.to_dict(),
            "approval": approval,
        }
    draft = store.get_intake_draft(session.research_session_id, owner_id)
    if draft is None or draft.status != "complete":
        return None
    payload = build_session_plan_output(store, session, owner_id)
    try:
        return author_plan(session.research_session_id, owner_id, payload)
    except Exception:
        # A concurrent author may have won the CAS.  Replay the durable plan
        # instead of surfacing a misleading failure to the user.
        existing = store.get_session_plan(session.research_session_id, owner_id)
        if existing is None:
            raise
        current = store.get_session(session.research_session_id, owner_id)
        approvals = store.list_approvals(session.research_session_id, owner_id, subject_version=existing.version)
        return {
            "research_session_id": session.research_session_id,
            "status": current.status,
            "subject_version": existing.version,
            "plan": existing.to_dict(),
            "approval": next((item.to_dict() for item in approvals if item.kind == "plan"), None),
        }


__all__ = ["build_session_plan_output", "ensure_session_plan"]
