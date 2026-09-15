"""NDSS 目录解析（Crossref work-list + OpenAlex work），纯函数、无网络。

为什么单独一个 parser 模块：与 ``ccs_paper_parser`` / ``usenix_paper_parser`` 的分层一致——
source 负责网络、条件抓取、增量与富化编排，parser 只做字节到领域记录的纯变换，
因此可以用真实固定样本离线测试（样本见 ``tests/fixtures/ndss/README.md``）。

数据来源与权威级别（spec-032「官方会议 > 官方 DOI 元数据 > 聚合书目来源」）：

- **Crossref**（Internet Society 自己提交的 DOI 元数据，prefix ``10.14722``）→
  ``AUTHORITY_OFFICIAL_DOI``：标题、作者、年份、DOI、容器标题、官方 PDF 地址。
- **OpenAlex** → ``AUTHORITY_AGGREGATOR``：摘要、关键词。
  聚合来源只补缺失字段，永不覆盖更高权威来源已写入的值。

NDSS 的三个实测形态特点（决定了本模块与 ACM CCS 版本的差异）：

1. **容器标题年份在中间**：``Proceedings 2024 Network and Distributed System Security Symposium``，
   不是 ACM 的 ``Proceedings of the 2024 ACM SIGSAC ...``；短语级包含 + 年份即可匹配。
2. **Crossref 不提供 ``page``**（实测 615/615 条主会条目缺失），所以 CCS 的「正文 ≤2 页判前置页」
   规则在此**不适用**；前置页只能用**行首锚定**的标题规则过滤。实测主会容器下 615 条全是研究论文，
   真实前置页条目只出现在 co-located 容器里（例如 VehicleSec 的 ``Poster: ...``）。
   锚定是硬要求：真实主会论文里有 ``Welcome to Jurassic Park…``、``Front-running Attack…``、
   ``…Abstract Similarity``、``…Matter Controller``，未锚定的 ``welcome``/``abstract`` 会误杀。
3. OpenAlex 对 Internet Society 的提交把 **doi.org 解析地址**塞进 ``best_oa_location.pdf_url``，
   那不是 PDF；只有路径真正以 ``.pdf`` 结尾的地址才会被记录。

本模块**不抓取**任何会议页面，也不下载/探测 PDF：``pdf_url`` 只是记录官方地址
（Crossref 提交的 ``www.ndss-symposium.org`` PDF），真正的下载仍走既有安全下载链。
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

NDSS_SOURCE_ID = "ndss"
NDSS_SOURCE_KIND = "ndss"
CROSSREF_SOURCE_ID = "crossref"
OPENALEX_SOURCE_ID = "openalex"
CROSSREF_HOST = "api.crossref.org"
OPENALEX_HOST = "api.openalex.org"
#: NDSS 在 Crossref 的 DOI 前缀（Internet Society 登记，含 co-located 会议）。
NDSS_DOI_PREFIX = "10.14722"
#: 逐年枚举用的书目查询串；容器标题漂移不影响它（漂移只在 container-title 上）。
NDSS_BIBLIOGRAPHIC_QUERY = "Network and Distributed System Security Symposium"
#: 主会容器标题的必备短语（大小写不敏感，HTML 实体已解码）。
NDSS_CONTAINER_PHRASE = "network and distributed system security symposium"

NDSS_PARSE_FAILED = "NDSS_PARSE_FAILED"
NDSS_INVALID_RESPONSE = "NDSS_INVALID_RESPONSE"
#: 有条目但没有任何一条通过会议容器过滤——这是「容器标题变化导致静默返回 0」的可观测信号。
NDSS_VENUE_FILTER_EMPTY = "NDSS_VENUE_FILTER_EMPTY"

AUTHORITY_OFFICIAL_VENUE = 3
AUTHORITY_OFFICIAL_DOI = 2
AUTHORITY_AGGREGATOR = 1
NDSS_OFFICIAL_DOI_AUTHORITY = AUTHORITY_OFFICIAL_DOI
NDSS_AGGREGATOR_AUTHORITY = AUTHORITY_AGGREGATOR
#: 字段来源 → 权威级别。未知来源按最高权威处理（宁可少写，不可覆盖）。
SOURCE_AUTHORITY: Mapping[str, int] = {
    CROSSREF_SOURCE_ID: AUTHORITY_OFFICIAL_DOI,
    OPENALEX_SOURCE_ID: AUTHORITY_AGGREGATOR,
}
_UNKNOWN_SOURCE_AUTHORITY = AUTHORITY_OFFICIAL_VENUE

DROP_FOREIGN_VENUE = "FOREIGN_VENUE"
DROP_NON_PAPER_TITLE = "NON_PAPER_TITLE"
DROP_MISSING_YEAR = "MISSING_YEAR"

#: NDSS 官方论文托管主机（Internet Society 自提交的 primary resource）。
NDSS_PAPER_HOST = "www.ndss-symposium.org"
DOI_RESOLVER_HOST = "doi.org"

# 前置页 / 非论文条目：前言、研讨会、海报、教程、主题演讲、目录、索引。
# **必须行首锚定**：实测主会真论文含 "Welcome to Jurassic Park…"、"Front-running Attack…"、
# "…with Abstract Similarity"、"…Matter Controller"、"…Service Sessions…"，
# 未锚定的 welcome / abstract / front / session 子串匹配会误杀真论文。
_NON_PAPER_TITLE_RE = re.compile(
    r"^workshop\b"
    r"|^posters?\b"
    r"|^doctoral symposium\b"
    r"|^session details\b"
    r"|^tutorial\b"
    r"|^demo\b"
    r"|^keynote\b"
    r"|^preface\b"
    r"|^front matter\b"
    r"|^title page\b"
    r"|^author index\b"
    r"|^table of contents\b"
    # 只认「Welcome message/address/remarks/from …」这类前言标题；
    # 裸的 "^welcome" 会误杀 2025 真论文 "Welcome to Jurassic Park: …"。
    r"|^welcome (?:message|address|remarks|from)\b"
    r"|^panel\b"
    r"|^proceedings\b"
    r"|^abstracts?\s+of\b",
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")


class NdssPaperParseError(RuntimeError):
    """NDSS 载荷无法解析；``code`` 为稳定错误码。"""

    def __init__(self, message: str = "NDSS 数据无法解析", *, code: str = NDSS_PARSE_FAILED) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = True


@dataclass(frozen=True)
class NdssCatalogRecord:
    """一条 NDSS 目录记录；``provenance`` 逐字段记录来源 id。"""

    doi: str
    title: str
    authors: tuple[str, ...]
    year: int
    container_title: str
    article_url: str
    source_kind: str = NDSS_SOURCE_KIND
    publication_stage: str = "published"
    abstract: str | None = None
    keywords: tuple[str, ...] = ()
    pdf_url: str | None = None
    pdf_access: str = "unknown"
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NdssDropped:
    """被过滤掉的条目，保留原因码便于审计。"""

    doi: str
    title: str
    reason: str


@dataclass(frozen=True)
class NdssCatalogResult:
    records: tuple[NdssCatalogRecord, ...] = ()
    dropped: tuple[NdssDropped, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NdssEnrichment:
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

    ``hosts`` 给定时做主机白名单。为 ``None`` 时不限制主机（OpenAlex 的 OA 地址可能托管在
    很多站点），但这里只**记录**该地址——真正的下载仍由既有安全下载链做 DNS/重定向/SSRF 校验，
    本适配器不发起任何 PDF 请求。
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


def _ndss_pdf_url(item: Mapping[str, Any]) -> str | None:
    """官方论文 PDF：Crossref 提交的 ``www.ndss-symposium.org`` primary resource。

    只接受该主机下以 ``.pdf`` 结尾的路径；其他地址（例如 co-located 会议或第三方镜像）忽略。
    """
    resource = item.get("resource")
    if not isinstance(resource, Mapping):
        return None
    primary = resource.get("primary")
    if not isinstance(primary, Mapping):
        return None
    url = _safe_record_url(primary.get("URL"), hosts=(NDSS_PAPER_HOST,))
    if url and urlsplit(url).path.casefold().endswith(".pdf"):
        return url
    return None


# --- 过滤规则 -----------------------------------------------------------------


def is_ndss_main_track(container: str, *, year: int | None = None) -> bool:
    """判断容器标题是否 NDSS 主会论文集（短语级包含 + 年份，容忍标题漂移）。

    实测格式为 ``Proceedings 2024 Network and Distributed System Security Symposium``
    （年份在中间），因此只做短语级包含判断 + 年份出现判断，不做前缀匹配。

    必须包含**完整**短语 ``network and distributed system security symposium``：
    仅凭 ``symposium`` 会把 co-located 的 ``Proceedings 2024 Symposium on Usable Security``
    （USEC）与 ``Proceedings Symposium on Vehicle Security & Privacy``（VehicleSec）
    一起收进来——它们与 NDSS 同处 prefix ``10.14722``，是 NDSS 版的 EuroS&P 误收风险。

    同时排除含 ``workshop`` 的容器：co-located 研讨会同样注册在 ``10.14722`` 下，
    这是容器标题将来把 NDSS 写进 workshop 名称时的兜底。
    """
    normalized = " ".join(html.unescape(str(container or "")).split()).casefold()
    if not normalized:
        return False
    if "workshop" in normalized:
        return False
    if NDSS_CONTAINER_PHRASE not in normalized:
        return False
    return year is None or str(int(year)) in normalized


def is_ndss_research_paper(title: str) -> bool:
    """判断标题是否为研究论文（而非前置页 / 海报 / 研讨会 / keynote 等条目）。"""
    cleaned = clean_title(title)
    if not cleaned:
        return False
    return _NON_PAPER_TITLE_RE.search(cleaned) is None


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

    判定顺序固定（先会议、再标题），原因码因此可稳定断言。
    没有「篇幅」判定：NDSS 的 Crossref 记录不带 ``page``（实测 615/615 缺失），
    ACM CCS 的 ≤2 页前置页规则在此不可用，前置页只由标题规则识别。
    """
    if not is_ndss_main_track(container_title(item), year=year):
        return DROP_FOREIGN_VENUE
    if not is_ndss_research_paper(clean_title(item.get("title"))):
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
            raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE)
    message = payload.get("message")
    if not isinstance(message, Mapping):
        # 也接受直接传入 message 本体（含 items）的调用方式。
        message = payload if isinstance(payload.get("items"), list) else None
    if not isinstance(message, Mapping) or not isinstance(message.get("items"), list):
        raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE)
    return list(message["items"]), message


