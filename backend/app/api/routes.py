import json
import time
import uuid
from typing import List

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.app.api.schemas import ChatRequest, KBAskRequest, KBReindexRequest
from backend.app.agents.article_agent import build_task
from backend.app.core.article_settings import ArticleSettings, load_article_settings, save_article_settings
from backend.app.core.config import CHUNK_V2_LLM_MODEL, KB_MAX_UPLOAD_MB, KB_PAPERS_DIR, MODEL_NAME
from backend.app.domain.article import ArticleCandidate, ArticleTask
from backend.app.graphs.chat import build_chat_graph
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
from backend.app.services.ollama import create_chat_model, get_available_models
from backend.app.services.task_store import TaskStore

router = APIRouter(prefix="/api")
article_tasks = TaskStore()
article_settings = load_article_settings()


def stream_event(event_type: str, **payload: object) -> str:
    data = json.dumps({"type": event_type, **payload}, ensure_ascii=False)
    return f"data: {data}\n\n"


RECOMMEND_MIN_CONFIDENCE = 0.5
RECOMMEND_MAX_COUNT = 3


def top_recommendations(candidates: List[ArticleCandidate]) -> List[ArticleCandidate]:
    """仅保留相似度（confidence）大于 50% 的候选，按相似度降序取前 3 条。"""
    qualified = [candidate for candidate in candidates if (candidate.confidence or 0) > RECOMMEND_MIN_CONFIDENCE]
    qualified.sort(key=lambda candidate: candidate.confidence or 0, reverse=True)
    return qualified[:RECOMMEND_MAX_COUNT]


@router.get("/health")
def health() -> dict:
    try:
        models = get_available_models()
    except httpx.HTTPError:
        models = []
    return {"status": "ok", "model": MODEL_NAME, "models": models}


@router.get("/agent/settings")
def get_agent_settings() -> dict:
    return article_settings.model_dump() | {
        "search_sources": len(article_settings.article_search_urls),
        "download_sources": len(article_settings.article_download_urls),
    }


@router.get("/agent/skills/download-paper")
def get_download_paper_skill() -> dict:
    try:
        status = skill_status(get_available_models())
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail="无法连接 Ollama 服务") from error
    if not status["available"]:
        raise HTTPException(status_code=503, detail=status)
    return status


@router.put("/agent/settings")
def update_agent_settings(settings: ArticleSettings) -> dict:
    global article_settings
    article_settings = settings
    save_article_settings(settings)
    return get_agent_settings()


def article_candidate_payload(candidate: ArticleCandidate) -> dict:
    return {"candidate_id": candidate.candidate_id, **candidate.__dict__}


def download_outcome(status: str) -> tuple[str, str]:
    messages = {
        "not_found": ("not_found", "没有找到可公开访问的 PDF 文件，请打开文章页面或提供合法下载地址。"),
        "invalid": ("invalid_source", "文章来源返回的内容不是 PDF，暂时无法下载。"),
        "rate_limited": ("rate_limited", "文章来源当前限流，请稍后重试。"),
        "login_required": ("login_required", "该文章需要登录，请完成登录后继续。"),
    }
    return messages.get(status, ("source_unavailable", "文章下载来源暂时不可用，请检查文章页面。"))


@router.get("/agent/tasks/{task_id}")
def get_agent_task(task_id: str) -> dict:
    task = article_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {**task.__dict__, "candidates": [article_candidate_payload(item) for item in task.candidates]}


