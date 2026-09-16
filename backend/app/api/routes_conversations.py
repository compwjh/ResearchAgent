import contextlib
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.api.common import stream_event
from backend.app.api.schemas import (
    ConversationMessageRequest,
    ConversationPatchRequest,
    ConversationReasoningRequest,
    MemoryAnalysisBatchDecisionRequest,
    MemoryAnalysisDecisionRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    SystemRulePatchRequest,
    SystemRulePutRequest,
)
from backend.app.chat.application.chat_runner import ChatStreamInterrupted, run_chat
from backend.app.chat.application.context_compaction import collapse_tool_outputs, get_compaction_worker
from backend.app.chat.application.conversation_service import (
    compose_chat_messages,
    compose_chat_prompt,
    get_memory_analysis_worker,
    get_memory_evolution_worker,
    has_explicit_global_intent,
    is_system_rule_intent,
)
from backend.app.chat.application.reasoning import (
    MAX_REASONING_CODEPOINTS,
    REASONING_EFFORTS,
    EventSequencer,
    ReasoningStreamFilter,
    filter_reasoning,
)
from backend.app.chat.application.token_budget import estimate_tokens
from backend.app.knowledge_base.application import (
    citation_payloads,
    clear_project_document_associations,
    hybrid_search,
    list_documents_for_project,
)
from backend.app.memory.markdown_store import read_user_memory_or_empty
from backend.app.memory.repository import OWNER_ID, MemoryRepository, SystemRuleUnavailableError
from backend.app.memory.session_search import search_sessions
from backend.app.platform.bootstrap import get_provider, register_provider
from backend.app.platform.config import (
    BASE_DIR,
    CHAT_COMPACT_TRIGGER_RATIO,
    CHAT_SUMMARY_BUDGET_CHARS,
    CHAT_TOTAL_TOKEN_BUDGET,
    KB_DIR,
)
from backend.app.platform.model_catalog import get_online_model, is_online_model
from backend.app.platform.observability import (
    prompt_observation_metadata,
    record_ollama_generation,
    redact_prompt_messages,
    utc_now,
)
from backend.app.platform.ollama import (
    EffortResolutionError,
    ReasoningCapabilities,
    ReasoningResolution,
    _provider_value,
    get_available_models,
    get_reasoning_capabilities,
    resolve_reasoning_effort,
)
from backend.app.research.application.intake import DEFAULT_FIELDS, ResearchIntakeCoordinator
from backend.app.research.application.intake_projection import (
    build_intake_projection,
    persist_intake_projection,
)
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_service import ToolRegistryService

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_research_intake_coordinator():
    """Compose the conversation-layer coordinator from existing registries/stores."""
    state_path = KB_DIR / "skill-state.json"
    return ResearchIntakeCoordinator(
        get_provider("research_store"),
        _repo(),
        SkillRegistryService(BASE_DIR / ".agents" / "skills", state_path),
        ToolRegistryService(build_default_tool_registry(), state_path),
    )


register_provider("research_intake_coordinator", _build_research_intake_coordinator)


def _repo() -> MemoryRepository:
    return get_provider("memory_repository")


register_provider("memory_repository", MemoryRepository, singleton=False)


def _project_payload(item):
    return {"project_id": item.project_id, "owner_id": item.owner_id, "name": item.name, "instructions": item.instructions, "status": item.status, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "last_activity_at": (item.last_activity_at or item.updated_at).isoformat()}


