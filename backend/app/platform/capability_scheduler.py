"""模型能力每日定时探测调度器（spec-035 Bug3）。

FastAPI lifespan 启动一个 asyncio 后台任务：启动先跑一轮全量探测，
之后每 24h 一轮。每轮对 ``GET /api/tags`` 的全部模型依次执行
``probe_reasoning_capabilities`` 并 upsert 入库；单模型探测失败
（unknown）不覆盖库中已有的有效结果（沿用 spec-026 B16 契约），
也不影响其它模型。

探测是同步阻塞 httpx 调用，整轮通过 ``asyncio.to_thread`` 下放线程，
不阻塞事件循环。调度器任何异常都只记录、不终止循环、不阻塞服务启动。
"""

import asyncio

from backend.app.platform.capability_store import upsert_capabilities
from backend.app.platform.ollama import probe_reasoning_capabilities

PROBE_INTERVAL_SECONDS = 24 * 60 * 60.0


def _list_models() -> list[str]:
    """枚举 Ollama 全部模型名；失败返回空列表（本轮空转）。"""
    import httpx

    from backend.app.platform.config import OLLAMA_BASE_URL

    try:
        response = httpx.get(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=10, trust_env=False
        )
        models = response.json().get("models") or []
    except (httpx.HTTPError, ValueError, TypeError):
        return []
    names = []
    for item in models:
        name = str((item or {}).get("name") or "").strip()
        if name:
            names.append(name)
    return names


def run_capability_sweep() -> int:
    """同步执行一轮全量探测并入库，返回成功写入的模型数。"""
    updated = 0
    for model in _list_models():
        capabilities = probe_reasoning_capabilities(model)
        if capabilities.source == "unknown":
            # 探测失败（Ollama 离线 / 模型冷启动）不得覆盖库中旧值。
            continue
        upsert_capabilities(
            capabilities.model,
            supported_efforts=capabilities.supported_efforts,
            default_effort=capabilities.default_effort,
            source=capabilities.source,
            evidence=dict(capabilities.evidence_ids or {}),
            probed_at=capabilities.cached_at,
        )
        updated += 1
    return updated


async def capability_probe_loop(
    *, interval_seconds: float = PROBE_INTERVAL_SECONDS
) -> None:
    """常驻循环：启动先探测一轮，之后每 interval_seconds 一轮。"""
    while True:
        try:
            updated = await asyncio.to_thread(run_capability_sweep)
            print(f"[capabilities] 探测完成：{updated} 个模型已更新")
        except Exception as error:  # 调度器永不因单轮失败退出
            print(f"[capabilities] 探测轮失败（已忽略）：{error}")
        await asyncio.sleep(interval_seconds)


_task: asyncio.Task | None = None


def start_capability_scheduler() -> None:
    """在 lifespan 中启动调度任务；重复调用幂等。"""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(capability_probe_loop())


async def stop_capability_scheduler() -> None:
    """在 lifespan 关闭时取消调度任务。"""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None
