import logging
import time

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
    MemoryCreateRequest,
    MemoryPatchRequest,
    SystemRulePatchRequest,
    SystemRulePutRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
)
from backend.app.chat.application.chat_runner import ChatStreamInterrupted, run_chat
from backend.app.chat.application.reasoning import EventSequencer, MAX_REASONING_CODEPOINTS, ReasoningStreamFilter, filter_reasoning, REASONING_EFFORTS
from backend.app.chat.application.conversation_service import (
    get_memory_analysis_worker, get_memory_evolution_worker, compose_chat_prompt,
    compose_chat_messages, has_explicit_global_intent, is_system_rule_intent,
)
from backend.app.knowledge_base.application import (
    citation_payloads,
    clear_project_document_associations,
    filter_hits_for_project,  # compatibility export; retrieval itself filters pre-RRF
    hybrid_search,
    list_documents_for_project,
)
from backend.app.memory.repository import OWNER_ID, MemoryRepository, SystemRuleUnavailableError
from backend.app.platform.bootstrap import get_provider, register_provider
from backend.app.platform.ollama import get_available_models, get_reasoning_capabilities, resolve_reasoning_effort
from backend.app.platform.observability import redact_prompt_messages, record_ollama_generation, utc_now

router = APIRouter()
logger = logging.getLogger(__name__)


def _repo() -> MemoryRepository:
    return get_provider("memory_repository")


register_provider("memory_repository", MemoryRepository, singleton=False)


def _project_payload(item):
    return {"project_id": item.project_id, "owner_id": item.owner_id, "name": item.name, "instructions": item.instructions, "status": item.status, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "last_activity_at": (item.last_activity_at or item.updated_at).isoformat()}


