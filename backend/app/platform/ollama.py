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

import contextlib
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterator, List, Optional

import httpx
from langchain_ollama import ChatOllama

from backend.app.platform import capability_store
from backend.app.platform.config import OLLAMA_BASE_URL
from backend.app.platform.ollama_direct import OllamaChatResult

REASONING_EFFORTS = ("off", "low", "medium", "high", "xhigh")
_CAPABILITY_TTL_SECONDS = 300.0
# spec-035 Bug3：SQLite 二级缓存的新鲜期（与后台每日探测周期对齐）。
_CAPABILITY_DB_TTL_SECONDS = 24 * 60 * 60.0
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
    # spec-035 Bug3：内存未命中时回源 SQLite（24h 内视为新鲜），避免每次切模型
    # 都实时探测 Ollama。探测结果由后台调度器每日刷新入库，这里只读。
    if not refresh:
        stored = capability_store.get_capabilities(key)
        if stored is not None and capability_store.probed_at_is_fresh(
            stored["probed_at"], max_age_seconds=_CAPABILITY_DB_TTL_SECONDS
        ):
            stored_caps = ReasoningCapabilities(
                stored["model"],
                stored["supported_efforts"],
                stored["default_effort"],
                "cache",
                stored["probed_at"],
                stored["evidence"],
            )
            with _capability_lock:
                _capability_cache[key] = (now, stored_caps)
            return replace(stored_caps, source="cache")
    capabilities = probe_reasoning_capabilities(key)
    if capabilities.source == "unknown":
        # A failed probe must not evict or overwrite a previously valid
        # entry (spec-026 B16).  Reuse the stale result — including its
        # original ``cached_at`` — when anything is cached, otherwise
        # report ``unknown``.  The SQLite tier is deliberately NOT consulted
        # here: the four-state source semantics stay byte-for-byte identical
        # to the pre-spec-035 contract.
        if cached is not None:
            return replace(cached[1], source="stale")
        return capabilities
    with _capability_lock:
        _capability_cache[key] = (now, capabilities)
    # 实时探测成功的结果写回 SQLite，供下次启动 / 其它 worker 直接命中。
    capability_store.upsert_capabilities(
        capabilities.model,
        supported_efforts=capabilities.supported_efforts,
        default_effort=capabilities.default_effort,
        source=capabilities.source,
        evidence=dict(capabilities.evidence_ids or {}),
        probed_at=capabilities.cached_at,
    )
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


# --------------------------------------------------------------------------- #
# 资源探针（Spec027 §动态模型和 Worker）：9B Worker 并发上限 + 全局公平轮转
# --------------------------------------------------------------------------- #
# 接口冻结在 platform 层，只从既有 `get_available_models()` 与 Ollama `/api/ps`
# 读取，禁止新增第二套模型客户端（Spec027 复用接缝）。所有新增符号仅依赖
# 标准库 + httpx + backend.app.platform.config，不 import 任何业务模块。

RESOURCE_MARGIN_FRACTION = 0.20   # 至少保留 20% 系统余量
PROBE_TIMEOUT_SECONDS = 3.0


def read_loaded_models(base_url: str | None = None, *, timeout: float = PROBE_TIMEOUT_SECONDS) -> list[dict]:
    """读取 Ollama `/api/ps` 当前已加载（驻留显存）的模型清单。

    仅从既有 Ollama 服务读取，不引入第二套模型客户端（Spec027 复用接缝）。

    设计为「薄读取」：任何网络/解析错误都**向上抛**（主要是 `httpx.HTTPError`），
    由 `ResourceProbe` 统一捕获并降级为单 Worker。这里故意不做 try/except——
    读取失败本身就是「探针能力不可用」的信号，吞掉异常反而会让上层误以为
    「无模型驻留 = 可安全并发」。

    `trust_env=False` 与 `get_available_models` 同理由：macOS 系统代理会把指向
    localhost:11434 的请求也送进代理，导致 503 误判为「Ollama 不可达」。

    `size_vram` 缺失时补 0（Ollama 某些版本字段名或省略该字段）。
    """
    url = f"{(base_url or OLLAMA_BASE_URL).rstrip('/')}/api/ps"
    response = httpx.get(url, timeout=timeout, trust_env=False)
    response.raise_for_status()
    models = response.json().get("models") or []
    return [{"name": m.get("name"), "size_vram": m.get("size_vram") or 0} for m in models]


