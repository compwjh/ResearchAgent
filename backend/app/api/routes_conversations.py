import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.api.common import stream_event
from backend.app.api.schemas import ConversationMessageRequest, ConversationPatchRequest, ProjectCreateRequest, ProjectPatchRequest
from backend.app.chat.application.chat_runner import run_chat
from backend.app.chat.application.conversation_service import classify_memory_intent, compose_chat_prompt
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.bootstrap import get_provider, register_provider
from backend.app.platform.ollama import get_available_models

router = APIRouter()


def _repo() -> MemoryRepository:
    return get_provider("memory_repository")


register_provider("memory_repository", MemoryRepository, singleton=False)


def _project_payload(item):
    return {"project_id": item.project_id, "owner_id": item.owner_id, "name": item.name, "instructions": item.instructions, "status": item.status, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def _conversation_payload(item):
    return {"conversation_id": item.conversation_id, "owner_id": item.owner_id, "project_id": item.project_id, "title": item.title, "status": item.status, "memory_history_policy": item.memory_history_policy, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def _message_payload(item):
    return {"message_id": item.message_id, "conversation_id": item.conversation_id, "role": item.role, "content": item.content, "status": item.status, "model": item.model, "mode": item.mode, "created_at": item.created_at.isoformat(), "completed_at": item.completed_at.isoformat() if item.completed_at else None}


def _memory_payload(item):
    return {"memory_id": item.memory_id, "owner_id": item.owner_id, "scope": item.scope, "project_id": item.project_id, "category": item.category, "statement": item.statement, "source_kind": item.source_kind, "status": item.status, "confidence": item.confidence, "supersedes_id": item.supersedes_id, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None}


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


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(project_id: str):
    if not _repo().delete_project(project_id, OWNER_ID): raise HTTPException(status_code=404, detail="项目不存在")


def _validate_model(model: str):
    try:
        available = get_available_models()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "message": "无法连接 Ollama 服务", "retryable": True}) from error
    if model not in available:
        raise HTTPException(status_code=400, detail={"code": "MODEL_NOT_FOUND", "message": f"模型 {model} 不存在", "retryable": False})


