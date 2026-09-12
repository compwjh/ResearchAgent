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

# Only the Drupal field below carries the paper abstract on presentation pages.
# ``description`` is a separate site-wide Open Access notice and must not match.
_PAPER_DESCRIPTION_RE = re.compile(r"(?:^|\s)field-name-field-paper-description(?:\s|$)")
_VOID_ELEMENTS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "wbr"})

# Drupal field classes holding the author list / abstract on accepted-paper
# listing pages. Real usenix.org pages put the class on an outer ``<div>`` and
# leave the inner ``<p>`` class-less, so the match is done on the class token
# set (not on a ``<p>``-only substring) and accepts both the full
# ``field-name-…`` form and the legacy short form used by older fixtures.
_PEOPLE_FIELD_CLASSES = frozenset({"field-name-field-paper-people-text", "field-paper-people-text"})
_DESC_FIELD_CLASSES = frozenset({"field-name-field-paper-description-long", "field-paper-description-long"})

# Drupal wraps a paper in ``<article class="node node-paper view-mode-…">``.
# Listing pages use ``view-mode-schedule``, presentation detail pages
# ``view-mode-full``. The two modes are kept apart on purpose: real listing
# pages also contain ``view-mode-full`` articles, so widening the listing match
# would collect papers the listing must not report.
_DETAIL_ARTICLE_CLASSES = ("node-paper", "view-mode-full")

# USENIX appends the site name to the document ``<title>`` ("… | USENIX",
# occasionally "… - USENIX"). Only that trailing site segment is dropped: the
# separator must be whitespace-delimited and the segment must be a short,
# site-like name mentioning USENIX, so a ``|`` or ``-`` belonging to the paper
# title itself is never removed.
_TITLE_SITE_SUFFIX_RE = re.compile(
    r"\s+[|\u2013\u2014-]\s+(?P<site>[A-Za-z0-9&.'\u2019-]+(?:\s+[A-Za-z0-9&.'\u2019-]+)?)$"
)


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
        self.abstract: list[str] = []
        self._contexts: list[tuple[str, str, list[str], str]] = []
        self._description_tag = ""
        self._description_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        tag = tag.casefold()
        if self._description_depth:
            # Inside .field-name-field-paper-description: ignore every nested
            # tag and capture text raw. A stray unclosed tag therefore cannot
            # leak the site-wide ``.description`` notice into the abstract.
            if tag in _VOID_ELEMENTS:
                # Block-level void tags separate fragments; keep them apart so
                # the whitespace collapse cannot join two words.
                self.abstract.append(" ")
            return
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
            # ``<h1>`` holds the clean paper title on presentation pages, while
            # the document ``<title>`` appends the site name ("… | USENIX").
            # They are kept under separate meta keys so the caller can prefer
            # the clean one; document order alone would hand it the suffixed
            # ``<title>``, which sits in ``<head>``.
            self._contexts.append((tag, "", [], "h1" if tag == "h1" else "title"))
        elif "author" in classes or values.get("rel", "").casefold() == "author":
            self._contexts.append((tag, "", [], "author"))
        if tag == "link" and values.get("href"):
            label = " ".join(value for value in (values.get("rel", ""), values.get("type", "")) if value)
            self.links.append((values["href"], label))
        elif _PAPER_DESCRIPTION_RE.search(values.get("class", "")):
            # Drupal standard field holding the paper abstract. The site-wide
            # <div class="description"> Open Access notice is deliberately
            # excluded: it is not the paper abstract.
            self._description_tag = tag
            self._description_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing <br/> separates text fragments; keep them apart so the
        # surrounding whitespace collapse cannot join two words.
        if self._description_depth:
            self.abstract.append(" ")
        else:
            self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data)
            if self._description_depth:
                self.abstract.append(data)
            for _, _, parts, _ in self._contexts:
                parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._description_depth:
            if tag == self._description_tag:
                # Track nesting of the field's own tag: the abstract ends at the
                # </div> that closes the field, which also makes a stray
                # unclosed inner tag harmless.
                self._description_depth -= 1
                if self._description_depth == 0:
                    self._description_tag = ""
            self.abstract.append(" ")
            return
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
            elif context_kind in {"title", "h1"}:
                self.meta.setdefault(context_kind, []).append(text_value)
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


def _without_site_suffix(value: str) -> str:
    """Drop a trailing ``" | USENIX"`` / ``" - USENIX"`` site name from a title."""
    candidate = value
    while True:
        match = _TITLE_SITE_SUFFIX_RE.search(candidate)
        if match is None or "usenix" not in match.group("site").casefold():
            return candidate
        candidate = candidate[: match.start()].rstrip()


