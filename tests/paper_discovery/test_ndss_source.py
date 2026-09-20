"""Spec-032 Task 04: NDSS 来源适配器定向测试（Crossref 目录 + OpenAlex 摘要）。

样本全部来自真实抓取，见 ``tests/fixtures/ndss/README.md``。
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

from backend.app.paper_discovery.infrastructure.ndss_paper_parser import (
    AUTHORITY_OFFICIAL_VENUE,
    NDSS_AGGREGATOR_AUTHORITY,
    NDSS_INVALID_RESPONSE,
    NDSS_OFFICIAL_DOI_AUTHORITY,
    NDSS_SOURCE_ID,
    NDSS_SOURCE_KIND,
    NDSS_VENUE_FILTER_EMPTY,
    NdssCatalogParser,
    NdssPaperParseError,
    is_ndss_main_track,
    is_ndss_research_paper,
    merge_enrichment,
    parse_crossref_catalog,
    parse_openalex_work,
)
from backend.app.paper_discovery.infrastructure.ndss_publication_source import (
    NDSS_OPENALEX_NO_HIT,
    NDSS_OPENALEX_UNAVAILABLE,
    NDSS_RATE_LIMITED,
    NDSS_UNAVAILABLE,
    NDSS_UNIT_REJECTED,
    NdssPublicationSource,
    NdssUnitRejected,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ndss"
PUBLIC_IP = "93.184.216.34"

#: 各年份 fixture 里真实主会论文的 DOI（顺序即 fixture 顺序）。
NDSS_MAIN_PAPERS: dict[int, tuple[str, ...]] = {
    2021: (
        "10.14722/ndss.2021.24051",
        "10.14722/ndss.2021.24118",
        "10.14722/ndss.2021.24378",
    ),
    2022: (
        "10.14722/ndss.2022.23037",
        "10.14722/ndss.2022.24078",
        "10.14722/ndss.2022.23106",
    ),
    2023: (
        "10.14722/ndss.2023.24832",
        "10.14722/ndss.2023.23072",
        "10.14722/ndss.2023.23398",
    ),
    2024: (
        "10.14722/ndss.2024.23295",
        "10.14722/ndss.2024.24125",
        "10.14722/ndss.2024.24327",
        "10.14722/ndss.2024.23197",
        "10.14722/ndss.2024.23492",
    ),
    2025: (
        "10.14722/ndss.2025.240418",
        "10.14722/ndss.2025.240294",
        "10.14722/ndss.2025.230187",
        "10.14722/ndss.2025.230284",
    ),
}

#: 真实「误收」候选：与 NDSS 同处 prefix 10.14722 的 co-located 会议/研讨会，必须丢弃。
NDSS_COLOCATED_DOIS: dict[int, tuple[str, ...]] = {
    2021: (
        "10.14722/autosec.2021.23035",  # VehicleSec 前身
        "10.14722/laser-ndss.2021.23056",  # DOI 里带 ndss，仍是另一个研讨会
        "10.14722/madweb.2021.23016",
        "10.14722/coronadef.2021.23004",
    ),
    2022: (
        "10.14722/usec.2022.23094",  # Symposium on Usable Security（非 workshop，靠短语过滤）
        "10.14722/autosec.2022.23018",
        "10.14722/bar.2022.23008",
        "10.14722/fuzzing.2022.23006",
    ),
    2023: (
        "10.14722/vehiclesec.2023.23087",
        "10.14722/usec.2023.231868",
        "10.14722/spacesec.2023.231491",
        "10.14722/wosoc.2023.23014",
    ),
    2024: (
        "10.14722/vehiclesec.2024.23012",
        "10.14722/usec.2024.23030",
        "10.14722/spacesec.2024.23008",
        "10.14722/sdiotsec.2024.23048",
    ),
    2025: (
        "10.14722/usec.2025.23031",
        "10.14722/futureg.2025.23071",
        "10.14722/wosoc.2025.23018",
        "10.14722/spacesec.2025.23027",
    ),
}

OPENALEX_2024_WITH_ABSTRACT = "openalex-work-10.14722-ndss.2024.23295-with-abstract-doi-pdf.json"
OPENALEX_2021_NO_ABSTRACT = "openalex-work-10.14722-ndss.2021.24378-no-abstract.json"
OPENALEX_2025_WITH_ABSTRACT = "openalex-work-10.14722-ndss.2025.240418-with-abstract.json"

#: 真实主会论文标题，含过滤规则陷阱词，必须保留。
REAL_TITLES_WITH_TRAP_WORDS = (
    # ^welcome 若不加限定会误杀这篇 2025 真论文
    "Welcome to Jurassic Park: A Comprehensive Study of Security Risks in Deno and its Ecosystem",
    # ^front matter 若不加 "matter" 会误杀
    "Front-running Attack in Sharded Blockchains and Fair Cross-shard Consensus",
    # abstract 子串匹配会误杀
    "GNNIC: Finding Long-Lost Sibling Functions with Abstract Similarity",
    # "Matter"（IoT Matter 协议）会误杀
    "Hidden and Lost Control: on Security Design Risks in IoT User-Facing Matter Controller",
    # "Sessions" 会误杀
    "Flow Correlation Attacks on Tor Onion Service Sessions with Sliding Subset Sum",
    "Real Threshold ECDSA",
    "Cross-Language Attacks",
)

#: 前置页 / 非论文标题形态（含真实抓取到的 VehicleSec poster 标题），必须丢弃。
FRONT_MATTER_TITLES = (
    "Poster: Sensor-based Vehicle Image Authentication",  # 真实（10.14722/vehiclesec.2024.2510）
    "Poster: Effects of Knowledge and Experience on Drivers' Intention to Use CAVs",  # 真实
    "Poster: Exploring CAN Ringing for ECU Fingerprinting",  # 真实
    "Title Page",
    "Author Index",
    "Front Matter",
    "Table of Contents",
    "Session details: Keynote Talk I",
    "Keynote Address: Security in the Next Decade",
    "Welcome Message from the Program Chairs",
    "Doctoral Symposium",
    "Workshop on Measurements, Attacks, and Defenses for the Web",
    "Tutorial: Binary Analysis 101",
    "Panel: The Future of Network Security",
)


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _crossref(year: int) -> dict[str, Any]:
    return _load(f"crossref-ndss-{year}.json")


def _items(year: int) -> list[dict[str, Any]]:
    return list(_crossref(year)["message"]["items"])


def _source(handler, **kwargs: Any) -> NdssPublicationSource:
    return NdssPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
        **kwargs,
    )


# --- parser：目录过滤与 provenance ---------------------------------------------


def test_catalog_keeps_real_research_papers_with_crossref_provenance():
    result = parse_crossref_catalog(_crossref(2024), year=2024)

    assert [record.doi for record in result.records] == list(NDSS_MAIN_PAPERS[2024])
    first = result.records[0]
    assert first.title == "Bernoulli Honeywords"
    assert first.authors == ("Ke Coby Wang", "Michael K. Reiter")
    assert first.year == 2024
    assert first.container_title == "Proceedings 2024 Network and Distributed System Security Symposium"
    # NDSS 在 Crossref 只有 DOI 解析地址可用作官方记录页，官方 PDF 另存 pdf_url。
    assert first.article_url == "https://doi.org/10.14722/ndss.2024.23295"
    assert first.pdf_url == "https://www.ndss-symposium.org/wp-content/uploads/2024-295-paper.pdf"
    assert first.pdf_access == "public"
    assert first.abstract is None
    assert first.source_kind == NDSS_SOURCE_KIND
    for field in ("title", "authors", "year", "doi", "container_title", "article_url", "pdf_url"):
        assert first.provenance[field] == "crossref"


@pytest.mark.parametrize("year", sorted(NDSS_MAIN_PAPERS))
def test_multi_year_catalogs_all_parse_the_same_research_papers(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    assert [record.doi for record in result.records] == list(NDSS_MAIN_PAPERS[year])
    assert {record.year for record in result.records} == {year}
    for record in result.records:
        # 容器标题格式为「Proceedings <year> Network and Distributed System Security Symposium」
        assert str(year) in record.container_title
        assert "Network and Distributed System Security Symposium" in record.container_title
        assert record.pdf_url and record.pdf_url.startswith("https://www.ndss-symposium.org/")
        assert record.pdf_url.endswith(".pdf")
    assert result.warnings == ()


@pytest.mark.parametrize("year", sorted(NDSS_MAIN_PAPERS))
def test_container_phrase_is_matched_across_years(year):
    containers = {record.container_title for record in parse_crossref_catalog(_crossref(year), year=year).records}
    assert containers == {f"Proceedings {year} Network and Distributed System Security Symposium"}
    for container in containers:
        assert is_ndss_main_track(container, year=year) is True
    # 年份在中间（不是 "Proceedings of the ..."），且缺年份即不匹配
    assert is_ndss_main_track("Proceedings Network and Distributed System Security Symposium", year=year) is False
    assert is_ndss_main_track("Proceedings 2019 Network and Distributed System Security Symposium", year=year) is False


@pytest.mark.parametrize("year", sorted(NDSS_COLOCATED_DOIS))
def test_colocated_venues_sharing_the_doi_prefix_are_rejected(year):
    result = parse_crossref_catalog(_crossref(year), year=year)

    dropped = {entry.doi: entry.reason for entry in result.dropped}
    kept = {record.doi for record in result.records}
    for doi in NDSS_COLOCATED_DOIS[year]:
        assert doi not in kept
        assert dropped[doi] == "FOREIGN_VENUE"
    # fixture 里每个 co-located 条目的容器都必须被否掉（含 USEC 这种非 workshop 会议）
    items = {item["DOI"]: item for item in _items(year)}
    for doi in NDSS_COLOCATED_DOIS[year]:
        container = " ".join(items[doi]["container-title"])
        assert is_ndss_main_track(container, year=year) is False


def test_symposium_on_usable_security_is_not_matched_by_a_loose_symposium_keyword():
    """NDSS 版的「相近会议误收」反例：USEC 是独立会议，不得靠 'symposium' 关键字收进来。"""
    usec = "Proceedings 2024 Symposium on Usable Security"
    vehiclesec = "Proceedings Symposium on Vehicle Security &amp; Privacy"

    assert "symposium" in usec.casefold()
    assert is_ndss_main_track(usec, year=2024) is False
    assert is_ndss_main_track(vehiclesec, year=2024) is False
    # 只认完整短语，不认 'distributed system security' 之类的部分短语
    assert is_ndss_main_track("Proceedings 2024 Workshop on Distributed System Security", year=2024) is False
    assert is_ndss_main_track("", year=2024) is False


@pytest.mark.parametrize("title", REAL_TITLES_WITH_TRAP_WORDS)
def test_research_paper_filter_keeps_real_titles_containing_trap_words(title):
    assert is_ndss_research_paper(title) is True


@pytest.mark.parametrize("title", FRONT_MATTER_TITLES)
def test_research_paper_filter_drops_front_matter_titles(title):
    assert is_ndss_research_paper(title) is False


def test_structure_change_front_matter_under_the_main_container_is_dropped():
    """结构变化模拟：若 NDSS 某天把 poster 登记进主会容器，适配器必须丢弃它。

    样本本体是真实 2024 响应，仅把其中一条真实主会条目的标题替换为同一出版方
    （VehicleSec 2024）真实存在的 poster 标题，用于固定前置页过滤行为。
    """
    payload = json.loads(json.dumps(_crossref(2024)))
    poster = next(item for item in payload["message"]["items"] if item["DOI"] == "10.14722/ndss.2024.23492")
    poster["title"] = ["Poster: Sensor-based Vehicle Image Authentication"]

    result = parse_crossref_catalog(payload, year=2024)

    assert "10.14722/ndss.2024.23492" not in {record.doi for record in result.records}
    dropped = {entry.doi: entry.reason for entry in result.dropped}
    assert dropped["10.14722/ndss.2024.23492"] == "NON_PAPER_TITLE"


def test_venue_filter_returning_nothing_is_reported_not_silently_empty():
    payload = json.loads(json.dumps(_crossref(2024)))
    items = payload["message"]["items"]
    payload["message"]["items"] = [item for item in items if item["DOI"] in NDSS_COLOCATED_DOIS[2024]]

    result = parse_crossref_catalog(payload, year=2024)

    assert result.records == ()
    assert NDSS_VENUE_FILTER_EMPTY in result.warnings


def test_parse_rejects_payload_that_is_not_a_crossref_work_list():
    with pytest.raises(NdssPaperParseError) as error:
        parse_crossref_catalog("not json", year=2024)

    assert error.value.code == NDSS_INVALID_RESPONSE


def test_openalex_abstract_is_merged_with_aggregator_provenance():
    record = next(
        item
        for item in parse_crossref_catalog(_crossref(2024), year=2024).records
        if item.doi == "10.14722/ndss.2024.23295"
    )
    assert record.abstract is None

    enrichment = parse_openalex_work(_load(OPENALEX_2024_WITH_ABSTRACT))
    assert enrichment.abstract.startswith('Decoy passwords, or "honeywords,"')
    assert enrichment.keywords[0] == "Password"
    assert AUTHORITY_OFFICIAL_VENUE < NDSS_OFFICIAL_DOI_AUTHORITY < NDSS_AGGREGATOR_AUTHORITY

    merged = merge_enrichment(record, enrichment)

    assert merged.abstract == enrichment.abstract
    assert merged.provenance["abstract"] == "openalex"
    assert merged.provenance["title"] == "crossref"
    assert merged.provenance["pdf_url"] == "crossref"
    # 官方 PDF（Crossref 提交的 ndss-symposium.org 地址）不被聚合来源覆盖
    assert merged.pdf_url == record.pdf_url


def test_openalex_doi_resolver_pdf_url_is_not_recorded_as_a_pdf():
    """OpenAlex 对 Internet Society 的提交把 doi.org 解析地址塞进 best_oa_location.pdf_url。

    那不是 PDF 地址，适配器只接受真正以 .pdf 结尾的路径，因此该字段应为 None。
    """
    payload = _load(OPENALEX_2024_WITH_ABSTRACT)
    assert payload["best_oa_location"]["pdf_url"] == "https://doi.org/10.14722/ndss.2024.23295"

    enrichment = parse_openalex_work(payload)

    assert enrichment.pdf_url is None
    assert enrichment.is_oa is True


def test_missing_openalex_abstract_keeps_record_without_abstract_provenance():
    record = next(
        item
        for item in parse_crossref_catalog(_crossref(2021), year=2021).records
        if item.doi == "10.14722/ndss.2021.24378"
    )

    enrichment = parse_openalex_work(_load(OPENALEX_2021_NO_ABSTRACT))
    assert enrichment.abstract is None
    assert enrichment.pdf_url is None

    merged = merge_enrichment(record, enrichment)

    assert merged.abstract is None
    assert "abstract" not in merged.provenance
    assert merged.keywords == enrichment.keywords  # 关键词是聚合来源补充，缺失摘要不影响


def test_lower_authority_enrichment_never_overwrites_higher_authority_fields():
    record = next(
        item
        for item in parse_crossref_catalog(_crossref(2024), year=2024).records
        if item.doi == "10.14722/ndss.2024.23295"
    )
    # 模拟更高权威来源（NDSS 官方页面）已写入摘要/关键词：低权威的 OpenAlex 不得覆盖。
    authoritative = dataclasses.replace(
        record,
        abstract="官方页面摘要",
        keywords=("官方关键词",),
        provenance={**record.provenance, "abstract": "ndss_official_page", "keywords": "ndss_official_page"},
    )

    merged = merge_enrichment(authoritative, parse_openalex_work(_load(OPENALEX_2025_WITH_ABSTRACT)))

    assert merged.abstract == "官方页面摘要"
    assert merged.keywords == ("官方关键词",)
    assert merged.provenance["abstract"] == "ndss_official_page"


def test_object_parser_matches_module_level_functions():
    parser = NdssCatalogParser()
    result = parser.parse_catalog(_crossref(2023), year=2023)

    assert [record.doi for record in result.records] == list(NDSS_MAIN_PAPERS[2023])
    enrichment = parser.parse_enrichment(_load(OPENALEX_2025_WITH_ABSTRACT))
    assert parser.merge(result.records[0], enrichment).provenance["abstract"] == "openalex"


# --- source：单元发现、条件抓取、增量、健康 ------------------------------------


def test_discover_units_builds_one_allowlisted_unit_per_year():
    source = _source(lambda request: httpx.Response(200, json={}))

    units = source.discover_units({"years": [2025, 2024, 2024]})

    assert [unit.fetch_unit_id for unit in units] == [
        f"{NDSS_SOURCE_ID}|ndss|2024",
        f"{NDSS_SOURCE_ID}|ndss|2025",
    ]
    assert [unit.unit_key for unit in units] == ["ndss:2024", "ndss:2025"]
    assert [unit.year for unit in units] == [2024, 2025]
    assert [unit.status for unit in units] == ["pending", "pending"]
    assert [unit.source_kind for unit in units] == [NDSS_SOURCE_KIND, NDSS_SOURCE_KIND]
    for unit, year in zip(units, (2024, 2025), strict=True):
        parts = urlsplit(unit.source_url)
        assert parts.hostname == "api.crossref.org"
        assert parts.path == "/works"
        query = parse_qs(parts.query)
        assert "prefix:10.14722" in query["filter"][0]
        assert f"from-pub-date:{year}-01-01" in query["filter"][0]
        assert f"until-pub-date:{year}-12-31" in query["filter"][0]
        assert "type:proceedings-article" in query["filter"][0]
        assert str(year) in query["query.bibliographic"][0]
        assert query["rows"] == ["1000"]
    assert source.source_id == NDSS_SOURCE_ID
    assert source.allowed_hosts == frozenset({"api.crossref.org", "api.openalex.org"})


def test_discover_units_rejects_unsupported_scope_without_network():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(200, json={}))

    for scope in ({"years": [1990]}, {"years": ["twenty"]}, {"years": []}, {"years": [None]}, object()):
        with pytest.raises(NdssUnitRejected) as error:
            source.discover_units(scope)
        assert error.value.code == NDSS_UNIT_REJECTED
    assert calls == []


def test_fetch_unit_sends_conditional_headers_and_reports_not_modified():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304, headers={"ETag": '"ndss-2024-v1"'})

    source = _source(handler)
    unit = source.discover_units([2024])[0]
    previous = dataclasses.replace(unit, status="completed", etag='"ndss-2024-v1"', content_hash="hash-v1")

    outcome = source.fetch_unit(previous, conditional_headers={"If-None-Match": '"ndss-2024-v1"'})

    assert outcome.not_modified is True
    assert outcome.error_code is None
    assert outcome.payload is None
    assert outcome.unit.status == "completed"
    assert outcome.unit.etag == '"ndss-2024-v1"'
    assert outcome.unit.content_hash == "hash-v1"
    assert seen[0].headers["if-none-match"] == '"ndss-2024-v1"'
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

    assert outcome.error_code == NDSS_UNIT_REJECTED
    assert outcome.unit.status == "failed"
    assert outcome.payload is None
    assert calls == []


@pytest.mark.parametrize("status,code", [(429, NDSS_RATE_LIMITED), (503, NDSS_UNAVAILABLE)])
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
    assert source.fetch_unit(unit).error_code == NDSS_INVALID_RESPONSE

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    timed_out = _source(broken).fetch_unit(unit)
    assert timed_out.error_code == NDSS_UNAVAILABLE
    assert timed_out.unit.status == "failed"


def test_sync_year_follows_offset_pages():
    items = _items(2024)
    pages = {0: items[:2], 2: items[2:4], 4: items[4:6]}
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.crossref.org":
            return httpx.Response(200, json=_load(OPENALEX_2024_WITH_ABSTRACT))
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
    assert [record.doi for record in result.records] == list(NDSS_MAIN_PAPERS[2024])
    assert result.error_code is None
    assert result.cached is False
    assert result.unit.paper_count == len(NDSS_MAIN_PAPERS[2024])


def test_sync_year_enriches_missing_abstracts_in_one_batched_openalex_request():
    """富化是**批量**的：N 条记录只发一次 OpenAlex 请求，而不是每条一次。

    改动前这里断言 ``len(openalex_requests) == len(NDSS_MAIN_PAPERS[2024])``（每条一次）。
    实测 140 条耗时 142 秒、且重跑不省；批量化后同量级约 10 秒。
    """
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        # 只有 23295 在 OpenAlex 里有记录，其余按「未命中」处理
        return httpx.Response(200, json={"results": [_load(OPENALEX_2024_WITH_ABSTRACT)]})

    result = _source(handler).sync_year(2024)

    # 5 条主会论文 -> 1 次批量请求（而不是 5 次）
    assert len(openalex_requests) == 1
    assert "filter=doi%3A10.14722%2Fndss.2024.23295" in openalex_requests[0]
    assert "per-page=50" in openalex_requests[0]

    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.14722/ndss.2024.23295"].abstract.startswith('Decoy passwords, or "honeywords,"')
    assert by_doi["10.14722/ndss.2024.23295"].provenance["abstract"] == "openalex"
    # 批量里没有命中的记录：摘要为空，记 NO_HIT，但整年不算失败
    assert by_doi["10.14722/ndss.2024.24125"].abstract is None
    assert NDSS_OPENALEX_NO_HIT in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(NDSS_MAIN_PAPERS[2024])


def test_sync_year_falls_back_to_per_record_enrichment_when_the_batch_fails():
    """整批失败（429/5xx）时退回单条路径：不丢数据，语义与批量化前一致。"""
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        url = str(request.url)
        openalex_requests.append(url)
        if "filter=doi" in url:
            return httpx.Response(429, text="rate limited")  # 批量接口被限流
        if "23295" in url:
            return httpx.Response(200, json=_load(OPENALEX_2024_WITH_ABSTRACT))
        if "24125" in url:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(404, json={"error": "not found"})

    result = _source(handler).sync_year(2024)

    # 1 次批量 + 退回后的每条一次
    assert len(openalex_requests) == 1 + len(NDSS_MAIN_PAPERS[2024])
    by_doi = {record.doi: record for record in result.records}
    assert by_doi["10.14722/ndss.2024.23295"].abstract.startswith('Decoy passwords, or "honeywords,"')
    assert by_doi["10.14722/ndss.2024.24125"].abstract is None
    assert NDSS_OPENALEX_UNAVAILABLE in result.warnings
    assert NDSS_OPENALEX_NO_HIT in result.warnings
    assert result.error_code is None
    assert len(result.records) == len(NDSS_MAIN_PAPERS[2024])


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
        return httpx.Response(200, json=_load(OPENALEX_2024_WITH_ABSTRACT))

    source = _source(handler)
    first = source.sync_year(2024)
    second = source.sync_year(2024, previous_unit=first.unit)

    assert len(crossref_calls) == 2
    # 第一次走批量（5 条 -> 1 次请求），第二次命中缓存、0 次富化请求
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
        return httpx.Response(200, json=_load(OPENALEX_2025_WITH_ABSTRACT))

    result = _source(handler).sync_units({"years": [2023, 2024]})

    # 与 USENIX 范式一致：部分失败 → status=partial，来源级 error_code 保持空
    assert result.failed_years == (2024,)
    assert result.status == "partial"
    assert result.error_code is None
    assert {record.year for record in result.records} == {2023}
    assert NDSS_VENUE_FILTER_EMPTY not in result.warnings


def test_health_is_side_effect_free():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(500))

    health = source.health()

    assert calls == []
    assert health["source_id"] == NDSS_SOURCE_ID
    assert health["source_kind"] == NDSS_SOURCE_KIND
    assert health["authority_rank"] == NDSS_OFFICIAL_DOI_AUTHORITY
    assert sorted(health["allowed_hosts"]) == ["api.crossref.org", "api.openalex.org"]
    assert health["enabled"] is True
    assert health["error_code"] is None


def test_normalize_identity_reuses_existing_doi_then_title_rules():
    source = _source(lambda request: httpx.Response(200, json={}))
    record = parse_crossref_catalog(_crossref(2024), year=2024).records[0]

    assert source.normalize_identity(record) == "doi:10.14722/ndss.2024.23295"
    without_doi = dataclasses.replace(record, doi="")
    assert source.normalize_identity(without_doi) == "title:bernoullihoneywords|2024"
    assert source.normalize_identity(
        dataclasses.replace(record, doi="https://doi.org/10.14722/ndss.2024.23295")
    ) == "doi:10.14722/ndss.2024.23295"


def test_batch_safe_doi_rejects_anything_that_could_inject_a_filter():
    """DOI 会被拼进 OpenAlex 的 ``filter=doi:`` **查询语法**里。

    一个含 ``|`` / 空格 / 引号的 DOI 就能注入额外过滤条件、改变整个查询语义，
    因此只有严格 DOI 形态且不含分隔符的字符串允许进批量；其余必须返回 ``None``，
    由调用方退回单条请求（绝不静默丢弃）。
    """
    from backend.app.paper_discovery.infrastructure.openalex_batch_enricher import (
        batch_safe_doi,
    )

    assert batch_safe_doi("10.14722/ndss.2024.24017") == "10.14722/ndss.2024.24017"
    assert batch_safe_doi(" 10.14722/ndss.2024.24017 ") == "10.14722/ndss.2024.24017"

    for evil in (
        "10.14722/ndss.2024.24017|from_publication_date:2000-01-01",  # 注入额外过滤条件
        "10.14722/a b",                                               # 空白截断语法
        "10.14722/a&b",
        '10.14722/a"b',
        "10.14722/a<b>",
        "not-a-doi",
        "10.x/y",
        "",
        None,
        12345,
    ):
        assert batch_safe_doi(evil) is None, evil


def test_a_record_with_an_injectable_doi_still_gets_enriched_per_record():
    """不可批量化的 DOI 不能丢：必须退回单条路径，富化结果与改动前一致。"""
    openalex_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref(2024), headers={"ETag": '"v1"'})
        openalex_requests.append(str(request.url))
        if "23295" in str(request.url):
            return httpx.Response(200, json=_load(OPENALEX_2024_WITH_ABSTRACT))
        return httpx.Response(404, json={"error": "not found"})

    source = _source(handler)
    from backend.app.paper_discovery.infrastructure.ndss_paper_parser import NdssCatalogRecord

    def _rec(doi: str, title: str) -> NdssCatalogRecord:
        return NdssCatalogRecord(
            doi=doi, title=title, year=2024, authors=(), container_title="NDSS", article_url=None
        )

    odd = _rec("10.14722/ndss.2024.23295|x", "Odd DOI")
    good = _rec("10.14722/ndss.2024.24125", "Good DOI")

    items, warnings = source.enrich_records([odd, good])

    # 畸形 DOI 走单条、正常 DOI 走批量
    assert any("filter=doi" in url for url in openalex_requests)
    assert any("23295%7Cx" in url or "23295|x" in url for url in openalex_requests)
    assert items[0].abstract is not None  # 没有被静默丢弃
    assert NDSS_OPENALEX_NO_HIT in warnings