def _conversation_payload(item):
    return {"conversation_id": item.conversation_id, "owner_id": item.owner_id, "project_id": item.project_id, "title": item.title, "status": item.status, "memory_history_policy": item.memory_history_policy, "reasoning_effort": item.reasoning_effort, "memory_binding_at": item.memory_binding_at.isoformat() if item.memory_binding_at else None, "memory_binding_message_id": item.memory_binding_message_id, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


_INTAKE_STATUSES = frozenset({"intake", "clarification", "active_conflict", "error"})
_INTAKE_CHOICE_IDS = frozenset({"modify_current", "cancel_then_new", "new_conversation"})
_INTAKE_FIELD_NAMES = frozenset({"topic", "objective", "time_range", *DEFAULT_FIELDS})


def _safe_intake_projection(payload):
    """Return only the historical Intake fields supported by the UI contract."""
    if not isinstance(payload, dict) or payload.get("schema_version") != "task03-intake-v1":
        return None
    status = payload.get("status")
    if status not in _INTAKE_STATUSES:
        return None
    fields = []
    raw_fields = payload.get("fields")
    for item in raw_fields if isinstance(raw_fields, list) else []:
        if not isinstance(item, dict) or item.get("field_name") not in _INTAKE_FIELD_NAMES:
            continue
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            confidence = max(0.0, min(1.0, float(confidence)))
        else:
            confidence = None
        field = {
            "field_name": item["field_name"],
            "value_json": item.get("value_json", "")[:20000] if isinstance(item.get("value_json"), str) else "",
            "source": str(item.get("source") or "")[:80],
            "confidence": confidence,
            "confirmation_status": str(item.get("confirmation_status") or "")[:80],
            "message_id": str(item.get("message_id") or "")[:128] or None,
        }
        fields.append(field)
    choices = []
    raw_choices = payload.get("choices")
    for choice in raw_choices if isinstance(raw_choices, list) else []:
        if not isinstance(choice, dict) or choice.get("id") not in _INTAKE_CHOICE_IDS:
            continue
        choices.append({"id": choice["id"], "label": str(choice.get("label") or "")[:120]})
    skill = payload.get("skill")
    skill_snapshot = None
    if isinstance(skill, dict) and skill.get("skill_id") == "deep-research-orchestration":
        skill_snapshot = {
            "skill_id": "deep-research-orchestration",
            "name": str(skill.get("name") or "deep-research-orchestration")[:120],
            "description": str(skill.get("description") or "")[:500],
            "version": str(skill.get("version") or "")[:80],
            "content_hash": str(skill.get("content_hash") or "")[:128],
            "tools": [str(name)[:120] for name in skill.get("tools", []) if isinstance(name, str)][:32]
            if isinstance(skill.get("tools"), list)
            else [],
        }
    session = payload.get("research_session")
    session_snapshot = None
    if isinstance(session, dict) and session.get("research_session_id"):
        session_snapshot = {
            "research_session_id": str(session["research_session_id"])[:128],
            "intake_draft_id": str(session.get("intake_draft_id") or "")[:128],
            "status": str(session.get("status") or "")[:80],
        }
    return {
        "schema_version": "task03-intake-v1",
        "status": status,
        "fields": fields,
        "missing": [name for name in payload.get("missing", []) if name in _INTAKE_FIELD_NAMES]
        if isinstance(payload.get("missing"), list)
        else [],
        "choices": choices,
        "question": str(payload.get("question") or "")[:2000] or None,
        "skill": skill_snapshot,
        "research_session": session_snapshot,
    }


def _intake_projection_for_message(repo, item, owner_id=OWNER_ID):
    if item.role != "assistant":
        return None
    try:
        steps = repo.list_processing_steps(item.message_id, owner_id)
    except Exception:
        logger.warning("unable to load historical intake projection", exc_info=True)
        return None
    for step in reversed(steps):
        if step.kind != "research_intake" or not step.detail_json:
            continue
        try:
            projection = _safe_intake_projection(json.loads(step.detail_json))
        except (TypeError, ValueError):
            continue
        if projection is not None:
            return projection
    return None


def _intake_projection_from_result(result):
    return build_intake_projection(result)


def _persist_intake_projection(repo, assistant_message, result):
    return persist_intake_projection(repo, assistant_message, result)


def _message_payload(item, repo=None, owner_id=OWNER_ID):
    payload = {"message_id": item.message_id, "conversation_id": item.conversation_id, "parent_message_id": item.parent_message_id, "role": item.role, "content": item.content, "status": item.status, "model": item.model, "mode": item.mode, "reasoning_content": item.reasoning_content, "reasoning_status": item.reasoning_status, "reasoning_started_at": item.reasoning_started_at.isoformat() if item.reasoning_started_at else None, "reasoning_completed_at": item.reasoning_completed_at.isoformat() if item.reasoning_completed_at else None, "first_reasoning_at": item.first_reasoning_at.isoformat() if item.first_reasoning_at else None, "first_answer_token_at": item.first_answer_token_at.isoformat() if item.first_answer_token_at else None, "reasoning_truncated": item.reasoning_truncated, "reasoning_chars": item.reasoning_chars, "last_event_seq": item.last_event_seq, "created_at": item.created_at.isoformat(), "completed_at": item.completed_at.isoformat() if item.completed_at else None}
    if repo is not None:
        intake = _intake_projection_for_message(repo, item, owner_id)
        if intake is not None:
            payload["intake"] = intake
            payload["research_intake"] = intake
        report = _research_report_projection(repo, item, owner_id)
        if report is not None:
            payload["report"] = report
            payload["research_report"] = report
    return payload


def _research_report_projection(repo, item, owner_id=OWNER_ID):
    """Project only owner-bound report metadata onto historical messages."""
    if item.role != "assistant":
        return None
    try:
        store = get_provider("research_store")
        tasks, _ = store.list_tasks(owner_id, limit=100)
        task = None
        session = None
        for candidate in tasks:
            if candidate.conversation_id != item.conversation_id:
                continue
            candidate_session = store.get_session_by_task(candidate.research_task_id, owner_id)
            if candidate_session is not None and candidate_session.final_message_id == item.message_id:
                task, session = candidate, candidate_session
                break
        if task is None or session is None:
            return None
        artifacts = store.list_artifacts_for_task(task.research_task_id, owner_id, report_version=task.current_plan_version)
    except Exception:
        logger.warning("unable to load historical research report projection", exc_info=True)
        return None
    if not artifacts:
        return None
    safe_artifacts = []
    for artifact in artifacts:
        if artifact.artifact_type not in {"markdown", "html", "citation_manifest"}:
            continue
        safe_artifacts.append({
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "report_version": artifact.report_version,
            "content_hash": artifact.content_hash,
            "download_url": f"/api/research-sessions/{session.research_session_id}/artifacts/{artifact.artifact_id}/download",
        })
    if not safe_artifacts:
        return None
    citation = next((item for item in safe_artifacts if item["artifact_type"] == "citation_manifest"), None)
    return {
        "report_version": task.current_plan_version,
        "status": task.status,
        "safe_summary": {"artifact_count": len(safe_artifacts), "has_citation_manifest": citation is not None},
        "artifacts": safe_artifacts,
        "citation_manifest": citation,
        "download_url": next((item["download_url"] for item in safe_artifacts if item["artifact_type"] == "html"), None),
    }


def _system_rule_payload(item):
    return {"content": item.content, "enabled": item.enabled, "updated_at": item.updated_at.isoformat()}


def _prior_tool_outputs(repo: MemoryRepository, conversation_id: str, *, exclude_message_id: Optional[str] = None) -> str:
    """收集本会话**已完成历史轮次**的处理步骤并做结构化塌缩。

    spec-038 P3：旧步骤塌缩为一行「工具名 + 状态 + 摘要首行」，最近
    ``CHAT_TOOL_OUTPUT_KEEP_RECENT`` 步保留原文。只取**已有回答内容**的 assistant
    消息（``exclude_message_id`` 为本次在途的 assistant 占位消息，必须排除，否则会把
    本轮刚建的「记忆召回/回答生成」步骤当成历史工具输出注入）。

    失败一律 fail-open 降级为空串，绝不阻断回答装配（塌缩属优化，不是必需路径）。
    """
    try:
        history = repo.list_context_messages(conversation_id, OWNER_ID)
        assistant_ids = [
            m.message_id
            for m in history
            if getattr(m, "role", None) == "assistant"
            and (m.content or "").strip()
            and m.message_id != exclude_message_id
        ]
        steps = []
        for message_id in assistant_ids:
            steps.extend(repo.list_processing_steps(message_id, OWNER_ID))
        if not steps:
            return ""
        return collapse_tool_outputs(steps)
    except Exception:  # noqa: BLE001 — 裁剪失败不阻断回答
        return ""


_CONTEXT_BREAKDOWN_LABELS = {
    "project_instructions": "项目指令",
    # spec-038 起 ``memories`` 表停用，``memory`` 段实际承载的是 spec-022 跨会话召回
    # 注入的最近若干条会话摘要，故标注为「最近跨会话记忆」，而非笼统的「长期记忆 / 摘要」。
    "memory": "最近跨会话记忆",
    "recall": "按需跨会话检索",
    "file_memory": "文件记忆 (USER.md / MEMORY.md)",
    "rag": "知识库检索",
    "history": "会话历史",
    "tool_outputs": "工具调用记录",
    "question": "当前问题",
}


def _build_context_breakdown(sections, budget_tokens: int) -> list[dict]:
    """把 ``compose_chat_prompt(return_sections=True)`` 的 (kind, text) 列表转成占比明细。

    每项含中文 label、估算 token、UTF-8 字节数；按 token 降序，便于「哪个文件占最多」展示。
    ``budget_tokens`` 仅透传备用（前端用它算百分比），本函数不依赖其值。
    """
    rows: list[dict] = []
    for kind, text in sections:
        rows.append({
            "kind": kind,
            "label": _CONTEXT_BREAKDOWN_LABELS.get(kind, kind),
            "tokens": estimate_tokens(text),
            "bytes": len(text.encode("utf-8")),
        })
    rows.sort(key=lambda r: r["tokens"], reverse=True)
    return rows


def compute_context_usage(repo: MemoryRepository, conversation) -> dict:
    """Dry-run 用量估算：与真实装配同源（同一 ``compose_chat_prompt`` + 同一预算配置），
    但只覆盖历史段 + 记忆/摘要段，不触发 RAG 检索、不调用模型、无副作用。

    返回 ``{used_tokens, budget_tokens, ratio, segment_count, compaction_status, breakdown}``；
    ``breakdown`` 为各上下文段落（项目指令 / 记忆 / 文件记忆 / 会话历史 等）的占比明细列表，
    每项含 ``kind / label / tokens / bytes``，供前端圆圈 hover 弹出明细。
    ``budget_tokens <= 0`` 时 ``ratio`` 按 1.0 处理并记录观测，禁止除零崩溃；
    ``compaction_status`` 取该会话最新 job 的 status，无 job 为 ``idle``。
    """
    history = repo.list_context_messages(conversation.conversation_id, OWNER_ID)
    # spec-038：``memories`` 表已停用，DB 长期记忆段不再参与装配；文件记忆快照
    # （USER.md / MEMORY.md / 项目 MD）由 ``compose_chat_prompt`` 内部读盘叠加。
    memories: list = []
    summaries = repo.list_recall_summaries(OWNER_ID, conversation.project_id, budget_chars=CHAT_SUMMARY_BUDGET_CHARS)
    segments = repo.list_conversation_segments(conversation.conversation_id, OWNER_ID, conversation.project_id)
    project_instructions = None
    if conversation.project_id:
        project = repo.get_project(conversation.project_id, OWNER_ID)
        project_instructions = project.instructions if project else None
    prompt_sections = compose_chat_prompt(
        "", history, memories, project_instructions, summaries,
        rag_hits=None, include_question=False, segments=segments,
        return_sections=True,
    )
    prompt_text = "\n\n".join(text for _, text in prompt_sections)
    used_tokens = estimate_tokens(prompt_text)
    budget_tokens = CHAT_TOTAL_TOKEN_BUDGET
    if budget_tokens <= 0:
        logger.warning("CHAT_TOTAL_TOKEN_BUDGET <= 0; context-usage ratio clamped to 1.0")
        ratio = 1.0
    else:
        ratio = used_tokens / budget_tokens
    latest_job = repo.get_latest_compaction_job(conversation.conversation_id, OWNER_ID)
    compaction_status = latest_job.status if latest_job else "idle"
    return {
        "used_tokens": used_tokens,
        "budget_tokens": budget_tokens,
        "ratio": ratio,
        "segment_count": len(segments),
        "compaction_status": compaction_status,
        "breakdown": _build_context_breakdown(prompt_sections, budget_tokens),
    }


@router.get("/system-rule")
def get_system_rule():
    try:
        return _system_rule_payload(_repo().get_system_rule(OWNER_ID))
    except SystemRuleUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "SYSTEM_RULE_UNAVAILABLE", "message": "系统规则暂时不可用", "retryable": True}) from error


@router.put("/system-rule")
def put_system_rule(payload: SystemRulePutRequest):
    try:
        return _system_rule_payload(_repo().upsert_system_rule(OWNER_ID, payload.content, payload.enabled))
    except ValueError as error:
        code = "SYSTEM_RULE_CONFLICT" if payload.enabled and not payload.content.strip() else "INVALID_SYSTEM_RULE"
        raise HTTPException(status_code=409 if code == "SYSTEM_RULE_CONFLICT" else 400, detail={"code": code, "message": str(error), "retryable": False}) from error
    except SystemRuleUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "SYSTEM_RULE_UNAVAILABLE", "message": "系统规则暂时不可用", "retryable": True}) from error


@router.patch("/system-rule")
def patch_system_rule(payload: SystemRulePatchRequest):
    try:
        return _system_rule_payload(_repo().set_system_rule_enabled(OWNER_ID, payload.enabled))
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": "SYSTEM_RULE_CONFLICT", "message": str(error), "retryable": False}) from error
    except SystemRuleUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "SYSTEM_RULE_UNAVAILABLE", "message": "系统规则暂时不可用", "retryable": True}) from error


