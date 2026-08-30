"""Qdrant 索引读写与建库流水线（spec-011）。

并发约束（011-tech-review R5）：模块级单例 client + 单 worker + 写锁。
"""

import threading
import uuid
from pathlib import Path
from typing import List, Optional

from qdrant_client import QdrantClient, models

from backend.app.core.config import EMBED_DIM, KB_COLLECTION, QDRANT_PATH
from backend.app.services.kb.embed import EmbeddingError, embed_texts, encode_sparse
from backend.app.services.kb.parse import Chunk, PdfParseError, build_chunks, extract_pages, total_chars
from backend.app.services.kb.store import (
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
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


def point_id(paper_id: str, chunk_index: int) -> str:
    """确定性点 id：同一论文同一片段重复索引不会产生重复点。"""
    return str(uuid.uuid5(_NAMESPACE, f"{paper_id}:{chunk_index}"))


def upsert_chunks(
    paper_id: str,
    file_name: str,
    chunks: List[Chunk],
    uploaded_at: str = "",
    client: Optional[QdrantClient] = None,
) -> int:
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
                    id=point_id(paper_id, chunk.chunk_index),
                    vector={
                        DENSE_VECTOR: vectors[position],
                        SPARSE_VECTOR: encode_sparse(chunk.text),
                    },
                    payload={
                        "paper_id": paper_id,
                        "file_name": file_name,
                        "page": chunk.page,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "uploaded_at": uploaded_at,
                    },
                )
                for position, chunk in enumerate(chunks)
            ],
        )
    return len(chunks)


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