@router.post("/agent/run")
def run_agent(request: ChatRequest):
    query = request.question.strip()
    if not query or len(query) > 500:
        raise HTTPException(status_code=400, detail="问题不能为空且最多支持 500 个字符")
    task = build_task(str(uuid.uuid4()), query)
    article_tasks.save(task)

    def generate():
        yield stream_event("meta", task_id=task.task_id)
        yield stream_event("normalized", normalized_query=task.normalized_query)
        yield stream_event("intent", intent=task.intent, confidence=task.intent_confidence, skill=SKILL_NAME if task.intent == "download_paper" else None)
        if task.intent == "chat":
            try:
                available_models = get_available_models()
                if request.model not in available_models:
                    yield stream_event("error", message=f"模型 {request.model} 不存在")
                    return
                yield stream_event("meta", model=request.model, mode=request.mode)
                graph = build_chat_graph(create_chat_model(request.model))
                for event in graph.stream({"question": task.normalized_query}, stream_mode="custom"):
                    yield stream_event(event["type"], content=event["content"])
                yield stream_event("done")
            except Exception as error:
                yield stream_event("error", message=str(error) if request.mode == "developer" else "普通问答服务不可用")
            return
        yield stream_event("stage", name="searching", message="正在检索文章")
        try:
            task.candidates = search_articles(task.normalized_query, article_settings)
        except httpx.HTTPError as error:
            task.status = "failed"
            task.error = "文章检索来源不可用"
            article_tasks.save(task)
            yield stream_event("error", message=task.error)
            return
        if not task.candidates:
            task.status = "failed"
            task.error = "没有找到候选文章，请补充作者、年份或 DOI"
            article_tasks.save(task)
            yield stream_event("error", message=task.error)
            return
        task.candidates = top_recommendations(task.candidates)
        if not task.candidates:
            task.status = "failed"
            task.error = "没有找到相似度大于 50% 的候选文章，请补充更精确的标题、作者或 DOI"
            article_tasks.save(task)
            yield stream_event("error", message=task.error)
            yield stream_event("done")
            return
        task.status = "awaiting_selection"
        article_tasks.save(task)
        for candidate in task.candidates:
            yield stream_event("candidate", candidate=article_candidate_payload(candidate))
        yield stream_event("result", task_id=task.task_id, message="请选择要下载的文章")
        yield stream_event("done")

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/agent/articles/search")
def search_articles_endpoint(payload: dict):
    query = str(payload.get("query", "")).strip()
    if not query or len(query) > 500:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空且最多支持 500 个字符")
    task = build_task(str(uuid.uuid4()), query)
    if task.intent != "download_paper":
        raise HTTPException(status_code=400, detail="该请求不是论文下载意图")
    try:
        raw_candidates = search_articles(task.normalized_query, article_settings)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="文章检索来源不可用") from error
    task.candidates = top_recommendations(raw_candidates)
    task.status = "awaiting_selection" if task.candidates else "failed"
    task.error = None if task.candidates else "没有找到相似度大于 50% 的候选文章"
    article_tasks.save(task)
    return {"task_id": task.task_id, "status": task.status, "candidates": [article_candidate_payload(item) for item in task.candidates], "error": task.error}


@router.post("/agent/articles/download")
def download_article_endpoint(payload: dict):
    task = article_tasks.get(payload.get("task_id"))
    candidate_id = payload.get("candidate_id")
    candidate = next((item for item in task.candidates if item.candidate_id == candidate_id), None) if task else None
    if not task or not candidate:
        raise HTTPException(status_code=404, detail="任务或候选文章不存在")
    use_skill = payload.get("use_skill")
    if use_skill is None:
        try:
            use_skill = skill_status(get_available_models())["available"]
        except httpx.HTTPError:
            use_skill = False
    if use_skill:
        try:
            status = skill_status(get_available_models())
        except httpx.HTTPError as error:
            raise HTTPException(status_code=503, detail="无法连接 Ollama 服务") from error
        if not status["available"]:
            raise HTTPException(status_code=503, detail=status)
    task.selected_candidate_id = candidate_id
    if not candidate.pdf_url:
        pdf_status, resolved_url = probe_pdf_url(candidate, article_settings)
        candidate.pdf_url_status = pdf_status
        if resolved_url and pdf_status == "public_pdf":
            candidate.pdf_url = resolved_url
        article_tasks.save(task)
        if pdf_status == "login_required":
            task.status = "waiting_login"
            task.human_action = "waiting_login"
            candidate.requires_login = True
            article_tasks.save(task)
            outcome, user_message = download_outcome(pdf_status)
            return {"status": "waiting_login", "download_outcome": outcome, "user_message": user_message, "task_id": task.task_id, "candidate_id": candidate_id, "source_name": candidate.source_name, "login_url": candidate.article_url or candidate.pdf_url}
        if pdf_status != "public_pdf":
            task.status = "failed"
            outcome, task.error = download_outcome(pdf_status)
            article_tasks.save(task)
            raise HTTPException(status_code=404, detail={"download_outcome": outcome, "user_message": task.error, "article_url": candidate.article_url})
    if candidate.requires_login:
        task.status = "waiting_login"
        task.human_action = "waiting_login"
        article_tasks.save(task)
        return {"status": "waiting_login", "task_id": task.task_id, "candidate_id": candidate_id, "source_name": candidate.source_name, "login_url": candidate.article_url or candidate.pdf_url}
    executor = download_under_skill if use_skill else download_article
    try:
        result = next(executor(candidate, article_settings))
    except PermissionError as error:
        task.status = "waiting_login"
        task.human_action = "waiting_login"
        article_tasks.save(task)
        return {"status": "waiting_login", "download_outcome": "login_required", "user_message": "该文章需要登录，请完成登录后继续。", "task_id": task.task_id, "candidate_id": candidate_id, "source_name": candidate.source_name, "login_url": candidate.article_url or candidate.pdf_url, "message": str(error)}
    except (httpx.HTTPError, ValueError) as error:
        task.status = "failed"
        task.error = str(error)
        article_tasks.save(task)
        raise HTTPException(status_code=502, detail=task.error) from error
    if result.get("type") == "error":
        task.status = "failed"
        task.error = result.get("user_message", "下载失败")
        article_tasks.save(task)
        raise HTTPException(
            status_code=502,
            detail={"download_outcome": result.get("download_outcome", "source_unavailable"), "user_message": task.error},
        )
    task.status = "completed"
    task.result = result
    article_tasks.save(task)
    return {"status": task.status, **result}


