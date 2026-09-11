import logging
import time
from typing import List

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.api import routes_skills as _skill_routes
from backend.app.api import routes_tools as _tool_routes
from backend.app.api.schemas import (
    ChatRequest,
)
from backend.app.chat.application.chat_runner import run_chat
from backend.app.platform.config import (
    MODEL_NAME,
    SKILL_TOOL_MAX_ROUNDS,
    SKILL_TOOL_RETRY,
    SKILL_TOOL_TIMEOUT_SECONDS,
)
from backend.app.platform.observability import flush, record_ollama_generation, utc_now
from backend.app.platform.ollama import get_available_models
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)
from backend.app.skills import intent as _skill_intent
from backend.app.skills.intent import SkillDecision

logger = logging.getLogger(__name__)

router = APIRouter()
article_settings = load_article_settings()
paper_discovery_store = None
paper_discovery_store_path = None
paper_discovery_search_service = None
paper_import_batch_service = None
paper_import_batch_store_path = None
paper_browser_manager = None
# Sessions are keyed by import item, so a resume request can never borrow a
# different item's authenticated browser context.
paper_browser_sessions = {}


from backend.app.api.common import *  # noqa: F401,F403


@router.post("/chat")
def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    max_length = 20_000 if request.mode == "developer" else 2_000
    if len(question) > max_length:
        raise HTTPException(status_code=400, detail=f"当前模式最多支持 {max_length:,} 个字符")

    try:
        available_models: List[str] = get_available_models()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="无法连接 Ollama 服务") from error
    if request.model not in available_models:
        raise HTTPException(status_code=400, detail=f"模型 {request.model} 不存在，请从已安装模型中选择")

    selected_model = request.model

    def generate():
        started = utc_now()
        wall_start = time.perf_counter()

        # —— Skill 识别（双触发：规则 + LLM）；异常一律降级为无技能，绝不阻断对话 ——
        decision: SkillDecision = SkillDecision(status="none")
        available_names: List[str] = []
        try:
            registry = _skill_routes.get_skill_registry()
            skills = registry.list_skills()
            available_names = [s.name for s in skills]
            decision = _skill_intent.detect_skill(question, skills)
        except Exception as error:  # 识别失败不得影响对话
            logger.warning("Skill 识别异常，降级为无技能：%s", error)

        prompt = None
        if decision.is_usable():
            detail = _skill_routes.get_skill_registry().get_skill(decision.skill)
            if detail is not None:
                prompt = _skill_intent.build_skill_prompt(question, detail.body)

        yield stream_event("meta", model=selected_model, mode=request.mode)

        # 命中 Skill 时给出结构化 intent 事件（前端 showSkillHint 消费 skill 字段）
        intent_event = _skill_intent.to_intent_event(decision, available_names)
        if intent_event:
            event_type = intent_event.pop("type")
            yield stream_event(event_type, **intent_event)

        if decision.status in ("disabled", "not_found", "ambiguous"):
            # 不调用模型，直接提示并结束，对话不中断
            hint = _skill_intent.format_skill_hint(decision, available_names)
            if hint:
                yield stream_event("result", message=hint)
            yield stream_event("done")
            return

        # 命中 Skill 且有可用 Tool -> 走 Tool 执行编排（Task07：原生 function calling 优先 + 计划 JSON 降级）。
        # 仅 matched（is_usable）且存在 enabled 工具时进入；否则走原 run_chat 链路（行为完全不变）。
        enabled_tools = [
            t for t in _tool_routes.get_tool_registry().list_tools() if t.enabled
        ]
        if decision.is_usable() and not enabled_tools:
            # B3（spec-023.1）：全部 Tool 被禁用属「未定义行为」，不得静默回退。
            # 明确告知用户本次未走 Tool 流程及原因，再按普通链路继续回答。
            yield stream_event(
                "token",
                content="（提示：当前所有工具均已被禁用，本次未进入工具执行流程，将由模型直接回答。）\n",
            )
        if decision.is_usable() and enabled_tools:
            from backend.app.skills import tool_dispatch as _tool_dispatch
            from backend.app.skills import tool_executor as _tool_executor

            loop = _tool_executor.ToolLoop(
                tools=enabled_tools,
                model_call=_tool_executor.make_model_call(
                    selected_model,
                    timeout=SKILL_TOOL_TIMEOUT_SECONDS,
                    retry=SKILL_TOOL_RETRY,
                ),
                dispatch=_tool_dispatch.build_default_dispatch(),
                max_rounds=SKILL_TOOL_MAX_ROUNDS,
            )
            for ev in loop.run(system_prompt=prompt, user_question=question):
                # 只把最终回答（token）回流给前端；tool 过程事件供服务端日志，不破坏既有前端契约
                if ev.get("type") == "token":
                    yield stream_event("token", content=ev["content"])
            yield stream_event("done")
            return

        # 原有链路：none 或 matched 但无可用 Tool 都走 run_chat；matched 注入技能正文
        run = run_chat(question, selected_model, prompt=prompt)
        try:
            for event in run.events:
                yield stream_event(event["type"], content=event["content"])
        except Exception as error:
            if run.result is not None:
                try:
                    record_ollama_generation(
                        model=selected_model,
                        prompt_messages=[{"role": "user", "content": prompt if prompt is not None else question}],
                        result=run.result,
                        route=run.route,
                        started_at=started,
                        tags=["chat"],
                        # 失败必须显式标记：否则失败请求会混进成功耗时分位，
                        # 任务 06 的成功率/错误率统计也会失真。
                        success=False,
                        error_type=type(error).__name__,
                    )
                    flush()
                except Exception:
                    pass
            detail = str(error) if request.mode == "developer" else f"无法连接 Ollama，请确认服务已启动且模型 {MODEL_NAME} 已安装"
            yield stream_event("error", detail=detail)
            return

        if request.mode == "developer":
            yield stream_event("debug", debug={"mode": request.mode, "input_length": len(question), "elapsed_ms": round((time.perf_counter() - wall_start) * 1000, 1), "graph_node": "ask_model"})
        yield stream_event("done")

        if run.result is not None:
            try:
                record_ollama_generation(
                    model=selected_model,
                    prompt_messages=[{"role": "user", "content": prompt if prompt is not None else question}],
                    result=run.result,
                    route=run.route,
                    started_at=started,
                    tags=["chat"],
                 )
                flush()
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== 知识库 / RAG（spec-011）====================
