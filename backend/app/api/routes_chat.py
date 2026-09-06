import json
import os
import time
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from backend.app.api.schemas import (
    ChatRequest,
    ConferenceUpdateRequest,
    KBAskRequest,
    KBReindexRequest,
    PaperImportBatchRequest,
    PaperImportBatchResponse,
    PaperImportItemActionRequest,
    PaperImportItemLoginResponse,
    PaperImportRequest,
    PaperImportResponse,
    PaperAcceptedRequest,
    PaperSearchRequest,
)
from backend.app.agents.article_agent import build_task
from backend.app.platform.settings.settings_repository import (
    ArticleSettings,
    load_article_settings,
    save_article_settings,
)
from backend.app.core.config import BASE_DIR, CHUNK_V2_LLM_MODEL, KB_MAX_UPLOAD_MB, KB_PAPERS_DIR, MODEL_NAME
from backend.app.observability import end_trace, flush, record_ollama_generation, start_trace, utc_now
from backend.app.domain.article import ArticleCandidate, ArticleTask
from backend.app.domain.paper_discovery import SearchSession
from backend.app.services.article_download import download_article, probe_pdf_url
from backend.app.services.article_search import search_articles
from backend.app.services.download_paper_skill import SKILL_NAME, build_skill_plan, download_under_skill, skill_status
from backend.app.services.kb import (
    CHUNKERS,
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_INDEXING,
    build_prompt,
    citation_payloads,
    count_points,
    delete_paper,
    ensure_collection,
    get_client,
    get_paper,
    hybrid_search,
    index_paper,
    index_paper_chunker,
    load_papers,
    new_record,
    remove_paper,
    run_index_task_sync,
    save_upload,
    submit_index_task,
    update_chunker_state,
    upsert_paper,
)
from backend.app.services.kb.embed import embed_texts
from backend.app.services.kb.retrieve import reranker_health
from backend.app.services.kb.store import resolve_paper_path
from backend.app.services.ollama import create_chat_model, get_available_models, run_chat
from backend.app.services.dblp_publication_source import DBLPPublicationSource
from backend.app.services.openalex_enricher import OpenAlexEnricher
from backend.app.services.paper_discovery_search import PaperDiscoverySearchError, PaperDiscoverySearchService
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
from backend.app.services.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    PaperDownloadError,
)
from backend.app.services.paper_import import (
    KB_IMPORT_FAILED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    import_candidate,
    safe_import_error_code,
    safe_import_error_message,
)
from backend.app.services.paper_import_batch_service import (
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.services.paper_import_batch_store import PaperImportBatchStore
from backend.app.services.paper_browser_manager import BrowserManagerError, PaperBrowserManager
from backend.app.services.task_store import TaskStore

router = APIRouter()
article_tasks = TaskStore()
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
