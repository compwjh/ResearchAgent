import json
import os
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, field_validator

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


def load_article_settings() -> ArticleSettings:
    if SETTINGS_PATH.exists():
        return ArticleSettings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
    raw = os.getenv("ARTICLE_SETTINGS_JSON", "")
    if raw:
        return ArticleSettings.model_validate(json.loads(raw))
    return ArticleSettings(
        article_search_urls=[url for url in os.getenv("ARTICLE_SEARCH_URLS", "").split(",") if url],
        article_download_urls=[url for url in os.getenv("ARTICLE_DOWNLOAD_URLS", "").split(",") if url],
        article_download_dir=os.getenv("ARTICLE_DOWNLOAD_DIR", str(BASE_DIR / "data" / "articles")),
    )


def save_article_settings(settings: ArticleSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
