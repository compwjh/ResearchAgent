import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import List
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.app.core.config import BASE_DIR
from backend.app.domain.article import ArticleCandidate
from backend.app.paper_discovery.application.entry import (
    DBLPPublicationSource,
    OpenAlexEnricher,
    PaperBrowserManager,
    PaperDiscoveryStore,
    PaperImportBatchStore,
)
from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
from backend.app.paper_discovery.application.paper_import import (
    import_candidate,
)
from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchService,
)
from backend.app.platform.bootstrap import get_provider, register_provider
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)
from backend.app.services.task_store import TaskStore


def article_tasks() -> TaskStore:
    """返回文章任务仓储；经 composition root 解析，测试可用 override_provider 替换。"""
    return get_provider("article_tasks")


register_provider("article_tasks", TaskStore)

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


def _build_paper_store() -> PaperDiscoveryStore:
    global paper_discovery_store, paper_discovery_store_path
    from backend.app.api import routes
    article_settings = routes.article_settings
    configured_path = Path(article_settings.paper_discovery_db_path)
    if not configured_path.is_absolute():
        configured_path = BASE_DIR / configured_path
    if paper_discovery_store is None or paper_discovery_store_path != configured_path:
        paper_discovery_store = PaperDiscoveryStore(database_path=configured_path)
        paper_discovery_store_path = configured_path
    return paper_discovery_store


def _build_paper_search_service() -> PaperDiscoverySearchService:
    global paper_discovery_search_service
    from backend.app.api import routes
    article_settings = routes.article_settings
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
    from backend.app.api import routes
    article_settings = routes.article_settings
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


def _build_paper_batch_service() -> PaperImportBatchService:
    """Build the batch orchestrator lazily so routes remain test-injectable."""
    global paper_import_batch_service, paper_import_batch_store_path
    from backend.app.api import routes
    article_settings = routes.article_settings
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


def _build_paper_browser_manager() -> PaperBrowserManager:
    global paper_browser_manager
    from backend.app.api import routes
    article_settings = routes.article_settings
    if paper_browser_manager is None:
        paper_browser_manager = PaperBrowserManager(settings=article_settings)
    return paper_browser_manager


def _paper_store() -> PaperDiscoveryStore:
    return get_provider("paper_discovery_store")


def _paper_search_service() -> PaperDiscoverySearchService:
    return get_provider("paper_search_service")


def _paper_batch_service() -> PaperImportBatchService:
    return get_provider("paper_batch_service")


def _paper_browser_manager() -> PaperBrowserManager:
    return get_provider("paper_browser_manager")


register_provider("paper_discovery_store", _build_paper_store, singleton=False)
register_provider("paper_search_service", _build_paper_search_service, singleton=False)
register_provider("paper_batch_service", _build_paper_batch_service, singleton=False)
register_provider("paper_browser_manager", _build_paper_browser_manager, singleton=False)


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


__all__ = [
    # module-level shared state
    "article_tasks",
    "article_settings",
    "paper_discovery_store",
    "paper_discovery_store_path",
    "paper_discovery_search_service",
    "paper_import_batch_service",
    "paper_import_batch_store_path",
    "paper_browser_manager",
    "paper_browser_sessions",
    # helpers
    "_paper_discovery_enabled",
    "_paper_api_error",
    "_paper_store",
    "_paper_search_service",
    "_paper_candidate_value",
    "_paper_candidate_hosts",
    "_paper_batch_service",
    "_paper_browser_manager",
    "_conference_payload",
    "_candidate_payload",
    "_validation_error_code",
    "_accepted_validation_error_code",
    "paper_request_validation_error_response",
    "stream_event",
    "top_recommendations",
    # constants
    "RECOMMEND_MIN_CONFIDENCE",
    "RECOMMEND_MAX_COUNT",
    "CONFERENCE_SEARCH_QUERY_MAX_LENGTH",
]