def _payload_year(items: Iterable[Any]) -> int | None:
    for item in items:
        if isinstance(item, Mapping):
            year = _item_year(item)
            if year is not None:
                return year
    return None


def _record(item: Mapping[str, Any], *, year: int) -> NdssCatalogRecord:
    doi = normalize_doi(item.get("DOI"))
    pdf_url = _ndss_pdf_url(item)
    provenance = {
        "title": CROSSREF_SOURCE_ID,
        "authors": CROSSREF_SOURCE_ID,
        "year": CROSSREF_SOURCE_ID,
        "doi": CROSSREF_SOURCE_ID,
        "container_title": CROSSREF_SOURCE_ID,
        "article_url": CROSSREF_SOURCE_ID,
    }
    if pdf_url:
        # Internet Society 把 camera-ready PDF 作为该作品的 primary resource 提交，
        # 且 NDSS 全部录用论文都在 www.ndss-symposium.org 公开托管；这里只记录地址，
        # 不发起任何请求，真正下载仍走既有安全下载链。
        provenance["pdf_url"] = CROSSREF_SOURCE_ID
    return NdssCatalogRecord(
        doi=doi,
        title=clean_title(item.get("title")),
        authors=_author_names(item),
        year=year,
        container_title=container_title(item),
        # Crossref 不含 NDSS 官方 HTML 页面地址，DOI 解析器就是权威记录页。
        article_url=f"https://{DOI_RESOLVER_HOST}/{doi}" if doi else "",
        pdf_url=pdf_url,
        pdf_access="public" if pdf_url else "unknown",
        provenance=provenance,
    )