@router.delete("/system-rule", status_code=204)
def delete_system_rule():
    try:
        _repo().clear_system_rule(OWNER_ID)
    except SystemRuleUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": "SYSTEM_RULE_UNAVAILABLE", "message": "系统规则暂时不可用", "retryable": True}) from error


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreateRequest):
    try:
        return _project_payload(_repo().create_project(OWNER_ID, payload.name, payload.instructions))
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": "PROJECT_EXISTS", "message": str(error), "retryable": False}) from error


@router.get("/projects")
def list_projects(cursor: str | None = None, limit: int = Query(20, ge=1, le=100)):
    try:
        items, next_cursor = _repo().list_projects(OWNER_ID, cursor, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": str(error), "retryable": False}) from error
    return {"projects": [_project_payload(item) for item in items], "next_cursor": next_cursor}


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatchRequest):
    try:
        item = _repo().update_project(project_id, OWNER_ID, **payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": "PROJECT_EXISTS", "message": str(error), "retryable": False}) from error
    if not item:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在", "retryable": False})
    return _project_payload(item)


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: str):
    item = _repo().update_project(project_id, OWNER_ID, status="active")
    if not item:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在", "retryable": False})
    return _project_payload(item)


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(project_id: str):
    if not _repo().get_project(project_id, OWNER_ID):
        raise HTTPException(status_code=404, detail="项目不存在")
    # Knowledge-base source bytes and derived indexes are independent of the
    # project lifecycle.  Detach first; a failure fails closed and preserves
    # the project so an association cannot leak across a future project.
    try:
        clear_project_document_associations(project_id, owner_id=OWNER_ID)
    except Exception as error:
        raise HTTPException(status_code=503, detail={"code": "DOCUMENT_ASSOCIATION_FAILED", "message": "项目文档关联暂时无法解除", "retryable": True}) from error
    # Spec027：项目删除时其 Research Task / 计划 / 事件 / 选集 / 报告随项目删除。
    # 级联走应用层（外键为 RESTRICT，无 DB CASCADE）；与上面同款 fail-closed：
    # 失败则保留项目并返回 503，避免删掉项目后留下无法再被清理的孤儿 research 数据。
    try:
        get_provider("research_service").delete_tasks_for_project(project_id, OWNER_ID)
    except Exception as error:
        raise HTTPException(status_code=503, detail={"code": "RESEARCH_CASCADE_FAILED", "message": "研究任务级联删除暂时无法完成", "retryable": True}) from error
    _repo().delete_project(project_id, OWNER_ID)


def _validate_model(model: str):
    try:
        available = get_available_models()
    except httpx.HTTPError as error:
        # Ollama 不可达：线上模型仍可用，仅当模型既非线上也非本地时才报 503
        if not is_online_model(model):
            raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": "无法连接 Ollama 服务", "retryable": True}) from error
        return
    if model not in available and not is_online_model(model):
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND", "message": f"模型 {model} 不存在", "retryable": False})


def _resolve_request_effort(model: str, requested: str | None, explicit: bool | None = None):
    # ``resolve_reasoning_effort`` 只抛 ``EffortResolutionError``（``ValueError``
    # 子类）：能力探测失败已被 ``get_reasoning_capabilities`` 吸收为 ``stale``/``unknown``
    # （spec-026 Task 02），因此这里不再需要 ``RuntimeError`` 分支（历史实现里的该分支
    # 已成死代码）。异常携带上一轮探测得到的 ``capabilities``，本规范 P2-1 要求**复用**
    # 它而非二次探测（最坏再跑一轮 5 档串行探测，最多 25s）。
    #
    # ``explicit`` 表示「本次请求是否由调用方显式给出档位」。默认按 ``requested is not None``
    # 推断；但会话冻结值与 owner 偏好在库里无记录时都会被填成 ``"xhigh"``
    # （``get_last_reasoning_effort``），此时值非空却**不是**用户本轮的选择，路由层必须
    # 显式传 ``explicit=False`` 才能正确识别。
    if explicit is None:
        explicit = requested is not None
    requested_effort = str(requested if requested is not None else "xhigh").strip().lower()
    try:
        return resolve_reasoning_effort(model, requested)
    except EffortResolutionError as error:
        code = error.code
        if code == "INVALID_REASONING_EFFORT":
            raise HTTPException(status_code=400, detail={"code": code, "message": "推理档位无效", "retryable": False}) from error
        # 走到这里只可能是 REASONING_EFFORT_UNSUPPORTED。``error.capabilities`` 已是
        # 上一轮探测结果，必须区分「能力未知」与「确实不支持」：探测失败且无缓存时
        # ``supported_efforts`` 为空，此时把未知说成「不支持」会误导用户（spec-026 裁决 B）。
        # 有旧缓存（``stale``）时按旧能力集判断，仍不支持才 409。
        capabilities = error.capabilities
        if capabilities.supported_efforts:
            raise HTTPException(status_code=409, detail={"code": "REASONING_EFFORT_UNSUPPORTED", "message": "当前模型不支持该推理档位", "retryable": False}) from error
        # ``off`` 即 ``think=false``，不需要模型具备 thinking 能力，任何模型都安全，
        # 因此能力未知时仍然放行（provider 取值复用 ``_provider_value``，与
        # ``resolve_reasoning_effort`` 一致，避免两处映射漂移，spec-026 P2-3）。
        #
        # 请求**未携带**档位时默认取的 ``xhigh`` 是后端替用户造的默认值：不能因为自己
        # 造的默认值在能力未知时命中不支持，就把整个请求以 503 拒掉 —— 那会复现 spec-026
        # 原本要修掉的「模型能力暂时不可用」烦人报错（探测在模型加载/冷启动时必然抖动）。
        # 只有用户**显式**选择了非 off 档位、且能力未知无法确认时才返回 503。
        if requested_effort == "off" or not explicit:
            provider_value = _provider_value("off")
            return ReasoningResolution(str(model), "off", provider_value, capabilities, {"think": provider_value})
        raise HTTPException(status_code=503, detail={"code": "MODEL_CAPABILITIES_UNAVAILABLE", "message": "模型能力暂时不可用", "retryable": True}) from error


def _reasoning_options_payload(capabilities: "ReasoningCapabilities") -> dict:
    """Serialize capabilities for ``GET /chat/reasoning-options``（spec-026 §端点/接口）。"""
    cached_at = capabilities.cached_at
    if capabilities.source == "unknown" and not cached_at:
        # 探测失败且无任何缓存：该字段表示「本次尝试时间」，不是缓存写入时间。
        cached_at = utc_now().isoformat()
    return {"model": capabilities.model, "supported_efforts": list(capabilities.supported_efforts), "default_effort": capabilities.default_effort, "source": capabilities.source, "cached_at": cached_at}


@router.get("/chat/reasoning-options")
def reasoning_options(model: str | None = None, refresh: int = 0):
    selected = (model or "").strip()
    if not selected:
        from backend.app.platform.config import MODEL_NAME
        selected = MODEL_NAME
    # spec-035 Task05：线上模型不支持 think 档位，直接返回「不支持」（200），
    # 避免被下方 404 拦截，也避免前端因 MODEL_NOT_FOUND 报错。
    if get_online_model(selected) is not None:
        return {"supported": False, "efforts": []}
    try:
        available = get_available_models()
    except httpx.HTTPError:
        # Ollama 不可达时无法区分「服务不可用」与「模型不存在」，因此既不判 404，
        # 也不返回 503：交给能力缓存层给出 ``stale``（有旧结果）或 ``unknown``。
        return _reasoning_options_payload(get_reasoning_capabilities(selected, refresh=bool(refresh)))
    if selected not in available:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND", "message": f"模型 {selected} 不存在", "retryable": False})
    return _reasoning_options_payload(get_reasoning_capabilities(selected, refresh=bool(refresh)))


@router.patch("/conversations/{conversation_id}/reasoning")
def patch_conversation_reasoning(conversation_id: str, payload: ConversationReasoningRequest):
    effort = payload.reasoning_effort
    if effort not in REASONING_EFFORTS:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REASONING_EFFORT", "message": "推理档位无效", "retryable": False})
    repo = _repo()
    conversation = repo.get_conversation(conversation_id, OWNER_ID)
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    try:
        messages, _ = repo.list_messages(conversation_id, OWNER_ID, target_chars=1, limit=2)
        selected_model = next((item.model for item in messages if item.model), None)
    except Exception:
        selected_model = None
    if not selected_model:
        from backend.app.platform.config import MODEL_NAME
        selected_model = MODEL_NAME
    resolution = _resolve_request_effort(selected_model, effort)
    updated, last_effort, updated_at = repo.update_conversation_reasoning(conversation_id, OWNER_ID, resolution.effort)
    payload = _conversation_payload(updated)
    payload.update({"last_reasoning_effort": last_effort, "updated_at": updated_at.isoformat() if updated_at else payload.get("updated_at")})
    return payload