def _conversation_payload(item):
    return {"conversation_id": item.conversation_id, "owner_id": item.owner_id, "project_id": item.project_id, "title": item.title, "status": item.status, "memory_history_policy": item.memory_history_policy, "reasoning_effort": item.reasoning_effort, "memory_binding_at": item.memory_binding_at.isoformat() if item.memory_binding_at else None, "memory_binding_message_id": item.memory_binding_message_id, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def _message_payload(item):
    return {"message_id": item.message_id, "conversation_id": item.conversation_id, "parent_message_id": item.parent_message_id, "role": item.role, "content": item.content, "status": item.status, "model": item.model, "mode": item.mode, "reasoning_content": item.reasoning_content, "reasoning_status": item.reasoning_status, "reasoning_started_at": item.reasoning_started_at.isoformat() if item.reasoning_started_at else None, "reasoning_completed_at": item.reasoning_completed_at.isoformat() if item.reasoning_completed_at else None, "first_reasoning_at": item.first_reasoning_at.isoformat() if item.first_reasoning_at else None, "first_answer_token_at": item.first_answer_token_at.isoformat() if item.first_answer_token_at else None, "reasoning_truncated": item.reasoning_truncated, "reasoning_chars": item.reasoning_chars, "last_event_seq": item.last_event_seq, "created_at": item.created_at.isoformat(), "completed_at": item.completed_at.isoformat() if item.completed_at else None}


def _memory_payload(item):
    return {"memory_id": item.memory_id, "owner_id": item.owner_id, "scope": item.scope, "project_id": item.project_id, "category": item.category, "statement": item.statement, "source_kind": item.source_kind, "status": item.status, "confidence": item.confidence, "supersedes_id": item.supersedes_id, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None}


def _system_rule_payload(item):
    return {"content": item.content, "enabled": item.enabled, "updated_at": item.updated_at.isoformat()}


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


def _memory_error(error: Exception) -> HTTPException:
    message = str(error)
    if isinstance(error, LookupError):
        code = "MEMORY_SCOPE_NOT_FOUND" if "project" in message else "MEMORY_NOT_FOUND"
        status = 404
    elif "already" in message:
        code, status = "MEMORY_CONFLICT", 409
    else:
        code, status = "INVALID_MEMORY", 400
    return HTTPException(status_code=status, detail={"code": code, "message": message, "retryable": False})


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
    try: item = _repo().update_project(project_id, OWNER_ID, **payload.model_dump(exclude_unset=True))
    except ValueError as error: raise HTTPException(status_code=409, detail={"code": "PROJECT_EXISTS", "message": str(error), "retryable": False}) from error
    if not item: raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在", "retryable": False})
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
        detached = clear_project_document_associations(project_id, owner_id=OWNER_ID)
    except Exception as error:
        raise HTTPException(status_code=503, detail={"code": "DOCUMENT_ASSOCIATION_FAILED", "message": "项目文档关联暂时无法解除", "retryable": True}) from error
    _repo().delete_project(project_id, OWNER_ID)


def _validate_model(model: str):
    try:
        available = get_available_models()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": "无法连接 Ollama 服务", "retryable": True}) from error
    if model not in available:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND", "message": f"模型 {model} 不存在", "retryable": False})


def _resolve_request_effort(model: str, requested: str | None):
    try:
        return resolve_reasoning_effort(model, requested)
    except (ValueError, RuntimeError) as error:
        code = str(error)
        if isinstance(error, RuntimeError):
            raise HTTPException(status_code=503, detail={"code": "MODEL_CAPABILITIES_UNAVAILABLE", "message": "模型能力暂时不可用", "retryable": True}) from error
        if code == "INVALID_REASONING_EFFORT":
            raise HTTPException(status_code=400, detail={"code": code, "message": "推理档位无效", "retryable": False}) from error
        raise HTTPException(status_code=409, detail={"code": "REASONING_EFFORT_UNSUPPORTED", "message": "当前模型不支持该推理档位", "retryable": False}) from error


@router.get("/chat/reasoning-options")
def reasoning_options(model: str | None = None):
    selected = (model or "").strip()
    if not selected:
        from backend.app.platform.config import MODEL_NAME
        selected = MODEL_NAME
    try:
        _validate_model(selected)
        capabilities = get_reasoning_capabilities(selected)
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail={"code": "MODEL_CAPABILITIES_UNAVAILABLE", "message": "模型能力暂时不可用", "retryable": True}) from error
    return {"model": capabilities.model, "supported_efforts": list(capabilities.supported_efforts), "default_effort": capabilities.default_effort, "source": capabilities.source, "cached_at": capabilities.cached_at}


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
    while True:
        try:
            event = next(iterator)
            if event.get("type") in {"thinking", "reasoning_delta", "token"} and event.get("content"):
                saw_partial_output = True
            yield event
        except StopIteration:
            return
        except GeneratorExit:
            raise
        except Exception as error:
            if saw_partial_output:
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
        selected_effort = reasoning_effort or getattr(conversation, "reasoning_effort", "medium")
        reasoning_started_mono = None
        reasoning_duration_ms = None
        adapter_event_seq = 0
        finished = False
        generation_started = False
        try:
            system_rule = repo.get_system_rule(OWNER_ID)
        except Exception:
            # A rule-enabled request cannot safely continue when its state is
            # unknown.  Persist failure before emitting any model event/token.
            try:
                repo.update_message(assistant_message.message_id, OWNER_ID, status="failed")
            except Exception:
                pass
            yield frame("meta", project_id=conversation.project_id, conversation_id=conversation.conversation_id, user_message_id=user_message.message_id, assistant_message_id=assistant_message.message_id, model=model, mode=mode, reasoning_effort=selected_effort, capabilities_source=capabilities_source)
            yield frame("error", code="SYSTEM_RULE_UNAVAILABLE", message="系统规则暂时不可用", retryable=True)
            yield frame("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="failed", duration_ms=0, reasoning_duration_ms=None, answer_duration_ms=0)
            return
        try:
            # Raw events are an append-only audit/input stream for the local
            # evolution worker.  They are advisory and never block SSE.
            try:
                repo.append_raw_event(OWNER_ID, conversation.conversation_id, "user_message", {"content": user_message.content}, message_id=user_message.message_id, idempotency_key=f"message:{user_message.message_id}")
            except Exception:
                pass
            yield frame("meta", project_id=conversation.project_id, conversation_id=conversation.conversation_id, user_message_id=user_message.message_id, assistant_message_id=assistant_message.message_id, model=model, mode=mode, reasoning_effort=selected_effort, capabilities_source=capabilities_source)
            recall_running = repo.create_processing_step(assistant_message.message_id, "memory_recall", "running", label="记忆召回")
            yield frame("progress", step_id=recall_running.step_id, kind=recall_running.kind, label=recall_running.label, status="running", summary=None)
            try:
                recall_context = repo.list_recall_context(OWNER_ID, conversation.project_id, query=user_message.content, memory_char_budget=4000, summary_char_budget=1500)
                memories = recall_context["memories"]
                summaries = recall_context["summaries"]
                recall_status = "completed"
                recall_summary = f"召回 {len(memories)} 条长期记忆和 {len(summaries)} 条相关摘要"
            except Exception:
                # Memory is advisory context. A corrupt/locked memory read must
                # not prevent ordinary chat from continuing.
                memories = []
                summaries = []
                recall_status = "failed"
                recall_summary = "记忆召回失败，已跳过"
            usage_failures = 0
            for memory in memories:
                try:
                    repo.mark_memory_used(memory.memory_id, OWNER_ID)
                    yield frame("memory", status="used", memory_id=memory.memory_id, scope=memory.scope, project_id=memory.project_id, statement=memory.statement)
                except Exception:
                    usage_failures += 1
                    yield frame("memory", status="skipped", memory_id=memory.memory_id, scope=memory.scope, project_id=memory.project_id, statement=memory.statement, message="记忆使用记录未保存")
            if usage_failures:
                recall_status = "failed"
                recall_summary = f"召回 {len(memories)} 条长期记忆，其中 {usage_failures} 条使用记录未保存"
            recall_done = repo.create_processing_step(assistant_message.message_id, "memory_recall", recall_status, recall_summary, label="记忆召回")
            yield frame("progress", step_id=recall_done.step_id, kind=recall_done.kind, label=recall_done.label, status=recall_status, summary=recall_done.summary)
            if system_rule.enabled and system_rule.content:
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
                    except Exception as error:
                        rag_hits = []
                        rag_failed = repo.create_processing_step(assistant_message.message_id, "rag_retrieval", "failed", "知识库检索失败，已跳过", label="知识库检索")
                        yield frame("progress", step_id=rag_failed.step_id, kind=rag_failed.kind, label=rag_failed.label, status="failed", summary=rag_failed.summary)
            history = [message for message in repo.list_context_messages(conversation.conversation_id, OWNER_ID) if message.message_id != user_message.message_id]
            if sum(len(message.content or "") for message in history) > 12000:
                try:
                    repo.append_raw_event(OWNER_ID, conversation.conversation_id, "context_pressure", {"summary": "会话上下文达到整理阈值"}, message_id=user_message.message_id, idempotency_key=f"pressure:{user_message.message_id}")
                except Exception:
                    pass
            messages = compose_chat_messages(user_message.content, history, memories, project_instructions, summaries, rag_hits=rag_hits, system_rule=system_rule.content if system_rule.enabled else None)
            repo.update_message(assistant_message.message_id, OWNER_ID, status="streaming")
            generation_started = True
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
                    try:
                        repo.append_raw_event(OWNER_ID, conversation.conversation_id, "tool_failure", {"error": _redact_sensitive(event.get("message") or event.get("content") or "工具失败"), "verified": False}, message_id=user_message.message_id, idempotency_key=f"tool-failure:{user_message.message_id}")
                    except Exception:
                        pass
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
                if reasoning_seen:
                    interrupted_iso = utc_now().isoformat()
                    reasoning_duration_ms = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                    repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="interrupted", completed_at=interrupted_iso, chars=len(reasoning_parts[0]) if reasoning_parts else 0)
                    yield frame("reasoning_completed", status="interrupted", duration_ms=reasoning_duration_ms, completed_at=interrupted_iso)
                    reasoning_seen = False
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
                if reasoning_seen:
                    reasoning_duration_ms = max(0.0, (time.monotonic() - reasoning_started_at) * 1000.0) if reasoning_started_at else None
                    completed_iso = utc_now().isoformat()
                    repo.update_message_reasoning(assistant_message.message_id, OWNER_ID, status="failed", completed_at=completed_iso, last_event_seq=sequencer.event_seq)
                    yield frame("reasoning_completed", status="failed", duration_ms=reasoning_duration_ms, completed_at=completed_iso)
                    reasoning_seen = False
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


