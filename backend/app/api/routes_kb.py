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
def kb_component_status() -> dict:
    reranker_detail = reranker_health()
    status = {
        "qdrant": False,
        "embedding": False,
        "reranker": bool(reranker_detail["enabled"] and reranker_detail["available"]),
        "reranker_detail": reranker_detail,
        "papers": len(load_papers()),
        "chunks": 0,
        # spec-012：v2 结构分析模型是否可用（不可用时 v2 会降级为规则切分）
        "v2_llm": {"model": CHUNK_V2_LLM_MODEL, "available": False},
    }
    try:
        installed = get_available_models()
        # Ollama 对未显式带 tag 的模型返回 `<name>:latest`，故两种写法都要认
        status["v2_llm"]["available"] = (
            CHUNK_V2_LLM_MODEL in installed or f"{CHUNK_V2_LLM_MODEL}:latest" in installed
        )
    except Exception:
        pass
    try:
        client = get_client()
        ensure_collection(client)
        status["qdrant"] = True
        status["chunks"] = count_points(client)
    except Exception:
        status["qdrant"] = False
    try:
        embed_texts(["健康检查"])
        status["embedding"] = True
    except Exception:
        status["embedding"] = False
    return status


@router.get("/kb/health")
def kb_health() -> dict:
    return kb_component_status()


@router.get("/kb/papers")
def list_kb_papers() -> dict:
    return {"papers": load_papers()}


@router.post("/kb/upload")
async def upload_kb_paper(file: UploadFile = File(...)) -> dict:
    file_name = (file.filename or "").strip()
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持上传 PDF 文件")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > KB_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件超过 {KB_MAX_UPLOAD_MB}MB 上限")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件内容不是合法的 PDF")

    record = new_record(file_name)
    _, path = save_upload(file_name, content, paper_id=record.paper_id)
    upsert_paper(record)
    # v1 同步建索引：完成后立即返回，用户可马上用 v1 提问（spec-012）。
    # R1：经同一单线程池排队，避免与后台 v2 任务争抢 bge-m3 / 27B 显存。
    result = run_index_task_sync(
        record.paper_id,
        CHUNKER_V1,
        lambda progress: index_paper_chunker(record, path, CHUNKER_V1, progress=progress),
    )
    # v2 异步提交：27B 结构分析较慢，进度由 GET /api/kb/papers 轮询
    _submit_index_task(record.paper_id, path, CHUNKER_V2)
    return result


def _submit_index_task(paper_id: str, path, chunker: str) -> bool:
    """提交一个异步索引任务；已在跑则返回 False（去重，不重复跑）。

    先把状态置为 `indexing`，这样任务在线程池排队时前端就能看到「索引中 0%」，
    而不是停留在旧状态。
    """
    update_chunker_state(paper_id, chunker, status=STATUS_INDEXING, progress=0, error=None)

    def _runner(progress) -> dict:
        data = get_paper(paper_id) or {"paper_id": paper_id, "file_name": "", "uploaded_at": ""}
        return index_paper_chunker(data, path, chunker, progress=progress)

    return submit_index_task(paper_id, chunker, _runner)


@router.post("/kb/papers/{paper_id}/reindex")
def reindex_kb_paper(paper_id: str, request: KBReindexRequest = KBReindexRequest()) -> dict:
    """重建指定论文的索引（spec-012）。

    `chunker` 为 `all`（默认）时重建 v1 + v2 两个版本。
    提交后异步执行，用 `GET /api/kb/papers` 轮询进度。
    """
    paper = get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    path = resolve_paper_path(paper, KB_PAPERS_DIR)
    if not path.exists():
        raise HTTPException(status_code=404, detail="论文原件已丢失，无法重建索引")

    targets = CHUNKERS if request.chunker == "all" else (request.chunker,)
    submitted = {name: _submit_index_task(paper_id, path, name) for name in targets}
    return {"paper_id": paper_id, "submitted": submitted, "paper": get_paper(paper_id)}


