"""Safe, injectable metadata extraction for IEEE Xplore paper pages.

The parser deliberately has no network or browser side effects.  A caller may
provide an HTML snapshot, or a Playwright-like page fake exposing ``content``
and ``url``.  Only the exact IEEE Xplore HTTPS origin is accepted, and the
result never contains request headers or cookies.
"""

from __future__ import annotations

import html as html_module
import inspect
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit


IEEE_ORIGIN = "https://ieeexplore.ieee.org"
IEEE_HOST = "ieeexplore.ieee.org"
IEEE_PARSE_FAILED = "IEEE_PARSE_FAILED"

_AUTH_QUERY_NAMES = frozenset(
    {
        "auth",
        "authorization",
        "api_key",
        "apikey",
        "access_key",
        "key",
        "password",
        "passwd",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
        "cookie",
        "access_token",
        "refresh_token",
        "id_token",
        "jwt",
    }
)
_AUTH_QUERY_RE = re.compile(r"(?:^|[_-])(token|secret|password|credential|signature)(?:$|[_-])", re.I)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_PDF_PATH_RE = re.compile(r"(?:\.pdf(?:$|[?#])|/pdf(?:[/._?-]|$)|/download(?:[/._?-]|$)|/stamp/)", re.I)
_PDF_TEXT_RE = re.compile(r"\b(?:pdf|download)\b", re.I)


class IEEEPaperParseError(RuntimeError):
    """Stable, retryable parser error without exposing page contents."""

    code = IEEE_PARSE_FAILED
    retryable = True

    def __init__(self, message: str = "IEEE 页面结构暂不可解析，请重试") -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class IEEEPaper:
    """Safe fields extracted from one IEEE Xplore article page."""

    pdf_url: str | None
    article_url: str
    title: str
    doi: str | None = None

    @property
    def pdf_access(self) -> str:
        return "public" if self.pdf_url else "unknown"


# A descriptive alias makes the result name convenient for callers that use
# the parser as an adapter rather than as a site-specific implementation.
IEEEParseResult = IEEEPaper


@dataclass
class _PageData:
    title_values: list[str]
    doi_values: list[str]
    article_values: list[str]
    pdf_values: list[str]
    pdf_text_values: list[str]
    links: list[str]


class _IEEEHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.data = _PageData([], [], [], [], [], [])
        self._text_stack: list[bool] = []
        self._link_hrefs: list[str] = []
        self._text_parts: list[str] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.casefold(): value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        tag_name = tag.casefold()
        if tag_name in {"a", "button"}:
            href = values.get("href") or values.get("data-href") or values.get("data-url") or values.get("data-pdf-url") or ""
            self._link_hrefs.append(href)
            if href:
                self.data.links.append(href)
            self._text_stack.append(
                bool(_PDF_TEXT_RE.search(values.get("aria-label", "") + " " + values.get("title", ""))))
            self._text_parts = []
        if tag_name == "meta":
            key = values.get("name") or values.get("property") or values.get("itemprop")
            content = values.get("content", "").strip()
            if key and content:
                key = key.casefold()
                if key in {"citation_title", "og:title", "dc.title", "title"}:
                    self.data.title_values.append(content)
                elif key in {"citation_doi", "dc.identifier", "doi", "prism.doi"}:
                    self.data.doi_values.append(content)
                elif key in {"citation_pdf_url", "pdf_url", "pdfurl"}:
                    self.data.pdf_values.append(content)
                elif key in {"og:url", "canonical", "citation_publication_url"}:
                    self.data.article_values.append(content)
        elif tag_name == "link":
            href = values.get("href", "").strip()
            rel = values.get("rel", "").casefold()
            kind = values.get("type", "").casefold()
            if href and ("canonical" in rel or "alternate" in rel and "pdf" not in kind):
                self.data.article_values.append(href)
            if href and ("pdf" in kind or _PDF_PATH_RE.search(href)):
                self.data.pdf_values.append(href)
        elif tag_name in {"a", "button"}:
            href = values.get("href") or values.get("data-href") or values.get("data-url")
            if href and (_PDF_PATH_RE.search(href) or _PDF_TEXT_RE.search(values.get("aria-label", "") + " " + values.get("title", ""))):
                self.data.pdf_values.append(href)
                self._text_stack[-1] = True
        else:
            for key in ("data-pdf-url", "data-pdfurl", "data-download-url", "data-download"):
                if values.get(key):
                    self.data.pdf_values.append(values[key])
        if tag_name == "title" or tag_name == "h1":
            self._text_stack.append(False)
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._text_stack:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name in {"title", "h1"}:
            text = " ".join("".join(self._text_parts).split())
            if text:
                self.data.title_values.append(text)
            if self._text_stack:
                self._text_stack.pop()
            self._text_parts = []
        elif tag_name in {"a", "button"}:
            text = " ".join("".join(self._text_parts).split())
            href = self._link_hrefs.pop() if self._link_hrefs else ""
            if text and _PDF_TEXT_RE.search(text):
                self.data.pdf_text_values.append(text)
                if href:
                    self.data.pdf_values.append(href)
            if self._text_stack:
                self._text_stack.pop()
            self._text_parts = []


