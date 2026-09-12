"""Ollama 模型接入（Spec017）：模型枚举与会话模型创建。

本模块位于 `platform` 跨业务适配层，**禁止 import 业务模块**（静态边界规则，
Task07 会用 AST 静态检查强制）。因此这里只保留与业务无关的 Ollama 能力：

- `get_available_models()`：枚举本地可用模型；
- `create_chat_model()`：创建 LangChain 的 ChatOllama 会话模型；
- `ChatRun`：一次聊天的执行句柄（数据结构）。

需要驱动 LangGraph 会话图的 `run_chat` 已下沉到聊天上下文
`backend.app.chat.application.chat_runner`，因为 `graphs.chat` 属业务模块，
留在 platform 会构成反向依赖。
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterator, List, Optional

import httpx
from langchain_ollama import ChatOllama

from backend.app.platform.config import OLLAMA_BASE_URL
from backend.app.platform.ollama_direct import OllamaChatResult

REASONING_EFFORTS = ("off", "low", "medium", "high", "xhigh")
_CAPABILITY_TTL_SECONDS = 300.0
_capability_cache: dict[str, tuple[float, "ReasoningCapabilities"]] = {}
_capability_lock = threading.RLock()


@dataclass(frozen=True)
class ReasoningCapabilities:
    model: str
    supported_efforts: tuple[str, ...]
    # ``None`` when the support set is empty (``unknown``); never fabricate a
    # default such as ``off`` for an unprobed model (spec-026 B1).
    default_effort: Optional[str]
    source: str = "cache"
    cached_at: str = ""
    evidence_ids: dict[str, str] = None

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass(frozen=True)
class ReasoningResolution:
    model: str
    requested_effort: str
    provider_value: object
    capabilities: ReasoningCapabilities
    route_payload: dict
    evidence_id: Optional[str] = None

    @property
    def effort(self) -> str:
        return self.requested_effort

    def __getitem__(self, key: str):
        return getattr(self, key)


class EffortResolutionError(ValueError):
    """Raised by ``resolve_reasoning_effort`` on validation failure.

    Carries the already-probed ``capabilities`` so the caller can decide 409
    vs 503 without re-probing the model (spec-026 P2-1): the failure path must
    reuse this object, never call ``get_reasoning_capabilities`` again.  It is
    a ``ValueError`` subclass so existing ``except ValueError`` callers stay
    compatible and ``str(error)`` still yields the ``code``.
    """

    def __init__(self, code: str, capabilities: "ReasoningCapabilities"):
        super().__init__(code)
        self.code = code
        self.capabilities = capabilities


def _highest_supported(supported: "tuple[str, ...] | list[str] | set[str]") -> Optional[str]:
    """Return the highest supported effort by ``REASONING_EFFORTS`` ordering.

    ``supported`` is normally already ordered, but callers/tests may pass an
    arbitrary order, so filter through the canonical ordering first.  An empty
    set yields ``None`` — the previous ``supported[0]`` fallback silently
    returned the *lowest* effort (``off``), which is the spec-026 bug.
    """
    ordered = [effort for effort in REASONING_EFFORTS if effort in supported]
    return ordered[-1] if ordered else None


def probe_reasoning_capabilities(model: str) -> ReasoningCapabilities:
    """Probe each effort with a short non-streaming Ollama request.

    A failed probe is a normal condition (Ollama not running / model cold), so
    it never raises: an empty support set yields an ``unknown`` capability
    object with ``supported_efforts=()`` and ``default_effort=None``.  It is
    never downgraded to ``('off',)`` — fabricating support is exactly the bug
    this contract fixes.
    """
    model = str(model or "").strip()
    supported, evidence = [], {}
    for effort in REASONING_EFFORTS:
        provider_value = False if effort == "off" else (True if effort == "xhigh" else effort)
        payload = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly OK."}], "stream": False, "think": provider_value, "options": {"temperature": 0, "num_predict": 1}}
        try:
            response = httpx.post(f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=payload, timeout=5, trust_env=False)
            if response.status_code != 200:
                continue
            body = response.json() if response.content else {}
            message = body.get("message") or {}
            thinking = message.get("thinking")
            if (effort == "off" and not thinking) or (effort != "off" and isinstance(thinking, str) and thinking):
                supported.append(effort)
            else:
                continue
            evidence[effort] = f"OLLAMA-PROBE-{hashlib.sha256(json.dumps({'model': model, 'effort': effort, 'status': response.status_code}, sort_keys=True).encode()).hexdigest()[:16]}"
        except (httpx.HTTPError, ValueError, TypeError):
            continue
    if not supported:
        return ReasoningCapabilities(model, (), None, "unknown", "", {})
    return ReasoningCapabilities(model, tuple(supported), _highest_supported(supported), "ollama_probe", datetime.now(timezone.utc).isoformat(), evidence)


def get_reasoning_capabilities(model: str, *, refresh: bool = False) -> ReasoningCapabilities:
    key = str(model or "").strip()
    now = time.monotonic()
    with _capability_lock:
        cached = _capability_cache.get(key)
        if cached and not refresh and now - cached[0] < _CAPABILITY_TTL_SECONDS:
            return replace(cached[1], source="cache")
        capabilities = probe_reasoning_capabilities(key)
        if capabilities.source == "unknown":
            # A failed probe must not evict or overwrite a previously valid
            # entry (spec-026 B16).  Reuse the stale result — including its
            # original ``cached_at`` — when anything is cached, otherwise
            # report ``unknown``.
            if cached is not None:
                return replace(cached[1], source="stale")
            return capabilities
        _capability_cache[key] = (now, capabilities)
        return capabilities


def clear_reasoning_capability_cache() -> None:
    with _capability_lock:
        _capability_cache.clear()


def _provider_value(requested: str) -> object:
    """Map an application effort to Ollama's transport ``think`` value.

    ``off`` → boolean ``False``; ``xhigh`` → boolean ``True`` (Ollama's
    thinking mode); every other effort passes the string through untouched.
    Single source of truth shared by ``resolve_reasoning_effort`` and the
    ``unknown``+``off`` fallback in ``routes_conversations._resolve_request_effort``
    (spec-026 P2-3) so the two mappings cannot drift.
    """
    return False if requested == "off" else (True if requested == "xhigh" else requested)


def resolve_reasoning_effort(model: str, effort: Optional[str] = None) -> ReasoningResolution:
    """Resolve a session effort to the exact provider value.

    ``off`` maps to boolean ``False``; string efforts are never silently
    downgraded.  Unsupported xhigh/high therefore fail before model creation.

    Validation failures raise ``EffortResolutionError`` carrying the already
    probed ``capabilities`` (spec-026 P2-1) so the caller need not re-probe.
    """
    capabilities = get_reasoning_capabilities(model)
    requested = str(effort if effort is not None else "xhigh").strip().lower()
    if requested not in REASONING_EFFORTS:
        raise EffortResolutionError("INVALID_REASONING_EFFORT", capabilities)
    if requested not in capabilities.supported_efforts:
        raise EffortResolutionError("REASONING_EFFORT_UNSUPPORTED", capabilities)
    # Ollama's boolean thinking mode is the provider representation of the
    # application-level ``xhigh`` effort.  Keep ``requested_effort`` as the
    # stable business value while exposing the exact transport value to both
    # direct and LangChain callers.
    provider_value: object = _provider_value(requested)
    route_payload = {"think": provider_value}
    return ReasoningResolution(str(model), requested, provider_value, capabilities, route_payload, capabilities.evidence_ids.get(requested) if capabilities.evidence_ids else None)


def get_available_models() -> List[str]:
    response = httpx.get(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags",
        timeout=5,
        trust_env=False,
    )
    response.raise_for_status()
    return [item["name"] for item in response.json().get("models", [])]


def create_chat_model(model_name: str, *, reasoning: Optional[bool | str] = None) -> ChatOllama:
    """创建本地 Ollama 会话模型。

    `trust_env=False` 是必须的：httpx 默认会读取 macOS 系统代理配置，
    把指向 localhost:11434 的请求也送去代理，代理返回 503，表现为「无法连接 Ollama」。

    `reasoning` 默认 **None（不下发开关）**，保持改动前行为：ChatOllama 会把该参数
    映射为请求体的 `think` 字段（langchain_ollama 中 `"think": kwargs.pop("reasoning",
    self.reasoning)`）。对不支持 thinking 的模型（如 `deepseek-coder-v2:16b`），下发
    `think: true` 会让 Ollama 返回 HTTP 400 `does not support thinking`；对思考模型
    （如 `qwen3.5:9b`）则会强制开启思维链、拖长响应。因此只有显式传入 True/False 时
    才下发该开关——KB 问答经 `run_chat(..., think=False)` 显式关闭思维链。
    """
    return ChatOllama(
        model=model_name,
        base_url=OLLAMA_BASE_URL,
        client_kwargs={"trust_env": False},
        async_client_kwargs={"trust_env": False},
        sync_client_kwargs={"trust_env": False},
        reasoning=reasoning,
    )


@dataclass
class ChatRun:
    """一次聊天的执行句柄。

    route：实际使用的链路（"langchain" | "direct"）；
    events：可迭代，产出 {"type": "token"|"thinking", "content": str}；
    result：迭代结束（或失败）后可用的 OllamaChatResult。
    """

    route: str
    events: "Iterator[dict]" = None
    result: Optional[OllamaChatResult] = None

    def __iter__(self) -> "Iterator[dict]":
        return iter(self.events)

    def __next__(self) -> dict:
        return next(self.events)
