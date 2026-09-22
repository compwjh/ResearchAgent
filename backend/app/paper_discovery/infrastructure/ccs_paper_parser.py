"""ACM CCS 目录解析（Crossref work-list + OpenAlex work），纯函数、无网络。

为什么单独一个 parser 模块：与 ``usenix_publication_source`` / ``usenix_paper_parser``
的分层保持一致——source 负责网络、条件抓取、增量与富化编排，parser 只做字节到领域记录的
纯变换，因此可以用真实固定样本离线测试。

数据来源与权威级别（spec-032「官方会议 > 官方 DOI 元数据 > 聚合书目来源」）：

- **Crossref**（ACM member ``320`` 自己提交的 DOI 元数据）→ ``AUTHORITY_OFFICIAL_DOI``：
  标题、作者、年份、DOI、容器标题、官方页面地址。
- **OpenAlex** → ``AUTHORITY_AGGREGATOR``：摘要、关键词、OA PDF 地址。
  聚合来源只补缺失字段，永不覆盖更高权威来源已写入的值。

Crossref 的 ``abstract`` 字段对 ACM 恒为 null（实测），摘要只能来自 OpenAlex。
``dl.acm.org`` 对普通 HTTP 请求返回 403，因此本模块**不抓取** ACM 页面，也不下载/探测 PDF：
``pdf_url`` 只是记录 OpenAlex 给出的 OA 地址，真正的下载仍走既有安全下载链。
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATOR,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    DEFAULT_SOURCE_AUTHORITY,
    UNKNOWN_SOURCE_AUTHORITY,
    may_overwrite,
)
from backend.app.paper_discovery.infrastructure.openalex_enricher import _abstract_from_inverted_index

# Canonical Spec032 source ID/kind.  ``acm-ccs`` and ``acm_ccs`` remain readable
# through ``domain.source_authority.canonical_source_id`` for old cache rows.
CCS_SOURCE_ID = "ccs"
CCS_SOURCE_KIND = "ccs"
CROSSREF_SOURCE_ID = "crossref"
OPENALEX_SOURCE_ID = "openalex"
CROSSREF_HOST = "api.crossref.org"
OPENALEX_HOST = "api.openalex.org"
#: ACM 在 Crossref 的 member id（DOI 前缀 10.1145 的登记方）。
CROSSREF_MEMBER_ID = "320"
#: 逐年枚举用的书目查询串；容器标题漂移不影响它（漂移只在 container-title 上）。
CCS_BIBLIOGRAPHIC_QUERY = "ACM SIGSAC Conference on Computer and Communications Security"

CCS_PARSE_FAILED = "CCS_PARSE_FAILED"
CCS_INVALID_RESPONSE = "CCS_INVALID_RESPONSE"
#: 有条目但没有任何一条通过会议容器过滤——这是「标题漂移导致静默返回 0」的可观测信号。
CCS_VENUE_FILTER_EMPTY = "CCS_VENUE_FILTER_EMPTY"

# 旧值 3/2/1（数值越大越权威）与聚合 adapter 的 10/20/30 方向相反，已在 Task05 统一为
# domain/source_authority 的 10/20/30（数值越小越权威）；以下为兼容别名/映射。
CCS_OFFICIAL_DOI_AUTHORITY = AUTHORITY_OFFICIAL_DOI
CCS_AGGREGATOR_AUTHORITY = AUTHORITY_AGGREGATOR
#: 字段来源 → 权威级别。未知来源按最高权威处理（宁可少写，不可覆盖）。
SOURCE_AUTHORITY: Mapping[str, int] = dict(DEFAULT_SOURCE_AUTHORITY)
_UNKNOWN_SOURCE_AUTHORITY = UNKNOWN_SOURCE_AUTHORITY

DROP_FOREIGN_VENUE = "FOREIGN_VENUE"
DROP_NON_PAPER_TITLE = "NON_PAPER_TITLE"
DROP_FRONT_MATTER = "FRONT_MATTER"
DROP_INVITED_TALK = "INVITED_TALK"
DROP_MISSING_YEAR = "MISSING_YEAR"

ACM_DL_HOST = "dl.acm.org"
DOI_RESOLVER_HOST = "doi.org"

# 非论文条目：前言、研讨会（workshop）前言、海报、教程、主题演讲、讨论组、目录。
# 必须词边界 / 行首锚定：2019–2025 全量扫描确认
# 「Posterior Security」「Program Ingredients Abstraction」「… Concurrent Analysis」
# 「… Committee for Rollups」都是真论文，用 poster/abstract/committee 子串匹配会误杀。
_NON_PAPER_TITLE_RE = re.compile(
    r"\bworkshop\b"
    r"|^poster\b"
    r"|doctoral symposium"
    r"|^session details\b"
    r"|^tutorial\b"
    r"|^demo\b"
    r"|^keynote\b"
    r"|^preface\b"
    r"|^front matter\b"
    r"|^welcome\b"
    r"|^panel\b"
    r"|^table of contents\b"
    r"|^proceedings\b"
    r"|^abstracts?\s+of\b",
    re.IGNORECASE,
)

# 前言 / 整场会议条目只有 1–2 页正文（研讨会前言、Doctoral Symposium、keynote 摘要、
# 海报与 demo 摘要）。实测 2019–2025 主会容器下所有 ≤2 页条目均为非研究论文。
_FRONT_MATTER_MAX_PAGES = 2
# 邀请报告 / keynote：单作者且正文 ≤3 页。真论文即使单作者也有 12–13 页（2025 实测）。
_INVITED_TALK_MAX_PAGES = 3

_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_TAG_RE = re.compile(r"<[^>]+>")


class CcsPaperParseError(RuntimeError):
    """ACM CCS 载荷无法解析；``code`` 为稳定错误码。"""

    def __init__(self, message: str = "ACM CCS 数据无法解析", *, code: str = CCS_PARSE_FAILED) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = True


@dataclass(frozen=True)
class CcsCatalogRecord:
    """一条 CCS 目录记录；``provenance`` 逐字段记录来源 id。"""

    doi: str
    title: str
    authors: tuple[str, ...]
    year: int
    container_title: str
    article_url: str
    source_kind: str = CCS_SOURCE_KIND
    publication_stage: str = "published"
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    pdf_url: str | None = None
    pdf_access: str = "unknown"
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CcsDropped:
    """被过滤掉的条目，保留原因码便于审计。"""

    doi: str
    title: str
    reason: str


@dataclass(frozen=True)
class CcsCatalogResult:
    records: tuple[CcsCatalogRecord, ...] = ()
    dropped: tuple[CcsDropped, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CcsEnrichment:
    """OpenAlex 单篇作品补充信息（聚合来源，权威级别最低）。"""

    doi: str = ""
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    pdf_url: str | None = None
    is_oa: bool = False


# --- 文本与 URL 清洗 -----------------------------------------------------------


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []


def clean_title(value: Any) -> str:
    """把 Crossref 标题数组清洗成单行纯文本（去标签、解实体、折叠空白）。"""
    raw = " ".join(_text_list(value))
    return " ".join(html.unescape(_TAG_RE.sub(" ", raw)).split())


def container_title(item: Mapping[str, Any]) -> str:
    return clean_title(item.get("container-title"))


def _safe_record_url(raw: Any, *, hosts: Iterable[str] | None = None) -> str | None:
    """只接受无凭据、无 fragment、无控制字符的 https 地址。

    ``hosts`` 给定时做主机白名单（用于 ACM/DOI 官方页面）；为 ``None`` 时不限制主机
    （OpenAlex 的 OA PDF 可能托管在很多站点），但这里只**记录**该地址——真正的下载
    仍由既有安全下载链做 DNS/重定向/SSRF 校验，本适配器不发起任何 PDF 请求。
    """
    if not isinstance(raw, str) or not raw:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return None
    try:
        parts = urlsplit(html.unescape(raw.strip()))
        port = parts.port
    except (TypeError, ValueError):
        return None
    if parts.scheme.casefold() != "https" or not parts.hostname:
        return None
    if parts.username or parts.password or parts.fragment or port not in (None, 443):
        return None
    if hosts is not None and parts.hostname.casefold() not in {host.casefold() for host in hosts}:
        return None
    return f"https://{parts.hostname}{parts.path}"


def _acm_article_url(item: Mapping[str, Any], doi: str) -> str:
    """官方页面地址：优先 Crossref 里的 dl.acm.org 文章页，否则退回 doi.org 解析器。"""
    candidates: list[Any] = []
    links = item.get("link")
    if isinstance(links, list):
        candidates.extend(link.get("URL") for link in links if isinstance(link, Mapping))
    resource = item.get("resource")
    if isinstance(resource, Mapping):
        primary = resource.get("primary")
        if isinstance(primary, Mapping):
            candidates.append(primary.get("URL"))
    candidates.append(item.get("URL"))
    for candidate in candidates:
        url = _safe_record_url(candidate, hosts=(ACM_DL_HOST,))
        if url and "/doi/" in url and "/pdf" not in url.casefold():
            return url
    return f"https://{DOI_RESOLVER_HOST}/{doi}" if doi else ""


# --- 过滤规则 -----------------------------------------------------------------


def is_ccs_main_track(container: str, *, year: int | None = None) -> bool:
    """判断容器标题是否 CCS 主会论文集（模糊匹配，容忍 ACM 的标题漂移）。

    实测 2025 是 ``Proceedings of the 2025 ACM SIGSAC Conference ...``，2024 却是
    ``Proceedings of the 2024 **on** ACM SIGSAC Conference ...``（多一个 "on"），
    精确前缀匹配会让某些年份静默返回 0，所以只做短语级包含判断。

    必须同时含 ``sigsac``：仅凭 ``computer and communications security`` 会把
    ACM Asia Conference on Computer and Communications Security（AsiaCCS，
    实测 2024 有 143 条、2025 有 125 条）一起收进来。
    """
    normalized = " ".join(html.unescape(str(container or "")).split()).casefold()
    if not normalized:
        return False
    if "workshop" in normalized:
        return False
    if "computer and communications security" not in normalized:
        return False
    if "sigsac" not in normalized:
        return False
    return year is None or str(int(year)) in normalized


def is_ccs_research_paper(title: str) -> bool:
    """判断标题是否为研究论文（而非前言 / 海报 / 研讨会 / keynote 等条目）。"""
    cleaned = clean_title(title)
    if not cleaned:
        return False
    return _NON_PAPER_TITLE_RE.search(cleaned) is None


def page_span(item: Mapping[str, Any]) -> int | None:
    """条目正文页数；页码缺失或不是 ``起-止`` 形式时返回 ``None``。"""
    match = _PAGE_RANGE_RE.match(str(item.get("page") or ""))
    if match is None:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    return end - start + 1 if end >= start else None


def _author_names(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw = item.get("author")
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        given = " ".join(str(entry.get("given") or "").split())
        family = " ".join(str(entry.get("family") or "").split())
        name = " ".join(part for part in (given, family) if part).strip()
        if not name:
            name = " ".join(str(entry.get("name") or "").split())
        if name and name not in names:
            names.append(name)
    return tuple(names)


def drop_reason(item: Mapping[str, Any], *, year: int | None) -> str | None:
    """返回丢弃原因码，或 ``None`` 表示保留。

    判定顺序固定（先会议、再标题、再篇幅、最后形态），原因码因此可稳定断言。
    """
    if not is_ccs_main_track(container_title(item), year=year):
        return DROP_FOREIGN_VENUE
    if not is_ccs_research_paper(clean_title(item.get("title"))):
        return DROP_NON_PAPER_TITLE
    span = page_span(item)
    if span is not None and span <= _FRONT_MATTER_MAX_PAGES:
        return DROP_FRONT_MATTER
    if len(_author_names(item)) <= 1 and (span is None or span <= _INVITED_TALK_MAX_PAGES):
        return DROP_INVITED_TALK
    return None


# --- Crossref 目录解析 ---------------------------------------------------------


def _date_parts_year(item: Mapping[str, Any], key: str) -> int | None:
    value = item.get(key)
    if not isinstance(value, Mapping):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first = parts[0]
    if not isinstance(first, list) or not first:
        return None
    try:
        year = int(first[0])
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def _item_year(item: Mapping[str, Any]) -> int | None:
    for key in ("issued", "published-print", "published-online", "published", "created"):
        year = _date_parts_year(item, key)
        if year is not None:
            return year
    return None


def _crossref_items(payload: Any) -> tuple[list[Any], Mapping[str, Any]]:
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise CcsPaperParseError(code=CCS_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise CcsPaperParseError(code=CCS_INVALID_RESPONSE)
    message = payload.get("message")
    if not isinstance(message, Mapping):
        # 也接受直接传入 message 本体（含 items）的调用方式。
        message = payload if isinstance(payload.get("items"), list) else None
    if not isinstance(message, Mapping) or not isinstance(message.get("items"), list):
        raise CcsPaperParseError(code=CCS_INVALID_RESPONSE)
    return list(message["items"]), message


def _payload_year(items: Iterable[Any]) -> int | None:
    for item in items:
        if isinstance(item, Mapping):
            year = _item_year(item)
            if year is not None:
                return year
    return None


def _record(item: Mapping[str, Any], *, year: int) -> CcsCatalogRecord:
    doi = normalize_doi(item.get("DOI"))
    return CcsCatalogRecord(
        doi=doi,
        title=clean_title(item.get("title")),
        authors=_author_names(item),
        year=year,
        container_title=container_title(item),
        article_url=_acm_article_url(item, doi),
        provenance={
            "title": CROSSREF_SOURCE_ID,
            "authors": CROSSREF_SOURCE_ID,
            "year": CROSSREF_SOURCE_ID,
            "doi": CROSSREF_SOURCE_ID,
            "container_title": CROSSREF_SOURCE_ID,
            "article_url": CROSSREF_SOURCE_ID,
        },
    )


def parse_crossref_catalog(payload: Any, *, year: int | None = None) -> CcsCatalogResult:
    """解析一页 Crossref work-list，返回 CCS 主会研究论文与丢弃明细。

    ``year`` 为抓取单元年份；缺省时从条目 ``issued`` 推断，用于校验容器标题里的年份。
    """
    items, _ = _crossref_items(payload)
    resolved_year = int(year) if year is not None else _payload_year(items)
    records: list[CcsCatalogRecord] = []
    dropped: list[CcsDropped] = []
    venue_hits = 0
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if is_ccs_main_track(container_title(item), year=resolved_year):
            venue_hits += 1
        reason = drop_reason(item, year=resolved_year)
        if reason is None and _item_year(item) is None and resolved_year is None:
            reason = DROP_MISSING_YEAR
        if reason is not None:
            dropped.append(
                CcsDropped(
                    doi=normalize_doi(item.get("DOI")),
                    title=clean_title(item.get("title")),
                    reason=reason,
                )
            )
            continue
        records.append(_record(item, year=_item_year(item) or int(resolved_year or 0)))
    warnings = (CCS_VENUE_FILTER_EMPTY,) if items and not venue_hits else ()
    return CcsCatalogResult(tuple(records), tuple(dropped), warnings)


# --- OpenAlex 富化与合并 -------------------------------------------------------


def parse_openalex_work(payload: Any) -> CcsEnrichment:
    """解析 OpenAlex 单篇作品：摘要（倒排索引还原）、关键词、OA PDF。"""
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise CcsPaperParseError(code=CCS_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise CcsPaperParseError(code=CCS_INVALID_RESPONSE)
    if payload.get("id") is None and payload.get("doi") is None:
        raise CcsPaperParseError(code=CCS_INVALID_RESPONSE)
    keywords: list[str] = []
    raw_keywords = payload.get("keywords")
    if isinstance(raw_keywords, list):
        for entry in raw_keywords:
            name = " ".join(str(entry.get("display_name") or "").split()) if isinstance(entry, Mapping) else ""
            if name and name not in keywords:
                keywords.append(name)
    location = payload.get("best_oa_location")
    pdf_url = _safe_record_url(location.get("pdf_url")) if isinstance(location, Mapping) else None
    open_access = payload.get("open_access")
    is_oa = bool(open_access.get("is_oa")) if isinstance(open_access, Mapping) else False
    return CcsEnrichment(
        doi=normalize_doi(payload.get("doi")),
        # 倒排索引还原复用 openalex_enricher 里既有实现，避免第二套摘要重建逻辑。
        abstract=_abstract_from_inverted_index(payload.get("abstract_inverted_index")),
        keywords=tuple(keywords),
        pdf_url=pdf_url,
        is_oa=is_oa,
    )


def _may_write(existing_source: str | None, incoming_source: str) -> bool:
    """低权威来源不得覆盖高权威字段（spec-032 字段级 provenance 合同）。

    委托给 domain.source_authority.may_overwrite（唯一方向：数值越小越权威）。
    ``existing_source is None`` 表示该字段还没有归属来源 → 可写。来源 id 未知时按最高
    权威处理：宁可少写一次，也不能把未知（很可能是官方页面）的值覆盖掉。
    """
    return may_overwrite(existing_source, incoming_source)


def merge_enrichment(record: CcsCatalogRecord, enrichment: CcsEnrichment) -> CcsCatalogRecord:
    """用聚合来源补充缺失字段；已存在的字段（无论权威高低）一律不覆盖。

    双重保护：字段为空 + 现有来源权威严格低于写入来源。ACM 的 Crossref 摘要在实测中
    恒为 null，因此这里的「不覆盖」主要面向未来官方页面来源写入的高权威摘要。
    """
    provenance = dict(record.provenance)
    updates: dict[str, Any] = {}

    abstract = " ".join(str(enrichment.abstract or "").split())
    if abstract and not (record.abstract or "").strip() and _may_write(record.provenance.get("abstract"), OPENALEX_SOURCE_ID):
        updates["abstract"] = abstract
        provenance["abstract"] = OPENALEX_SOURCE_ID

    keywords = tuple(name for name in enrichment.keywords if name)
    if keywords and not record.keywords and _may_write(record.provenance.get("keywords"), OPENALEX_SOURCE_ID):
        updates["keywords"] = keywords
        provenance["keywords"] = OPENALEX_SOURCE_ID

    pdf_url = _safe_record_url(enrichment.pdf_url)
    if pdf_url and not record.pdf_url and _may_write(record.provenance.get("pdf_url"), OPENALEX_SOURCE_ID):
        updates["pdf_url"] = pdf_url
        updates["pdf_access"] = "public"
        provenance["pdf_url"] = OPENALEX_SOURCE_ID

    if not updates:
        return record
    return replace(record, provenance=provenance, **updates)


class CcsCatalogParser:
    """对象式入口，便于注入；行为与模块级函数完全一致。"""

    def parse_catalog(self, payload: Any, *, year: int | None = None) -> CcsCatalogResult:
        return parse_crossref_catalog(payload, year=year)

    def parse_enrichment(self, payload: Any) -> CcsEnrichment:
        return parse_openalex_work(payload)

    def merge(self, record: CcsCatalogRecord, enrichment: CcsEnrichment) -> CcsCatalogRecord:
        return merge_enrichment(record, enrichment)


__all__ = [
    "AUTHORITY_AGGREGATOR",
    "AUTHORITY_OFFICIAL_DOI",
    "AUTHORITY_OFFICIAL_VENUE",
    "CCS_AGGREGATOR_AUTHORITY",
    "CCS_BIBLIOGRAPHIC_QUERY",
    "CCS_INVALID_RESPONSE",
    "CCS_OFFICIAL_DOI_AUTHORITY",
    "CCS_PARSE_FAILED",
    "CCS_SOURCE_ID",
    "CCS_SOURCE_KIND",
    "CCS_VENUE_FILTER_EMPTY",
    "CROSSREF_HOST",
    "CROSSREF_MEMBER_ID",
    "CROSSREF_SOURCE_ID",
    "CcsCatalogParser",
    "CcsCatalogRecord",
    "CcsCatalogResult",
    "CcsDropped",
    "CcsEnrichment",
    "CcsPaperParseError",
    "DROP_FOREIGN_VENUE",
    "DROP_FRONT_MATTER",
    "DROP_INVITED_TALK",
    "DROP_MISSING_YEAR",
    "DROP_NON_PAPER_TITLE",
    "OPENALEX_HOST",
    "OPENALEX_SOURCE_ID",
    "SOURCE_AUTHORITY",
    "clean_title",
    "container_title",
    "drop_reason",
    "is_ccs_main_track",
    "is_ccs_research_paper",
    "merge_enrichment",
    "page_span",
    "parse_crossref_catalog",
    "parse_openalex_work",
]
