"""Qdrant 索引读写与建库流水线（spec-011）。

并发约束（011-tech-review R5）：模块级单例 client + 单 worker + 写锁。
"""

import hashlib
import re
import threading
import uuid
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from qdrant_client import QdrantClient, models

from backend.app.knowledge_base.infrastructure.chunkers import build_chunks_v1, build_chunks_v2, ollama_boundary_judge
from backend.app.knowledge_base.infrastructure.embed import EmbeddingError, embed_texts, encode_sparse
from backend.app.knowledge_base.infrastructure.inspection import (
    InspectionError,
    build_inspection_manifest,
)
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestStoreError,
    publication_mutation_lock,
)
from backend.app.knowledge_base.infrastructure.migration import (
    KnowledgeDocumentMigrationError,
    publish_index_state,
)
from backend.app.knowledge_base.infrastructure.markdown import extract_markdown_provenance
from backend.app.knowledge_base.infrastructure.normalize import detect_citation, locate_reference_start
from backend.app.knowledge_base.infrastructure.parse import (
    Chunk,
    PdfParseError,
    build_chunks,
    extract_pages,
    extract_pages_normalized,
    extract_pdf_provenance,
    total_chars,
)
from backend.app.knowledge_base.infrastructure.provenance import build_source_provenance_bundle
from backend.app.knowledge_base.infrastructure.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
    get_paper,
    record_id,
    update_chunker_state,
    upsert_paper,
)
from backend.app.platform.config import EMBED_DIM, KB_COLLECTION, KB_META_PATH, QDRANT_PATH

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"


class IndexWriteBoundaryError(RuntimeError):
    """Raised when a legacy index writer has no explicit destination.

    The old helpers predate generation/candidate isolation and used the live
    ``KB_COLLECTION`` whenever the caller omitted a collection.  Keeping the
    error on this infrastructure boundary makes accidental direct consumers
    fail closed instead of silently writing the formal index.
    """

    code = "DESTINATION_COLLECTION_REQUIRED"

    def __init__(self) -> None:
        super().__init__(self.code)


_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _required_destination(destination: Optional[str]) -> str:
    if not isinstance(destination, str) or not _COLLECTION_NAME.fullmatch(destination):
        raise IndexWriteBoundaryError()
    return destination

# 扫描件判定阈值：整篇可提取字符数低于此值视为无文本层
MIN_TEXT_CHARS = 100

_client: Optional[QdrantClient] = None
_client_lock = threading.Lock()
_write_lock = threading.Lock()


_NAMESPACE = uuid.UUID("6f2caa19-8501-42e8-9db7-14c1796dddc6")


def get_client(path: Optional[str] = None) -> QdrantClient:
    """懒加载单例：本地文件模式不允许被多进程同时打开。"""
    global _client
    with _client_lock:
        if _client is None:
            target = Path(path or QDRANT_PATH)
            target.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(target))
        return _client


def reset_client() -> None:
    """仅供测试与运维：丢弃当前单例。"""
    global _client
    with _client_lock:
        _client = None