def _redact_sensitive(value: object) -> str:
    """Keep progress/tool summaries useful without persisting credentials or paths."""
    text = " ".join(str(value or "").split())
    import re
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", text)
    return text[:500]


def _iter_run_events(run):
    """Read provider events without confusing iterator failure with completion."""
    iterator = iter(run.events)
    saw_partial_output = False
    saw_answer_token = False
    reasoning_completed = False
    while True:
        try:
            event = next(iterator)
            event_type = event.get("type")
            if event_type in {"thinking", "reasoning_delta", "token"} and event.get("content"):
                saw_partial_output = True
            if event_type == "token" and event.get("content"):
                saw_answer_token = True
            if event_type == "reasoning_completed":
                reasoning_completed = True
            yield event
        except StopIteration:
            return
        except GeneratorExit:
            raise
        except Exception as error:
            # Once the provider has explicitly completed reasoning but has
            # not emitted an answer token, a later provider exception remains
            # a normal chat failure.  The reasoning subphase is already
            # durably completed and must not be rewritten as failed (or
            # emitted twice).  A failure after an answer token is still a
            # resumable stream interruption.
            if saw_partial_output and (saw_answer_token or not reasoning_completed):
                raise ChatStreamInterrupted(f"流式迭代中断：{_redact_sensitive(error)}") from error
            # No provider output was observed. Preserve the normal model
            # failure path (CHAT_FAILED/MODEL_UNAVAILABLE) for initial errors.
            raise


