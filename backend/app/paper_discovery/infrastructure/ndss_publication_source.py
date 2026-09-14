"""NDSS 来源适配器：Crossref 逐年目录 + OpenAlex 摘要富化。

照搬 ``ccs_publication_source`` / ``usenix_publication_source`` 的范式（source 负责网络/缓存/编排，
parser 负责纯解析），并实现 spec-032 冻结的 Source Adapter 合同：

======================  ==========================================================
``source_id``           ``ndss``（全局唯一）
``authority_rank``      官方 DOI 元数据（Internet Society 提交到 Crossref 的记录）
``discover_units``      按年份产出抓取单元（``ndss:2024``）
``fetch_unit``          ETag / Last-Modified / 内容 hash + 超时 + 条件请求
``parse_catalog``       委托纯 parser，产出带字段级 provenance 的目录记录
``normalize_identity``  复用既有 DOI / 标题规范化
``health``              无副作用、无网络
======================  ==========================================================

安全边界（与 spec-032「明确不做」一致）：

- 只请求 ``api.crossref.org`` 与 ``api.openalex.org``，URL 由服务端模板拼装，
  调用方**无法**传入任意根 URL；每次请求前都过平台既有 ``validate_url``（含 DNS/内网隔离）。
- 不抓取 ``ndss-symposium.org``，不下载、不探测任何 PDF，不绕过付费墙或登录。
  Crossref 提交的官方 PDF 地址与 OpenAlex 给出的 OA 地址只作为元数据记录，
  真正下载仍走既有安全下载链。
- **PDF 获取层级**：NDSS（Internet Society）**不在**持久化浏览器白名单内
  （``paper_browser_manager.SUPPORTED_SITES`` 只有 ``acm`` / ``ieee``），因此本适配器
  **不构造、也不伪造** acm/ieee 直链；记录到的 ``www.ndss-symposium.org`` 公开 PDF 由
  ``conference_pdf_downloader`` 判为 ``open_access``（走既有公开直下链，需调用方把该主机
  加入 ``allowed_hosts``），拿不到时判为 ``unavailable``——永远不会是 ``browser_required``。
- 无状态漂移：适配器不写任何 store；单元与字段 provenance 交给上层（Task05）合并。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlencode

import httpx

from backend.app.core.url_security import URLSecurityError, validate_url
from backend.app.paper_discovery.domain.paper_discovery import SourceFetchUnit
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.paper_discovery.infrastructure.ndss_paper_parser import (
    CROSSREF_HOST,
    NDSS_AGGREGATOR_AUTHORITY,
    NDSS_BIBLIOGRAPHIC_QUERY,
    NDSS_DOI_PREFIX,
    NDSS_INVALID_RESPONSE,
    NDSS_OFFICIAL_DOI_AUTHORITY,
    NDSS_SOURCE_ID,
    NDSS_SOURCE_KIND,
    OPENALEX_HOST,
    NdssCatalogParser,
    NdssCatalogRecord,
    NdssCatalogResult,
    NdssDropped,
    NdssPaperParseError,
    container_title,
    is_ndss_main_track,
)
from backend.app.paper_discovery.infrastructure.openalex_batch_enricher import (
    OPENALEX_BATCH_SIZE,
    batch_safe_doi,
    build_batch_url,
    works_by_doi,
)
from backend.app.platform.observability.spans import utc_now

NDSS_UNAVAILABLE = "NDSS_UNAVAILABLE"
NDSS_RATE_LIMITED = "NDSS_RATE_LIMITED"
NDSS_UNIT_REJECTED = "NDSS_UNIT_REJECTED"
NDSS_OPENALEX_UNAVAILABLE = "NDSS_OPENALEX_UNAVAILABLE"
NDSS_OPENALEX_NO_HIT = "NDSS_OPENALEX_NO_HIT"
NDSS_OPENALEX_INVALID_RESPONSE = "NDSS_OPENALEX_INVALID_RESPONSE"

DEFAULT_USER_AGENT = "ResearchAgent-Spec032/1.0 (NDSS source; mailto:research-agent@example.invalid)"
CONFERENCE_ID = "ndss"
_ACCEPT_JSON = {"Accept": "application/json"}


def _utc_iso() -> str:
    """统一 UTC 时间戳（复用平台时钟，秒级精度，``Z`` 结尾）。"""
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


class NdssUnitRejected(NdssPaperParseError):
    """抓取单元范围不合法（年份非法/越界/为空）。"""

    def __init__(self, message: str = "NDSS 抓取单元范围不合法") -> None:
        super().__init__(message, code=NDSS_UNIT_REJECTED)


class _PageFailure(Exception):
    """翻页过程中的失败；携带失败单元与稳定错误码。"""

    def __init__(self, unit: SourceFetchUnit, error_code: str) -> None:
        super().__init__(error_code)
        self.unit = unit
        self.error_code = error_code


@dataclass(frozen=True)
class NdssFetchOutcome:
    """一次 ``fetch_unit`` 的结果；``unit`` 已带上新的缓存状态。"""

    unit: SourceFetchUnit
    payload: Optional[Mapping[str, Any]] = None
    body: Optional[bytes] = None
    not_modified: bool = False
    error_code: Optional[str] = None


@dataclass(frozen=True)
class NdssYearResult:
    """单个年份单元的结果（一年失败不影响其他年份）。"""

    year: int
    unit: SourceFetchUnit
    records: tuple[NdssCatalogRecord, ...] = ()
    dropped: tuple[NdssDropped, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: Optional[str] = None
    cached: bool = False


@dataclass(frozen=True)
class NdssSyncResult:
    """``sync_units`` 的聚合结果，供上层合并与进度展示。"""

    units: tuple[SourceFetchUnit, ...] = ()
    records: tuple[NdssCatalogRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: Optional[str] = None
    status: str = "completed"
    failed_years: tuple[int, ...] = ()
    cached_years: tuple[int, ...] = ()


class NdssPublicationSource:
    """NDSS 主会目录来源（Crossref 目录 + OpenAlex 摘要）。"""

    source_id = NDSS_SOURCE_ID
    source_kind = NDSS_SOURCE_KIND
    #: 官方 DOI 元数据（Internet Society 自提交，prefix 10.14722），
    #: 低于官方会议页面、高于聚合书目来源。
    authority_rank = NDSS_OFFICIAL_DOI_AUTHORITY
    allowed_hosts = frozenset({CROSSREF_HOST, OPENALEX_HOST})
    #: NDSS 首届为 1995；上界留出提前配置的余地。
    MIN_YEAR = 1995
    MAX_YEAR = 2100

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        parser: Optional[NdssCatalogParser] = None,
        timeout: float = 20.0,
        dns_resolver: Any = None,
        rate_limit_seconds: float = 1.0,
        max_rows: int = 1000,
        max_pages: int = 5,
        user_agent: str = DEFAULT_USER_AGENT,
        now: Any = time.monotonic,
        sleep: Any = time.sleep,
        utcnow: Any = _utc_iso,
    ) -> None:
        self.client = client
        self.parser = parser or NdssCatalogParser()
        self.timeout = timeout
        self.dns_resolver = dns_resolver
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.max_rows = max(1, int(max_rows))
        self.max_pages = max(1, int(max_pages))
        self.user_agent = user_agent
        self._now = now
        self._sleep = sleep
        self._utcnow = utcnow
        self._next_request_at = 0.0
        self._lock = threading.Lock()
        # 单元内容未变化时复用已富化记录，避免重复富化（"内容未变化不重复向量化"的适配器侧对应）。
        self._record_cache: dict[tuple[str, Optional[str]], tuple[NdssCatalogRecord, ...]] = {}

    # --- 合同：单元发现 -------------------------------------------------------

    def discover_units(self, scope: Any) -> tuple[SourceFetchUnit, ...]:
        """按年份产出抓取单元；范围非法时抛 ``NdssUnitRejected``（不发任何请求）。"""
        years = self._scope_years(scope)
        now = self._utcnow()
        return tuple(
            SourceFetchUnit(
                fetch_unit_id=f"{self.source_id}|{CONFERENCE_ID}|{year}",
                source_kind=self.source_kind,
                conference_id=CONFERENCE_ID,
                year=year,
                unit_key=f"{CONFERENCE_ID}:{year}",
                source_url=self._crossref_url(year),
                status="pending",
                created_at=now,
                updated_at=now,
            )
            for year in years
        )

    def _scope_years(self, scope: Any) -> list[int]:
        if isinstance(scope, Mapping):
            raw: Any = scope.get("years")
        elif isinstance(scope, (str, int)) and not isinstance(scope, bool):
            raw = [scope]
        elif isinstance(scope, Iterable):
            raw = list(scope)
        else:
            raise NdssUnitRejected()
        if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
            raise NdssUnitRejected()
        years: set[int] = set()
        for value in raw:
            if isinstance(value, bool) or value is None:
                raise NdssUnitRejected()
            if isinstance(value, int):
                year = value
            elif isinstance(value, str) and value.strip().isdigit():
                year = int(value.strip())
            else:
                raise NdssUnitRejected()
            if not self.MIN_YEAR <= year <= self.MAX_YEAR:
                raise NdssUnitRejected()
            years.add(year)
        if not years:
            raise NdssUnitRejected()
        return sorted(years)

    def _crossref_url(self, year: int, *, offset: int = 0) -> str:
        """服务端拼装的 Crossref 查询 URL；调用方无法注入主机或路径。"""
        params = {
            "query.bibliographic": f"{NDSS_BIBLIOGRAPHIC_QUERY} {int(year)}",
            "filter": (
                f"prefix:{NDSS_DOI_PREFIX},type:proceedings-article,"
                f"from-pub-date:{int(year)}-01-01,until-pub-date:{int(year)}-12-31"
            ),
            "rows": self.max_rows,
            "offset": max(0, int(offset)),
        }
        return f"https://{CROSSREF_HOST}/works?{urlencode(params)}"

    def _openalex_url(self, doi: str) -> str:
        return f"https://{OPENALEX_HOST}/works/doi:{normalize_doi(doi)}"

    # --- 合同：条件抓取 -------------------------------------------------------

    def fetch_unit(
        self,
        unit: SourceFetchUnit,
        conditional_headers: Optional[Mapping[str, str]] = None,
    ) -> NdssFetchOutcome:
        """抓取一个单元（一页），支持 ETag / Last-Modified / 内容 hash 与超时。

        ``conditional_headers`` 缺省时从 ``unit.etag`` / ``unit.last_modified`` 推导，
        因此单元本身就是增量缓存载体。304 视为「内容未变化」：不产生新 ``content_hash``，
        保留旧值，供上层决定是否复用已索引记录。
        """
        try:
            validate_url(unit.source_url, allowed_hosts={CROSSREF_HOST}, dns_resolver=self.dns_resolver)
        except URLSecurityError:
            return NdssFetchOutcome(
                unit=self._failed_unit(unit, NDSS_UNIT_REJECTED),
                error_code=NDSS_UNIT_REJECTED,
            )
        headers = {"User-Agent": self.user_agent, **_ACCEPT_JSON}
        headers.update(dict(conditional_headers) if conditional_headers is not None else self._conditional_headers(unit))
        try:
            self._before_request()
            response = self._client().get(
                unit.source_url, headers=headers, timeout=self.timeout, follow_redirects=False
            )
        except (httpx.HTTPError, OSError):
            return NdssFetchOutcome(unit=self._failed_unit(unit, NDSS_UNAVAILABLE), error_code=NDSS_UNAVAILABLE)
        if response.status_code == 304:
            return NdssFetchOutcome(
                unit=replace(
                    unit,
                    status="completed",
                    etag=response.headers.get("ETag") or unit.etag,
                    last_modified=response.headers.get("Last-Modified") or unit.last_modified,
                    error_code=None,
                    last_attempt_at=self._utcnow(),
                    last_success_at=self._utcnow(),
                ),
                not_modified=True,
            )
        if response.status_code == 429:
            return NdssFetchOutcome(unit=self._failed_unit(unit, NDSS_RATE_LIMITED), error_code=NDSS_RATE_LIMITED)
        if response.status_code >= 400:
            return NdssFetchOutcome(unit=self._failed_unit(unit, NDSS_UNAVAILABLE), error_code=NDSS_UNAVAILABLE)
        body = response.content if response.content is not None else response.text.encode("utf-8")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return NdssFetchOutcome(unit=self._failed_unit(unit, NDSS_INVALID_RESPONSE), error_code=NDSS_INVALID_RESPONSE)
        if not isinstance(payload, Mapping):
            return NdssFetchOutcome(unit=self._failed_unit(unit, NDSS_INVALID_RESPONSE), error_code=NDSS_INVALID_RESPONSE)
        return NdssFetchOutcome(
            unit=replace(
                unit,
                status="completed",
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                content_hash=hashlib.sha256(body).hexdigest(),
                error_code=None,
                last_attempt_at=self._utcnow(),
                last_success_at=self._utcnow(),
            ),
            payload=payload,
            body=body,
        )

    @staticmethod
    def _conditional_headers(unit: SourceFetchUnit) -> dict[str, str]:
        headers: dict[str, str] = {}
        if unit.etag:
            headers["If-None-Match"] = unit.etag
        if unit.last_modified:
            headers["If-Modified-Since"] = unit.last_modified
        return headers

    def _failed_unit(self, unit: SourceFetchUnit, error_code: str) -> SourceFetchUnit:
        return replace(unit, status="failed", error_code=error_code, last_attempt_at=self._utcnow())

    # --- 合同：解析 / 身份 / 健康 ---------------------------------------------

    def parse_catalog(self, response: Any, *, year: Optional[int] = None) -> NdssCatalogResult:
        """解析一次抓取结果（``NdssFetchOutcome``、payload 或 JSON 文本）。"""
        if isinstance(response, NdssFetchOutcome):
            payload: Any = response.payload
            if year is None:
                year = response.unit.year
        else:
            payload = response
        if payload is None:
            raise NdssPaperParseError(code=NDSS_INVALID_RESPONSE)
        return self.parser.parse_catalog(payload, year=year)

    def normalize_identity(self, record: NdssCatalogRecord) -> str:
        """复用既有 DOI / 标题规范化规则产出身份键（DOI 优先）。"""
        doi = normalize_doi(record.doi)
        if doi:
            return f"doi:{doi}"
        return f"title:{normalize_title(record.title)}|{record.year}"

    def health(self) -> dict[str, Any]:
        """来源健康与能力声明；无网络、无副作用、不含任何凭据。"""
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "authority_rank": self.authority_rank,
            "enabled": True,
            "allowed_hosts": sorted(self.allowed_hosts),
            "unit_scope": "year",
            "min_year": self.MIN_YEAR,
            "max_year": self.MAX_YEAR,
            "fetch": "conditional_etag_content_hash",
            "pdf_download": "delegated_to_safe_download_chain",
            "aggregator_authority": NDSS_AGGREGATOR_AUTHORITY,
            "official_doi_authority": NDSS_OFFICIAL_DOI_AUTHORITY,
            "error_code": None,
        }

    # --- OpenAlex 富化 -------------------------------------------------------

    def enrich_record(self, record: NdssCatalogRecord) -> tuple[NdssCatalogRecord, tuple[str, ...]]:
        """补一条记录的摘要/关键词/OA PDF；失败只产生告警，绝不抛错。"""
        if (record.abstract or "").strip() or not normalize_doi(record.doi):
            return record, ()
        url = self._openalex_url(record.doi)
        try:
            validate_url(url, allowed_hosts={OPENALEX_HOST}, dns_resolver=self.dns_resolver)
        except URLSecurityError:
            return record, (NDSS_OPENALEX_UNAVAILABLE,)
        try:
            self._before_request()
            response = self._client().get(
                url, headers={"User-Agent": self.user_agent, **_ACCEPT_JSON},
                timeout=self.timeout, follow_redirects=False,
            )
        except (httpx.HTTPError, OSError):
            return record, (NDSS_OPENALEX_UNAVAILABLE,)
        if response.status_code == 404:
            return record, (NDSS_OPENALEX_NO_HIT,)
        if response.status_code >= 400:
            return record, (NDSS_OPENALEX_UNAVAILABLE,)
        try:
            enrichment = self.parser.parse_enrichment(response.content)
        except (NdssPaperParseError, ValueError):
            return record, (NDSS_OPENALEX_INVALID_RESPONSE,)
        return self.parser.merge(record, enrichment), ()

    #: 批量查询只取 parser 真正会读的字段，避免拉回整篇作品。
    _OPENALEX_BATCH_SELECT = "id,doi,keywords,best_oa_location,open_access,abstract_inverted_index"

    def enrich_records(
        self, records: Iterable[NdssCatalogRecord]
    ) -> tuple[tuple[NdssCatalogRecord, ...], tuple[str, ...]]:
        """批量补摘要/关键词/OA PDF：每 50 条一次 OpenAlex 请求，而不是每条一次。

        语义与 :meth:`enrich_record` **完全一致**（失败只记告警、绝不抛错、
        不覆盖已有字段），只是把网络往返从 N 次降到 N/50 次。
        不能安全拼进 ``filter=doi:`` 的 DOI 会退回单条路径，保证结果不因批量化而改变。
        """
        items = list(records)
        warnings: list[str] = []
        resolved: set[int] = set()

        for start in range(0, len(items), OPENALEX_BATCH_SIZE):
            window = list(range(start, min(start + OPENALEX_BATCH_SIZE, len(items))))
            chunk: list[tuple[int, NdssCatalogRecord]] = []
            for index in window:
                record = items[index]
                if (record.abstract or "").strip() or not normalize_doi(record.doi):
                    continue
                if batch_safe_doi(record.doi) is None:
                    continue  # 不可信 DOI：不进批量，退回单条
                chunk.append((index, record))
            if not chunk:
                continue

            try:
                url = build_batch_url(
                    f"https://{OPENALEX_HOST}/works",
                    [record.doi for _, record in chunk],
                    select=self._OPENALEX_BATCH_SELECT,
                    per_page=OPENALEX_BATCH_SIZE,
                )
                validate_url(url, allowed_hosts={OPENALEX_HOST}, dns_resolver=self.dns_resolver)
            except (URLSecurityError, ValueError):
                continue  # 退回单条
            try:
                self._before_request()
                response = self._client().get(
                    url, headers={"User-Agent": self.user_agent, **_ACCEPT_JSON},
                    timeout=self.timeout, follow_redirects=False,
                )
            except (httpx.HTTPError, OSError):
                continue  # 整批网络失败：退回单条，避免丢数据
            if response.status_code >= 400:
                continue
            try:
                indexed = works_by_doi(response.json())
            except (ValueError, TypeError):
                continue
            for index, record in chunk:
                work = indexed.get(normalize_doi(record.doi) or "")
                if work is None:
                    warnings.append(NDSS_OPENALEX_NO_HIT)
                else:
                    try:
                        items[index] = self.parser.merge(record, self.parser.parse_enrichment(work))
                    except (NdssPaperParseError, ValueError):
                        warnings.append(NDSS_OPENALEX_INVALID_RESPONSE)
                resolved.add(index)

        # 批量没覆盖到的（不可信 DOI 或整批失败）退回原有单条路径，行为与改动前一致。
        for index, record in enumerate(items):
            if index in resolved:
                continue
            if (record.abstract or "").strip() or not normalize_doi(record.doi):
                continue
            enriched, issues = self.enrich_record(record)
            items[index] = enriched
            warnings.extend(issues)

        return tuple(items), tuple(dict.fromkeys(warnings))

    # --- 编排：年份单元同步 ---------------------------------------------------

    def sync_year(self, year: int, *, previous_unit: Optional[SourceFetchUnit] = None) -> NdssYearResult:
        """抓取、解析并富化一个年份单元；内容未变化时复用已富化记录。"""
        unit = self.discover_units([year])[0]
        conditional: Mapping[str, str] = {}
        if previous_unit is not None:
            unit = replace(
                unit,
                etag=previous_unit.etag,
                last_modified=previous_unit.last_modified,
                content_hash=previous_unit.content_hash,
            )
            conditional = self._conditional_headers(previous_unit)
        outcome = self.fetch_unit(unit, conditional_headers=conditional)
        if outcome.error_code is not None:
            return NdssYearResult(year=int(year), unit=outcome.unit, error_code=outcome.error_code)
        if outcome.not_modified:
            cached = self._record_cache.get((unit.fetch_unit_id, outcome.unit.content_hash))
            if cached is not None:
                return NdssYearResult(
                    year=int(year), unit=outcome.unit, records=cached, cached=True
                )
            # 没有可复用的记录（例如新进程首次运行）：去掉条件头强制完整读取，
            # 否则「304 + 空结果」会被误报成缓存命中，静默丢掉整年目录。
            outcome = self.fetch_unit(
                replace(unit, etag=None, last_modified=None), conditional_headers={}
            )
            if outcome.error_code is not None:
                return NdssYearResult(year=int(year), unit=outcome.unit, error_code=outcome.error_code)

        try:
            items, bodies, total = self._fetch_pages(int(year), unit, outcome)
        except _PageFailure as failure:
            return NdssYearResult(year=int(year), unit=failure.unit, error_code=failure.error_code)
        result = self.parser.parse_catalog({"message": {"items": items, "total-results": total}}, year=int(year))
        # 富化走批量（每 50 条一次 OpenAlex 请求）；单条 enrich_record 保留给
        # 不可批量化的记录与既有调用方。
        enriched_records, enrich_warnings = self.enrich_records(result.records)
        warnings = list(result.warnings) + list(enrich_warnings)
        records = list(enriched_records)
        content_hash = hashlib.sha256(b"".join(bodies)).hexdigest()
        completed = replace(
            unit,
            status="completed",
            content_hash=content_hash,
            paper_count=len(records),
            etag=outcome.unit.etag,
            last_modified=outcome.unit.last_modified,
            error_code=None,
            last_success_at=self._utcnow(),
            updated_at=self._utcnow(),
        )
        with self._lock:
            self._record_cache[(unit.fetch_unit_id, content_hash)] = tuple(records)
        return NdssYearResult(
            year=int(year),
            unit=completed,
            records=tuple(records),
            dropped=result.dropped,
            warnings=tuple(dict.fromkeys(warnings)),
            error_code=None,
        )

    def _fetch_pages(
        self, year: int, unit: SourceFetchUnit, first: NdssFetchOutcome
    ) -> tuple[list[Any], list[bytes], Optional[int]]:
        """按 ``offset`` 翻页收集条目，直到相关性窗口越过 NDSS。

        翻页停止条件（任一命中）：本页没有条目、本页不是满页（``len < rows`` 说明到底了）、
        本页没有任何 NDSS 主会条目、或达到 ``max_pages`` 上限。

        特意**不**用 ``message.total-results`` 作为终止条件：它是书目查询的相关性总量
        （实测 2024 为 258），而不是 NDSS 主会论文数；且其中混着同前缀（10.14722）的
        co-located 会议/研讨会条目，按它翻页会为每年多扫无关条目。实测 2021–2025 的主会
        论文全部落在第一页（最多 211 条 < 1000），所以「本页无主会命中」就是可靠且礼貌的
        停止信号。Crossref 也不支持 cursor（同项目实测扫 6000 条 0 命中）。
        """
        items: list[Any] = []
        bodies: list[bytes] = []
        offset, pages, total = 0, 0, None
        page = first
        while True:
            message = (page.payload or {}).get("message")
            if not isinstance(message, Mapping):
                raise _PageFailure(page.unit, NDSS_INVALID_RESPONSE)
            page_items = message.get("items") if isinstance(message.get("items"), list) else []
            items.extend(page_items)
            bodies.append(page.body or b"")
            if total is None:
                total = message.get("total-results") if isinstance(message.get("total-results"), int) else len(page_items)
            hits = sum(
                1
                for item in page_items
                if isinstance(item, Mapping) and is_ndss_main_track(container_title(item), year=year)
            )
            offset += self.max_rows
            pages += 1
            if not page_items or len(page_items) < self.max_rows or not hits or pages >= self.max_pages:
                break
            page = self.fetch_unit(
                replace(unit, source_url=self._crossref_url(year, offset=offset)), conditional_headers={}
            )
            if page.error_code is not None:
                raise _PageFailure(page.unit, page.error_code)
        return items, bodies, total

    def sync_units(self, scope: Any) -> NdssSyncResult:
        """按年份单元同步；单年失败不影响其他年份（不产生跨年副作用）。"""
        units = self.discover_units(scope)
        records: list[NdssCatalogRecord] = []
        warnings: list[str] = []
        failed: list[int] = []
        cached: list[int] = []
        completed_units: list[SourceFetchUnit] = []
        for unit in units:
            outcome = self.sync_year(int(unit.year or 0))
            completed_units.append(outcome.unit)
            if outcome.error_code is not None:
                failed.append(outcome.year)
                continue
            records.extend(outcome.records)
            warnings.extend(outcome.warnings)
            if outcome.cached:
                cached.append(outcome.year)
        if failed and len(failed) == len(units):
            status, error_code = "failed", NDSS_UNAVAILABLE
        elif failed:
            # 部分失败：详情在 failed_years 里，来源级错误码保持空，避免把部分成功当成整源不可用。
            status, error_code = "partial", None
        else:
            status, error_code = "completed", None
        return NdssSyncResult(
            units=tuple(completed_units),
            records=tuple(records),
            warnings=tuple(dict.fromkeys(warnings)),
            error_code=error_code,
            status=status,
            failed_years=tuple(failed),
            cached_years=tuple(cached),
        )

    # --- 内部工具 -------------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)
        return self.client

    def _before_request(self) -> None:
        """礼貌限速：Crossref/OpenAlex 都要求低频访问，复用 USENIX 的节流写法。"""
        with self._lock:
            now = self._now()
            wait = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + self.rate_limit_seconds
        if wait:
            self._sleep(wait)


__all__ = [
    "CONFERENCE_ID",
    "DEFAULT_USER_AGENT",
    "NDSS_OPENALEX_INVALID_RESPONSE",
    "NDSS_OPENALEX_NO_HIT",
    "NDSS_OPENALEX_UNAVAILABLE",
    "NDSS_RATE_LIMITED",
    "NDSS_UNAVAILABLE",
    "NDSS_UNIT_REJECTED",
    "NdssFetchOutcome",
    "NdssPublicationSource",
    "NdssSyncResult",
    "NdssUnitRejected",
    "NdssYearResult",
]
