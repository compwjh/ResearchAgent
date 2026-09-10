import logging
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.app.api import common
from backend.app.api.schemas import (
    ConferenceUpdateRequest,
    PaperAcceptedRequest,
    PaperImportBatchRequest,
    PaperImportBatchResponse,
    PaperImportItemActionRequest,
    PaperImportItemLoginResponse,
    PaperImportRequest,
    PaperImportResponse,
    AsyncPaperSearchRequest,
)
from backend.app.paper_discovery.application.entry import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    BrowserManagerError,
    PaperDownloadError,
)
from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
from backend.app.paper_discovery.application.paper_import import (
    DUPLICATE_IMPORT,
    KB_IMPORT_FAILED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    import_candidate,
    safe_import_error_code,
    safe_import_error_message,
)
from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.paper_discovery.domain.paper_discovery import SearchJob, SearchSession, SearchSourceProgress

router = APIRouter()

logger = logging.getLogger(__name__)

from backend.app.api.common import *  # noqa: F401,F403


def _async_progress_payload(progress) -> dict:
    return {
        "source_kind": progress.source_kind, "status": progress.status,
        "cached_units": progress.cached_units, "fetching_units": progress.fetching_units,
        "completed_units": progress.completed_units, "paper_count": progress.paper_count,
        "error_code": progress.error_code, "message_code": progress.message_code,
    }


def _async_job_payload(store, job: SearchJob, *, event_cursor: int | None = None) -> dict:
    progress = {item.source_kind: _async_progress_payload(item) for item in store.get_source_progress(job.search_id)}
    for source in ("usenix", "dblp"):
        progress.setdefault(source, {
            "source_kind": source, "status": "queued", "cached_units": [], "fetching_units": [],
            "completed_units": [], "paper_count": 0, "error_code": None, "message_code": "SOURCE_QUEUED",
        })
    events = store.get_search_events(job.search_id, event_cursor)
    return {
        "search_id": job.search_id, "status": job.status, "degraded": bool(job.degraded),
        "total_results": job.total_results, "source_progress": [progress["usenix"], progress["dblp"]],
        "next_event_cursor": events[-1].event_id if events else event_cursor,
        "events": [{"event_id": event.event_id, "node_name": event.node_name,
                    "source_kind": event.source_kind, "event_type": event.event_type,
                    "status": event.status, "safe_payload": event.safe_payload,
                    "created_at": event.created_at} for event in events],
    }