def _message_stream(repo: MemoryRepository, conversation, user_message, assistant_message, model: str, mode: str, reasoning_effort: str | None = None, capabilities_source: str = "cache"):
    def generate():
        stream_started = time.monotonic()
        sequencer = EventSequencer(assistant_message.message_id)
        def frame(event_type: str, **payload):
            output = sequencer.emit(event_type, **payload)
            if output:
                try:
                    repo.record_event_seq(assistant_message.message_id, OWNER_ID, sequencer.event_seq, terminal_status=payload.get("status") if event_type == "done" else None)
                except Exception as error:
                    logger.warning("event sequence persistence unavailable for %s: %s", assistant_message.message_id, error)
            return output
        parts: list[str] = []
        reasoning_parts: list[str] = []
        reasoning_stream_filter = ReasoningStreamFilter()
        reasoning_stream_chars = 0
        reasoning_content_seen = False
        answer_started = False
        reasoning_completed_emitted = False
        selected_effort = reasoning_effort or getattr(conversation, "reasoning_effort", "medium")
        reasoning_started_mono = None
        reasoning_duration_ms = None
        adapter_event_seq = 0
        finished = False
        # spec-038 P1：全局指令改读 L1 文件记忆 USER.md。fail-open——读取失败一律
        # 降级为空串；不再因「系统规则不可用」中断整轮对话。用户全局画像的 CRUD
        # 接口（/api/system-rule）保持原样，供 P2 迁移。
        user_memory = read_user_memory_or_empty()
        try:
            # Raw events are an append-only audit/input stream for the local
            # evolution worker.  They are advisory and never block SSE.
            with contextlib.suppress(Exception):
                repo.append_raw_event(OWNER_ID, conversation.conversation_id, "user_message", {"content": user_message.content}, message_id=user_message.message_id, idempotency_key=f"message:{user_message.message_id}")
            yield frame("meta", project_id=conversation.project_id, conversation_id=conversation.conversation_id, user_message_id=user_message.message_id, assistant_message_id=assistant_message.message_id, model=model, mode=mode, reasoning_effort=selected_effort, capabilities_source=capabilities_source)
            recall_running = repo.create_processing_step(assistant_message.message_id, "memory_recall", "running", label="记忆召回")
            yield frame("progress", step_id=recall_running.step_id, kind=recall_running.kind, label=recall_running.label, status="running", summary=None)
            # spec-038：``memories`` 表已停用，长期记忆改由 MD 文件承载（快照由
            # ``compose_chat_messages`` 内部读盘叠加）。此处保留仍存的
            # ``conversation_summaries`` 召回，并新增 L2 FTS5 跨会话检索
            # （``session_search``）——它索引历史消息与 MD 记忆笔记，是 spec-038 P2
            # 真正的跨会话记忆入口；旧的 ``memories`` 表召回已废弃，必须用它才能翻旧账。
            # 任何失败均 fail-open：绝不因检索异常中断整轮对话。
            try:
                memories = []
                summaries = repo.list_recall_summaries(OWNER_ID, conversation.project_id, query=user_message.content, budget_chars=CHAT_SUMMARY_BUDGET_CHARS)
                # L2：FTS5 检索历史会话 + MD 记忆笔记；排除当前进行中的会话，
                # 避免把本回合对话当“记忆”回灌。MD 笔记 conversation_id 为 NULL，保留。
                recall_hits: list[dict] = []
                try:
                    l2 = search_sessions(user_message.content, owner_id=OWNER_ID, match_mode="or")
                    # 排除当前会话后，按 bm25 相关度取前 5 条注入；截掉长尾噪声
                    # （如本会话早期的“我答不上来”、DeFi/记忆层讨论等弱相关命中），
                    # 既保住真正的跨会话答案，又不让弱模型被无关历史带偏。
                    recall_hits = [
                        hit for hit in l2.get("hits", [])
                        if hit.get("conversation_id") != conversation.conversation_id
                    ][:5]
                except Exception:
                    logger.warning("L2 session_search 召回失败，降级跳过", exc_info=True)
                recall_status = "completed"
                recall_summary = (
                    f"召回 {len(summaries)} 条会话摘要、L2 FTS5 命中 {len(recall_hits)} 条"
                )
            except Exception:
                # Memory is advisory context. A corrupt/locked memory read must
                # not prevent ordinary chat from continuing.
                memories = []
                summaries = []
                recall_hits = []
                recall_status = "failed"
                recall_summary = "记忆召回失败，已跳过"
            recall_done = repo.create_processing_step(assistant_message.message_id, "memory_recall", recall_status, recall_summary, label="记忆召回")
            yield frame("progress", step_id=recall_done.step_id, kind=recall_done.kind, label=recall_done.label, status=recall_status, summary=recall_done.summary)
            if user_memory:
                applied = repo.create_processing_step(assistant_message.message_id, "system_rule", "completed", "已应用系统规则", label="已应用系统规则")
                yield frame("progress", step_id=applied.step_id, kind=applied.kind, label=applied.label, status="completed", summary=applied.summary)
            project_instructions = None
            if conversation.project_id:
                project = repo.get_project(conversation.project_id, OWNER_ID)
                project_instructions = project.instructions if project else None
            rag_hits = []
            # Retrieval is opt-in for a project with at least one visible
            # document.  Unbound conversations never query project documents.
            if conversation.project_id:
                try:
                    visible_documents = list_documents_for_project(conversation.project_id, owner_id=OWNER_ID)
                except Exception:
                    visible_documents = []
                if visible_documents:
                    rag_running = repo.create_processing_step(assistant_message.message_id, "rag_retrieval", "running", label="知识库检索")
                    yield frame("progress", step_id=rag_running.step_id, kind=rag_running.kind, label=rag_running.label, status="running", summary=None)
                    try:
                        # Reuse the canonical dense+sparse/RRF/reranker facade.
                        # The same canonical allowlist reaches both dense and
                        # sparse query legs before RRF/reranking/top-k.
                        document_ids = [record["document_id"] for record in visible_documents]
                        rag_hits = hybrid_search(
                            user_message.content,
                            top_k=10,
                            document_ids=document_ids,
                        )[:5]
                        rag_done = repo.create_processing_step(assistant_message.message_id, "rag_retrieval", "completed", f"召回 {len(rag_hits)} 条知识库证据", label="知识库检索")
                        yield frame("progress", step_id=rag_done.step_id, kind=rag_done.kind, label=rag_done.label, status="completed", summary=rag_done.summary)
                    except Exception:
                        rag_hits = []
                        rag_failed = repo.create_processing_step(assistant_message.message_id, "rag_retrieval", "failed", "知识库检索失败，已跳过", label="知识库检索")
                        yield frame("progress", step_id=rag_failed.step_id, kind=rag_failed.kind, label=rag_failed.label, status="failed", summary=rag_failed.summary)
            history = [message for message in repo.list_context_messages(conversation.conversation_id, OWNER_ID) if message.message_id != user_message.message_id]
            if sum(len(message.content or "") for message in history) > 12000:
                with contextlib.suppress(Exception):
                    repo.append_raw_event(OWNER_ID, conversation.conversation_id, "context_pressure", {"summary": "会话上下文达到整理阈值"}, message_id=user_message.message_id, idempotency_key=f"pressure:{user_message.message_id}")
            segments = repo.list_conversation_segments(conversation.conversation_id, OWNER_ID, conversation.project_id)
            # spec-038 P3：工具输出预裁剪。旧步骤结构化塌缩成一行，最近 N 步保留原文，
            # 降低上下文占用；塌缩逻辑单点在 context_compaction.collapse_tool_outputs。
            tool_outputs = _prior_tool_outputs(
                repo, conversation.conversation_id, exclude_message_id=assistant_message.message_id
            )
            messages = compose_chat_messages(user_message.content, history, memories, project_instructions, summaries, rag_hits=rag_hits, system_rule=user_memory or None, segments=segments, project_id=conversation.project_id, tool_outputs=tool_outputs, recall_hits=recall_hits)
            # Spec025 Task04：装配后按阈值自动触发后台异步压缩；绝不阻塞本次响应，
            # 失败只记录观测（与既有 context_pressure 事件并存，不改其语义）。
            try:
                usage = compute_context_usage(repo, conversation)
                if usage["ratio"] >= CHAT_COMPACT_TRIGGER_RATIO:
                    get_compaction_worker(repo).enqueue(
                        conversation.conversation_id, OWNER_ID, conversation.project_id,
                        "auto", est_tokens_before=usage["used_tokens"],
                    )
            except Exception as error:
                logger.warning("auto context compaction trigger failed: %s", error)
            repo.update_message(assistant_message.message_id, OWNER_ID, status="streaming")
            generation_running = repo.create_processing_step(assistant_message.message_id, "generation", "running", label="回答生成")
            yield frame("progress", step_id=generation_running.step_id, kind=generation_running.kind, label=generation_running.label, status="running", summary=None)
            run = run_chat(user_message.content, model, messages=messages, reasoning_effort=selected_effort)
            reasoning_started_at = None
            reasoning_seen = False
            if selected_effort != "off":
                reasoning_started_at = time.monotonic()
                reasoning_started_mono = reasoning_started_at
                reasoning_seen = True
                started_iso = utc_now().isoformat()
                repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="running", started_at=started_iso, first_reasoning_at=None, last_event_seq=sequencer.event_seq)
                yield frame("reasoning_started", effort=selected_effort, started_at=started_iso)
            for event in _iter_run_events(run):
                if event.get("event_seq") is not None:
                    incoming_seq = int(event["event_seq"])
                    if incoming_seq <= adapter_event_seq:
                        continue
                    if incoming_seq != adapter_event_seq + 1:
                        repo.update_message(assistant_message.message_id, OWNER_ID, status="failed")
                        yield frame("error", code="EVENT_SEQUENCE_GAP", message="事件序列中断", retryable=False)
                        yield frame("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="failed", duration_ms=max(0.0, (time.monotonic() - stream_started) * 1000.0), reasoning_duration_ms=reasoning_duration_ms, answer_duration_ms=max(0.0, (time.monotonic() - stream_started) * 1000.0))
                        return
                    adapter_event_seq = incoming_seq
                if event.get("type") in {"error", "tool_error"}:
                    with contextlib.suppress(Exception):
                        repo.append_raw_event(OWNER_ID, conversation.conversation_id, "tool_failure", {"error": _redact_sensitive(event.get("message") or event.get("content") or "工具失败"), "verified": False}, message_id=user_message.message_id, idempotency_key=f"tool-failure:{user_message.message_id}")
                if event.get("type") in {"thinking", "reasoning_delta"} and selected_effort != "off" and not answer_started:
                    clean = reasoning_stream_filter.push(event.get("content") or "")
                    if clean:
                        if not reasoning_content_seen:
                            reasoning_content_seen = True
                            repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, first_reasoning_at=utc_now().isoformat(), last_event_seq=sequencer.event_seq)
                        if not reasoning_seen:
                            reasoning_started_at = time.monotonic()
                            reasoning_seen = True
                            repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="running", started_at=utc_now().isoformat(), first_reasoning_at=utc_now().isoformat(), last_event_seq=sequencer.event_seq)
                            yield frame("reasoning_started", effort=selected_effort, started_at=utc_now().isoformat())
                        reasoning_parts.append(clean)
                        filtered, truncated = filter_reasoning(reasoning_parts)
                        reasoning_parts[:] = [filtered]
                        repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, content=filtered, status="running", truncated=truncated, chars=len(filtered), last_event_seq=sequencer.event_seq)
                        # Keep the live panel bounded as well as the durable
                        # field; otherwise many deltas could exceed the
                        # 20,000-code-point contract before persistence trims.
                        remaining = max(0, MAX_REASONING_CODEPOINTS - reasoning_stream_chars)
                        visible_clean = clean[:remaining]
                        reasoning_stream_chars += len(visible_clean)
                        if visible_clean:
                            yield frame("reasoning_delta", content=visible_clean)
                if event.get("type") == "reasoning_completed" and selected_effort != "off" and reasoning_seen:
                    # Some adapters expose an explicit reasoning terminal
                    # event before the first answer token.  Treat it as the
                    # authoritative subphase transition so a later provider
                    # failure cannot regress the durable reasoning state.
                    completed_iso = utc_now().isoformat()
                    provider_status = event.get("status") or "completed"
                    if provider_status not in {"completed", "failed", "interrupted"}:
                        provider_status = "completed"
                    duration = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                    reasoning_duration_ms = duration
                    repo.update_message_reasoning(
                        assistant_message.message_id,
                        OWNER_ID,
                        status=provider_status,
                        completed_at=completed_iso,
                        last_event_seq=sequencer.event_seq,
                    )
                    yield frame("reasoning_completed", status=provider_status, duration_ms=duration, completed_at=completed_iso)
                    reasoning_seen = False
                    reasoning_completed_emitted = True
                if event.get("type") == "token":
                    token = event.get("content", ""); parts.append(token)
                    answer_started = True
                    if reasoning_seen:
                        tail = reasoning_stream_filter.finish()
                        if tail:
                            reasoning_parts.append(tail)
                            filtered, truncated = filter_reasoning(reasoning_parts)
                            repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, content=filtered, truncated=truncated, chars=len(filtered), last_event_seq=sequencer.event_seq)
                            # ``tail`` is flushed after the last chunk and must
                            # consume the same live SSE budget as ordinary
                            # reasoning deltas.  Durable persistence is
                            # truncated separately, so cap the wire stream too.
                            remaining = max(0, MAX_REASONING_CODEPOINTS - reasoning_stream_chars)
                            visible_tail = tail[:remaining]
                            reasoning_stream_chars += len(visible_tail)
                            if visible_tail:
                                yield frame("reasoning_delta", content=visible_tail)
                        completed_iso = utc_now().isoformat()
                        duration = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                        reasoning_duration_ms = duration
                        repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="completed", completed_at=completed_iso, last_event_seq=sequencer.event_seq)
                        yield frame("reasoning_completed", status="completed", duration_ms=duration, completed_at=completed_iso)
                        reasoning_seen = False
                        reasoning_completed_emitted = True
                    repo.update_message(assistant_message.message_id, OWNER_ID, content="".join(parts), status="streaming", first_answer_token_at=utc_now().isoformat() if not parts[:-1] else None, last_event_seq=sequencer.event_seq)
                    yield frame("token", content=token)
            # A direct provider can return already-generated chunks together
            # with an abnormal end marker.  It is not a successful completion.
            if getattr(run.result, "interrupted", False) or (
                run.route == "direct" and run.result is not None and not getattr(run.result, "completed_normally", False)
            ):
                raise ChatStreamInterrupted("Ollama 流式连接中断，已保存部分内容")
            content = "".join(parts)
            try:
                record_ollama_generation(
                    model=model,
                    prompt_messages=redact_prompt_messages(messages),
                    result=run.result,
                    route=run.route,
                    started_at=utc_now(),
                    tags=["conversation"],
                    extra_metadata={key: value for key, value in {"reasoning_status": "completed" if selected_effort != "off" else None, "reasoning_duration_ms": reasoning_duration_ms, "answer_duration_ms": max(0.0, (time.monotonic() - stream_started) * 1000.0)}.items() if value is not None},
                )
            except Exception:
                pass
            generation_done = repo.create_processing_step(assistant_message.message_id, "generation", "completed", "回答已生成", label="回答生成")
            yield frame("progress", step_id=generation_done.step_id, kind=generation_done.kind, label=generation_done.label, status="completed", summary=generation_done.summary)
            if rag_hits:
                # Sources are deliberately emitted only after the final token
                # and generation completion event.  The frontend may render
                # either the canonical ``sources`` field or its citations alias.
                sources = citation_payloads(rag_hits)[:5]
                yield frame("sources", sources=sources, citations=sources)
            repo.finalize_processing_steps(assistant_message.message_id, status="completed")
            if reasoning_seen:
                tail = reasoning_stream_filter.finish()
                if tail:
                    reasoning_parts.append(tail)
                    filtered, truncated = filter_reasoning(reasoning_parts)
                    repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, content=filtered, truncated=truncated, chars=len(filtered), last_event_seq=sequencer.event_seq)
                    # The carry flushed by ``finish`` is part of the same
                    # reasoning stream; do not let it exceed the 20,000-char
                    # SSE contract after the prior deltas have been emitted.
                    remaining = max(0, MAX_REASONING_CODEPOINTS - reasoning_stream_chars)
                    visible_tail = tail[:remaining]
                    reasoning_stream_chars += len(visible_tail)
                    if visible_tail:
                        yield frame("reasoning_delta", content=visible_tail)
                reasoning_duration_ms = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                completed_iso = utc_now().isoformat()
                repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="completed", completed_at=completed_iso, last_event_seq=sequencer.event_seq)
                yield frame("reasoning_completed", status="completed", duration_ms=reasoning_duration_ms, completed_at=completed_iso)
                reasoning_seen = False
                reasoning_completed_emitted = True
            answer_duration_ms = max(0.0, (time.monotonic() - stream_started) * 1000.0)
            repo.update_message(assistant_message.message_id, OWNER_ID, content=content, status="completed")
            # All durable completed state and the final reasoning transition
            # are written before exposing the terminal SSE event.  A client
            # disconnect during earlier progress/reasoning events therefore
            # remains recoverable as interrupted.
            finished = True
            yield frame("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="completed", duration_ms=answer_duration_ms, reasoning_duration_ms=reasoning_duration_ms, answer_duration_ms=answer_duration_ms)
        except GeneratorExit:
            raise
        except ChatStreamInterrupted as error:
            content = "".join(parts)
            try:
                repo.update_message(assistant_message.message_id, OWNER_ID, content=content, status="interrupted")
                if reasoning_seen and not reasoning_completed_emitted:
                    interrupted_iso = utc_now().isoformat()
                    reasoning_duration_ms = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                    repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="interrupted", completed_at=interrupted_iso, chars=len(reasoning_parts[0]) if reasoning_parts else 0)
                    yield frame("reasoning_completed", status="interrupted", duration_ms=reasoning_duration_ms, completed_at=interrupted_iso)
                    reasoning_seen = False
                    reasoning_completed_emitted = True
                interrupted_step = repo.create_processing_step(assistant_message.message_id, "generation", "interrupted", "流式连接中断，已保存已生成内容", label="回答生成")
                yield frame("progress", step_id=interrupted_step.step_id, kind=interrupted_step.kind, label=interrupted_step.label, status="interrupted", summary=interrupted_step.summary)
                yield frame("error", code="STREAM_INTERRUPTED", message="流式连接中断，已保存已生成内容", retryable=True)
                repo.finalize_processing_steps(assistant_message.message_id, status="interrupted", summary="流式连接中断，未完成步骤已终止")
                duration_ms = max(0.0, (time.monotonic() - stream_started) * 1000.0)
                yield frame("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="interrupted", duration_ms=duration_ms, reasoning_duration_ms=reasoning_duration_ms, answer_duration_ms=duration_ms)
            except Exception:
                # The finally block below still performs the durable fallback
                # when the response has already become unwritable.
                pass
        except Exception as error:
            content = "".join(parts)
            try:
                repo.update_message(assistant_message.message_id, OWNER_ID, content=content, status="failed")
                generation_failed = repo.create_processing_step(assistant_message.message_id, "generation", "failed", "回答生成失败", label="回答生成")
                yield frame("progress", step_id=generation_failed.step_id, kind=generation_failed.kind, label=generation_failed.label, status="failed", summary=generation_failed.summary)
                if reasoning_seen and not reasoning_completed_emitted:
                    reasoning_duration_ms = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                    completed_iso = utc_now().isoformat()
                    repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="failed", completed_at=completed_iso, last_event_seq=sequencer.event_seq)
                    yield frame("reasoning_completed", status="failed", duration_ms=reasoning_duration_ms, completed_at=completed_iso)
                    reasoning_seen = False
                    reasoning_completed_emitted = True
                yield frame("error", code="CHAT_FAILED", message=_redact_sensitive(error), retryable=True)
                repo.finalize_processing_steps(assistant_message.message_id, status="failed", summary="回答失败，未完成步骤已终止")
                answer_duration_ms = max(0.0, (time.monotonic() - stream_started) * 1000.0)
                yield frame("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="failed", duration_ms=answer_duration_ms, reasoning_duration_ms=reasoning_duration_ms, answer_duration_ms=answer_duration_ms)
            except Exception:
                # Preserve the original failure and let the finally block make
                # a best-effort durable status update.
                pass
        finally:
            try:
                get_memory_evolution_worker(repo).enqueue_session(conversation.conversation_id)
            except Exception as error:
                logger.warning("memory evolution enqueue unavailable: %s", error)
                pass
            if not finished:
                try:
                    current = repo.get_message(assistant_message.message_id, OWNER_ID)
                    if current and current.status in {"pending", "streaming"}:
                        repo.update_message(assistant_message.message_id, OWNER_ID, content="".join(parts), status="interrupted")
                        if current.reasoning_status == "running":
                            repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="interrupted", completed_at=utc_now().isoformat(), chars=len(current.reasoning_content or ""))
                        repo.create_processing_step(assistant_message.message_id, "generation", "interrupted", "流式连接中断，已保存已生成内容", label="回答生成")
                    repo.finalize_processing_steps(assistant_message.message_id, status="interrupted", summary="流式连接中断，未完成步骤已终止")
                except Exception:
                    pass
    return generate()


