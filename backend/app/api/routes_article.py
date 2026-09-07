import uuid

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.agents.article_agent import build_task
from backend.app.api.schemas import (
    ChatRequest,
)
from backend.app.domain.article import ArticleCandidate
from backend.app.observability import flush, record_ollama_generation, utc_now
from backend.app.platform.settings.settings_repository import (
    ArticleSettings,
    save_article_settings,
)
from backend.app.services.article_download import download_article, probe_pdf_url
from backend.app.services.article_search import search_articles
from backend.app.services.download_paper_skill import SKILL_NAME, build_skill_plan, download_under_skill, skill_status
from backend.app.services.ollama import get_available_models, run_chat

router = APIRouter()

from backend.app.api.common import *  # noqa: F401,F403


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
    global article_settings, paper_discovery_search_service, paper_import_batch_service, paper_import_batch_store_path, paper_browser_manager
    article_settings = settings
    # `routes.article_settings` 是共享 facade（common helper / routes_paper / 测试
    # 都通过它读取最新设置）。上面只重新绑定了本模块的全局，这里同步 facade，
    # 否则其它模块经 star-import 拿到的仍是旧快照。
    from backend.app.api import routes
    routes.article_settings = settings
    # Rebuild paper-discovery dependencies on the next request so changed
    # path/timeout/default-year settings take effect without a process restart.
    paper_discovery_search_service = None
    paper_import_batch_service = None
    paper_import_batch_store_path = None
    if paper_browser_manager is not None:
        try:
            paper_browser_manager.close()
        except Exception:
            pass
    paper_browser_manager = None
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
                started = utc_now()
                run = run_chat(task.normalized_query, request.model)
                try:
                    for event in run.events:
                        yield stream_event(event["type"], content=event["content"])
                except Exception as error:
                    if run.result is not None:
                        try:
                            record_ollama_generation(
                                model=request.model,
                                prompt_messages=[{"role": "user", "content": task.normalized_query}],
                                result=run.result,
                                route=run.route,
                                started_at=started,
                                tags=["chat", "agent"],
                                # 失败必须显式标记，避免污染成功耗时分位
                                success=False,
                                error_type=type(error).__name__,
                             )
                            flush()
                        except Exception:
                            pass
                    raise
                if run.result is not None:
                    try:
                        record_ollama_generation(
                            model=request.model,
                            prompt_messages=[{"role": "user", "content": task.normalized_query}],
                            result=run.result,
                            route=run.route,
                            started_at=started,
                            tags=["chat", "agent"],
                          )
                        flush()
                    except Exception:
                        pass
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