def ensure_collection(
    client: QdrantClient,
    dim: Optional[int] = None,
    *,
    collection_name: Optional[str] = None,
) -> None:
    """Ensure a dense+sparse collection exists.

    ``collection_name`` is deliberately required.  Callers must obtain the
    destination from a generation-aware application port or pass an explicit
    isolated collection; there is no implicit ``KB_COLLECTION`` fallback.
    """
    size = int(dim or EMBED_DIM)
    target_collection = _required_destination(collection_name)
    if client.collection_exists(target_collection):
        return
    client.create_collection(
        collection_name=target_collection,
        vectors_config={DENSE_VECTOR: models.VectorParams(size=size, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )


def point_id(paper_id: str, chunk_index: int, chunker: str = CHUNKER_V1) -> str:
    """确定性点 id：同一论文同一片段重复索引不会产生重复点。

    spec-012：**必须带 chunker 维度**，否则 v1/v2 的 `chunk_index` 会撞车
    互相覆盖（原为 `f"{paper_id}:{chunk_index}"`）。
    `chunker` 默认 v1，保证既有两参数调用行为不变。
    """
    return str(uuid.uuid5(_NAMESPACE, f"{paper_id}:{chunker}:{chunk_index}"))


def upsert_chunks(
    paper_id: str,
    file_name: str,
    chunks: List[Chunk],
    uploaded_at: str = "",
    client: Optional[QdrantClient] = None,
    chunker: str = CHUNKER_V1,
    ref_start_page: Optional[int] = None,
    destination_collection: Optional[str] = None,
    document_id: Optional[str] = None,
    source_sha256: Optional[str] = None,
) -> int:
    """写入片段；`chunker` 与 `is_citation` 进入 payload 供检索过滤。

    `ref_start_page` 非空时按 `detect_citation` 计算每个 chunk 的 `is_citation`；
    为 None（默认）时统一为 False，保持既有行为。
    """
    if not chunks:
        return 0
    collection = _required_destination(destination_collection)
    target = client or get_client()
    with _write_lock:
        ensure_collection(target, collection_name=collection)
        vectors = embed_texts([chunk.text for chunk in chunks])
        points = []
        for position, chunk in enumerate(chunks):
            payload = {
                "paper_id": paper_id,
                "file_name": file_name,
                "page": chunk.page,
                "page_end": chunk.page_end,
                "section": chunk.section,
                "chunker": chunker,
                "is_citation": (
                    detect_citation(chunk.text, chunk.page, ref_start_page=ref_start_page)
                    if ref_start_page is not None
                    else False
                ),
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "uploaded_at": uploaded_at,
            }
            # New knowledge-document records need the identity and source
            # hash required by the inspection-manifest contract.  Keep the
            # legacy payload shape unchanged for callers that do not provide
            # these values.
            if document_id:
                payload["document_id"] = document_id
            if source_sha256:
                payload["source_sha256"] = source_sha256
            points.append(
                models.PointStruct(
                    id=point_id(paper_id, chunk.chunk_index, chunker),
                    vector={
                        DENSE_VECTOR: vectors[position],
                        SPARSE_VECTOR: encode_sparse(chunk.text),
                    },
                    payload=payload,
                )
            )
        target.upsert(
            collection_name=collection,
            points=points,
        )
    return len(chunks)


def delete_paper_chunker(
    paper_id: str,
    chunker: str,
    client: Optional[QdrantClient] = None,
    destination_collection: Optional[str] = None,
) -> None:
    """按 `paper_id + chunker` 删除该版本的旧点（重建索引前必须调用）。

    spec-012 T3：确定性 point_id 无法自动清理多出的旧点
    （重建后片段数变少时，多余旧点会永久残留并污染检索）。
    """
    collection = _required_destination(destination_collection)
    target = client or get_client()
    if not target.collection_exists(collection):
        return
    with _write_lock:
        target.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="paper_id", match=models.MatchValue(value=paper_id)
                        ),
                        models.FieldCondition(
                            key="chunker", match=models.MatchValue(value=chunker)
                        ),
                    ]
                )
            ),
        )


def delete_paper(
    paper_id: str,
    client: Optional[QdrantClient] = None,
    *,
    destination_collection: Optional[str] = None,
) -> None:
    collection = _required_destination(destination_collection)
    target = client or get_client()
    if not target.collection_exists(collection):
        return
    with _write_lock:
        target.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id))]
                )
            ),
        )


def count_points(
    client: Optional[QdrantClient] = None,
    *,
    collection_name: Optional[str] = None,
) -> int:
    target = client or get_client()
    collection = collection_name or KB_COLLECTION
    if not target.collection_exists(collection):
        return 0
    return target.count(collection_name=collection).count


def index_paper(
    record,
    file_path,
    client: Optional[QdrantClient] = None,
    *,
    destination_collection: Optional[str] = None,
) -> dict:
    """解析 -> 切片 -> 向量化 -> 入库；返回更新后的记录 dict。

    任何异常都收敛为 `failed` 状态并附带可读错误，不向调用方抛裸异常。
    """
    destination = _required_destination(destination_collection)
    paper_id = record_id(record)
    file_name = getattr(record, "file_name", None)
    if file_name is None and isinstance(record, Mapping):
        file_name = record.get("file_name", "")
    try:
        pages = extract_pages(file_path)
    except PdfParseError as error:
        record.status = STATUS_FAILED
        record.error = str(error)
        return upsert_paper(record).to_dict()

    record.page_count = len(pages)
    if total_chars(pages) < MIN_TEXT_CHARS:
        record.status = STATUS_PARTIAL
        record.chunk_count = 0
        record.error = "未提取到足够文本（疑似扫描件），未建立索引"
        return upsert_paper(record).to_dict()

    chunks = build_chunks(pages)
    if not chunks:
        record.status = STATUS_PARTIAL
        record.chunk_count = 0
        record.error = "未能切分出可索引的文本"
        return upsert_paper(record).to_dict()

    try:
        record.chunk_count = upsert_chunks(
            paper_id,
            file_name or "",
            chunks,
            uploaded_at=record.uploaded_at,
            client=client,
            destination_collection=destination,
        )
    except (EmbeddingError, ValueError, OSError) as error:
        record.status = STATUS_FAILED
        record.error = f"索引失败：{error}"
        return upsert_paper(record).to_dict()

    record.status = STATUS_INDEXED
    record.error = None
    return upsert_paper(record).to_dict()


