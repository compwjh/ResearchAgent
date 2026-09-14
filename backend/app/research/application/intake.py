"""Conversation-layer Deep Research intake.

This module is deliberately a small coordinator: it discovers and activates the
registered Skill, persists the Intake projection, and never creates a
ResearchTask or AgentRun.  The ResearchStore remains the sole research-store
writer and MemoryRepository remains the sole conversation-store writer.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.app.research.domain.contracts import SESSION_TERMINAL
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import (
    ResearchSessionActiveConflict,
)

DEEP_RESEARCH_SKILL = "deep-research-orchestration"
BLOCKING_FIELDS = ("topic", "objective", "time_range")
DEFAULT_FIELDS: dict[str, Any] = {
    "language": "zh",
    "sources": ["usenix"],
    "depth": "balanced",
    "output": "markdown",
    "citations": "inline",
    "constraints": [],
}

ACTIVATE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {"skill_name": {"type": "string"}},
    "required": ["skill_name"],
    "additionalProperties": False,
}
ACTIVATE_SKILL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "object"},
        "schema_version": {"type": "string"},
    },
    "required": ["skill", "schema_version"],
}
BEGIN_RESEARCH_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "conversation_id": {"type": "string"},
        "message_id": {"type": "string"},
        "fields": {"type": "object"},
    },
    "required": ["conversation_id", "message_id", "fields"],
    "additionalProperties": False,
}
BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "research_session_id": {"type": "string"},
        "intake_draft_id": {"type": "string"},
        "fields": {"type": "array"},
        "missing": {"type": "array"},
    },
    "required": ["research_session_id", "intake_draft_id", "fields", "missing"],
}
REGISTERED_CAPABILITIES = {
    "activate_skill": {
        "input_schema": ACTIVATE_SKILL_SCHEMA,
        "output_schema": ACTIVATE_SKILL_OUTPUT_SCHEMA,
    },
    "begin_research_intake": {
        "input_schema": BEGIN_RESEARCH_INTAKE_SCHEMA,
        "output_schema": BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA,
    },
}


@dataclass
class IntakeResult:
    status: str
    session: ResearchSession | None = None
    fields: list[IntakeField] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    activation: dict[str, Any] | None = None
    choices: list[dict[str, str]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    question: str | None = None


class ResearchIntakeCoordinator:
    """Classify a turn and maintain one resumable Intake per conversation."""

    def __init__(self, store, memory_repository, skill_registry, tool_registry=None) -> None:
        self.store = store
        self.memory_repository = memory_repository
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry

    @staticmethod
    def classify(message: str) -> str:
        text = (message or "").strip().lower()
        explicit = (
            "深度研究" in text
            or "deep research" in text
            or "研究报告" in text
            or bool(re.search(r"(?:帮我|请|请帮我).{0,12}(?:研究|分析).{2,}", text))
        )
        if explicit:
            return "explicit"
        if any(token in text for token in ("查一下", "查查", "研究一下", "搜一下")):
            return "ambiguous"
        return "ordinary"

    def activate_skill(self, skill_name: str = DEEP_RESEARCH_SKILL) -> dict[str, Any]:
        """Perform the summary → enabled check → full body activation gate."""
        if skill_name != DEEP_RESEARCH_SKILL:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "仅允许激活 Deep Research Skill"},
            }
        summary = next(
            (item for item in self.skill_registry.list_skills() if item.name == skill_name),
            None,
        )
        if summary is None:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill 不存在"},
            }
        if not summary.enabled:
            return {
                "ok": False,
                "error": {"code": "SKILL_DISABLED", "message": "Deep Research Skill 已禁用"},
            }
        detail = self.skill_registry.get_skill(skill_name)
        if detail is None:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill 正文不可用"},
            }
        declared_tools = tuple(detail.tools)
        if self.tool_registry is not None:
            for tool_name in declared_tools:
                tool = self.tool_registry.get_tool(tool_name)
                if tool is None or not tool.enabled:
                    return {
                        "ok": False,
                        "error": {
                            "code": "CAPABILITY_NOT_AUTHORIZED",
                            "message": f"Skill 声明的 Tool 不可用：{tool_name}",
                        },
                    }
        elif declared_tools:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill Tool Registry 不可用"},
            }
        content_hash = hashlib.sha256(detail.body.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "skill": {
                "name": detail.name,
                "description": detail.description,
                "tools": list(detail.tools),
                "body": detail.body,
                "schema_version": "1",
                "skill_id": detail.name,
                "version": "1",
                "content_hash": content_hash,
            },
            "schema_version": "1",
        }

    def begin_research_intake(
        self,
        conversation_id: str,
        owner_id: str,
        message_id: str,
        fields: dict[str, Any] | None = None,
    ) -> IntakeResult:
        """Explicit capability entry point used by a conversation Agent.

        ``handle_message`` is the HTTP-facing classifier; this method is the
        structured capability it delegates to and is intentionally limited to
        Session/Draft persistence.
        """
        active = self._active_session(conversation_id, owner_id)
        if active is not None:
            return self._active_conflict(active)
        activation = self.activate_skill()
        if not activation["ok"]:
            return IntakeResult(status="error", error=activation["error"])
        session = ResearchSession(
            research_session_id=uuid.uuid4().hex,
            owner_id=owner_id,
            conversation_id=conversation_id,
            trigger_message_id=message_id,
            intake_draft_id=uuid.uuid4().hex,
            status="intake_pending",
        )
        try:
            session = self.store.create_session(session, memory_repository=self.memory_repository)
        except ResearchSessionActiveConflict:
            return self._active_conflict(self._active_session(conversation_id, owner_id))
        self._persist_fields(session, fields or {}, message_id, owner_id)
        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        missing = [name for name in BLOCKING_FIELDS if not self._has_value(saved, name)]
        if not missing:
            self.store.update_intake_status(session.intake_draft_id, owner_id, "complete")
        return IntakeResult(
            status="intake",
            session=session,
            fields=saved,
            missing=missing,
            activation=activation,
            question=self._question(missing),
        )

    def handle_message(
        self, conversation_id: str, owner_id: str, message_id: str, message: str
    ) -> IntakeResult:
        classification = self.classify(message)
        active = self._active_session(conversation_id, owner_id)
        if active is None and classification == "ordinary":
            return IntakeResult(status="ordinary")
        if active is None and classification == "ambiguous":
            return IntakeResult(
                status="clarification",
                question="你是想让我进行深度研究，还是只查找一条信息？请说明研究主题、目标和时间范围。",
            )

        # A second explicit research request in the same conversation is a
        # new-intent attempt, not an Intake answer.  Preserve the active
        # projection and return the product's three explicit choices.
        if active is not None and classification == "explicit" and message_id != active.trigger_message_id:
            return self._active_conflict(active)

        activation = self.activate_skill()
        if not activation["ok"]:
            return IntakeResult(status="error", error=activation["error"])

        if active is None:
            fields = self._extract_fields(message)
            session = ResearchSession(
                research_session_id=uuid.uuid4().hex,
                owner_id=owner_id,
                conversation_id=conversation_id,
                trigger_message_id=message_id,
                intake_draft_id=uuid.uuid4().hex,
                status="intake_pending",
            )
            try:
                session = self.store.create_session(session, memory_repository=self.memory_repository)
            except ResearchSessionActiveConflict:
                active = self._active_session(conversation_id, owner_id)
                return self._active_conflict(active)
            self._persist_fields(session, fields, message_id, owner_id)
        else:
            session = active
            # Replaying the trigger message returns the durable projection and
            # does not create another session or rewrite field provenance.
            if message_id != session.trigger_message_id:
                self._persist_fields(session, self._extract_follow_up(session, message), message_id, owner_id)

        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        missing = [name for name in BLOCKING_FIELDS if not self._has_value(saved, name)]
        if not missing:
            draft = self.store.get_intake_draft(session.research_session_id, owner_id)
            if draft is not None and draft.status == "collecting":
                self.store.update_intake_status(draft.intake_draft_id, owner_id, "complete")
        return IntakeResult(
            status="intake",
            session=session,
            fields=saved,
            missing=missing,
            activation=activation,
            question=self._question(missing),
        )

    def _active_session(self, conversation_id: str, owner_id: str) -> ResearchSession | None:
        finder = getattr(self.store, "get_active_session", None)
        if finder is not None:
            return finder(conversation_id, owner_id)
        sessions = self.store.list_sessions(owner_id)
        return next(
            (
                item
                for item in sessions
                if item.conversation_id == conversation_id and item.status not in SESSION_TERMINAL
            ),
            None,
        )

    @staticmethod
    def _active_conflict(session: ResearchSession | None) -> IntakeResult:
        return IntakeResult(
            status="active_conflict",
            session=session,
            choices=[
                {"id": "modify_current", "label": "修改当前研究"},
                {"id": "cancel_then_new", "label": "取消后新建"},
                {"id": "new_conversation", "label": "在新会话研究"},
            ],
            error={
                "code": "RESEARCH_SESSION_ACTIVE_CONFLICT",
                "message": "当前会话已有进行中的研究 Intake",
                "retryable": False,
            },
        )

    def _persist_fields(self, session, values: dict[str, Any], message_id: str, owner_id: str) -> None:
        existing = {item.field_name: item for item in self.store.list_intake_fields(session.intake_draft_id, owner_id)}
        for name, value in {**DEFAULT_FIELDS, **values}.items():
            if name in existing and existing[name].updated_by_message_id == message_id:
                continue
            source = "user_explicit" if name in values else "system_default"
            confidence = 1.0 if source == "user_explicit" else 1.0
            confirmation = "confirmed" if source == "user_explicit" else "not_required"
            self.store.upsert_intake_field(
                IntakeField(
                    intake_draft_id=session.intake_draft_id,
                    field_name=name,
                    value_json=json.dumps(value, ensure_ascii=False),
                    source=source,
                    confidence=confidence,
                    confirmation_status=confirmation,
                    updated_by_message_id=message_id,
                    updated_at="",
                ),
                owner_id,
            )

    @staticmethod
    def _extract_fields(message: str) -> dict[str, Any]:
        text = (message or "").strip()
        values: dict[str, Any] = {}
        topic = ResearchIntakeCoordinator._capture(text, r"主题(?:是|为)[:：]?(.+?)(?:，|,|。|；|;|$)")
        if topic is None:
            topic = ResearchIntakeCoordinator._capture(text, r"关于\s*(.+?)(?:的深度研究|进行深度研究|研究|，|,|。|$)")
        if topic is None:
            topic = ResearchIntakeCoordinator._capture(text, r"(?:^|[，,。；;])研究\s*(.+?)(?:，|,|。|；|;|$)")
        if topic:
            values["topic"] = topic.strip()
        objective = ResearchIntakeCoordinator._capture(text, r"目标(?:是|为)[:：]?(.+?)(?:，|,|。|；|;|$)")
        if objective is None:
            objective = ResearchIntakeCoordinator._capture(text, r"(?:总结|分析|梳理)(.{2,}?)(?:，|,|。|；|;|$)")
        if objective:
            values["objective"] = objective.strip()
        years = re.search(r"(20\d{2})\s*(?:-|–|—|~|至|到)\s*(20\d{2})", text)
        if years:
            values["time_range"] = {"from": int(years.group(1)), "to": int(years.group(2))}
        return values

    def _extract_follow_up(self, session: ResearchSession, message: str) -> dict[str, Any]:
        values = self._extract_fields(message)
        saved = {item.field_name for item in self.store.list_intake_fields(session.intake_draft_id, session.owner_id)}
        missing = [name for name in BLOCKING_FIELDS if name not in saved]
        plain = (message or "").strip()
        if len(missing) == 1 and plain and missing[0] not in values:
            values[missing[0]] = plain
        return values

    @staticmethod
    def _capture(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _has_value(fields: list[IntakeField], name: str) -> bool:
        return any(item.field_name == name and item.value_json not in ("", "null", "[]") for item in fields)

    @staticmethod
    def _question(missing: list[str]) -> str | None:
        labels = {"topic": "研究主题", "objective": "研究目标", "time_range": "时间范围"}
        return "请补充：" + "、".join(labels[item] for item in missing) if missing else None


__all__ = [
    "ACTIVATE_SKILL_SCHEMA",
    "ACTIVATE_SKILL_OUTPUT_SCHEMA",
    "BEGIN_RESEARCH_INTAKE_SCHEMA",
    "BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA",
    "REGISTERED_CAPABILITIES",
    "BLOCKING_FIELDS",
    "ResearchIntakeCoordinator",
    "IntakeResult",
]
