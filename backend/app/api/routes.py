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

router = APIRouter(prefix="/api")
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


def _paper_discovery_enabled() -> bool:
    """读取请求时的开关，便于关闭后立即停止新增检索请求。"""
    return os.getenv("PAPER_DISCOVERY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _paper_api_error(status_code: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "retryable": retryable, "request_id": uuid.uuid4().hex},
    )


def _paper_store() -> PaperDiscoveryStore:
    global paper_discovery_store, paper_discovery_store_path
    configured_path = Path(article_settings.paper_discovery_db_path)
    if not configured_path.is_absolute():
        configured_path = BASE_DIR / configured_path
    if paper_discovery_store is None or paper_discovery_store_path != configured_path:
        paper_discovery_store = PaperDiscoveryStore(database_path=configured_path)
        paper_discovery_store_path = configured_path
    return paper_discovery_store


def _paper_search_service() -> PaperDiscoverySearchService:
    global paper_discovery_search_service
    if paper_discovery_search_service is None:
        timeout = article_settings.paper_discovery_request_timeout_seconds
        paper_discovery_search_service = PaperDiscoverySearchService(
            dblp_source=DBLPPublicationSource(timeout=timeout),
            openalex_enricher=OpenAlexEnricher(timeout=timeout),
            store=_paper_store(),
            settings=article_settings,
            default_years=article_settings.paper_discovery_default_years,
        )
    return paper_discovery_search_service


def _paper_batch_service() -> PaperImportBatchService:
    """Build the batch orchestrator lazily so routes remain test-injectable."""
    global paper_import_batch_service, paper_import_batch_store_path
    configured_path = Path(article_settings.paper_discovery_db_path)
    if not configured_path.is_absolute():
        configured_path = BASE_DIR / configured_path
    if paper_import_batch_service is None or paper_import_batch_store_path != configured_path:
        store = PaperImportBatchStore(database_path=configured_path)
        paper_import_batch_service = PaperImportBatchService(
            store=store,
            discovery_store=_paper_store(),
            importer=import_candidate,
            settings=article_settings,
            allowed_hosts_resolver=_paper_candidate_hosts,
            conference_short_name_resolver=lambda candidate: next(
                (source.short_name for source in _paper_store().list_conferences()
                 if source.conference_id == _paper_candidate_value(candidate, "conference_id")),
                None,
            ),
        )
        paper_import_batch_store_path = configured_path
    return paper_import_batch_service


def _paper_browser_manager() -> PaperBrowserManager:
    global paper_browser_manager
    if paper_browser_manager is None:
        paper_browser_manager = PaperBrowserManager(settings=article_settings)
    return paper_browser_manager


def _conference_payload(source) -> dict:
    return asdict(source)


def _candidate_payload(candidate) -> dict:
    return asdict(candidate)


def _validation_error_code(error: ValidationError) -> str:
    locations = {str(item) for detail in error.errors() for item in detail.get("loc", ())}
    if "query" in locations:
        return "INVALID_QUERY"
    if "years" in locations:
        return "INVALID_YEARS"
    if "limit" in locations:
        return "INVALID_LIMIT"
    if "conference_id" in locations:
        return "INVALID_CONFERENCE"
    if "publication_scope" in locations:
        return "INVALID_PUBLICATION_SCOPE"
    return "INVALID_SEARCH_REQUEST"


def _accepted_validation_error_code(error: ValidationError) -> str:
    locations = {str(item) for detail in error.errors() for item in detail.get("loc", ())}
    for field, code in (
        ("year", "INVALID_ACCEPTED_YEAR"),
        ("cycle", "INVALID_ACCEPTED_CYCLE"),
        ("q", "INVALID_ACCEPTED_QUERY"),
        ("limit", "INVALID_ACCEPTED_LIMIT"),
    ):
        if field in locations:
            return code
    return "INVALID_ACCEPTED_REQUEST"


