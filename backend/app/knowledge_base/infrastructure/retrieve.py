"""混合检索：dense + sparse 双路召回，RRF 融合，可选 rerank（spec-011）。

为什么用 RRF 而不是分数加权：dense 是余弦（有界）、sparse 是点积（无界），
量纲不可比；RRF 只利用排名，无需归一化调参（见 011-tech-review §四）。
"""

import math
import re
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

import httpx
from qdrant_client import models

from backend.app.core.config import (
    KB_CANDIDATE_POOL,
    KB_COLLECTION,
    KB_RERANK_CANDIDATES,
    KB_TOP_K,
    RERANKER_API_MODEL,
    RERANKER_BASE_URL,
    RERANKER_CONNECT_TIMEOUT_SECONDS,
    RERANKER_ENABLED,
    RERANKER_READ_TIMEOUT_SECONDS,
)
from backend.app.knowledge_base.infrastructure.embed import embed_texts, encode_sparse
from backend.app.knowledge_base.infrastructure.index import DENSE_VECTOR, SPARSE_VECTOR, get_client
from backend.app.knowledge_base.infrastructure.reranker import _url as _reranker_url
from backend.app.knowledge_base.infrastructure.reranker import rerank_hits
from backend.app.knowledge_base.infrastructure.store import CHUNKER_V1
from backend.app.observability import record_event
from backend.app.observability.safe import safe_call

RRF_K = 60
_SCORE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_RERANKER_MODEL_ID = "ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0"
_RERANKER_HEALTH_TTL = 30.0
_RERANKER_HEALTH_PROBE = (
    "What is the capital of France?",
    (
        "Whales are marine mammals that breathe air.",
        "Paris is the capital and most populous city of France.",
        "The Moon orbits Earth approximately every 27 days.",
    ),
)
_health_condition = threading.Condition()
_health_cache = {}
_health_inflight = set()

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
    rerank_score: Optional[float] = None
    rerank_rank: Optional[int] = None

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
    started_at = time.perf_counter()
    effective_top_k = max(1, int(top_k or KB_TOP_K))
    limit = max(1, int(candidate_pool or KB_CANDIDATE_POOL))
    metadata = {
        "top_k": effective_top_k,
        "candidate_pool": limit,
        "chunker": chunker,
        "reranker_enabled": RERANKER_ENABLED,
     }
    try:
       target = client or get_client()
       dense_vector = embed_texts([question])[0]

       if not target.collection_exists(KB_COLLECTION):
           safe_call(record_event,
               name="kb.retrieval",
               metadata={**metadata, "hit_count": 0, "status": "ok"},
               duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            )
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
       candidate_count = max(effective_top_k, KB_RERANK_CANDIDATES)
       candidates = hits[:candidate_count]
       rerank_result = rerank_hits(
           question,
           candidates,
           base_url=RERANKER_BASE_URL,
           api_model=RERANKER_API_MODEL,
           enabled=RERANKER_ENABLED,
           connect_timeout=RERANKER_CONNECT_TIMEOUT_SECONDS,
           read_timeout=RERANKER_READ_TIMEOUT_SECONDS,
       )
       if rerank_result.used and rerank_result.scores_by_original_index is not None:
           for hit, score in zip(candidates, rerank_result.scores_by_original_index):
               hit.rerank_score = score
           for rank, hit in enumerate(rerank_result.hits, start=1):
               hit.rerank_rank = rank
       result = rerank_result.hits[:effective_top_k]
       _record_rerank_result(
           rerank_result,
           input_count=len(candidates),
           output_count=len(result),
       )
       safe_call(
           record_event,
           name="kb.retrieval",
           metadata={
               **metadata,
               "rerank_candidate_count": len(candidates),
               "hit_count": len(result),
               "status": "ok",
           },
           duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
       )
       return result
    except Exception as error:  # 记录后原样抛出，绝不吞、绝不改变异常类型
       safe_call(
           record_event,
           name="kb.retrieval",
           metadata={**metadata, "status": "error", "error_type": type(error).__name__},
           duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
       )
       raise


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
    """Return the real, cached readiness state used by the health endpoint."""
    state = reranker_health()
    return bool(state["enabled"] and state["available"])


