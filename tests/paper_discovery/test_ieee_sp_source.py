"""Spec-032 Task 04: IEEE S&P 来源适配器定向测试（Crossref 目录 + OpenAlex 摘要）。

样本全部来自真实抓取，见 ``tests/fixtures/ieee_sp/README.md``。
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

from backend.app.paper_discovery.infrastructure.ieee_sp_paper_parser import (
    IEEE_SP_AGGREGATOR_AUTHORITY,
    IEEE_SP_INVALID_RESPONSE,
    IEEE_SP_OFFICIAL_DOI_AUTHORITY,
    IEEE_SP_SOURCE_ID,
    IEEE_SP_SOURCE_KIND,
    IEEE_SP_VENUE_FILTER_EMPTY,
    IeeeSpCatalogParser,
    IeeeSpPaperParseError,
    is_ieee_sp_main_track,
    is_ieee_sp_research_paper,
    merge_enrichment,
    parse_crossref_catalog,
    parse_openalex_work,
)
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import (
    IEEE_SP_OPENALEX_NO_HIT,
    IEEE_SP_OPENALEX_UNAVAILABLE,
    IEEE_SP_RATE_LIMITED,
    IEEE_SP_UNAVAILABLE,
    IEEE_SP_UNIT_REJECTED,
    IeeeSpPublicationSource,
    IeeeSpUnitRejected,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ieee_sp"
PUBLIC_IP = "93.184.216.34"

# 真实研究论文（IEEE S&P 主会容器 + 完整篇幅），必须保留。
SP_2024_PAPERS = (
    "10.1109/sp54263.2024.00212",
    "10.1109/sp54263.2024.00255",
    "10.1109/sp54263.2024.00219",
    "10.1109/sp54263.2024.00270",
    "10.1109/sp54263.2024.00026",
)
SP_2025_PAPERS = (
    "10.1109/sp61157.2025.00241",
    "10.1109/sp61157.2025.00083",
    "10.1109/sp61157.2025.00033",
    "10.1109/sp61157.2025.00243",
    "10.1109/sp61157.2025.00256",
)
# 真实前置页条目（IEEE 登记为 proceedings-article 且带 DOI），必须按 NON_PAPER_TITLE 丢弃。
SP_FRONT_MATTER = {
    2021: (
        "10.1109/sp40001.2021.00120",  # Organizing Committee
        "10.1109/sp40001.2021.00116",  # [Copyright notice]
        "10.1109/sp40001.2021.00121",  # Program Committee
        "10.1109/sp40001.2021.00123",  # Author Index
        "10.1109/sp40001.2021.00115",  # [Title page iii]
        "10.1109/sp40001.2021.00117",  # Table of Contents
        "10.1109/sp40001.2021.00118",  # Message from the General Chair
    ),
    2024: (
        "10.1109/sp54263.2024.00185",  # Copyright Page
        "10.1109/sp54263.2024.00193",  # Author Index
        "10.1109/sp54263.2024.00190",  # Organizing Committee
        "10.1109/sp54263.2024.00189",  # External Reviewers
        "10.1109/sp54263.2024.00187",  # Title Page iii
        "10.1109/sp54263.2024.00188",  # Table of Contents
        "10.1109/sp54263.2024.00192",  # Message from the Program Chairs
    ),
    2025: (
        "10.1109/sp61157.2025.00109",  # Keynotes
        "10.1109/sp61157.2025.00105",  # Title Page
        "10.1109/sp61157.2025.00239",  # Author Index
        "10.1109/sp61157.2025.00262",  # Organizing Committee
        "10.1109/sp61157.2025.00263",  # External Reviewers
        "10.1109/sp61157.2025.00265",  # Program Committee
        "10.1109/sp61157.2025.00108",  # Table of Contents
        "10.1109/sp61157.2025.00107",  # Copyright and Reprint Permissions
        "10.1109/sp61157.2025.00261",  # Message from the Program Chairs
    ),
}
# EuroS&P（另一个会议）主会 + EuroS&P Workshop 条目，必须按 FOREIGN_VENUE 丢弃。
EUROSP_MAIN = {
    2021: "10.1109/eurosp51992.2021.00002",
    2024: "10.1109/eurosp60621.2024.00001",
    2025: "10.1109/eurosp63326.2025.00070",
}
EUROSP_WORKSHOP = {
    2021: "10.1109/eurospw54576.2021.00035",
    2024: "10.1109/eurospw61312.2024.00002",
    2025: "10.1109/eurospw67616.2025.00002",
}
# 兄弟会议（IEEE TrustCom）条目，必须按 FOREIGN_VENUE 丢弃。
SIBLING_VENUE = {
    2021: "10.1109/trustcom53373.2021.00002",
    2024: "10.1109/trustcom63139.2024.00003",
    2025: "10.1109/trustcom66490.2025.00003",
}
OPENALEX_WITH_PDF = "openalex-work-10.1109-sp61157.2025.00241-with-oa-pdf.json"
OPENALEX_NO_PDF = "openalex-work-10.1109-sp54263.2024.00212-abstract-no-pdf.json"
OPENALEX_NO_ABSTRACT = "openalex-work-10.1109-sp61157.2025.00033-no-abstract.json"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _crossref(year: int) -> dict[str, Any]:
    return _load(f"crossref-sp-{year}.json")


def _source(handler, **kwargs: Any) -> IeeeSpPublicationSource:
    return IeeeSpPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
        **kwargs,
    )


# --- parser：目录过滤与 provenance ---------------------------------------------


def test_catalog_keeps_real_research_papers_with_crossref_provenance():
    result = parse_crossref_catalog(_crossref(2024), year=2024)

    assert [record.doi for record in result.records] == list(SP_2024_PAPERS)
    first = result.records[0]
    assert first.title == "Budget Recycling Differential Privacy"
    assert first.authors == ("Bo Jiang", "Jian Du", "Sagar Sharma", "Qiang Yan")
    assert first.year == 2024
    assert first.container_title == "2024 IEEE Symposium on Security and Privacy (SP)"
    assert first.article_url == "https://ieeexplore.ieee.org/document/10646786/"
    assert first.abstract is None
    assert first.pdf_access == "unknown"
    assert first.source_kind == IEEE_SP_SOURCE_KIND
    for field in ("title", "authors", "year", "doi", "container_title", "article_url"):
        assert first.provenance[field] == "crossref"


def test_article_url_never_uses_the_staging_pdf_link():
    item = _crossref(2024)["message"]["items"][0]
    # IEEE 的 link[] 指向 http + xplorestaging + PDF；不得被采纳。
    assert item["link"][0]["URL"].startswith("http://xplorestaging.ieee.org/")
    record = parse_crossref_catalog(_crossref(2024), year=2024).records[0]
    assert "xplorestaging" not in record.article_url
    assert record.article_url.startswith("https://ieeexplore.ieee.org/document/")


@pytest.mark.parametrize("year", [2021, 2022, 2023, 2024, 2025])
def test_every_year_parses_real_papers_across_container_drift(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    assert result.records, f"{year} 未解析出任何论文（容器匹配规则可能失效）"
    assert IEEE_SP_VENUE_FILTER_EMPTY not in result.warnings
    for record in result.records:
        assert record.year == year
        assert is_ieee_sp_main_track(record.container_title, year=year) is True


def test_european_symposium_container_is_excluded_not_matched():
    eurosp = "2024 IEEE 9th European Symposium on Security and Privacy (EuroS&P)"
    main = "2024 IEEE Symposium on Security and Privacy (SP)"

    # 两者都含 "symposium on security and privacy"；只有排除 european 才能区分。
    assert "symposium on security and privacy" in eurosp.casefold()
    assert is_ieee_sp_main_track(eurosp, year=2024) is False
    assert is_ieee_sp_main_track(main, year=2024) is True
    # EuroS&P Workshop 同时含 european + workshop，也必须排除。
    assert is_ieee_sp_main_track(
        "2024 IEEE European Symposium on Security and Privacy Workshops (EuroS&PW)", year=2024
    ) is False


@pytest.mark.parametrize("year", sorted(EUROSP_MAIN))
def test_eurosp_entries_are_dropped_as_foreign_venue(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    kept = {record.doi for record in result.records}
    assert EUROSP_MAIN[year] not in kept
    assert dropped[EUROSP_MAIN[year]] == "FOREIGN_VENUE"
    assert EUROSP_WORKSHOP[year] not in kept
    assert dropped[EUROSP_WORKSHOP[year]] == "FOREIGN_VENUE"


@pytest.mark.parametrize("year", sorted(SIBLING_VENUE))
def test_sibling_conference_entries_are_dropped_as_foreign_venue(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    assert SIBLING_VENUE[year] not in {record.doi for record in result.records}
    assert dropped[SIBLING_VENUE[year]] == "FOREIGN_VENUE"


@pytest.mark.parametrize("year", sorted(SP_FRONT_MATTER))
def test_front_matter_entries_are_dropped_with_stable_reason(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    kept = {record.doi for record in result.records}
    assert SP_FRONT_MATTER[year], "fixture 应含前置页样本"
    for doi in SP_FRONT_MATTER[year]:
        assert doi not in kept, f"{doi} 是前置页，不应保留"
        assert dropped[doi] == "NON_PAPER_TITLE"
    # 会议容器匹配成功，因此不应报「容器过滤为空」。
    assert IEEE_SP_VENUE_FILTER_EMPTY not in result.warnings


def test_page_span_is_not_used_so_real_papers_with_odd_pages_survive():
    # 2022 真论文 page=None；2023 真论文 page="2032-2032"（起==止）。
    # 若照搬 ACM CCS 的页数规则，这两篇会被误杀。
    assert _crossref(2022)["message"]["items"][-1]["DOI"] == "10.1109/sp46214.2022.9833599"
    assert _crossref(2022)["message"]["items"][-1].get("page") is None
    assert _crossref(2023)["message"]["items"][-1]["DOI"] == "10.1109/sp46215.2023.10179333"
    assert _crossref(2023)["message"]["items"][-1]["page"] == "2032-2032"

    assert "10.1109/sp46214.2022.9833599" in {r.doi for r in parse_crossref_catalog(_crossref(2022), year=2022).records}
    assert "10.1109/sp46215.2023.10179333" in {r.doi for r in parse_crossref_catalog(_crossref(2023), year=2023).records}


@pytest.mark.parametrize(
    "title",
    [
        # 真实反例：含 copyright 但确为真论文
        "Copy, Right? A Testing Framework for Copyright Protection of Deep Learning Models",
        "PromptCARE: Prompt Copyright Protection by Watermark Injection and Verification",
        "SoK: Dataset Copyright Auditing in Machine Learning Systems",
        # 真实短标题论文（2 词以内）
        "Dropout Attacks",
        "Machine Unlearning",
        "PAC-Private Algorithms",
        "Post-quantum WireGuard",
        "SoK: Quantifying Cyber Risk",
    ],
)
def test_research_paper_filter_keeps_titles_containing_trap_words(title):
    assert is_ieee_sp_research_paper(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Author Index",
        "Copyright Page",
        "[Copyright notice]",
        "Copyright and Reprint Permissions",
        "External Reviewers",
        "Keynotes",
        "Organizing Committee",
        "Program Committee",
        "Table of Contents",
        "Title Page",
        "Title Page i",
        "[Title page iii]",
        "Message from the General Chair",
        "Message from the Program Chairs",
        "Front Matter",
        "Editorial",
    ],
)
def test_research_paper_filter_drops_front_matter_titles(title):
    assert is_ieee_sp_research_paper(title) is False


def test_venue_filter_returning_nothing_is_reported_not_silently_empty():
    payload = _crossref(2024)
    payload["message"]["items"] = [payload["message"]["items"][-1]]  # 只剩 TrustCom 兄弟会议

    result = parse_crossref_catalog(payload, year=2024)

    assert result.records == ()
    assert IEEE_SP_VENUE_FILTER_EMPTY in result.warnings


def test_parse_rejects_payload_that_is_not_a_crossref_work_list():
    with pytest.raises(IeeeSpPaperParseError) as error:
        parse_crossref_catalog("not json", year=2024)

    assert error.value.code == IEEE_SP_INVALID_RESPONSE


def test_openalex_abstract_and_oa_pdf_carry_aggregator_provenance():
    result = parse_crossref_catalog(_crossref(2025), year=2025)
    record = next(item for item in result.records if item.doi == "10.1109/sp61157.2025.00241")
    assert record.abstract is None  # Crossref 目录本身无摘要

    merged = parse_openalex_work(_load(OPENALEX_WITH_PDF))
    assert merged.abstract.startswith("The widespread adoption of conversational AI platforms")
    assert merged.pdf_url == "https://arxiv.org/pdf/2504.06552"
    assert merged.keywords
    assert IEEE_SP_OFFICIAL_DOI_AUTHORITY < IEEE_SP_AGGREGATOR_AUTHORITY

    filled = merge_enrichment(record, merged)
    assert filled.abstract == merged.abstract
    assert filled.keywords == merged.keywords
    assert filled.pdf_url == merged.pdf_url
    assert filled.pdf_access == "public"
    assert filled.provenance["abstract"] == "openalex"
    assert filled.provenance["pdf_url"] == "openalex"
    assert filled.provenance["title"] == "crossref"


def test_abstract_without_oa_pdf_keeps_pdf_unknown():
    result = parse_crossref_catalog(_crossref(2024), year=2024)
    record = next(item for item in result.records if item.doi == "10.1109/sp54263.2024.00212")

    enrichment = parse_openalex_work(_load(OPENALEX_NO_PDF))
    assert enrichment.abstract
    assert enrichment.pdf_url is None

    filled = merge_enrichment(record, enrichment)
    assert filled.abstract == enrichment.abstract
    assert filled.pdf_url is None
    assert filled.pdf_access == "unknown"
    assert filled.provenance["abstract"] == "openalex"
    assert "pdf_url" not in filled.provenance


def test_missing_openalex_abstract_keeps_record_without_abstract_provenance():
    result = parse_crossref_catalog(_crossref(2025), year=2025)
    record = next(item for item in result.records if item.doi == "10.1109/sp61157.2025.00033")

    enrichment = parse_openalex_work(_load(OPENALEX_NO_ABSTRACT))
    assert enrichment.abstract is None
    assert enrichment.pdf_url is None

    merged = merge_enrichment(record, enrichment)
    assert merged.abstract is None
    assert "abstract" not in merged.provenance
    assert merged.keywords == enrichment.keywords  # 关键词是聚合来源补充，缺失摘要不影响


def test_lower_authority_enrichment_never_overwrites_higher_authority_fields():
    result = parse_crossref_catalog(_crossref(2025), year=2025)
    record = next(item for item in result.records if item.doi == "10.1109/sp61157.2025.00241")
    # 模拟更高权威来源（官方会议页面）已写入摘要/关键词/PDF：低权威的 OpenAlex 不得覆盖。
    authoritative = dataclasses.replace(
        record,
        abstract="官方页面摘要",
        keywords=("官方关键词",),
        pdf_url="https://www.ieee-security.org/TC/SP2025/papers/x.pdf",
        provenance={
            **record.provenance,
            "abstract": "ieee_sp_page",
            "keywords": "ieee_sp_page",
            "pdf_url": "ieee_sp_page",
        },
    )

    merged = merge_enrichment(authoritative, parse_openalex_work(_load(OPENALEX_WITH_PDF)))

    assert merged.abstract == "官方页面摘要"
    assert merged.keywords == ("官方关键词",)
    assert merged.pdf_url == "https://www.ieee-security.org/TC/SP2025/papers/x.pdf"
    assert merged.provenance["abstract"] == "ieee_sp_page"
    assert merged.provenance["pdf_url"] == "ieee_sp_page"


# --- source：单元发现、条件抓取、增量、健康 ------------------------------------


def test_discover_units_builds_one_allowlisted_unit_per_year():
    source = _source(lambda request: httpx.Response(200, json={}))

    units = source.discover_units({"years": [2025, 2024, 2024]})

    assert [unit.fetch_unit_id for unit in units] == [
        f"{IEEE_SP_SOURCE_ID}|sp|2024",
        f"{IEEE_SP_SOURCE_ID}|sp|2025",
    ]
    assert [unit.unit_key for unit in units] == ["sp:2024", "sp:2025"]
    assert [unit.year for unit in units] == [2024, 2025]
    assert [unit.status for unit in units] == ["pending", "pending"]
    for unit, year in zip(units, (2024, 2025), strict=True):
        parts = urlsplit(unit.source_url)
        assert parts.hostname == "api.crossref.org"
        assert parts.path == "/works"
        assert parts.query
        query = parse_qs(parts.query)
        assert "member:263" in query["filter"][0]
        assert f"from-pub-date:{year}-01-01" in query["filter"][0]
        assert query["rows"] == ["1000"]
        assert "IEEE Symposium on Security and Privacy" in query["query.bibliographic"][0]
        assert source.source_id == IEEE_SP_SOURCE_ID
        assert source.allowed_hosts == frozenset({"api.crossref.org", "api.openalex.org"})


def test_discover_units_rejects_unsupported_scope_without_network():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(200, json={}))

    for scope in ({"years": [1979]}, {"years": ["twenty"]}, {"years": []}, {"years": [None]}):
        with pytest.raises(IeeeSpUnitRejected) as error:
            source.discover_units(scope)
        assert error.value.code == IEEE_SP_UNIT_REJECTED
    assert calls == []


def test_fetch_unit_sends_conditional_headers_and_reports_not_modified():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304, headers={"ETag": '"sp-2024-v1"'})

    source = _source(handler)
    unit = source.discover_units([2024])[0]
    previous = dataclasses.replace(
        unit, status="completed", etag='"sp-2024-v1"', content_hash="hash-v1"
    )

    outcome = source.fetch_unit(previous, conditional_headers={"If-None-Match": '"sp-2024-v1"'})

    assert outcome.not_modified is True
    assert outcome.error_code is None
    assert outcome.payload is None
    assert outcome.unit.status == "completed"
    assert outcome.unit.etag == '"sp-2024-v1"'
    assert outcome.unit.content_hash == "hash-v1"
    assert seen[0].headers["if-none-match"] == '"sp-2024-v1"'
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

    assert outcome.error_code == IEEE_SP_UNIT_REJECTED
    assert outcome.unit.status == "failed"
    assert outcome.payload is None
    assert calls == []


@pytest.mark.parametrize("status,code", [(429, IEEE_SP_RATE_LIMITED), (503, IEEE_SP_UNAVAILABLE)])
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
    assert source.fetch_unit(unit).error_code == IEEE_SP_INVALID_RESPONSE

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    timed_out = _source(broken).fetch_unit(unit)
    assert timed_out.error_code == IEEE_SP_UNAVAILABLE
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
    assert [record.doi for record in result.records] == list(SP_2024_PAPERS)
    assert result.error_code is None
    assert result.cached is False
    assert result.unit.paper_count == len(SP_2024_PAPERS)


def test_sync_year_enriches_missing_abstracts_in_one_batched_openalex_request():
    """富化是**批量**的：N 条记录只发一次 OpenAlex 请求，而不是每条一次。

    S&P 2024/2025 各约 260 篇主会论文；若退回「每条一次」，单年就要 260+ 次往返。
    """
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2025), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        # 只有 00241 在 OpenAlex 里有记录，其余按「未命中」处理
        return httpx.Response(200, json={"results": [_load(OPENALEX_WITH_PDF)]})

    result = _source(handler).sync_year(2025)

    # 5 条主会论文 -> 1 次批量请求（而不是 5 次）
    assert len(openalex_requests) == 1
    assert "filter=doi%3A10.1109" in openalex_requests[0]
    assert "per-page=50" in openalex_requests[0]

    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.1109/sp61157.2025.00241"].abstract.startswith("The widespread adoption")
    assert by_doi["10.1109/sp61157.2025.00241"].provenance["abstract"] == "openalex"
    # 批量里没有命中的记录：摘要为空，记 NO_HIT，但整年不算失败
    assert by_doi["10.1109/sp61157.2025.00083"].abstract is None
    assert IEEE_SP_OPENALEX_NO_HIT in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(SP_2025_PAPERS)


def test_sync_year_enriches_missing_abstracts_and_degrades_on_openalex_failure():
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2025), headers={"ETag": '"v1"'})
        url = str(request.url)
        openalex_requests.append(url)
        if "filter=doi" in url:
            # 批量接口被限流：整批失败 -> 退回单条，语义与批量化前完全一致
            return httpx.Response(429, text="rate limited")
        if "00083" in url:
            return httpx.Response(404, text="not found")  # 真实：该篇不在 OpenAlex
        if "00033" in url:
            return httpx.Response(200, json=_load(OPENALEX_NO_ABSTRACT))
        if "00241" in url:
            return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))
        return httpx.Response(429, text="rate limited")

    result = _source(handler).sync_year(2025)

    # 1 次批量 + 退回后的每条一次
    assert len(openalex_requests) == 1 + len(SP_2025_PAPERS)
    assert "filter=doi%3A10.1109" in openalex_requests[0]
    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.1109/sp61157.2025.00241"].abstract.startswith("The widespread adoption of conversational AI platforms")
    assert by_doi["10.1109/sp61157.2025.00241"].provenance["abstract"] == "openalex"
    assert by_doi["10.1109/sp61157.2025.00241"].pdf_url == "https://arxiv.org/pdf/2504.06552"
    # OpenAlex 无该篇 / 摘要缺失 / 限流：只降级该篇，不产生来源级错误
    assert by_doi["10.1109/sp61157.2025.00083"].abstract is None
    assert by_doi["10.1109/sp61157.2025.00033"].abstract is None
    assert IEEE_SP_OPENALEX_NO_HIT in result.warnings
    assert IEEE_SP_OPENALEX_UNAVAILABLE in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(SP_2025_PAPERS)


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
    assert IEEE_SP_VENUE_FILTER_EMPTY not in result.warnings


def test_health_is_side_effect_free():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(500))

    health = source.health()

    assert calls == []
    assert health["source_id"] == IEEE_SP_SOURCE_ID
    assert health["source_kind"] == IEEE_SP_SOURCE_KIND
    assert health["authority_rank"] == IEEE_SP_OFFICIAL_DOI_AUTHORITY
    assert sorted(health["allowed_hosts"]) == ["api.crossref.org", "api.openalex.org"]
    assert health["enabled"] is True
    assert health["error_code"] is None


def test_normalize_identity_reuses_existing_doi_then_title_rules():
    source = _source(lambda request: httpx.Response(200, json={}))
    record = parse_crossref_catalog(_crossref(2024), year=2024).records[0]

    assert source.normalize_identity(record) == "doi:10.1109/sp54263.2024.00212"
    without_doi = dataclasses.replace(record, doi="")
    assert source.normalize_identity(without_doi) == "title:budgetrecyclingdifferentialprivacy|2024"
    assert source.normalize_identity(
        dataclasses.replace(record, doi="https://doi.org/10.1109/sp54263.2024.00212")
    ) == "doi:10.1109/sp54263.2024.00212"


def test_parser_object_matches_module_functions():
    parser = IeeeSpCatalogParser()

    result = parser.parse_catalog(_crossref(2024), year=2024)
    assert [record.doi for record in result.records] == list(SP_2024_PAPERS)
    enrichment = parser.parse_enrichment(_load(OPENALEX_WITH_PDF))
    assert enrichment.abstract
    record = result.records[0]
    assert parser.merge(record, enrichment).provenance["abstract"] == "openalex"


def test_a_record_with_an_injectable_doi_still_gets_enriched_per_record():
    """不可批量化的 DOI 不能丢：必须退回单条路径，富化结果与改动前一致。

    DOI 会被拼进 ``filter=doi:`` 的**查询语法**里，含 ``|`` 的 DOI 能注入额外过滤
    条件，因此不能进批量；但「不能进批量」绝不等于「不富化」。
    """
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2025), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        if "00241" in str(request.url):
            return httpx.Response(200, json=_load(OPENALEX_WITH_PDF))
        return httpx.Response(404, json={"error": "not found"})

    source = _source(handler)
    from backend.app.paper_discovery.infrastructure.ieee_sp_paper_parser import IeeeSpCatalogRecord

    def _rec(doi: str, title: str) -> IeeeSpCatalogRecord:
        return IeeeSpCatalogRecord(
            doi=doi, title=title, year=2025, authors=(), container_title="S&P", article_url=""
        )

    odd = _rec("10.1109/sp61157.2025.00241|x", "Odd DOI")
    good = _rec("10.1109/sp61157.2025.00083", "Good DOI")

    items, warnings = source.enrich_records([odd, good])

    # 畸形 DOI 走单条、正常 DOI 走批量
    assert any("filter=doi" in url for url in openalex_requests)
    assert any("00241%7Cx" in url or "00241|x" in url for url in openalex_requests)
    assert items[0].abstract is not None  # 没有被静默丢弃
    assert IEEE_SP_OPENALEX_NO_HIT in warnings
