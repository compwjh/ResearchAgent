
import httpx
from fastapi import APIRouter

from backend.app.api.common import *  # noqa: F401,F403
from backend.app.platform.config import MODEL_NAME, WARMUP_ENABLED
from backend.app.platform.ollama import get_available_models
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)
from backend.app.platform.warmup import is_warmup_started, readiness_snapshot

router = APIRouter()
article_settings = load_article_settings()
paper_discovery_store = None
paper_discovery_store_path = None
paper_discovery_search_service = None
paper_import_batch_service = None
paper_import_batch_store_path = None
paper_browser_manager = None
# Sessions are keyed by import item, so a resume request can never borrow a
# different item's authenticated browser context.
paper_browser_sessions = {}


@router.get("/health")
def health() -> dict:
    try:
        models = get_available_models()
    except httpx.HTTPError:
        models = []
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "models": models,
        "paper_discovery_enabled": _paper_discovery_enabled(),
    }


@router.get("/ready")
def api_ready() -> dict:
    """首屏就绪探针：恒 200，预热任何异常也绝不返回非 200（fail-open）。

    返回各预热项 ``{status, elapsed_ms, error}`` 与整体 ``ready`` 布尔：
    - ``ready`` 为 True 表示服务可对外提供（warmup 未启用/未启动，或所有预热项已达终态）；
    - 预热项仍在进行（loading）时 ``ready`` 为 False，但接口依旧 200。
    """
    snapshot = readiness_snapshot()
    if not WARMUP_ENABLED or not is_warmup_started():
        # 尚未开始预热（如 lifespan 未触发）或已禁用——服务本身可用。
        overall_ready = True
    else:
        overall_ready = all(item["status"] in ("ready", "failed") for item in snapshot.values())
    return {"ready": overall_ready, "warmup": snapshot}


# ==================== 论文检索（spec-015 / Task03）====================