def _start_message(payload: ConversationMessageRequest, conversation_id: str | None = None):
    content = (payload.content or payload.question or payload.message or "").strip()
    if not content or len(content) > 20000:
        raise HTTPException(status_code=400, detail={"code": "INVALID_MESSAGE", "message": "消息不能为空且最多支持 20000 个字符", "retryable": False})
    _validate_model(payload.model)
    repo = _repo()
    if conversation_id:
        conversation = repo.get_conversation(conversation_id, OWNER_ID)
        if not conversation: raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
        # An existing conversation's frozen effort wins over the owner
        # default.  This keeps a stale/unsupported owner preference from
        # rejecting an otherwise valid session turn.
        requested_effort = payload.reasoning_effort if payload.reasoning_effort is not None else conversation.reasoning_effort
        resolution = _resolve_request_effort(payload.model, requested_effort)
    else:
        inherited_effort = payload.reasoning_effort or repo.get_last_reasoning_effort(OWNER_ID)
        resolution = _resolve_request_effort(payload.model, inherited_effort)
        try: conversation, user, assistant = repo.create_conversation_messages(OWNER_ID, content, payload.project_id, payload.model, payload.mode, resolution.effort, update_preference=payload.reasoning_effort is not None)
        except LookupError as error: raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
        except ValueError as error: raise HTTPException(status_code=409, detail={"code": "PROJECT_NOT_ACTIVE", "message": str(error), "retryable": False}) from error
        except Exception as error: raise HTTPException(status_code=503, detail={"code": "MESSAGE_TRANSACTION_FAILED", "message": "消息与会话偏好更新未完成", "retryable": True}) from error
    if conversation_id:
        try:
            conversation, user, assistant = repo.create_message_pair(
                conversation.conversation_id,
                OWNER_ID,
                content,
                model=payload.model,
                mode=payload.mode,
                reasoning_effort=resolution.effort if payload.reasoning_effort is not None else None,
                update_preference=payload.reasoning_effort is not None,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": str(error), "retryable": False}) from error
        except Exception as error:
            raise HTTPException(status_code=503, detail={"code": "MESSAGE_TRANSACTION_FAILED", "message": "消息与会话偏好更新未完成", "retryable": True}) from error
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
    return StreamingResponse(_message_stream(repo, conversation, user, assistant, payload.model, payload.mode, resolution.effort, resolution.capabilities.source), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/messages")
def create_first_message(payload: ConversationMessageRequest):
    return _start_message(payload)


@router.post("/conversations/{conversation_id}/messages")
def create_message(conversation_id: str, payload: ConversationMessageRequest):
    return _start_message(payload, conversation_id)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    item = _repo().get_conversation(conversation_id, OWNER_ID)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return _conversation_payload(item)


@router.get("/conversations")
def list_conversations(project_id: str | None = None, cursor: str | None = None, limit: int = Query(20, ge=1, le=100), status: str | None = None, unbound_only: bool = False):
    try: items, next_cursor = _repo().list_conversations(OWNER_ID, project_id, cursor, limit, status=status, unbound_only=unbound_only)
    except LookupError as error: raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error:
        code = "INVALID_CONVERSATION_FILTER" if str(error) in {"invalid conversation status", "unbound_only cannot be combined with project_id"} else "INVALID_CURSOR"
        raise HTTPException(status_code=400, detail={"code": code, "message": str(error), "retryable": False}) from error
    return {"conversations": [_conversation_payload(item) for item in items], "next_cursor": next_cursor}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, before: str | None = None, target_chars: int = Query(4000, ge=1, le=100000)):
    try: items, next_cursor = _repo().list_messages(conversation_id, OWNER_ID, before=before, target_chars=target_chars)
    except LookupError as error: raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error: raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": str(error), "retryable": False}) from error
    return {"messages": [_message_payload(item) for item in items], "next_cursor": next_cursor}


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, payload: ConversationPatchRequest):
    try: item = _repo().update_conversation(conversation_id, OWNER_ID, **payload.model_dump(exclude_unset=True))
    except LookupError as error: raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    except ValueError as error: raise HTTPException(status_code=409, detail={"code": "CONVERSATION_CONFLICT", "message": str(error), "retryable": False}) from error
    if not item: raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
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
    if not _repo().delete_conversation(conversation_id, OWNER_ID): raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/messages/{message_id}/processing-steps")
