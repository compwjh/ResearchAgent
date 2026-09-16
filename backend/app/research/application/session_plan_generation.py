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


_DEFAULT_CAPABILITIES = (
    {"skill": "usenix-catalog-orchestration", "tools": ["search_paper_catalog", "fetch_paper_detail"]},
    {"skill": "research-paper-evaluation", "tools": []},
    {"skill": "research-coverage-review", "tools": []},
    {"skill": "research-report-synthesis", "tools": []},
)


def _decode(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _target_count(value: Any, default: int = 12) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    match = re.search(r"(?:目标论文数|target[_ -]?paper[_ -]?count)\s*[:：]?\s*(\d+)", text, re.I)
    if not match:
        return default
    return max(1, min(int(match.group(1)), 20))


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
    target = _target_count(fields.get("constraints"))
    quality_profile = depth if depth in {"speed", "balanced", "quality"} else "balanced"
    draft = Planner().build_plan(
        goal=objective or "深度研究",
        quality_profile=quality_profile,
        target_paper_count=target,
        language=language,
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
        "capabilities": [dict(item) for item in _DEFAULT_CAPABILITIES],
        "budget": {
            "quality_profile": quality_profile,
            "target_paper_count": draft.target_paper_count,
            "soft_budget_seconds": 1500,
            "language": language,
        },
        "report_structure": {
            "sections": ["研究问题", "方法与来源", "主要发现", "局限与后续工作"],
            "format": "markdown",
            "citations": "inline",
            "language": language,
            "title": "深度研究报告",
        },
        "safe_summary": {
            "decision": "已根据确认的 Intake 生成首版计划，等待用户批准",
            "notes": "首版计划使用确定性 Planner；批准后才会创建 ResearchTask 并执行搜索。",
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
