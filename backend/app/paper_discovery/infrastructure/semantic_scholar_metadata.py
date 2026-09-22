"""Academic Graph metadata, recall and graph-assistance client.

This module is deliberately separate from the PDF fallback adapter.  It only
returns structured metadata and graph edges; callers decide whether a record is
eligible for the catalog and the existing download/import chain remains the
only component allowed to fetch a PDF.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import quote

import httpx

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import (
    SEMANTIC_SCHOLAR_API_URL,
    SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS,
    SemanticScholarRequestLimiter,
    get_semantic_scholar_request_limiter,
    semantic_scholar_retry_delay,
)

SEMANTIC_SCHOLAR_METADATA_FIELDS = (
    "paperId,title,abstract,authors,year,externalIds,url,venue,publicationTypes,"
    "fieldsOfStudy,citationCount"
)
SEMANTIC_SCHOLAR_MAX_BATCH_IDS = 500
SEMANTIC_SCHOLAR_METADATA_TITLE_THRESHOLD = 0.86
SEMANTIC_SCHOLAR_MAX_PAPER_ID_LENGTH = 200


@dataclass(frozen=True)
class SemanticScholarMetadata:
    paper_id: str
    title: str
    authors: tuple[str, ...] = ()
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    abstract: Optional[str] = None
    venue: Optional[str] = None
    fields_of_study: tuple[str, ...] = ()
    citation_count: Optional[int] = None
    source_url: Optional[str] = None


@dataclass(frozen=True)
class SemanticScholarEnrichment:
    catalog_paper_id: str
    metadata: Optional[SemanticScholarMetadata] = None
    code: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.metadata is not None


@dataclass(frozen=True)
class SemanticScholarRequestResult:
    payload: Any = None
    code: Optional[str] = None
    retryable: bool = False
    graph_page: Optional["SemanticScholarGraphPage"] = None


@dataclass(frozen=True)
class SemanticScholarGraphPage:
    """Normalized, metadata-only page returned by a graph-edge request.

    ``payload`` is kept on :class:`SemanticScholarRequestResult` for callers
    that need the provider envelope, while this page is the stable contract
    for application code.  It deliberately contains only paper metadata and
    pagination state; no provider response headers or request credentials are
    exposed.
    """

    relation: str
    source_paper_id: str
    items: tuple[SemanticScholarMetadata, ...] = ()
    offset: int = 0
    next_offset: Optional[int] = None
    total: Optional[int] = None


def _value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _arxiv_id(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if raw.casefold().startswith("arxiv:"):
        raw = raw.split(":", 1)[1]
    return raw or None


def _authors(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        name.strip()
        for item in value
        for name in [item.get("name") if isinstance(item, Mapping) else item]
        if isinstance(name, str) and name.strip()
    )


def _metadata(payload: Mapping[str, Any]) -> Optional[SemanticScholarMetadata]:
    paper_id = str(payload.get("paperId") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not paper_id or not title:
        return None
    external = payload.get("externalIds") if isinstance(payload.get("externalIds"), Mapping) else {}
    year = payload.get("year") if isinstance(payload.get("year"), int) else None
    fields = payload.get("fieldsOfStudy")
    field_values = tuple(str(value).strip() for value in fields if str(value).strip()) if isinstance(fields, list) else ()
    citation_count = payload.get("citationCount") if isinstance(payload.get("citationCount"), int) else None
    return SemanticScholarMetadata(
        paper_id=paper_id,
        title=title,
        authors=_authors(payload.get("authors")),
        year=year,
        doi=normalize_doi(external.get("DOI")) or None,
        arxiv_id=_arxiv_id(external.get("ArXiv")),
        abstract=str(payload.get("abstract") or "").strip() or None,
        venue=str(payload.get("venue") or "").strip() or None,
        fields_of_study=field_values,
        citation_count=citation_count,
        source_url=str(payload.get("url") or "").strip() or None,
    )


def _nonnegative_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _parse_graph_page(
    payload: Any,
    relation: str,
    source_paper_id: str,
    offset: int,
) -> Optional[SemanticScholarGraphPage]:
    """Normalize one citations/references response without trusting its shape."""
    if relation not in {"citations", "references"} or not isinstance(payload, Mapping):
        return None

    # The Graph API normally returns ``data`` as a list.  Empty reference
    # pages have also been observed as ``data: null`` (and, in one provider
    # response variant, with the field omitted) together with ``total: 0``.
    # Treat only that explicit empty-page envelope as a valid page: accepting
    # arbitrary missing/wrong-shaped data would hide a provider schema change.
    total_value = payload.get("total")
    total = _nonnegative_int(total_value)
    if total_value is not None and total is None:
        return None
    rows_value = payload.get("data")
    if rows_value is None:
        if total != 0:
            return None
        rows: list[Any] = []
    elif isinstance(rows_value, list):
        rows = rows_value
    else:
        return None

    provider_offset = payload.get("offset")
    if provider_offset is not None and _nonnegative_int(provider_offset) is None:
        return None
    provider_next = payload.get("next")
    if provider_next is not None and _nonnegative_int(provider_next) is None:
        return None
    edge_key = "citingPaper" if relation == "citations" else "citedPaper"
    items: list[SemanticScholarMetadata] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        candidate = row.get(edge_key)
        if not isinstance(candidate, Mapping):
            continue
        metadata = _metadata(candidate)
        if metadata is None or metadata.paper_id in seen_ids:
            continue
        seen_ids.add(metadata.paper_id)
        items.append(metadata)
    # ``next=0`` is the API's terminal-page sentinel, not an offset to loop
    # back to.  If a non-zero total contradicts that sentinel, derive the
    # next offset from the request offset and the provider row count.
    next_offset = _nonnegative_int(provider_next)
    if next_offset == 0:
        next_offset = None
    if next_offset is None and total is not None and offset + len(rows) < total:
        next_offset = offset + len(rows)
    return SemanticScholarGraphPage(
        relation=relation,
        source_paper_id=source_paper_id,
        items=tuple(items),
        offset=offset,
        next_offset=next_offset,
        total=total,
    )


class SemanticScholarGraphClient:
    """Small, rate-limited wrapper around the Academic Graph API."""

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        api_key: Optional[str] = None,
        retries: int = 1,
        backoff: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
        rate_limiter: Optional[SemanticScholarRequestLimiter] = None,
    ) -> None:
        self.client = client
        self.api_key = (api_key if api_key is not None else os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")).strip()
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))
        self.sleep = sleep
        self.now = now
        if rate_limiter is not None:
            self.rate_limiter = rate_limiter
        elif sleep is time.sleep and now is time.monotonic:
            self.rate_limiter = get_semantic_scholar_request_limiter()
        else:
            self.rate_limiter = SemanticScholarRequestLimiter(
                interval_seconds=SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS,
                sleep=sleep,
                now=now,
            )
        self._batch_cache: dict[tuple[str, ...], tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None,
                 json: Any = None) -> SemanticScholarRequestResult:
        headers = {"Accept": "application/json", "User-Agent": "ResearchAgent-paper-discovery/1.0"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        client = self.client
        owned = client is None
        if client is None:
            client = httpx.Client(timeout=20.0, trust_env=False)
        last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
        last_response: Optional[httpx.Response] = None
        try:
            for attempt in range(self.retries + 1):
                self.rate_limiter.wait_for_slot()
                # A Retry-After value belongs only to the response that
                # produced it; network failures on a later attempt must use
                # the exponential fallback instead of a stale header.
                last_response = None
                try:
                    response = client.request(method, f"{SEMANTIC_SCHOLAR_API_URL}{path}", params=params,
                                              json=json, headers=headers)
                except (httpx.TimeoutException, httpx.HTTPError, OSError):
                    last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
                else:
                    last_response = response
                    if response.status_code in {401, 403}:
                        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_AUTH_FAILED")
                    if response.status_code == 404:
                        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_NOT_FOUND")
                    if response.status_code == 429:
                        last_code = "SEMANTIC_SCHOLAR_RATE_LIMITED"
                    elif response.status_code >= 500:
                        last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
                    elif response.status_code >= 400:
                        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_HTTP_ERROR")
                    else:
                        try:
                            return SemanticScholarRequestResult(payload=response.json())
                        except (ValueError, TypeError):
                            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_INVALID_RESPONSE")
                if attempt < self.retries:
                    self.sleep(semantic_scholar_retry_delay(last_response, attempt, self.backoff))
            return SemanticScholarRequestResult(code=last_code, retryable=True)
        finally:
            if owned:
                client.close()

    def batch(self, identifiers: Iterable[str], *, fields: str = SEMANTIC_SCHOLAR_METADATA_FIELDS) -> SemanticScholarRequestResult:
        values = list(dict.fromkeys(str(value).strip() for value in identifiers if str(value).strip()))
        if not values:
            return SemanticScholarRequestResult(payload=[])
        if len(values) > SEMANTIC_SCHOLAR_MAX_BATCH_IDS:
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_BATCH_LIMIT")
        return self._request("POST", "/paper/batch", params={"fields": fields}, json={"ids": values})

    def search_bulk(self, query: str, *, limit: int = 20, year: Optional[int] = None,
                    fields: str = SEMANTIC_SCHOLAR_METADATA_FIELDS) -> SemanticScholarRequestResult:
        query = str(query or "").strip()
        if not query:
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_QUERY_REQUIRED")
        params: dict[str, Any] = {"query": query[:500], "limit": max(1, min(int(limit), 100)), "fields": fields}
        if year is not None:
            params["year"] = str(int(year))
        return self._request("GET", "/paper/search/bulk", params=params)

    @staticmethod
    def parse_search_results(payload: Any) -> tuple[SemanticScholarMetadata, ...]:
        """Parse bulk-search data without treating venue as conference proof."""
        rows = payload.get("data") if isinstance(payload, Mapping) else payload
        if not isinstance(rows, list):
            return ()
        return tuple(metadata for row in rows if isinstance(row, Mapping)
                     for metadata in [_metadata(row)] if metadata is not None)

    @staticmethod
    def parse_graph_page(
        payload: Any,
        relation: str,
        source_paper_id: str,
        *,
        offset: int = 0,
    ) -> Optional[SemanticScholarGraphPage]:
        """Parse a provider graph envelope into the stable page contract."""
        try:
            page_offset = max(0, int(offset))
        except (TypeError, ValueError):
            return None
        return _parse_graph_page(payload, relation, str(source_paper_id).strip(), page_offset)

    def autocomplete(self, query: str, *, limit: int = 10) -> SemanticScholarRequestResult:
        if not str(query or "").strip():
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_QUERY_REQUIRED")
        return self._request("GET", "/paper/autocomplete", params={"query": str(query).strip()[:100], "limit": max(1, min(int(limit), 20))})

    def graph_edges(self, paper_id: str, relation: str, *, limit: int = 20, offset: int = 0,
                    fields: str = SEMANTIC_SCHOLAR_METADATA_FIELDS) -> SemanticScholarRequestResult:
        if relation not in {"citations", "references"}:
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_RELATION_UNSUPPORTED")
        identifier = str(paper_id or "").strip()
        if not identifier:
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED")
        if (
            len(identifier) > SEMANTIC_SCHOLAR_MAX_PAPER_ID_LENGTH
            or any(ord(character) < 32 for character in identifier)
            or any(character in "/?#" for character in identifier)
        ):
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_IDENTIFIER_INVALID")
        try:
            page_offset = max(0, int(offset))
            page_limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_PAGINATION_INVALID")
        result = self._request(
            "GET", f"/paper/{quote(identifier, safe=':')}/{relation}",
            params={
                "limit": page_limit,
                "offset": page_offset,
                "fields": fields,
            },
        )
        if result.code is not None:
            return result
        page = _parse_graph_page(result.payload, relation, identifier, page_offset)
        if page is None:
            return SemanticScholarRequestResult(
                payload=result.payload,
                code="SEMANTIC_SCHOLAR_INVALID_RESPONSE",
            )
        return SemanticScholarRequestResult(payload=result.payload, graph_page=page)

    def enrich(self, candidates: Iterable[Any], *, cache_ttl_seconds: float = 86400.0) -> tuple[SemanticScholarEnrichment, ...]:
        values = list(candidates)
        identifiers: dict[str, tuple[str, Any]] = {}
        for candidate in values:
            identifier = (
                normalize_doi(_value(candidate, "doi"))
                or _arxiv_id(_value(candidate, "arxiv_id"))
                or str(_value(candidate, "semantic_scholar_id", "") or "").strip()
            )
            if identifier:
                if normalize_doi(_value(candidate, "doi")):
                    key = f"DOI:{identifier}"
                elif _arxiv_id(_value(candidate, "arxiv_id")):
                    key = f"ARXIV:{identifier}"
                else:
                    key = identifier
                identifiers[key] = (str(_value(candidate, "catalog_paper_id", "")), candidate)
        if not identifiers:
            return tuple(SemanticScholarEnrichment(str(_value(candidate, "catalog_paper_id", "")), code="SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED") for candidate in values)
        keys = list(identifiers)
        payloads: list[Any] = []
        for start in range(0, len(keys), SEMANTIC_SCHOLAR_MAX_BATCH_IDS):
            cache_key = tuple(keys[start:start + SEMANTIC_SCHOLAR_MAX_BATCH_IDS])
            with self._cache_lock:
                cached = self._batch_cache.get(cache_key)
            if cached is not None and self.now() - cached[0] <= cache_ttl_seconds:
                result = SemanticScholarRequestResult(payload=cached[1])
            else:
                result = self.batch(cache_key)
                if result.code is None:
                    with self._cache_lock:
                        self._batch_cache[cache_key] = (self.now(), result.payload)
            if result.code:
                return tuple(SemanticScholarEnrichment(str(_value(candidate, "catalog_paper_id", "")), code=result.code) for candidate in values)
            if isinstance(result.payload, list):
                payloads.extend(result.payload)
        by_id: dict[str, SemanticScholarMetadata] = {}
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            metadata = _metadata(payload)
            if metadata is None:
                continue
            for key in (f"DOI:{metadata.doi}" if metadata.doi else None, f"ARXIV:{metadata.arxiv_id}" if metadata.arxiv_id else None, metadata.paper_id):
                if key:
                    by_id[key] = metadata
        output: list[SemanticScholarEnrichment] = []
        for identifier, (catalog_id, candidate) in identifiers.items():
            metadata = by_id.get(identifier)
            if metadata is None or not self._matches(candidate, metadata):
                output.append(SemanticScholarEnrichment(catalog_id, code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN"))
            else:
                output.append(SemanticScholarEnrichment(catalog_id, metadata=metadata))
        return tuple(output)

    @staticmethod
    def _matches(candidate: Any, metadata: SemanticScholarMetadata) -> bool:
        title = str(_value(candidate, "title", ""))
        if SequenceMatcher(None, normalize_title(title), normalize_title(metadata.title)).ratio() < SEMANTIC_SCHOLAR_METADATA_TITLE_THRESHOLD:
            return False
        candidate_year = _value(candidate, "year")
        if isinstance(candidate_year, int) and metadata.year is not None and candidate_year != metadata.year:
            return False
        candidate_authors = {normalize_title(str(value)) for value in (_value(candidate, "authors", ()) or ()) if str(value).strip()}
        metadata_authors = {normalize_title(value) for value in metadata.authors}
        return not candidate_authors or not metadata_authors or bool(candidate_authors & metadata_authors)


__all__ = [
    "SEMANTIC_SCHOLAR_MAX_PAPER_ID_LENGTH",
    "SEMANTIC_SCHOLAR_MAX_BATCH_IDS",
    "SEMANTIC_SCHOLAR_METADATA_FIELDS",
    "SemanticScholarEnrichment",
    "SemanticScholarGraphPage",
    "SemanticScholarGraphClient",
    "SemanticScholarMetadata",
    "SemanticScholarRequestResult",
]