@router.post("/agent/articles/probe")
def probe_article_endpoint(payload: dict):
    task = article_tasks.get(payload.get("task_id"))
    candidate_id = payload.get("candidate_id")
    candidate = next((item for item in task.candidates if item.candidate_id == candidate_id), None) if task else None
    if not task or not candidate:
        raise HTTPException(status_code=404, detail="任务或候选文章不存在")
    status, resolved_url = probe_pdf_url(candidate, article_settings)
    candidate.pdf_url_status = status
    if status == "public_pdf":
        candidate.pdf_url = resolved_url
    elif status == "login_required":
        candidate.requires_login = True
    article_tasks.save(task)
    outcome, user_message = download_outcome(status)
    return {"candidate_id": candidate_id, "pdf_url_status": status, "download_outcome": "downloaded" if status == "public_pdf" else outcome, "user_message": "已找到可访问的 PDF 地址，可以下载。" if status == "public_pdf" else user_message, "article_url": candidate.article_url, "pdf_url": candidate.pdf_url, "requires_login": candidate.requires_login}


@router.post("/agent/articles/plan-download")
def plan_article_download(payload: dict):
    task = article_tasks.get(payload.get("task_id"))
    candidate_id = payload.get("candidate_id")
    candidate = next((item for item in task.candidates if item.candidate_id == candidate_id), None) if task else None
    if not task or not candidate:
        raise HTTPException(status_code=404, detail="任务或候选文章不存在")
    try:
        status = skill_status(get_available_models())
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail="无法连接 Ollama 服务") from error
    if not status["available"]:
        raise HTTPException(status_code=503, detail=status)
    try:
        plan = build_skill_plan(candidate, str(payload.get("model") or status["worker_model"]))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="子模型无法生成下载计划") from error
    return {"task_id": task.task_id, **plan}


@router.post("/agent/tasks/{task_id}/human-actions/login-completed")
def login_completed(task_id: str, payload: dict):
    task = article_tasks.get(task_id)
    if not task or task.status != "waiting_login":
        raise HTTPException(status_code=400, detail="任务当前不在等待登录状态")
    candidate_id = payload.get("candidate_id")
    candidate = next((item for item in task.candidates if item.candidate_id == candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="候选文章不存在")
    candidate.requires_login = False
    task.human_action = "login_completed"
    article_tasks.save(task)
    return download_article_endpoint({"task_id": task_id, "candidate_id": candidate_id})


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
    conversation_graph = build_chat_graph(create_chat_model(selected_model))

    def generate():
        started_at = time.perf_counter()
        yield stream_event("meta", model=selected_model, mode=request.mode)
        try:
            for event in conversation_graph.stream({"question": question}, stream_mode="custom"):
                yield stream_event(event["type"], content=event["content"])
        except Exception as error:
            detail = str(error) if request.mode == "developer" else f"无法连接 Ollama，请确认服务已启动且模型 {MODEL_NAME} 已安装"
            yield stream_event("error", detail=detail)
            return

        if request.mode == "developer":
            yield stream_event("debug", debug={"mode": request.mode, "input_length": len(question), "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1), "graph_node": "ask_model"})
        yield stream_event("done")

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== 知识库 / RAG（spec-011）====================

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
    if not get_paper(paper_id):
        raise HTTPException(status_code=404, detail="论文不存在")
    path = KB_PAPERS_DIR / f"{paper_id}.pdf"
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
        yield stream_event("meta", model=request.model, top_k=top_k, chunker=chunker)
        yield stream_event("stage", name="retrieving", message="正在检索知识库")
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
        chat_model = create_chat_model(request.model)
        try:
            for chunk in chat_model.stream(build_prompt(question, hits)):
                content = getattr(chunk, "content", "") or ""
                if content:
                    yield stream_event("token", content=content)
        except Exception as error:
            yield stream_event("error", message=f"生成失败：{error}")
            return
        yield stream_event(
            "debug",
            debug={"elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1), "hits": len(hits)},
        )
        yield stream_event("done")

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
