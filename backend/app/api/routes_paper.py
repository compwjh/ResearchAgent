import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.app.api import routes
from backend.app.api.schemas import (
    ConferenceUpdateRequest,
    PaperAcceptedRequest,
    PaperImportBatchRequest,
    PaperImportBatchResponse,
    PaperImportItemActionRequest,
    PaperImportItemLoginResponse,
    PaperImportRequest,
    PaperImportResponse,
    PaperSearchRequest,
)
from backend.app.domain.paper_discovery import SearchSession
from backend.app.services.paper_browser_manager import BrowserManagerError
from backend.app.services.paper_discovery_search import PaperDiscoverySearchError
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

router = APIRouter()

from backend.app.api.common import *  # noqa: F401,F403


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
    default_years = getattr(service, "default_years", routes.article_settings.paper_discovery_default_years)
    if request.year is not None and request.year > current_year:
        return _paper_api_error(422, "INVALID_ACCEPTED_YEAR", "year 必须为 1900 到当前年份的整数")
    years = [request.year] if request.year is not None else list(range(current_year - default_years, current_year))
    limit = request.limit or getattr(service, "default_limit", routes.article_settings.paper_discovery_search_limit)
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
            routes.article_settings,
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