def _report(progress: Optional[Callable[[int], None]], value: int) -> None:
    """进度回写；回调自身抛错不能影响索引流程。"""
    if progress is None:
        return
    with suppress(Exception):
        progress(max(0, min(100, int(value))))


def _record_value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _normalize_index_error(message: Any) -> str:
    """Collapse parser hash failures into the canonical publication error."""
    value = str(message)
    if value in {"PDF_SOURCE_HASH_MISMATCH", "SOURCE_HASH_MISMATCH"}:
        return "SOURCE_HASH_MISMATCH"
    return value


def _source_pages(provenance: Any) -> List[tuple[Optional[int], str]]:
    """Project parser provenance into the page text needed by citation detection."""
    if getattr(provenance, "media_type", "") == "text/markdown":
        return [(None, str(getattr(provenance, "normalized_text", "") or ""))]
    by_page: Dict[int, List[str]] = {}
    for block in getattr(provenance, "blocks", ()):
        by_page.setdefault(int(block.page), []).append(str(getattr(block, "raw_text", "") or ""))
    return [(page, "".join(texts)) for page, texts in sorted(by_page.items())]


def _bundle_chunks(bundle: Any) -> List[Chunk]:
    chunks: List[Chunk] = []
    for value in bundle.chunks:
        chunks.append(
            Chunk(
                text=str(value["text"]),
                page=value.get("page"),
                page_end=value.get("page_end"),
                section=str(value.get("section") or ""),
                chunk_index=int(value["chunk_index"]),
            )
        )
    return chunks


def _build_index_bundle(record: Any, file_path: Any, chunker: str, llm: Optional[Callable[[str], str]]) -> tuple[Any, Any, List[Chunk]] | None:
    """Build provenance and chunks once for canonical document records.

    Returning the chunks from the bundle is intentional: v2's LLM output is
    consumed by both Qdrant and the manifest, so the two artifacts cannot
    diverge because of a second LLM call.
    """
    document_id = str(_record_value(record, "document_id") or record_id(record) or "")
    source_sha256 = _record_value(record, "source_sha256")
    media_type = str(_record_value(record, "media_type") or "application/pdf")
    if not document_id or not isinstance(source_sha256, str) or not source_sha256:
        return None
    if media_type == "text/markdown":
        provenance = extract_markdown_provenance(
            file_path,
            document_id=document_id,
            source_sha256=source_sha256,
        )
    elif media_type == "application/pdf":
        provenance = extract_pdf_provenance(
            file_path,
            document_id=document_id,
            source_sha256=source_sha256,
        )
    else:
        return None
    bundle = build_source_provenance_bundle(
        provenance,
        chunker=chunker,
        llm=llm if chunker == CHUNKER_V2 else None,
    )
    return provenance, bundle, _bundle_chunks(bundle)


def _source_digest(path: Any) -> str | None:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except (OSError, ValueError):
        return None
    return digest.hexdigest()


def _publish_inspection_manifest(
    record: Any,
    bundle: Any,
    chunks: List[Chunk],
    *,
    meta_path: Optional[Path],
) -> Any:
    """Publish the manifest from the exact payloads sent to Qdrant."""
    document = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    document_id = str(document.get("document_id") or record_id(document))
    document["document_id"] = document_id
    payloads = [
        {
            "document_id": document_id,
            "source_sha256": bundle.source_sha256,
            "chunker": bundle.chunker,
            "chunk_index": int(chunk.chunk_index),
            "text": chunk.text,
            "page": chunk.page,
            "page_end": chunk.page_end,
            "section": chunk.section,
        }
        for chunk in chunks
    ]
    manifest = build_inspection_manifest(document, bundle, payloads)
    root = Path(meta_path or KB_META_PATH).resolve().parent
    return InspectionManifestStore(root).write(manifest)


def _canonical_index_record(record: Any) -> bool:
    return bool(
        _record_value(record, "document_id")
        and isinstance(_record_value(record, "source_sha256"), str)
        and _record_value(record, "source_sha256")
    )