def _intake_stream(repo, conversation, user_message, assistant_message, result, model, mode, reasoning_effort):
    """Serialize a durable Intake result using the existing conversation SSE shape."""
    owner_id = getattr(user_message, "owner_id", OWNER_ID)
    def generate():
        started = time.monotonic()
        sequencer = EventSequencer(assistant_message.message_id)

        def frame(event_type: str, **payload):
            output = sequencer.emit(event_type, **payload)
            if output:
                try:
                    repo.record_event_seq(
                        assistant_message.message_id,
                        owner_id,
                        sequencer.event_seq,
                        terminal_status=payload.get("status") if event_type == "done" else None,
                    )
                except Exception as error:
                    logger.warning("intake event sequence persistence unavailable: %s", error)
            return output

        try:
            _persist_intake_projection(repo, assistant_message, result)
        except Exception:
            # The SSE response remains useful if a projection write is
            # temporarily unavailable; the error is observable in logs and
            # the next turn can retry its own durable projection.
            logger.exception("unable to persist research intake projection")
        yield frame(
            "meta",
            project_id=conversation.project_id,
            conversation_id=conversation.conversation_id,
            user_message_id=user_message.message_id,
            assistant_message_id=assistant_message.message_id,
            model=model,
            mode=mode,
            reasoning_effort=reasoning_effort,
        )
        if result.activation:
            yield frame(
                "skill_activation",
                status="completed" if result.activation.get("ok") else "failed",
                skill=(result.activation.get("skill") or {}).get("name"),
                description=(result.activation.get("skill") or {}).get("description"),
            )
        if result.status == "active_conflict":
            # This is an interactive, recoverable choice rather than a
            # failed turn.  Keep the assistant completed so the user can
            # choose how to proceed and preserve the active Session.
            content = "当前会话已有进行中的研究，请选择修改当前研究、取消后新建或在新会话研究。"
            repo.update_message(assistant_message.message_id, owner_id, content=content, status="completed")
            yield frame(
                "intake",
                status=result.status,
                research_session=(result.session.to_dict() if result.session else None),
                fields=[],
                missing=[],
                choices=result.choices,
                question=None,
            )
            yield frame(
                "done",
                conversation_id=conversation.conversation_id,
                message_id=assistant_message.message_id,
                status="completed",
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return
        if result.error:
            content = result.error.get("message", "研究请求暂时无法处理")
            repo.update_message(assistant_message.message_id, owner_id, content=content, status="failed")
            yield frame("error", **result.error)
            yield frame(
                "done",
                conversation_id=conversation.conversation_id,
                message_id=assistant_message.message_id,
                status="failed",
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return
        field_payload = [
            {**item.to_dict(), "message_id": item.updated_by_message_id}
            for item in result.fields
        ]
        if result.status == "clarification":
            content = result.question or "请说明是否要进行深度研究。"
        elif result.status == "active_conflict":
            content = result.error.get("message", "当前会话已有进行中的研究") if result.error else "当前会话已有进行中的研究"
        else:
            content = result.question or "研究 Intake 已保存，参数齐全后将生成计划。"
        repo.update_message(assistant_message.message_id, owner_id, content=content, status="completed")
        yield frame(
            "intake",
            status=result.status,
            research_session=(result.session.to_dict() if result.session else None),
            fields=field_payload,
            missing=result.missing,
            choices=result.choices,
            question=result.question,
        )
        yield frame(
            "done",
            conversation_id=conversation.conversation_id,
            message_id=assistant_message.message_id,
            status="completed",
            duration_ms=(time.monotonic() - started) * 1000,
        )
    return generate()


def _failed_message_stream(repo, conversation, user_message, assistant_message, detail):
    """Return a durable failed turn after the user/assistant rows exist."""
    if isinstance(detail, dict):
        code = str(detail.get("code", "MODEL_UNAVAILABLE"))
        message = str(detail.get("message", "模型暂时不可用"))
        retryable = bool(detail.get("retryable", True))
    else:
        code, message, retryable = "MODEL_UNAVAILABLE", "模型暂时不可用", True
    owner_id = getattr(user_message, "owner_id", OWNER_ID)
    repo.update_message(assistant_message.message_id, owner_id, content=message, status="failed")

    def generate():
        yield stream_event(
            "meta",
            project_id=conversation.project_id,
            conversation_id=conversation.conversation_id,
            user_message_id=user_message.message_id,
            assistant_message_id=assistant_message.message_id,
            model=user_message.model,
            mode=user_message.mode,
        )
        yield stream_event("error", code=code, message=message, retryable=retryable)
        yield stream_event(
            "done",
            conversation_id=conversation.conversation_id,
            message_id=assistant_message.message_id,
            status="failed",
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


def _start_message(payload: ConversationMessageRequest, conversation_id: str | None = None):
    content = (payload.content or payload.question or payload.message or "").strip()
    if not content or len(content) > 20000:
        raise HTTPException(status_code=400, detail={"code": "INVALID_MESSAGE", "message": "消息不能为空且最多支持 20000 个字符", "retryable": False})
    repo = _repo()
    if conversation_id:
        conversation = repo.get_conversation(conversation_id, OWNER_ID)
        if not conversation:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    else:
        conversation = None
    # An explicitly selected non-off effort must be rejected as a real HTTP
    # 503 when capability probing is unavailable.  The normal message path
    # intentionally persists a failed turn for model/unsupported-effort
    # failures, so only this capability-unknown branch is preflighted before
    # the first conversation/message write.  Reuse a successful resolution
    # below to avoid probing the same model twice.
    preflight_resolution = None
    requested_effort = str(payload.reasoning_effort or "").strip().lower()
    if payload.reasoning_effort is not None and requested_effort not in {"", "off"}:
        try:
            _validate_model(payload.model)
        except HTTPException:
            # Preserve the historical durable failed-turn contract for model
            # availability/not-found errors; the post-persistence path emits
            # its SSE error frame as before.
            pass
        else:
            try:
                preflight_resolution = _resolve_request_effort(
                    payload.model, payload.reasoning_effort, explicit=True
                )
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, dict) else {}
                if (
                    error.status_code == 503
                    and detail.get("code") == "MODEL_CAPABILITIES_UNAVAILABLE"
                ):
                    raise
                # Known unsupported/invalid effort keeps the established
                # post-persistence SSE mapping; only unknown capability is a
                # transport-level availability failure.
    # Freeze the turn in the existing conversation store before any model or
    # Skill/Intake preflight.  A failed preflight must remain recoverable.
    try:
        if conversation_id:
            conversation, user, assistant = repo.create_message_pair(
                conversation.conversation_id,
                OWNER_ID,
                content,
                model=payload.model,
                mode=payload.mode,
                reasoning_effort=payload.reasoning_effort,
                update_preference=payload.reasoning_effort is not None,
            )
        else:
            conversation, user, assistant = repo.create_conversation_messages(
                OWNER_ID,
                content,
                payload.project_id,
                payload.model,
                payload.mode,
                payload.reasoning_effort,
                update_preference=payload.reasoning_effort is not None,
            )
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND" if conversation_id else "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": "PROJECT_NOT_ACTIVE", "message": str(error), "retryable": False}) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail={"code": "MESSAGE_TRANSACTION_FAILED", "message": "消息与会话偏好更新未完成", "retryable": True}) from error

    try:
        _validate_model(payload.model)
    except HTTPException as error:
        return _failed_message_stream(repo, conversation, user, assistant, error.detail)
    if preflight_resolution is not None:
        resolution = preflight_resolution
    else:
        try:
            requested_effort = payload.reasoning_effort if payload.reasoning_effort is not None else conversation.reasoning_effort
            resolution = _resolve_request_effort(payload.model, requested_effort, explicit=payload.reasoning_effort is not None)
        except HTTPException as error:
            return _failed_message_stream(repo, conversation, user, assistant, error.detail)
    # Persist the message-bound analysis job before opening SSE.  Only queueing
    # happens on the request path; classification and memory writes are fully
    # independent of answer generation.
    try:
        analysis_job = repo.create_memory_analysis_job(user.message_id, OWNER_ID)
        get_memory_analysis_worker(repo).enqueue(analysis_job.analysis_id)
    except Exception as error:
        logger.warning("memory analysis enqueue unavailable: %s", error)
    # Starting the local evolution worker is cheap and scans durable retry
    # work.  Its failures are advisory and never block chat delivery.
    try:
        get_memory_evolution_worker(repo)
    except Exception as error:
        # Worker startup/scanning is advisory.  The durable event is already
        # written by the stream and can be picked up by a later retry/startup;
        # never turn worker initialization into a chat failure.
        logger.warning("memory evolution worker startup unavailable: %s", error)
        pass
    classification = ResearchIntakeCoordinator.classify(content)
    try:
        intake = get_provider("research_intake_coordinator").handle_message(
            conversation.conversation_id, OWNER_ID, user.message_id, content
        )
    except Exception:
        # Research persistence/Skill discovery is optional for ordinary chat.
        # A research-shaped turn gets a diagnosable failed SSE; ordinary chat
        # continues through the established model stream.
        logger.exception("research intake unavailable")
        intake = None
        if classification in {"explicit", "ambiguous"}:
            return _failed_message_stream(
                repo,
                conversation,
                user,
                assistant,
                {"code": "INTAKE_UNAVAILABLE", "message": "研究 Intake 暂时不可用，请稍后重试。", "retryable": True},
            )
        try:
            repo.create_processing_step(
                assistant.message_id,
                "research_intake",
                "failed",
                "研究 Intake 不可用，已回退普通聊天",
                label="研究 Intake",
            )
        except Exception:
            logger.warning("unable to persist research intake fallback marker", exc_info=True)
    if intake is not None and intake.status != "ordinary":
        return StreamingResponse(
            _intake_stream(repo, conversation, user, assistant, intake, payload.model, payload.mode, resolution.effort),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return StreamingResponse(_message_stream(repo, conversation, user, assistant, payload.model, payload.mode, resolution.effort, resolution.capabilities.source), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/messages")
def create_first_message(payload: ConversationMessageRequest):
    return _start_message(payload)


@router.post("/conversations/{conversation_id}/messages")
def create_message(conversation_id: str, payload: ConversationMessageRequest):
    return _start_message(payload, conversation_id)


@router.get("/conversations/{conversation_id}/context-usage")
def get_context_usage(conversation_id: str):
    repo = _repo()
    conversation = repo.get_conversation(conversation_id, OWNER_ID)
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return compute_context_usage(repo, conversation)


@router.post("/conversations/{conversation_id}/compactions")
def create_compaction(conversation_id: str):
    repo = _repo()
    conversation = repo.get_conversation(conversation_id, OWNER_ID)
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    # 已有非终态 job：直接 409，不重复入队（DB 部分唯一索引仍为唯一可靠去重）。
    existing = repo.get_latest_compaction_job(conversation_id, OWNER_ID)
    if existing is not None and existing.status not in {"done", "failed"}:
        raise HTTPException(status_code=409, detail={"code": "COMPACTION_IN_PROGRESS", "message": "压缩进行中", "retryable": False})
    worker = get_compaction_worker(repo)
    try:
        job = worker.enqueue(conversation_id, OWNER_ID, conversation.project_id, "manual")
    except Exception as error:
        raise HTTPException(status_code=500, detail={"code": "COMPACTION_ENQUEUE_FAILED", "message": str(error) or "压缩入队失败", "retryable": True}) from error
    if job is None:
        raise HTTPException(status_code=409, detail={"code": "COMPACTION_IN_PROGRESS", "message": "压缩进行中", "retryable": False})
    return {"job_id": job.job_id, "status": job.status, "trigger": "manual"}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    item = _repo().get_conversation(conversation_id, OWNER_ID)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return _conversation_payload(item)


@router.get("/conversations")
def list_conversations(project_id: str | None = None, cursor: str | None = None, limit: int = Query(20, ge=1, le=100), status: str | None = None, unbound_only: bool = False):
    try:
        items, next_cursor = _repo().list_conversations(OWNER_ID, project_id, cursor, limit, status=status, unbound_only=unbound_only)
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error:
        code = "INVALID_CONVERSATION_FILTER" if str(error) in {"invalid conversation status", "unbound_only cannot be combined with project_id"} else "INVALID_CURSOR"
        raise HTTPException(status_code=400, detail={"code": code, "message": str(error), "retryable": False}) from error
    return {"conversations": [_conversation_payload(item) for item in items], "next_cursor": next_cursor}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, before: str | None = None, target_chars: int = Query(4000, ge=1, le=100000)):
    repo = _repo()
    try:
        items, next_cursor = repo.list_messages(conversation_id, OWNER_ID, before=before, target_chars=target_chars)
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": str(error), "retryable": False}) from error
    return {"messages": [_message_payload(item, repo, OWNER_ID) for item in items], "next_cursor": next_cursor}


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, payload: ConversationPatchRequest):
    try:
        item = _repo().update_conversation(conversation_id, OWNER_ID, **payload.model_dump(exclude_unset=True))
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": "CONVERSATION_CONFLICT", "message": str(error), "retryable": False}) from error
    if not item:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return _conversation_payload(item)


@router.post("/conversations/{conversation_id}/restore")
def restore_conversation(conversation_id: str):
    try:
        item = _repo().update_conversation(conversation_id, OWNER_ID, status="active")
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": "CONVERSATION_CONFLICT", "message": str(error), "retryable": False}) from error
    if not item:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return _conversation_payload(item)


@router.delete("/conversations/{conversation_id}", status_code=204)
def remove_conversation(conversation_id: str):
    if not _repo().delete_conversation(conversation_id, OWNER_ID):
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/messages/{message_id}/processing-steps")
def get_processing_steps(message_id: str):
    steps = _repo().list_processing_steps(message_id, OWNER_ID)
    if not steps and not _repo().get_message(message_id, OWNER_ID):
        raise HTTPException(status_code=404, detail="消息不存在")
    # Keep the historical flat shape and append the v2 adjacency fields.  Old
    # clients ignore unknown keys; tree-capable clients use parent_step_id and
    # stable node_key/source_event_id for incremental upserts.
    return {"steps": [s.to_dict() for s in steps]}


def _analysis_job_payload(job):
    return {
        "analysis_id": job.analysis_id,
        "user_message_id": job.user_message_id,
        "project_id_snapshot": job.project_id_snapshot,
        "status": job.status,
        "model": job.model,
        "cursor": job.cursor,
        "batch_no": job.batch_no,
        "saved_count": job.saved_count,
        "pending_count": job.pending_count,
        "failed_count": job.failed_count,
        "error_code": job.error_code,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _analysis_item_payload(item):
    return {
        "item_id": item.item_id,
        "analysis_id": item.analysis_id,
        "statement": item.statement,
        "suggested_scope": item.suggested_scope,
        "confidence": item.confidence,
        "rationale_summary": item.rationale_summary,
        "decision_status": item.decision_status,
        "memory_id": item.memory_id,
        "created_at": item.created_at.isoformat(),
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
    }


@router.get("/messages/{user_message_id}/memory-analysis")
def get_memory_analysis(user_message_id: str, cursor: str | None = None, limit: int = Query(10, ge=1, le=100)):
    repo = _repo()
    try:
        job = repo.get_memory_analysis_job(user_message_id, OWNER_ID)
        if not job:
            if not repo.get_message(user_message_id, OWNER_ID):
                raise LookupError("user message not found")
            raise LookupError("memory analysis not found")
        items, next_cursor = repo.list_memory_analysis_items(user_message_id, OWNER_ID, cursor=cursor, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": str(error), "retryable": False}) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "MEMORY_ANALYSIS_NOT_FOUND", "message": str(error), "retryable": False}) from error
    summary = _analysis_job_payload(job)
    return {"job": summary, "analysis": summary, "items": [_analysis_item_payload(item) for item in items], "next_cursor": next_cursor}


def _analysis_item_decision(item_id: str, payload: MemoryAnalysisDecisionRequest):
    repo = _repo()
    item = repo.get_memory_analysis_item(item_id, OWNER_ID)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "MEMORY_ANALYSIS_ITEM_NOT_FOUND", "message": "分析结果不存在", "retryable": False})
    if item.decision_status != "pending_confirmation":
        return item
    job = repo.get_memory_analysis_job_by_id(item.analysis_id, OWNER_ID)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "MEMORY_ANALYSIS_NOT_FOUND", "message": "分析任务不存在", "retryable": False})
    if payload.decision == "ignore":
        return repo.update_memory_analysis_item(item_id, OWNER_ID, decision_status="ignored")
    source_message = repo.get_message(job.user_message_id, OWNER_ID)
    source_text = source_message.content if source_message else ""
    if is_system_rule_intent(source_text):
        raise HTTPException(status_code=409, detail={"code": "SYSTEM_RULE_REQUIRES_EXPLICIT_SAVE", "message": "系统规则建议必须在系统规则编辑器中显式保存", "retryable": False})
    scope = "global" if payload.decision == "save_global" else "project"
    if scope == "global" and not has_explicit_global_intent(source_text):
        raise HTTPException(status_code=409, detail={"code": "GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT", "message": "原始消息未明确要求全局范围", "retryable": False})
    if scope == "project" and job.project_id_snapshot and payload.project_id and payload.project_id != job.project_id_snapshot:
        raise HTTPException(status_code=409, detail={"code": "PROJECT_SCOPE_SNAPSHOT_MISMATCH", "message": "绑定项目记忆只能写入发送时项目", "retryable": False})
    project_id = None if scope == "global" else (payload.project_id or job.project_id_snapshot)
    if scope == "project":
        if not project_id:
            raise HTTPException(status_code=400, detail={"code": "PROJECT_REQUIRED", "message": "保存到项目需要 project_id", "retryable": False})
        project = repo.get_project(project_id, OWNER_ID)
        if not project or project.status != "active":
            raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在或不可用", "retryable": False})
    # spec-038：``memories`` 表已停用，决策不再直接落库，只更新审计流水中的分析项
    # 状态（``auto_saved``）。记忆内容本身改由 MD 承载，落盘在 P2/P3 接入。
    return repo.update_memory_analysis_item(item_id, OWNER_ID, decision_status="auto_saved")


