"""NDSS Symposium 官方目录适配器（spec-032 Task04）。

真实页面结构（2026 实测）：

- 列表页 ``https://www.ndss-symposium.org/ndss{year}/accepted-papers/``
  每个条目是 ``<div class="pt-cv-content-item ...">``，标题在
  ``<h2 class="pt-cv-title"><a href="/ndss-paper/<slug>/">Title</a></h2>``，
  作者在 ``<div class="pt-cv-ctf-display_authors">…<p>姓名 (单位), …</p>``。
  列表页只有标题 + 作者，**没有摘要和 PDF**。
- 详情页 ``https://www.ndss-symposium.org/ndss-paper/<slug>/``
  标题是首个 ``<h1>``；``<div class="paper-data">`` 的第一个 ``<p>`` 是作者、
  第二个（及之后）是摘要（含 ``<br />`` 与 ``textbf{…}`` 这类 LaTeX 残留）；
  PDF 在 ``<a class="… pdf-button" href="…/wp-content/uploads/…-paper.pdf">``。

安全约束与 USENIX 源一致：只接受 ``www.ndss-symposium.org`` 官方域名与固定
路径形态，任意 URL 一律拒绝且不发起请求。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable, List, Optional, Tuple

import httpx

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_title

NDSS_HOST = "www.ndss-symposium.org"
NDSS_ORIGIN = f"https://{NDSS_HOST}"
LISTING_RE = re.compile(r"^https://www\.ndss-symposium\.org/ndss(?P<year>\d{4})/accepted-papers/?$")
DETAIL_RE = re.compile(r"^https://www\.ndss-symposium\.org/ndss-paper/(?P<slug>[a-z0-9-]+)/?$")

NDSS_LIST_URL_REJECTED = "NDSS_LIST_URL_REJECTED"
NDSS_DETAIL_URL_REJECTED = "NDSS_DETAIL_URL_REJECTED"
NDSS_FETCH_FAILED = "NDSS_FETCH_FAILED"
NDSS_PARSE_FAILED = "NDSS_PARSE_FAILED"


@dataclass(frozen=True)
class NdssPaper:
    """一条 NDSS 目录记录（列表页字段 + 可选详情字段）。"""

    title: str
    article_url: str
    authors: Tuple[str, ...] = ()
    year: Optional[int] = None
    abstract: str = ""
    official_pdf_url: str = ""
    source_kind: str = "ndss"
    raw: dict = field(default_factory=dict)

    def __getitem__(self, key: str):
        return getattr(self, key)


def listing_url(year: int) -> str:
    return f"{NDSS_ORIGIN}/ndss{int(year)}/accepted-papers/"


def _clean_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value or "")
    # 真实页面里 LaTeX 命令的反斜杠常常已被站点吞掉，故反斜杠可选。
    text = re.sub(r"\\?(?:textbf|textit|emph|texttt)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_abstract(value: str) -> str:
    text = _clean_text(value)
    # 摘要段落之间的句号粘连（"end.Start"）补一个空格，便于阅读与后续切分。
    text = re.sub(r"(?<=[a-z0-9\)])\.(?=[A-Z])", ". ", text)
    return text.strip()


def _split_authors(value: str) -> Tuple[str, ...]:
    """把 ``姓名 (单位), 姓名 (单位)`` 解析为纯姓名元组。"""
    text = _clean_text(value)
    if not text:
        return ()
    names: List[str] = []
    for chunk in re.split(r",(?![^(]*\))", text):
        name = re.sub(r"\([^)]*\)", "", chunk).strip(" ,;")
        name = re.sub(r"\s+", " ", name)
        if name and name.lower() not in {"and", "et al."}:
            names.append(name)
    return tuple(names)


class _ListParser(HTMLParser):
    """解析 accepted-papers 列表页：标题 + 详情页 URL + 作者。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.papers: List[NdssPaper] = []
        self._depth = 0
        self._item_depth: Optional[int] = None
        self._in_title = False
        self._in_authors = False
        self._authors_depth: Optional[int] = None
        self._buffer: List[str] = []
        self._title = ""
        self._url = ""
        self._authors = ""

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        attrs = dict(attrs or {})
        classes = (attrs.get("class") or "").split()
        self._depth += 1
        if tag == "div" and "pt-cv-content-item" in classes and self._item_depth is None:
            self._item_depth = self._depth
            self._title, self._url, self._authors = "", "", ""
            return
        if self._item_depth is None:
            return
        if tag == "h2" and "pt-cv-title" in classes:
            self._in_title = True
            self._buffer = []
        elif tag == "a" and self._in_title and not self._url:
            self._url = (attrs.get("href") or "").strip()
        elif tag == "div" and "pt-cv-ctf-display_authors" in classes and self._authors_depth is None:
            self._authors_depth = self._depth
            self._in_authors = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_title or self._in_authors:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "h2":
            self._title = "".join(self._buffer).strip()
            self._in_title = False
        elif self._in_authors and tag == "div" and self._authors_depth == self._depth:
            self._authors = "".join(self._buffer)
            self._in_authors = False
            self._authors_depth = None
        if tag in {"div", "h2"} and self._item_depth == self._depth:
            self._emit()
            self._item_depth = None
        self._depth -= 1

    def _emit(self) -> None:
        title = self._title.strip()
        url = self._url.strip()
        if not title or not url:
            return
        year = _year_from_url(url) or _year_from_url(self._url)
        self.papers.append(
            NdssPaper(
                title=title,
                article_url=url,
                authors=_split_authors(self._authors),
                year=year,
                raw={"authors_text": self._authors.strip()},
            )
        )


