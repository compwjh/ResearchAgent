"""Spec027 Research Task HTTP 接口（Task03 第 5 批：端点骨架）。

分层与复用（路由/校验/错误风格照 `routes_conversations.py`）：
- api 只做 HTTP 语义与参数解析，业务规则一律在 `research.application`：本模块只从
  `research.application.entry`（受控出口）取 `ResearchServiceError`，不 import
  `research.domain` / `research.infrastructure`，也不在模块顶层实例化任何业务对象
  （静态边界规则：一律经 `get_provider` 解析）。
- `owner_id` 统一用既有单用户隔离范式 `backend.app.memory.repository.OWNER_ID`，
  不引入新鉴权（Spec027 §持久化与并发：沿用现有单 OWNER_ID 模型）。
- 计划与 WorkItem 的**只读投影**经 `research_store` provider（与 `research_service`
  同源的缓存工厂 `entry.build_research_store`）；测试可用 `override_provider` 同时
  替换这两个 provider，注入临时目录的 service/store，不碰真实库与网络。

错误出口：
- 服务层错误一律 `ResearchServiceError(code, http_status, message)` → `_error` 返回
  `{"error": {"code", "message"}}` + `exc.http_status`，code 取自 027 冻结词表。
- 仅三类**纯 HTTP 层**输入校验（keyset 游标非法、after_seq / Last-Event-ID 非法、
  按游标重连却发现任务已删除）用 `_api_error`：沿用 api 惯例码，不进入 027 冻结
  词表，因为服务层不产生这些码。
- 会话/项目归属校验（Spec027 §端点与事件接口：POST 失败列含「404 会话/项目」、
  GET 失败列含「404 project」）同用 `_api_error` 返回 404 `CONVERSATION_NOT_FOUND` /
  `PROJECT_NOT_FOUND`：校验查的是**既有 memory repository**（Spec022 会话与项目的
  唯一存储），属 api 组合装配层职责，解析结果再作为参数传给 service，service 层
  不 import memory.repository。
- 该 memory 依赖属**外部依赖**：其故障（库损坏/不可读）与调度装配故障同款返回
  503 `SOURCE_UNAVAILABLE` + 稳定错误体（复用 027 冻结码，不新增码），只记服务端日志，
  不产生裸 500 `{"detail": ...}`（P2-A）。

SSE：`GET /{id}/events` 只推送已持久化的 `safe_payload_json`，不泄露隐藏思维链、
完整 Prompt 或凭据（Spec027 §端点与事件接口 / §用户界面）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.memory.repository import OWNER_ID
from backend.app.platform.bootstrap import get_provider
from backend.app.platform.config import BASE_DIR, KB_DIR
from backend.app.research.application.approval_service import PlanApprovalService, ResearchCommandError
from backend.app.research.application.entry import ResearchServiceError
from backend.app.research.application.intake import ResearchIntakeCoordinator
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_service import ToolRegistryService

router = APIRouter(prefix="/research-tasks", tags=["research-tasks"])
session_router = APIRouter(prefix="/research-sessions", tags=["research-sessions"])
notification_router = APIRouter(prefix="/research-notifications", tags=["research-notifications"])
logger = logging.getLogger(__name__)
_SESSION_CREATE_LOCK = threading.RLock()

# 终态集合：与 `research.domain.contracts.TASK_TERMINAL` 逐字一致。api 只经
# application/entry 依赖 research（不 import domain），故在此显式列出。
_TASK_TERMINAL = frozenset({"partial", "completed", "failed", "cancelled", "interrupted"})

# 任务摘要里 goal 的截断长度（与 service 的 draft 事件摘要一致，不放大段原文）。
_GOAL_EXCERPT_CHARS = 120

# SSE：轮询间隔、心跳间隔（秒）与单批读取上限。
_EVENT_POLL_SECONDS = 0.05
_EVENT_HEARTBEAT_SECONDS = 15.0
_EVENT_BATCH_LIMIT = 200


class ResearchTaskCreateRequest(BaseModel):
    """创建研究任务请求。

    `goal` / `conversation_id` 声明为可空是为了由本模块统一转成 400
    ``PLAN_VALIDATION_FAILED``：若交给 pydantic 必填校验，缺失字段会变成 FastAPI
    默认的 422 ``detail``，破坏 027 稳定错误体契约。
    """

    model_config = ConfigDict(extra="forbid")

    goal: Optional[str] = Field(default=None, max_length=4000)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    project_id: Optional[str] = Field(default=None, max_length=100)
    quality_profile: str = Field(default="balanced", max_length=32)
    target_paper_count: Optional[int] = Field(default=None)
    language: str = Field(default="zh", max_length=16)
    review_plan_first: bool = Field(default=False)


class ResearchTaskFeedbackRequest(BaseModel):
    """计划批准（``action="approve"``）或补充范围（``add_scope``）。"""

    model_config = ConfigDict(extra="forbid")

    action: Optional[str] = Field(default=None, max_length=32)
    add_scope: Optional[str] = Field(default=None, max_length=4000)


class ResearchTaskPatchProjectRequest(BaseModel):
    """移动/解绑项目归属；``project_id`` 为 null 表示解绑（可显式传 null）。"""

    model_config = ConfigDict(extra="forbid")

    project_id: Optional[str] = Field(default=None, max_length=100)


class ResearchSessionCreateRequest(BaseModel):
    """Task02 base schema for the conversational research session boundary."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: Optional[str] = Field(default=None, max_length=100)
    trigger_message_id: Optional[str] = Field(default=None, max_length=100)
    project_id: Optional[str] = Field(default=None, max_length=100)
    intake: dict = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=200)