@router.post("/memory-analysis/items/{item_id}/decision")
def decide_memory_analysis_item(item_id: str, payload: MemoryAnalysisDecisionRequest):
    return {"item": _analysis_item_payload(_analysis_item_decision(item_id, payload))}


@router.post("/messages/{user_message_id}/memory-analysis/decisions")
def decide_memory_analysis_items(user_message_id: str, payload: MemoryAnalysisBatchDecisionRequest):
    repo = _repo()
    job = repo.get_memory_analysis_job(user_message_id, OWNER_ID)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "MEMORY_ANALYSIS_NOT_FOUND", "message": "分析任务不存在", "retryable": False})
    items = repo.list_memory_analysis_item_ids(job.analysis_id, OWNER_ID, payload.item_ids)
    selected = [item for item in items if item.decision_status == "pending_confirmation"]
    results = []
    failures = []
    for item in selected:
        decision = "ignore" if payload.decision in {"ignore", "ignore_all"} else ("save_global" if payload.decision == "save_global" else ("save_project" if payload.decision == "save_project" else ("save_global" if item.suggested_scope == "global" else "save_project")))
        try:
            results.append(_analysis_item_decision(item.item_id, MemoryAnalysisDecisionRequest(decision=decision, project_id=payload.project_id)))
        except HTTPException as error:
            failures.append({"item_id": item.item_id, "code": error.detail.get("code") if isinstance(error.detail, dict) else "DECISION_FAILED", "message": error.detail.get("message") if isinstance(error.detail, dict) else str(error.detail)})
    return {"analysis": _analysis_job_payload(repo.get_memory_analysis_job(user_message_id, OWNER_ID)), "items": [_analysis_item_payload(item) for item in results], "failed": failures, "selected_count": len(selected)}
# ---------------------------------------------------------------------------
# spec-038 P1/P2：长期记忆的 CRUD 端点已随 ``memories`` 表停用一并移除。
#
# 真相源改为 MD 文件：
# - 全局用户画像（原 /system-rule）→ ``USER.md``，见上方同名端点；
# - 长期记忆 / 项目记忆 → ``MEMORY.md`` / ``projects/<id>.md``，由 P2/P3 以 MD
#   为真相源重建对应接口（届时复用 ``MarkdownMemoryStore``，不再新建第二套实现）。
# ---------------------------------------------------------------------------
