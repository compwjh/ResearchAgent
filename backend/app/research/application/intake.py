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

from backend.app.research.application.session_plan_generation import (
    extract_paper_count_constraints,
    resolve_paper_count_constraints,
)
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


# ---------------------------------------------------------------------------
# Intake 意图路由：判断一条进入研究会话的用户消息是
#   (a) 「在回答 Intake 提问」  → 喂给抽取器（既有主流程）
#   (b) 「在提问 / 元问题 / 下命令」 → 走普通对话/命令通道，不喂抽取器
#
# **默认取向（fail-open）**：默认归为 (a)（喂抽取器）。只有当消息被**明确识别**
# 为提问或命令时才归为 (b)。理由（与需求方拍板一致）：宁可偶尔把一句提问当成
# 回答，也绝不让正常填写流程被漏掉；这样不会破坏既有主流程。任何未匹配规则
# 的消息都回落到 (a)。
#
# 实现选择：规则 / 确定性判定，零依赖、可注入、可单测、不加延迟。仓库已有
# ``backend/app/skills/intent.py``（Skill 调用意图）与 ``classify_memory_intent``
# （memory 存储意图），两者服务完全不同的领域、且含 LLM 调用，不适用于本场景；
# 因此此处新增一个独立的规则分类器，并不重复既有 LLM 意图实现（项目红线）。
# ---------------------------------------------------------------------------
_INTENT_QUESTION_END = "？?"
_INTENT_QUESTION_PREFIXES = (
    "哪些", "什么", "怎么", "怎样", "为什么", "为何", "能否", "能不能",
    "可不可以", "有没有", "多少", "何时", "哪个", "哪几个", "谁", "啥",
    "几点", "哪儿", "哪里", "如何", "有哪些", "有什么", "这些是",
)
_INTENT_COMMAND_PREFIXES = (
    "取消", "重来", "重新开始", "重新做", "重新来", "换主题", "换个主题",
    "换个", "不要了", "中止", "退出研究", "结束研究", "结束", "算了",
    "别做", "别再", "先暂停", "暂停", "退出", "停止", "停一下",
)
# 元问题短句：命中即 (b)。覆盖「有哪些研究目标能给我选」「这是什么意思」等。
_INTENT_META_SUBSTRINGS = (
    "能给我选", "给我选", "是什么意思", "什么意思", "刚才填", "之前填",
    "我填的", "填的是", "刚才说的", "之前说的", "有什么区别", "怎么理解",
)
# 礼貌 / 主语前缀：判定「是否以疑问词开头」前先剥掉，避免「我想问…」漏判。
_INTENT_LEADING_POLITE = (
    "请", "那", "你就", "你看", "我想问", "我想知道", "请问", "帮我看看",
    "帮我说说", "我想", "我", "你", "它", "这", "那我们",
)


def classify_intake_intent(message: str) -> str:
    """Return ``"answer"`` (a) or ``"question_or_command"`` (b).

    Default (fail-open) is ``"answer"`` — see module note above.  The logic is
    intentionally regex/keyword based so it is deterministic, dependency-free,
    and unit-testable; a model-backed classifier can be injected instead via
    ``ResearchIntakeCoordinator(intent_classifier=...)`` without touching callers.
    """
    text = (message or "").strip()
    if not text:
        return "answer"
    # (b) 强信号：以问号结尾
    if text[-1] in _INTENT_QUESTION_END:
        return "question_or_command"
    # 剥掉礼貌 / 主语前缀后，若以疑问词开头 → (b)
    head = text
    changed = True
    while changed:
        changed = False
        for prefix in _INTENT_LEADING_POLITE:
            if head.startswith(prefix):
                head = head[len(prefix):]
                changed = True
                break
    if any(head.startswith(q) for q in _INTENT_QUESTION_PREFIXES):
        return "question_or_command"
    # (b) 命令：以命令词开头
    if any(text.startswith(c) for c in _INTENT_COMMAND_PREFIXES):
        return "question_or_command"
    # (b) 元问题短句
    if any(s in text for s in _INTENT_META_SUBSTRINGS):
        return "question_or_command"
    # 其余一律归为 (a)，维持既有填写流程
    return "answer"


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

    def __init__(self, store, memory_repository, skill_registry, tool_registry=None, intent_classifier=None) -> None:
        self.store = store
        self.memory_repository = memory_repository
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        # 意图路由判定器，默认用内置规则分类器；可注入替换（如模型版）便于单测。
        self.intent_classifier = intent_classifier or classify_intake_intent

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
        missing = self._missing_fields(saved)
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
            # ① 收齐即停：draft 已 complete（参数齐全或计划已生成）后，后续用户
            # 消息不再进入抽取器，改为走普通对话/命令通道，避免污染已确认字段。
            draft = self.store.get_intake_draft(session.research_session_id, owner_id)
            if draft is not None and draft.status == "complete":
                return IntakeResult(status="ordinary")
            # Replaying the trigger message returns the durable projection and
            # does not create another session or rewrite field provenance.
            if message_id != session.trigger_message_id:
                # ② 意图判定：默认归为「回答 intake」（喂抽取器）；只有被明确识别为
                # 提问 / 元问题 / 命令时才走普通通道（b），不污染 Intake 字段。
                if self.intent_classifier(message) == "question_or_command":
                    return IntakeResult(status="ordinary")
                self._persist_fields(session, self._extract_follow_up(session, message), message_id, owner_id)

        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        missing = self._missing_fields(saved)
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
        constraints = extract_paper_count_constraints(text)
        if constraints:
            values["constraints"] = constraints
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

    @classmethod
    def _missing_fields(cls, fields: list[IntakeField]) -> list[str]:
        missing = [name for name in BLOCKING_FIELDS if not cls._has_value(fields, name)]
        constraints = next((item for item in fields if item.field_name == "constraints"), None)
        if constraints is not None:
            try:
                value = json.loads(constraints.value_json or "null")
            except (TypeError, ValueError):
                value = None
            resolution = resolve_paper_count_constraints(value)
            if resolution["has_count_constraint"] and not resolution["valid"]:
                missing.append("constraints")
        return missing

    @staticmethod
    def _question(missing: list[str]) -> str | None:
        labels = {
            "topic": "研究主题",
            "objective": "研究目标",
            "time_range": "时间范围",
            "constraints": "论文数量约束",
        }
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
    "classify_intake_intent",
]