def paper_request_validation_error_response(request: Request, error: RequestValidationError) -> JSONResponse | None:
    """将论文接口的声明式请求校验错误映射为稳定错误体。

    这两个接口的 Pydantic 参数在进入路由函数前由 FastAPI 校验，因此不能
    在函数内部捕获 ``ValidationError``；通过应用级处理器只拦截论文接口，
    其余接口仍保留 FastAPI 默认的 ``detail`` 响应。
    """
    path = request.url.path
    if request.method == "PATCH" and path.startswith("/api/papers/conferences/"):
        return _paper_api_error(422, "INVALID_CONFERENCE_UPDATE", "会议更新请求只支持 enabled 布尔值")
    if request.method == "POST" and path == "/api/papers/search":
        code = _validation_error_code(error)
        message = {
            "INVALID_QUERY": "query 必须为 1-500 个字符",
            "INVALID_YEARS": "years 必须为不超过 10 个整数的列表",
            "INVALID_LIMIT": "limit 必须在 1 到 100 之间",
            "INVALID_CONFERENCE": "conference_id 必须为非空字符串",
            "INVALID_PUBLICATION_SCOPE": "publication_scope 只支持 published、accepted 或 all",
        }.get(code, "搜索请求参数无效")
        return _paper_api_error(422, code, message)
    if request.method == "GET" and path.startswith("/api/papers/conferences/") and path.endswith("/accepted"):
        code = _accepted_validation_error_code(error)
        message = {
            "INVALID_ACCEPTED_YEAR": "year 必须为 1900 到当前年份的整数",
            "INVALID_ACCEPTED_CYCLE": "cycle 只支持 cycle1、cycle2 等受控格式",
            "INVALID_ACCEPTED_QUERY": "q 必须为 1-500 个字符",
            "INVALID_ACCEPTED_LIMIT": "limit 必须在 1 到 100 之间",
        }.get(code, "accepted 查询参数无效")
        return _paper_api_error(422, code, message)
    if request.method == "POST" and path == "/api/papers/imports":
        locations = {str(item) for detail in error.errors() for item in detail.get("loc", ())}
        body = getattr(error, "body", None)
        # Union validation reports the batch model's missing ``candidate_ids``
        # even for the retained Task05 single-paper shape.  The parsed body is
        # safe to inspect here and lets the two stable validation codes remain
        # backwards compatible without accepting any extra metadata.
        if isinstance(body, dict) and "candidate_id" in body and "candidate_ids" not in body:
            return _paper_api_error(422, "INVALID_IMPORT_REQUEST", "search_id 和 candidate_id 必须为非空字符串")
        return _paper_api_error(422, "INVALID_IMPORT_BATCH_REQUEST", "search_id、candidate_ids 和 idempotency_key 参数无效")
    if request.method == "POST" and path == "/api/papers/import-batches":
        return _paper_api_error(422, "INVALID_IMPORT_BATCH_REQUEST", "search_id、candidate_ids 和 idempotency_key 参数无效")
    if request.method == "POST" and path.startswith("/api/papers/import-items/") and path.endswith("/login"):
        return _paper_api_error(422, "INVALID_LOGIN_REQUEST", "登录动作不接受 URL 或凭证")
    if request.method == "POST" and path.startswith("/api/papers/import-items/") and path.endswith("/resume"):
        return _paper_api_error(422, "INVALID_RESUME_REQUEST", "续传动作不接受 URL 或凭证")
    return None


def stream_event(event_type: str, **payload: object) -> str:
    data = json.dumps({"type": event_type, **payload}, ensure_ascii=False)
    return f"data: {data}\n\n"


RECOMMEND_MIN_CONFIDENCE = 0.5
RECOMMEND_MAX_COUNT = 3
CONFERENCE_SEARCH_QUERY_MAX_LENGTH = 100


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
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "models": models,
        "paper_discovery_enabled": _paper_discovery_enabled(),
    }


# ==================== 论文检索（spec-015 / Task03）====================

@router.get("/papers/conferences/search")
def search_paper_conferences(q: str = ""):
    """Search only the conference sources already configured on the server.

    This endpoint intentionally performs no venue discovery or external
    request.  The client receives the same safe payload as the conference
    listing endpoint, and the server remains the authority for every source
    identity returned here.
    """
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    query = q.strip()
    if not query:
        return _paper_api_error(400, "INVALID_CONFERENCE_QUERY", "会议搜索关键词不能为空")
    if len(query) > CONFERENCE_SEARCH_QUERY_MAX_LENGTH:
        return _paper_api_error(400, "CONFERENCE_QUERY_TOO_LONG", "会议搜索关键词不得超过 100 个字符")

    try:
        conferences = _paper_store().list_conferences()
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)

    needle = query.casefold()
    matches = [
        source for source in conferences
        if any(
            needle in str(value or "").casefold()
            for value in (source.name, source.short_name, source.conference_id)
        )
    ]
    return {"conferences": [_conference_payload(source) for source in matches]}


