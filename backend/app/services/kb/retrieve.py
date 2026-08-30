"""混合检索：dense + sparse 双路召回，RRF 融合，可选 rerank（spec-011）。

为什么用 RRF 而不是分数加权：dense 是余弦（有界）、sparse 是点积（无界），
量纲不可比；RRF 只利用排名，无需归一化调参（见 011-tech-review §四）。
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from qdrant_client import models

from backend.app.core.config import (
    KB_CANDIDATE_POOL,
    KB_COLLECTION,
    KB_TOP_K,
    RERANKER_MODEL,
)
from backend.app.services.kb.embed import embed_texts, encode_sparse
from backend.app.services.kb.index import DENSE_VECTOR, SPARSE_VECTOR, get_client

RRF_K = 60
_SCORE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class Hit:
    paper_id: str
    file_name: str
    page: int
    chunk_index: int
    text: str
    score: float


def _to_hit(point) -> Hit:
    payload = point.payload or {}
    return Hit(
        paper_id=payload.get("paper_id", ""),
        file_name=payload.get("file_name", ""),
        page=int(payload.get("page", 0) or 0),
        chunk_index=int(payload.get("chunk_index", 0) or 0),
        text=payload.get("text", "") or "",
        score=float(point.score or 0.0),
    )


def rrf_fuse(ranked_lists: Sequence[Sequence], k: int = RRF_K) -> List[Hit]:
    """倒数排名融合：score = Σ 1/(k + rank)，rank 从 1 开始；按融合分降序。"""
    fused = {}
    for ranked in ranked_lists:
        for position, point in enumerate(ranked, start=1):
            hit = _to_hit(point)
            key = (hit.paper_id, hit.chunk_index)
            accumulated = fused.get(key)
            if accumulated is None:
                fused[key] = Hit(
                    paper_id=hit.paper_id,
                    file_name=hit.file_name,
                    page=hit.page,
                    chunk_index=hit.chunk_index,
                    text=hit.text,
                    score=0.0,
                )
                accumulated = fused[key]
            accumulated.score += 1.0 / (k + position)
    return sorted(fused.values(), key=lambda hit: hit.score, reverse=True)


def hybrid_search(
    question: str,
    *,
    top_k: Optional[int] = None,
    candidate_pool: Optional[int] = None,
    client=None,
) -> List[Hit]:
    target = client or get_client()
    limit = max(1, int(candidate_pool or KB_CANDIDATE_POOL))
    dense_vector = embed_texts([question])[0]

    if not target.collection_exists(KB_COLLECTION):
        return []

    dense_points = target.query_points(
        collection_name=KB_COLLECTION,
        query=dense_vector,
        using=DENSE_VECTOR,
        limit=limit,
    ).points
    sparse_points = target.query_points(
        collection_name=KB_COLLECTION,
        query=encode_sparse(question),
        using=SPARSE_VECTOR,
        limit=limit,
    ).points

    hits = rrf_fuse([dense_points, sparse_points])
    hits = hits[: max(1, int(top_k or KB_TOP_K))]
    return rerank(question, hits)


def reranker_available() -> bool:
    """reranker 为可插拔能力：未配置模型即视为不可用，主链路不受影响。"""
    return bool(RERANKER_MODEL)


def rerank(question: str, hits: List[Hit], model: Optional[str] = None) -> List[Hit]:
    """生成式重排；任何异常都降级为原顺序返回。"""
    name = model or RERANKER_MODEL
    if not name or len(hits) <= 1:
        return hits
    try:
        from backend.app.services.ollama import create_chat_model

        chat = create_chat_model(name)
        scored = []
        for hit in hits:
            prompt = (
                "判断下面段落与问题的相关程度，只输出 0 到 10 的整数，不要输出其它内容。\n"
                f"问题：{question}\n段落：{hit.text}\n分数："
            )
            raw = str(getattr(chat.invoke(prompt), "content", "") or "")
            match = _SCORE_PATTERN.search(raw)
            scored.append((float(match.group()) if match else 0.0, hit))
        return [hit for _, hit in sorted(scored, key=lambda item: item[0], reverse=True)]
    except Exception:
        return hits


def build_filter(paper_id: Optional[str]):
    """按论文过滤（预留：前端指定单篇检索时使用）。"""
    if not paper_id:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id))]
    )
