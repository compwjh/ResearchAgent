"""Owner-scoped literature-map MVP HTTP routes."""

from __future__ import annotations

import math
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from backend.app.literature_maps.application.analysis import MapAnalysisError
from backend.app.literature_maps.application.runtime import get_literature_map_service
from backend.app.literature_maps.domain.models import SCHEMA_VERSION
from backend.app.literature_maps.infrastructure.store import LiteratureMapStoreError
from backend.app.memory.repository import OWNER_ID

router = APIRouter(prefix="/literature-maps")


class MapCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str = Field(min_length=1, max_length=500)
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=100)
    year_start: StrictInt | None = Field(default=None, ge=1900, le=2100)
    year_end: StrictInt | None = Field(default=None, ge=1900, le=2100)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    conference_ids: list[str] = Field(default_factory=list, max_length=50)
    limit: StrictInt = Field(default=30)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class MapPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=100)


class PositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=100)
    x: float
    y: float


class ViewportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    scale: float


class MapViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)
    positions: list[PositionRequest] = Field(default_factory=list, max_length=200)
    viewport: ViewportRequest | None = None
    filters: dict[str, Any] | None = None
    layers: dict[Literal["citation", "similarity"], bool] | None = None


class ImportRequest(BaseModel):
    """Empty action body; source URLs are always resolved from the node."""

    model_config = ConfigDict(extra="forbid")


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["topic", "references", "citations", "refresh"]
    node_id: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class PreviewApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class NodeMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class GroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: StrictInt = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class GroupPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: StrictInt = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class GroupDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)


class NodeGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: StrictInt = Field(ge=0)
    group_id: str | None = Field(default=None, min_length=1, max_length=100)


class MapAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_level: Literal["abstract", "full"]
    model: str | None = Field(default=None, min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class MapConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_level: Literal["abstract", "full"]
    idempotency_key: str = Field(min_length=1, max_length=200)


def _error(error: Exception) -> HTTPException:
    code = str(error)
    if isinstance(error, MapAnalysisError):
        return HTTPException(status_code=error.status, detail={"code": error.code, "message": error.message, "retryable": error.retryable})
    if code in {"MAP_ABSTRACT_UNAVAILABLE", "MAP_FULLTEXT_UNAVAILABLE", "MAP_EVIDENCE_UNAVAILABLE", "MAP_ANALYSIS_SOURCE_CHANGED", "MAP_NODE_REMOVED", "MAP_CONVERSATION_PROJECT_MISMATCH"}:
        return HTTPException(status_code=409, detail={"code": code, "message": "当前论文依据或会话状态已变化，请重新读取后重试", "retryable": False})
    if isinstance(error, LookupError) or code in {"PROJECT_NOT_FOUND", "IMPORT_BRIDGE_UNAVAILABLE"}:
        status = 404 if code != "IMPORT_BRIDGE_UNAVAILABLE" else 503
        error_code = "MAP_NOT_FOUND" if isinstance(error, LookupError) else code
        message = "地图或节点不存在" if isinstance(error, LookupError) else "文献导入流程暂不可用"
    elif isinstance(error, (LiteratureMapStoreError, sqlite3.Error)) or code in {
        "MAP_STORAGE_UNAVAILABLE", "MAP_IMPORT_STATE_UNAVAILABLE",
    }:
        status, error_code, message = 503, "MAP_STORAGE_UNAVAILABLE", "文献地图暂时不可用，请稍后重试"
    elif code == "MAP_NO_RETRYABLE_UNITS":
        status, error_code, message = 409, code, "当前作业没有可重试的失败单元"
    elif code in {"revision conflict", "idempotency conflict", "job is not retryable", "map stopped", "MAP_JOB_INVALID_INPUT", "MAP_IDEMPOTENCY_STATE_INVALID"} or code.startswith("MAP_CONFLICT"):
        status, error_code, message = 409, "MAP_CONFLICT", "地图版本或作业状态已变化，请重新读取后重试"
        if code == "idempotency conflict":
            error_code, message = "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同参数"
    elif code == "IMPORT_URL_UNSAFE":
        status, error_code, message = 400, code, "导入链接必须是安全的 http/https 地址"
    elif code == "INVALID_MAP_SCOPE":
        status, error_code, message = 400, code, "地图来源或会议范围不受支持，请选择服务端支持的范围"
    elif code in {"UNSUPPORTED_SOURCE", "UNSUPPORTED_CONFERENCE"}:
        status, error_code = 400, code
        message = {
            "UNSUPPORTED_SOURCE": "source_id 不是服务端支持的来源",
            "UNSUPPORTED_CONFERENCE": "conference_id 不是服务端支持的会议",
        }[code]
    elif code in {"TOPIC_REQUIRED", "INVALID_LIMIT", "INVALID_YEARS", "invalid viewport", "invalid position", "invalid node", "INVALID_PREVIEW_KIND", "PREVIEW_NODE_REQUIRED", "PREVIEW_NOT_READY", "INVALID_PREVIEW_CANDIDATE", "PREVIEW_BATCH_LIMIT", "MAP_NODE_LIMIT", "NODE_NOT_REMOVED", "NODE_ALREADY_REMOVED", "INVALID_GROUP_NAME", "INVALID_GROUP_COLOR", "INVALID_GROUP_ID", "GROUP_LIMIT", "MAP_NODE_REMOVED"}:
        status, error_code, message = 400, code, "地图创建参数不合法"
    elif code == "PROJECT_NOT_FOUND":
        status, error_code, message = 404, code, "项目不存在或不可访问"
    else:
        status, error_code, message = 503, "MAP_STORAGE_UNAVAILABLE", "文献地图暂时不可用，请稍后重试"
    return HTTPException(status_code=status, detail={"code": error_code, "message": message, "retryable": status >= 500})


def _envelope(**values: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **values}


@router.post("", status_code=202)
def create_literature_map(payload: MapCreateRequest):
    try:
        service = get_literature_map_service()
        result = service.create_map(owner_id=OWNER_ID, topic=payload.topic, name=payload.name, project_id=payload.project_id, year_start=payload.year_start, year_end=payload.year_end, source_ids=payload.source_ids, conference_ids=payload.conference_ids, requested_count=payload.limit, idempotency_key=payload.idempotency_key)
    except Exception as error:
        raise _error(error) from error
    return _envelope(map_id=result.map.map_id, job_id=result.job.job_id, status=result.map.status, map=result.map.to_dict(), job=result.job.to_dict())


@router.get("")
def list_literature_maps(limit: int = Query(100, ge=1, le=100)):
    try:
        maps = get_literature_map_service().store.list_maps(OWNER_ID, limit=limit)
    except Exception as error:
        raise _error(error) from error
    return _envelope(maps=[item.to_dict() for item in maps])


@router.get("/{map_id}")
def get_literature_map(map_id: str):
    try:
        service = get_literature_map_service()
        item = service.store.get_map(map_id, OWNER_ID)
        latest_job = service.store.latest_job(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    if item is None:
        raise _error(LookupError("map not found"))
    return _envelope(map=item.to_dict(), latest_job=latest_job.to_dict() if latest_job else None)


@router.patch("/{map_id}")
def patch_literature_map(map_id: str, payload: MapPatchRequest):
    try:
        service = get_literature_map_service()
        kwargs = {"expected_revision": payload.expected_revision, "name": payload.name}
        if "project_id" in payload.model_fields_set:
            kwargs["project_id"] = payload.project_id
        item = service.update_map(map_id, OWNER_ID, **kwargs)
    except Exception as error:
        raise _error(error) from error
    return _envelope(map=item.to_dict())


@router.delete("/{map_id}", status_code=204)
def delete_literature_map(map_id: str):
    try:
        deleted = get_literature_map_service().store.delete_map(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    if not deleted:
        raise _error(LookupError("map not found"))


@router.get("/{map_id}/graph")
def get_literature_map_graph(map_id: str):
    try:
        return get_literature_map_service().graph(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error


@router.get("/{map_id}/groups")
def get_literature_map_groups(map_id: str):
    try:
        return get_literature_map_service().groups(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error


@router.post("/{map_id}/groups")
def create_literature_map_group(map_id: str, payload: GroupCreateRequest):
    try:
        return get_literature_map_service().create_group(
            map_id,
            OWNER_ID,
            expected_revision=payload.expected_revision,
            name=payload.name,
            color=payload.color,
        )
    except Exception as error:
        raise _error(error) from error


@router.patch("/{map_id}/groups/{group_id}")
def patch_literature_map_group(map_id: str, group_id: str, payload: GroupPatchRequest):
    try:
        return get_literature_map_service().update_group(
            map_id,
            group_id,
            OWNER_ID,
            expected_revision=payload.expected_revision,
            name=payload.name,
            color=payload.color,
        )
    except Exception as error:
        raise _error(error) from error


@router.delete("/{map_id}/groups/{group_id}")
def delete_literature_map_group(map_id: str, group_id: str, payload: GroupDeleteRequest):
    try:
        return get_literature_map_service().delete_group(
            map_id,
            group_id,
            OWNER_ID,
            expected_revision=payload.expected_revision,
        )
    except Exception as error:
        raise _error(error) from error


@router.put("/{map_id}/nodes/{node_id}/group")
def put_literature_map_node_group(map_id: str, node_id: str, payload: NodeGroupRequest):
    try:
        return get_literature_map_service().assign_node_group(
            map_id,
            node_id,
            OWNER_ID,
            expected_revision=payload.expected_revision,
            group_id=payload.group_id,
        )
    except Exception as error:
        raise _error(error) from error


@router.get("/{map_id}/export")
def export_literature_map(map_id: str):
    try:
        payload = get_literature_map_service().export_map(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    response = JSONResponse(content=payload, media_type="application/json")
    # Keep the filename constant so map names or path-like identifiers cannot
    # influence a response header.  The map_id remains in the JSON payload.
    response.headers["Content-Disposition"] = 'attachment; filename="literature-map.json"'
    return response


@router.get("/{map_id}/nodes/{node_id}")
def get_literature_map_node(map_id: str, node_id: str):
    try:
        return _envelope(node=get_literature_map_service().node(map_id, node_id, OWNER_ID).to_dict())
    except Exception as error:
        raise _error(error) from error


def _analysis_service():
    service = get_literature_map_service()
    analysis = getattr(service, "analysis_service", None)
    if analysis is None:
        raise MapAnalysisError("MAP_ANALYSIS_UNAVAILABLE", "地图分析暂不可用", retryable=True, status=503)
    return analysis


@router.get("/{map_id}/nodes/{node_id}/analyses")
def list_literature_map_analyses(map_id: str, node_id: str):
    try:
        analysis = _analysis_service()
        source_status = analysis.source_status(map_id, node_id, OWNER_ID)
        items = analysis.store.list_analyses(map_id, node_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(analyses=[item.to_dict() for item in items], source_status=source_status)


@router.post("/{map_id}/nodes/{node_id}/analyses", status_code=202)
def create_literature_map_analysis(map_id: str, node_id: str, payload: MapAnalysisRequest):
    try:
        if payload.model:
            # Keep model existence/capability validation on the existing
            # conversation boundary; the map endpoint only carries the
            # validated selection into its durable job.
            from backend.app.api.routes_conversations import _validate_model

            _validate_model(payload.model)
        analysis, job, _created = _analysis_service().request_analysis(
            map_id,
            node_id,
            OWNER_ID,
            evidence_level=payload.evidence_level,
            model=payload.model,
            idempotency_key=payload.idempotency_key,
        )
    except Exception as error:
        raise _error(error) from error
    return _envelope(map_id=map_id, node_id=node_id, analysis_id=analysis.analysis_id, job_id=job.job_id, status=job.status, analysis=analysis.to_dict(), job=job.to_dict())


@router.get("/{map_id}/analyses/{analysis_id}")
def get_literature_map_analysis(map_id: str, analysis_id: str):
    try:
        analysis_service = _analysis_service()
        analysis = analysis_service.store.get_analysis(analysis_id, map_id, OWNER_ID)
        if analysis is None:
            raise LookupError("analysis not found")
        job = analysis_service.store.get_analysis_job(analysis_id, map_id, OWNER_ID)
        if job is None:
            raise LookupError("analysis job not found")
    except Exception as error:
        raise _error(error) from error
    return _envelope(analysis=analysis.to_dict(), job=job.to_dict())


@router.post("/{map_id}/nodes/{node_id}/conversation")
def create_literature_map_conversation(map_id: str, node_id: str, payload: MapConversationRequest):
    try:
        result = _analysis_service().create_conversation(
            map_id,
            node_id,
            OWNER_ID,
            evidence_level=payload.evidence_level,
            idempotency_key=payload.idempotency_key,
        )
    except Exception as error:
        raise _error(error) from error
    return _envelope(**result)


# Keep the plural spelling as a harmless compatibility alias while the
# frozen contract uses the singular resource name.
@router.post("/{map_id}/nodes/{node_id}/conversations")
def create_literature_map_conversation_plural(map_id: str, node_id: str, payload: MapConversationRequest):
    return create_literature_map_conversation(map_id, node_id, payload)


@router.post("/{map_id}/previews", status_code=202)
def create_literature_map_preview(map_id: str, payload: PreviewRequest):
    try:
        preview = get_literature_map_service().create_preview(
            map_id,
            OWNER_ID,
            kind=payload.kind,
            node_id=payload.node_id,
            query=payload.query,
            idempotency_key=payload.idempotency_key,
        )
        _, job = get_literature_map_service().get_preview(map_id, preview.preview_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(preview_id=preview.preview_id, map_id=map_id, job_id=preview.job_id, status=preview.status, base_revision=preview.base_revision, preview=preview.to_dict(), job=job.to_dict())


@router.get("/{map_id}/previews/{preview_id}")
def get_literature_map_preview(map_id: str, preview_id: str):
    try:
        preview, job = get_literature_map_service().get_preview(map_id, preview_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(preview=preview.to_dict(), job=job.to_dict())


@router.post("/{map_id}/previews/{preview_id}/apply", status_code=202)
def apply_literature_map_preview(map_id: str, preview_id: str, payload: PreviewApplyRequest):
    try:
        result = get_literature_map_service().apply_preview(
            map_id,
            preview_id,
            OWNER_ID,
            expected_revision=payload.expected_revision,
            selected_candidate_ids=payload.selected_candidate_ids,
            idempotency_key=payload.idempotency_key,
        )
    except Exception as error:
        raise _error(error) from error
    return _envelope(**result)


@router.post("/{map_id}/nodes/{node_id}/remove")
def remove_literature_map_node(map_id: str, node_id: str, payload: NodeMutationRequest):
    try:
        result = get_literature_map_service().remove_node(map_id, node_id, OWNER_ID, expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key)
    except Exception as error:
        raise _error(error) from error
    return _envelope(**result)


@router.post("/{map_id}/nodes/{node_id}/restore", status_code=202)
def restore_literature_map_node(map_id: str, node_id: str, payload: NodeMutationRequest):
    try:
        result = get_literature_map_service().restore_node(map_id, node_id, OWNER_ID, expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key)
    except Exception as error:
        raise _error(error) from error
    return _envelope(**result)


@router.patch("/{map_id}/view")
def patch_literature_map_view(map_id: str, payload: MapViewRequest):
    if payload.viewport is not None and (not all(math.isfinite(value) for value in (payload.viewport.x, payload.viewport.y, payload.viewport.scale)) or payload.viewport.scale <= 0):
        raise _error(ValueError("invalid viewport"))
    if any(not all(math.isfinite(value) for value in (position.x, position.y)) for position in payload.positions):
        raise _error(ValueError("invalid position"))
    try:
        service = get_literature_map_service()
        item = service.store.update_view(map_id, OWNER_ID, expected_revision=payload.expected_revision, positions=[position.model_dump() for position in payload.positions], viewport=payload.viewport.model_dump() if payload.viewport else None, filters=payload.filters, layers=payload.layers)
    except Exception as error:
        raise _error(error) from error
    return _envelope(map=item.to_dict())


@router.get("/{map_id}/jobs/{job_id}")
def get_literature_map_job(map_id: str, job_id: str):
    try:
        item = get_literature_map_service().store.get_job(job_id, map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    if item is None:
        raise _error(LookupError("job not found"))
    return _envelope(job=item.to_dict())


@router.get("/{map_id}/events")
def list_literature_map_events(map_id: str, after_seq: int = Query(0, ge=0)):
    try:
        service = get_literature_map_service()
        events, cursor = service.store.list_events(map_id, OWNER_ID, after_seq=after_seq)
        map_item = service.store.get_map(map_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    if map_item is None:
        raise _error(LookupError("map not found"))
    return _envelope(events=[event.to_dict() for event in events], next_cursor=cursor)


@router.post("/{map_id}/jobs/{job_id}/stop")
def stop_literature_map_job(map_id: str, job_id: str):
    try:
        job = get_literature_map_service().stop_job(map_id, job_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(job=job.to_dict())


@router.post("/{map_id}/jobs/{job_id}/retry")
def retry_literature_map_job(map_id: str, job_id: str):
    try:
        job = get_literature_map_service().retry_job(map_id, job_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(job=job.to_dict())


@router.post("/{map_id}/nodes/{node_id}/imports", status_code=202)
def import_literature_map_node(map_id: str, node_id: str, payload: ImportRequest | None = None):
    try:
        result = get_literature_map_service().import_node(map_id, node_id, OWNER_ID)
    except Exception as error:
        raise _error(error) from error
    return _envelope(**result)


__all__ = ["router"]
