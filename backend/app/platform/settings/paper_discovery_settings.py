"""Paper-discovery domain settings.

This model owns only the paper-discovery search / download configuration.  It
lives in its own module so the discovery domain can evolve independently of the
article-retrieval domain, while the combined :class:`ArticleSettings` keeps the
persisted JSON document and HTTP contract intact.
"""

from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.core.config import BASE_DIR


class PaperDiscoverySettings(BaseModel):
    paper_discovery_search_limit: int = 20
    paper_discovery_max_search_limit: int = 100
    paper_discovery_candidate_pool: int = 200
    paper_discovery_search_ttl_seconds: int = 86400
    paper_discovery_db_path: str = str(BASE_DIR / "data" / "paper_search" / "state.sqlite3")
    paper_discovery_default_years: int = 5
    paper_discovery_request_timeout_seconds: float = 20.0
    paper_discovery_allowed_hosts: List[str] = Field(default_factory=list)

    # Fixed server-side host allowlist for paper-discovery downloads.  It is
    # intentionally independent of candidate.pdf_url: snapshots are external
    # data and must never expand the set of permitted download origins.
    @field_validator(
        "paper_discovery_search_limit",
        "paper_discovery_max_search_limit",
        "paper_discovery_candidate_pool",
        "paper_discovery_search_ttl_seconds",
        "paper_discovery_default_years",
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
