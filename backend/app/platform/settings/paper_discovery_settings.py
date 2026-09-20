"""Paper-discovery domain settings.

This model owns only the paper-discovery search / download configuration.  It
lives in its own module so the discovery domain can evolve independently of the
article-retrieval domain, while the combined :class:`ArticleSettings` keeps the
persisted JSON document and HTTP contract intact.
"""

from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.platform.config import BASE_DIR

# 搜索快照（search_jobs.expires_at）的默认有效期。
# 研究任务从检索到用户确认全文获取往往跨若干天：原 24h 会让「隔天点确认」必然
# 撞上 SEARCH_EXPIRED，导入桥在下载前就失败。7 天覆盖典型的一周研究周期；
# 仍可用 PAPER_DISCOVERY_SEARCH_TTL_SECONDS 覆盖。
DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS = 7 * 24 * 60 * 60


class PaperDiscoverySettings(BaseModel):
    paper_discovery_search_limit: int = 20
    paper_discovery_max_search_limit: int = 100
    paper_discovery_candidate_pool: int = 200
    paper_discovery_search_ttl_seconds: int = DEFAULT_PAPER_DISCOVERY_SEARCH_TTL_SECONDS
    paper_discovery_db_path: str = str(BASE_DIR / "data" / "paper_search" / "state.sqlite3")
    paper_discovery_default_years: int = 5
    paper_discovery_request_timeout_seconds: float = 20.0
    paper_discovery_allowed_hosts: List[str] = Field(default_factory=list)
    # DBLP now answers its publication API with a bot challenge page instead of
    # JSON, so every request fails as DBLP_INVALID_RESPONSE.  The source stays
    # wired but disabled until the upstream serves JSON again; setting the
    # environment variable to a truthy value re-enables it without a code change.
    paper_discovery_dblp_enabled: bool = False

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
