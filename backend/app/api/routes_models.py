"""GET /api/models 端点（spec-035 Task04）。

返回「端侧模型 / 线上模型」分组结构；`?probe=1` 时对已配置线上模型做
轻量连通性探测（max_tokens=1，串行 + 15s 总耗时上限，单项失败只降级该项）。

绝不返回非 200：Ollama 不可达 → local 组为空数组；无线上配置 → online 组为空数组；
探查异常被 `probe_online_model` 内部吞掉，整体仍 200。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from backend.app.platform import config
from backend.app.platform.model_catalog import (
    OnlineModelEntry,
    get_online_models,
    probe_online_model,
)
from backend.app.platform.ollama import REASONING_EFFORTS, get_available_models

router = APIRouter()

LOCAL_LABEL = "端侧模型"
ONLINE_LABEL = "线上模型"
LOCAL_STATUS = "ready"
# 探测总耗时上限：超出后剩余线上模型直接置 unknown，不阻塞页面加载
_PROBE_TOTAL_BUDGET_SECONDS = 15.0
_PROBE_PER_MODEL_TIMEOUT = 8.0


def _build_local_models() -> list[dict]:
    """端侧模型组：status 恒 ready。Ollama 不可达等异常 → 空组（仍 200）。"""
    try:
        names = get_available_models()
    except Exception:
        names = []
    models: list[dict] = []
    for name in names:
        models.append(
            {
                "id": name,
                "name": name,
                "source": "local",
                "provider": None,
                "display_name": name,
                "current": False,  # 由调用方统一回填
                "status": LOCAL_STATUS,
                "capabilities": {"reasoning_efforts": list(REASONING_EFFORTS)},
            }
        )
    return models


def _build_online_models(probe: bool, start: float) -> list[dict]:
    """线上模型组：capabilities.reasoning_efforts 恒 null。

    仅当 `probe` 为 True 且仍在总耗时预算内时才触发真实探测；否则 status=unknown。
    """
    entries: list[OnlineModelEntry] = get_online_models()
    models: list[dict] = []
    for entry in entries:
        if probe and (time.monotonic() - start) <= _PROBE_TOTAL_BUDGET_SECONDS:
            status = probe_online_model(entry, timeout=_PROBE_PER_MODEL_TIMEOUT)
        else:
            status = "unknown"
        models.append(
            {
                "id": entry.id,
                "name": entry.model,
                "source": "online",
                "provider": entry.provider,
                "display_name": entry.display_name,
                "current": False,
                "status": status,
                "capabilities": {"reasoning_efforts": None},
            }
        )
    return models


def _resolve_current(all_models: list[dict]) -> str | None:
    """当前默认模型取 config.MODEL_NAME；不在可用列表内则回退第一个可用；都为空则 None。"""
    if not all_models:
        return None
    candidate = config.MODEL_NAME
    if any(m["id"] == candidate for m in all_models):
        return candidate
    return all_models[0]["id"]


@router.get("/models")
def list_models(request: Request) -> dict:
    probe = request.query_params.get("probe") == "1"
    start = time.monotonic()
    local = _build_local_models()
    online = _build_online_models(probe, start)
    all_models = local + online
    current_id = _resolve_current(all_models)
    for m in all_models:
        m["current"] = m["id"] == current_id
    return {
        "current": current_id,
        "groups": [
            {"source": "local", "label": LOCAL_LABEL, "models": local},
            {"source": "online", "label": ONLINE_LABEL, "models": online},
        ],
    }