def _mark_index_failed(
    record: Any,
    paper_id: str,
    chunker: str,
    *,
    error: str,
    meta_path: Optional[Path],
    refresh_marker: bool = True,
) -> None:
    """Best-effort strict failed-state publication with no path leakage."""
    if not _canonical_index_record(record):
        update_chunker_state(
            paper_id, chunker, status=STATUS_FAILED, progress=0, error=error, meta_path=meta_path
        )
        return
    try:
        with publication_mutation_lock():
            hash_kwargs = {}
            if error == "SOURCE_HASH_MISMATCH":
                hash_kwargs = {
                    "indexed_source_sha256": str(_record_value(record, "source_sha256")),
                    "source_hash_state": "mismatch",
                }
            publish_index_state(
                Path(meta_path or KB_META_PATH),
                paper_id,
                chunker,
                status=STATUS_FAILED,
                progress=0,
                chunk_count=0,
                error=error,
                **hash_kwargs,
            )
            if refresh_marker:
                FinalizeBundleStore(Path(meta_path or KB_META_PATH).resolve().parent.parents[1]).refresh_live_digests()
    except Exception:
        # Failure to persist the controlled failure is itself fail-closed.  In
        # particular, do not call the compatibility writer as a fallback.
        return


def _manifest_status(manifest: Mapping[str, Any]) -> str:
    status = manifest.get("status")
    return {
        "ready": STATUS_INDEXED,
        "partial": STATUS_PARTIAL,
        "failed": STATUS_FAILED,
    }.get(str(status), STATUS_FAILED)


def _publish_manifest_and_state(
    record: Any,
    bundle: Any,
    chunks: List[Chunk],
    *,
    paper_id: str,
    chunker: str,
    file_path: Any,
    count: int,
    meta_path: Optional[Path],
) -> Mapping[str, Any]:
    """Publish manifest, strict metadata, and live generation marker in order."""
    source_sha256 = str(bundle.source_sha256)
    meta = Path(meta_path or KB_META_PATH)
    finalizer = FinalizeBundleStore(meta.resolve().parent.parents[1])
    with publication_mutation_lock():
        try:
            manifest = _publish_inspection_manifest(record, bundle, chunks, meta_path=meta)
        except (InspectionError, ManifestStoreError, OSError, ValueError) as error:
            _mark_index_failed(
                record,
                paper_id,
                chunker,
                error="MANIFEST_PUBLISH_FAILED",
                meta_path=meta,
                refresh_marker=False,
            )
            raise ManifestStoreError("MANIFEST_PUBLISH_FAILED", status=503) from error
        manifest_value = manifest.to_dict() if hasattr(manifest, "to_dict") else dict(manifest)
        try:
            publish_index_state(
                meta,
                paper_id,
                chunker,
                status=_manifest_status(manifest_value),
                progress=int(manifest_value.get("progress", 100)),
                chunk_count=count,
                error=manifest_value.get("error"),
                indexed_source_sha256=source_sha256,
                source_hash_state="verified",
            )
        except KnowledgeDocumentMigrationError as error:
            _mark_index_failed(
                record,
                paper_id,
                chunker,
                error="INDEX_FINALIZE_REQUIRED",
                meta_path=meta,
                refresh_marker=False,
            )
            raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503) from error
        try:
            finalizer.refresh_live_digests()
            finalizer.require_generation()
            live_manifest = InspectionManifestStore(meta.resolve().parent).read(paper_id, chunker).to_dict()
            if (
                live_manifest.get("index_fingerprint") != manifest_value.get("index_fingerprint")
                or live_manifest.get("source_sha256") != source_sha256
                or live_manifest.get("indexed_source_sha256") != source_sha256
                or _source_digest(file_path) != source_sha256
            ):
                raise ManifestStoreError("SOURCE_HASH_MISMATCH", status=409)
            return live_manifest
        except Exception as error:
            _mark_index_failed(
                record,
                paper_id,
                chunker,
                error="SOURCE_HASH_MISMATCH" if getattr(error, "code", "") == "SOURCE_HASH_MISMATCH" else "INDEX_FINALIZE_REQUIRED",
                meta_path=meta,
                # The manifest may already be ready while marker verification
                # failed; leave marker/live deliberately mismatched so every
                # reader gate rejects this intermediate publication.
                refresh_marker=False,
            )
            raise ManifestStoreError(
                "SOURCE_HASH_MISMATCH" if getattr(error, "code", "") == "SOURCE_HASH_MISMATCH" else "INDEX_FINALIZE_REQUIRED",
                status=409 if getattr(error, "code", "") == "SOURCE_HASH_MISMATCH" else 503,
            ) from error


