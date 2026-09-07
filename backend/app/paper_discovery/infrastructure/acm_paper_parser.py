"""Credential-safe ACM Digital Library page adapter.

Only injected HTML/page fakes are accepted; this module never performs network
requests or reads browser cookies/headers.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urljoin, urlsplit

from backend.app.paper_discovery.domain.paper_import_identity import canonical_doi

ACM_ORIGIN = "https://dl.acm.org"
ACM_PARSE_FAILED = "ACM_PARSE_FAILED"


class AcmPaperParseError(RuntimeError):
    def __init__(self, message: str = "ACM 页面结构无法解析") -> None:
        super().__init__(message)
        self.code = ACM_PARSE_FAILED
        self.message = message
        self.retryable = True


@dataclass(frozen=True)
class AcmPaperParseResult:
    pdf_url: str | None
    article_url: str
    title: str
    doi: str | None = None

    @property
    def pdf_access(self) -> str:
        return "public" if self.pdf_url else "unknown"


# Site adapters use a short result name in callers; keep both spellings
# available for integration code written before this parser was finalized.
AcmPaper = AcmPaperParseResult
ACMPaper = AcmPaperParseResult
ACMParseResult = AcmPaperParseResult


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.values: dict[str, list[str]] = {}
        self._title: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.casefold(): value for key, value in attrs if value is not None}
        if "href" in data:
            self.links.append(data["href"])
        for key in ("data-pdf-url", "data-download-url", "data-article-url", "citation_pdf_url"):
            if key in data:
                self.values.setdefault(key, []).append(data[key])
        if tag.casefold() == "meta":
            name = (data.get("name") or data.get("property") or "").casefold()
            content = data.get("content")
            if content:
                self.values.setdefault(name, []).append(content)
        if tag.casefold() in {"title", "h1"}:
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"title", "h1"}:
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)

    @property
    def title(self) -> str: return " ".join(self._title)


def _safe_url(raw: Any, base: str, *, require_doi: bool = True) -> str | None:
    if not isinstance(raw, str) or not raw or any(ord(char) < 32 for char in raw):
        return None
    try:
        parsed = urlsplit(urljoin(base or ACM_ORIGIN + "/", raw))
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if (parsed.scheme.casefold(), (parsed.hostname or "").casefold(), port) != ("https", "dl.acm.org", None):
        return None
    if parsed.username or parsed.password or parsed.fragment or parsed.query or "\\" in parsed.path:
        return None
    if not parsed.path.startswith("/") or (require_doi and not parsed.path.startswith("/doi/")):
        return None
    return f"{ACM_ORIGIN}{parsed.path}"


def _normal_title(value: Any) -> str:
    value = html_lib.unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s*[|–-]\s*ACM Digital Library\s*$", "", value, flags=re.I).strip()


def _doi(values: Iterable[Any]) -> str | None:
    for value in values:
        text = unquote(html_lib.unescape(str(value or "")).strip())
        match = re.search(r"10\.\d{4,9}/\S+", text, flags=re.I)
        if match:
            result = canonical_doi(match.group(0))
            if result:
                return result
    return None


def _page_input(source: Any) -> tuple[str, str, Iterable[Any]]:
    if isinstance(source, str):
        return source, ACM_ORIGIN + "/", ()
    if isinstance(source, Mapping):
        return (str(source.get("html") or source.get("content") or ""),
                str(source.get("url") or ACM_ORIGIN + "/"), source.get("requests", ()))
    content = getattr(source, "content", "")
    try:
        content = content() if callable(content) else content
    except Exception as exc:
        raise AcmPaperParseError() from exc
    page_url = getattr(source, "url", ACM_ORIGIN + "/")
    try:
        page_url = page_url() if callable(page_url) else page_url
    except Exception:
        page_url = ACM_ORIGIN + "/"
    requests = getattr(source, "pdf_requests", getattr(source, "requests", ()))
    if callable(requests):
        requests = requests()
    return str(content or ""), str(page_url or ACM_ORIGIN + "/"), requests or ()


def _request_parts(request: Any) -> tuple[str, str, Mapping[str, str]]:
    if isinstance(request, str):
        return request, "GET", {}
    if isinstance(request, Mapping):
        raw_url, method, raw_headers = request.get("url", ""), request.get("method", "GET"), request.get("headers", {})
    else:
        raw_url, method = getattr(request, "url", ""), getattr(request, "method", "GET")
        raw_headers = getattr(request, "headers", {})
    if callable(raw_url):
        raw_url = raw_url()
    if callable(raw_headers):
        raw_headers = raw_headers()
    headers = {str(key).casefold(): str(value) for key, value in (raw_headers.items() if isinstance(raw_headers, Mapping) else ())}
    return (str(raw_url or ""), str(method or "GET"), headers)


def parse_acm_page(source: Any, page_url: str | None = None, *, pdf_requests: Iterable[Any] = ()) -> AcmPaperParseResult:
    """Parse an ACM page or injectable fake, returning only allowlisted URLs."""
    try:
        markup, supplied_url, requests = _page_input(source)
    except AcmPaperParseError:
        raise
    except Exception as exc:
        raise AcmPaperParseError() from exc
    base = page_url or supplied_url
    requests = [*requests, *pdf_requests]
    if _safe_url(base, ACM_ORIGIN + "/", require_doi=False) is None:
        raise AcmPaperParseError()
    document = _Document()
    try:
        document.feed(markup)
        document.close()
    except Exception as exc:
        raise AcmPaperParseError() from exc
    article = _safe_url(base, ACM_ORIGIN + "/")
    article = article if article and "/pdf" not in urlsplit(article).path.casefold() else None
    pdf: str | None = None
    for raw in [*document.links, *sum(document.values.values(), [])]:
        safe = _safe_url(raw, base)
        if safe and any(token in urlsplit(safe).path.casefold() for token in ("/doi/pdf", "/doi/epdf", ".pdf")):
            pdf = pdf or safe
        elif safe and "/doi/" in urlsplit(safe).path.casefold() and "/pdf" not in urlsplit(safe).path.casefold():
            article = article or safe
    try:
        for request in requests:
            raw, method, headers = _request_parts(request)
            if any(name in {"cookie", "authorization"} for name in headers):
                raise AcmPaperParseError()
            if method.casefold() != "get":
                continue
            safe = _safe_url(raw, base, require_doi=False)
            if safe and (any(token in urlsplit(safe).path.casefold() for token in ("/doi/pdf", "/doi/epdf", ".pdf")) or "application/pdf" in headers.get("accept", "").casefold()):
                pdf = pdf or safe
    except AcmPaperParseError:
        raise
    except Exception as exc:
        raise AcmPaperParseError() from exc
    title_values = []
    for key in ("citation_title", "og:title", "dc.title", "title"):
        title_values.extend(document.values.get(key, []))
    title = _normal_title(title_values[0] if title_values else document.title)
    doi_values = []
    for key, values in document.values.items():
        if "doi" in key or key in {"dc.identifier", "citation_pdf_url"}:
            doi_values.extend(values)
    if article:
        path = unquote(urlsplit(article).path).split("/doi/", 1)[-1]
        parts = path.split("/")
        doi_values.append("/".join(parts[1:]) if parts and not parts[0].startswith("10.") else path)
    doi = _doi(doi_values)
    if not (article and title):
        raise AcmPaperParseError()
    return AcmPaperParseResult(pdf_url=pdf, article_url=article, title=title, doi=doi)


class AcmPaperParser:
    """Small object wrapper useful for dependency injection in task services."""

    def parse_html(self, page_html: str, *, page_url: str, pdf_requests: Iterable[Any] = ()) -> AcmPaperParseResult:
        return parse_acm_page(page_html, page_url, pdf_requests=pdf_requests)

    def parse_page(self, page: Any) -> AcmPaperParseResult:
        try:
            return parse_acm_page(page)
        except AcmPaperParseError:
            raise
        except Exception as exc:
            raise AcmPaperParseError() from exc

    def parse(self, source: Any, *, page_url: str | None = None, pdf_requests: Iterable[Any] = ()) -> AcmPaperParseResult:
        if isinstance(source, str):
            if page_url is None:
                raise AcmPaperParseError()
            return self.parse_html(source, page_url=page_url, pdf_requests=pdf_requests)
        return self.parse_page(source)


__all__ = ["ACM_ORIGIN", "ACM_PARSE_FAILED", "AcmPaperParseError", "AcmPaperParseResult", "AcmPaper", "ACMPaper", "ACMParseResult", "AcmPaperParser", "parse_acm_page"]
