import base64
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, List

import httpx
from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.app.api.common import *  # noqa: F401,F403
from backend.app.api.schemas import KBAskRequest
from backend.app.chat.application.chat_runner import run_chat
from backend.app.knowledge_base.application import (
    CHUNKER_V1,
    CHUNKER_V2,
    CHUNKERS,
    DocumentReadError,
    InspectionManifestStore,
    KnowledgeDocumentMigrationError,
    ManifestStoreError,
    build_prompt,
    citation_payloads,
    count_points,
    create_uploaded_document,
    delete_document,
    embed_texts,
    ensure_collection,
    get_client,
    hybrid_search,
    load_papers,
    load_papers_strict,
    read_document_source,
    reranker_health,
    submit_document_reindex,
)
from backend.app.platform.config import CHUNK_V2_LLM_MODEL, KB_DIR, KB_MAX_UPLOAD_MB
from backend.app.platform.observability import end_trace, flush, record_ollama_generation, start_trace, utc_now
from backend.app.platform.ollama import get_available_models
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)

router = APIRouter()
# FastAPI evaluates ``File(...)``/``Query(...)`` defaults while importing the
# module.  Keep the existing route signatures explicit while documenting the
# framework-call rule for the static checker.
# ruff: noqa: B008,SIM105
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


def kb_component_status() -> dict:
    reranker_detail = reranker_health()
    generation = {"ready": False, "error_code": "INDEX_REBUILD_REQUIRED"}
    try:
        generation["ready"] = True
        generation["error_code"] = None
        _generation_store().require_generation()
    except ManifestStoreError as error:
        generation["ready"] = False
        generation["error_code"] = getattr(error, "code", "INDEX_REBUILD_REQUIRED")
    status = {
        "qdrant": False,
        "embedding": False,
        "reranker": bool(reranker_detail["enabled"] and reranker_detail["available"]),
        "reranker_detail": reranker_detail,
        "papers": len(load_papers()),
        "chunks": 0,
        # spec-012：v2 结构分析模型是否可用（不可用时 v2 会降级为规则切分）
        "v2_llm": {"model": CHUNK_V2_LLM_MODEL, "available": False},
        "generation": generation,
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


def _document_error(
    status: int,
    code: str,
    message: str,
    *,
    request: Request | None = None,
    document_id: str | None = None,
    chunker: str | None = None,
    task_id: str | None = None,
    retryable: bool = False,
    details: Any = None,
    headers: dict[str, str] | None = None,
    operation_status: str | None = None,
    progress: int | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error_code": code,
        "message": message,
        "retryable": bool(retryable),
        "request_id": (request.headers.get("X-Request-ID") if request else None) or uuid.uuid4().hex,
    }
    for key, value in (
        ("document_id", document_id),
        ("chunker", chunker),
        ("task_id", task_id),
        ("status", operation_status),
        ("progress", progress),
        ("details", details),
    ):
        if value is not None:
            body[key] = value
    response_headers = dict(headers or {})
    if status >= 500 and "Retry-After" not in response_headers:
        response_headers["Retry-After"] = "10"
    if status >= 500:
        retry_details = dict(details) if isinstance(details, dict) else {}
        retry_details.setdefault("retry_after_seconds", 10)
        body["details"] = retry_details
    return JSONResponse(status_code=status, content=body, headers=response_headers)


def _document_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": item.get("document_id") or item.get("paper_id"),
        "file_name": item.get("file_name"),
        "media_type": item.get("media_type"),
        "source_sha256": item.get("source_sha256"),
        "source_immutable": item.get("source_immutable", False),
        "status": item.get("status"),
        "created_at": item.get("created_at") or item.get("uploaded_at"),
        "page_count": item.get("page_count"),
        "chunk_count": item.get("chunk_count", 0),
        "chunkers": item.get("chunkers", {}),
        "error": item.get("error"),
    }


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = base64.urlsafe_b64decode(cursor.encode("ascii") + b"=" * (-len(cursor) % 4)).decode("ascii")
        offset = int(value)
    except (ValueError, TypeError, UnicodeError, base64.binascii.Error):
        raise ValueError from None
    if offset < 0:
        raise ValueError
    return offset


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii").rstrip("=")


def _encode_inspection_cursor(document_id: str, chunker: str, offset: int) -> str:
    value = {"schema_version": "inspection-cursor-v1", "document_id": document_id, "chunker": chunker, "offset": offset}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_inspection_cursor(cursor: str | None, document_id: str, chunker: str) -> int:
    if not cursor:
        return 0
    if len(cursor) > 512:
        raise ValueError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"=" * (-len(cursor) % 4))
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, base64.binascii.Error):
        raise ValueError from None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "inspection-cursor-v1"
        or value.get("document_id") != document_id
        or value.get("chunker") != chunker
        or not isinstance(value.get("offset"), int)
        or isinstance(value.get("offset"), bool)
        or value["offset"] < 0
    ):
        raise ValueError
    return value["offset"]


