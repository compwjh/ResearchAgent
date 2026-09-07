"""Qdrant 索引读写与建库流水线（spec-011）。

并发约束（011-tech-review R5）：模块级单例 client + 单 worker + 写锁。
"""

import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from qdrant_client import QdrantClient, models

from backend.app.core.config import EMBED_DIM, KB_COLLECTION, QDRANT_PATH
from backend.app.services.kb.chunkers import build_chunks_v1, build_chunks_v2, ollama_boundary_judge
from backend.app.services.kb.embed import EmbeddingError, embed_texts, encode_sparse
from backend.app.services.kb.normalize import detect_citation, locate_reference_start
from backend.app.services.kb.parse import (
    Chunk,
    PdfParseError,
    build_chunks,
    extract_pages,
    extract_pages_normalized,
    total_chars,
)
from backend.app.services.kb.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
    get_paper,
    update_chunker_state,
    upsert_paper,
)

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"

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


def ensure_collection(client: QdrantClient, dim: Optional[int] = None) -> None:
    size = int(dim or EMBED_DIM)
    if client.collection_exists(KB_COLLECTION):
        return
    client.create_collection(
        collection_name=KB_COLLECTION,
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
) -> int:
    """写入片段；`chunker` 与 `is_citation` 进入 payload 供检索过滤。

    `ref_start_page` 非空时按 `detect_citation` 计算每个 chunk 的 `is_citation`；
    为 None（默认）时统一为 False，保持既有行为。
    """
    if not chunks:
        return 0
    target = client or get_client()
    with _write_lock:
        ensure_collection(target)
        vectors = embed_texts([chunk.text for chunk in chunks])
        target.upsert(
            collection_name=KB_COLLECTION,
            points=[
                models.PointStruct(
                    id=point_id(paper_id, chunk.chunk_index, chunker),
                    vector={
                        DENSE_VECTOR: vectors[position],
                        SPARSE_VECTOR: encode_sparse(chunk.text),
                    },
                    payload={
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
                    },
                )
                for position, chunk in enumerate(chunks)
            ],
        )
    return len(chunks)


def delete_paper_chunker(
    paper_id: str,
    chunker: str,
    client: Optional[QdrantClient] = None,
) -> None:
    """按 `paper_id + chunker` 删除该版本的旧点（重建索引前必须调用）。

    spec-012 T3：确定性 point_id 无法自动清理多出的旧点
    （重建后片段数变少时，多余旧点会永久残留并污染检索）。
    """
    target = client or get_client()
    if not target.collection_exists(KB_COLLECTION):
        return
    with _write_lock:
        target.delete(
            collection_name=KB_COLLECTION,
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


def delete_paper(paper_id: str, client: Optional[QdrantClient] = None) -> None:
    target = client or get_client()
    if not target.collection_exists(KB_COLLECTION):
        return
    with _write_lock:
        target.delete(
            collection_name=KB_COLLECTION,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id))]
                )
            ),
        )


def count_points(client: Optional[QdrantClient] = None) -> int:
    target = client or get_client()
    if not target.collection_exists(KB_COLLECTION):
        return 0
    return target.count(collection_name=KB_COLLECTION).count


def index_paper(record, file_path, client: Optional[QdrantClient] = None) -> dict:
    """解析 -> 切片 -> 向量化 -> 入库；返回更新后的记录 dict。

    任何异常都收敛为 `failed` 状态并附带可读错误，不向调用方抛裸异常。
    """
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
            record.paper_id,
            record.file_name,
            chunks,
            uploaded_at=record.uploaded_at,
            client=client,
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
    try:
        progress(max(0, min(100, int(value))))
    except Exception:
        pass


def index_paper_chunker(
    record,
    file_path,
    chunker: str = CHUNKER_V1,
    *,
    progress: Optional[Callable[[int], None]] = None,
    client: Optional[QdrantClient] = None,
    llm: Optional[Callable[[str], str]] = None,
    meta_path: Optional[Path] = None,
) -> dict:
    """按指定切分版本建索引（spec-012），返回更新后的论文 dict（含 `chunkers`）。

    `meta_path` 用于隔离测试（默认写真实元数据文件）。

    进度区间：解析清洗 0→10、切分 10→70（v2 的 LLM 阶段在此区间内细分）、
    入库 70→100。任何异常都收敛为 `failed` 并附可读错误，**不向上抛裸异常**，
    以免异步线程带着异常退出导致状态永远卡在 indexing。
    """
    paper_id = getattr(record, "paper_id", None) or record.get("paper_id")

    def _fail(message: str) -> dict:
        update_chunker_state(
            paper_id, chunker, status=STATUS_FAILED, progress=0, error=message, meta_path=meta_path
        )
        _report(progress, 100)
        return get_paper(paper_id, meta_path) or (
            record.to_dict() if hasattr(record, "to_dict") else dict(record)
        )

    update_chunker_state(
        paper_id, chunker, status=STATUS_INDEXING, progress=0, error=None, meta_path=meta_path
    )
    _report(progress, 0)

    try:
        pages = extract_pages_normalized(file_path)
    except PdfParseError as error:
        return _fail(str(error))
    except Exception as error:  # 解析层以外的意外（文件被删、权限等）
        return _fail(f"解析失败：{error}")

    if total_chars(pages) < MIN_TEXT_CHARS:
        return _fail("未提取到足够文本（疑似扫描件），未建立索引")
    _report(progress, 10)

    try:
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
    except Exception as error:
        return _fail(f"切分失败：{error}")

    if not chunks:
        return _fail("未能切分出可索引的文本")
    _report(progress, 70)

    ref_start = locate_reference_start(pages)
    try:
        # T3：先按 paper_id + chunker 删除该版本旧点，避免残留污染检索。
        try:
            delete_paper_chunker(paper_id, chunker, client=client)
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
        )
    except (EmbeddingError, ValueError, OSError) as error:
        return _fail(f"索引失败：{error}")
    except Exception as error:
        return _fail(f"索引失败：{error}")

    _report(progress, 95)
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


def backfill_chunker_defaults(client: Optional[QdrantClient] = None) -> int:
    """给 spec-011 遗留点补齐 `chunker` 等新增 payload 字段，返回补写数量。

    **为什么必须有这一步**：spec-012 的检索会按 `chunker` 等值过滤，
    而 spec-011 建的点没有该字段，Qdrant 对缺失字段的点**不会匹配**，
    结果是用户在点上「重建索引」之前，旧论文将完全检索不到。
    这里统一补 `chunker=v1` / `is_citation=False` / `section=""` /
    `page_end=page`，使旧数据按 v1 语义继续可用。
    """
    target = client or get_client()
    if not target.collection_exists(KB_COLLECTION):
        return 0

    updated = 0
    batch_size = 256
    offset = None
    with _write_lock:
        while True:
            points, offset = target.scroll(
                collection_name=KB_COLLECTION,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            stale = [point for point in (points or []) if not (point.payload or {}).get("chunker")]
            if stale:
                target.set_payload(
                    collection_name=KB_COLLECTION,
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
                        collection_name=KB_COLLECTION,
                        payload={"page_end": page},
                        points=ids,
                    )
                updated += len(stale)
            if not offset:
                break
    return updated