def _parse_vm_stat_pages(line: str) -> int | None:
    """解析 `vm_stat` 单行数字，去掉尾随点号与空白；无法解析返回 None。

    `vm_stat` 输出形如 `Pages free:                        123456.`，数字后带尾随点。
    """
    match = re.search(r":\s*([\d.]+)\s*$", line)
    if not match:
        return None
    token = match.group(1).rstrip(".")
    try:
        return int(token)
    except ValueError:
        return None


def system_available_memory_bytes() -> int | None:
    """返回系统近似可用内存（字节）；不可用时返回 None（探针能力不可用）。

    故意不引入 psutil：本机只是资源探针的「能力可用性」信号，近似值已足够裁决 9B
    并发上限，精确显存占用交给 Ollama `/api/ps` 的 `size_vram`。任何读取失败都必须
    返回 None 并由 `ResourceProbe` 统一降级为单 Worker，因此此处用窄 try/except 兜住
    异常、**绝不冒泡**。

    - Linux：解析 `/proc/meminfo` 的 `MemAvailable:`（单位为 kB，乘 1024 得字节）。
    - macOS（darwin）：解析 `vm_stat` 的 free + speculative + inactive 页数 × 页大小。
    - 其他平台：返回 None。
    """
    if sys.platform == "linux":
        with contextlib.suppress(OSError, ValueError), open(
            "/proc/meminfo", encoding="utf-8"
        ) as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    value = line.split()[1]  # kB
                    return int(value) * 1024
        return None

    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["vm_stat"],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_SECONDS,
                check=False,
            )
            if proc.returncode != 0:
                return None
            page_size: int | None = None
            free_pages: int | None = None
            speculative_pages: int | None = None
            inactive_pages: int | None = None
            for line in proc.stdout.splitlines():
                if "page size of" in line:
                    # 形如 "Mach Virtual Memory Statistics: (page size of 16384 bytes)"
                    m = re.search(r"page size of\s+(\d+)\s+bytes", line)
                    if m:
                        page_size = int(m.group(1))
                elif line.startswith("Pages free:"):
                    free_pages = _parse_vm_stat_pages(line)
                elif line.startswith("Pages speculative:"):
                    speculative_pages = _parse_vm_stat_pages(line)
                elif line.startswith("Pages inactive:"):
                    inactive_pages = _parse_vm_stat_pages(line)
            if (
                page_size is None
                or free_pages is None
                or speculative_pages is None
                or inactive_pages is None
            ):
                return None
            return (free_pages + speculative_pages + inactive_pages) * page_size
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    return None


@dataclass(frozen=True)
class ResourceSnapshot:
    """一次资源探针的只读快照（冻结，便于在并发调度中安全传递与比较）。"""

    available_memory_bytes: int
    model_footprint_bytes: int
    loaded_model_count: int


class ResourceProbeUnavailable(Exception):
    """探针拿不到可用内存或已加载模型占用时抛出。

    调用方据此统一降级为单 Worker 并发 `RESOURCE_PROBE_FAILED`，而非用猜测值裁决。
    """