def _fail() -> None:
    raise IEEEPaperParseError()


def _safe_ieee_url(value: object, *, base_url: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail()
    candidate = html_module.unescape(value.strip())
    if base_url:
        candidate = urljoin(base_url, candidate)
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except (TypeError, ValueError):
        _fail()
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != IEEE_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
    ):
        _fail()
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        decoded = unquote(key).casefold()
        if decoded in _AUTH_QUERY_NAMES or _AUTH_QUERY_RE.search(decoded):
            _fail()
    return candidate


def _clean_title(values: Iterable[str]) -> str:
    for value in values:
        title = " ".join(str(value).split()).strip(" -|")
        if not title:
            continue
        # IEEE commonly appends this fixed branding to the HTML title.  Do
        # not strip arbitrary suffixes from citation_title or h1 values.
        title = re.sub(r"\s*\|\s*IEEE(?:\s+Xplore)?(?:\s+Digital Library)?(?:\s+.*)?$", "", title, flags=re.I)
        title = re.sub(r"\s*-\s*IEEE\s+Xplore.*$", "", title, flags=re.I)
        if title:
            return title
    _fail()


def _clean_doi(values: Iterable[str]) -> str | None:
    for value in values:
        match = _DOI_RE.search(str(value).strip())
        if match:
            return match.group(0).rstrip(".,;)]}")
    return None


def _looks_like_pdf(value: str) -> bool:
    return bool(_PDF_PATH_RE.search(value))


