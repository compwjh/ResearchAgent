"""Injected, allowlisted USENIX accepted-paper source."""

from __future__ import annotations

from dataclasses import dataclass
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Optional

import httpx

from backend.app.domain.paper_discovery import ConferenceSource
from backend.app.services.arxiv_adapter import ArxivFallbackAdapter
from backend.app.services.paper_discovery_normalization import normalize_title
from backend.app.services.paper_download import (
    INVALID_PDF,
    PDF_TOO_LARGE,
    PaperDownloadError,
    download_candidate,
)
from backend.app.services.paper_download_security import URLSecurityError, validate_url
from backend.app.services.usenix_paper_parser import UsenixAcceptedParser


@dataclass(frozen=True)
class UsenixAcceptedResult:
    records: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: Optional[str] = None


class UsenixAcceptedSource:
    """Recall USENIX accepted papers with official media priority.

    The client is injected so callers can use a fixture transport.  No network
    operation is performed while the search store is being written.
    """

    origin = "https://www.usenix.org"

    def __init__(self, *, client: Optional[httpx.Client] = None,
                 parser: Optional[UsenixAcceptedParser] = None,
                 arxiv_adapter: Optional[ArxivFallbackAdapter] = None,
                 timeout: float = 20.0,
                 dns_resolver: Optional[Callable[[str], Iterable[object]]] = None,
                 peer_ip_resolver: Optional[Callable[..., str | None]] = None,
                 cache_ttl_seconds: float = 86400.0,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 pdf_page_validator: Optional[Callable[[Any], int]] = None) -> None:
        self.client = client
        self.parser = parser or UsenixAcceptedParser()
        self.arxiv_adapter = arxiv_adapter or ArxivFallbackAdapter()
        self.timeout = timeout
        self.dns_resolver, self.peer_ip_resolver = dns_resolver, peer_ip_resolver
        self.cache_ttl_seconds, self._now, self._sleep = max(0.0, cache_ttl_seconds), now, sleep
        self.pdf_page_validator = pdf_page_validator
        self._cache: dict[tuple[str, object], tuple[float, object]] = {}
        self._search_cache: dict[tuple[object, ...], tuple[float, UsenixAcceptedResult]] = {}
        self._next_request_at = 0.0
        self._lock = threading.Lock()
        self._probe_state = threading.local()

    def search(self, source: ConferenceSource, query: str, years: Iterable[int],
               limit: int = 20, *, cycle: str = "1") -> UsenixAcceptedResult:
        if source.conference_id != "usenix-security":
            return UsenixAcceptedResult(error_code="ACCEPTED_ROUTE_UNAVAILABLE")
        selected_years = tuple(dict.fromkeys(years))
        cycle = str(cycle).removeprefix("cycle") or "1"
        route = self._route(source)
        if route is None:
            return UsenixAcceptedResult(error_code="ACCEPTED_ROUTE_UNAVAILABLE")
        cache_key = (source.conference_id, normalize_title(query), selected_years, cycle, limit)
        cached = self._cached(self._search_cache, cache_key)
        if cached is not None:
            return cached
        interval = self._rate_limit(route)
        self._probe_state.retryable = False
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        failed_years = 0
        for year in selected_years:
            listing = self._listing_url(route, int(year), cycle)
            try:
                markup = self._get_text(listing, interval)
                details = self.parser.parse_listing(markup, page_url=listing)
            except Exception:
                failed_years += 1
                warnings.append("USENIX_UNAVAILABLE")
                continue
            for detail_url in details:
                if len(records) >= limit:
                    break
                try:
                    paper = self.parser.parse_detail(self._get_text(detail_url, interval), page_url=detail_url)
                except Exception:
                    warnings.append("USENIX_PARSE_FAILED")
                    continue
                if normalize_title(query) not in normalize_title(paper.title):
                    continue
                pdf_url, stage = self._preferred_pdf(paper, interval)
                if not pdf_url:
                    try:
                        fallback = self.arxiv_adapter.lookup(paper.title, paper.authors, paper.year)
                    except Exception:
                        fallback = None
                        warnings.append("ARXIV_UNAVAILABLE")
                    if fallback is None:
                        source_kind, arxiv_id = "usenix_accepted", None
                    elif fallback.match:
                        pdf_url, stage = fallback.match.pdf_url, fallback.match.publication_stage
                        source_kind, arxiv_id = "arxiv", fallback.match.arxiv_id
                    else:
                        source_kind, arxiv_id = "usenix_accepted", None
                        if fallback.code:
                            warnings.append(str(fallback.code))
                else:
                    source_kind, arxiv_id = "usenix_accepted", None
                links = [{"kind": "usenix_page", "url": paper.article_url}]
                for kind, value in (("usenix_pdf", paper.official_pdf_url), ("usenix_prepublication_pdf", paper.prepublication_pdf_url)):
                    if value:
                        links.append({"kind": kind, "url": value})
                if arxiv_id:
                    links.extend(({"kind": "arxiv_page", "url": fallback.match.source_page_url},
                                  {"kind": "arxiv_pdf", "url": pdf_url}))
                records.append({"info": {
                    "title": paper.title, "authors": list(paper.authors), "year": paper.year,
                    "url": paper.article_url, "ee": pdf_url, "source_page_url": paper.article_url,
                    "pdf_url": pdf_url, "publication_stage": stage, "source_kind": source_kind,
                    "arxiv_id": arxiv_id, "source_links": links,
                }})
        error = "USENIX_UNAVAILABLE" if failed_years == len(selected_years) and failed_years else None
        result = UsenixAcceptedResult(tuple(records), tuple(dict.fromkeys(warnings)), error)
        if not result.error_code and not result.warnings and not getattr(self._probe_state, "retryable", False):
            with self._lock:
                self._search_cache[cache_key] = (self._now(), result)
        return result

    def _get_text(self, url: str, interval: float = 1.0) -> str:
        cached = self._cached(self._cache, ("text", url))
        if cached is not None:
            return str(cached)
        validate_url(url, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
        self._before_request(interval)
        response = self._client().get(url, timeout=self.timeout, follow_redirects=False)
        response.raise_for_status()
        with self._lock:
            self._cache[("text", url)] = (self._now(), response.text)
        return response.text

    def _get_pdf(self, url: str, interval: float = 1.0) -> bool:
        cached = self._cached(self._cache, ("pdf", url))
        if cached is not None:
            return bool(cached)
        try:
            validate_url(url, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
            with tempfile.TemporaryDirectory(prefix="usenix-probe-") as temp_dir:
                download_candidate(
                    {"pdf_url": url},
                    self._probe_settings(),
                    {"www.usenix.org"},
                    client=_ProbeClient(self, self._client(), interval),
                    dns_resolver=self.dns_resolver,
                    peer_ip_resolver=self.peer_ip_resolver,
                    temp_dir=temp_dir,
                    pdf_page_validator=self.pdf_page_validator,
                    validate_pdf_pages=True,
                )
            valid = True
        except PaperDownloadError as error:
            valid = False
            # Invalid/oversized bodies are stable probe results; transient or
            # policy errors remain retryable and are deliberately not cached.
            if error.code not in {INVALID_PDF, PDF_TOO_LARGE}:
                self._probe_state.retryable = True
                return False
        except (URLSecurityError, httpx.HTTPError, OSError):
            self._probe_state.retryable = True
            return False
        with self._lock:
            self._cache[("pdf", url)] = (self._now(), valid)
        return valid

    def _client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)
        return self.client

    def _preferred_pdf(self, paper: Any, interval: float = 1.0) -> tuple[Optional[str], str]:
        if paper.official_pdf_url and self._get_pdf(paper.official_pdf_url, interval):
            return paper.official_pdf_url, "accepted"
        if paper.prepublication_pdf_url and self._get_pdf(paper.prepublication_pdf_url, interval):
            return paper.prepublication_pdf_url, "prepublication"
        return None, "accepted"

    def _route(self, source: ConferenceSource) -> Mapping[str, Any] | None:
        routes = getattr(source, "discovery_routes", None) or []
        if not routes:
            return {"enabled": True, "rate_limit_seconds": 1.0}
        for route in routes:
            if isinstance(route, Mapping) and route.get("route_type") == "usenix_accepted":
                return route if route.get("enabled", True) else None
        return None

    @staticmethod
    def _rate_limit(route: Mapping[str, Any]) -> float:
        try:
            value = float(route.get("rate_limit_seconds", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.0, value)

    def _listing_url(self, route: Mapping[str, Any], year: int, cycle: str) -> str:
        template = str(route.get("listing_url_template") or
                       f"{self.origin}/conference/usenixsecurity{{yy}}/cycle{{cycle}}-accepted-papers")
        return template.replace("{yy}", f"{year % 100:02d}").replace("{year}", str(year)).replace("{cycle}", cycle)

    def _before_request(self, interval: float) -> None:
        with self._lock:
            now = self._now()
            wait = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + interval
        if wait:
            self._sleep(wait)

    def _cached(self, cache: dict, key: object) -> object | None:
        with self._lock:
            entry = cache.get(key)
            if entry and self._now() - entry[0] <= self.cache_ttl_seconds:
                return entry[1]
            if entry:
                cache.pop(key, None)
        return None

    def _probe_settings(self) -> Any:
        from backend.app.core.article_settings import ArticleSettings
        return ArticleSettings(article_download_dir=tempfile.gettempdir())


class _ProbeClient:
    """Force the shared downloader's request seam to remain no-redirect."""

    def __init__(self, owner: UsenixAcceptedSource, client: httpx.Client, interval: float) -> None:
        self.owner, self.client, self.interval = owner, client, interval

    def stream(self, method: str, url: str, **kwargs: Any):
        self.owner._before_request(self.interval)
        kwargs["follow_redirects"] = False
        return self.client.stream(method, url, **kwargs)


USENIXAcceptedSource = UsenixAcceptedSource

__all__ = ["UsenixAcceptedResult", "UsenixAcceptedSource", "USENIXAcceptedSource"]
