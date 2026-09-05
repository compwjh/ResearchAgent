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
