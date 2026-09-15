"""线上模型注册表（spec-035 Task02）。

从 `.env` 的 `ONLINE_MODELS` 解析线上模型清单，注册为 `OnlineModelEntry`。
解析严格按 spec「解析规则」：去空白、非法跳过 + warning、provider 小写、
缺 Key 不注册、缺地址用内置默认表、协议仅 https 或 loopback http、重复保留首个、
绝不 fail-fast。本模块不发起任何网络请求，不实例化任何模型客户端。
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# 轻量探测结果的进程内缓存：{entry_id: (时间戳, status)}，TTL 60s。
# 同 id 在 TTL 内命中直接返回，避免重复消耗外发请求。
_PROBE_CACHE: dict[str, tuple[float, str]] = {}
_PROBE_TTL_SECONDS = 60.0

# 内置默认地址表（provider 小写）
DEFAULT_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
}


@dataclass
class OnlineModelEntry:
    """线上模型注册表项。

    `id` 为 `provider:model`，即前端 value 与请求体模型名；
    `api_key` 绝不出现在任何日志或 HTTP 响应中。
    """

    id: str
    provider: str
    model: str
    display_name: str
    base_url: str
    api_key: str
    source: str = "online"


def get_online_models(raw: str | None = None) -> list[OnlineModelEntry]:
    """解析 `ONLINE_MODELS` 为已注册线上模型列表。

    默认从 `os.getenv("ONLINE_MODELS")` 实时读取（便于测试与运行时注入）；
    也可传入 `raw` 字符串直接解析。任何非法项都跳过并 warning，绝不 fail-fast。
    """
    if raw is None:
        raw = os.getenv("ONLINE_MODELS", "")
    if not raw:
        return []

    entries: list[OnlineModelEntry] = []
    seen_ids: set[str] = set()

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue  # 去空白、忽略空项（静默）

        if item.count(":") != 1:
            logger.warning(
                "Skipping invalid ONLINE_MODELS entry (need exactly one ':'): %r",
                item,
            )
            continue

        provider_raw, model = item.split(":", 1)
        provider = provider_raw.strip().lower()
        model = model.strip()
        if not provider or not model:
            logger.warning(
                "Skipping invalid ONLINE_MODELS entry (empty provider or model): %r",
                item,
            )
            continue

        provider_upper = provider.upper().replace("-", "_")
        # 缺 API_KEY → 不注册（对应 spec Q9：不展示），静默。
        api_key = os.getenv(f"{provider_upper}_API_KEY", "").strip()
        if not api_key:
            continue

        # 缺 BASE_URL → 用内置默认表；未知 provider 且无地址 → 跳过 + warning。
        base_url = os.getenv(f"{provider_upper}_BASE_URL", "").strip()
        if not base_url:
            base_url = DEFAULT_BASE_URLS.get(provider, "")
        if not base_url:
            logger.warning(
                "Skipping online model %s: no %s_BASE_URL and provider not in default table",
                f"{provider}:{model}",
                provider_upper,
            )
            continue

        # 协议仅允许 https:// 或 loopback http://（SSRF 防护）。
        if not _is_allowed_base_url(base_url):
            logger.warning(
                "Skipping online model %s: BASE_URL scheme/host not allowed "
                "(only https:// or loopback http://): %s",
                f"{provider}:{model}",
                base_url,
            )
            continue

        entry_id = f"{provider}:{model}"
        if entry_id in seen_ids:
            logger.warning("Skipping duplicate online model: %s", entry_id)
            continue
        seen_ids.add(entry_id)

        entries.append(
            OnlineModelEntry(
                id=entry_id,
                provider=provider,
                model=model,
                display_name=entry_id,
                base_url=base_url,
                api_key=api_key,
                source="online",
            )
        )

    return entries


def get_online_model(model_id: str) -> OnlineModelEntry | None:
    """按 `id`（`provider:model`）查询单个线上模型，未注册返回 None。"""
    for entry in get_online_models():
        if entry.id == model_id:
            return entry
    return None


def is_online_model(name: str) -> bool:
    """仅查线上注册表判断 `name` 是否为已注册线上模型。

    不调用 Ollama、不发起任何网络请求，只查本地环境变量解析出的
    `ONLINE_MODELS` 注册表（`get_online_models`）。供路由校验时为线上模型
    与模块级 `get_available_models()`（本地）取并集短路，从而保留各路由模块
    级 `get_available_models` 这一测试 patch 目标。
    """
    if not name:
        return False
    try:
        return get_online_model(name) is not None
    except Exception:
        logger.debug("online registry lookup failed for %r", name)
        return False


def is_model_available(name: str) -> bool:
    """判断模型是否可用：**本地 ∪ 线上** 并集。

    内部复用 `get_available_models()`（本地）与 `get_online_model()`（线上），
    两侧各自独立尝试，**单侧失败互不影响**：

    - 线上注册表命中即返回 `True`（即使 Ollama 不可达）；
    - Ollama 不可达时仍可通过线上注册表认出线上模型，反之亦然；
    - 注册表为空 / 未配置时，仍可通过本地认出本地模型。

    不发起任何网络请求（线上侧仅查本地注册表；Ollama 侧仅在需要时枚举本地模型）。
    """
    if not name:
        return False

    # 线上侧：查本地注册表（不发起网络请求）。异常隔离，避免影响本地侧判断。
    try:
        if get_online_model(name) is not None:
            return True
    except Exception:
        logger.debug("online registry check failed for %r", name)

    # 本地侧：枚举本地可用模型。函数内延迟 import，避免与 ollama 形成循环依赖
    # （ollama.create_chat_model 也会延迟 import 本模块的 get_online_model）。
    # Ollama 不可达等异常隔离：线上侧已先判定，本地失败不影响线上结论。
    try:
        from backend.app.platform.ollama import get_available_models
        return name in set(get_available_models())
    except Exception:
        logger.debug("ollama get_available_models failed for %r", name)
        return False


def probe_online_model(entry: "OnlineModelEntry", *, timeout: float = 8.0) -> str:
    """对单个线上模型做轻量连通性探测（`max_tokens=1`）。

    请求 `POST {base_url}/chat/completions`：
    - 成功（2xx）→ `\"ready\"`；
    - 超时 / 非 2xx / 异常 → `\"unreachable\"`。
    内嵌 60s 内存缓存，同 `id` 命中直接返回，不再发请求，避免重复消耗。

    **绝不抛异常**（保证调用方 `/api/models` 始终 200），也**绝不记录 Key 或响应体**
    （日志只记 provider + 状态码）。
    """
    now = time.monotonic()
    cached = _PROBE_CACHE.get(entry.id)
    if cached is not None:
        cached_at, cached_status = cached
        if now - cached_at < _PROBE_TTL_SECONDS:
            return cached_status

    url = entry.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": entry.model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {entry.api_key}"}
    status = "unreachable"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=headers)
        code = resp.status_code
        status = "ready" if 200 <= code < 300 else "unreachable"
        # 仅记 provider + 状态码，绝不记 Key、绝不记响应体
        logger.info(
            "online model probe: provider=%s http_status=%s", entry.provider, code
        )
    except httpx.TimeoutException:
        status = "unreachable"
        logger.info("online model probe: provider=%s timeout", entry.provider)
    except Exception:
        status = "unreachable"
        logger.info("online model probe: provider=%s error", entry.provider)
    _PROBE_CACHE[entry.id] = (now, status)
    return status


def _is_allowed_base_url(url: str) -> bool:
    """仅允许 https:// 或 loopback http://（SSRF 防护）。"""
    if url.startswith("https://"):
        return True
    if url.startswith("http://"):
        host = url[len("http://"):].split("/", 1)[0].split(":", 1)[0].lower()
        return host in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1")
    return False