def _year_from_url(url: str) -> Optional[int]:
    match = re.search(r"/ndss(?:-paper/|)(\d{4})|/ndss(\d{4})", url or "")
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return int(value) if value else None


def parse_ndss_list(html: str, *, page_url: str = "") -> Tuple[NdssPaper, ...]:
    """解析 accepted-papers 列表页。页内无摘要/PDF，需再抓详情页。"""
    if not (html or "").strip():
        return ()
    parser = _ListParser()
    parser.feed(html)
    parser.close()
    year = _year_from_url(page_url)
    papers: List[NdssPaper] = []
    seen: set[str] = set()
    for paper in parser.papers:
        key = paper.article_url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        papers.append(paper if paper.year or year is None else NdssPaper(**{**paper.__dict__, "year": year}))
    return tuple(papers)


class _DetailParser(HTMLParser):
    """解析 ndss-paper 详情页：h1 标题、paper-data 作者/摘要、PDF 按钮。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.paragraphs: List[str] = []
        self.pdf_url = ""
        self.year: Optional[int] = None
        self._depth = 0
        self._in_h1 = False
        self._in_paper_data = False
        self._paper_data_depth: Optional[int] = None
        self._in_p = False
        self._buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        attrs = dict(attrs or {})
        classes = (attrs.get("class") or "").split()
        self._depth += 1
        if tag == "h1" and not self.title:
            self._in_h1 = True
            self._buffer = []
        elif tag == "div" and "paper-data" in classes and self._paper_data_depth is None:
            self._paper_data_depth = self._depth
            self._in_paper_data = True
        elif self._in_paper_data and tag == "p":
            self._in_p = True
            self._buffer = []
        elif tag == "a" and "pdf-button" in classes and not self.pdf_url:
            self.pdf_url = (attrs.get("href") or "").strip()
        # 年份挂在文章节点（``category-ndss-YYYY``）上而非 <body>，任何元素都可能是载体。
        if self.year is None:
            self.year = _year_from_body_class(attrs.get("class") or "")

    def handle_data(self, data: str) -> None:
        if self._in_h1 or self._in_p:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_h1 and tag == "h1":
            self.title = "".join(self._buffer).strip()
            self._in_h1 = False
        if self._in_p and tag == "p":
            text = "".join(self._buffer)
            self.paragraphs.append(text)
            self._in_p = False
        if self._in_paper_data and tag == "div" and self._paper_data_depth == self._depth:
            self._in_paper_data = False
            self._paper_data_depth = None
        self._depth -= 1


def _year_from_body_class(value: str) -> Optional[int]:
    match = re.search(r"category-ndss-(\d{4})", value or "")
    return int(match.group(1)) if match else None


def parse_ndss_detail(html: str, *, page_url: str = "") -> NdssPaper:
    """解析详情页；解析不出标题即抛 ``ValueError``（与 USENIX 解析器同口径）。"""
    if not (html or "").strip():
        raise ValueError(NDSS_PARSE_FAILED)
    parser = _DetailParser()
    parser.feed(html)
    parser.close()
    title = parser.title.strip()
    if not title:
        raise ValueError(NDSS_PARSE_FAILED)
    authors = _split_authors(parser.paragraphs[0]) if parser.paragraphs else ()
    abstract = _clean_abstract(" ".join(parser.paragraphs[1:])) if len(parser.paragraphs) > 1 else ""
    pdf_url = parser.pdf_url
    if not pdf_url:
        match = re.search(r"https://www\.ndss-symposium\.org/wp-content/uploads/[^\"' )]+\.pdf", html)
        pdf_url = match.group(0) if match else ""
    return NdssPaper(
        title=title,
        article_url=(page_url or "").strip(),
        authors=authors,
        year=parser.year,
        abstract=abstract,
        official_pdf_url=pdf_url,
        raw={"paragraphs": len(parser.paragraphs)},
    )


class NdssAcceptedSource:
    """NDSS 官方目录源：只做目录发现与详情抓取，不下载 PDF。"""

    source_kind = "ndss"
    user_agent = "ResearchAgent-Spec032/1.0 (NDSS)"

    def __init__(self, *, timeout: float = 20.0, interval: float = 1.0,
                 client: Optional[httpx.Client] = None):
        self.timeout = timeout
        self.interval = max(0.0, interval)
        self._client = client

    # -- URL 白名单 ------------------------------------------------------
    @staticmethod
    def listing_url_ok(url: str) -> Optional[str]:
        value = (url or "").strip()
        return value if LISTING_RE.match(value) else None

    @staticmethod
    def detail_url_ok(url: str) -> Optional[str]:
        value = (url or "").strip()
        return value if DETAIL_RE.match(value) else None

    # -- 抓取 ------------------------------------------------------------
    def fetch_listing(self, year: int) -> Tuple[Optional[Tuple[NdssPaper, ...]], Optional[str]]:
        url = listing_url(year)
        text, error = self._get(url)
        if text is None:
            return None, error
        try:
            return parse_ndss_list(text, page_url=url), None
        except Exception:
            return None, NDSS_PARSE_FAILED

    def fetch_paper_detail(self, url: Any) -> dict[str, Any]:
        """抓取一个白名单内的 NDSS 详情页并返回扁平字典（与 USENIX 契约一致）。"""
        safe_url = url if isinstance(url, str) else ""
        if self.detail_url_ok(safe_url) is None:
            return {
                "ok": False, "url": safe_url, "error_code": NDSS_DETAIL_URL_REJECTED,
                "error": "只接受 NDSS 官方论文详情页（https://www.ndss-symposium.org/ndss-paper/<slug>/）",
            }
        text, error_code = self._get(safe_url)
        if text is None:
            return {"ok": False, "url": safe_url, "error_code": error_code or NDSS_FETCH_FAILED,
                    "error": f"详情页抓取失败：{error_code or NDSS_FETCH_FAILED}"}
        try:
            paper = parse_ndss_detail(text, page_url=safe_url)
        except Exception:
            return {"ok": False, "url": safe_url, "error_code": NDSS_PARSE_FAILED,
                    "error": "详情页解析失败（页面结构可能已变化）"}
        return {
            "ok": True, "url": safe_url, "error_code": None, "error": None,
            "title": paper.title, "authors": list(paper.authors), "abstract": paper.abstract,
            "official_pdf_url": paper.official_pdf_url, "year": paper.year,
            "source_kind": self.source_kind,
        }

    def _get(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        client = self._client
        owns = False
        if client is None:
            client = httpx.Client(timeout=self.timeout, trust_env=False, follow_redirects=True)
            owns = True
        try:
            response = client.get(url, headers={"User-Agent": self.user_agent})
        except httpx.HTTPError:
            return None, NDSS_FETCH_FAILED
        finally:
            if owns:
                client.close()
        if response.status_code != 200:
            return None, NDSS_FETCH_FAILED
        return response.text, None

    def discover(self, years: Iterable[int]) -> dict[int, Tuple[NdssPaper, ...]]:
        """按年份发现列表页论文（不抓详情）。单年失败不影响其它年份。"""
        found: dict[int, Tuple[NdssPaper, ...]] = {}
        for year in years:
            papers, _error = self.fetch_listing(int(year))
            if papers:
                found[int(year)] = papers
        return found

    @staticmethod
    def normalize_identity(paper: NdssPaper) -> str:
        return f"title:{normalize_title(paper.title)}:{paper.year or ''}"