def _health_detail(enabled: bool, available: bool, model: str, reason: Optional[str]) -> dict:
    return {
        "enabled": bool(enabled),
        "available": bool(available),
        "backend": "llama.cpp",
        "model": model,
        "reason": None if available else reason,
    }


def _health_probe(
    endpoint: Optional[str], model: str, connect_timeout: float, read_timeout: float,
    transport=None,
) -> dict:
    if endpoint is None:
        return _health_detail(True, False, model, "connection")
    timeout = httpx.Timeout(
        min(max(float(connect_timeout), 0.001), 2.0),
        connect=min(max(float(connect_timeout), 0.001), 2.0),
        read=min(max(float(read_timeout), 0.001), 2.0),
    )
    kwargs = {"timeout": timeout, "trust_env": False}
    if transport is not None:
        kwargs["transport"] = transport
    try:
        with httpx.Client(**kwargs) as client:
            ready = client.get(f"{endpoint}/health")
            if not ready.is_success:
                return _health_detail(True, False, model, "model_not_prepared")
            try:
                health_payload = ready.json()
            except (ValueError, UnicodeError):
                return _health_detail(True, False, model, "quality_probe_failed")
            if not isinstance(health_payload, dict):
                return _health_detail(True, False, model, "quality_probe_failed")

            payload = {"query": _RERANKER_HEALTH_PROBE[0], "documents": list(_RERANKER_HEALTH_PROBE[1])}
            if model != _RERANKER_MODEL_ID:
                payload["model"] = model
            response = client.post(f"{endpoint}/v1/rerank", json=payload)
            if not response.is_success:
                return _health_detail(True, False, model, "quality_probe_failed")
            try:
                data = response.json()
            except (ValueError, UnicodeError):
                return _health_detail(True, False, model, "quality_probe_failed")
            scores, invalid_reason = _probe_scores(data)
            if invalid_reason or scores is None or scores[1] <= max(scores[0], scores[2]):
                return _health_detail(True, False, model, "quality_probe_failed")
            return _health_detail(True, True, model, None)
    except httpx.TimeoutException:
        return _health_detail(True, False, model, "timeout")
    except httpx.ConnectError:
        return _health_detail(True, False, model, "connection")
    except httpx.HTTPError:
        return _health_detail(True, False, model, "connection")
    except (TypeError, ValueError, OverflowError):
        return _health_detail(True, False, model, "quality_probe_failed")
    except Exception:
        return _health_detail(True, False, model, "quality_probe_failed")


def _probe_scores(data: object):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return None, "schema"
    results = data["results"]
    if len(results) != 3:
        return None, "index"
    scores = {}
    for item in results:
        if not isinstance(item, dict):
            return None, "schema"
        index, score = item.get("index"), item.get("relevance_score")
        if isinstance(index, bool) or not isinstance(index, int) or index not in (0, 1, 2) or index in scores:
            return None, "index"
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None, "score"
        score = float(score)
        if not math.isfinite(score):
            return None, "score"
        scores[index] = score
    if set(scores) != {0, 1, 2}:
        return None, "index"
    return (scores[0], scores[1], scores[2]), None