def index_paper_chunker(
    record,
    file_path,
    chunker: str = CHUNKER_V1,
    *,
    progress: Optional[Callable[[int], None]] = None,
    client: Optional[QdrantClient] = None,
    llm: Optional[Callable[[str], str]] = None,
    meta_path: Optional[Path] = None,
    destination_collection: Optional[str] = None,
) -> dict:
    """按指定切分版本建索引（spec-012），返回更新后的论文 dict（含 `chunkers`）。

    `meta_path` 用于隔离测试（默认写真实元数据文件）。

    进度区间：解析清洗 0→10、切分 10→70（v2 的 LLM 阶段在此区间内细分）、
    入库 70→100。任何异常都收敛为 `failed` 并附可读错误，**不向上抛裸异常**，
    以免异步线程带着异常退出导致状态永远卡在 indexing。
    """
    destination = _required_destination(destination_collection)
    paper_id = record_id(record)

    def _fail(message: str) -> dict:
        normalized_message = _normalize_index_error(message)
        _mark_index_failed(
            record,
            paper_id,
            chunker,
            error=normalized_message,
            meta_path=meta_path,
            refresh_marker=normalized_message != "SOURCE_HASH_MISMATCH",
        )
        _report(progress, 100)
        return get_paper(paper_id, meta_path) or (
            record.to_dict() if hasattr(record, "to_dict") else dict(record)
        )

    update_chunker_state(
        paper_id, chunker, status=STATUS_INDEXING, progress=0, error=None, meta_path=meta_path
    )
    _report(progress, 0)

    bundle = None
    provenance = None
    try:
        bundle_result = _build_index_bundle(
            record,
            file_path,
            chunker,
            llm if llm is not None else ollama_boundary_judge,
        )
        if bundle_result is not None:
            provenance, bundle, chunks = bundle_result
            pages = _source_pages(provenance)
            # Markdown is allowed to be a short document; the PDF threshold
            # remains the existing scanned-PDF guard.
            if (
                getattr(provenance, "media_type", "") == "application/pdf"
                and total_chars(pages) < MIN_TEXT_CHARS
            ):
                return _fail("未提取到足够文本（疑似扫描件），未建立索引")
            _report(progress, 60)
        else:
            pages = extract_pages_normalized(file_path)
            if total_chars(pages) < MIN_TEXT_CHARS:
                return _fail("未提取到足够文本（疑似扫描件），未建立索引")
            _report(progress, 10)
            if chunker == CHUNKER_V2:
                def _sub_progress(value: int) -> None:
                    # 把 v2 自身 0-100 的进度映射到全局 10-70
                    _report(progress, 10 + int(60 * max(0, min(100, int(value))) / 100))

                chunks, _llm_used = build_chunks_v2(
                    pages,
                    llm=llm if llm is not None else ollama_boundary_judge,
                    progress=_sub_progress,
                )
            else:
                chunks = build_chunks_v1(pages)
                _report(progress, 60)
    except (PdfParseError, InspectionError, ManifestStoreError, ValueError) as error:
        return _fail(str(error))
    except Exception as error:  # 解析层以外的意外（文件被删、权限等）
        return _fail(f"解析/切分失败：{error}")

    if not chunks:
        return _fail("未能切分出可索引的文本")
    _report(progress, 70)

    ref_start = locate_reference_start(pages) if pages and pages[0][0] is not None else None
    document_id = str(_record_value(record, "document_id") or "") or None
    source_sha256 = _record_value(record, "source_sha256")
    try:
        # T3：先按 paper_id + chunker 删除该版本旧点，避免残留污染检索。
        try:
            delete_kwargs = {"client": client, "destination_collection": destination}
            delete_paper_chunker(paper_id, chunker, **delete_kwargs)
        except Exception:
            pass  # 首次索引时 collection 可能不存在，忽略即可
        count = upsert_chunks(
            paper_id,
            getattr(record, "file_name", "") or record.get("file_name", ""),
            chunks,
            uploaded_at=getattr(record, "uploaded_at", "") or record.get("uploaded_at", ""),
            client=client,
            chunker=chunker,
            ref_start_page=ref_start,
            destination_collection=destination,
            document_id=document_id,
            source_sha256=source_sha256 if isinstance(source_sha256, str) else None,
        )
    except (EmbeddingError, ValueError, OSError) as error:
        return _fail(f"索引失败：{error}")
    except Exception as error:
        return _fail(f"索引失败：{error}")

    # The parser verifies the immutable hash before chunking.  Re-check after
    # the vector write as well: a source mutation during embedding must never
    # reach manifest or verified metadata publication.
    if bundle is not None:
        expected_source_sha256 = str(bundle.source_sha256)
        if _source_digest(file_path) != expected_source_sha256:
            return _fail("SOURCE_HASH_MISMATCH")

    _report(progress, 95)
    if bundle is not None:
        try:
            _publish_manifest_and_state(
                record,
                bundle,
                chunks,
                paper_id=paper_id,
                chunker=chunker,
                file_path=file_path,
                count=count,
                meta_path=meta_path,
            )
        except ManifestStoreError as error:
            _report(progress, 100)
            return get_paper(paper_id, meta_path) or (
                record.to_dict() if hasattr(record, "to_dict") else dict(record)
            )
    else:
        # Legacy records have no canonical source hash/manifest.  Keep their
        # compatibility state path unchanged; canonical documents always use
        # the strict manifest+metadata publication above.
        update_chunker_state(
            paper_id,
            chunker,
            status=STATUS_INDEXED,
            progress=100,
            chunk_count=count,
            error=None,
            meta_path=meta_path,
        )
    _report(progress, 100)
    return get_paper(paper_id, meta_path) or (
        record.to_dict() if hasattr(record, "to_dict") else dict(record)
    )


