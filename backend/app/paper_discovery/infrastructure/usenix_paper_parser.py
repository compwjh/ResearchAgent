"""Pure, allowlisted parser for USENIX accepted-paper pages."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

USENIX_ORIGIN = "https://www.usenix.org"
USENIX_PARSE_FAILED = "USENIX_PARSE_FAILED"


class UsenixPaperParseError(RuntimeError):
    code = USENIX_PARSE_FAILED
    retryable = True


@dataclass(frozen=True)
class UsenixAcceptedPaper:
    article_url: str
    title: str
    authors: tuple[str, ...]
    year: int
    official_pdf_url: str | None = None
    prepublication_pdf_url: str | None = None
    publication_stage: str = "accepted"
    source_kind: str = "usenix_accepted"
    abstract: str = ""
    keywords: tuple[str, ...] = ()

    @property
    def pdf_url(self) -> str | None:
        return self.official_pdf_url or self.prepublication_pdf_url

    @property
    def pdf_access(self) -> str:
        return "public" if self.pdf_url else "unknown"


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.meta: dict[str, list[str]] = {}
        self.text: list[str] = []
        self._contexts: list[tuple[str, str, list[str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        tag = tag.casefold()
        if tag == "meta":
            key = (values.get("name") or values.get("property") or values.get("itemprop") or "").casefold()
            value = values.get("content", "").strip()
            if key and value:
                self.meta.setdefault(key, []).append(html.unescape(value))
        if tag == "time" and values.get("datetime"):
            self.meta.setdefault("date", []).append(values["datetime"])
        if tag == "a" and values.get("href"):
            self._contexts.append((tag, values["href"], [], "link"))
        classes = (values.get("class", "") + " " + values.get("itemprop", "")).casefold()
        if tag in {"title", "h1"}:
            self._contexts.append((tag, "", [], "title"))
        elif "author" in classes or values.get("rel", "").casefold() == "author":
            self._contexts.append((tag, "", [], "author"))
        if tag == "link" and values.get("href"):
            label = " ".join(value for value in (values.get("rel", ""), values.get("type", "")) if value)
            self.links.append((values["href"], label))

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data)
            for _, _, parts, _ in self._contexts:
                parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._contexts) - 1, -1, -1):
            context_tag, href, parts, context_kind = self._contexts[index]
            if context_tag != tag:
                continue
            self._contexts.pop(index)
            text_value = " ".join("".join(parts).split())
            if context_kind == "link" and href:
                # Keep the explicit href separate from rendered link text.
                # The parser must never infer a USENIX PDF path from that text.
                self.links.append((href, text_value))
            elif context_kind == "title":
                self.meta.setdefault("title", []).append(text_value)
            elif context_kind == "author" and text_value:
                self.meta.setdefault("author", []).append(text_value)


def _page(markup: str) -> _Page:
    if not isinstance(markup, str) or not markup.strip():
        raise UsenixPaperParseError()
    parser = _Page()
    try:
        parser.feed(markup)
        parser.close()
    except Exception as error:
        raise UsenixPaperParseError() from error
    return parser


def _safe_url(raw: Any, base: str, *, presentation: bool = False) -> str | None:
    if not isinstance(raw, str) or not raw or any(ord(char) < 32 for char in raw):
        return None
    try:
        parsed = urlsplit(urljoin(base, html.unescape(raw.strip())))
        port = parsed.port
    except (TypeError, ValueError):
        return None
    path = parsed.path
    if (parsed.scheme, parsed.hostname, port) != ("https", "www.usenix.org", None):
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment or "\\" in path:
        return None
    if presentation and not re.match(r"^/conference/[^/]+/presentation/[^/]+/?$", path, re.I):
        return None
    return f"{USENIX_ORIGIN}{path}"


def parse_accepted_listing(markup: str, *, page_url: str) -> tuple[str, ...]:
    """Extract only explicit USENIX presentation links from an accepted list."""
    listing = _safe_url(page_url, USENIX_ORIGIN + "/")
    if not listing:
        raise UsenixPaperParseError()
    found: list[str] = []
    for href, _ in _page(markup).links:
        safe = _safe_url(href, listing, presentation=True)
        if safe and safe not in found:
            found.append(safe)
    return tuple(found)


def parse_usenix_detail(markup: str, *, page_url: str) -> UsenixAcceptedPaper:
    """Extract metadata and explicit official/prepublication PDF links."""
    page = _page(markup)
    article = _safe_url(page_url, USENIX_ORIGIN + "/")
    if not article or not _safe_url(article, article, presentation=True):
        raise UsenixPaperParseError()
    titles = page.meta.get("citation_title", []) + page.meta.get("og:title", []) + page.meta.get("title", [])
    title = next((" ".join(value.split()).strip(" -|") for value in titles if value.strip()), "")
    authors = page.meta.get("citation_author", []) + page.meta.get("author", [])
    authors = tuple(dict.fromkeys(item.strip() for value in authors for item in re.split(r"[,;|]", value) if item.strip()))
    years = page.meta.get("citation_publication_date", []) + page.meta.get("date", [])
    year_match = re.search(r"\b(20\d{2})\b", " ".join(years + page.text))
    if not title or not authors or not year_match:
        raise UsenixPaperParseError()
    official = prepublication = None
    for href, label in page.links:
        safe = _safe_url(href, article)
        if not safe or not safe.casefold().endswith(".pdf"):
            continue
        marker = f"{label} {safe}".casefold()
        if "prepub" in marker or "pre-publication" in marker or "prepublication" in marker:
            prepublication = prepublication or safe
        else:
            official = official or safe
    return UsenixAcceptedPaper(article, title, authors, int(year_match.group(1)), official, prepublication)


_PRESENTATION_RE = re.compile(r"^/conference/[^/]+/presentation/[^/]+/?$", re.I)
_CONFERENCE_RE = re.compile(r"^/conference/([^/]+)/")


class _Blocks(HTMLParser):
    """Collect per-paper metadata from accepted-paper schedule blocks.

    Only ``<article class="node node-paper view-mode-schedule">`` blocks are
    considered. Within each block the title comes from the first ``<h2>``,
    authors from ``.field-paper-people-text`` and the abstract from
    ``.field-paper-description-long``. The most specific presentation href is
    recorded but is never turned into a PDF path.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []

    def _current_block(self) -> dict[str, str] | None:
        for frame in reversed(self._stack):
            if frame["kind"] == "article":
                return frame["block"]
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        tag = tag.casefold()
        if tag == "article":
            classes = (values.get("class", "") + " " + values.get("itemprop", "")).casefold()
            if "node-paper" in classes and "view-mode-schedule" in classes:
                block = {"title": "", "authors": "", "abstract": "", "presentation": None}
                self.blocks.append(block)
                self._stack.append({"kind": "article", "block": block})
            return
        if tag == "h2":
            self._stack.append({"kind": "title", "data": []})
            return
        if tag == "a" and values.get("href"):
            block = self._current_block()
            if block is not None and block["presentation"] is None:
                href = html.unescape(values["href"].strip())
                if _PRESENTATION_RE.match(href):
                    block["presentation"] = values["href"]
            return
        if tag == "p":
            classes = values.get("class", "").casefold()
            if "field-paper-people-text" in classes:
                self._stack.append({"kind": "people", "data": []})
            elif "field-paper-description-long" in classes:
                self._stack.append({"kind": "desc", "data": []})

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        for frame in reversed(self._stack):
            if frame["kind"] in ("title", "people", "desc"):
                frame["data"].append(data)
                return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "article":
            while self._stack and self._stack[-1]["kind"] != "article":
                self._stack.pop()
            if self._stack and self._stack[-1]["kind"] == "article":
                self._stack.pop()
            return
        if tag == "h2" and self._stack and self._stack[-1]["kind"] == "title":
            frame = self._stack.pop()
            block = self._current_block()
            if block is not None and not block["title"]:
                block["title"] = " ".join("".join(frame["data"]).split())
            return
        if tag == "p" and self._stack and self._stack[-1]["kind"] in ("people", "desc"):
            frame = self._stack.pop()
            block = self._current_block()
            if block is not None:
                text = " ".join("".join(frame["data"]).split())
                if frame["kind"] == "people":
                    block["authors"] = text
                else:
                    block["abstract"] = text