def get_processing_steps(message_id: str):
    steps = _repo().list_processing_steps(message_id, OWNER_ID)
    if not steps and not _repo().get_message(message_id, OWNER_ID): raise HTTPException(status_code=404, detail="消息不存在")
    return {"steps": [{"step_id": s.step_id, "message_id": s.message_id, "kind": s.kind, "label": s.label, "status": s.status, "summary": s.summary, "started_at": s.started_at.isoformat(), "completed_at": s.completed_at.isoformat() if s.completed_at else None} for s in steps]}


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
    duplicate = None
    for status in ("active", "candidate", "superseded", "disabled", "deleted"):
        for memory in repo.list_memories(OWNER_ID, project_id, scope=scope, status=status):
            if " ".join(memory.statement.split()).casefold() == " ".join(item.statement.split()).casefold():
                duplicate = memory
                break
        if duplicate:
            break
    if duplicate:
        return repo.update_memory_analysis_item(item_id, OWNER_ID, decision_status="duplicate", memory_id=duplicate.memory_id)
    category = "user_preference" if scope == "global" else "project_rule"
    conflict = next((memory for memory in repo.list_memories(OWNER_ID, project_id, scope=scope, status="active") if memory.category == category and memory.statement.casefold() != item.statement.casefold()), None)
    evidence = (None, job.user_message_id, "manual", item.statement[:500])
    if scope == "project" and project_id != job.project_id_snapshot:
        # A user may explicitly route an unbound result into a selected
        # project; the original message is evidence, but cannot be attached
        # across project scopes under the repository's isolation contract.
        evidence = None
    try:
        record = repo.create_memory(
            OWNER_ID, scope, project_id, category, item.statement, "manual", max(0.0, min(1.0, item.confidence)),
            status="active", supersedes_id=conflict.memory_id if conflict else None,
            evidence=evidence,
        )
        if conflict:
            repo.update_memory(conflict.memory_id, OWNER_ID, status="superseded")
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=409, detail={"code": "MEMORY_DECISION_CONFLICT", "message": str(error), "retryable": False}) from error
    return repo.update_memory_analysis_item(item_id, OWNER_ID, decision_status="superseded" if conflict else "auto_saved", memory_id=record.memory_id)


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


