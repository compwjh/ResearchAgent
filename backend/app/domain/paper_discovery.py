from dataclasses import dataclass, field
from typing import List, Optional
@dataclass
class ConferenceSource:
    conference_id: str
    name: str
    short_name: str
    dblp_stream: str
    venue_aliases: List[str] = field(default_factory=list)
    built_in: bool = False
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    discovery_routes: List[dict] = field(default_factory=list)
@dataclass
class SearchSession:
    search_id: str
    query: str
    expires_at: str
    created_at: str = ""
@dataclass
class PaperCandidate:
    candidate_id: str
    search_id: str
    title: str
    conference_id: str
    conference_name: str
    year: Optional[int] = None
    authors: List[str] = field(default_factory=list)
    dblp_key: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    article_url: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_access: str = "unknown"
    retrieval_score: float = 0.0
    rerank_score: Optional[float] = None
    final_score: float = 0.0
    rank: int = 0
    existing_paper_id: Optional[str] = None
    initial_rank: int = 0
    normalized_title: str = ""
    publication_stage: str = "published"
    source_kind: str = "dblp"
    source_page_url: Optional[str] = None
    arxiv_id: Optional[str] = None
    source_links: List[dict] = field(default_factory=list)


# --- schema v2: global catalog and asynchronous retrieval ---------------------------------
# Status enumerations are fixed by spec-015 "SQLite schema v2"; they are also enforced as
# TEXT CHECK constraints in the DDL so the stored values cannot drift from these definitions.
FETCH_UNIT_STATES = ("pending", "fetching", "completed", "partial", "failed")
CATALOG_INDEX_STATES = ("pending", "indexed", "failed")
SEARCH_JOB_STATES = ("queued", "running", "completed", "partial", "failed")
SEARCH_PROGRESS_STATES = (
    "queued", "checking_cache", "fetching", "merging", "completed", "cached", "failed",
)


@dataclass
class SourceFetchUnit:
    """A unit of catalog metadata fetched from one source/conference/year."""
    fetch_unit_id: str
    source_kind: str
    conference_id: str
    year: Optional[int] = None
    unit_key: str = ""
    source_url: Optional[str] = None
    status: str = "pending"
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_hash: Optional[str] = None
    paper_count: int = 0
    error_code: Optional[str] = None
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CatalogPaper:
    """A globally deduplicated catalog paper keyed by catalog_paper_id."""
    catalog_paper_id: str
    conference_id: str
    year: Optional[int] = None
    title: str = ""
    normalized_title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    doi: Optional[str] = None
    dblp_key: Optional[str] = None
    publication_stage: str = "published"
    official_page_url: Optional[str] = None
    official_pdf_url: Optional[str] = None
    prepublication_pdf_url: Optional[str] = None
    arxiv_id: Optional[str] = None
    metadata_hash: str = ""
    index_status: str = "pending"
    index_version: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CatalogSourceRecord:
    source_record_id: str
    catalog_paper_id: str
    fetch_unit_id: str
    source_kind: str
    source_key: str
    raw_metadata: dict = field(default_factory=dict)
    observed_at: str = ""


@dataclass
class SearchJob:
    search_id: str
    query: str
    conference_ids: List[str] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    status: str = "queued"
    graph_version: Optional[str] = None
    degraded: bool = False
    error_code: Optional[str] = None
    total_results: int = 0
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    expires_at: str = ""
    updated_at: str = ""


@dataclass
class SearchSourceProgress:
    search_id: str
    source_kind: str
    status: str = "queued"
    cached_units: List[dict] = field(default_factory=list)
    fetching_units: List[dict] = field(default_factory=list)
    completed_units: List[dict] = field(default_factory=list)
    paper_count: int = 0
    error_code: Optional[str] = None
    message_code: Optional[str] = None
    updated_at: str = ""


@dataclass
class SearchEvent:
    event_id: int
    search_id: str
    node_name: str
    source_kind: Optional[str] = None
    event_type: str = ""
    status: Optional[str] = None
    safe_payload: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class SearchResult:
    search_id: str
    catalog_paper_id: str
    rank: int
    retrieval_score: float = 0.0
    rerank_score: Optional[float] = None
    final_score: float = 0.0
    snapshot: dict = field(default_factory=dict)
    created_at: str = ""
