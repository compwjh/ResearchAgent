import json
import os
import time
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from backend.app.api.schemas import (
    ChatRequest,
    ConferenceUpdateRequest,
    KBAskRequest,
    KBReindexRequest,
    PaperImportBatchRequest,
    PaperImportBatchResponse,
    PaperImportItemActionRequest,
    PaperImportItemLoginResponse,
    PaperImportRequest,
    PaperImportResponse,
    PaperAcceptedRequest,
    PaperSearchRequest,
)
from backend.app.agents.article_agent import build_task
from backend.app.platform.settings.settings_repository import (
    ArticleSettings,
    load_article_settings,
    save_article_settings,
)
from backend.app.core.config import BASE_DIR, CHUNK_V2_LLM_MODEL, KB_MAX_UPLOAD_MB, KB_PAPERS_DIR, MODEL_NAME
from backend.app.observability import end_trace, flush, record_ollama_generation, start_trace, utc_now
from backend.app.domain.article import ArticleCandidate, ArticleTask
from backend.app.domain.paper_discovery import SearchSession
from backend.app.services.article_download import download_article, probe_pdf_url
from backend.app.services.article_search import search_articles
from backend.app.services.download_paper_skill import SKILL_NAME, build_skill_plan, download_under_skill, skill_status
from backend.app.services.kb import (
    CHUNKERS,
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_INDEXING,
    build_prompt,
    citation_payloads,
    count_points,
    delete_paper,
    ensure_collection,
    get_client,
    get_paper,
    hybrid_search,
    index_paper,
    index_paper_chunker,
    load_papers,
    new_record,
    remove_paper,
    run_index_task_sync,
    save_upload,
    submit_index_task,
    update_chunker_state,
    upsert_paper,
)
from backend.app.services.kb.embed import embed_texts
from backend.app.services.kb.retrieve import reranker_health
from backend.app.services.kb.store import resolve_paper_path
from backend.app.services.ollama import create_chat_model, get_available_models, run_chat
from backend.app.services.dblp_publication_source import DBLPPublicationSource
from backend.app.services.openalex_enricher import OpenAlexEnricher
from backend.app.services.paper_discovery_search import PaperDiscoverySearchError, PaperDiscoverySearchService
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
from backend.app.services.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    PaperDownloadError,
)
from backend.app.services.paper_import import (
    KB_IMPORT_FAILED,
    PAPER_ALREADY_EXISTS,
    PaperImportError,
    import_candidate,
    safe_import_error_code,
    safe_import_error_message,
)
from backend.app.services.paper_import_batch_service import (
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.services.paper_import_batch_store import PaperImportBatchStore
from backend.app.services.paper_browser_manager import BrowserManagerError, PaperBrowserManager
from backend.app.services.task_store import TaskStore

router = APIRouter()
article_tasks = TaskStore()
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
