"""受控的 Semantic Scholar OA 论文查找适配器。

Semantic Scholar 只负责通过 Academic Graph API 查找论文元数据和
``openAccessPdf.url``；它不是下载器，也不是可信主机注册表。返回的 PDF 地址
必须由调用方提供固定 allowlist，再交给既有 ``paper_download``/``paper_import``
链路校验。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import quote, urlsplit

import httpx

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_API_HOST = "api.semanticscholar.org"
SEMANTIC_SCHOLAR_FIELDS = (
    "paperId,title,abstract,authors,year,externalIds,url,openAccessPdf"
)
SEMANTIC_SCHOLAR_TITLE_THRESHOLD = 0.86
SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class SemanticScholarMatch:
    paper_id: str
    title: str
    authors: tuple[str, ...]
    year: Optional[int]
    doi: Optional[str]
    arxiv_id: Optional[str]
    abstract: Optional[str]
    source_page_url: Optional[str]
    pdf_url: Optional[str]
    open_access_status: Optional[str] = None


@dataclass(frozen=True)
class SemanticScholarResult:
    match: Optional[SemanticScholarMatch] = None
    code: Optional[str] = None
    retryable: bool = False

    @property
    def matched(self) -> bool:
        return self.match is not None


def _value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _authors(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for author in value:
        name = author.get("name") if isinstance(author, Mapping) else author
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return tuple(names)


def _author_key(value: str) -> str:
    return normalize_title(value)


def _arxiv_id(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if raw.casefold().startswith("arxiv:"):
        raw = raw.split(":", 1)[1]
    return raw or None


def _safe_https_url(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port:
        return None
    return value.strip()


class SemanticScholarFallbackAdapter:
    """Look up one candidate by DOI/ArXiv ID and expose a safe OA candidate.

    The adapter deliberately does not accept arbitrary API URLs, cookies, or a
    caller-supplied paper id.  Title search is left for a later extension because
    it cannot provide the same identity guarantees as an existing DOI/ArXiv id.
    """

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
        cache_ttl_seconds: float = 86400.0,
        retries: int = 1,
        backoff: float = 0.5,
        api_key: Optional[str] = None,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.now = now
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))
        self.api_key = (api_key if api_key is not None else os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")).strip()
        self._cache: dict[str, tuple[float, SemanticScholarResult]] = {}
        self._last_request: Optional[float] = None
        self._lock = threading.Lock()

    def lookup(self, candidate: Any, *, allowed_hosts: Iterable[str] = ()) -> SemanticScholarResult:
        identifier, expected_kind = self._identifier(candidate)
        if not identifier:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED")
        key = f"{expected_kind}:{identifier}"
        with self._lock:
            cached = self._cache.get(key)
            if cached and self.now() - cached[0] <= self.cache_ttl_seconds:
                return self._filter_pdf_host(cached[1], allowed_hosts)
        result = self._query(identifier, expected_kind, candidate)
        with self._lock:
            self._cache[key] = (self.now(), result)
        return self._filter_pdf_host(result, allowed_hosts)

    @staticmethod
    def _identifier(candidate: Any) -> tuple[Optional[str], Optional[str]]:
        arxiv = _value(candidate, "arxiv_id")
        if arxiv:
            return _arxiv_id(arxiv), "ARXIV"
        doi = normalize_doi(_value(candidate, "doi"))
        if doi:
            return doi, "DOI"
        return None, None

    def _query(self, identifier: str, kind: str, candidate: Any) -> SemanticScholarResult:
        endpoint = f"{SEMANTIC_SCHOLAR_API_URL}/paper/{quote(f'{kind}:{identifier}', safe=':')}"
        headers = {"Accept": "application/json", "User-Agent": "ResearchAgent-paper-discovery/1.0"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        client = self.client
        owned_client = client is None
        if client is None:
            client = httpx.Client(timeout=20.0, trust_env=False)
        last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
        try:
            for attempt in range(self.retries + 1):
                self._wait_for_slot()
                try:
                    response = client.get(endpoint, params={"fields": SEMANTIC_SCHOLAR_FIELDS}, headers=headers)
                except (httpx.TimeoutException, httpx.HTTPError, OSError):
                    last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
                else:
                    if response.status_code == 401 or response.status_code == 403:
                        return SemanticScholarResult(code="SEMANTIC_SCHOLAR_AUTH_FAILED")
                    if response.status_code == 404:
                        return SemanticScholarResult(code="SEMANTIC_SCHOLAR_NOT_FOUND")
                    if response.status_code == 429:
                        last_code = "SEMANTIC_SCHOLAR_RATE_LIMITED"
                    elif response.status_code >= 500:
                        last_code = "SEMANTIC_SCHOLAR_UNAVAILABLE"
                    elif response.status_code >= 400:
                        return SemanticScholarResult(code="SEMANTIC_SCHOLAR_HTTP_ERROR")
                    else:
                        try:
                            payload = response.json()
                        except (ValueError, TypeError):
                            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_INVALID_RESPONSE")
                        return self._parse(payload, candidate, identifier, kind)
                if attempt < self.retries:
                    self.sleep(self.backoff * (2**attempt))
            return SemanticScholarResult(code=last_code, retryable=True)
        finally:
            if owned_client:
                client.close()

    def _parse(self, payload: Any, candidate: Any, identifier: str, kind: str) -> SemanticScholarResult:
        if not isinstance(payload, Mapping):
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_INVALID_RESPONSE")
        title = str(payload.get("title") or "").strip()
        if not title:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_INVALID_RESPONSE")
        external = payload.get("externalIds") if isinstance(payload.get("externalIds"), Mapping) else {}
        doi = normalize_doi(external.get("DOI")) or None
        arxiv = _arxiv_id(external.get("ArXiv"))
        expected = normalize_doi(identifier) if kind == "DOI" else _arxiv_id(identifier)
        actual = doi if kind == "DOI" else arxiv
        title_score = SequenceMatcher(None, normalize_title(title), normalize_title(_value(candidate, "title", ""))).ratio()
        if expected and not actual:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN")
        if expected and actual and expected != (normalize_doi(actual) if kind == "DOI" else _arxiv_id(actual)):
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN")
        if title_score < SEMANTIC_SCHOLAR_TITLE_THRESHOLD:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN")
        candidate_year = _value(candidate, "year")
        year = payload.get("year") if isinstance(payload.get("year"), int) else None
        if isinstance(candidate_year, int) and year is not None and candidate_year != year:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN")
        candidate_authors = {_author_key(str(item)) for item in (_value(candidate, "authors", []) or [])}
        authors = _authors(payload.get("authors"))
        result_authors = {_author_key(item) for item in authors}
        if candidate_authors and result_authors and not candidate_authors.intersection(result_authors):
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_MATCH_UNCERTAIN")
        oa = payload.get("openAccessPdf") if isinstance(payload.get("openAccessPdf"), Mapping) else {}
        pdf_url = _safe_https_url(oa.get("url"))
        match = SemanticScholarMatch(
            paper_id=str(payload.get("paperId") or ""), title=title, authors=authors,
            year=year, doi=doi, arxiv_id=arxiv, abstract=str(payload.get("abstract") or "").strip() or None,
            source_page_url=_safe_https_url(payload.get("url")), pdf_url=pdf_url,
            open_access_status=str(oa.get("status") or "").strip() or None,
        )
        if not match.paper_id:
            return SemanticScholarResult(code="SEMANTIC_SCHOLAR_INVALID_RESPONSE")
        if not match.pdf_url:
            return SemanticScholarResult(match=match, code="SEMANTIC_SCHOLAR_NO_OPEN_PDF")
        return SemanticScholarResult(match=match)

    @staticmethod
    def _filter_pdf_host(result: SemanticScholarResult, allowed_hosts: Iterable[str]) -> SemanticScholarResult:
        if not result.match or not result.match.pdf_url:
            return result
        try:
            host = (urlsplit(result.match.pdf_url).hostname or "").casefold()
        except ValueError:
            return SemanticScholarResult(match=result.match, code="SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST")
        allowlist = {str(value).strip().casefold() for value in allowed_hosts if str(value).strip()}
        if host not in allowlist:
            return SemanticScholarResult(match=result.match, code="SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST")
        return result

    def _wait_for_slot(self) -> None:
        with self._lock:
            if self._last_request is not None:
                wait = SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS - (self.now() - self._last_request)
                if wait > 0:
                    self.sleep(wait)
            self._last_request = self.now()


__all__ = [
    "SEMANTIC_SCHOLAR_API_HOST",
    "SEMANTIC_SCHOLAR_API_URL",
    "SEMANTIC_SCHOLAR_FIELDS",
    "SemanticScholarFallbackAdapter",
    "SemanticScholarMatch",
    "SemanticScholarResult",
]