class ResourceProbe:
    """全局资源探针：裁决 9B 级 fast 模型的并行 Worker 并发上限。

    只从既有 `get_available_models()` 与 Ollama `/api/ps` 读取，保留至少 20% 系统
    余量。三个 provider 默认走模块级实现，允许注入以便离线测试。调度交给模块级
    全局单例 `_GLOBAL_WORKER_SCHEDULER`，保证多 Task 共享同一额度、按任务公平轮转。
    """

    MARGIN_FRACTION = RESOURCE_MARGIN_FRACTION

    def __init__(self, *, available_models_provider=None, loaded_models_provider=None,
                 memory_provider=None, scheduler=None):
        # provider 默认分别为模块级既有能力；允许注入以便离线测试。
        self._available_models = available_models_provider or get_available_models
        self._loaded_models = loaded_models_provider or read_loaded_models
        self._memory = memory_provider or system_available_memory_bytes
        self._scheduler = scheduler or _GLOBAL_WORKER_SCHEDULER

    def snapshot(self) -> ResourceSnapshot:
        """采集一次资源快照；任一探针环节不可用即抛 `ResourceProbeUnavailable`。

        本机 `/api/ps` 当前无驻留模型时，`footprint` 为 0 会走到
        `ResourceProbeUnavailable` → 单 Worker。这是**诚实降级**而非缺陷：
        Task02 门禁已实测本机 `/api/ps == {"models": []}`，即无模型驻留时无法得知
        占用，宁可保守地降为单 Worker，也不凭空假设可并发。
        """
        try:
            self._available_models()  # 任一异常 → 探针不可用
        except Exception as exc:  # 含 httpx.HTTPError / json 解析等
            raise ResourceProbeUnavailable(f"available models probe failed: {exc}") from exc
        try:
            loaded = self._loaded_models()  # 任一异常 → 探针不可用
        except Exception as exc:
            raise ResourceProbeUnavailable(f"loaded models probe failed: {exc}") from exc

        available = self._memory()
        if available is None or available <= 0:
            raise ResourceProbeUnavailable("system available memory unavailable or non-positive")

        footprint = max([m.get("size_vram") or 0 for m in loaded], default=0)
        if footprint <= 0:
            # 当前无模型驻留、无法得知占用 → 诚实降级为单 Worker，不是缺陷。
            raise ResourceProbeUnavailable("no loaded model footprint known")

        return ResourceSnapshot(available, footprint, len(loaded))

    def max_safe_workers(self) -> tuple[int, str | None]:
        """返回 (安全并发上限, 错误码)。

        正常：保留 MARGIN_FRACTION 余量后，按可用内存 ÷ 单模型显存占用取整，至少 1。
        探针不可用：返回 (1, "RESOURCE_PROBE_FAILED")，由调用方发出可见事件。
        """
        try:
            snap = self.snapshot()
        except ResourceProbeUnavailable:
            return 1, "RESOURCE_PROBE_FAILED"
        usable = snap.available_memory_bytes * (1 - self.MARGIN_FRACTION)
        raw = int(usable // snap.model_footprint_bytes)
        return max(1, raw), None

    def arbitrate(self, task_id: str, requested: int) -> tuple[int, str | None]:
        """裁决某 Task 实际可领用的 Worker 数 (granted, code)。

        cap 由 `max_safe_workers` 给出；具体额度交给全局调度器公平轮转，保证两个
        Task 同时运行时不各自独立估算内存。
        """
        cap, code = self.max_safe_workers()
        granted = self._scheduler.acquire(task_id, requested, cap)
        return granted, code

    def release(self, task_id: str) -> None:
        """释放该 task 占用的 Worker 额度。"""
        self._scheduler.release(task_id)


class _GlobalWorkerScheduler:
    """单进程内全局共享的 9B 并发额度调度器（Spec027：两个 Task 同时运行时不各自
    独立估算内存，额度必须全局共享并按任务公平轮转）。

    所有方法在 `threading.Lock` 内执行，避免并发领用时的「读-判断-写」竞态。
    任一 Task 最多拿全局上限的一半（cap // 2），保证两个 Task 均分。同一 task 重复
    acquire 会累加额度（调用方负责在任务结束时 release）。
    """

    def __init__(self) -> None:
        self._grants: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, task_id: str, requested: int, cap: int) -> int:
        with self._lock:
            per_task = max(1, cap // 2)  # 全局上限，任一 Task 最多拿一半，保证均分
            used = sum(self._grants.values())
            grant = max(0, min(int(requested), per_task, cap - used))
            self._grants[task_id] = self._grants.get(task_id, 0) + grant
            return grant

    def release(self, task_id: str) -> None:
        with self._lock:
            self._grants.pop(task_id, None)

    def in_use(self) -> int:
        with self._lock:
            return sum(self._grants.values())


# 模块级全局单例：单进程内所有 Research Task 共享同一并发额度。
_GLOBAL_WORKER_SCHEDULER = _GlobalWorkerScheduler()
