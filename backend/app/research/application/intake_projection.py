"""Durable, UI-safe projection for conversational research Intake results."""

from __future__ import annotations

import json


def build_plan_projection(plan_result: dict | None) -> dict | None:
    """Return only the fields needed to restore a Session plan card."""
    if not isinstance(plan_result, dict):
        return None
    plan = plan_result.get("plan")
    if not isinstance(plan, dict):
        return None
    safe_plan = {
        key: plan.get(key)
        for key in (
            "research_session_id", "version", "schema_version", "output_hash",
            "objective", "scope_json", "work_items_json", "capabilities_json",
            "budget_json", "report_structure_json", "safety_summary_json", "status",
        )
        if key in plan
    }
    approval = plan_result.get("approval")
    safe_approval = None
    if isinstance(approval, dict):
        safe_approval = {
            key: approval.get(key)
            for key in ("approval_request_id", "research_session_id", "kind", "subject_id", "subject_version", "status")
            if key in approval
        }
    return {
        "schema_version": "task04-plan-v1",
        "research_session_id": plan_result.get("research_session_id") or safe_plan.get("research_session_id"),
        "status": plan_result.get("status"),
        "subject_version": plan_result.get("subject_version") or safe_plan.get("version"),
        "plan": safe_plan,
        "approval": safe_approval,
    }


def build_intake_projection(result) -> dict:
    """Build a bounded projection without persisting a Skill body or prompt."""
    fields = [
        {
            "field_name": item.field_name,
            "value_json": item.value_json,
            "source": item.source,
            "confidence": item.confidence,
            "confirmation_status": item.confirmation_status,
            "message_id": item.updated_by_message_id,
        }
        for item in result.fields
    ]
    activation_skill = (result.activation or {}).get("skill") or {}
    skill = None
    if activation_skill:
        skill = {
            key: activation_skill.get(key)
            for key in (
                "skill_id",
                "name",
                "description",
                "version",
                "content_hash",
                "tools",
            )
        }
    session = result.session.to_dict() if result.session else None
    if session:
        session = {
            "research_session_id": session.get("research_session_id"),
            "intake_draft_id": session.get("intake_draft_id"),
            "status": session.get("status"),
        }
    return {
        "schema_version": "task03-intake-v1",
        "status": result.status,
        "fields": fields,
        "missing": list(result.missing),
        "choices": list(result.choices),
        "question": result.question,
        "skill": skill,
        "research_session": session,
    }


def persist_intake_projection(repo, assistant_message, result) -> dict:
    """Persist the same safe projection used by streaming and history reads."""
    projection = build_intake_projection(result)
    status = "failed" if result.status == "error" else "completed"
    session = projection.get("research_session") or {}
    repo.create_processing_step(
        assistant_message.message_id,
        "research_intake",
        status,
        "研究 Intake 已保存" if status == "completed" else "研究 Intake 失败",
        label="研究 Intake",
        node_key=f"research-intake:{assistant_message.message_id}",
        detail_json=json.dumps(projection, ensure_ascii=False, sort_keys=True),
        research_session_id=session.get("research_session_id"),
    )
    return projection


def finalize_intake_message(repo, assistant_message, result) -> dict:
    """Persist Intake and close an assistant placeholder created outside SSE."""
    projection = persist_intake_projection(repo, assistant_message, result)
    failed = result.status == "error"
    content = (
        (result.error or {}).get("message", "研究 Intake 失败")
        if failed
        else result.question or "研究 Intake 已保存，参数齐全后将生成计划。"
    )
    repo.update_message(
        assistant_message.message_id,
        getattr(assistant_message, "owner_id", "local-user"),
        content=content,
        status="failed" if failed else "completed",
    )
    return projection


def persist_plan_projection(repo, assistant_message, plan_result: dict | None) -> dict | None:
    """Persist a safe plan projection alongside the Intake processing step."""
    projection = build_plan_projection(plan_result)
    if projection is None:
        return None
    # Replaying the idempotent recovery endpoint must not append an unbounded
    # series of identical processing rows to the same historical message.
    try:
        existing = repo.list_processing_steps(assistant_message.message_id, getattr(assistant_message, "owner_id", "local-user"))
    except Exception:
        existing = []
    if any(
        step.kind == "research_plan"
        and step.node_key == f"research-plan:{assistant_message.message_id}"
        for step in existing
    ):
        return projection
    repo.create_processing_step(
        assistant_message.message_id,
        "research_plan",
        "completed",
        "研究计划已生成，等待用户批准",
        label="研究计划",
        node_key=f"research-plan:{assistant_message.message_id}",
        detail_json=json.dumps(projection, ensure_ascii=False, sort_keys=True),
        research_session_id=projection.get("research_session_id"),
    )
    return projection


__all__ = [
    "build_intake_projection",
    "build_plan_projection",
    "persist_intake_projection",
    "finalize_intake_message",
    "persist_plan_projection",
]
