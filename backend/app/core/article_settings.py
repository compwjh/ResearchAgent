import json
import os
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.core.config import BASE_DIR

SETTINGS_PATH = BASE_DIR / "data" / "article_settings.json"


class ArticleSettings(BaseModel):
    article_metadata_sources: List[str] = Field(default_factory=lambda: ["crossref", "openalex"])
    article_max_candidates_per_source: int = 20
    article_retry_count: int = 2
    article_retry_backoff_seconds: float = 1
    article_pdf_probe_timeout_seconds: int = 10
    article_search_urls: List[str] = Field(default_factory=list)
    article_download_urls: List[str] = Field(default_factory=list)
    article_download_dir: str = str(BASE_DIR / "data" / "articles")
    article_auto_download: bool = False
    article_match_threshold: float = 0.90
    article_max_file_size_mb: int = 100
    article_request_timeout_seconds: int = 30
    article_login_timeout_seconds: int = 300
    # Paper-discovery settings live here until the dedicated settings endpoint
    # is introduced.  Keeping them in the existing settings object avoids a
    # second configuration loader while allowing the search service to be
    # configured in tests and by the application.
    paper_discovery_search_limit: int = 20
    paper_discovery_max_search_limit: int = 100
    paper_discovery_candidate_pool: int = 200
    paper_discovery_search_ttl_seconds: int = 86400
    paper_discovery_db_path: str = str(BASE_DIR / "data" / "paper_search" / "state.sqlite3")
    paper_discovery_default_years: int = 5
    paper_discovery_request_timeout_seconds: float = 20.0
    # Fixed server-side host allowlist for paper-discovery downloads.  It is
    # intentionally independent of candidate.pdf_url: snapshots are external
    # data and must never expand the set of permitted download origins.
    paper_discovery_allowed_hosts: List[str] = Field(default_factory=list)

    @field_validator("article_search_urls", "article_download_urls")
    @classmethod
    def validate_urls(cls, urls: List[str]) -> List[str]:
        for url in urls:
            if not url.startswith(("http://", "https://")):
                raise ValueError("文章来源地址必须使用 HTTP(S)")
        return urls

    @field_validator("article_max_candidates_per_source")
    @classmethod
    def validate_candidate_count(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("每个来源候选数必须在 1 到 100 之间")
        return value

    @field_validator(
        "paper_discovery_search_limit", "paper_discovery_max_search_limit", "paper_discovery_candidate_pool",
        "paper_discovery_search_ttl_seconds", "paper_discovery_default_years",
    )
    @classmethod
    def validate_paper_discovery_positive(cls, value: int) -> int:
        if isinstance(value, bool) or value < 1:
            raise ValueError("论文发现配置必须为正整数")
        return value

    @field_validator("paper_discovery_request_timeout_seconds")
    @classmethod
    def validate_paper_discovery_timeout(cls, value: float) -> float:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("论文发现请求超时必须为正数")
        return value

    @field_validator("paper_discovery_allowed_hosts")
    @classmethod
    def validate_paper_discovery_allowed_hosts(cls, values: List[str]) -> List[str]:
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("论文下载 allowlist 必须为非空主机名")
        return [value.strip() for value in values]

    @model_validator(mode="after")
    def validate_paper_discovery_limits(self):
        if self.paper_discovery_search_limit > self.paper_discovery_max_search_limit:
            raise ValueError("论文发现默认 limit 不能超过最大 limit")
        if self.paper_discovery_max_search_limit > 100:
            raise ValueError("论文发现最大 limit 不能超过 100")
        return self


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
        "paper_discovery_db_path": os.getenv("PAPER_DISCOVERY_DB_PATH"),
        "paper_discovery_default_years": os.getenv("PAPER_DISCOVERY_DEFAULT_YEARS"),
        "paper_discovery_search_limit": os.getenv("PAPER_DISCOVERY_SEARCH_LIMIT"),
        "paper_discovery_max_search_limit": os.getenv("PAPER_DISCOVERY_MAX_SEARCH_LIMIT"),
        "paper_discovery_candidate_pool": os.getenv("PAPER_DISCOVERY_CANDIDATE_POOL"),
        "paper_discovery_search_ttl_seconds": os.getenv("PAPER_DISCOVERY_SEARCH_TTL_SECONDS"),
        "paper_discovery_request_timeout_seconds": os.getenv("PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS"),
        "paper_discovery_allowed_hosts": (
            [value.strip() for value in os.getenv("PAPER_DISCOVERY_ALLOWED_HOSTS", "").split(",") if value.strip()]
            if os.getenv("PAPER_DISCOVERY_ALLOWED_HOSTS") is not None else None
        ),
    }
    overrides = {key: value for key, value in env_values.items() if value is not None}
    return ArticleSettings.model_validate(settings.model_dump() | overrides) if overrides else settings


def save_article_settings(settings: ArticleSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