@router.delete("/kb/papers/{paper_id}")
def delete_kb_paper(paper_id: str) -> dict:
    if not remove_paper(paper_id):
        raise HTTPException(status_code=404, detail="论文不存在")
    vectors_removed = True
    try:
        delete_paper(paper_id)
    except Exception:
        vectors_removed = False
    return {"deleted": True, "vectors_removed": vectors_removed}


@router.post("/kb/ask")
def kb_ask(request: KBAskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if len(question) > 2_000:
        raise HTTPException(status_code=400, detail="问题最多支持 2000 个字符")
    try:
        available_models: List[str] = get_available_models()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="无法连接 Ollama 服务") from error
    if request.model not in available_models:
        raise HTTPException(status_code=400, detail=f"模型 {request.model} 不存在，请从已安装模型中选择")

    top_k = max(1, min(int(request.top_k or 5), 20))

    chunker = request.chunker or CHUNKER_V1

    def generate():
        started_at = time.perf_counter()
        started = utc_now()
        yield stream_event("meta", model=request.model, top_k=top_k, chunker=chunker)
        yield stream_event("stage", name="retrieving", message="正在检索知识库")
        try:
            # 观测初始化也必须隔离；例如 SDK/client 被替换或初始化异常时，
            # 不得阻断检索与 SSE 主链路。
            try:
                start_trace("kb-ask", tags=["kb"])
            except Exception:
                pass
            try:
                hits = hybrid_search(question, top_k=top_k, chunker=chunker)
            except Exception as error:
                yield stream_event("error", message=f"知识库检索失败：{error}")
                return
            yield stream_event("citations", citations=citation_payloads(hits))
            if not hits:
                # v2 未就绪时明确提示，**不回退到 v1**（spec-012 边界）
                message = "知识库中没有找到相关内容，请先上传论文或换个问法。"
                if chunker == CHUNKER_V2:
                    message = (
                        "所选切分版本（v2 结构感知）尚未就绪或没有命中内容。"
                        "可先切回 v1 提问，或在论文列表点「重建索引」生成 v2。"
                    )
                yield stream_event("token", content=message)
                yield stream_event("done")
                return
            prompt = build_prompt(question, hits)
            run = run_chat(question, request.model, prompt=prompt, think=False)
            kb_metadata = {
                "top_k": top_k,
                "chunker": chunker,
                "hit_count": len(hits),
                "question_chars": len(question),
                "prompt_chars": len(prompt),
            }
            try:
                for ev in run.events:
                    yield stream_event(ev["type"], content=ev["content"])
            except Exception as error:
                yield stream_event("error", message=f"生成失败：{error}")
                # 失败也要留痕：否则失败请求既进不了错误率统计，也丢失了诊断信息。
                if run.result is not None:
                    try:
                        record_ollama_generation(
                            model=request.model,
                            prompt_messages=[{"role": "user", "content": prompt}],
                            result=run.result,
                            route=run.route,
                            name="kb.generation",
                            started_at=started,
                            tags=["kb"],
                            extra_metadata=kb_metadata,
                            success=False,
                            error_type=type(error).__name__,
                        )
                        flush()
                    except Exception:
                        pass
                return
            try:
                record_ollama_generation(
                    model=request.model,
                    prompt_messages=[{"role": "user", "content": prompt}],
                    result=run.result,
                    route=run.route,
                    name="kb.generation",
                    started_at=started,
                    tags=["kb"],
                    extra_metadata=kb_metadata,
                )
                flush()
            except Exception:
                # 上报失败绝不影响 SSE 输出，也绝不替换/吞噬原有业务异常。
                pass
            yield stream_event(
                "debug",
                debug={"elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1), "hits": len(hits)},
            )
            yield stream_event("done")
        finally:
            try:
                end_trace()
            except Exception:
                # trace 收尾失败不能改变已经生成的业务结果或 SSE 契约。
                pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