def parse_crossref_catalog(payload: Any, *, year: int | None = None) -> NdssCatalogResult:
    """解析一页 Crossref work-list，返回 NDSS 主会研究论文与丢弃明细。

    ``year`` 为抓取单元年份；缺省时从条目 ``issued`` 推断，用于校验容器标题里的年份。
    """
    items, _ = _crossref_items(payload)
    resolved_year = int(year) if year is not None else _payload_year(items)
    records: list[NdssCatalogRecord] = []
    dropped: list[NdssDropped] = []
    venue_hits = 0
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if is_ndss_main_track(container_title(item), year=resolved_year):
            venue_hits += 1
        reason = drop_reason(item, year=resolved_year)
        if reason is None and _item_year(item) is None and resolved_year is None:
            reason = DROP_MISSING_YEAR
        if reason is not None:
            dropped.append(
                NdssDropped(
                    doi=normalize_doi(item.get("DOI")),
                    title=clean_title(item.get("title")),
                    reason=reason,
                )
            )
            continue
        records.append(_record(item, year=_item_year(item) or int(resolved_year or 0)))
    warnings = (NDSS_VENUE_FILTER_EMPTY,) if items and not venue_hits else ()
    return NdssCatalogResult(tuple(records), tuple(dropped), warnings)


# --- OpenAlex 富化与合并 -------------------------------------------------------


