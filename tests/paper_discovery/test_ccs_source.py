"""Spec-032 Task 04: ACM CCS 来源适配器定向测试（Crossref 目录 + OpenAlex 摘要）。

样本全部来自真实抓取，见 ``tests/fixtures/ccs/README.md``。
本文件不访问网络：所有 HTTP 走 ``httpx.MockTransport``，DNS 走注入的假 resolver。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    CCS_AGGREGATOR_AUTHORITY,
    CCS_INVALID_RESPONSE,
    CCS_OFFICIAL_DOI_AUTHORITY,
    CCS_SOURCE_ID,
    CCS_SOURCE_KIND,
    CCS_VENUE_FILTER_EMPTY,
    CcsCatalogParser,
    CcsPaperParseError,
    is_ccs_main_track,
    is_ccs_research_paper,
    parse_crossref_catalog,
    parse_openalex_work,
)
from backend.app.paper_discovery.infrastructure.ccs_publication_source import (
    CCS_OPENALEX_NO_HIT,
    CCS_OPENALEX_UNAVAILABLE,
    CCS_RATE_LIMITED,
    CCS_UNAVAILABLE,
    CCS_UNIT_REJECTED,
    CcsPublicationSource,
    CcsUnitRejected,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ccs"
PUBLIC_IP = "93.184.216.34"

# 真实研究论文（Crossref 主会容器 + 完整篇幅），必须保留。
CCS_2024_PAPERS = (
    "10.1145/3658644.3670328",
    "10.1145/3658644.3690303",
    "10.1145/3658644.3690220",
    "10.1145/3658644.3670374",
    "10.1145/3658644.3670378",
)
# 真实非论文条目及其应命中的稳定原因码。
CCS_2024_NON_PAPERS = {
    "10.1145/3658644.3698218": "NON_PAPER_TITLE",  # ACM CCS 2024 Doctoral Symposium
    "10.1145/3658644.3691403": "NON_PAPER_TITLE",  # Poster: ...
    "10.1145/3658644.3691398": "NON_PAPER_TITLE",  # Poster: ...
    "10.1145/3658644.3691548": "NON_PAPER_TITLE",  # CCSW 2024 -- Cloud Computing Security Workshop
    "10.1145/3658644.3690866": "INVITED_TALK",  # keynote：单作者 + 3 页
}
ASIA_CCS_2024 = "10.1145/3634737.3665025"
OPENALEX_WITH_PDF = "openalex-work-10.1145-3658644.3670374-with-oa-pdf.json"
OPENALEX_NO_PDF = "openalex-work-10.1145-3658644.3670328-no-oa-pdf.json"
OPENALEX_NO_ABSTRACT = "openalex-work-10.1145-3658644.3670378-no-abstract.json"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _crossref(year: int) -> dict[str, Any]:
    return _load(f"crossref-ccs-{year}.json")


def _doi(item: dict[str, Any]) -> str:
    return str(item.get("DOI"))


def _source(handler, **kwargs: Any) -> CcsPublicationSource:
    return CcsPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
        **kwargs,
    )


# --- parser：目录过滤与 provenance ---------------------------------------------


def test_catalog_keeps_real_research_papers_with_crossref_provenance():
    result = parse_crossref_catalog(_crossref(2024), year=2024)

    assert [record.doi for record in result.records] == list(CCS_2024_PAPERS)
    first = result.records[0]
    assert first.title == "Asynchronous Authentication"
    assert first.authors == ("Marwa Mouallem", "Ittay Eyal")
    assert first.year == 2024
    assert first.container_title == (
        "Proceedings of the 2024 on ACM SIGSAC Conference on Computer and Communications Security"
    )
    assert first.article_url == "https://dl.acm.org/doi/10.1145/3658644.3670328"
    assert first.abstract is None
    assert first.pdf_access == "unknown"
    assert first.source_kind == CCS_SOURCE_KIND
    for field in ("title", "authors", "year", "doi", "container_title", "article_url"):
        assert first.provenance[field] == "crossref"


def test_container_title_drift_is_matched_fuzzily_across_years():
    containers = {
        year: _crossref(year)["message"]["items"][0]["container-title"][0] for year in (2023, 2024, 2025)
    }
    assert "2024 on ACM SIGSAC" in containers[2024]  # ACM 多写了 "on"
    assert "2024 on ACM SIGSAC" not in containers[2025].replace("2025", "2024")
    assert " on ACM SIGSAC" not in containers[2025]
    assert " on ACM SIGSAC" not in containers[2023]
    for year, container in containers.items():
        assert is_ccs_main_track(container, year=year) is True
    # 逐年都能解析出论文（精确前缀匹配会在某些年静默返回 0）
    for year in (2023, 2024, 2025):
        assert parse_crossref_catalog(_crossref(year), year=year).records


def test_sibling_venue_asia_ccs_is_rejected():
    result = parse_crossref_catalog(_crossref(2024), year=2024)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    assert dropped[ASIA_CCS_2024] == "FOREIGN_VENUE"
    asia = _crossref(2024)["message"]["items"][-1]
    assert _doi(asia) == ASIA_CCS_2024
    assert "Asia Conference on Computer and Communications Security" in asia["container-title"][0]
    assert is_ccs_main_track(asia["container-title"][0], year=2024) is False


@pytest.mark.parametrize("doi,reason", sorted(CCS_2024_NON_PAPERS.items()))
def test_non_paper_entries_are_dropped_with_stable_reasons(doi, reason):
    result = parse_crossref_catalog(_crossref(2024), year=2024)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    assert doi not in {record.doi for record in result.records}
    assert dropped[doi] == reason
    assert result.warnings == ()


@pytest.mark.parametrize(
    "title",
    [
        # 真实反例（2019–2025 全量扫描中确认为真论文，不得误杀）
        "Posterior Security: Anonymity and Message Hiding of Standard Signatures",
        "Program Ingredients Abstraction and Instantiation for Synthesis-based JVM Testing",
        "CoCo: Efficient Browser Extension Vulnerability Detection via Coverage-guided, Concurrent Analysis",
        "A Secure Sequencer and Data Availability Committee for Rollups",
    ],
)
def test_research_paper_filter_keeps_titles_containing_trap_words(title):
    assert is_ccs_research_paper(title) is True


@pytest.mark.parametrize(
    "title",
    [
        # 真实非论文条目（fixture 内或 2019–2025 扫描所见）
        "ACM CCS 2024 Doctoral Symposium",
        "Poster: Cyber Security Economics Model (CYSEM)",
        "CCSW 2024 -- Cloud Computing Security Workshop",
        "Tutorial-HEPack4ML '23: Advanced HE Packing Methods with Applications to ML",
        "Session details: Keynote Talk I",
    ],
)
def test_research_paper_filter_drops_front_matter_and_workshop_titles(title):
    assert is_ccs_research_paper(title) is False


def test_venue_filter_returning_nothing_is_reported_not_silently_empty():
    payload = _crossref(2024)
    payload["message"]["items"] = [payload["message"]["items"][-1]]  # 只剩 AsiaCCS

    result = parse_crossref_catalog(payload, year=2024)

    assert result.records == ()
    assert CCS_VENUE_FILTER_EMPTY in result.warnings


def test_parse_rejects_payload_that_is_not_a_crossref_work_list():
    with pytest.raises(CcsPaperParseError) as error:
        parse_crossref_catalog("not json", year=2024)

    assert error.value.code == CCS_INVALID_RESPONSE


def test_openalex_abstract_and_oa_pdf_carry_aggregator_provenance():
    result = parse_crossref_catalog(_crossref(2024), year=2024)
    record = next(item for item in result.records if item.doi == "10.1145/3658644.3670374")

    enriched = CcsCatalogParser().parse_catalog(
        _crossref(2024), year=2024
    ).records  # 目录本身无摘要
    assert record.abstract is None
    assert [item.doi for item in enriched] == list(CCS_2024_PAPERS)

    merged = parse_openalex_work(_load(OPENALEX_WITH_PDF))
    assert merged.abstract.startswith("PKI schemes provide a critical foundation")
    assert merged.pdf_url == "https://dl.acm.org/doi/pdf/10.1145/3658644.3670374"
    assert merged.keywords[0] == "Computer science"
    assert CCS_OFFICIAL_DOI_AUTHORITY < CCS_AGGREGATOR_AUTHORITY

    from backend.app.paper_discovery.infrastructure.ccs_paper_parser import merge_enrichment

    filled = merge_enrichment(record, merged)
    assert filled.abstract == merged.abstract
    assert filled.keywords == merged.keywords
    assert filled.pdf_url == merged.pdf_url
    assert filled.pdf_access == "public"
    assert filled.provenance["abstract"] == "openalex"
    assert filled.provenance["title"] == "crossref"


def test_missing_openalex_abstract_keeps_record_without_abstract_provenance():
    result = parse_crossref_catalog(_crossref(2024), year=2024)
    record = next(item for item in result.records if item.doi == "10.1145/3658644.3670378")

    from backend.app.paper_discovery.infrastructure.ccs_paper_parser import merge_enrichment

    enrichment = parse_openalex_work(_load(OPENALEX_NO_ABSTRACT))
    assert enrichment.abstract is None
    assert enrichment.pdf_url is None

    merged = merge_enrichment(record, enrichment)
    assert merged.abstract is None
    assert "abstract" not in merged.provenance
    assert merged.keywords == enrichment.keywords  # 关键词是聚合来源补充，缺失摘要不影响


def test_lower_authority_enrichment_never_overwrites_higher_authority_fields():
    from backend.app.paper_discovery.infrastructure.ccs_paper_parser import merge_enrichment

    result = parse_crossref_catalog(_crossref(2024), year=2024)
    record = next(item for item in result.records if item.doi == "10.1145/3658644.3670374")
    # 模拟更高权威来源（官方页面）已写入摘要：低权威的 OpenAlex 摘要不得覆盖。
    authoritative = dataclasses.replace(
        record,
        abstract="官方页面摘要",
        keywords=("官方关键词",),
        pdf_url="https://dl.acm.org/doi/pdf/10.1145/3658644.3670374",
        provenance={**record.provenance, "abstract": "acm_ccs_page", "keywords": "acm_ccs_page"},
    )

    merged = merge_enrichment(authoritative, parse_openalex_work(_load(OPENALEX_WITH_PDF)))

    assert merged.abstract == "官方页面摘要"
    assert merged.keywords == ("官方关键词",)
    assert merged.provenance["abstract"] == "acm_ccs_page"


# --- source：单元发现、条件抓取、增量、健康 ------------------------------------


def test_discover_units_builds_one_allowlisted_unit_per_year():
    source = _source(lambda request: httpx.Response(200, json={}))

    units = source.discover_units({"years": [2025, 2024, 2024]})

    assert [unit.fetch_unit_id for unit in units] == [
        f"{CCS_SOURCE_ID}|ccs|2024",
        f"{CCS_SOURCE_ID}|ccs|2025",
    ]
    assert [unit.unit_key for unit in units] == ["ccs:2024", "ccs:2025"]
    assert [unit.year for unit in units] == [2024, 2025]
    assert [unit.status for unit in units] == ["pending", "pending"]
    for unit, year in zip(units, (2024, 2025), strict=True):
        parts = urlsplit(unit.source_url)
        assert parts.hostname == "api.crossref.org"
        assert parts.path == "/works"
        assert parts.query
        query = parse_qs(parts.query)
        assert f"from-pub-date:{year}-01-01" in query["filter"][0]
        assert query["rows"] == ["1000"]
        assert source.source_id == CCS_SOURCE_ID
        assert source.allowed_hosts == frozenset({"api.crossref.org", "api.openalex.org"})


def test_discover_units_rejects_unsupported_scope_without_network():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(200, json={}))

    for scope in ({"years": [1990]}, {"years": ["twenty"]}, {"years": []}, {"years": [None]}):
        with pytest.raises(CcsUnitRejected) as error:
            source.discover_units(scope)
        assert error.value.code == CCS_UNIT_REJECTED
    assert calls == []


def test_fetch_unit_sends_conditional_headers_and_reports_not_modified():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304, headers={"ETag": '"ccs-2024-v1"'})

    source = _source(handler)
    unit = source.discover_units([2024])[0]
    previous = dataclasses.replace(
        unit, status="completed", etag='"ccs-2024-v1"', content_hash="hash-v1"
    )

    outcome = source.fetch_unit(previous, conditional_headers={"If-None-Match": '"ccs-2024-v1"'})

    assert outcome.not_modified is True
    assert outcome.error_code is None
    assert outcome.payload is None
    assert outcome.unit.status == "completed"
    assert outcome.unit.etag == '"ccs-2024-v1"'
    assert outcome.unit.content_hash == "hash-v1"
    assert seen[0].headers["if-none-match"] == '"ccs-2024-v1"'
    assert seen[0].headers["user-agent"] == source.user_agent
    assert seen[0].url.host == "api.crossref.org"


def test_fetch_unit_records_etag_content_hash_and_timeout():
    body = json.dumps(_crossref(2024), ensure_ascii=False).encode("utf-8")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=body, headers={"ETag": '"v9"', "Last-Modified": "Wed, 03 Dec 2025 00:00:00 GMT"}
        )

    source = _source(handler, timeout=7.5)
    unit = source.discover_units([2024])[0]

    outcome = source.fetch_unit(unit)

    assert outcome.error_code is None
    assert outcome.not_modified is False
    assert outcome.payload["message"]["items"]
    assert outcome.unit.etag == '"v9"'
    assert outcome.unit.last_modified == "Wed, 03 Dec 2025 00:00:00 GMT"
    assert outcome.unit.content_hash == hashlib.sha256(body).hexdigest()
    assert outcome.unit.status == "completed"
    assert source.timeout == 7.5
    assert "if-none-match" not in seen[0].headers


def test_fetch_unit_rejects_non_allowlisted_url_without_request():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(200, json={}))
    unit = dataclasses.replace(
        source.discover_units([2024])[0],
        source_url="https://evil.test/works?rows=1000",
    )

    outcome = source.fetch_unit(unit)

    assert outcome.error_code == CCS_UNIT_REJECTED
    assert outcome.unit.status == "failed"
    assert outcome.payload is None
    assert calls == []


@pytest.mark.parametrize("status,code", [(429, CCS_RATE_LIMITED), (503, CCS_UNAVAILABLE)])
def test_fetch_unit_maps_upstream_failures_to_stable_codes(status, code):
    source = _source(lambda request: httpx.Response(status, text="busy"))
    unit = source.discover_units([2024])[0]

    outcome = source.fetch_unit(unit)

    assert outcome.error_code == code
    assert outcome.unit.status == "failed"
    assert outcome.unit.error_code == code


def test_fetch_unit_maps_invalid_json_and_network_errors():
    source = _source(lambda request: httpx.Response(200, text="<html>nope</html>"))
    unit = source.discover_units([2024])[0]
    assert source.fetch_unit(unit).error_code == CCS_INVALID_RESPONSE

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    timed_out = _source(broken).fetch_unit(unit)
    assert timed_out.error_code == CCS_UNAVAILABLE
    assert timed_out.unit.status == "failed"


def test_sync_year_follows_offset_pages():
    items = _crossref(2024)["message"]["items"]
    pages = {0: items[:2], 2: items[2:4], 4: items[4:6]}
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.crossref.org":
            return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))
        offset = parse_qs(urlsplit(str(request.url)).query)["offset"][0]
        offsets.append(offset)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "message-type": "work-list",
                "message-version": "1.0.0",
                "message": {"total-results": 6, "items": pages[int(offset)]},
            },
        )

    source = _source(handler, max_rows=2, max_pages=3)

    result = source.sync_year(2024)

    # 每页 2 条（== rows）故继续翻页，直到 max_pages 上限
    assert offsets == ["0", "2", "4"]
    assert [record.doi for record in result.records] == list(CCS_2024_PAPERS)
    assert result.error_code is None
    assert result.cached is False
    assert result.unit.paper_count == len(CCS_2024_PAPERS)


def test_sync_year_enriches_missing_abstracts_in_one_batched_openalex_request():
    """富化是**批量**的：N 条记录只发一次 OpenAlex 请求，而不是每条一次。

    CCS 2024 实测 418 篇主会论文；若退回「每条一次」，单年就要 400+ 次往返，
    且 ETag 缓存只覆盖 Crossref 目录、不覆盖富化，所以每次同步都会慢。
    """
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        # 只有 3670374 在 OpenAlex 里有记录，其余按「未命中」处理
        return httpx.Response(200, json={"results": [_load(OPENALEX_WITH_PDF)]})

    result = _source(handler).sync_year(2024)

    # 5 条主会论文 -> 1 次批量请求（而不是 5 次）
    assert len(openalex_requests) == 1
    assert "filter=doi%3A10.1145" in openalex_requests[0]
    assert "per-page=50" in openalex_requests[0]

    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.1145/3658644.3670374"].abstract.startswith("PKI schemes provide")
    assert by_doi["10.1145/3658644.3670374"].provenance["abstract"] == "openalex"
    # 批量里没有命中的记录：摘要为空，记 NO_HIT，但整年不算失败
    assert by_doi["10.1145/3658644.3670328"].abstract is None
    assert CCS_OPENALEX_NO_HIT in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(CCS_2024_PAPERS)


def test_sync_year_enriches_missing_abstracts_and_degrades_on_openalex_failure():
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        url = str(request.url)
        openalex_requests.append(url)
        if "filter=doi" in url:
            # 批量接口：3670378 无摘要，3670328 被限流（整批失败 -> 退回单条）
            if "3670328" in url:
                return httpx.Response(429, text="rate limited")
            return httpx.Response(200, json={"results": [_load(OPENALEX_NO_ABSTRACT)]})
        if "3670378" in url:
            return httpx.Response(200, json=_load(OPENALEX_NO_ABSTRACT))
        if "3670328" in url:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))

    result = _source(handler).sync_year(2024)

    # 富化是批量的：不再「每条一次」；本例批量被限流后退回单条，因此 1 + N 次
    assert len(openalex_requests) == 1 + len(CCS_2024_PAPERS)
    assert "filter=doi%3A10.1145" in openalex_requests[0]
    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.1145/3658644.3670374"].abstract.startswith("PKI schemes provide")
    assert by_doi["10.1145/3658644.3670374"].provenance["abstract"] == "openalex"
    # OpenAlex 失败只降级该篇摘要，不产生来源级错误
    assert by_doi["10.1145/3658644.3670328"].abstract is None
    assert CCS_OPENALEX_UNAVAILABLE in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(CCS_2024_PAPERS)


def test_sync_year_reuses_unchanged_unit_without_re_enriching():
    crossref_calls: list[str] = []
    openalex_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            crossref_calls.append(str(request.url))
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304, headers={"ETag": '"v1"'})
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        openalex_calls.append(str(request.url))
        return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))

    source = _source(handler)
    first = source.sync_year(2024)
    second = source.sync_year(2024, previous_unit=first.unit)

    assert len(crossref_calls) == 2
    # 第一次走批量（N 条 -> 1 次请求），第二次命中缓存、0 次富化请求
    assert len(openalex_calls) == 1
    assert second.cached is True
    assert [record.doi for record in second.records] == [record.doi for record in first.records]
    assert [record.abstract for record in second.records] == [record.abstract for record in first.records]
    assert second.unit.content_hash == first.unit.content_hash
    assert second.unit.status == "completed"


def test_sync_units_isolates_failing_years_and_keeps_the_others():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            if "2024-01-01" in (request.url.params.get("filter") or ""):
                return httpx.Response(503, text="upstream down")
            return httpx.Response(200, json=_crossref(2023))
        return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))

    result = _source(handler).sync_units({"years": [2023, 2024]})

    # 与 USENIX 范式一致：部分失败 → status=partial，来源级 error_code 保持空
    assert result.failed_years == (2024,)
    assert result.status == "partial"
    assert result.error_code is None
    assert {record.year for record in result.records} == {2023}
    assert CCS_VENUE_FILTER_EMPTY not in result.warnings


def test_health_is_side_effect_free():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(500))

    health = source.health()

    assert calls == []
    assert health["source_id"] == CCS_SOURCE_ID
    assert health["source_kind"] == CCS_SOURCE_KIND
    assert health["authority_rank"] == CCS_OFFICIAL_DOI_AUTHORITY
    assert sorted(health["allowed_hosts"]) == ["api.crossref.org", "api.openalex.org"]
    assert health["enabled"] is True
    assert health["error_code"] is None


def test_normalize_identity_reuses_existing_doi_then_title_rules():
    source = _source(lambda request: httpx.Response(200, json={}))
    record = parse_crossref_catalog(_crossref(2024), year=2024).records[0]

    assert source.normalize_identity(record) == "doi:10.1145/3658644.3670328"
    without_doi = dataclasses.replace(record, doi="")
    assert source.normalize_identity(without_doi) == "title:asynchronousauthentication|2024"
    assert source.normalize_identity(dataclasses.replace(record, doi="https://doi.org/10.1145/3658644.3670328")) == (
        "doi:10.1145/3658644.3670328"
    )


def test_a_record_with_an_injectable_doi_still_gets_enriched_per_record():
    """不可批量化的 DOI 不能丢：必须退回单条路径，富化结果与改动前一致。

    DOI 会被拼进 ``filter=doi:`` 的**查询语法**里，含 ``|`` 的 DOI 能注入额外过滤
    条件，因此不能进批量；但「不能进批量」绝不等于「不富化」——否则一篇论文会
    在有完全可用的 OpenAlex 记录时静默丢摘要。
    """
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        if "3670374" in str(request.url):
            return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))
        return httpx.Response(404, json={"error": "not found"})

    source = _source(handler)
    from backend.app.paper_discovery.infrastructure.ccs_paper_parser import CcsCatalogRecord

    def _rec(doi: str, title: str) -> CcsCatalogRecord:
        return CcsCatalogRecord(
            doi=doi, title=title, year=2024, authors=(), container_title="CCS", article_url=""
        )

    odd = _rec("10.1145/3658644.3670374|x", "Odd DOI")
    good = _rec("10.1145/3658644.3670328", "Good DOI")

    items, warnings = source.enrich_records([odd, good])

    # 畸形 DOI 走单条、正常 DOI 走批量
    assert any("filter=doi" in url for url in openalex_requests)
    assert any("3670374%7Cx" in url or "3670374|x" in url for url in openalex_requests)
    assert items[0].abstract is not None  # 没有被静默丢弃
    assert CCS_OPENALEX_NO_HIT in warnings