def _async_expired(job: SearchJob) -> bool:
    if not job.expires_at:
        return False
    try:
        return datetime.fromisoformat(job.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return False


@router.post("/papers/searches", status_code=202)
def create_async_paper_search(request: AsyncPaperSearchRequest):
    """Create a persisted search and schedule graph execution without waiting on sources."""
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    years = list(dict.fromkeys(request.years))
    if request.conference_ids != ["usenix-security"]:
        return _paper_api_error(400, "UNSUPPORTED_CONFERENCE", "异步目录检索当前仅支持 USENIX Security")
    current_year = datetime.now(timezone.utc).year
    if years != sorted(years) or any(year < 1900 or year > current_year for year in years):
        return _paper_api_error(
            400, "INVALID_YEARS", "years 必须为升序且在受控范围内",
            details={"min_year": 1900, "max_year": current_year},
        )
    now = datetime.now(timezone.utc)
    ttl = getattr(common.article_settings, "paper_discovery_search_ttl_seconds", 86400)
    search_id = uuid.uuid4().hex
    job = SearchJob(search_id, request.query.strip(), request.conference_ids, years, "queued", "catalog-search-v1",
                    False, None, 0, now.isoformat(timespec="seconds").replace("+00:00", "Z"), None, None,
                    (now + timedelta(seconds=ttl)).isoformat(timespec="seconds").replace("+00:00", "Z"), now.isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        store = _paper_store()
        store.create_search_job(job)
        for source in ("usenix", "dblp"):
            store.save_source_progress(SearchSourceProgress(
                search_id, source, "queued", message_code="SOURCE_QUEUED", updated_at=job.created_at,
            ))
        submit_paper_catalog_search(search_id)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_UNAVAILABLE", "论文检索任务暂时无法启动", True)
    return _async_job_payload(store, job)


@router.get("/papers/searches/{search_id}")
def get_async_paper_search(search_id: str, event_cursor: int | None = Query(default=None, ge=0)):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    store = _paper_store()
    job = store.get_search_job(search_id)
    if job is None:
        return _paper_api_error(404, "SEARCH_NOT_FOUND", "搜索任务不存在")
    if _async_expired(job):
        return _paper_api_error(410, "SEARCH_EXPIRED", "搜索任务已过期")
    return _async_job_payload(store, job, event_cursor=event_cursor)


@router.get("/papers/searches/{search_id}/results")
def get_async_paper_results(search_id: str, page: int = Query(default=1)):
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    if page < 1:
        return _paper_api_error(400, "INVALID_PAGE", "page 必须从 1 开始")
    store = _paper_store()
    job = store.get_search_job(search_id)
    if job is None:
        return _paper_api_error(404, "SEARCH_NOT_FOUND", "搜索任务不存在")
    if _async_expired(job):
        return _paper_api_error(410, "SEARCH_EXPIRED", "搜索任务已过期")
    if job.status not in {"completed", "partial", "failed"}:
        return _paper_api_error(409, "SEARCH_NOT_READY", "搜索结果尚未冻结")
    total = len(store.get_search_results(search_id))
    if job.status == "failed" and total == 0:
        return _paper_api_error(409, "SEARCH_NO_RESULTS", "搜索没有可读结果")
    page_size = 10
    total_pages = (total + page_size - 1) // page_size
    rows = store.get_search_results_page(search_id, page, page_size)
    return {
        "search_id": search_id, "status": job.status, "page": page, "page_size": page_size,
        "total": total, "total_pages": total_pages, "has_next": page < total_pages,
        "items": [row.snapshot for row in rows],
    }


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


@router.get("/papers/conferences/{conference_id}/accepted")
def list_accepted_papers(
    conference_id: str,
    request: Annotated[PaperAcceptedRequest, Query()],
):
    """从全局 accepted catalog 读取兼容结果并保存候选快照。

    Task15 的主链负责刷新 USENIX accepted catalog；这个历史兼容入口只读
    已持久化的目录，不能在请求线程再次触发 accepted source 网络抓取。
    """
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        store = _paper_store()
        source = next((item for item in store.list_conferences() if item.conference_id == conference_id), None)
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
    current_year = datetime.now(timezone.utc).year
    try:
        service = _paper_search_service()
    except Exception:
        service = None
    default_years = getattr(service, "default_years", common.article_settings.paper_discovery_default_years)
    if request.year is not None and request.year > current_year:
        return _paper_api_error(422, "INVALID_ACCEPTED_YEAR", "year 必须为 1900 到当前年份的整数")
    years = [request.year] if request.year is not None else list(range(current_year - default_years, current_year))
    limit = request.limit or getattr(service, "default_limit", common.article_settings.paper_discovery_search_limit)
    query = request.q or ""
    try:
        list_catalog_papers = getattr(store, "list_catalog_papers", None)
        if not callable(list_catalog_papers):
            return _paper_api_error(424, "CATALOG_NOT_READY", "accepted 论文目录尚未准备好，请稍后重试", True)
        try:
            papers = list(list_catalog_papers([source.conference_id], years, index_status=None))
        except TypeError:
            # Narrow fake stores and older adapters may only expose positional
            # filters; production uses the explicit administrative read above.
            papers = list(list_catalog_papers([source.conference_id], years))
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)

    accepted_papers = []
    source_kinds = getattr(store, "get_catalog_source_kinds", None)
    for paper in papers:
        if getattr(paper, "publication_stage", None) != "accepted":
            continue
        if callable(source_kinds):
            try:
                kinds = set(source_kinds(paper.catalog_paper_id) or ())
            except Exception:
                kinds = set()
            if kinds and not kinds.intersection({"usenix", "usenix_accepted"}):
                continue
        accepted_papers.append(paper)
    if not accepted_papers:
        return _paper_api_error(424, "CATALOG_NOT_READY", "accepted 论文目录尚未准备好，请稍后重试", True)

    query_key = query.casefold().strip()
    if query_key:
        accepted_papers = [
            paper for paper in accepted_papers
            if query_key in " ".join(str(value or "") for value in (
                getattr(paper, "title", ""), getattr(paper, "abstract", ""),
                " ".join(getattr(paper, "authors", []) or []), getattr(paper, "doi", ""),
            )).casefold()
        ]
    accepted_papers.sort(key=lambda paper: (
        -(int(paper.year) if getattr(paper, "year", None) is not None else -1),
        getattr(paper, "normalized_title", "") or str(getattr(paper, "title", "")).casefold(),
        str(getattr(paper, "catalog_paper_id", "")),
    ))
    candidate_records = []
    for paper in accepted_papers:
        candidate_records.append({"info": {
            "title": paper.title, "year": paper.year, "authors": list(paper.authors or []),
            "abstract": paper.abstract, "doi": paper.doi, "key": paper.dblp_key,
            "url": paper.official_page_url, "ee": paper.official_pdf_url,
            "pdf_url": paper.official_pdf_url, "publication_stage": "accepted",
            "source_kind": "usenix_accepted", "source_page_url": paper.official_page_url,
            "source_links": [
                {"kind": "accepted_page", "url": paper.official_page_url},
                {"kind": "pdf", "url": paper.official_pdf_url},
            ],
        }})

    search_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    ttl = getattr(service, "search_ttl_seconds", getattr(common.article_settings, "paper_discovery_search_ttl_seconds", 86400))
    session = SearchSession(
        search_id=search_id,
        query=query,
        expires_at=(now + timedelta(seconds=ttl)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        created_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    candidates = []
    candidate_from_record = getattr(service, "_candidate_from_record", PaperDiscoverySearchService._candidate_from_record)
    for initial_rank, record in enumerate(candidate_records):
        candidate = candidate_from_record(record, source, search_id, query)
        if candidate is None:
            continue
        candidate.initial_rank = initial_rank
        candidates.append(candidate)
    candidates = candidates[:limit]
    for rank, candidate in enumerate(candidates, 1):
        candidate.rank = rank
    try:
        store.save_search(session, candidates)
    except Exception:
        return _paper_api_error(503, "PAPER_DISCOVERY_STORE_UNAVAILABLE", "论文检索配置暂时不可用", True)
    return {
        "search_id": session.search_id,
        "query": session.query,
        "expires_at": session.expires_at,
        "candidates": [_candidate_payload(candidate) for candidate in candidates[:limit]],
        "warnings": [],
        "degraded": False,
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
            # catalog async-search 的检索上下文只落在 search_jobs 表，search_sessions
            # 对其恒为空；与批量路径 _paper_server_snapshot 保持一致，回退到 job 解析，
            # 避免把"未就绪/已过期/可解析"的合法 search_id 误报为 SEARCH_NOT_FOUND。
            try:
                job, by_id = _paper_catalog_import_inputs(store, request.search_id, [request.candidate_id])
            except PaperImportBatchServiceError as error:
                return _paper_batch_error_response(error)
            if _paper_search_expired(getattr(job, "expires_at", "")):
                return _paper_batch_error_response(
                    PaperImportBatchServiceError("SEARCH_EXPIRED", "搜索会话已过期")
                )
            candidate = by_id.get(request.candidate_id)
            if candidate is None:
                return _paper_batch_error_response(
                    PaperImportBatchServiceError("CANDIDATE_NOT_FOUND", "候选论文不存在")
                )
            session = job
        else:
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
            common.article_settings,
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
    "SEARCH_NOT_READY": 400,
    "INVALID_SEARCH_SNAPSHOT": 400,
    "INVALID_STATE_TRANSITION": 400,
    "INVALID_SEARCH_ID": 400,
    "INVALID_CANDIDATE_ID": 400,
    "EMPTY_BATCH": 400,
    "BATCH_LIMIT_EXCEEDED": 400,
    "DATABASE_LOCKED": 503,
    DUPLICATE_IMPORT: 409,
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
        "SEARCH_NOT_READY": "搜索结果尚未冻结",
        "INVALID_SEARCH_SNAPSHOT": "搜索候选快照无效",
        "INVALID_STATE_TRANSITION": "当前状态不允许此操作",
        "INVALID_SEARCH_ID": "搜索会话编号无效",
        "INVALID_CANDIDATE_ID": "候选编号无效",
        "EMPTY_BATCH": "批量导入至少需要一项",
        "BATCH_LIMIT_EXCEEDED": "单批最多 20 项",
        "DATABASE_LOCKED": "批次状态库正忙，请稍后重试",
        DUPLICATE_IMPORT: "该论文已在导入批次中，请在原批次重试",
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


def _paper_catalog_import_inputs(store, search_id, candidate_ids):
    """Resolve async catalog-search candidates for import.

    Returns ``(job, by_id)`` where ``job`` is the SearchJob (carries expires_at
    for the expiry check) and ``by_id`` maps candidate_id -> snapshot dict with
    ``candidate_id`` injected (= catalog_paper_id). Raises
    PaperImportBatchServiceError for not-found / not-ready.
    """
    job = store.get_search_job(search_id)
    if job is None:
        raise PaperImportBatchServiceError("SEARCH_NOT_FOUND", "搜索会话不存在")
    if getattr(job, "status", "") not in {"completed", "partial", "failed"}:
        raise PaperImportBatchServiceError("SEARCH_NOT_READY", "搜索结果尚未冻结")
    results = store.get_search_results(search_id)
    by_id: dict[str, object] = {}
    for result in results:
        snapshot = dict(result.snapshot)
        cid = snapshot.get("catalog_paper_id") or getattr(result, "catalog_paper_id", None)
        snapshot.setdefault("candidate_id", cid)
        snapshot.setdefault("search_id", search_id)
        by_id[cid] = snapshot
    return job, by_id


def _paper_server_snapshot(search_id: str, candidate_ids: list[str]) -> tuple[object, list[object]]:
    """Resolve all import inputs from the server-owned search snapshot."""
    store = _paper_store()
    session = store.get_search_session(search_id)
    if session is None:
        job, by_id = _paper_catalog_import_inputs(store, search_id, candidate_ids)
        if _paper_search_expired(getattr(job, "expires_at", "")):
            raise PaperImportBatchServiceError("SEARCH_EXPIRED", "搜索会话已过期")
        candidates = [by_id[cid] for cid in candidate_ids if cid in by_id]
        if not candidates:
            raise PaperImportBatchServiceError("CANDIDATE_NOT_FOUND", "候选论文不存在")
        return job, candidates
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
        job = discovery.get_search_job(batch.search_id)
        if job is None:
            raise PaperImportBatchServiceError("SEARCH_NOT_FOUND", "搜索会话不存在")
        if _paper_search_expired(getattr(job, "expires_at", "")):
            raise PaperImportBatchServiceError("SEARCH_EXPIRED", "搜索会话已过期")
        session = job
        candidates = []
        for result in discovery.get_search_results(batch.search_id):
            snapshot = dict(result.snapshot)
            cid = snapshot.get("catalog_paper_id") or getattr(result, "catalog_paper_id", None)
            snapshot.setdefault("candidate_id", cid)
            snapshot.setdefault("search_id", batch.search_id)
            candidates.append(snapshot)
    else:
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
    except Exception as error:
        logger.exception("批量导入未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )


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
        service = _paper_batch_service()
        # First-access recovery (spec-021): reuse the existing lease-recovery
        # mechanism and re-submit any queued batch whose runner is missing, so a
        # crashed runner / restart cannot leave it permanently in queued.
        try:
            service.recover_expired_leases()
            service.maybe_recover_batch(batch_id)
        except Exception:  # noqa: BLE001 - recovery must not block the status read
            logger.exception("导入批次恢复失败：%s", batch_id)
        return _paper_batch_status_payload(service, batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception as error:
        logger.exception("批量导入未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )


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
    except Exception as error:
        logger.exception("批量导入未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )


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
    except Exception as error:
        logger.exception("批量导入未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )


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
    except Exception as error:
        logger.exception("批量导入未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )
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


@router.post("/papers/import-items/{item_id}/retry", response_model=PaperImportBatchResponse)
def retry_paper_import_item(item_id: str, _request: PaperImportItemActionRequest | None = None):
    """重试单个失败条目：仅把该条目回到 queued 并后台提交，立即返回批次负载。

    复用 service.retry_item（store.retry_item 仅允许 failed → queued）；非 failed 条目
    由 store 抛 INVALID_STATE_TRANSITION，缺失条目抛 ITEM_NOT_FOUND，均回落到稳定错误响应。
    """
    if not _paper_discovery_enabled():
        return _paper_api_error(503, "PAPER_DISCOVERY_DISABLED", "论文检索功能当前已关闭")
    try:
        service = _paper_batch_service()
        # 复用既有的条目/批次/服务端快照解析（与 login/resume 同构），并校验条目存在。
        candidates = _paper_snapshot_for_item(service, item_id)
        item = service.store.get_item(item_id)
        service.retry_item(item.item_id, candidates=candidates)
        return _paper_batch_status_payload(service, item.batch_id)
    except PaperImportBatchServiceError as error:
        return _paper_batch_error_response(error)
    except Exception as error:
        logger.exception("单条目重试未预期异常：%s", type(error).__name__)
        return _paper_batch_error_response(
            PaperImportBatchServiceError("IMPORT_BATCH_ERROR", "批量导入失败")
        )


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