def parse_openalex_work(payload: Any) -> NdssEnrichment:
    """解析 OpenAlex 单篇作品：摘要（倒排索引还原）、关键词、OA PDF。"""
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE) from error
    if not isinstance(payload, Mapping):
        raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE)
    if payload.get("id") is None and payload.get("doi") is None:
        raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE)
    keywords: list[str] = []
    raw_keywords = payload.get("keywords")
    if isinstance(raw_keywords, list):
        for entry in raw_keywords:
            name = " ".join(str(entry.get("display_name") or "").split()) if isinstance(entry, Mapping) else ""
            if name and name not in keywords:
                keywords.append(name)
    location = payload.get("best_oa_location")
    pdf_url = _safe_record_url(location.get("pdf_url")) if isinstance(location, Mapping) else None
    if pdf_url and not urlsplit(pdf_url).path.casefold().endswith(".pdf"):
        # NDSS 特有：OpenAlex 把 doi.org 解析地址塞进 best_oa_location.pdf_url，
        # 那不是 PDF 地址，记录它会把 DOI 页面当成可下载 PDF。
        pdf_url = None
    open_access = payload.get("open_access")
    is_oa = bool(open_access.get("is_oa")) if isinstance(open_access, Mapping) else False
    return NdssEnrichment(
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


def merge_enrichment(record: NdssCatalogRecord, enrichment: NdssEnrichment) -> NdssCatalogRecord:
    """用聚合来源补充缺失字段；已存在的字段（无论权威高低）一律不覆盖。

    双重保护：字段为空 + 现有来源权威严格低于写入来源。NDSS 的 Crossref 记录没有摘要，
    因此这里的「不覆盖」主要面向未来官方页面来源写入的高权威摘要，以及已由 Crossref
    写入的官方 PDF 地址。
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


class NdssCatalogParser:
    """对象式入口，便于注入；行为与模块级函数完全一致。"""

    def parse_catalog(self, payload: Any, *, year: int | None = None) -> NdssCatalogResult:
        return parse_crossref_catalog(payload, year=year)

    def parse_enrichment(self, payload: Any) -> NdssEnrichment:
        return parse_openalex_work(payload)

    def merge(self, record: NdssCatalogRecord, enrichment: NdssEnrichment) -> NdssCatalogRecord:
        return merge_enrichment(record, enrichment)


__all__ = [
    "AUTHORITY_AGGREGATOR",
    "AUTHORITY_OFFICIAL_DOI",
    "AUTHORITY_OFFICIAL_VENUE",
    "CROSSREF_HOST",
    "CROSSREF_SOURCE_ID",
    "DROP_FOREIGN_VENUE",
    "DROP_MISSING_YEAR",
    "DROP_NON_PAPER_TITLE",
    "DOI_RESOLVER_HOST",
    "NDSS_AGGREGATOR_AUTHORITY",
    "NDSS_BIBLIOGRAPHIC_QUERY",
    "NDSS_CONTAINER_PHRASE",
    "NDSS_DOI_PREFIX",
    "NDSS_INVALID_RESPONSE",
    "NDSS_OFFICIAL_DOI_AUTHORITY",
    "NDSS_PAPER_HOST",
    "NDSS_PARSE_FAILED",
    "NDSS_SOURCE_ID",
    "NDSS_SOURCE_KIND",
    "NDSS_VENUE_FILTER_EMPTY",
    "NdssCatalogParser",
    "NdssCatalogRecord",
    "NdssCatalogResult",
    "NdssDropped",
    "NdssEnrichment",
    "NdssPaperParseError",
    "OPENALEX_HOST",
    "OPENALEX_SOURCE_ID",
    "SOURCE_AUTHORITY",
    "clean_title",
    "container_title",
    "drop_reason",
    "is_ndss_main_track",
    "is_ndss_research_paper",
    "merge_enrichment",
    "parse_crossref_catalog",
    "parse_openalex_work",
]
