"""OpenAlex metadata enrichment for DBLP paper candidates.

OpenAlex is deliberately a best-effort supplement: a failure never removes the
DBLP candidate and no rerank score is created here.
"""
import time
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title


@dataclass(frozen=True)
class OpenAlexWarning:
    code: str
    candidate_id: Optional[str] = None
    stage: str = ""
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class OpenAlexEnrichmentResult:
    candidates: Tuple[PaperCandidate, ...]
    warnings: Tuple[OpenAlexWarning, ...] = ()
    error_code: Optional[str] = None

    @property
    def warning_codes(self) -> Tuple[str, ...]:
        return tuple(item.code for item in self.warnings)


class OpenAlexMetadata(dict):
    """Backward-compatible mapping carrying the structured helper outcome."""

    def __init__(self, *args: Any, warnings: Tuple[OpenAlexWarning, ...] = (), error_code: Optional[str] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.warnings = warnings
        self.error_code = error_code


def _abstract_from_inverted_index(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    words: Dict[int, str] = {}
    for token, positions in value.items():
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, int):
                    words[position] = str(token)
    return " ".join(words[index] for index in sorted(words)) or None


class OpenAlexEnricher:
    endpoint = "https://api.openalex.org/works"
    user_agent = "ResearchAgent-Spec015/1.0 (OpenAlex enricher)"
    title_similarity_threshold = 0.85

    def __init__(self, *, timeout: float = 20.0, retries: int = 0, backoff: float = 0.25,
                 client: Optional[httpx.Client] = None, transport: Any = None,
                 sleep=time.sleep, user_agent: Optional[str] = None,
                 title_similarity_threshold: Optional[float] = None):
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = max(0.0, backoff)
        self.client = client
        self.transport = transport
        self.sleep = sleep
        self.user_agent = user_agent or self.user_agent
        self.title_similarity_threshold = (self.title_similarity_threshold if title_similarity_threshold is None
                                           else title_similarity_threshold)

    def enrich(self, candidates: Iterable[PaperCandidate]) -> OpenAlexEnrichmentResult:
        enriched: List[PaperCandidate] = []
        warnings: List[OpenAlexWarning] = []
        hard_failures = 0
        attempted = 0
        for candidate in candidates:
            attempted += 1
            result, issues = self._enrich_one(candidate)
            enriched.append(result)
            warnings.extend(issues)
            if any(issue.stage in ("doi", "title") and issue.code in {
                "OPENALEX_TIMEOUT", "OPENALEX_RATE_LIMITED", "OPENALEX_HTTP_ERROR",
                "OPENALEX_NETWORK_ERROR", "OPENALEX_INVALID_RESPONSE",
            } for issue in issues):
                hard_failures += 1
        error_code = "OPENALEX_UNAVAILABLE" if attempted and hard_failures == attempted else None
        return OpenAlexEnrichmentResult(tuple(enriched), tuple(warnings), error_code)

    enrich_candidates = enrich

    def enrich_by_doi(self, doi: str, *, title: str = "", year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Compatibility helper for service orchestration that wants one DOI."""
        # Preserve the DBLP context so a DOI miss can use the title/year
        # fallback without losing the original candidate metadata.
        candidate = PaperCandidate("openalex-lookup", "openalex-lookup", title, "", "", year=year, doi=doi)
        result = self.enrich([candidate])
        enriched = result.candidates[0]
        metadata = self._metadata(enriched) if enriched != candidate else {}
        return OpenAlexMetadata(metadata, warnings=result.warnings, error_code=result.error_code)

    def enrich_by_title(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Compatibility helper for service orchestration that wants one title."""
        candidate = PaperCandidate("openalex-lookup", "openalex-lookup", title, "", "", year=year)
        result = self.enrich([candidate])
        enriched = result.candidates[0]
        metadata = self._metadata(enriched) if enriched != candidate else {}
        return OpenAlexMetadata(metadata, warnings=result.warnings, error_code=result.error_code)

    def _enrich_one(self, candidate: PaperCandidate) -> Tuple[PaperCandidate, List[OpenAlexWarning]]:
        warnings: List[OpenAlexWarning] = []
        if candidate.pdf_access not in {"unknown", "public", "login_required", "unavailable"}:
            candidate = replace(candidate, pdf_access="unknown")
        doi = normalize_doi(candidate.doi)
        if doi:
            payload, issue = self._request({"filter": "doi:" + doi, "per-page": 5}, candidate.candidate_id, "doi")
            if issue:
                return candidate, [issue]
            exact = next((item for item in self._results(payload) if normalize_doi(item.get("doi")) == doi), None)
            if exact is not None:
                if not isinstance(exact.get("locations", []), list):
                    warnings.append(OpenAlexWarning("OPENALEX_INVALID_LOCATIONS", candidate.candidate_id, "doi"))
                return self._merge(candidate, exact), warnings
            warnings.append(OpenAlexWarning("OPENALEX_NO_HIT", candidate.candidate_id, "doi"))

        title = str(candidate.title or "").strip()
        if not title:
            warnings.append(OpenAlexWarning("OPENALEX_NO_QUERY", candidate.candidate_id, "title"))
            return candidate, warnings
        payload, issue = self._request({"search": title, "per-page": 10}, candidate.candidate_id, "title")
        if issue:
            return candidate, warnings + [issue]
        matching = []
        for item in self._results(payload):
            item_title = str(item.get("title") or "")
            item_year = item.get("publication_year")
            if candidate.year is not None and str(item_year) != str(candidate.year):
                continue
            similarity = SequenceMatcher(None, normalize_title(title), normalize_title(item_title)).ratio()
            if similarity >= self.title_similarity_threshold:
                matching.append((similarity, item))
        if not matching:
            warnings.append(OpenAlexWarning("OPENALEX_NO_HIT", candidate.candidate_id, "title"))
            return candidate, warnings
        matching.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
        if not isinstance(matching[0][1].get("locations", []), list):
            warnings.append(OpenAlexWarning("OPENALEX_INVALID_LOCATIONS", candidate.candidate_id, "title"))
        return self._merge(candidate, matching[0][1]), warnings

    def _request(self, params: Dict[str, Any], candidate_id: str, stage: str) -> Tuple[Optional[Dict[str, Any]], Optional[OpenAlexWarning]]:
        last_issue: Optional[OpenAlexWarning] = None
        for attempt in range(self.retries + 1):
            try:
                kwargs = {"params": params, "headers": {"User-Agent": self.user_agent}, "timeout": self.timeout}
                if self.client is not None:
                    response = self.client.get(self.endpoint, **kwargs)
                else:
                    with httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport) as client:
                        response = client.get(self.endpoint, **kwargs)
                if response.status_code == 429:
                    last_issue = OpenAlexWarning("OPENALEX_RATE_LIMITED", candidate_id, stage, True)
                    if attempt < self.retries:
                        self.sleep(self.backoff * (2 ** attempt))
                        continue
                    return None, last_issue
                if response.status_code >= 500:
                    last_issue = OpenAlexWarning("OPENALEX_HTTP_ERROR", candidate_id, stage, True)
                    if attempt < self.retries:
                        self.sleep(self.backoff * (2 ** attempt))
                        continue
                    return None, last_issue
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError:
                    return None, OpenAlexWarning("OPENALEX_INVALID_RESPONSE", candidate_id, stage)
                if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
                    return None, OpenAlexWarning("OPENALEX_INVALID_RESPONSE", candidate_id, stage)
                return payload, None
            except httpx.TimeoutException:
                last_issue = OpenAlexWarning("OPENALEX_TIMEOUT", candidate_id, stage, True)
            except httpx.HTTPStatusError as error:
                code = "OPENALEX_RATE_LIMITED" if error.response is not None and error.response.status_code == 429 else "OPENALEX_HTTP_ERROR"
                last_issue = OpenAlexWarning(code, candidate_id, stage, True)
            except httpx.HTTPError:
                last_issue = OpenAlexWarning("OPENALEX_NETWORK_ERROR", candidate_id, stage, True)
            if attempt < self.retries:
                self.sleep(self.backoff * (2 ** attempt))
        return None, last_issue or OpenAlexWarning("OPENALEX_NETWORK_ERROR", candidate_id, stage, True)

    @staticmethod
    def _results(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [item for item in (payload or {}).get("results", []) if isinstance(item, dict)]

    @staticmethod
    def _metadata(candidate: PaperCandidate) -> Dict[str, Any]:
        return {field: getattr(candidate, field) for field in ("doi", "abstract", "article_url", "pdf_url", "pdf_access")}

    @staticmethod
    def _merge(candidate: PaperCandidate, item: Dict[str, Any]) -> PaperCandidate:
        open_access = item.get("open_access") or {}
        if not isinstance(open_access, dict):
            open_access = {}
        locations = item.get("locations")
        if not isinstance(locations, list):
            locations = []
        location = item.get("best_oa_location") or item.get("primary_location") or {}
        if not isinstance(location, dict):
            location = {}
        pdf_url = location.get("pdf_url") or open_access.get("oa_url")
        article_url = location.get("landing_page_url") or item.get("id")
        abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index"))
        if not pdf_url:
            pdf_url = next((row.get("pdf_url") for row in locations if isinstance(row, dict) and row.get("pdf_url")), None)
        updates = {
            "doi": candidate.doi or normalize_doi(item.get("doi")) or None,
            "abstract": candidate.abstract or abstract,
            "article_url": candidate.article_url or article_url,
            "pdf_url": candidate.pdf_url or pdf_url,
            "pdf_access": "public" if open_access.get("is_oa") is True else candidate.pdf_access,
        }
        if updates["pdf_access"] not in {"unknown", "public", "login_required", "unavailable"}:
            updates["pdf_access"] = "unknown"
        return replace(candidate, **updates)


def enrich_candidates(candidates: Iterable[PaperCandidate], **kwargs: Any) -> OpenAlexEnrichmentResult:
    return OpenAlexEnricher(**kwargs).enrich(candidates)