def _blocks(markup: str) -> _Blocks:
    if not isinstance(markup, str) or not markup.strip():
        raise UsenixPaperParseError()
    parser = _Blocks()
    try:
        parser.feed(markup)
        parser.close()
    except Exception as error:
        raise UsenixPaperParseError() from error
    return parser


def _conference_code(page_url: str) -> str | None:
    try:
        match = _CONFERENCE_RE.match(urlsplit(page_url).path)
    except (TypeError, ValueError):
        return None
    return match.group(1) if match else None


def _year_from_page_url(page_url: str, *, markup: str) -> int | None:
    code = _conference_code(page_url)
    if code:
        digits = re.findall(r"\d{2}", code)
        if digits:
            candidate = 2000 + int(digits[-1])
            if 1990 <= candidate <= 2100:
                return candidate
    text_match = re.search(r"\b(19|20)\d{2}\b", markup)
    if text_match:
        return int(text_match.group(0))
    return None


def _split_authors(text: str) -> tuple[str, ...]:
    names: list[str] = []
    for group in re.split(r"\s*;\s*|\s+and\s+", text):
        name = " ".join(group.split(",", 1)[0].split())
        if name:
            names.append(name)
    return tuple(names)


def parse_accepted_papers(markup: str, *, page_url: str) -> tuple[UsenixAcceptedPaper, ...]:
    """Extract per-paper metadata from an accepted-paper listing page.

    Supports the cycle / summer / fall schedule layouts. The listing pages do
    not carry an explicit PDF href or an official keywords field, so the
    returned papers keep ``official_pdf_url`` / ``prepublication_pdf_url`` as
    ``None`` and ``keywords`` as an empty tuple; keywords are never inferred.
    """
    listing = _safe_url(page_url, USENIX_ORIGIN + "/")
    if not listing:
        raise UsenixPaperParseError()
    blocks = _blocks(markup)
    year = _year_from_page_url(listing, markup=markup)
    if year is None:
        raise UsenixPaperParseError()
    listing_code = _conference_code(listing)
    papers: list[UsenixAcceptedPaper] = []
    for block in blocks.blocks:
        if not block["title"] or block["presentation"] is None:
            continue
        article = _safe_url(block["presentation"], listing, presentation=True)
        if not article:
            continue
        if listing_code is not None:
            paper_code = _conference_code(article)
            if paper_code is None or paper_code != listing_code:
                continue
        papers.append(
            UsenixAcceptedPaper(
                article,
                block["title"],
                _split_authors(block["authors"]),
                year,
                abstract=block["abstract"],
            )
        )
    return tuple(papers)


parse_usenix_accepted_list = parse_accepted_listing


class UsenixAcceptedParser:
    def parse_listing(self, markup: str, *, page_url: str) -> tuple[str, ...]:
        return parse_accepted_listing(markup, page_url=page_url)

    def parse_detail(self, markup: str, *, page_url: str) -> UsenixAcceptedPaper:
        return parse_usenix_detail(markup, page_url=page_url)

    def parse_papers(self, markup: str, *, page_url: str) -> tuple[UsenixAcceptedPaper, ...]:
        return parse_accepted_papers(markup, page_url=page_url)


__all__ = ["USENIX_ORIGIN", "USENIX_PARSE_FAILED", "UsenixPaperParseError", "UsenixAcceptedPaper", "UsenixAcceptedParser", "parse_accepted_listing", "parse_usenix_accepted_list", "parse_usenix_detail", "parse_accepted_papers"]
