from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ArticleCandidate:
    candidate_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    article_url: Optional[str] = None
    pdf_url: Optional[str] = None
    source_name: str = "configured"
    source_kind: str = "configured"
    confidence: float = 0.0
    requires_login: bool = False
    pdf_url_status: str = "unknown"
    source_error: Optional[str] = None


@dataclass
class ArticleTask:
    task_id: str
    query: str
    normalized_query: str
    intent: str
    intent_confidence: float
    status: str = "searching"
    candidates: List[ArticleCandidate] = field(default_factory=list)
    human_action: str = "not_required"
    selected_candidate_id: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
