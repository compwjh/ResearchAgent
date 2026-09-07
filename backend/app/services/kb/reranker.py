"""Fail-open batch client for llama.cpp's local rerank endpoint (spec-014)."""
from __future__ import annotations

import ipaddress
import math
import threading
import time
from typing import Callable, Dict, Generic, List, Literal, NamedTuple, Optional, Sequence, Tuple, TypeVar
from urllib.parse import urlsplit

import httpx

T = TypeVar("T")
RerankReason = Literal[
    "disabled", "too_few_candidates", "connection", "timeout", "http_status", "invalid_json",
    "invalid_schema", "invalid_index", "invalid_score", "unexpected",
]
DEFAULT_BASE_URL = "http://127.0.0.1:11435"
DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, MIN_NEGATIVE_TTL = 2.0, 60.0, 30.0
class RerankResult(NamedTuple, Generic[T]):
    hits: List[T]
    used: bool; degraded: bool
    reason: Optional[RerankReason]
    elapsed_ms: float
    scores_by_original_index: Optional[Tuple[float, ...]] = None

_cache: Dict[Tuple[str, str], Tuple[RerankReason, float]] = {}
_lock = threading.Lock()

def clear_negative_cache() -> None:
    with _lock:
        _cache.clear()

def _url(value: str) -> Optional[str]:
    raw = (value or DEFAULT_BASE_URL).strip().rstrip("/")
    try:
        parsed, host = urlsplit(raw), urlsplit(raw).hostname
        _ = parsed.port
        loopback = bool(host) and (
            host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
        )
        if (parsed.scheme != "http" or not loopback or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            return None
    except (ValueError, TypeError):
        return None
    return raw

def _positive(value: float, default: float) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else default
    except (TypeError, ValueError):
        return default

def _fail(hits: Sequence[T], reason: RerankReason, ms: float = 0.0) -> RerankResult[T]:
    return RerankResult(list(hits), False, True, reason, ms)

def _cached(key: Tuple[str, str], now: float) -> Optional[RerankReason]:
    with _lock:
        state = _cache.get(key)
        if state and state[1] > now:
            return state[0]
        _cache.pop(key, None)
    return None

def _remember(key: Tuple[str, str], reason: RerankReason, now: float, ttl: float) -> None:
    with _lock:
        _cache[key] = reason, now + max(MIN_NEGATIVE_TTL, ttl)

def _scores(data: object, size: int) -> Tuple[Optional[List[float]], Optional[RerankReason]]:
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return None, "invalid_schema"
    results, values = data["results"], [None] * size
    if len(results) != size:
        return None, "invalid_index"
    for item in results:
        if not isinstance(item, dict):
            return None, "invalid_schema"
        index, score = item.get("index"), item.get("relevance_score")
        if (isinstance(index, bool) or not isinstance(index, int) or index < 0
                or index >= size or values[index] is not None):
            return None, "invalid_index"
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None, "invalid_score"
        score = float(score)
        if not math.isfinite(score):
            return None, "invalid_score"
        values[index] = score
    if any(score is None for score in values):
        return None, "invalid_index"
    return [float(score) for score in values], None

def rerank_hits(
    query: str, hits: Sequence[T], *, base_url: str = DEFAULT_BASE_URL,
    api_model: str = "", enabled: bool = True,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT, negative_ttl: float = MIN_NEGATIVE_TTL,
    transport: Optional[httpx.BaseTransport] = None,
    document_getter: Optional[Callable[[T], str]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> RerankResult[T]:
    """Use one request and return a new, stably sorted list or the original order."""
    original = list(hits)
    if not enabled:
        return _fail(original, "disabled")
    if len(original) <= 1:
        return _fail(original, "too_few_candidates")
    endpoint = _url(base_url)
    if endpoint is None or not isinstance(query, str) or not query.strip():
        return _fail(original, "unexpected")
    now, model = clock or time.monotonic, (api_model or "").strip()
    key, cached = (endpoint, model), _cached((endpoint, model), now())
    if cached:
        return _fail(original, cached)
    getter = document_getter or (lambda hit: getattr(hit, "text", ""))
    try:
        documents = [str(getter(hit) or "") for hit in original]
    except Exception:
        return _fail(original, "unexpected")
    payload = {"query": query, "documents": documents}
    if model:
        payload["model"] = model
    started, reason = now(), None
    timeout = httpx.Timeout(_positive(read_timeout, DEFAULT_READ_TIMEOUT),
                            connect=_positive(connect_timeout, DEFAULT_CONNECT_TIMEOUT))
    try:
        kwargs = {"timeout": timeout, "trust_env": False}
        if transport is not None:
            kwargs["transport"] = transport
        with httpx.Client(**kwargs) as client:
            response = client.post(f"{endpoint}/v1/rerank", json=payload)
        if not response.is_success:
            reason = "http_status"
        else:
            try:
                data = response.json()
            except (ValueError, UnicodeError):
                reason = "invalid_json"
            else:
                scores, reason = _scores(data, len(original))
                if reason is None and scores is not None:
                    order = sorted(range(len(original)), key=lambda i: (-scores[i], i))
                    with _lock:
                        _cache.pop(key, None)
                    return RerankResult([original[i] for i in order], True, False, None,
                                        (now() - started) * 1000.0, tuple(scores))
    except httpx.TimeoutException:
        reason = "timeout"
    except httpx.ConnectError:
        reason = "connection"
    except Exception:
        reason = "unexpected"
    elapsed, reason = (now() - started) * 1000.0, reason or "unexpected"
    _remember(key, reason, now(), _positive(negative_ttl, MIN_NEGATIVE_TTL))
    return _fail(original, reason, elapsed)