@router.get("/memories")
def list_memories(project_id: str | None = None, scope: str | None = Query(None, pattern="^(global|project)$"), status: str = Query("active", pattern="^(candidate|active|superseded|disabled|deleted)$")):
    try:
        if project_id is not None and scope is None:
            scope = "project"
        items = _repo().list_memories(OWNER_ID, project_id, scope=scope, status=status)
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    return {"memories": [_memory_payload(item) for item in items]}


@router.post("/memories", status_code=201)
def create_memory(payload: MemoryCreateRequest):
    try:
        item = _repo().create_memory(OWNER_ID, payload.scope, payload.project_id, payload.category, payload.statement, payload.source_kind, payload.confidence, status=payload.status)
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    return _memory_payload(item)


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str):
    item = _repo().get_memory(memory_id, OWNER_ID)
    if not item:
        raise _memory_error(LookupError("memory not found"))
    return _memory_payload(item)


@router.get("/memories/{memory_id}/evidence")
@router.get("/memories/{memory_id}/sources")
@router.get("/memories/{memory_id}/source")
def get_memory_evidence(memory_id: str):
    item = _repo().get_memory(memory_id, OWNER_ID)
    if not item:
        raise _memory_error(LookupError("memory not found"))
    evidence = _repo().list_memory_evidence(memory_id, OWNER_ID)
    return {"memory_id": memory_id, "evidence": [{"memory_id": e.memory_id, "conversation_id": e.conversation_id, "message_id": e.message_id, "evidence_type": e.evidence_type, "excerpt": e.excerpt} for e in evidence]}


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: str, payload: MemoryPatchRequest):
    try:
        item = _repo().update_memory(memory_id, OWNER_ID, **payload.model_dump(exclude_unset=True))
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    if not item:
        raise _memory_error(LookupError("memory not found"))
    return _memory_payload(item)


@router.post("/memories/{memory_id}/confirm")
def confirm_memory(memory_id: str):
    try:
        item = _repo().confirm_memory(memory_id, OWNER_ID)
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    if not item:
        raise _memory_error(LookupError("memory not found"))
    return _memory_payload(item)


@router.post("/memories/{memory_id}/disable")
def disable_memory(memory_id: str):
    try:
        item = _repo().update_memory(memory_id, OWNER_ID, status="disabled")
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    if not item:
        raise _memory_error(LookupError("memory not found"))
    return _memory_payload(item)


@router.post("/memories/{memory_id}/undo")
@router.post("/memories/{memory_id}/restore")
def undo_memory(memory_id: str):
    try:
        item = _repo().undo_memory(memory_id, OWNER_ID)
    except (ValueError, LookupError) as error:
        raise _memory_error(error) from error
    if not item:
        raise _memory_error(LookupError("memory not found"))
    return _memory_payload(item)


@router.delete("/memories/{memory_id}", status_code=204)
def remove_memory(memory_id: str):
    if not _repo().delete_memory(memory_id, OWNER_ID):
        raise _memory_error(LookupError("memory not found"))
