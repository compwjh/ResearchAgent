"""Strict, cached arXiv fallback for USENIX accepted-paper candidates."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_title

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_HOSTS = frozenset({"arxiv.org", "export.arxiv.org"})
MIN_REQUEST_INTERVAL_SECONDS = 3.0
TITLE_THRESHOLD = 0.90
AUTHOR_THRESHOLD = 0.80
_NEW_ARXIV_ID = re.compile(r"^[0-9]{4}\.[0-9]{4,5}(?:v[1-9][0-9]*)?$", re.IGNORECASE)
_OLD_ARXIV_ID = re.compile(r"^[a-z0-9][a-z0-9.-]*/[0-9]{7}(?:v[1-9][0-9]*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ArxivMatch:
    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    pdf_url: str
    source_page_url: str
    score: float
    source_kind: str = "arxiv"
    publication_stage: str = "prepublication"


@dataclass(frozen=True)
class ArxivFallbackResult:
    match: Optional[ArxivMatch] = None
    code: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.match is not None


def _text(node: Optional[ElementTree.Element]) -> str:
    return " ".join((node.itertext() if node is not None else ())).strip()


def _safe_pdf(value: str) -> Optional[str]:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in ARXIV_HOSTS or parsed.username or parsed.password or parsed.port:
        return None
    if parsed.query or parsed.fragment or not parsed.path.startswith("/pdf/"):
        return None
    return value


def _arxiv_id(value: str) -> Optional[str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.hostname not in ARXIV_HOSTS or parsed.username or parsed.password or port
            or parsed.query or parsed.fragment or not parsed.path.startswith("/abs/")):
        return None
    return normalize_arxiv_id(parsed.path.removeprefix("/abs/").strip("/"))


def normalize_arxiv_id(value: object) -> Optional[str]:
    """Normalize a bare arXiv identity without accepting URLs or injection."""
    raw = str(value or "").strip()
    if raw.casefold().startswith("arxiv:"):
        raw = raw.split(":", 1)[1].strip()
    normalized = raw.casefold()
    if not (_NEW_ARXIV_ID.fullmatch(normalized) or _OLD_ARXIV_ID.fullmatch(normalized)):
        return None
    return normalized


def arxiv_identity_matches(expected: object, actual: object) -> bool:
    """Compare IDs, allowing an unversioned ID to match its returned latest version."""
    expected_id = normalize_arxiv_id(expected)
    actual_id = normalize_arxiv_id(actual)
    if expected_id is None or actual_id is None:
        return False
    expected_base, expected_version = _split_arxiv_version(expected_id)
    actual_base, actual_version = _split_arxiv_version(actual_id)
    return expected_base == actual_base and (expected_version is None or expected_version == actual_version)


def _split_arxiv_version(value: str) -> tuple[str, str | None]:
    base, separator, version = value.rpartition("v")
    if separator and version.isdigit():
        return base, version
    return value, None


def _author_key(value: str) -> str:
    return normalize_title(value)


class ArxivFallbackAdapter:
    """Query arXiv only after official USENIX media is unavailable."""

    def __init__(self, *, client: Optional[httpx.Client] = None, sleep: Callable[[float], None] = time.sleep,
                 cache_ttl_seconds: float = 86400.0, now: Callable[[], float] = time.monotonic,
                 retries: int = 2, backoff: float = 0.25) -> None:
        self.client, self.sleep, self.cache_ttl, self.now = client, sleep, max(0.0, cache_ttl_seconds), now
        self.retries, self.backoff = max(0, retries), max(0.0, backoff)
        self._cache: dict[tuple[object, ...], tuple[float, ArxivFallbackResult]] = {}
        self._last_request: Optional[float] = None
        self._lock = threading.Lock()

    def lookup(self, title: str, authors: Iterable[str], year: int, *, usenix_pdf_available: bool = False) -> ArxivFallbackResult:
        if usenix_pdf_available:
            return ArxivFallbackResult(code="USENIX_PDF_AVAILABLE")
        title_key = normalize_title(title)
        author_keys = tuple(sorted({_author_key(str(value)) for value in authors if _author_key(str(value))}))
        if not title_key or not author_keys or not isinstance(year, int) or isinstance(year, bool):
            return ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN")
        key = ("title", title_key, author_keys, year)
        with self._lock:
            cached = self._cache.get(key)
            if cached and self.now() - cached[0] <= self.cache_ttl:
                return cached[1]
        result = self._query(title, author_keys, year)
        with self._lock:
            self._cache[key] = (self.now(), result)
        return result

    def lookup_by_id(
        self,
        arxiv_id: object,
        title: str,
        authors: Iterable[str],
        year: int,
        *,
        usenix_pdf_available: bool = False,
    ) -> ArxivFallbackResult:
        """Query one normalized arXiv ID while retaining metadata identity gates."""
        if usenix_pdf_available:
            return ArxivFallbackResult(code="USENIX_PDF_AVAILABLE")
        normalized_id = normalize_arxiv_id(arxiv_id)
        title_key = normalize_title(title)
        author_keys = tuple(sorted({_author_key(str(value)) for value in authors if _author_key(str(value))}))
        if normalized_id is None:
            return ArxivFallbackResult(code="ARXIV_IDENTITY_CONFLICT")
        if not title_key or not author_keys or not isinstance(year, int) or isinstance(year, bool):
            return ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN")
        key = ("id", normalized_id, title_key, author_keys, year)
        with self._lock:
            cached = self._cache.get(key)
            if cached and self.now() - cached[0] <= self.cache_ttl:
                return cached[1]
        result = self._query_by_id(normalized_id, title, author_keys, year)
        with self._lock:
            self._cache[key] = (self.now(), result)
        return result

    def _query(self, title: str, authors: tuple[str, ...], year: int) -> ArxivFallbackResult:
        return self._request_feed(
            {"search_query": f'ti:"{title}"', "start": 0, "max_results": 20},
            title,
            authors,
            year,
        )

    def _query_by_id(
        self,
        arxiv_id: str,
        title: str,
        authors: tuple[str, ...],
        year: int,
    ) -> ArxivFallbackResult:
        return self._request_feed(
            {"id_list": arxiv_id, "start": 0, "max_results": 20},
            title,
            authors,
            year,
            expected_arxiv_id=arxiv_id,
        )

    def _request_feed(
        self,
        params: dict[str, object],
        title: str,
        authors: tuple[str, ...],
        year: int,
        *,
        expected_arxiv_id: str | None = None,
    ) -> ArxivFallbackResult:
        """Fetch and parse one Atom response through the existing safe seam."""
        client = self.client
        owned_client = client is None
        if client is None:
            client = httpx.Client(timeout=20.0, trust_env=False)
        last_code = "ARXIV_UNAVAILABLE"
        root: ElementTree.Element | None = None
        try:
            for attempt in range(self.retries + 1):
                self._wait_for_slot()
                try:
                    response = client.get(ARXIV_API_URL, params=params,
                                         headers={"User-Agent": "ResearchAgent-Spec015/1.0"})
                    if response.status_code == 429:
                        last_code = "ARXIV_RATE_LIMITED"
                    elif response.status_code >= 500:
                        last_code = "ARXIV_HTTP_ERROR"
                    else:
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError:
                            return ArxivFallbackResult(code="ARXIV_HTTP_ERROR")
                        try:
                            root = ElementTree.fromstring(response.text)
                        except (ElementTree.ParseError, ValueError):
                            return ArxivFallbackResult(code="ARXIV_INVALID_RESPONSE")
                        break
                except httpx.TimeoutException:
                    last_code = "ARXIV_UNAVAILABLE"
                except (httpx.HTTPError, OSError):
                    last_code = "ARXIV_UNAVAILABLE"
                if attempt < self.retries:
                    self.sleep(self.backoff * (2 ** attempt))
            else:
                return ArxivFallbackResult(code=last_code)
        finally:
            if owned_client:
                client.close()
        if root is None:
            return ArxivFallbackResult(code=last_code)
        return self._parse_feed(root, title, authors, year, expected_arxiv_id=expected_arxiv_id)

    def _parse_feed(
        self,
        root: ElementTree.Element,
        title: str,
        authors: tuple[str, ...],
        year: int,
        *,
        expected_arxiv_id: str | None = None,
    ) -> ArxivFallbackResult:
        title_key = normalize_title(title)
        best: Optional[ArxivMatch] = None
        identity_conflict = False
        metadata_conflict = False
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            entry_title = " ".join(_text(entry.find("a:title", ns)).split())
            entry_authors = tuple(_text(node.find("a:name", ns)) for node in entry.findall("a:author", ns))
            published = _text(entry.find("a:published", ns))[:4]
            try:
                entry_year = int(published)
            except ValueError:
                continue
            arxiv_id = _arxiv_id(_text(entry.find("a:id", ns)))
            if expected_arxiv_id is not None and not arxiv_identity_matches(expected_arxiv_id, arxiv_id):
                if arxiv_id is not None:
                    identity_conflict = True
                continue
            title_score = SequenceMatcher(None, title_key, normalize_title(entry_title)).ratio()
            candidate_authors = {_author_key(value) for value in entry_authors}
            author_score = len(set(authors) & candidate_authors) / max(len(authors), len(candidate_authors))
            if entry_year != year or title_score < TITLE_THRESHOLD or author_score < AUTHOR_THRESHOLD:
                if expected_arxiv_id is not None and arxiv_identity_matches(expected_arxiv_id, arxiv_id):
                    metadata_conflict = True
                continue
            pdf_url = next((_safe_pdf(link.attrib.get("href", "")) for link in entry.findall("a:link", ns)
                            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf"), None)
            if not arxiv_id or not pdf_url:
                continue
            score = round(title_score * 0.7 + author_score * 0.3, 6)
            match = ArxivMatch(arxiv_id, entry_title, entry_authors, entry_year, pdf_url,
                               f"https://arxiv.org/abs/{arxiv_id}", score)
            if best is None or match.score > best.score:
                best = match
        if best is not None:
            return ArxivFallbackResult(best, None)
        if expected_arxiv_id is not None and (identity_conflict or metadata_conflict):
            return ArxivFallbackResult(code="ARXIV_IDENTITY_CONFLICT")
        return ArxivFallbackResult(code="ARXIV_MATCH_UNCERTAIN")

    def _wait_for_slot(self) -> None:
        """Reserve the next request slot without holding the lock over I/O."""
        with self._lock:
            if self._last_request is not None:
                wait = MIN_REQUEST_INTERVAL_SECONDS - (self.now() - self._last_request)
                if wait > 0:
                    self.sleep(wait)
            self._last_request = self.now()


__all__ = [
    "ARXIV_API_URL",
    "ArxivFallbackAdapter",
    "ArxivFallbackResult",
    "ArxivMatch",
    "arxiv_identity_matches",
    "normalize_arxiv_id",
]
