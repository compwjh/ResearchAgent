"""Spec032 聚合书目来源适配器（OpenAlex / Crossref）。

本模块是 **纯适配层**：只负责把聚合来源的目录响应解析成统一的
``SourceRecord``，并提供可复用的增量抓取单元（``FetchUnit``）与字段级
provenance 合并。**不做**数据库写入、API 装配、PDF 下载（分别由 Task05
与既有安全链路负责）。

设计约束（spec032）：
- 聚合来源只**补缺**，不能覆盖更高权威（官方会议目录）的标题/摘要/关键词/官方链接；
- 抓取单元支持 ETag / Last-Modified / 内容 hash：内容未变化即跳过重复解析与向量化；
- 单源失败不得清空旧缓存（这里只把单元标为 ``failed``，缓存由调用方持有）；
- ``health()`` 必须安全、脱敏、无下载副作用。

既有能力复用：OpenAlex 的 inverted-index 摘要还原复用
``openalex_enricher._abstract_from_inverted_index``，DOI/标题规范化复用
``paper_discovery_normalization``，不复制旧客户端。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from backend.app.paper_discovery.domain.paper_discovery_normalization import (
    normalize_doi,
    normalize_title,
)
from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATE,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    canonical_source_id,
)
from backend.app.paper_discovery.domain.source_contract import (
    SOURCE_CONTRACT_SCHEMA_VERSION,
    SourceResult,
)
from backend.app.paper_discovery.infrastructure.openalex_enricher import (
    _abstract_from_inverted_index,
)

# 权威常量集中定义于 domain/source_authority（唯一方向：数值越小越权威）。
# 此处保留旧名 AUTHORITY_OFFICIAL / AUTHORITY_AGGREGATE 作为别名（被测试引用），
# 指向同一套唯一常量，避免两套方向相反的判定；AUTHORITY_DOI_METADATA 已不再使用并删除。
AUTHORITY_OFFICIAL = AUTHORITY_OFFICIAL_VENUE

# 只有这些字段参与跨来源合并，且低权威只能填补缺失值。
MERGEABLE_FIELDS = (
    "title",
    "abstract",
    "keywords",
    "authors",
    "year",
    "doi",
    "page_url",
    "pdf_url",
)


@dataclass(frozen=True)
class SourceRecord:
    """一个来源解析出的目录记录。provenance 记录每个字段来自哪个来源。"""

    source_id: str
    source_record_id: str
    authority_rank: int
    title: str = ""
    abstract: str = ""
    keywords: Tuple[str, ...] = ()
    authors: Tuple[str, ...] = ()
    year: Optional[int] = None
    doi: str = ""
    page_url: str = ""
    pdf_url: str = ""
    provenance: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Source records may be reconstructed from a pre-Task06 cache.  Normalize
        # only the controlled historical aliases; extension/unknown provenance is
        # deliberately preserved and handled fail-closed by authority_rank_for().
        object.__setattr__(self, "source_id", canonical_source_id(self.source_id))
        object.__setattr__(
            self,
            "provenance",
            {field: canonical_source_id(source) for field, source in self.provenance.items()},
        )

    def identity_key(self) -> str:
        """去重身份：优先规范化 DOI，退回规范化标题+年份。"""
        doi = normalize_doi(self.doi)
        if doi:
            return f"doi:{doi}"
        return f"title:{normalize_title(self.title)}:{self.year or ''}"

    def provenance_for(self, field_name: str) -> str:
        return self.provenance.get(field_name, self.source_id)


@dataclass(frozen=True)
class FetchUnit:
    """一个可持久化、可条件抓取的目录单元（年份/cycle/track）。"""

    source_id: str
    scope_key: str
    params: Dict[str, Any] = field(default_factory=dict)
    etag: str = ""
    last_modified: str = ""
    content_hash: str = ""
    status: str = "pending"  # pending | fetched | unchanged | failed
    cursor: str = ""

    def conditional_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers

    def with_result(
        self,
        *,
        status: str,
        etag: str = "",
        last_modified: str = "",
        body: bytes | str | None = None,
        cursor: str = "",
    ) -> "FetchUnit":
        digest = self.content_hash
        if status == "fetched" and body is not None:
            raw = body.encode("utf-8") if isinstance(body, str) else body
            digest = hashlib.sha256(raw).hexdigest()
        return replace(
            self,
            status=status,
            etag=etag or self.etag,
            last_modified=last_modified or self.last_modified,
            content_hash=digest,
            cursor=cursor or self.cursor,
        )


def content_fingerprint(body: bytes | str) -> str:
    raw = body.encode("utf-8") if isinstance(body, str) else body
    return hashlib.sha256(raw).hexdigest()


def merge_source_records(
    base: SourceRecord, incoming: SourceRecord
) -> Tuple[SourceRecord, List[str]]:
    """按 authority_rank 合并两个来源记录：低权威只补缺，绝不覆盖高权威字段。

    返回 (合并结果, 本次真正被填补的字段名列表)。同权威时以 ``incoming`` 补齐
    ``base`` 的空字段（不覆盖非空）。
    """
    if incoming.identity_key() != base.identity_key():
        return base, []
    filled: List[str] = []
    updates: Dict[str, Any] = {}
    provenance = dict(base.provenance)
    for name in MERGEABLE_FIELDS:
        current = getattr(base, name)
        candidate = getattr(incoming, name)
        if not _is_present(candidate):
            continue
        # 官方字段不可被聚合来源降级：字段已存在时，只有更权威的来源可覆盖。
        if _is_present(current) and incoming.authority_rank >= base.authority_rank:
            continue
        updates[name] = candidate
        provenance[name] = incoming.source_id
        filled.append(name)
    if not updates:
        return base, filled
    merged = replace(base, provenance=provenance, **updates)
    return merged, filled


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (tuple, list)):
        return bool(value)
    return True


class SourceAdapter:
    """聚合来源适配器基类：定义 spec032 的 Source Adapter 合同。"""

    source_id: str = ""
    source_kind: str = "aggregate"
    authority_rank: int = AUTHORITY_AGGREGATE
    endpoint: str = ""
    user_agent: str = "ResearchAgent-Spec032/1.0"
    contract_schema_version: str = SOURCE_CONTRACT_SCHEMA_VERSION

    def __init__(self, *, timeout: float = 20.0, client: Any = None):
        self.timeout = timeout
        self.client = client

    # -- 合同 ------------------------------------------------------------
    def discover_units(self, scope: Mapping[str, Any]) -> List[FetchUnit]:
        """按 scope（如 year / from_year..to_year / topic）拆分抓取单元。"""
        raise NotImplementedError

    def fetch_unit(
        self, unit: FetchUnit, conditional_headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[FetchUnit, Optional[Any]]:
        """抓取一个单元；返回 (更新后的 unit, 解析后的 payload 或 None)。

        ``None`` 表示内容未变化（304 / hash 相同）或抓取失败——由调用方决定
        是否重试；单源失败不清空旧缓存。
        """
        raise NotImplementedError

    def parse_catalog(self, response: Any) -> List[SourceRecord]:
        raise NotImplementedError

    def normalize_identity(self, record: SourceRecord) -> str:
        return record.identity_key()

    def health(self) -> Dict[str, Any]:
        raise NotImplementedError

    def result(
        self,
        operation: str,
        *,
        status: str = "completed",
        scope: Optional[Mapping[str, Any]] = None,
        coverage: Optional[Mapping[str, Any]] = None,
        papers: Iterable[Any] = (),
        error: Any = None,
        artifact_handles: Optional[Mapping[str, Any]] = None,
        elapsed_ms: int = 0,
    ) -> SourceResult:
        """Wrap source-specific records in the shared Task06 result envelope.

        Existing ``parse_catalog`` callers keep their typed list return; Worker
        implementations can opt into this wrapper without duplicating a second
        parser or network client.
        """
        return SourceResult(
            schema_version=self.contract_schema_version,
            source_id=self.source_id,
            operation=operation,
            status=status,
            scope=dict(scope or {}),
            coverage=dict(coverage or {}),
            papers=tuple(papers),
            error=error,
            artifact_handles=dict(artifact_handles or {}),
            elapsed_ms=elapsed_ms,
        )

    def parse_catalog_result(
        self, response: Any, *, scope: Optional[Mapping[str, Any]] = None,
        coverage: Optional[Mapping[str, Any]] = None,
    ) -> SourceResult:
        """Parse and return a versioned result while preserving ``parse_catalog``."""
        records = self.parse_catalog(response)
        return self.result(
            "parse_catalog", scope=scope, coverage=coverage, papers=records,
        )

    # -- 公共工具 --------------------------------------------------------
    def _get(self, params: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None):
        import httpx

        client = self.client
        owns_client = False
        if client is None:
            client = httpx.Client(timeout=self.timeout, trust_env=False)
            owns_client = True
        try:
            return client.get(
                self.endpoint,
                params=dict(params),
                headers={"User-Agent": self.user_agent, **(dict(headers or {}))},
            )
        except httpx.HTTPError:
            return None
        finally:
            if owns_client and hasattr(client, "close"):
                client.close()

    @staticmethod
    def _unchanged(unit: FetchUnit, response: Any) -> Optional[bool]:
        """判断响应是否表示内容未变化；非 304 返回 None。"""
        status = getattr(response, "status_code", None)
        if status == 304:
            return True
        return None

    @staticmethod
    def _json(response: Any) -> Optional[Mapping[str, Any]]:
        try:
            payload = response.json()
        except (ValueError, TypeError):
            try:
                payload = json.loads(getattr(response, "text", "") or "")
            except (ValueError, TypeError):
                return None
        return payload if isinstance(payload, Mapping) else None


class OpenAlexCatalogAdapter(SourceAdapter):
    """OpenAlex works 目录适配器（聚合书目来源）。"""

    source_id = "openalex"
    source_kind = "openalex"
    authority_rank = AUTHORITY_AGGREGATE
    endpoint = "https://api.openalex.org/works"
    user_agent = "ResearchAgent-Spec032/1.0 (OpenAlex)"

    select = "id,doi,title,display_name,publication_year,authorships,abstract_inverted_index,primary_location,keywords"

    def discover_units(self, scope: Mapping[str, Any]) -> List[FetchUnit]:
        units: List[FetchUnit] = []
        for year in _years(scope):
            units.append(
                FetchUnit(
                    source_id=self.source_id,
                    scope_key=f"openalex:{year}",
                    params={"filter": f"from_publication_date:{year}-01-01,to_publication_date:{year}-12-31"},
                )
            )
        return units

    def fetch_unit(self, unit, conditional_headers=None):
        params = dict(unit.params)
        params.setdefault("select", self.select)
        params.setdefault("per-page", 200)
        if unit.cursor:
            params["cursor"] = unit.cursor
        response = self._get(params, conditional_headers or unit.conditional_headers())
        if response is None:
            return unit.with_result(status="failed"), None
        if self._unchanged(unit, response):
            return unit.with_result(status="unchanged"), None
        if getattr(response, "status_code", None) != 200:
            return unit.with_result(status="failed"), None
        payload = self._json(response)
        if payload is None:
            return unit.with_result(status="failed"), None
        body = getattr(response, "content", None) or b""
        if unit.content_hash and content_fingerprint(body) == unit.content_hash:
            return unit.with_result(status="unchanged"), None
        updated = unit.with_result(
            status="fetched",
            etag=response.headers.get("ETag", ""),
            last_modified=response.headers.get("Last-Modified", ""),
            body=body,
            cursor=str(payload.get("meta", {}).get("next_cursor") or ""),
        )
        return updated, payload

    def parse_catalog(self, response: Any) -> List[SourceRecord]:
        if isinstance(response, Mapping):
            items = response.get("results") or []
        elif isinstance(response, (bytes, str)):
            payload = json.loads(response if isinstance(response, str) else response.decode("utf-8"))
            items = payload.get("results") or []
        else:
            return []
        records: List[SourceRecord] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            record = self._record(item)
            if record is not None:
                records.append(record)
        return records

    def _record(self, item: Mapping[str, Any]) -> Optional[SourceRecord]:
        title = str(item.get("display_name") or item.get("title") or "").strip()
        if not title:
            return None
        authors = []
        for authorship in item.get("authorships") or []:
            name = (authorship or {}).get("author", {}) or {}
            display = str(name.get("display_name") or "").strip()
            if display:
                authors.append(display)
        location = item.get("primary_location") or {}
        landing = str((location or {}).get("landing_page_url") or "").strip()
        pdf = str((location or {}).get("pdf_url") or "").strip()
        keywords = []
        for keyword in item.get("keywords") or []:
            value = str((keyword or {}).get("display_name") or "").strip()
            if value:
                keywords.append(value)
        year = item.get("publication_year")
        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None
        doi = normalize_doi(str(item.get("doi") or "")) or ""
        record_id = str(item.get("id") or doi or title)
        record = SourceRecord(
            source_id=self.source_id,
            source_record_id=record_id,
            authority_rank=self.authority_rank,
            title=title,
            abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")) or "",
            keywords=tuple(keywords),
            authors=tuple(authors),
            year=year,
            doi=doi,
            page_url=landing,
            pdf_url=pdf,
        )
        return replace(
            record,
            provenance={
                name: self.source_id
                for name in MERGEABLE_FIELDS
                if _is_present(getattr(record, name))
            },
        )

    def health(self) -> Dict[str, Any]:
        response = self._get({"per-page": 1, "select": "id"})
        ok = response is not None and getattr(response, "status_code", None) == 200
        # ``kind`` is a legacy health payload key retained for old callers.  The
        # canonical contract identity is exposed by ``source_kind`` on the adapter
        # and by SourceResult.source_id; Task06 does not break this read path.
        return {"source_id": self.source_id, "ok": bool(ok), "kind": "aggregate"}


class CrossrefCatalogAdapter(SourceAdapter):
    """Crossref works 目录适配器（聚合书目来源）。"""

    source_id = "crossref"
    source_kind = "crossref"
    # Crossref member/publisher metadata is DOI authority (rank 20), not a
    # conference-venue rank.  Conference filtering does not change provenance.
    authority_rank = AUTHORITY_OFFICIAL_DOI
    endpoint = "https://api.crossref.org/works"
    user_agent = "ResearchAgent-Spec032/1.0 (Crossref; mailto:unset@example.invalid)"

    def discover_units(self, scope: Mapping[str, Any]) -> List[FetchUnit]:
        units: List[FetchUnit] = []
        for year in _years(scope):
            units.append(
                FetchUnit(
                    source_id=self.source_id,
                    scope_key=f"crossref:{year}",
                    params={
                        "filter": f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
                    },
                )
            )
        return units

    def fetch_unit(self, unit, conditional_headers=None):
        params = dict(unit.params)
        params.setdefault("rows", 200)
        if unit.cursor:
            params["cursor"] = unit.cursor
        response = self._get(params, conditional_headers or unit.conditional_headers())
        if response is None:
            return unit.with_result(status="failed"), None
        if self._unchanged(unit, response):
            return unit.with_result(status="unchanged"), None
        if getattr(response, "status_code", None) != 200:
            return unit.with_result(status="failed"), None
        payload = self._json(response)
        if payload is None:
            return unit.with_result(status="failed"), None
        body = getattr(response, "content", None) or b""
        if unit.content_hash and content_fingerprint(body) == unit.content_hash:
            return unit.with_result(status="unchanged"), None
        updated = unit.with_result(
            status="fetched",
            etag=response.headers.get("ETag", ""),
            last_modified=response.headers.get("Last-Modified", ""),
            body=body,
            cursor=str((payload.get("message") or {}).get("next-cursor") or ""),
        )
        return updated, payload

    def parse_catalog(self, response: Any) -> List[SourceRecord]:
        if isinstance(response, Mapping):
            message = response.get("message") or {}
        elif isinstance(response, (bytes, str)):
            payload = json.loads(response if isinstance(response, str) else response.decode("utf-8"))
            message = payload.get("message") or {}
        else:
            return []
        items = (message or {}).get("items") or []
        records: List[SourceRecord] = []
        for item in items:
            if isinstance(item, Mapping):
                record = self._record(item)
                if record is not None:
                    records.append(record)
        return records

    @staticmethod
    def _year(item: Mapping[str, Any]) -> Optional[int]:
        for key in ("published-print", "published-online", "issued"):
            parts = ((item.get(key) or {}).get("date-parts") or [[]])
            if parts and parts[0]:
                try:
                    return int(parts[0][0])
                except (TypeError, ValueError):
                    continue
        return None

    def _record(self, item: Mapping[str, Any]) -> Optional[SourceRecord]:
        titles = item.get("title") or []
        title = str(titles[0]).strip() if titles else ""
        if not title:
            return None
        authors = []
        for entry in item.get("author") or []:
            given = str((entry or {}).get("given") or "").strip()
            family = str((entry or {}).get("family") or "").strip()
            name = " ".join(part for part in (given, family) if part)
            if name:
                authors.append(name)
        year = self._year(item)
        doi = normalize_doi(str(item.get("DOI") or "")) or ""
        page_url = str(item.get("URL") or "").strip()
        pdf_url = ""
        for link in item.get("link") or []:
            if str((link or {}).get("content-type") or "").lower() == "application/pdf":
                pdf_url = str((link or {}).get("URL") or "").strip()
        abstract = str(item.get("abstract") or "").strip()
        record = SourceRecord(
            source_id=self.source_id,
            source_record_id=str(item.get("DOI") or title),
            authority_rank=self.authority_rank,
            title=title,
            abstract=abstract,
            authors=tuple(authors),
            year=year,
            doi=doi,
            page_url=page_url,
            pdf_url=pdf_url,
        )
        return replace(
            record,
            provenance={
                name: self.source_id
                for name in MERGEABLE_FIELDS
                if _is_present(getattr(record, name))
            },
        )

    def health(self) -> Dict[str, Any]:
        response = self._get({"rows": 1})
        ok = response is not None and getattr(response, "status_code", None) == 200
        return {"source_id": self.source_id, "ok": bool(ok), "kind": "aggregate"}


def _years(scope: Mapping[str, Any]) -> List[int]:
    """把 scope 解析为年份列表：支持 year / years / from_year+to_year。"""
    raw_years = scope.get("years")
    if isinstance(raw_years, (list, tuple)) and raw_years:
        return [int(year) for year in raw_years]
    single = scope.get("year")
    if single is not None:
        return [int(single)]
    start = scope.get("from_year")
    end = scope.get("to_year")
    if start is not None and end is not None:
        return list(range(int(start), int(end) + 1))
    return []


def dedupe_by_identity(records: Iterable[SourceRecord]) -> List[SourceRecord]:
    """按身份去重（DOI 优先），保留首次出现的记录。"""
    seen: Dict[str, SourceRecord] = {}
    for record in records:
        seen.setdefault(record.identity_key(), record)
    return list(seen.values())