class IEEEPaperParser:
    """Parse one injected IEEE page or a Playwright-like page fake."""

    def parse_html(
        self,
        page_html: str,
        *,
        page_url: str = IEEE_ORIGIN + "/",
        pdf_requests: Iterable[object] = (),
    ) -> IEEEPaper:
        if not isinstance(page_html, str) or not page_html.strip():
            _fail()
        base_url = _safe_ieee_url(page_url)
        parser = _IEEEHTMLParser()
        try:
            parser.feed(page_html)
            parser.close()
        except Exception as error:
            raise IEEEPaperParseError() from error

        # Validate explicitly extracted article links.  A changed/corrupted
        # canonical URL must not silently fall back to the browser URL.
        article_url: str | None = None
        canonical = parser.data.article_values[0] if parser.data.article_values else None
        if canonical:
            article_url = _safe_ieee_url(canonical, base_url=base_url)
        for raw_url in parser.data.links:
            if article_url or _looks_like_pdf(raw_url):
                continue
            try:
                safe = _safe_ieee_url(raw_url, base_url=base_url)
            except IEEEPaperParseError:
                continue
            if "/document/" in urlsplit(safe).path.casefold():
                article_url = safe
        if article_url is None and "/document/" in urlsplit(base_url).path.casefold():
            article_url = base_url
        if article_url is None:
            _fail()

        pdf_candidates = list(parser.data.pdf_values)
        for request in pdf_requests:
            url, method, headers = self._request_parts(request)
            if not url:
                continue
            if any(name.casefold() in {"cookie", "authorization"} for name in headers):
                raise IEEEPaperParseError()
            if method.casefold() != "get":
                continue
            if _looks_like_pdf(url) or "application/pdf" in next((value for name, value in headers.items() if name.casefold() == "accept"), "").casefold():
                pdf_candidates.append(url)

        pdf_url: str | None = None
        for raw_url in pdf_candidates:
            # Only links/request URLs that advertise PDF/download are treated
            # as download candidates; ordinary external navigation is ignored.
            resolved = _safe_ieee_url(raw_url, base_url=article_url)
            if _looks_like_pdf(resolved) or raw_url in parser.data.pdf_values:
                pdf_url = resolved
                break

        return IEEEPaper(
            pdf_url=pdf_url,
            article_url=article_url,
            title=_clean_title(parser.data.title_values),
            doi=_clean_doi([*parser.data.doi_values, page_html]),
        )

    def parse_page(self, page: Any) -> IEEEPaper:
        try:
            content = page.content() if callable(getattr(page, "content", None)) else getattr(page, "content")
            page_url = page.url() if callable(getattr(page, "url", None)) else getattr(page, "url")
            requests = getattr(page, "pdf_requests", getattr(page, "requests", ()))
            if callable(requests):
                requests = requests()
            if inspect.isawaitable(content) or inspect.isawaitable(page_url):
                _fail()
            return self.parse_html(content, page_url=page_url, pdf_requests=requests or ())
        except IEEEPaperParseError:
            raise
        except Exception as error:
            raise IEEEPaperParseError() from error

    def parse(self, source: object, *, page_url: str | None = None, pdf_requests: Iterable[object] = ()) -> IEEEPaper:
        if isinstance(source, str):
            if page_url is None:
                _fail()
            return self.parse_html(source, page_url=page_url, pdf_requests=pdf_requests)
        return self.parse_page(source)

    @staticmethod
    def _request_parts(request: object) -> tuple[str, str, Mapping[str, str]]:
        if isinstance(request, str):
            return request, "GET", {}
        if isinstance(request, Mapping):
            raw_url = request.get("url", "")
            method = str(request.get("method", "GET"))
            raw_headers = request.get("headers", {})
        else:
            raw_url = getattr(request, "url", "")
            method = str(getattr(request, "method", "GET"))
            raw_headers = getattr(request, "headers", {})
        if callable(raw_url):
            raw_url = raw_url()
        if callable(raw_headers):
            raw_headers = raw_headers()
        headers = {str(key).casefold(): str(value) for key, value in (raw_headers.items() if isinstance(raw_headers, Mapping) else ())}
        return (str(raw_url) if raw_url else ""), method, headers


def parse_ieee_page(
    source: object,
    page_url: str | None = None,
    *,
    pdf_requests: Iterable[object] = (),
) -> IEEEPaper:
    """Parse injected HTML, a mapping, or a Playwright-like page fake."""

    if isinstance(source, str):
        return IEEEPaperParser().parse_html(source, page_url=page_url or IEEE_ORIGIN + "/", pdf_requests=pdf_requests)
    if isinstance(source, Mapping):
        markup = source.get("html") or source.get("content") or ""
        supplied_url = source.get("url") or page_url or IEEE_ORIGIN + "/"
        requests = [*source.get("requests", ()), *pdf_requests]
        return IEEEPaperParser().parse_html(str(markup), page_url=str(supplied_url), pdf_requests=requests)
    if page_url is not None:
        return IEEEPaperParser().parse_html(str(getattr(source, "content", "")), page_url=page_url, pdf_requests=pdf_requests)
    return IEEEPaperParser().parse_page(source)


IEEEPaperParseResult = IEEEPaper
IEEEPaper = IEEEPaper

__all__ = [
    "IEEE_ORIGIN",
    "IEEE_PARSE_FAILED",
    "IEEEP​​aperParseError",
    "IEEEP​​aper",
    "IEEEPaperParseResult",
    "IEEEPaper",
    "IEEEParseResult",
    "IEEEP​​aperParser",
    "parse_ieee_page",
]

# Keep public adapter names explicit for dependency-injection callers.
__all__ = [
    "IEEE_ORIGIN",
    "IEEE_PARSE_FAILED",
    "IEEE" + "PaperParseError",
    "IEEE" + "Paper",
    "IEEE" + "PaperParseResult",
    "IEEEParseResult",
    "IEEE" + "PaperParser",
    "parse_ieee_page",
]
