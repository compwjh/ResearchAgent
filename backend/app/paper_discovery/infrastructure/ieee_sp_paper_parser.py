"""IEEE Symposium on Security and Privacy (S&P) 目录解析（Crossref work-list + OpenAlex work）。

纯函数、无网络，与 ``ccs_paper_parser`` / ``usenix_paper_parser`` 保持同一分层：source 负责网络、
条件抓取、增量与富化编排，parser 只做字节到领域记录的纯变换，因此可用真实固定样本离线测试。

数据来源与权威级别（spec-032「官方会议 > 官方 DOI 元数据 > 聚合书目来源」）：

- **Crossref**（IEEE member ``263`` 自己提交的 DOI 元数据）→ ``AUTHORITY_OFFICIAL_DOI``：
  标题、作者、年份、DOI、容器标题、IEEE Xplore 官方页面地址。
- **OpenAlex** → ``AUTHORITY_AGGREGATOR``：摘要、关键词、OA PDF 地址。
  聚合来源只补缺失字段，永不覆盖更高权威来源已写入的值。

与 ACM CCS 的关键差异（实测）：

1. **IEEE 的 Crossref member 是 263**（不是 ACM 的 320，也不是常被误用的 266）。
2. **必须排除 ``european``**：``IEEE European Symposium on Security and Privacy``（EuroS&P）是**另一个
   会议**，其容器标题同样包含 ``symposium on security and privacy``，不排除会污染 S&P 各年目录。
3. **前置页只能靠标题过滤**：IEEE 把 ``Keynotes`` / ``Title Page`` / ``Author Index`` /
   ``Organizing Committee`` / ``Table of Contents`` / ``Copyright Page`` / ``Message from the ...``
   等登记为 ``proceedings-article`` 且带 DOI。实测真实论文的 ``page`` 字段可能是 ``None`` 或
   ``起==止``（如 ``2032-2032``），因此**不能**用 CCS 的页数规则，否则会误杀真论文。

Crossref 的 ``abstract`` 字段对 IEEE 恒为 null（实测），摘要只能来自 OpenAlex。
``dl.ieee.org`` / Xplore 的 PDF 多为付费墙；本模块**不抓取** Xplore 页面、不下载/探测任何 PDF，
``pdf_url`` 只记录 OpenAlex 给出的 OA 地址，真正下载仍走既有安全下载链。
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.infrastructure.openalex_enricher import _abstract_from_inverted_index

IEEE_SP_SOURCE_ID = "ieee-sp"
IEEE_SP_SOURCE_KIND = "ieee_sp"
CROSSREF_SOURCE_ID = "crossref"
OPENALEX_SOURCE_ID = "openalex"
CROSSREF_HOST = "api.crossref.org"
OPENALEX_HOST = "api.openalex.org"
#: IEEE 在 Crossref 的 member id（DOI 前缀 10.1109 的登记方）。
CROSSREF_MEMBER_ID = "263"
#: 逐年枚举用的书目查询串；容器标题漂移不影响它（漂移只在 container-title 上）。
IEEE_SP_BIBLIOGRAPHIC_QUERY = "IEEE Symposium on Security and Privacy"

IEEE_SP_PARSE_FAILED = "IEEE_SP_PARSE_FAILED"
IEEE_SP_INVALID_RESPONSE = "IEEE_SP_INVALID_RESPONSE"
#: 有条目但没有任何一条通过会议容器过滤——这是「匹配规则失效导致静默返回 0」的可观测信号。
IEEE_SP_VENUE_FILTER_EMPTY = "IEEE_SP_VENUE_FILTER_EMPTY"

AUTHORITY_OFFICIAL_VENUE = 3
AUTHORITY_OFFICIAL_DOI = 2
AUTHORITY_AGGREGATOR = 1
IEEE_SP_OFFICIAL_DOI_AUTHORITY = AUTHORITY_OFFICIAL_DOI
IEEE_SP_AGGREGATOR_AUTHORITY = AUTHORITY_AGGREGATOR
#: 字段来源 → 权威级别。未知来源按最高权威处理（宁可少写，不可覆盖）。
SOURCE_AUTHORITY: Mapping[str, int] = {
    CROSSREF_SOURCE_ID: AUTHORITY_OFFICIAL_DOI,
    OPENALEX_SOURCE_ID: AUTHORITY_AGGREGATOR,
}
_UNKNOWN_SOURCE_AUTHORITY = AUTHORITY_OFFICIAL_VENUE

DROP_FOREIGN_VENUE = "FOREIGN_VENUE"
DROP_NON_PAPER_TITLE = "NON_PAPER_TITLE"
DROP_MISSING_YEAR = "MISSING_YEAR"

IEEE_XPLORE_HOST = "ieeexplore.ieee.org"
DOI_RESOLVER_HOST = "doi.org"

# 前置页 / 整场会议条目：IEEE 把它们登记为 proceedings-article 且带 DOI。
# 必须**锚定**（^...$），否则会把真论文误杀——实测 S&P 真论文里含 copyright 的有
# 「Copy, Right? A Testing Framework for Copyright Protection of Deep Learning Models」、
# 「PromptCARE: Prompt Copyright Protection...」、「SoK: Dataset Copyright Auditing...」；
# 短标题真论文有「Dropout Attacks」「Machine Unlearning」「Post-quantum WireGuard」。
_IEEE_SP_FRONT_MATTER_RE = re.compile(
    r"^author index$"
    r"|^copyright page$"
    r"|^copyright and reprint permissions$"
    r"|^\[?copyright notice\]?$"
    r"|^external reviewers$"
    r"|^keynotes?$"
    r"|^message from\b"
    r"|^organizing committee$"
    r"|^program committee$"
    r"|^table of contents$"
    r"|^\[?title page\b"
    r"|^front matter$"
    r"|^editorial\b"
    r"|^preface\b"
    r"|^welcome\b"
    r"|^session details\b"
    r"|^proceedings\b",
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")


class IeeeSpPaperParseError(RuntimeError):
    """IEEE S&P 载荷无法解析；``code`` 为稳定错误码。"""

    def __init__(self, message: str = "IEEE S&P 数据无法解析", *, code: str = IEEE_SP_PARSE_FAILED) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = True


@dataclass(frozen=True)
class IeeeSpCatalogRecord:
    """一条 S&P 目录记录；``provenance`` 逐字段记录来源 id。"""

    doi: str
    title: str
    authors: tuple[str, ...]
    year: int
    container_title: str
    article_url: str
    source_kind: str = IEEE_SP_SOURCE_KIND
    publication_stage: str = "published"
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    pdf_url: str | None = None
    pdf_access: str = "unknown"
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IeeeSpDropped:
    """被过滤掉的条目，保留原因码便于审计。"""

    doi: str
    title: str
    reason: str


@dataclass(frozen=True)
class IeeeSpCatalogResult:
    records: tuple[IeeeSpCatalogRecord, ...] = ()
    dropped: tuple[IeeeSpDropped, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IeeeSpEnrichment:
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

    ``hosts`` 给定时做主机白名单（用于 IEEE Xplore 官方页面）；为 ``None`` 时不限制主机
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


def _ieee_article_url(item: Mapping[str, Any], doi: str) -> str:
    """官方页面地址：优先 Crossref 里的 ieeexplore 文章页，否则退回 doi.org 解析器。

    IEEE 的 ``link[]`` 指向 ``http://xplorestaging.ieee.org/...pdf``（http + staging 主机 + PDF），
    既非官方页面也不应下载，因此**不**采纳；只接受 ``resource.primary.URL`` 上的 Xplore 文档页。
    """
    candidates: list[Any] = []
    resource = item.get("resource")
    if isinstance(resource, Mapping):
        primary = resource.get("primary")
        if isinstance(primary, Mapping):
            candidates.append(primary.get("URL"))
    candidates.append(item.get("URL"))
    for candidate in candidates:
        url = _safe_record_url(candidate, hosts=(IEEE_XPLORE_HOST,))
        if url and "/document/" in url:
            return url
    return f"https://{DOI_RESOLVER_HOST}/{doi}" if doi else ""


# --- 过滤规则 -----------------------------------------------------------------


def is_ieee_sp_main_track(container: str, *, year: int | None = None) -> bool:
    """判断容器标题是否 IEEE S&P 主会论文集（模糊匹配，容忍标题漂移）。

    必须同时满足：含 ``symposium on security and privacy``、含年份、**不含 ``european``**、
    不含 ``workshop``。实测容器标题形如 ``2024 IEEE Symposium on Security and Privacy (SP)``；
    EuroS&P（``... European Symposium on Security and Privacy (EuroS&P)``）与 EuroS&PW
    同样包含 ``symposium on security and privacy``，只有排除 ``european`` 才能挡掉。
    """
    normalized = " ".join(html.unescape(str(container or "")).split()).casefold()
    if not normalized:
        return False
    if "workshop" in normalized:
        return False
    if "european" in normalized:
        return False
    if "symposium on security and privacy" not in normalized:
        return False
    return year is None or str(int(year)) in normalized


def is_ieee_sp_research_paper(title: str) -> bool:
    """判断标题是否为研究论文（而非前言 / 委员会 / 目录 / keynote 等条目）。"""
    cleaned = clean_title(title)
    if not cleaned:
        return False
    return _IEEE_SP_FRONT_MATTER_RE.search(cleaned) is None


def drop_reason(item: Mapping[str, Any], *, year: int | None) -> str | None:
    """返回丢弃原因码，或 ``None`` 表示保留。

    判定顺序固定（先会议、再标题），原因码因此可稳定断言。**不**使用页数规则：IEEE 真论文的
    ``page`` 可能缺失或 ``起==止``，用页数过滤会误杀。
    """
    if not is_ieee_sp_main_track(container_title(item), year=year):
        return DROP_FOREIGN_VENUE
    if not is_ieee_sp_research_paper(clean_title(item.get("title"))):
        return DROP_NON_PAPER_TITLE
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
            raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE)
    message = payload.get("message")
    if not isinstance(message, Mapping):
        # 也接受直接传入 message 本体（含 items）的调用方式。
        message = payload if isinstance(payload.get("items"), list) else None
    if not isinstance(message, Mapping) or not isinstance(message.get("items"), list):
        raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE)
    return list(message["items"]), message


def _payload_year(items: Iterable[Any]) -> int | None:
    for item in items:
        if isinstance(item, Mapping):
            year = _item_year(item)
            if year is not None:
                return year
    return None


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


def _record(item: Mapping[str, Any], *, year: int) -> IeeeSpCatalogRecord:
    doi = normalize_doi(item.get("DOI"))
    return IeeeSpCatalogRecord(
        doi=doi,
        title=clean_title(item.get("title")),
        authors=_author_names(item),
        year=year,
        container_title=container_title(item),
        article_url=_ieee_article_url(item, doi),
        provenance={
            "title": CROSSREF_SOURCE_ID,
            "authors": CROSSREF_SOURCE_ID,
            "year": CROSSREF_SOURCE_ID,
            "doi": CROSSREF_SOURCE_ID,
            "container_title": CROSSREF_SOURCE_ID,
            "article_url": CROSSREF_SOURCE_ID,
        },
    )


def parse_crossref_catalog(payload: Any, *, year: int | None = None) -> IeeeSpCatalogResult:
    """解析一页 Crossref work-list，返回 S&P 主会研究论文与丢弃明细。

    ``year`` 为抓取单元年份；缺省时从条目 ``issued`` 推断，用于校验容器标题里的年份。
    """
    items, _ = _crossref_items(payload)
    resolved_year = int(year) if year is not None else _payload_year(items)
    records: list[IeeeSpCatalogRecord] = []
    dropped: list[IeeeSpDropped] = []
    venue_hits = 0
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if is_ieee_sp_main_track(container_title(item), year=resolved_year):
            venue_hits += 1
        reason = drop_reason(item, year=resolved_year)
        if reason is None and _item_year(item) is None and resolved_year is None:
            reason = DROP_MISSING_YEAR
        if reason is not None:
            dropped.append(
                IeeeSpDropped(
                    doi=normalize_doi(item.get("DOI")),
                    title=clean_title(item.get("title")),
                    reason=reason,
                )
            )
            continue
        records.append(_record(item, year=_item_year(item) or int(resolved_year or 0)))
    warnings = (IEEE_SP_VENUE_FILTER_EMPTY,) if items and not venue_hits else ()
    return IeeeSpCatalogResult(tuple(records), tuple(dropped), warnings)


# --- OpenAlex 富化与合并 -------------------------------------------------------


def parse_openalex_work(payload: Any) -> IeeeSpEnrichment:
    """解析 OpenAlex 单篇作品：摘要（倒排索引还原）、关键词、OA PDF。"""
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE)
    if payload.get("id") is None and payload.get("doi") is None:
        raise IeeeSpPaperParseError(code=IEEE_SP_INVALID_RESPONSE)
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
    return IeeeSpEnrichment(
        doi=normalize_doi(payload.get("doi")),
        # 倒排索引还原复用 openalex_enricher 里既有实现，避免第二套摘要重建逻辑。
        abstract=_abstract_from_inverted_index(payload.get("abstract_inverted_index")),
        keywords=tuple(keywords),
        pdf_url=pdf_url,
        is_oa=is_oa,
    )


def _may_write(existing_source: str | None, incoming_source: str) -> bool:
    """低权威来源不得覆盖高权威字段（spec-032 字段级 provenance 合同）。

    ``existing_source is None`` 表示该字段还没有归属来源 → 可写。来源 id 未知时按最高
    权威处理：宁可少写一次，也不能把未知（很可能是官方页面）的值覆盖掉。
    """
    if existing_source is None:
        return True
    existing = SOURCE_AUTHORITY.get(existing_source, _UNKNOWN_SOURCE_AUTHORITY)
    return existing < SOURCE_AUTHORITY.get(incoming_source, _UNKNOWN_SOURCE_AUTHORITY)


def merge_enrichment(record: IeeeSpCatalogRecord, enrichment: IeeeSpEnrichment) -> IeeeSpCatalogRecord:
    """用聚合来源补充缺失字段；已存在的字段（无论权威高低）一律不覆盖。

    双重保护：字段为空 + 现有来源权威严格低于写入来源。IEEE 的 Crossref 摘要在实测中
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