def backfill_chunker_defaults(
    client: Optional[QdrantClient] = None,
    *,
    destination_collection: Optional[str] = None,
) -> int:
    """给 spec-011 遗留点补齐 `chunker` 等新增 payload 字段，返回补写数量。

    **为什么必须有这一步**：spec-012 的检索会按 `chunker` 等值过滤，
    而 spec-011 建的点没有该字段，Qdrant 对缺失字段的点**不会匹配**，
    结果是用户在点上「重建索引」之前，旧论文将完全检索不到。
    这里统一补 `chunker=v1` / `is_citation=False` / `section=""` /
    `page_end=page`，使旧数据按 v1 语义继续可用。
    """
    destination = _required_destination(destination_collection)
    target = client or get_client()
    if not target.collection_exists(destination):
        return 0

    updated = 0
    batch_size = 256
    offset = None
    with _write_lock:
        while True:
            points, offset = target.scroll(
                collection_name=destination,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            stale = [point for point in (points or []) if not (point.payload or {}).get("chunker")]
            if stale:
                target.set_payload(
                    collection_name=destination,
                    payload={"chunker": CHUNKER_V1, "is_citation": False, "section": ""},
                    points=[point.id for point in stale],
                )
                # page_end 依赖各自 page，按页分组批量写，避免逐点调用
                grouped: Dict[int, List[Any]] = {}
                for point in stale:
                    page = int((point.payload or {}).get("page", 0) or 0)
                    grouped.setdefault(page, []).append(point.id)
                for page, ids in grouped.items():
                    target.set_payload(
                        collection_name=destination,
                        payload={"page_end": page},
                        points=ids,
                    )
                updated += len(stale)
            if not offset:
                break
    return updated


class GenerationBoundIndexPort:
    """Generation-authorized facade for the legacy chunker implementation.

    The parser/embedder implementation remains in this module for backwards
    compatibility, but application consumers receive a destination-bound
    object instead of importing a write helper that can choose a collection.
    The destination is validated once and is passed explicitly on every
    operation.
    """

    def __init__(self, destination_collection: str, *, client: Optional[QdrantClient] = None) -> None:
        self.destination_collection = _required_destination(destination_collection)
        self.client = client

    def index_document(
        self,
        record: Any,
        file_path: Any,
        chunker: str = CHUNKER_V1,
        *,
        progress: Optional[Callable[[int], None]] = None,
        llm: Optional[Callable[[str], str]] = None,
        meta_path: Optional[Path] = None,
    ) -> dict:
        return index_paper_chunker(
            record,
            file_path,
            chunker,
            progress=progress,
            client=self.client,
            llm=llm,
            meta_path=meta_path,
            destination_collection=self.destination_collection,
        )

    def delete_document(self, paper_id: str, chunker: str = CHUNKER_V1) -> None:
        delete_paper_chunker(
            paper_id,
            chunker,
            client=self.client,
            destination_collection=self.destination_collection,
        )