def _canonical_document(document_id: str) -> bool:
    try:
        records = load_papers_strict()
    except Exception:
        raise RuntimeError from None
    return any(
        isinstance(item, dict)
        and item.get("schema_version") == "knowledge-document-v1"
        and (item.get("document_id") or item.get("paper_id")) == document_id
        for item in records
    )


def _generation_store() -> Any:
    # FinalizeBundleStore receives the repository root; its live root is
    # ``data/kb``.  The inspection store receives that live root directly.
    from backend.app.knowledge_base.application import FinalizeBundleStore

    return FinalizeBundleStore(KB_DIR.parents[1])


def _require_generation(request: Request, *, finalize_pending: bool = False) -> JSONResponse | None:
    try:
        _generation_store().require_generation(finalize_pending=finalize_pending)
    except ManifestStoreError as error:
        status = int(getattr(error, "status", 409))
        return _document_error(
            status,
            getattr(error, "code", "INDEX_REBUILD_REQUIRED"),
            "索引代际尚未完成提交" if status >= 500 else "索引尚未完成全库重建",
            request=request,
            retryable=status >= 500,
        )
    return None


@router.get("/kb/documents")
def list_documents(
    request: Request,
    limit: str = Query(default="50"),
    cursor: str | None = Query(default=None),
):
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 0
    if limit_value < 1 or limit_value > 100:
        return _document_error(400, "INVALID_LIMIT", "limit 必须在 1 到 100 之间", request=request)
    try:
        offset = _decode_cursor(cursor)
        records = load_papers_strict()
    except ValueError:
        return _document_error(400, "INVALID_CURSOR", "cursor 无效", request=request)
    except Exception:
        return _document_error(503, "METADATA_INVALID", "文档元数据暂时不可用", request=request, retryable=True)
    summaries = [
        _document_summary(item)
        for item in records
        if isinstance(item, dict) and item.get("schema_version") == "knowledge-document-v1"
    ]
    if offset > len(summaries):
        return _document_error(400, "INVALID_CURSOR", "cursor 无效", request=request)
    page = summaries[offset : offset + limit_value]
    next_cursor = _encode_cursor(offset + limit_value) if offset + limit_value < len(summaries) else None
    payload = {"documents": page, "next_cursor": next_cursor, "total": len(summaries)}
    etag = '"sha256:%s"' % hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if request.headers.get("if-none-match", "").strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(status_code=200, content=payload, headers={"ETag": etag})


@router.post("/kb/documents/upload", status_code=201)
async def upload_document(request: Request, file: UploadFile | None = File(default=None)):
    if file is None:
        return _document_error(400, "INVALID_REQUEST", "upload 请求缺少 file", request=request)
    file_name = (file.filename or "").strip()
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in {".md", ".markdown"}:
        media_type = "text/markdown"
    else:
        return _document_error(415, "UNSUPPORTED_MEDIA_TYPE", "只支持 PDF 或 UTF-8 Markdown", request=request)
    if file.content_type != media_type:
        return _document_error(415, "UNSUPPORTED_MEDIA_TYPE", "文件扩展名与 MIME 类型不一致", request=request)
    max_bytes = KB_MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        return _document_error(413, "PAYLOAD_TOO_LARGE", "文件超过上传容量上限", request=request, retryable=False)
    if len(file_name.encode("utf-8")) > 255:
        return _document_error(413, "PAYLOAD_TOO_LARGE", "文件名超过 UTF-8 字节上限", request=request)
    try:
        result = create_uploaded_document(file_name, media_type, content)
    except DocumentReadError as error:
        code = error.code
        if code == "SOURCE_EMPTY":
            code = "INVALID_PDF" if media_type == "application/pdf" else "INVALID_ENCODING"
        elif code == "INVALID_UTF8":
            code = "INVALID_ENCODING"
        elif code == "SOURCE_MEDIA_TYPE_UNSUPPORTED":
            code = "UNSUPPORTED_MEDIA_TYPE"
        return _document_error(error.status, code, "原件校验失败", request=request, retryable=error.status >= 500)
    except KnowledgeDocumentMigrationError as error:
        status = 503 if error.code in {"METADATA_INVALID", "MIGRATION_WRITE_FAILED"} else 400
        return _document_error(status, error.code, "文档元数据写入失败", request=request, retryable=status >= 500)
    except Exception:
        return _document_error(503, "SOURCE_WRITE_FAILED", "原件暂时无法保存", request=request, retryable=True)
    document = result["document"]
    return {
        "document_id": document["document_id"],
        "media_type": document["media_type"],
        "file_name": document["file_name"],
        "source_sha256": document["source_sha256"],
        "status": document["status"],
        "chunkers": document["chunkers"],
        "task_id": result.get("task_id"),
    }


