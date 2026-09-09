"""Single source of truth for reading and writing the settings document.

The persisted ``data/article_settings.json`` document mixes two configuration
domains: the article assistant and paper discovery.  The two domains are split
into their own Pydantic models (:class:`ArticleAssistantSettings` and
:class:`PaperDiscoverySettings`) and re-aggregated here as the combined
:class:`ArticleSettings` so the HTTP contract (``GET/PUT /api/agent/settings``)
stays unchanged.

This module is the *only* place that reads or writes the document.  Writes are
read-modify-write and atomic: the existing document is read first, the incoming
domain fields are merged on top, every unknown key (and any other domain's
fields) is preserved, and the result is published with a temporary file plus
``os.replace`` so a crash can never leave a half-written settings file that
silently drops the other domain's configuration.
"""

import json
import os
from pathlib import Path

from backend.app.platform.config import BASE_DIR
from backend.app.platform.settings.article_assistant_settings import ArticleAssistantSettings
from backend.app.platform.settings.paper_discovery_settings import PaperDiscoverySettings


class ArticleSettings(ArticleAssistantSettings, PaperDiscoverySettings):
    """Combined article-assistant + paper-discovery settings.

    This aggregate is the public type used by services and routes.  It keeps the
    flat field layout of the legacy model so ``model_dump`` / ``model_validate``
    and the HTTP request/response bodies are byte-compatible.
    """


SETTINGS_PATH = BASE_DIR / "data" / "article_settings.json"


def _env_bool(name: str) -> bool | None:
    """Parse a tri-state boolean environment override; unset yields None."""
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_article_settings() -> ArticleSettings:
    settings: ArticleSettings
    if SETTINGS_PATH.exists():
        settings = ArticleSettings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
    else:
        raw = os.getenv("ARTICLE_SETTINGS_JSON", "")
        if raw:
            settings = ArticleSettings.model_validate(json.loads(raw))
        else:
            settings = ArticleSettings(
                article_search_urls=[url for url in os.getenv("ARTICLE_SEARCH_URLS", "").split(",") if url],
                article_download_urls=[url for url in os.getenv("ARTICLE_DOWNLOAD_URLS", "").split(",") if url],
                article_download_dir=os.getenv("ARTICLE_DOWNLOAD_DIR", str(BASE_DIR / "data" / "articles")),
            )

    # Paper discovery can be configured independently of the legacy settings
    # JSON. Environment values override persisted values when supplied.
    env_values = {
        "paper_discovery_dblp_enabled": _env_bool("PAPER_DISCOVERY_DBLP_ENABLED"),
        "paper_discovery_db_path": os.getenv("PAPER_DISCOVERY_DB_PATH"),
        "paper_discovery_default_years": os.getenv("PAPER_DISCOVERY_DEFAULT_YEARS"),
        "paper_discovery_search_limit": os.getenv("PAPER_DISCOVERY_SEARCH_LIMIT"),
        "paper_discovery_max_search_limit": os.getenv("PAPER_DISCOVERY_MAX_SEARCH_LIMIT"),
        "paper_discovery_candidate_pool": os.getenv("PAPER_DISCOVERY_CANDIDATE_POOL"),
        "paper_discovery_search_ttl_seconds": os.getenv("PAPER_DISCOVERY_SEARCH_TTL_SECONDS"),
        "paper_discovery_request_timeout_seconds": os.getenv(
            "PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS"
        ),
        "paper_discovery_allowed_hosts": (
            [value.strip() for value in os.getenv("PAPER_DISCOVERY_ALLOWED_HOSTS", "").split(",") if value.strip()]
            if os.getenv("PAPER_DISCOVERY_ALLOWED_HOSTS") is not None
            else None
        ),
    }
    overrides = {key: value for key, value in env_values.items() if value is not None}
    return ArticleSettings.model_validate(settings.model_dump() | overrides) if overrides else settings


def _read_document(path: Path) -> dict:
    """Return the persisted document as a dict, or an empty dict if absent."""
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def save_article_settings(settings: ArticleSettings) -> None:
    """Persist ``settings`` via an atomic read-modify-write.

    The current document is read first so that fields owned by the other domain
    and any unknown keys survive the write.  The merged document is then
    published atomically (temporary file + ``os.replace``) to avoid tearing the
    file and silently dropping configuration.
    """
    document_path = SETTINGS_PATH
    document_path.parent.mkdir(parents=True, exist_ok=True)

    merged = _read_document(document_path)
    merged.update(settings.model_dump())

    payload = json.dumps(merged, indent=2, ensure_ascii=False)
    temporary = document_path.with_name(f"{document_path.name}.tmp.{os.getpid()}")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, document_path)
    finally:
        if temporary.exists():
            temporary.unlink()
