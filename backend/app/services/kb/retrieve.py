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
from backend.app.services.kb.store import CHUNKER_V1

RRF_K = 60
_SCORE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

# 参考文献意图识别（spec-012）：用**短语**而非单词，避免正文里出现
# 单个 "reference"（如 reference implementation）就误判为问参考文献。
_CITATION_INTENT = [
    re.compile(r"参考\s*(文献|书目)"),
    re.compile(r"引用\s*(了)?\s*(哪些|什么)"),
    re.compile(r"引文|文献来源|出处|引用文献"),
    re.compile(r"\breference\s*(list|section|entry|entries)\b", re.IGNORECASE),
    re.compile(r"\blist\s+of\s+references\b", re.IGNORECASE),
    re.compile(r"\bbibliograph(y|ies)\b", re.IGNORECASE),
    re.compile(r"\bcitation(s)?\b", re.IGNORECASE),
    re.compile(r"\bcited\s+by\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+papers?\s+(are\s+)?cited\b", re.IGNORECASE),
    re.compile(r"\breferences?\s*[?？.]*\s*$", re.IGNORECASE),
]


@dataclass
class Hit:
    paper_id: str
    file_name: str
    page: int
    chunk_index: int
    text: str
    score: float
    # spec-012 新增，均带默认值以保证既有构造方式不被破坏
    chunker: str = CHUNKER_V1
    page_end: int = 0
    section: str = ""
    is_citation: bool = False

    def __post_init__(self) -> None:
        if not self.page_end or int(self.page_end) <= 0:
            self.page_end = int(self.page)


def _to_hit(point) -> Hit:
    payload = point.payload or {}
    return Hit(
        paper_id=payload.get("paper_id", ""),
        file_name=payload.get("file_name", ""),
        page=int(payload.get("page", 0) or 0),
        chunk_index=int(payload.get("chunk_index", 0) or 0),
        text=payload.get("text", "") or "",
        score=float(point.score or 0.0),
        chunker=payload.get("chunker") or CHUNKER_V1,
        page_end=int(payload.get("page_end", 0) or 0),
        section=payload.get("section") or "",
        is_citation=bool(payload.get("is_citation", False)),
    )


def rrf_fuse(ranked_lists: Sequence[Sequence], k: int = RRF_K) -> List[Hit]:
    """倒数排名融合：score = Σ 1/(k + rank)，rank 从 1 开始；按融合分降序。

    spec-012 T1：归并 key **必须含 chunker**，否则 v1/v2 的同一
    `chunk_index` 会被误当成同一片段而互相叠加分数（v1/v2 静默混召回）。
    """
    fused = {}
    for ranked in ranked_lists:
        for position, point in enumerate(ranked, start=1):
            hit = _to_hit(point)
            key = (hit.paper_id, hit.chunker, hit.chunk_index)
            accumulated = fused.get(key)
            if accumulated is None:
                fused[key] = hit
                accumulated = hit
                accumulated.score = 0.0
            accumulated.score += 1.0 / (k + position)
    return sorted(fused.values(), key=lambda hit: hit.score, reverse=True)


def hybrid_search(
    question: str,
    *,
    top_k: Optional[int] = None,
    candidate_pool: Optional[int] = None,
    chunker: Optional[str] = None,
    include_citations: Optional[bool] = None,
    paper_id: Optional[str] = None,
    client=None,
) -> List[Hit]:
    """双路召回 + RRF 融合 + 可选重排。

    spec-012：
    - `chunker` 非空时按切分版本过滤（v1/v2 隔离）；
    - `include_citations` 为 False 时排除参考文献片段；**默认按问题意图自动判定**
      （为 None 时调 `looks_like_citation_query`）——参考文献仍入库，只是默认不召回。
    - **两路都必须带同一个 filter**（T2），否则稀疏路会漏掉过滤条件。
    """
    target = client or get_client()
    limit = max(1, int(candidate_pool or KB_CANDIDATE_POOL))
    dense_vector = embed_texts([question])[0]

    if not target.collection_exists(KB_COLLECTION):
        return []

    allow_citations = (
        looks_like_citation_query(question) if include_citations is None else bool(include_citations)
    )
    query_filter = build_filter(
        paper_id=paper_id, chunker=chunker, include_citations=allow_citations
    )

    dense_points = target.query_points(
        collection_name=KB_COLLECTION,
        query=dense_vector,
        using=DENSE_VECTOR,
        limit=limit,
        query_filter=query_filter,
    ).points
    sparse_points = target.query_points(
        collection_name=KB_COLLECTION,
        query=encode_sparse(question),
        using=SPARSE_VECTOR,
        limit=limit,
        query_filter=query_filter,
    ).points

    hits = rrf_fuse([dense_points, sparse_points])
    hits = hits[: max(1, int(top_k or KB_TOP_K))]
    return rerank(question, hits)


def looks_like_citation_query(question: str) -> bool:
    """判断问题是否在问参考文献/出处（spec-012：仅自动意图识别，不提供手动开关）。

    命中即把 citation 纳入召回。用短语匹配以规避误判：
    正文里出现单个 "reference"（如 reference implementation）不会触发。
    """
    text = (question or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _CITATION_INTENT)


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


def build_filter(
    paper_id: Optional[str] = None,
    chunker: Optional[str] = None,
    include_citations: bool = True,
):
    """构造 Qdrant 过滤条件（spec-012）。

    - `chunker`：等值匹配切分版本，用于 v1/v2 隔离；
    - `include_citations=False`：追加 `is_citation == False`，把参考文献排除在默认召回外
      （参考文献仍入库，仅在问题明显在问参考文献时才纳入）。

    所有条件为空时返回 None（等价于不过滤）。
    """
    must = []
    if paper_id:
        must.append(
            models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id))
        )
    if chunker:
        must.append(
            models.FieldCondition(key="chunker", match=models.MatchValue(value=chunker))
        )
    if not include_citations:
        must.append(
            models.FieldCondition(key="is_citation", match=models.MatchValue(value=False))
        )
    return models.Filter(must=must) if must else None