def _message_stream(repo: MemoryRepository, conversation, user_message, assistant_message, model: str, mode: str):
    def generate():
        yield stream_event("meta", project_id=conversation.project_id, conversation_id=conversation.conversation_id, user_message_id=user_message.message_id, assistant_message_id=assistant_message.message_id, model=model, mode=mode)
        classification_running = repo.create_processing_step(assistant_message.message_id, "memory_classification", "running", label="记忆分析")
        yield stream_event("progress", step_id=classification_running.step_id, kind=classification_running.kind, label=classification_running.label, status="running", summary=None)
        try:
            intent = classify_memory_intent(user_message.content)
            classification_status = "completed"
            classification_summary = "已完成记忆意图分析"
        except Exception:
            # Classification is advisory: an unavailable parser/model must
            # never prevent the ordinary answer from being generated.
            from backend.app.chat.application.conversation_service import MemoryIntent
            intent = MemoryIntent("none", current_task=user_message.content)
            classification_status = "skipped"
            classification_summary = "记忆未分析/未保存"
        classification_done = repo.create_processing_step(assistant_message.message_id, "memory_classification", classification_status, classification_summary, label="记忆分析")
        yield stream_event("progress", step_id=classification_done.step_id, kind=classification_done.kind, label=classification_done.label, status=classification_status, summary=classification_summary)
        if classification_status == "skipped":
            yield stream_event("memory", status="not_analyzed", message="记忆未分析/未保存")
        if intent.intent == "explicit" and conversation.project_id:
            try:
                record = repo.create_memory(OWNER_ID, "project", conversation.project_id, "project_rule", intent.statement or user_message.content, "explicit", intent.confidence)
                repo.create_memory_evidence(record.memory_id, conversation.conversation_id, user_message.message_id, "user_statement", intent.statement)
                yield stream_event("memory", status="saved", memory_id=record.memory_id, scope="project", project_id=conversation.project_id, statement=record.statement)
            except Exception:
                yield stream_event("memory", status="not_saved", message="记忆未保存")
        elif intent.intent == "ambiguous" and conversation.project_id:
            yield stream_event("memory", status="needs_confirmation", scope="project", project_id=conversation.project_id, statement=intent.statement)
        elif intent.intent in {"explicit", "ambiguous"} and not conversation.project_id:
            yield stream_event("memory", status="needs_confirmation", scope="project", statement=intent.statement, message="请先绑定项目后保存")
        recall_running = repo.create_processing_step(assistant_message.message_id, "memory_recall", "running", label="记忆召回")
        yield stream_event("progress", step_id=recall_running.step_id, kind=recall_running.kind, label=recall_running.label, status="running", summary=None)
        memories = repo.list_memories(OWNER_ID, conversation.project_id) if conversation.project_id else []
        for memory in memories:
            repo.mark_memory_used(memory.memory_id, OWNER_ID)
            yield stream_event("memory", status="used", memory_id=memory.memory_id, scope=memory.scope, project_id=memory.project_id, statement=memory.statement)
        recall_done = repo.create_processing_step(assistant_message.message_id, "memory_recall", "completed", f"召回 {len(memories)} 条项目记忆", label="记忆召回")
        yield stream_event("progress", step_id=recall_done.step_id, kind=recall_done.kind, label=recall_done.label, status="completed", summary=recall_done.summary)
        prompt = compose_chat_prompt(user_message.content, repo.list_messages(conversation.conversation_id, OWNER_ID, target_chars=100000)[0], memories)
        repo.update_message(assistant_message.message_id, OWNER_ID, status="streaming")
        generation_running = repo.create_processing_step(assistant_message.message_id, "generation", "running", label="回答生成")
        yield stream_event("progress", step_id=generation_running.step_id, kind=generation_running.kind, label=generation_running.label, status="running", summary=None)
        parts = []
        try:
            run = run_chat(user_message.content, model, prompt=prompt)
            for event in run.events:
                if event.get("type") == "token":
                    token = event.get("content", ""); parts.append(token)
                    repo.update_message(assistant_message.message_id, OWNER_ID, content="".join(parts), status="streaming")
                    yield stream_event("token", content=token)
            content = "".join(parts)
            repo.update_message(assistant_message.message_id, OWNER_ID, content=content, status="completed")
            generation_done = repo.create_processing_step(assistant_message.message_id, "generation", "completed", "回答已生成", label="回答生成")
            yield stream_event("progress", step_id=generation_done.step_id, kind=generation_done.kind, label=generation_done.label, status="completed", summary=generation_done.summary)
            yield stream_event("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="completed")
        except Exception as error:
            content = "".join(parts)
            repo.update_message(assistant_message.message_id, OWNER_ID, content=content, status="failed")
            generation_failed = repo.create_processing_step(assistant_message.message_id, "generation", "failed", "回答生成失败", label="回答生成")
            yield stream_event("progress", step_id=generation_failed.step_id, kind=generation_failed.kind, label=generation_failed.label, status="failed", summary=generation_failed.summary)
            yield stream_event("error", code="CHAT_FAILED", message=str(error), retryable=True)
            yield stream_event("done", conversation_id=conversation.conversation_id, message_id=assistant_message.message_id, status="failed")
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
    else:
        try: conversation, user, assistant = repo.create_conversation_messages(OWNER_ID, content, payload.project_id, payload.model, payload.mode)
        except LookupError as error: raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": str(error), "retryable": False}) from error
    if conversation_id:
        user = repo.create_message(conversation.conversation_id, OWNER_ID, "user", content, status="completed", model=payload.model, mode=payload.mode)
        assistant = repo.create_message(conversation.conversation_id, OWNER_ID, "assistant", "", status="pending", model=payload.model, mode=payload.mode, parent_message_id=user.message_id)
    return StreamingResponse(_message_stream(repo, conversation, user, assistant, payload.model, payload.mode), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/messages")
def create_first_message(payload: ConversationMessageRequest):
    return _start_message(payload)


@router.post("/conversations/{conversation_id}/messages")
def create_message(conversation_id: str, payload: ConversationMessageRequest):
    return _start_message(payload, conversation_id)


@router.get("/conversations")
def list_conversations(project_id: str | None = None, cursor: str | None = None, limit: int = Query(20, ge=1, le=100)):
    try: items, next_cursor = _repo().list_conversations(OWNER_ID, project_id, cursor, limit)
    except (ValueError, LookupError) as error: raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": str(error), "retryable": False}) from error
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
    if not item: raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "会话不存在", "retryable": False})
    return _conversation_payload(item)


@router.delete("/conversations/{conversation_id}", status_code=204)
def remove_conversation(conversation_id: str):
    if not _repo().delete_conversation(conversation_id, OWNER_ID): raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/messages/{message_id}/processing-steps")
def get_processing_steps(message_id: str):
    steps = _repo().list_processing_steps(message_id, OWNER_ID)
    if not steps and not _repo().get_message(message_id, OWNER_ID): raise HTTPException(status_code=404, detail="消息不存在")
    return {"steps": [{"step_id": s.step_id, "message_id": s.message_id, "kind": s.kind, "label": s.label, "status": s.status, "summary": s.summary, "started_at": s.started_at.isoformat(), "completed_at": s.completed_at.isoformat() if s.completed_at else None} for s in steps]}


@router.get("/memories")
def list_memories(project_id: str | None = None):
    return {"memories": [_memory_payload(item) for item in _repo().list_memories(OWNER_ID, project_id)]}