def _read_document_source_response(document_id: str, request: Request):
    try:
        result = read_document_source(
            document_id,
            range_header=request.headers.get("range"),
            if_none_match=request.headers.get("if-none-match"),
            head_only=request.method == "HEAD",
        )
    except DocumentReadError as error:
        headers = {}
        if error.status == 416 and error.size is not None:
            headers["Content-Range"] = f"bytes */{error.size}"
        code = "UNSUPPORTED_MEDIA_TYPE" if error.code == "SOURCE_MEDIA_TYPE_UNSUPPORTED" else error.code
        return _document_error(error.status, code, "原件读取失败", request=request, document_id=document_id, retryable=error.status >= 500, headers=headers)
    headers = result.headers
    return Response(content=b"" if request.method == "HEAD" else result.body, status_code=result.status, headers=headers)


@router.get("/kb/documents/{document_id}/source")
def read_document_source_route(document_id: str, request: Request):
    return _read_document_source_response(document_id, request)


@router.head("/kb/documents/{document_id}/source")
def head_document_source_route(document_id: str, request: Request):
    return _read_document_source_response(document_id, request)


@router.get("/kb/documents/{document_id}/inspection")
def inspect_document(
    document_id: str,
    request: Request,
    chunker: str = Query(default="v1"),
    page_size: str = Query(default="200"),
    cursor: str | None = Query(default=None),
):
    if chunker not in CHUNKERS:
        return _document_error(400, "INVALID_CHUNKER", "chunker 必须为 v1 或 v2", request=request, document_id=document_id)
    try:
        page_size_value = int(page_size)
    except (TypeError, ValueError):
        page_size_value = 0
    if page_size_value < 1 or page_size_value > 500:
        return _document_error(400, "INVALID_PAGE_SIZE", "page_size 必须在 1 到 500 之间", request=request, document_id=document_id, chunker=chunker)
    try:
        offset = _decode_inspection_cursor(cursor, document_id, chunker)
    except ValueError:
        return _document_error(400, "INVALID_CURSOR", "cursor 无效", request=request, document_id=document_id, chunker=chunker)
    try:
        exists = _canonical_document(document_id)
    except RuntimeError:
        return _document_error(503, "METADATA_INVALID", "文档元数据暂时不可用", request=request, document_id=document_id, retryable=True)
    if not exists:
        return _document_error(404, "DOCUMENT_NOT_FOUND", "文档不存在", request=request, document_id=document_id, chunker=chunker)
    gate = _require_generation(request)
    if gate is not None:
        return gate
    manifest_store = InspectionManifestStore(KB_DIR)
    try:
        manifest = manifest_store.read(document_id, chunker).to_dict()
    except ManifestStoreError as error:
        if getattr(error, "code", "") == "MANIFEST_NOT_FOUND":
            task_id = hashlib.sha256(f"inspection:{document_id}:{chunker}".encode("utf-8")).hexdigest()[:32]
            try:
                manifest_store.claim(document_id, chunker, owner=f"inspection-{task_id}")
            except ManifestStoreError as claim_error:
                # An active claim is the durable idempotency record for the
                # build request; all callers may safely poll the same task.
                if getattr(claim_error, "code", "") != "MANIFEST_CLAIMED":
                    return _document_error(
                        503,
                        "MANIFEST_FAILED",
                        "检查清单构建任务暂时无法提交",
                        request=request,
                        document_id=document_id,
                        chunker=chunker,
                        retryable=True,
                    )
            return _document_error(
                202,
                "INSPECTION_BUILDING",
                "检查清单正在生成",
                request=request,
                document_id=document_id,
                chunker=chunker,
                task_id=task_id,
                operation_status="building",
                progress=0,
                retryable=True,
                headers={"Location": f"/api/kb/documents/{document_id}/inspection", "Retry-After": "2"},
            )
        return _document_error(
            503,
            "MANIFEST_FAILED",
            "检查清单不可用",
            request=request,
            document_id=document_id,
            chunker=chunker,
            retryable=True,
            details={"cause": getattr(error, "code", "MANIFEST_FAILED")},
        )
    try:
        blocks = list(manifest.get("blocks", []))
        chunks = list(manifest.get("chunks", []))
        anchors = list(manifest.get("anchors", []))
        totals = {"blocks": len(blocks), "chunks": len(chunks), "anchors": len(anchors)}
        if offset > max(totals.values(), default=0):
            raise ValueError
        page_end = offset + page_size_value
        visible_blocks = blocks[offset:page_end]
        visible_chunks = chunks[offset:page_end]
        visible_anchors = anchors[offset:page_end]
        has_next = page_end < max(totals.values(), default=0)
        next_cursor = _encode_inspection_cursor(document_id, chunker, page_end) if has_next else None
    except (TypeError, ValueError):
        return _document_error(400, "INVALID_CURSOR", "cursor 无效", request=request, document_id=document_id, chunker=chunker)
    response_manifest = dict(manifest)
    response_manifest.pop("blocks", None)
    response_manifest.pop("chunks", None)
    response_manifest.pop("anchors", None)
    response = {
        "document_id": document_id,
        "chunker": chunker,
        "manifest": response_manifest,
        "blocks": visible_blocks,
        "chunks": visible_chunks,
        "anchors": visible_anchors,
        "next_cursor": next_cursor,
        "total": totals,
    }
    etag = '"sha256:%s"' % hashlib.sha256(
        json.dumps({"manifest": manifest, "cursor": cursor or ""}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if request.headers.get("if-none-match", "").strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(status_code=200, content=response, headers={"ETag": etag})


@router.post("/kb/documents/{document_id}/reindex", status_code=202)
def reindex_document_route(document_id: str, request: Request, body: Any = Body(default=None)):
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return _document_error(400, "INVALID_REQUEST", "重建请求体必须为 JSON object", request=request, document_id=document_id)
    selected_chunker = body.get("chunker", "all")
    if selected_chunker not in (*CHUNKERS, "all"):
        return _document_error(400, "INVALID_CHUNKER", "chunker 必须为 v1、v2 或 all", request=request, document_id=document_id)
    try:
        exists = _canonical_document(document_id)
    except RuntimeError:
        return _document_error(503, "METADATA_INVALID", "文档元数据暂时不可用", request=request, document_id=document_id, retryable=True)
    if not exists:
        return _document_error(404, "DOCUMENT_NOT_FOUND", "文档不存在", request=request, document_id=document_id, chunker=selected_chunker)
    gate = _require_generation(request)
    if gate is not None:
        return gate
    try:
        result = submit_document_reindex(document_id, selected_chunker)
    except KnowledgeDocumentMigrationError as error:
        status = {
            "DOCUMENT_NOT_FOUND": 404,
            "SOURCE_NOT_FOUND": 404,
            "CHUNKER_UNSUPPORTED": 400,
            "SOURCE_HASH_MISMATCH": 409,
            "INDEX_ALREADY_RUNNING": 409,
        }.get(error.code, 503)
        code = "INVALID_CHUNKER" if error.code == "CHUNKER_UNSUPPORTED" else error.code
        return _document_error(status, code, "文档无法重建索引", request=request, document_id=document_id, chunker=selected_chunker, retryable=status >= 500)
    except Exception:
        return _document_error(503, "QDRANT_UNAVAILABLE", "索引任务暂时无法启动", request=request, document_id=document_id, chunker=selected_chunker, retryable=True)
    submitted = result.get("submitted", {}) if isinstance(result, dict) else {}
    if not isinstance(submitted, dict) or not submitted or not all(submitted.values()):
        return _document_error(
            409,
            "INDEX_ALREADY_RUNNING",
            "文档已有索引任务运行中",
            request=request,
            document_id=document_id,
            chunker=selected_chunker,
            operation_status="running",
            progress=0,
        )
    return JSONResponse(
        status_code=202,
        content={"task_id": result["task_id"], "document_id": document_id, "chunker": selected_chunker, "status": "queued", "progress": 0},
        headers={"Location": f"/api/kb/documents/{document_id}/inspection", "Retry-After": "2"},
    )


@router.delete("/kb/documents/{document_id}")
def delete_document_route(document_id: str, request: Request):
    try:
        result = delete_document(document_id)
    except Exception:
        return _document_error(503, "DELETE_PENDING", "文档删除待重试", request=request, document_id=document_id, retryable=True)
    if result is None:
        return _document_error(404, "DOCUMENT_NOT_FOUND", "文档不存在", request=request, document_id=document_id)
    if result.get("status") != "completed":
        return _document_error(
            503,
            "DELETE_PENDING",
            "文档删除待重试",
            request=request,
            document_id=document_id,
            retryable=True,
            details=result,
            headers={"Location": f"/api/kb/documents/{document_id}"},
        )
    return result


@router.post("/kb/upload", status_code=201)
async def upload_kb_paper(request: Request, file: UploadFile | None = File(default=None)) -> dict:
    """Compatibility alias for the canonical immutable document upload."""
    return await upload_document(request, file)


@router.post("/kb/papers/{paper_id}/reindex")
def reindex_kb_paper(
    paper_id: str,
    request: Request,
    body: Any = Body(default=None),
) -> dict:
    """Compatibility alias forwarding to the canonical document reindex API."""
    return reindex_document_route(paper_id, request, body)


@router.delete("/kb/papers/{paper_id}")
def delete_kb_paper(paper_id: str, request: Request) -> dict:
    """Compatibility alias forwarding to canonical document deletion."""
    return delete_document_route(paper_id, request)


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