class ResearchSessionCommandRequest(BaseModel):
    """All button and natural-language approvals use this exact command shape."""

    model_config = ConfigDict(extra="forbid")

    command: Literal[
        "approve_plan", "revise_plan", "cancel_research",
        "approve_capability", "approve_resource_extension", "decline_request",
    ]
    subject_version: int = Field(ge=0)
    scope_json: dict[str, object] = Field(default_factory=dict, max_length=32)
    idempotency_key: str = Field(min_length=1, max_length=200)

    @field_validator("scope_json")
    @classmethod
    def validate_scope(cls, value: dict[str, object]) -> dict[str, object]:
        """Bound the transport shape; registry authorization remains service-side."""
        forbidden = {"shell", "python", "__import__", "eval", "exec"}

        def visit(item: object, depth: int = 0) -> None:
            if depth > 4:
                raise ValueError("scope_json nesting is too deep")
            if isinstance(item, str):
                if len(item) > 2000 or item.lower() in forbidden or item.startswith(("http://", "https://")):
                    raise ValueError("scope_json contains an unsafe value")
            elif isinstance(item, dict):
                if len(item) > 32:
                    raise ValueError("scope_json has too many keys")
                for key, child in item.items():
                    if "url" in str(key).lower() or str(key).lower() in forbidden:
                        raise ValueError("scope_json contains an unsafe key")
                    visit(child, depth + 1)
            elif isinstance(item, list):
                if len(item) > 32:
                    raise ValueError("scope_json list is too large")
                for child in item:
                    visit(child, depth + 1)

        visit(value)
        return value


def _service():
    """解析 research_service provider；顶层不实例化任何业务对象（静态边界规则）。"""
    return get_provider("research_service")


def _store():
    """解析 research_store provider（只读投影：当前计划 / 取消计数）。"""
    return get_provider("research_store")


def _approval_service() -> PlanApprovalService:
    state_path = KB_DIR / "skill-state.json"
    return PlanApprovalService(
        store=_store(),
        memory_repository=_memory(),
        skill_registry=SkillRegistryService(BASE_DIR / ".agents" / "skills", state_path),
        tool_registry=ToolRegistryService(build_default_tool_registry(), state_path),
        # Approval materialization and execution share the same composed
        # ResearchService/Orchestrator runtime; no second dispatcher is
        # created at the Session command boundary.
        research_service=_service(),
    )


def _intake_coordinator():
    """Resolve the one conversation-layer Intake coordinator.

    ``routes_conversations`` normally registers this provider during app
    startup.  The fallback keeps this router independently testable while
    still reusing the same coordinator/registries and ResearchStore.
    """
    store = _store()
    memory = _memory()
    try:
        coordinator = get_provider("research_intake_coordinator")
        if getattr(coordinator, "store", None) is store and getattr(coordinator, "memory_repository", None) is memory:
            return coordinator
    except KeyError:
        pass
    state_path = KB_DIR / "skill-state.json"
    return ResearchIntakeCoordinator(
        store,
        memory,
        SkillRegistryService(BASE_DIR / ".agents" / "skills", state_path),
        ToolRegistryService(build_default_tool_registry(), state_path),
    )


def _memory():
    """解析 memory repository provider（会话/项目归属的**唯一**存储，Spec022 既有实现）。

    本模块只做只读存在性查询（`get_conversation` / `get_project`），不新建第二套
    会话/项目存储；测试可用 `override_provider("memory_repository", ...)` 注入替身。
    """
    return get_provider("memory_repository")


def _resolve_project_id(conversation_id: str, project_id: Optional[str]) -> tuple[Optional[str], Optional[JSONResponse]]:
    """校验会话/项目归属并解析任务最终 `project_id`（Spec027 §端点与事件接口 / §产品边界）。

    - 会话不存在或不属于该 owner → 404 `CONVERSATION_NOT_FOUND`；
    - 显式 `project_id` 非空时校验项目存在且属于该 owner，否则 404 `PROJECT_NOT_FOUND`；
    - `project_id` 为空时**从会话继承**（Spec027 §产品边界：「绑定项目的会话创建任务时
      自动继承项目」）；会话未绑定项目则保持 None。

    归属校验只发生在这里（api 组合装配层），解析后的 `project_id` 作为参数传给
    service，因此不破坏 `research_service` 第 8 行「`owner_id` 由调用方传入、
    不 import `backend.app.memory.repository`」的分层约束。
    返回 `(project_id, None)`；校验失败返回 `(None, 错误响应)`。

    错误码说明：spec 冻结的 13 码词表用于 research 任务流，本处为会话/项目归属校验，
    沿用既有 code 风格（`routes_conversations.py:195` 的 `PROJECT_NOT_FOUND`）。
    """
    repository = _memory()
    conversation = repository.get_conversation(conversation_id, OWNER_ID)
    if conversation is None:
        return None, _api_error("CONVERSATION_NOT_FOUND", 404, "会话不存在")
    if project_id:
        if repository.get_project(project_id, OWNER_ID) is None:
            return None, _api_error("PROJECT_NOT_FOUND", 404, "项目不存在")
        return project_id, None
    return conversation.project_id, None


def _error(exc: ResearchServiceError) -> JSONResponse:
    """服务层稳定错误统一出口：`{"error": {"code", "message"}}` + `http_status`。"""
    return JSONResponse(status_code=exc.http_status, content={"error": {"code": exc.code, "message": exc.message}})