def reranker_health(
    *, enabled: Optional[bool] = None, base_url: Optional[str] = None,
    api_model: Optional[str] = None, connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None, transport=None, clock=None,
) -> dict:
    """Probe loopback readiness and ranking quality, with a 30-second single-flight cache."""
    enabled = RERANKER_ENABLED if enabled is None else enabled
    base_url = RERANKER_BASE_URL if base_url is None else base_url
    api_model = RERANKER_API_MODEL if api_model is None else api_model
    connect_timeout = (
        RERANKER_CONNECT_TIMEOUT_SECONDS if connect_timeout is None else connect_timeout
    )
    read_timeout = RERANKER_READ_TIMEOUT_SECONDS if read_timeout is None else read_timeout
    model = (api_model or "").strip() or _RERANKER_MODEL_ID
    if not enabled:
        return _health_detail(False, False, model, "disabled")
    endpoint = _reranker_url(base_url)
    # Test transports are isolated from the process-wide production cache; the
    # live path remains keyed only by the configured loopback endpoint/model.
    key = (endpoint or "", model, id(transport) if transport is not None else None)
    now_fn = clock or time.monotonic
    while True:
        now = now_fn()
        with _health_condition:
            cached = _health_cache.get(key)
            if cached is not None and cached[1] > now:
                return dict(cached[0])
            if key not in _health_inflight:
                _health_inflight.add(key)
                break
            _health_condition.wait(timeout=0.1)
    detail = _health_detail(True, False, model, "quality_probe_failed")
    try:
        detail = _health_probe(endpoint, model, connect_timeout, read_timeout, transport)
    except Exception:
        detail = _health_detail(True, False, model, "quality_probe_failed")
    finally:
        with _health_condition:
            _health_cache[key] = (detail, now_fn() + _RERANKER_HEALTH_TTL)
            _health_inflight.discard(key)
            _health_condition.notify_all()
    return dict(detail)


def rerank(question: str, hits: List[Hit], model: Optional[str] = None) -> List[Hit]:
    """兼容旧调用方的逐条模型重排；主检索链路使用本机批量 reranker。"""
    started_at = time.perf_counter()
    name = (model or "").strip()
    enabled = bool(name)
    if not name:
        _record_rerank_event(
            status="disabled",
            input_count=len(hits),
            output_count=len(hits),
            enabled=False,
            degraded_reason="model_not_configured",
            started_at=started_at,
        )
        return hits
    if len(hits) <= 1:
        _record_rerank_event(
            status="disabled",
            input_count=len(hits),
            output_count=len(hits),
            enabled=enabled,
            degraded_reason="insufficient_candidates",
            started_at=started_at,
        )
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
        result = [hit for _, hit in sorted(scored, key=lambda item: item[0], reverse=True)]
        _record_rerank_event(
            status="ok",
            input_count=len(hits),
            output_count=len(result),
            enabled=True,
            started_at=started_at,
        )
        return result
    except Exception as error:
        _record_rerank_event(
            status="degraded",
            input_count=len(hits),
            output_count=len(hits),
            enabled=True,
            degraded_reason="rerank_exception",
            error_type=type(error).__name__,
            started_at=started_at,
        )
        return hits


def _record_rerank_result(result, *, input_count: int, output_count: int) -> None:
    """Emit Spec 013's event while preserving Spec 014's fail-open result."""
    used = bool(getattr(result, "used", False))
    reason = getattr(result, "reason", None)
    elapsed_ms = getattr(result, "elapsed_ms", 0.0)
    if used:
        status, degraded_reason = "ok", None
    elif reason == "disabled":
        status, degraded_reason = "disabled", reason
    else:
        status, degraded_reason = "degraded", reason
    _record_rerank_event(
        status=status,
        input_count=input_count,
        output_count=output_count,
        enabled=RERANKER_ENABLED,
        degraded_reason=degraded_reason,
        started_at=time.perf_counter() - (max(float(elapsed_ms or 0.0), 0.0) / 1000.0),
    )


def _record_rerank_event(
    *,
    status: str,
    input_count: int,
    output_count: int,
    enabled: bool,
    started_at: float,
    degraded_reason: Optional[str] = None,
    error_type: Optional[str] = None,
) -> None:
    metadata = {
        "status": status,
        "input_count": input_count,
        "output_count": output_count,
        "enabled": enabled,
    }
    if degraded_reason:
        metadata["degraded_reason"] = degraded_reason
    if error_type:
        metadata["error_type"] = error_type
    try:
        safe_call(record_event,
            name="kb.rerank",
            metadata=metadata,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
    except Exception:
        # 观测故障不得改变检索结果或降级语义。
        return


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