def _detail_presentation_key(url: Any, *, base: str) -> str | None:
    """Canonical identity of a presentation link, or ``None`` if it is not one.

    The comparison runs through ``_safe_url`` so the allowlist stays the single
    URL authority: a relative href is resolved against *base*, the canonical
    ``https://www.usenix.org`` origin is rebuilt (which makes the scheme and host
    case-insensitive for free), and a link carrying a port, query, credentials or
    a foreign host is rejected rather than compared. A fragment never identifies
    a paper, so it is dropped, and a trailing ``/`` is ignored.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    safe = _safe_url(url.strip().split("#", 1)[0], base, presentation=True)
    return safe.rstrip("/") if safe else None


def _detail_authors_block(
    blocks: list[dict[str, Any]], *, page_url: str, title: str
) -> dict[str, Any] | None:
    """Select the block describing *this* page's paper.

    A presentation page may embed further ``node-paper view-mode-full`` blocks
    (sidebar / related-paper teasers) ahead of the paper's own block, so the
    first block is not necessarily the right one and taking it silently yields
    the sidebar authors. Identity is established by the block's recorded
    presentation href, then by a matching title; only when neither signal is
    available does the first block win — the historical behaviour, kept so a page
    without either signal still parses and fail-closed stays the single
    rejection path.
    """
    if not blocks:
        return None
    wanted = _detail_presentation_key(page_url, base=page_url)
    if wanted is not None:
        for block in blocks:
            if _detail_presentation_key(block["presentation"], base=page_url) == wanted:
                return block
    if title:
        for block in blocks:
            if " ".join(block["title"].split()) == title:
                return block
    return blocks[0]


def parse_usenix_detail(markup: str, *, page_url: str) -> UsenixAcceptedPaper:
    """Extract metadata and explicit official/prepublication PDF links.

    USENIX only emits the ``citation_*`` meta block on some presentation pages,
    so each required field has a fallback: the author list is read from the
    paper's ``.field-name-field-paper-people-text`` field through the very same
    block parser the listing path uses, and the year falls back to the
    conference code in the page URL (``usenixsecurity22`` -> 2022). The meta
    tags keep priority over both fallbacks, and a page where a required field
    stays missing is still rejected rather than returned half-filled.

    The title is taken from ``citation_title`` -> ``og:title`` -> ``<h1>`` ->
    document ``<title>``; the last one is cleaned of its trailing
    ``" | USENIX"`` site name.
    """
    page = _page(markup)
    article = _safe_url(page_url, USENIX_ORIGIN + "/")
    if not article or not _safe_url(article, article, presentation=True):
        raise UsenixPaperParseError()
    titles = page.meta.get("citation_title", []) + page.meta.get("og:title", []) + page.meta.get("h1", [])
    title = next((" ".join(value.split()).strip(" -|") for value in titles if value.strip()), "")
    if not title:
        # Last resort: the document ``<title>``, minus its trailing site name.
        # Only this source carries the "… | USENIX" suffix, so only it is
        # cleaned; the ``.strip(" -|")`` trimming is unchanged.
        title = next(
            (
                _without_site_suffix(" ".join(value.split())).strip(" -|")
                for value in page.meta.get("title", [])
                if value.strip()
            ),
            "",
        )
    authors = page.meta.get("citation_author", []) + page.meta.get("author", [])
    authors = tuple(dict.fromkeys(item.strip() for value in authors for item in re.split(r"[,;|]", value) if item.strip()))
    if not authors:
        # Reuse the listing block parser instead of a second people-field
        # implementation: it already owns the field detection, the ``<em>``
        # affiliation exclusion, the first-``<p>`` rule and the separator
        # normalisation.
        detail_blocks = _blocks(markup, article_classes=_DETAIL_ARTICLE_CLASSES).blocks
        block = _detail_authors_block(detail_blocks, page_url=article, title=title)
        if block is not None:
            authors = _split_authors(block["authors"])
    years = page.meta.get("citation_publication_date", []) + page.meta.get("date", [])
    year_match = re.search(r"\b(20\d{2})\b", " ".join(years + page.text))
    # Priority is meta -> page text -> conference code in the URL; the URL never
    # overrides a year that the page itself states.
    year = int(year_match.group(1)) if year_match else _year_from_page_url(article, markup=markup)
    if not title or not authors or year is None:
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
    abstract = " ".join("".join(page.abstract).split())
    return UsenixAcceptedPaper(article, title, authors, year, official, prepublication, abstract=abstract)


_PRESENTATION_RE = re.compile(r"^/conference/[^/]+/presentation/[^/]+/?$", re.I)
_CONFERENCE_RE = re.compile(r"^/conference/([^/]+)/")

# Block-level elements whose boundary separates two text fragments. ``_Blocks``
# inserts a space at each such boundary inside an open field frame, because the
# frame stores the raw text nodes it read: the paragraphs of one field would
# otherwise be glued together by the whitespace collapse (`<p>A.</p><p>B.</p>`
# reads as `A.B.`). Inline elements such as ``<em>`` are deliberately absent —
# they split a sentence, not a paragraph.
_BLOCK_BOUNDARY_ELEMENTS = frozenset({"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6"})


class _Blocks(HTMLParser):
    """Collect per-paper metadata from accepted-paper schedule blocks.

    Only ``<article>`` blocks whose class carries every token of
    ``article_classes`` are considered (default:
    ``("node-paper", "view-mode-schedule")`` — the listing layout; the
    presentation-detail path passes ``_DETAIL_ARTICLE_CLASSES`` instead).
    Within each block the title comes from the first ``<h2>``, authors from
    ``.field-name-field-paper-people-text`` and the abstract from
    ``.field-name-field-paper-description-long``. Those field classes are
    matched on **any** element, because real pages carry them on an outer
    ``<div>`` and nest the class-less ``<p>`` two levels deeper. The most
    specific presentation href is recorded but is never turned into a PDF path.

    Real pages wrap every affiliation in ``<em>`` (``…, <em>MIT;</em> …``), so
    text read while inside ``<em>`` is dropped for the people field — otherwise
    the affiliation would be split into fake authors. The abstract keeps its
    ``<em>`` text, where the emphasis is legitimate. Self-closing ``<em/>``
    tags keep the emphasis depth balanced through the inherited
    ``handle_startendtag`` (a start/end pair).

    The people field also repeats itself as several ``<p>`` elements: the first
    one holds the authors, the following ones hold award / honour banners
    (``<p style="font-weight: 600; font-style: italic;">Distinguished Paper
    Award Winner …</p>``). Only the **first** ``<p>`` is part of the author
    list, so a people frame stops collecting text as soon as a ``<p>`` closes.
    The abstract is never truncated this way.
    """

    # Elements that never carry an end tag in Drupal output; they must not
    # disturb the nesting counter below.
    _UNTAGGED_ELEMENTS = _VOID_ELEMENTS | frozenset({"link", "meta", "source", "track", "param"})

    def __init__(self, *, article_classes: tuple[str, ...] = ("node-paper", "view-mode-schedule")) -> None:
        super().__init__(convert_charrefs=True)
        self._article_classes = article_classes
        self.blocks: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._open_tags: list[str] = []
        self._emphasis_depth = 0

    def _current_block(self) -> dict[str, str] | None:
        for frame in reversed(self._stack):
            if frame["kind"] == "article":
                return frame["block"]
        return None

    def _innermost_field_frame(self, kind: str) -> dict[str, Any] | None:
        """Return the innermost field frame, but only if it has ``kind``.

        Mirrors ``handle_data``: the nearest title / people / desc frame owns
        the text, so a ``<p>`` inside the abstract must not be attributed to an
        outer people field (and vice versa).
        """
        for frame in reversed(self._stack):
            if frame["kind"] in ("title", "people", "desc"):
                return frame if frame["kind"] == kind else None
        return None

    def _open_people_paragraph(self) -> None:
        """Start collecting the author field's first ``<p>``; ignore later ones.

        USENIX renders the people field as one ``<p>`` with the authors followed
        by further ``<p>`` elements carrying award / honour banners. A people
        frame therefore collects only up to the first ``<p>``: the second and
        every later paragraph is dropped instead of becoming a fake author. A
        field with no ``<p>`` at all (legacy inline markup) is unaffected,
        because its frame starts out collecting.
        """
        frame = self._innermost_field_frame("people")
        if frame is None:
            return
        if frame["p_seen"]:
            frame["collecting"] = False
        else:
            frame["p_seen"] = True

    def _close_people_paragraph(self) -> None:
        """Stop collecting once the author field's first ``<p>`` closes."""
        frame = self._innermost_field_frame("people")
        if frame is not None:
            frame["collecting"] = False

    def _separate_open_field(self) -> None:
        """Add a separator at a block-level boundary inside the open field frame.

        Mirrors ``handle_data``'s ownership rule: the innermost ``title`` /
        ``people`` / ``desc`` frame owns the text. Only ``people`` and ``desc``
        are fields, so the ``title`` frame receives no separator (its text is
        already joined on close) and the ``article`` frame is never touched.
        """
        for frame in reversed(self._stack):
            if frame["kind"] in ("people", "desc"):
                frame["data"].append(" ")
                return
            if frame["kind"] == "title":
                return

    @staticmethod
    def _field_kind(classes: str) -> str | None:
        tokens = set(classes.split())
        if tokens & _PEOPLE_FIELD_CLASSES:
            return "people"
        if tokens & _DESC_FIELD_CLASSES:
            return "desc"
        return None

    def _pop_open_tag(self, tag: str) -> None:
        """Mirror the open-element stack, tolerating stray unclosed tags."""
        if not self._open_tags:
            return
        if self._open_tags[-1] == tag:
            self._open_tags.pop()
            return
        for index in range(len(self._open_tags) - 1, -1, -1):
            if self._open_tags[index] == tag:
                del self._open_tags[index:]
                return

    def _close_finished_fields(self) -> None:
        """Settle field frames whose element has already been closed.

        A frame records the nesting depth at which its field element opened, so
        the field ends when any end tag drops the depth below that value. This
        replaces the old literal ``</p>`` check, which never fired on real pages
        (the class sits on a ``<div>`` there) and would close too early if it
        counted only same-name tags.
        """
        depth = len(self._open_tags)
        for index in range(len(self._stack) - 1, -1, -1):
            frame = self._stack[index]
            if frame["kind"] not in ("people", "desc") or frame["depth"] <= depth:
                continue
            del self._stack[index:]
            block = self._current_block()
            if block is None:
                continue
            text = " ".join("".join(frame["data"]).split())
            if frame["kind"] == "people":
                # Real markup separates authors with a comma and terminates each
                # affiliation group with ``;`` (inside the dropped ``<em>``).
                # Rewrite the comma -- and the ``, and `` last-pair form -- to
                # the separator ``_split_authors`` already groups on, so its
                # splitting heuristic itself stays untouched.
                block["authors"] = re.sub(r"\s+and\s+|,", ";", text)
            else:
                block["abstract"] = text

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        tag = tag.casefold()
        if tag == "em":
            # Affiliations live in ``<em>``; the depth is consulted by
            # ``handle_data`` so their text never becomes an author.
            self._emphasis_depth += 1
        if tag not in self._UNTAGGED_ELEMENTS:
            self._open_tags.append(tag)
        if tag in _BLOCK_BOUNDARY_ELEMENTS:
            self._separate_open_field()
        if tag == "article":
            classes = (values.get("class", "") + " " + values.get("itemprop", "")).casefold()
            if all(token in classes for token in self._article_classes):
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
        kind = self._field_kind(values.get("class", "").casefold())
        if kind is not None:
            self._stack.append(
                {
                    "kind": kind,
                    "data": [],
                    "depth": len(self._open_tags),
                    # Only consulted for people frames: whether the field's first
                    # ``<p>`` was seen and whether text is still wanted.
                    "p_seen": False,
                    "collecting": True,
                }
            )
            return
        if tag == "p":
            self._open_people_paragraph()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        for frame in reversed(self._stack):
            if frame["kind"] in ("title", "people", "desc"):
                if frame["kind"] == "people" and (self._emphasis_depth or not frame["collecting"]):
                    # Emphasis inside the author field is an affiliation, and
                    # text after the field's first ``<p>`` is an award banner:
                    # neither is a name, so drop it instead of feeding it to
                    # ``_split_authors``.
                    return
                frame["data"].append(data)
                return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "em" and self._emphasis_depth:
            self._emphasis_depth -= 1
        if tag not in self._UNTAGGED_ELEMENTS:
            self._pop_open_tag(tag)
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
        if tag == "p":
            self._close_people_paragraph()
        if tag in _BLOCK_BOUNDARY_ELEMENTS:
            self._separate_open_field()
        self._close_finished_fields()


def _blocks(markup: str, *, article_classes: tuple[str, ...] = ("node-paper", "view-mode-schedule")) -> _Blocks:
    if not isinstance(markup, str) or not markup.strip():
        raise UsenixPaperParseError()
    parser = _Blocks(article_classes=article_classes)
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