class IeeeSpCatalogParser:
    """对象式入口，便于注入；行为与模块级函数完全一致。"""

    def parse_catalog(self, payload: Any, *, year: int | None = None) -> IeeeSpCatalogResult:
        return parse_crossref_catalog(payload, year=year)

    def parse_enrichment(self, payload: Any) -> IeeeSpEnrichment:
        return parse_openalex_work(payload)

    def merge(self, record: IeeeSpCatalogRecord, enrichment: IeeeSpEnrichment) -> IeeeSpCatalogRecord:
        return merge_enrichment(record, enrichment)


__all__ = [
    "AUTHORITY_AGGREGATOR",
    "AUTHORITY_OFFICIAL_DOI",
    "AUTHORITY_OFFICIAL_VENUE",
    "CROSSREF_HOST",
    "CROSSREF_MEMBER_ID",
    "CROSSREF_SOURCE_ID",
    "DOI_RESOLVER_HOST",
    "DROP_FOREIGN_VENUE",
    "DROP_MISSING_YEAR",
    "DROP_NON_PAPER_TITLE",
    "IEEE_SP_AGGREGATOR_AUTHORITY",
    "IEEE_SP_BIBLIOGRAPHIC_QUERY",
    "IEEE_SP_INVALID_RESPONSE",
    "IEEE_SP_OFFICIAL_DOI_AUTHORITY",
    "IEEE_SP_PARSE_FAILED",
    "IEEE_SP_SOURCE_ID",
    "IEEE_SP_SOURCE_KIND",
    "IEEE_SP_VENUE_FILTER_EMPTY",
    "IEEE_XPLORE_HOST",
    "IeeeSpCatalogParser",
    "IeeeSpCatalogRecord",
    "IeeeSpCatalogResult",
    "IeeeSpDropped",
    "IeeeSpEnrichment",
    "IeeeSpPaperParseError",
    "OPENALEX_HOST",
    "OPENALEX_SOURCE_ID",
    "SOURCE_AUTHORITY",
    "clean_title",
    "container_title",
    "drop_reason",
    "is_ieee_sp_main_track",
    "is_ieee_sp_research_paper",
    "merge_enrichment",
    "parse_crossref_catalog",
    "parse_openalex_work",
]
