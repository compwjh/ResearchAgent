import time
from typing import List

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.api.schemas import (
    ChatRequest,
)
from backend.app.chat.application.chat_runner import run_chat
from backend.app.core.config import MODEL_NAME
from backend.app.platform.observability import flush, record_ollama_generation, utc_now
from backend.app.platform.ollama import get_available_models
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)

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
        run = run_chat(question, selected_model)
        yield stream_event("meta", model=selected_model, mode=request.mode)
        try:
            for event in run.events:
                yield stream_event(event["type"], content=event["content"])
        except Exception as error:
            if run.result is not None:
                try:
                    record_ollama_generation(
                        model=selected_model,
                        prompt_messages=[{"role": "user", "content": question}],
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
                    prompt_messages=[{"role": "user", "content": question}],
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