@router.get("/papers/conferences")
def list_paper_conferences():
    """列出服务端已配置会议，包含已停用的内置会议状态。"""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        conferences = _paper_store().list_conferences()
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    return {"conferences": [_conference_payload(source) for source in conferences]}


@router.patch("/papers/conferences/{conference_id}")
def update_paper_conference(conference_id: str, request: ConferenceUpdateRequest):
    """只允许修改已配置会议的 enabled 状态；不提供自定义会议入口。"""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        store = _paper_store()
        source = next((item for item in store.list_conferences() if item.conference_id == conference_id), None)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if source is None:
        return _paper_api_error(404, "CONFERENCE_NOT_FOUND", "会议配置不存在")
    try:
        updated = replace(source, enabled=request.enabled)
        store.save_conference(updated)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "会议配置暂时无法更新", True)
    return {"conference": _conference_payload(updated)}


@router.delete("/papers/conferences/{conference_id}")
def delete_paper_conference(conference_id: str):
    """内置会议不可删除；自定义会议管理在本任务范围外。"""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        source = next(
            (item for item in _paper_store().list_conferences() if item.conference_id == conference_id), None
        )
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if source is None:
        return _paper_api_error(404, "CONFERENCE_NOT_FOUND", "会议配置不存在")
    if source.built_in:
        return _paper_api_error(409, "BUILT_IN_CONFERENCE_PROTECTED", "内置会议不可删除，请使用启停操作")
    return _paper_api_error(409, "CUSTOM_CONFERENCE_UNSUPPORTED", "自定义会议管理尚未开放")


@router.post("/papers/search")
def search_papers(request: PaperSearchRequest):
    """检索单个已启用会议的论文；候选和搜索会话均由服务端生成。"""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        store = _paper_store()
        source = next((item for item in store.list_conferences() if item.conference_id == request.conference_id), None)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if source is None:
        return _paper_api_error(400, "CONFERENCE_NOT_CONFIGURED", "conference_id 不是服务端已配置会议")
    if not source.enabled:
        return _paper_api_error(400, "CONFERENCE_DISABLED", "conference_id 对应会议当前已停用")
    try:
        result = _paper_search_service().search(
            source, request.query, request.years, request.limit,
            publication_scope=request.publication_scope,
        )
    except PaperDiscoverySearchError as error:
        status = 400 if error.error_code.startswith(("INVALID_", "CONFERENCE_")) else 503
        return _paper_api_error(status, error.error_code, str(error), status != 400)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_UNAVAILABLE", "论文检索服务暂时不可用", True)

    candidates = list(getattr(result, "candidates", ()) or ())
    error_code = getattr(result, "error_code", None)
    if error_code and not candidates:
        return _paper_api_error(424, str(error_code), "论文检索来源暂时不可用，请稍后重试", True)
    warnings = list(getattr(result, "warnings", ()) or ())
    session = result.session
    return {
        "search_id": session.search_id,
        "query": session.query,
        "expires_at": session.expires_at,
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
        "warnings": warnings,
        "degraded": bool(warnings or error_code),
    }


