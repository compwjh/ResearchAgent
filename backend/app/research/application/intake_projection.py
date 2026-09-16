"""Durable, UI-safe projection for conversational research Intake results."""

from __future__ import annotations

import json


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


__all__ = [
    "build_intake_projection",
    "persist_intake_projection",
    "finalize_intake_message",
]
