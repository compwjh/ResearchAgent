
import httpx
from fastapi import APIRouter

from backend.app.core.config import MODEL_NAME
from backend.app.platform.settings.settings_repository import (
    load_article_settings,
)
from backend.app.services.ollama import get_available_models

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


from backend.app.api.common import *  # noqa: F401,F403


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


# ==================== 论文检索（spec-015 / Task03）====================