@router.get("/papers/conferences/{conference_id}/accepted")
def list_accepted_papers(
    conference_id: str,
    request: Annotated[PaperAcceptedRequest, Query()],
):
    """通过服务端 accepted source 读取受控 USENIX 路线并保存候选快照。"""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        source = next((item for item in _paper_store().list_conferences() if item.conference_id == conference_id), None)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if source is None:
        return _paper_api_error(404, "CONFERENCE_NOT_FOUND", "会议配置不存在")
    if not source.enabled:
        return _paper_api_error(400, "CONFERENCE_DISABLED", "conference_id 对应会议当前已停用")
    accepted_route = next(
        (route for route in source.discovery_routes
         if isinstance(route, dict) and route.get("route_type") == "usenix_accepted"
         and route.get("enabled", True) is True),
        None,
    )
    if accepted_route is None:
        return _paper_api_error(400, "ACCEPTED_ROUTE_NOT_CONFIGURED", "会议未配置 accepted 论文来源")
    try:
        service = _paper_search_service()
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_UNAVAILABLE", "论文检索服务暂时不可用", True)
    accepted_source = getattr(service, "accepted_source", None)
    search = getattr(accepted_source, "search", None)
    if not callable(search):
        return _paper_api_error(424, "ACCEPTED_SEARCH_UNSUPPORTED", "accepted 论文检索暂不可用", True)
    current_year = datetime.now(timezone.utc).year
    default_years = getattr(service, "default_years", article_settings.paper_discovery_default_years)
    if request.year is not None and request.year > current_year:
        return _paper_api_error(422, "INVALID_ACCEPTED_YEAR", "year 必须为 1900 到当前年份的整数")
    years = [request.year] if request.year is not None else list(range(current_year - default_years, current_year))
    limit = request.limit or getattr(service, "default_limit", article_settings.paper_discovery_search_limit)
    query = request.q or ""
    cycle = (request.cycle or "cycle1").removeprefix("cycle")
    try:
        result = search(source, query, years, limit=limit, cycle=cycle)
    except Exception:
        return _paper_api_error(424, "USENIX_UNAVAILABLE", "accepted 论文来源暂时不可用，请稍后重试", True)

    records = list(getattr(result, "records", ()) or ())
    warnings = list(getattr(result, "warnings", ()) or ())
    error_code = getattr(result, "error_code", None)
    search_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    ttl = getattr(service, "search_ttl_seconds", 86400)
    session = SearchSession(
        search_id=search_id,
        query=query,
        expires_at=(now + timedelta(seconds=ttl)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        created_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    candidates = []
    for initial_rank, record in enumerate(records):
        candidate = service._candidate_from_record(record, source, search_id, query)
        if candidate is None:
            continue
        candidate.initial_rank = initial_rank
        candidate.rank = len(candidates) + 1
        candidates.append(candidate)
    try:
        service.store.save_search(session, candidates)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if error_code and not candidates:
        return _paper_api_error(424, str(error_code), "accepted 论文来源暂时不可用，请稍后重试", True)
    return {
        "search_id": session.search_id,
        "query": session.query,
        "expires_at": session.expires_at,
        "candidates": [_candidate_payload(candidate) for candidate in candidates[:limit]],
        "warnings": warnings,
        "degraded": bool(warnings or error_code),
    }


_PAPER_IMPORT_ERROR_STATUS = {
    PAPER_ALREADY_EXISTS: 409,
    DOWNLOAD_BLOCKED: 400,
    LOGIN_REQUIRED: 424,
    DOWNLOAD_TIMEOUT: 424,
    INVALID_PDF: 502,
    PDF_TOO_LARGE: 502,
    PDF_NOT_FOUND: 502,
    KB_IMPORT_FAILED: 424,
}


def _paper_import_error_response(code: str, message: str, *, retryable: bool = False) -> JSONResponse:
    """Map importer errors to the paper API's stable error contract."""
    normalized = safe_import_error_code(code, KB_IMPORT_FAILED)
    status = _PAPER_IMPORT_ERROR_STATUS.get(normalized, 424)
    return _paper_api_error(status, normalized, safe_import_error_message(normalized), retryable)


def _paper_import_result_payload(result: object) -> dict:
    """Keep the API response limited to the documented import result fields."""
    if hasattr(result, "to_dict"):
        raw = result.to_dict()
    elif isinstance(result, dict):
        raw = result
    else:
        raw = {field: getattr(result, field, None) for field in (
            "paper_id", "stored_name", "status", "error_code", "existing",
        )}
    return {
        "paper_id": raw.get("paper_id"),
        "stored_name": raw.get("stored_name"),
        "status": str(raw.get("status") or "failed"),
        "error_code": raw.get("error_code"),
        "existing": bool(raw.get("existing", False)),
    }


def _paper_candidate_value(candidate: object, name: str, default=None):
    if isinstance(candidate, dict):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _paper_candidate_hosts(candidate: object) -> set[str]:
    """Return only the fixed server-side download host allowlist.

    ``candidate.pdf_url`` is a persisted external snapshot value, not a
    trust decision.  Never add its hostname here; the downloader validates
    that target against this fixed set on every hop.
    """
    hosts: set[str] = set()
    configured_hosts = getattr(article_settings, "paper_discovery_allowed_hosts", [])
    # Keep existing ArticleSettings download origins as a backwards-compatible
    # server configuration fallback when the dedicated setting is empty.
    configured = configured_hosts or article_settings.article_download_urls
    for value in configured:
        host = urlsplit(value).hostname if "://" in value else value
        if host:
            hosts.add(host.casefold())
    return hosts


def _paper_search_expired(expires_at: str) -> bool:
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        # A malformed server-side session is not importable and should not
        # result in an external request.
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= datetime.now(timezone.utc)


def _import_single_paper(request: PaperImportRequest):
    """Import exactly one candidate resolved from a server-side search snapshot."""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")

    try:
        store = _paper_store()
        session = store.get_search_session(request.search_id)
        if session is None:
            return _paper_api_error(404, "SEARCH_NOT_FOUND", "搜索会话不存在")
        if _paper_search_expired(session.expires_at):
            return _paper_api_error(400, "SEARCH_EXPIRED", "搜索会话已过期，不能继续导入")
        candidate = store.get_candidate(request.search_id, request.candidate_id)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if candidate is None:
        return _paper_api_error(404, "CANDIDATE_NOT_FOUND", "候选论文不存在")

    try:
        source = next(
            (item for item in store.list_conferences()
             if item.conference_id == _paper_candidate_value(candidate, "conference_id")),
            None,
        )
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    if source is None:
        return _paper_api_error(400, "CONFERENCE_NOT_CONFIGURED", "候选论文所属会议不是服务端已配置会议")

    try:
        result = import_candidate(
            candidate,
            article_settings,
            _paper_candidate_hosts(candidate),
            conference_short_name=source.short_name,
        )
    except PaperDownloadError as error:
        return _paper_import_error_response(
            error.code,
            error.message,
            retryable=error.code in {LOGIN_REQUIRED, DOWNLOAD_TIMEOUT},
        )
    except PaperImportError as error:
        return _paper_import_error_response(error.code, error.message, retryable=error.retryable)
    except Exception:
        return _paper_import_error_response(KB_IMPORT_FAILED, "知识库导入失败", retryable=True)

    payload = _paper_import_result_payload(result)
    if payload["error_code"]:
        return _paper_import_error_response(
            str(payload["error_code"]),
            "论文已在知识库中" if payload["error_code"] == PAPER_ALREADY_EXISTS else "论文导入失败",
            retryable=False,
        )
    return payload


_PAPER_BATCH_ERROR_STATUS = {
    "BATCH_NOT_FOUND": 404,
    "ITEM_NOT_FOUND": 404,
    "SEARCH_NOT_FOUND": 404,
    "CANDIDATE_NOT_FOUND": 404,
    "SEARCH_EXPIRED": 400,
    "INVALID_SEARCH_SNAPSHOT": 400,
    "INVALID_STATE_TRANSITION": 400,
    "INVALID_SEARCH_ID": 400,
    "INVALID_CANDIDATE_ID": 400,
    "EMPTY_BATCH": 400,
    "BATCH_LIMIT_EXCEEDED": 400,
    "DATABASE_LOCKED": 503,
}


def _paper_batch_error_response(error: PaperImportBatchServiceError) -> JSONResponse:
    code = str(getattr(error, "code", "IMPORT_BATCH_ERROR"))
    if code not in _PAPER_BATCH_ERROR_STATUS:
        code = "IMPORT_BATCH_ERROR"
    status = _PAPER_BATCH_ERROR_STATUS.get(code, 424)
    # Service exception text is not a transport for API responses.  Keep a
    # fixed message per stable code so URLs and credentials cannot leak even
    # when an injected store/library raises an unsafe message.
    messages = {
        "BATCH_NOT_FOUND": "导入批次不存在",
        "ITEM_NOT_FOUND": "导入条目不存在",
        "SEARCH_NOT_FOUND": "搜索会话不存在",
        "CANDIDATE_NOT_FOUND": "候选论文不存在",
        "SEARCH_EXPIRED": "搜索会话已过期",
        "INVALID_SEARCH_SNAPSHOT": "搜索候选快照无效",
        "INVALID_STATE_TRANSITION": "当前状态不允许此操作",
        "INVALID_SEARCH_ID": "搜索会话编号无效",
        "INVALID_CANDIDATE_ID": "候选编号无效",
        "EMPTY_BATCH": "批量导入至少需要一项",
        "BATCH_LIMIT_EXCEEDED": "单批最多 20 项",
        "DATABASE_LOCKED": "批次状态库正忙，请稍后重试",
        "IMPORT_BATCH_ERROR": "批量导入失败",
    }
    return _paper_api_error(status, code, messages.get(code, "批量导入失败"), bool(getattr(error, "retryable", False)))


def _safe_browser_error_message(error: BrowserManagerError) -> str:
    """Keep browser adapter details (URLs/headers) out of public errors."""
    message = str(getattr(error, "message", "浏览器当前不可用"))
    lowered = message.casefold()
    if any(token in lowered for token in ("cookie", "authorization", "password", "token", "secret", "http://", "https://")):
        return "浏览器当前不可用"
    return message[:500]


def _safe_import_error_message(value: object, code: object) -> str | None:
    """Return human-readable item errors without forwarding URLs or credentials."""
    if not value:
        return None
    return safe_import_error_message(code)


def _paper_batch_payload(batch: object, items: list[object]) -> dict:
    raw = batch.to_dict() if hasattr(batch, "to_dict") else dict(batch) if isinstance(batch, dict) else {
        name: getattr(batch, name, None) for name in (
            "batch_id", "search_id", "status", "state", "created_at", "updated_at",
            "total_count", "completed_count", "failed_count", "waiting_login_count", "cancelled_count",
        )
    }
    status = str(raw.get("status") or raw.get("state") or "queued")
    payload = {
        "batch_id": raw.get("batch_id"),
        "search_id": raw.get("search_id"),
        "status": status,
        "state": status,
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "total_count": int(raw.get("total_count") or 0),
        "completed_count": int(raw.get("completed_count") or 0),
        "failed_count": int(raw.get("failed_count") or 0),
        "waiting_login_count": int(raw.get("waiting_login_count") or 0),
        "cancelled_count": int(raw.get("cancelled_count") or 0),
        "items": [],
    }
    for item in items:
        value = item.to_dict() if hasattr(item, "to_dict") else dict(item) if isinstance(item, dict) else {
            name: getattr(item, name, None) for name in (
                "item_id", "batch_id", "candidate_id", "status", "state", "stored_name", "paper_id",
                "error_code", "error_message", "attempt_count", "created_at", "updated_at",
            )
        }
        item_status = str(value.get("status") or value.get("state") or "queued")
        payload["items"].append({
            "item_id": value.get("item_id"),
            "batch_id": value.get("batch_id"),
            "candidate_id": value.get("candidate_id"),
            "status": item_status,
            "state": item_status,
            "stored_name": value.get("stored_name"),
            "paper_id": value.get("paper_id"),
            "error_code": value.get("error_code"),
            "error_message": _safe_import_error_message(value.get("error_message"), value.get("error_code")),
            "attempt_count": int(value.get("attempt_count") or 0),
            "created_at": value.get("created_at"),
            "updated_at": value.get("updated_at"),
        })
    return payload


def _paper_batch_status_payload(service: PaperImportBatchService, batch_id: str) -> dict:
    result = service.get_status(batch_id)
    if not isinstance(result, dict) or result.get("batch") is None:
        raise PaperImportBatchServiceError("BATCH_NOT_FOUND", "导入批次不存在")
    return _paper_batch_payload(result["batch"], list(result.get("items") or []))


def _paper_server_snapshot(search_id: str, candidate_ids: list[str]) -> tuple[object, list[object]]:
    """Resolve all import inputs from the server-owned search snapshot."""
    store = _paper_store()
    session = store.get_search_session(search_id)
    if session is None:
        raise PaperImportBatchServiceError("SEARCH_NOT_FOUND", "搜索会话不存在")
    if _paper_search_expired(getattr(session, "expires_at", "")):
        raise PaperImportBatchServiceError("SEARCH_EXPIRED", "搜索会话已过期")
    candidates = []
    for candidate_id in candidate_ids:
        candidate = store.get_candidate(search_id, candidate_id)
        if candidate is None:
            raise PaperImportBatchServiceError("CANDIDATE_NOT_FOUND", "候选论文不存在")
        candidates.append(candidate)
    return session, candidates


def _paper_snapshot_for_item(service: PaperImportBatchService, item_id: str) -> list[object]:
    item = service.store.get_item(item_id)
    if item is None:
        raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
    batch = service.store.get_batch(item.batch_id)
    if batch is None:
        raise PaperImportBatchServiceError("BATCH_NOT_FOUND", "导入批次不存在")
    discovery = getattr(service, "discovery_store", None) or _paper_store()
    session = discovery.get_search_session(batch.search_id)
    if session is None:
        raise PaperImportBatchServiceError("SEARCH_NOT_FOUND", "搜索会话不存在")
    if _paper_search_expired(getattr(session, "expires_at", "")):
        raise PaperImportBatchServiceError("SEARCH_EXPIRED", "搜索会话已过期")
    candidates = list(discovery.get_candidates(batch.search_id))
    if not any(_paper_candidate_value(candidate, "candidate_id") == item.candidate_id for candidate in candidates):
        raise PaperImportBatchServiceError("CANDIDATE_NOT_FOUND", "候选论文不存在")
    # The service validates a complete batch snapshot before resuming one item;
    # returning every server candidate keeps that check intact for mixed batches.
    return candidates


def _create_paper_import_batch(request: PaperImportBatchRequest):
    """Create a batch from only the server-owned search snapshot."""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    if len(set(request.candidate_ids)) > 20:
        return _paper_api_error(400, "BATCH_LIMIT_EXCEEDED", "单批最多 20 项")
    try:
        session, candidates = _paper_server_snapshot(request.search_id, request.candidate_ids)
        service = _paper_batch_service()
        batch = service.create_batch(
            request.search_id,
            request.candidate_ids,
            search_session=session,
            candidates=candidates,
            idempotency_key=request.idempotency_key,
            auto_run=True,
        )
        return _paper_batch_status_payload(service, batch.batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception:
        return _paper_api_error(503, "IMPORT_BATCH_UNAVAILABLE", "批量导入服务暂时不可用", True)


@router.post("/papers/imports", response_model=PaperImportBatchResponse | PaperImportResponse)
def import_paper(request: PaperImportBatchRequest | PaperImportRequest):
    """Canonical batch endpoint, with the Task05 single-paper shape retained."""
    if isinstance(request, PaperImportRequest):
        return _import_single_paper(request)
    return _create_paper_import_batch(request)


@router.post("/papers/import-batches")
def create_paper_import_batch(request: PaperImportBatchRequest):
    """Compatibility alias for the pre-Task06 batch path."""
    return _create_paper_import_batch(request)


@router.get("/papers/imports/{batch_id}", response_model=PaperImportBatchResponse)
@router.get("/papers/import-batches/{batch_id}", response_model=PaperImportBatchResponse)
def get_paper_import_batch(batch_id: str):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        return _paper_batch_status_payload(_paper_batch_service(), batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception:
        return _paper_api_error(503, "IMPORT_BATCH_UNAVAILABLE", "批量导入服务暂时不可用", True)


@router.post("/papers/imports/{batch_id}/retry", response_model=PaperImportBatchResponse)
@router.post("/papers/import-batches/{batch_id}/retry", response_model=PaperImportBatchResponse)
def retry_paper_import_batch(batch_id: str):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        service = _paper_batch_service()
        batch = service.store.get_batch(batch_id)
        if batch is None:
            raise PaperImportBatchServiceError("BATCH_NOT_FOUND", "导入批次不存在")
        _, candidates = _paper_server_snapshot(batch.search_id, [item.candidate_id for item in service.store.get_items(batch_id)])
        service.retry_batch(batch_id, candidates=candidates)
        return _paper_batch_status_payload(service, batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception:
        return _paper_api_error(503, "IMPORT_BATCH_UNAVAILABLE", "批量导入服务暂时不可用", True)


@router.post("/papers/import-batches/{batch_id}/cancel")
def cancel_paper_import_batch(batch_id: str):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        service = _paper_batch_service()
        current = service.store.get_batch(batch_id)
        if current is None:
            raise PaperImportBatchServiceError("BATCH_NOT_FOUND", "导入批次不存在")
        if current.status in {"running", "completed", "cancelled"}:
            raise PaperImportBatchServiceError("INVALID_STATE_TRANSITION", "批次当前状态不可取消")
        service.cancel_batch(batch_id)
        return _paper_batch_status_payload(service, batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception:
        return _paper_api_error(503, "IMPORT_BATCH_UNAVAILABLE", "批量导入服务暂时不可用", True)


def _paper_item_browser_target(service: PaperImportBatchService, item_id: str) -> tuple[object, list[object], str, str]:
    """Resolve an item's browser target exclusively from its server snapshot."""
    candidates = _paper_snapshot_for_item(service, item_id)
    item = service.store.get_item(item_id)
    if item is None:  # _paper_snapshot_for_item already checks this; keep the type guard explicit.
        raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
    candidate = next(
        (value for value in candidates if _paper_candidate_value(value, "candidate_id") == item.candidate_id),
        None,
    )
    article_url = str(
        _paper_candidate_value(candidate, "article_url")
        or _paper_candidate_value(candidate, "pdf_url")
        or ""
    )
    hostname = (urlsplit(article_url).hostname or "").casefold()
    site = "acm" if hostname == "dl.acm.org" else "ieee" if hostname == "ieeexplore.ieee.org" else ""
    if not site or not article_url:
        raise BrowserManagerError(
            "BROWSER_ORIGIN_NOT_ALLOWED", "候选论文不属于受控登录站点", retryable=False,
        )
    return item, candidates, site, article_url


@router.post("/papers/import-items/{item_id}/login", response_model=PaperImportItemLoginResponse)
def login_paper_import_item(item_id: str, _request: PaperImportItemActionRequest | None = None):
    """Open a headed login page using only the server-owned item snapshot."""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        service = _paper_batch_service()
        _item, _candidates, site, article_url = _paper_item_browser_target(service, item_id)
        previous = paper_browser_sessions.pop(item_id, None)
        if previous is not None:
            try:
                previous.close()
            except Exception:
                pass
        session = _paper_browser_manager().open_session(site, article_url)
        paper_browser_sessions[item_id] = session
        return {"status": "opened", "item_id": item_id, "site": site}
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except BrowserManagerError as error:
        code = error.code if error.code in _BROWSER_ERROR_STATUS else "BROWSER_UNAVAILABLE"
        return _paper_api_error(_BROWSER_ERROR_STATUS.get(code, 503), code, _safe_browser_error_message(error), error.retryable)
    except Exception:
        return _paper_api_error(503, "BROWSER_UNAVAILABLE", "浏览器当前不可用", True)


@router.post("/papers/import-items/{item_id}/resume", response_model=PaperImportBatchResponse)
def resume_paper_import_item(item_id: str, _request: PaperImportItemActionRequest | None = None):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        service = _paper_batch_service()
        item, candidates, site, article_url = _paper_item_browser_target(service, item_id)
        session_key = item_id
        session = paper_browser_sessions.get(item_id)
        if session is None:
            return _paper_api_error(424, "BROWSER_SESSION_REQUIRED", "请先完成受控登录后再续传", True)
        downloader = getattr(session, "download_pdf", None)
        context = getattr(session, "context", None)
        resumed = service.resume_item(
            item_id,
            candidates=candidates,
            downloader=downloader if callable(downloader) else None,
            context=context,
        )
        return _paper_batch_status_payload(service, resumed.batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except BrowserManagerError as error:
        code = error.code if error.code in _BROWSER_ERROR_STATUS else "BROWSER_UNAVAILABLE"
        return _paper_api_error(_BROWSER_ERROR_STATUS.get(code, 503), code, _safe_browser_error_message(error), error.retryable)
    except Exception:
        return _paper_api_error(503, "IMPORT_BATCH_UNAVAILABLE", "批量导入服务暂时不可用", True)
    finally:
        # Closing is scoped to the exact item, so another item's authenticated
        # browser page is untouched.
        session = locals().get("session")
        session_key = locals().get("session_key")
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
            if paper_browser_sessions.get(session_key) is session:
                paper_browser_sessions.pop(session_key, None)


@router.get("/papers/browser/health")
@router.get("/papers/browser-health")
def paper_browser_health():
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        health = _paper_browser_manager().health()
        return {key: health.get(key) for key in ("available", "version", "supported_sites", "reason")}
    except Exception:
        return _paper_api_error(503, "BROWSER_UNAVAILABLE", "浏览器当前不可用", True)


_BROWSER_ERROR_STATUS = {
    "BROWSER_ORIGIN_NOT_ALLOWED": 400,
    "BROWSER_PROFILE_LOCKED": 409,
    "BROWSER_PROFILE_UNSAFE": 503,
    "BROWSER_UNAVAILABLE": 503,
    "BROWSER_TIMEOUT": 424,
    "BROWSER_CRASHED": 424,
    "BROWSER_CANCELLED": 424,
}


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