def _api_error(code: str, status_code: int, message: str) -> JSONResponse:
    """纯 HTTP 层输入校验错误出口（不入 027 冻结词表，见模块 docstring）。"""
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _utcnow() -> str:
    """当前 UTC 时间戳，格式与 research 侧一致：`YYYY-MM-DDTHH:MM:SSZ`。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _task_summary(task) -> dict:
    """任务摘要（不含完整 goal：只给截断摘要，避免大段原文进列表响应）。"""
    goal = task.goal or ""
    return {
        "research_task_id": task.research_task_id,
        "status": task.status,
        "current_plan_version": task.current_plan_version,
        "goal_excerpt": goal if len(goal) <= _GOAL_EXCERPT_CHARS else goal[:_GOAL_EXCERPT_CHARS],
        "quality_profile": task.quality_profile,
        "target_paper_count": task.target_paper_count,
        "language": task.language,
        "review_plan_first": bool(task.review_plan_first),
        "project_id": task.project_id,
        "conversation_id": task.conversation_id,
        "created_at": task.created_at,
    }


def _plan_payload(plan) -> dict:
    """计划只读投影：facets/rationale/status（facets_json 解析失败退化为 []）。"""
    try:
        facets = json.loads(plan.facets_json or "[]")
    except (TypeError, ValueError):
        facets = []
    if not isinstance(facets, list):
        facets = []
    return {
        "plan_version": plan.version,
        "status": plan.status,
        "planner_model": plan.planner_model,
        "rationale_summary": plan.rationale_summary,
        "facets": facets,
        "created_at": plan.created_at,
    }


def _json_value(value, fallback):
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed


def _session_plan_payload(plan) -> dict:
    """Safe whitelist projection for Task04 session-plan history."""
    if plan is None:
        return None
    return {
        "research_session_id": plan.research_session_id,
        "plan_version": plan.version,
        "schema_version": plan.schema_version,
        "output_hash": plan.output_hash,
        "objective": plan.objective,
        "scope": _json_value(plan.scope_json, {}),
        "work_items": _json_value(plan.work_items_json, []),
        "capabilities": _json_value(plan.capabilities_json, []),
        "budget": _json_value(plan.budget_json, {}),
        "report_structure": _json_value(plan.report_structure_json, {}),
        "safe_summary": _json_value(plan.safety_summary_json, {}),
        "status": plan.status,
        "created_at": plan.created_at,
    }


def _approval_payload(approval) -> dict:
    """Approval projection intentionally excludes idempotency/internal fields."""
    requested = _json_value(approval.requested_scope_json, {})
    approved = _json_value(approval.approved_scope_json, None)
    allowed = {
        "plan": {"plan_version", "output_hash"},
        "capability_override": {"skill", "skill_name", "tools", "approval_request_id"},
        "resource_extension": {"model_loops", "tool_calls", "seconds", "approval_request_id"},
    }.get(approval.kind, {"approval_request_id"})
    if not isinstance(requested, dict):
        requested = {}
    if not isinstance(approved, dict):
        approved = None
    requested = {key: requested[key] for key in allowed if key in requested}
    if approved is not None:
        approved = {key: approved[key] for key in allowed if key in approved}
    return {
        "approval_request_id": approval.approval_request_id,
        "kind": approval.kind,
        "status": approval.status,
        "subject_version": approval.subject_version,
        "scope": requested,
        "approved_scope": approved,
        "created_at": approval.created_at,
        "decided_at": approval.decided_at,
    }


def _current_plan(research_task_id: str) -> Optional[dict]:
    """当前计划（最大版本）只读投影；无计划返回 None。"""
    return _plan_payload(plan) if (plan := _store().get_current_plan(research_task_id)) is not None else None


def _selection_payload(selection) -> dict:
    """论文选集只读投影，不读取或复制 Spec015 论文元数据。"""
    try:
        facets = json.loads(selection.facets_json or "[]")
    except (TypeError, ValueError):
        facets = []
    if not isinstance(facets, list):
        facets = []
    return {
        "catalog_paper_id": selection.catalog_paper_id,
        "relevance": selection.relevance,
        "facets": facets,
        "evidence_level": selection.evidence_level,
        "created_at": selection.created_at,
    }


def _artifact_payload(artifact, research_session_id: str | None = None) -> dict:
    """Public artifact metadata; never expose storage paths or raw refs."""
    return {
        "artifact_id": artifact.artifact_id,
        "research_task_id": artifact.research_task_id,
        "report_version": artifact.report_version,
        "artifact_type": artifact.artifact_type,
        "content_hash": artifact.content_hash,
        "generated_by_agent_run_id": artifact.generated_by_agent_run_id,
        "created_at": artifact.created_at,
        "download_url": (
            f"/api/research-sessions/{research_session_id}/artifacts/{artifact.artifact_id}/download"
            if research_session_id else None
        ),
    }


def _notification_payload(notification) -> dict:
    try:
        payload = json.loads(notification.payload_json or "{}")
    except (TypeError, ValueError):
        payload = {}
    return {
        "notification_id": notification.notification_id,
        "research_session_id": notification.research_session_id,
        "research_task_id": notification.research_task_id,
        "notification_kind": notification.notification_kind,
        "status": notification.status,
        "subject_version": notification.subject_version,
        "event_seq": notification.event_seq,
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


def _cancelled_item_count(research_task_id: str) -> int:
    """当前已收敛为 cancelled 的 WorkItem 数（只读，用于 cancel 响应计数）。"""
    return sum(1 for item in _store().list_work_items(research_task_id) if item.status == "cancelled")


def _command_error(exc: ResearchCommandError) -> JSONResponse:
    retryable = exc.code in {"SOURCE_UNAVAILABLE", "TASK_MODEL_LIMIT_REACHED", "TASK_TIME_LIMIT_REACHED"}
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": {"code": exc.code, "message": exc.message, "retryable": retryable}},
    )


_SESSION_INTAKE_FIELDS = frozenset({
    "topic", "objective", "time_range", "language", "sources", "depth",
    "output", "citations", "constraints",
})


def _normalize_session_intake(values: dict, *, fallback_topic: str | None = None) -> dict:
    """Validate the small form summary before passing it to Intake storage."""
    if not isinstance(values, dict):
        raise ValueError("intake must be an object")
    unknown = set(values) - _SESSION_INTAKE_FIELDS
    if unknown:
        raise ValueError(f"unknown intake fields: {sorted(unknown)}")
    normalized: dict = {}
    for key, value in values.items():
        if key == "time_range":
            if not isinstance(value, dict) or set(value) - {"from", "to"}:
                raise ValueError("time_range must contain only from/to")
            if not all(isinstance(value.get(item), int) and not isinstance(value.get(item), bool) for item in ("from", "to")):
                raise ValueError("time_range from/to must be integers")
            if value["from"] > value["to"] or not (1900 <= value["from"] <= 2200 and 1900 <= value["to"] <= 2200):
                raise ValueError("time_range is invalid")
            normalized[key] = {"from": value["from"], "to": value["to"]}
        elif isinstance(value, str):
            if len(value.strip()) > 4000:
                raise ValueError(f"{key} is too long")
            normalized[key] = value.strip()
        elif isinstance(value, list):
            if len(value) > 32 or not all(isinstance(item, str) and len(item) <= 200 for item in value):
                raise ValueError(f"{key} is invalid")
            normalized[key] = [item.strip() for item in value]
        elif isinstance(value, dict):
            raise ValueError(f"{key} must be a string or list")
        else:
            raise ValueError(f"{key} is invalid")
    if fallback_topic and "topic" not in normalized:
        normalized["topic"] = fallback_topic[:4000]
    return normalized


def _intake_payload(result) -> dict:
    """Safe Session/Intake response; Skill bodies never cross this boundary."""
    session = result.session.to_dict() if result.session is not None else None
    fields = [item.to_dict() for item in result.fields]
    activation = result.activation
    if isinstance(activation, dict):
        activation = {key: value for key, value in activation.items() if key != "skill"}
        skill = (result.activation or {}).get("skill")
        if isinstance(skill, dict):
            activation["skill"] = {
                key: skill[key]
                for key in ("name", "skill_id", "version", "schema_version", "content_hash", "description", "tools")
                if key in skill
            }
    return {
        "status": result.status,
        "session": session,
        "fields": fields,
        "missing": list(result.missing),
        "question": result.question,
        "choices": list(result.choices),
        "activation": activation,
        "error": result.error,
    }


def _session_create_text(intake: dict) -> str:
    topic = str(intake.get("topic") or "").strip()
    objective = str(intake.get("objective") or "").strip()
    time_range = intake.get("time_range")
    text = "帮我做一个深度研究"
    if topic:
        text += f"，主题是{topic}"
    if objective:
        text += f"，目标是{objective}"
    if isinstance(time_range, dict):
        text += f"，时间范围是{time_range['from']}-{time_range['to']}"
    return text + "。"


def _create_unified_session_unlocked(payload: ResearchSessionCreateRequest, *, legacy_goal: str | None = None):
    """Create/enter the shared conversation → Intake Session flow."""
    intake = _normalize_session_intake(payload.intake, fallback_topic=legacy_goal)
    conversation_hint = (payload.conversation_id or "").strip()
    fingerprint = hashlib.sha256(json.dumps({
        "conversation_id": conversation_hint,
        "project_id": (payload.project_id or "").strip() or None,
        "trigger_message_id": payload.trigger_message_id,
        "intake": intake,
        "legacy_goal": legacy_goal,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    # A supplied trigger is itself the stable event identity.  This prevents
    # retries that carry a slightly different form projection from writing a
    # second Session; the stored fingerprint turns that difference into a
    # visible conflict instead of silently accepting it.
    request_key = payload.idempotency_key or (
        f"trigger:{payload.trigger_message_id}" if payload.trigger_message_id else f"request:{fingerprint}"
    )
    existing_request = _store().get_session_create_request(OWNER_ID, request_key)
    if existing_request is not None:
        if existing_request["request_fingerprint"] != fingerprint:
            return _api_error("SESSION_CREATE_IDEMPOTENCY_CONFLICT", 409, "幂等键对应了不同的研究请求")
        if existing_request.get("response_json"):
            return json.loads(existing_request["response_json"])
    topic = str(intake.get("topic") or legacy_goal or "深度研究").strip()
    conversation_id = (payload.conversation_id or "").strip()
    project_id = (payload.project_id or "").strip() or None
    memory = _memory()
    if payload.trigger_message_id and not conversation_id:
        return _api_error("MESSAGE_NOT_FOUND", 404, "触发消息必须属于指定会话")
    conversation = memory.get_conversation(conversation_id, OWNER_ID) if conversation_id else None
    if conversation_id and conversation is None:
        return _api_error("CONVERSATION_NOT_FOUND", 404, "会话不存在")
    if project_id and memory.get_project(project_id, OWNER_ID) is None:
        return _api_error("PROJECT_NOT_FOUND", 404, "项目不存在")
    if conversation is not None and project_id is not None and conversation.project_id != project_id:
        return _api_error("PROJECT_MISMATCH", 409, "显式项目与会话归属不一致")
    if conversation is not None and project_id is None:
        project_id = conversation.project_id
    if conversation is None:
        conversation = memory.create_conversation(OWNER_ID, project_id, f"深度研究：{topic}")
    else:
        # An explicit form creation in an existing conversation inherits its
        # current project and never rewrites a user's existing title.
        if payload.trigger_message_id:
            trigger = memory.get_message(payload.trigger_message_id, OWNER_ID)
            if trigger is None or trigger.conversation_id != conversation.conversation_id or trigger.role != "user":
                return _api_error("MESSAGE_NOT_FOUND", 404, "触发消息不存在")
        active = _store().get_active_session(conversation.conversation_id, OWNER_ID)
        if active is not None:
            return _api_error("RESEARCH_SESSION_ACTIVE_CONFLICT", 409, "当前会话已有进行中的研究 Intake")
    trigger_message_id = payload.trigger_message_id
    if trigger_message_id:
        trigger = memory.get_message(trigger_message_id, OWNER_ID)
    else:
        _conversation, trigger, _assistant = memory.create_idempotent_message_pair(
            conversation.conversation_id, OWNER_ID, _session_create_text(intake),
            idempotency_key=request_key, model=None, mode="research"
        )
    coordinator = _intake_coordinator()
    prior = _store().get_session_by_trigger(conversation.conversation_id, trigger.message_id, OWNER_ID)
    if prior is not None:
        # A process may have committed the Session before losing the response
        # idempotency record.  Replay the trigger projection rather than
        # returning an active conflict or creating another Session.
        result = coordinator.handle_message(conversation.conversation_id, OWNER_ID, trigger.message_id, trigger.content)
    else:
        result = coordinator.begin_research_intake(
            conversation.conversation_id, OWNER_ID, trigger.message_id, intake
        )
    if result.status == "active_conflict":
        return _api_error("RESEARCH_SESSION_ACTIVE_CONFLICT", 409, "当前会话已有进行中的研究 Intake")
    if result.status == "error":
        error = result.error or {"code": "SOURCE_UNAVAILABLE", "message": "研究 Intake 暂时不可用"}
        return _api_error(str(error.get("code") or "SOURCE_UNAVAILABLE"), 503, str(error.get("message") or "研究 Intake 暂时不可用"))
    response = {
        "research_session_id": result.session.research_session_id if result.session else None,
        "conversation": {
            "conversation_id": conversation.conversation_id,
            "project_id": conversation.project_id,
            "title": conversation.title,
        },
        "trigger_message_id": trigger.message_id,
        "intake": _intake_payload(result),
    }
    if result.session is not None:
        _store().save_session_create_request(
            owner_id=OWNER_ID, idempotency_key=request_key, request_fingerprint=fingerprint,
            research_session_id=result.session.research_session_id,
            conversation_id=conversation.conversation_id, trigger_message_id=trigger.message_id,
            response=response,
        )
    return response


def _create_unified_session(payload: ResearchSessionCreateRequest, *, legacy_goal: str | None = None):
    """Serialize Session creation so key reservation and message pair are single-writer."""
    with _SESSION_CREATE_LOCK:
        return _create_unified_session_unlocked(payload, legacy_goal=legacy_goal)


def _legacy_memory_compatibility_required(memory) -> bool:
    """Detect the pre-Session memory seam used by legacy task clients.

    Spec034's Session flow requires the durable idempotent message-pair
    operation.  Older integrations expose only the read-side conversation /
    project contract, however, and their ``POST /research-tasks`` requests
    still target the original task API.  Keep that compatibility boundary
    explicit in the production adapter rather than teaching tests a second
    repository implementation.  Real ``MemoryRepository`` instances always
    provide this method, so the Session endpoint remains unchanged.
    """
    return not callable(getattr(memory, "create_idempotent_message_pair", None))


def _create_legacy_task_compat(payload: ResearchTaskCreateRequest, goal: str, conversation_id: str):
    """Serve the old task API when only the pre-Session memory seam exists."""
    try:
        # Legacy semantics intentionally allow an explicit project to override
        # the conversation's project.  The new Session endpoint uses
        # ``_create_unified_session_unlocked`` and remains fail-closed on a
        # project mismatch.
        resolved_project_id, context_error = _resolve_project_id(conversation_id, payload.project_id)
    except Exception:
        logger.exception("legacy research task context validation failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务依赖暂时不可用"))
    if context_error is not None:
        return context_error
    try:
        task = _service().create_task(
            owner_id=OWNER_ID,
            goal=goal,
            conversation_id=conversation_id,
            project_id=resolved_project_id,
            quality_profile=payload.quality_profile,
            target_paper_count=payload.target_paper_count,
            language=payload.language,
            review_plan_first=payload.review_plan_first,
        )
    except ResearchServiceError as exc:
        return _error(exc)
    except Exception:
        logger.exception("legacy research task compatibility adapter failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务调度暂时不可用"))
    return _task_summary(task)


@session_router.get("/{research_session_id}/artifacts")
def list_research_artifacts(research_session_id: str, report_version: Optional[int] = Query(None, ge=1)):
    """List immutable report artifacts through the owner/session/task seam."""
    try:
        session = _store().get_session(research_session_id, OWNER_ID)
        if session is None:
            return _api_error("RESEARCH_SESSION_NOT_FOUND", 404, "研究会话不存在")
        if not session.research_task_id:
            return _api_error("ARTIFACT_NOT_READY", 409, "报告尚未生成")
        artifacts = _store().list_artifacts_for_task(session.research_task_id, OWNER_ID, report_version=report_version)
        return {"research_session_id": research_session_id, "artifacts": [_artifact_payload(item, research_session_id) for item in artifacts]}
    except Exception:
        logger.exception("research artifact list failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究报告依赖暂时不可用"))


@session_router.get("/{research_session_id}/artifacts/{artifact_id}/download")
def download_research_artifact(
    research_session_id: str, artifact_id: str, mode: str = Query("attachment")
):
    """Download an owner-bound in-database artifact; arbitrary paths are rejected."""
    try:
        session = _store().get_session(research_session_id, OWNER_ID)
        if session is None or not session.research_task_id:
            return _api_error("RESEARCH_SESSION_NOT_FOUND", 404, "研究会话不存在")
        artifact = _store().get_artifact(artifact_id, OWNER_ID)
        if artifact is None or artifact.research_task_id != session.research_task_id:
            return _api_error("ARTIFACT_NOT_FOUND", 404, "报告产物不存在")
        if artifact.artifact_type not in {"markdown", "html", "citation_manifest"}:
            return _api_error("ARTIFACT_NOT_FOUND", 404, "报告产物不存在")
        if mode not in {"attachment", "inline"} or (mode == "inline" and artifact.artifact_type != "html"):
            return _api_error("INVALID_ARTIFACT_MODE", 400, "仅 HTML 支持 inline 阅读")
        # Storage refs are intentionally not dereferenced by this API.
        if artifact.content is None:
            return _api_error("ARTIFACT_NOT_READY", 409, "该报告产物不可直接下载")
        media_type = {
            "markdown": "text/markdown; charset=utf-8",
            "html": "text/html; charset=utf-8",
            "citation_manifest": "application/json; charset=utf-8",
        }[artifact.artifact_type]
        suffix = {"markdown": "md", "html": "html", "citation_manifest": "json"}[artifact.artifact_type]
        response = Response(artifact.content, media_type=media_type)
        disposition = "inline" if mode == "inline" else "attachment"
        response.headers["Content-Disposition"] = f'{disposition}; filename="research-report-v{artifact.report_version}.{suffix}"'
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
    except Exception:
        logger.exception("research artifact download failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究报告依赖暂时不可用"))


@notification_router.get("")
def list_research_notifications(after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    """Owner-scoped notification replay/list endpoint."""
    items = _store().list_notifications(OWNER_ID, after_seq=after_seq, limit=limit)
    return {"notifications": [_notification_payload(item) for item in items]}


@notification_router.post("/{notification_id}/read")
def mark_research_notification_read(notification_id: str):
    """CAS unread→read; cross-owner IDs return the same not-found response."""
    item = _store().mark_notification_read(notification_id, OWNER_ID)
    if item is None:
        return _api_error("NOTIFICATION_NOT_FOUND", 404, "通知不存在")
    return _notification_payload(item)


@notification_router.get("/events")
def stream_research_notifications(
    request: Request, after_seq: int = Query(0, ge=0), polls: int = Query(20, ge=1, le=120)
):
    """Replay and bounded-poll owner notifications after Last-Event-ID."""
    header = request.headers.get("last-event-id")
    if header and header.strip():
        try:
            after_seq = max(0, int(header.strip()))
        except ValueError:
            return _api_error("INVALID_CURSOR", 400, "after_seq 或 Last-Event-ID 非法")
    return StreamingResponse(
        _notification_event_stream(after_seq, max_polls=polls), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )


def _notification_event_stream(
    after_seq: int, *, max_polls: int = 20, poll_seconds: float = _EVENT_POLL_SECONDS
):
    """Yield replay plus bounded cursor polls and heartbeats.

    The finite bound makes unit tests and proxies deterministic.  Clients
    reconnect with the last emitted event id to continue the same durable
    owner-scoped replay without a second message stream.
    """
    cursor = max(0, int(after_seq))
    for poll in range(max(1, min(int(max_polls), 120))):
        items = _store().list_notifications(OWNER_ID, after_seq=cursor, limit=_EVENT_BATCH_LIMIT)
        if items:
            for item in items:
                payload = _notification_payload(item)
                cursor = max(cursor, int(item.event_seq))
                yield f"id: {item.event_seq}\nevent: {item.notification_kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        else:
            yield ": heartbeat\n\n"
        if poll + 1 < max_polls:
            time.sleep(max(0.0, min(float(poll_seconds), 1.0)))


@session_router.get("/{research_session_id}")
def get_research_session(research_session_id: str):
    """Owner-scoped Session detail including immutable plan/approval history."""
    try:
        service = _approval_service()
        session = service.get_session(research_session_id, OWNER_ID)
        plan = _store().get_session_plan(research_session_id, OWNER_ID)
        return {
            **session.to_dict(),
            "plan": plan.to_dict() if plan else None,
            "plans": [item.to_dict() for item in _store().list_session_plans(research_session_id, OWNER_ID)],
            "approvals": [item.to_dict() for item in _store().list_approvals(research_session_id, OWNER_ID)],
            "artifacts": (
                [_artifact_payload(item, research_session_id) for item in _store().list_artifacts_for_task(session.research_task_id, OWNER_ID)]
                if session.research_task_id else []
            ),
            "notifications": [
                _notification_payload(item)
                for item in _store().list_notifications(OWNER_ID)
                if item.research_session_id == research_session_id
            ],
        }
    except ResearchCommandError as exc:
        return _command_error(exc)
    except Exception:
        logger.exception("research session command failed")
        return _command_error(ResearchCommandError("SOURCE_UNAVAILABLE", "研究命令依赖暂时不可用"))


@session_router.post("", status_code=202)
def create_research_session(payload: ResearchSessionCreateRequest):
    """Create a Session and first message through the shared Intake flow."""
    try:
        return _create_unified_session(payload)
    except (ValueError, LookupError) as exc:
        return _api_error("PLAN_VALIDATION_FAILED", 400, str(exc) or "研究表单参数非法")
    except ResearchCommandError as exc:
        return _command_error(exc)
    except Exception:
        logger.exception("research session create failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究会话依赖暂时不可用"))


@session_router.get("")
def list_research_sessions(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """Owner-scoped Session list used by the Research Tab."""
    try:
        if project_id and _memory().get_project(project_id, OWNER_ID) is None:
            return _api_error("PROJECT_NOT_FOUND", 404, "项目不存在")
        if project_id is None:
            sessions, next_cursor = _store().list_sessions_page(OWNER_ID, status=status, limit=limit, cursor=cursor)
        else:
            # Project binding lives in the conversation DB.  Walk the same
            # owner/status keyset pages and advance the raw cursor only after
            # every examined Session, so filtered pages cannot duplicate or
            # skip rows across requests.
            memory = _memory()
            sessions = []
            scan_cursor = cursor
            next_cursor = None
            while len(sessions) < limit:
                page, raw_next = _store().list_sessions_page(OWNER_ID, status=status, limit=100, cursor=scan_cursor)
                sessions.extend(
                    item for item in page
                    if (conversation := memory.get_conversation(item.conversation_id, OWNER_ID)) is not None
                    and conversation.project_id == project_id
                )
                scan_cursor = raw_next
                if raw_next is None:
                    break
            if len(sessions) > limit:
                sessions = sessions[:limit]
                next_cursor = _store().encode_sessions_cursor(sessions[-1], status=status)
            elif scan_cursor is not None:
                next_cursor = scan_cursor
        return {"research_sessions": [item.to_dict() for item in sessions], "next_cursor": next_cursor}
    except ValueError as exc:
        return _api_error("PLAN_VALIDATION_FAILED", 400, str(exc) or "状态非法")
    except Exception:
        logger.exception("research session list failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究会话依赖暂时不可用"))


@session_router.post("/{research_session_id}/commands")
def execute_research_session_command(research_session_id: str, payload: ResearchSessionCommandRequest):
    """Unified button/natural-language command boundary for Task04."""
    try:
        return _approval_service().command(
            research_session_id,
            OWNER_ID,
            command=payload.command,
            subject_version=payload.subject_version,
            scope_json=payload.scope_json,
            idempotency_key=payload.idempotency_key,
        )
    except ResearchCommandError as exc:
        return _command_error(exc)
    except Exception:
        logger.exception("research session command failed")
        return _command_error(ResearchCommandError("SOURCE_UNAVAILABLE", "研究命令依赖暂时不可用"))


@session_router.post("/{research_session_id}/plans", status_code=202)
def author_research_session_plan(research_session_id: str, payload: dict):
    """Persist a validated ResearchPlanOutput and create its pending Approval."""
    try:
        return _approval_service().author_plan(research_session_id, OWNER_ID, payload)
    except ResearchCommandError as exc:
        return _command_error(exc)
    except Exception:
        logger.exception("research session plan authoring failed")
        return _command_error(ResearchCommandError("SOURCE_UNAVAILABLE", "计划服务暂时不可用"))


@router.post("", status_code=202)
def create_research_task(payload: ResearchTaskCreateRequest):
    """Legacy adapter: enter the unified Session/Intake flow only.

    This endpoint intentionally does not call ``ResearchService.create_task``
    or start an Orchestrator.  Task creation is reserved for the approved
    Session plan command; the old payload remains available to older clients.
    """
    goal = (payload.goal or "").strip()
    conversation_id = (payload.conversation_id or "").strip()
    if not goal or not conversation_id:
        return _error(ResearchServiceError("PLAN_VALIDATION_FAILED", 400, "goal 与 conversation_id 为必填"))
    # Older Spec027 clients (and their minimal repository seam) predate the
    # conversational Session contract.  Route only that capability-limited
    # seam through the original task service; a real MemoryRepository enters
    # the unified Session flow below.  This does not weaken Session's
    # project-mismatch fail-closed rule.
    try:
        if _legacy_memory_compatibility_required(_memory()):
            return _create_legacy_task_compat(payload, goal, conversation_id)
    except Exception:
        logger.exception("legacy research task compatibility detection failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务依赖暂时不可用"))
    try:
        request = ResearchSessionCreateRequest(
            conversation_id=conversation_id,
            project_id=payload.project_id,
            intake={"topic": goal},
        )
        result = _create_unified_session(request, legacy_goal=goal)
        return result
    except ValueError as exc:
        return _error(ResearchServiceError("PLAN_VALIDATION_FAILED", 400, str(exc) or "研究请求非法"))
    except LookupError:
        return _api_error("CONVERSATION_NOT_FOUND", 404, "会话不存在")
    except Exception as exc:
        logger.exception("legacy research task adapter failed: %s", exc)
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究会话依赖暂时不可用"))


@router.get("")
def list_research_tasks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = None,
):
    """keyset 分页任务列表（按 created_at, research_task_id 升序）。

    `project_id` 非空时先校验项目存在且属于该 owner（Spec027 §端点与事件接口：失败列含
    「404 project」），不存在返回 404 `PROJECT_NOT_FOUND`（不再把未知项目当「空列表」，
    否则前端无法区分「项目不存在」与「项目下无任务」）；校验通过后按项目过滤。
    失败：400 游标非法（store `decode_cursor` 抛 ValueError）；404 项目不存在；
    503 依赖不可用（memory repository 归属校验抛意外异常，只记日志，稳定错误体
    `SOURCE_UNAVAILABLE`，见模块 docstring「错误出口」）。
    """
    if project_id:
        try:
            # P2-A：项目归属校验同样依赖 memory repository，故障语义与 POST 一致：
            # 返回 503 稳定错误体，不冒泡成裸 500。
            project = _memory().get_project(project_id, OWNER_ID)
        except Exception as exc:
            logger.exception("research task list project lookup failed: %s", exc)
            return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务依赖暂时不可用"))
        if project is None:
            # 归属校验语义与 POST 一致，错误码风格说明见 `_resolve_project_id`。
            return _api_error("PROJECT_NOT_FOUND", 404, "项目不存在")
    try:
        items, next_cursor = _service().list_tasks(
            OWNER_ID, project_id=project_id, status=status, limit=limit, cursor=cursor
        )
    except ResearchServiceError as exc:
        return _error(exc)
    except ValueError as exc:
        return _api_error("INVALID_CURSOR", 400, str(exc) or "游标非法")
    return {"research_tasks": [_task_summary(item) for item in items], "next_cursor": next_cursor}


@router.get("/{research_task_id}")
def get_research_task(research_task_id: str):
    """任务详情及 owner-scoped Session/plan/approval projection."""
    try:
        task = _service().get_task(research_task_id, OWNER_ID)
    except ResearchServiceError as exc:
        return _error(exc)
    try:
        detail = _task_summary(task)
        detail["updated_at"] = task.updated_at
        detail["completed_at"] = task.completed_at
        detail["plan"] = _current_plan(research_task_id)
        session = _store().get_session_by_task(research_task_id, OWNER_ID)
        detail["research_session_id"] = session.research_session_id if session else None
        if session is None:
            detail["plans"] = []
            detail["approvals"] = []
        else:
            current_session_plan = _store().get_session_plan(
                session.research_session_id, OWNER_ID, session.current_plan_version
            )
            if current_session_plan is not None:
                detail["plan"] = _session_plan_payload(current_session_plan)
            detail["plans"] = [
                _session_plan_payload(item)
                for item in _store().list_session_plans(session.research_session_id, OWNER_ID)
            ]
            detail["approvals"] = [
                _approval_payload(item)
                for item in _store().list_approvals(session.research_session_id, OWNER_ID)
            ]
        return detail
    except Exception:
        logger.exception("research task detail projection failed")
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务依赖暂时不可用"))


@router.get("/{research_task_id}/events")
def stream_research_events(research_task_id: str, request: Request, after_seq: int = Query(0, ge=0)):
    """SSE 事件流：先持久化再推送，只带安全 payload；支持 `Last-Event-ID`（优先于 query）。

    - 推送格式 `id: {event_seq}\\nevent: {event_type}\\ndata: {json}\\n\\n`，
      data 为 `{"research_task_id","event_seq","type","timestamp","payload"}`；
    - 任务进入终态且无新事件后发一条 `event: terminal` 并结束；该帧是**合成帧**，
      不带 `id:` 行且 data 的 `event_seq` 为 null（见 `_sse_frame`），客户端以 `event` 名判定收尾；
    - 每 15 秒发 `: heartbeat` 保活，单次循环 `time.sleep(0.5)`。
    - 失败：404（任务不存在）；410（带游标重连却发现任务已删除）。
    """
    resolved = _resolve_after_seq(request, after_seq)
    if isinstance(resolved, JSONResponse):
        return resolved
    try:
        _service().get_task(research_task_id, OWNER_ID)
    except ResearchServiceError as exc:
        if resolved > 0 or request.headers.get("last-event-id"):
            # 带着游标重连却找不到任务：任务已被删除（410），而非「从未存在」。
            return _api_error("TASK_DELETED", 410, "研究任务已被删除")
        return _error(exc)
    return StreamingResponse(
        _event_stream(research_task_id, resolved),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_after_seq(request: Request, after_seq: int) -> int | JSONResponse:
    """解析起始 seq：`Last-Event-ID` 请求头优先于 `after_seq`；非法返回 400 响应。"""
    header = request.headers.get("last-event-id")
    if header is None or not header.strip():
        return after_seq
    try:
        return max(0, int(header.strip()))
    except ValueError:
        return _api_error("INVALID_CURSOR", 400, "after_seq 或 Last-Event-ID 非法")


def _event_stream(research_task_id: str, start_seq: int):
    """事件流生成器：按 event_seq 连续推送，终态收尾，定期心跳。"""
    # Reconnect/idle recovery: consume pending cross-store projections once
    # before polling, even when no fresh ResearchEvent exists.
    with suppress(Exception):
        _service().drain_processing_projection_retries(research_task_id, OWNER_ID)
    cursor = start_seq
    last_flush = time.monotonic()
    while True:
        try:
            events = _service().list_events(
                research_task_id, OWNER_ID, after_seq=cursor, limit=_EVENT_BATCH_LIMIT
            )
            task = _service().get_task(research_task_id, OWNER_ID)
        except ResearchServiceError:
            # 响应头已发出，无法再改状态码：任务在推送期间被删除，发一条 terminal 后结束。
            # 合成帧不带 `id:`（见 `_sse_frame`）：游标保持在最后一条真实事件上。
            yield _sse_frame(research_task_id, None, "terminal", {"status": "deleted", "code": "TASK_DELETED"})
            return
        if events:
            for event in events:
                cursor = event.event_seq
                projection_error = False
                upsert = None
                try:
                    upsert = _service().project_event_for_sse(event, OWNER_ID)
                except Exception:
                    # Do not expose exception text.  The durable raw event is
                    # still emitted for legacy clients, followed by a stable
                    # retry frame for tree-aware clients.
                    projection_error = True
                # Projection completes (or records its retry marker) before
                # either raw or tree frames are yielded.
                yield _sse_frame(research_task_id, event.event_seq, event.event_type, _safe_payload(event))
                if upsert is not None:
                    # The upsert envelope is incremental data, not a second
                    # ResearchEvent.  It therefore has no duplicate SSE id.
                    yield _sse_frame(research_task_id, None, "processing_step", upsert)
                if projection_error:
                    yield _sse_frame(
                        research_task_id, None, "processing_step",
                        {"type": "processing_step", "operation": "syncing", "status": "trace_syncing", "code": "TRACE_PROJECTION_FAILED", "retryable": True},
                    )
            last_flush = time.monotonic()
            continue
        if task.status in _TASK_TERMINAL:
            # 合成帧不带 `id:`，避免与上一条真实事件 seq 重复污染 Last-Event-ID。
            yield _sse_frame(research_task_id, None, "terminal", {"status": task.status})
            return
        if time.monotonic() - last_flush >= _EVENT_HEARTBEAT_SECONDS:
            yield ": heartbeat\n\n"
            last_flush = time.monotonic()
        time.sleep(_EVENT_POLL_SECONDS)


def _safe_payload(event) -> dict:
    """事件安全 payload（store 已过滤），解析失败返回空字典，绝不回抛。"""
    try:
        value = json.loads(event.safe_payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sse_frame(research_task_id: str, event_seq: Optional[int], event_type: str, payload: dict) -> str:
    """单条 SSE 帧：data 为单行 JSON，禁止换行（SSE 以 \\n\\n 分帧）。

    `event_seq` 为 None 表示**合成帧**（本模块凭空补出的收尾帧，不对应任何持久化事件）：
    此时**省略 `id:` 行**。SSE 允许省略 `id`，客户端会保留上一条真实事件的
    `Last-Event-ID`，游标不被污染；若沿用上一条真实事件的 seq 当 `id`，客户端会把它记成
    重复值（任务无事件时甚至是 0），重连时 `_resolve_after_seq` 的 `resolved > 0` 判定失效。
    真实事件帧必须带 `id: {event_seq}`（data 里的 `event_seq` 与持久化 seq 一致）。
    """
    data = {
        "research_task_id": research_task_id,
        "event_seq": event_seq,
        "type": event_type,
        "timestamp": _utcnow(),
        "payload": payload,
    }
    id_line = "" if event_seq is None else f"id: {event_seq}\n"
    return f"{id_line}event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{research_task_id}/report")
def get_research_report(research_task_id: str, plan_version: Optional[int] = Query(None, ge=1)):
    """读取报告与论文选集（plan_version 为 None 取最大版本）。失败：404；409 `REPORT_NOT_READY`。"""
    try:
        report = _service().get_report(research_task_id, OWNER_ID, plan_version=plan_version)
    except ResearchServiceError as exc:
        return _error(exc)
    try:
        limitations = json.loads(report.limitations_json or "{}")
    except (TypeError, ValueError):
        limitations = {}
    try:
        selections = [_selection_payload(item) for item in _store().list_selections(research_task_id)]
    except Exception as exc:
        logger.exception("research report selections lookup failed: %s", exc)
        return _error(ResearchServiceError("SOURCE_UNAVAILABLE", 503, "研究任务依赖暂时不可用"))
    return {
        "report_id": report.report_id,
        "research_task_id": report.research_task_id,
        "plan_version": report.plan_version,
        "status": report.status,
        "markdown": report.markdown,
        "limitations": limitations,
        "selections": selections,
        "created_at": report.created_at,
    }


@router.post("/{research_task_id}/feedback")
def feedback_research_task(research_task_id: str, payload: ResearchTaskFeedbackRequest):
    """计划批准（``action="approve"``）或补充范围（追加新计划版本，不覆盖既有证据）。

    失败：400（既无 action 也无非空 add_scope）；409（状态不允许）。
    """
    try:
        task = _service().feedback(research_task_id, OWNER_ID, action=payload.action, add_scope=payload.add_scope)
    except ResearchServiceError as exc:
        return _error(exc)
    return {
        "research_task_id": task.research_task_id,
        "status": task.status,
        "current_plan_version": task.current_plan_version,
    }


@router.post("/{research_task_id}/cancel")
def cancel_research_task(research_task_id: str):
    """取消任务（空 body 也可）：停止新增节点，queued/running 的 WorkItem 一并收敛。

    失败：404；409 `TASK_TERMINAL_CONFLICT`（已终态重复取消）。
    """
    before = _cancelled_item_count(research_task_id)
    try:
        task = _service().cancel(research_task_id, OWNER_ID)
    except ResearchServiceError as exc:
        return _error(exc)
    return {
        "research_task_id": task.research_task_id,
        "status": task.status,
        "cancelled_work_items": max(0, _cancelled_item_count(research_task_id) - before),
    }


@router.patch("/{research_task_id}/project")
def patch_research_task_project(research_task_id: str, payload: ResearchTaskPatchProjectRequest):
    """移动/解绑项目归属（``project_id`` 显式传 null 表示解绑）。

    失败：404；400（请求体缺 `project_id` 键）；409 running/planning 禁止移动。
    """
    if "project_id" not in payload.model_fields_set:
        return _error(ResearchServiceError("PLAN_VALIDATION_FAILED", 400, "project_id 为必填（null 表示解绑）"))
    try:
        task = _service().patch_project(research_task_id, OWNER_ID, payload.project_id)
    except ResearchServiceError as exc:
        return _error(exc)
    return {"research_task_id": task.research_task_id, "project_id": task.project_id, "status": task.status}


@router.delete("/{research_task_id}")
def delete_research_task(research_task_id: str):
    """删除任务**私有数据**（计划/WorkItem/选集/报告/事件）。

    **不删** Spec015 论文目录与知识库：论文只以 `catalog_paper_id` 引用，删除任务
    不影响全局目录（Spec027 §端点与事件接口 / §明确不做）。
    失败：404；409 running/planning 禁止删除。
    """
    try:
        _service().delete_task(research_task_id, OWNER_ID)
    except ResearchServiceError as exc:
        return _error(exc)
    return {"deleted": True}
