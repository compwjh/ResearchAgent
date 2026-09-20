"""Spec032 Task07: fixed official IEEE S&P catalogue sample.

The HTML fixture is a captured subset of the official 2024 programme page.  The
test never requests a PDF: discovery is metadata-only and the source rejects
PDF payloads on an official catalogue unit.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from backend.app.paper_discovery.infrastructure.ieee_sp_paper_parser import (
    IEEE_SP_OFFICIAL_ABSTRACT_MISSING,
    IEEE_SP_OFFICIAL_KEYWORDS_MISSING,
    IEEE_SP_OFFICIAL_SOURCE_ID,
    IeeeSpPaperParseError,
    parse_official_catalog,
)
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import (
    IEEE_SP_OFFICIAL_CATALOG_URLS,
    IEEE_SP_OFFICIAL_HOST,
    IEEE_SP_UNIT_REJECTED,
    IeeeSpPublicationSource,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ieee_sp" / "official-program-papers-2024.html"
OFFICIAL_URL = IEEE_SP_OFFICIAL_CATALOG_URLS[2024]


def _body() -> bytes:
    return FIXTURE.read_bytes()


def _source(handler) -> IeeeSpPublicationSource:
    return IeeeSpPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: ["93.184.216.34"],
        rate_limit_seconds=0.0,
        sleep=lambda _seconds: None,
    )


def test_official_fixture_parses_metadata_with_explicit_missing_fields():
    result = parse_official_catalog(_body(), year=2024, page_url=OFFICIAL_URL)

    assert [record.title for record in result.records] == [
        "FedRecover: Recovering from Poisoning Attacks in Federated Learning using Historical Information",
        "It’s (DOM) Clobbering Time: Attack Techniques, Prevalence, and Defenses",
        "Private, Efficient, and Accurate: Protecting Models Trained by Multi-party Learning with Differential Privacy",
    ]
    assert len(result.records) == 3
    first = result.records[0]
    assert first.doi == ""
    assert first.year == 2024
    assert first.article_url == OFFICIAL_URL
    assert first.container_title == "2024 IEEE Symposium on Security and Privacy (SP)"
    assert first.authors == (
        "Xiaoyu Cao",
        "Jinyuan Jia",
        "Zaixi Zhang",
        "Neil Zhenqiang Gong",
    )
    for field in ("title", "authors", "year", "container_title", "article_url"):
        assert first.provenance[field] == IEEE_SP_OFFICIAL_SOURCE_ID
    assert first.abstract is None
    assert first.keywords == ()
    assert first.pdf_url is None
    assert set(result.warnings) == {
        IEEE_SP_OFFICIAL_ABSTRACT_MISSING,
        IEEE_SP_OFFICIAL_KEYWORDS_MISSING,
    }


def test_official_route_fetches_html_and_records_content_hash_without_pdf_probe():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.host == IEEE_SP_OFFICIAL_HOST
        assert not request.url.path.endswith(".pdf")
        return httpx.Response(200, content=_body(), headers={"ETag": '"official-v1"'})

    source = _source(handler)
    result = source.sync_year(2024, route="official")

    assert calls == [OFFICIAL_URL]
    assert result.error_code is None
    assert result.records
    assert result.unit.unit_key == "sp:2024:official"
    assert result.unit.content_hash == hashlib.sha256(_body()).hexdigest()
    assert result.unit.etag == '"official-v1"'
    assert result.unit.paper_count == len(result.records)


def test_official_discovery_is_explicit_and_other_years_are_not_invented():
    source = _source(lambda request: httpx.Response(500))
    units = source.discover_units({"years": [2024], "route": "official"})
    assert len(units) == 1
    assert units[0].source_url == OFFICIAL_URL
    assert units[0].unit_key == "sp:2024:official"
    assert source.discover_units({"years": [2025], "route": "official"}) == ()
    unavailable = source.sync_units({"years": [2025], "route": "official"})
    assert unavailable.status == "failed"
    assert unavailable.error_code == IEEE_SP_UNIT_REJECTED


def test_official_unit_rejects_unallowlisted_host_and_pdf_content():
    source = _source(lambda request: httpx.Response(200, content=b"%PDF-1.7"))
    unit = source.discover_units({"years": [2024], "route": "official"})[0]
    rejected_url = unit.__class__(**{**unit.__dict__, "source_url": "https://evil.example/catalog.html"})
    rejected = source.fetch_unit(rejected_url)
    assert rejected.error_code == IEEE_SP_UNIT_REJECTED

    pdf = source.fetch_unit(unit)
    assert pdf.error_code == IEEE_SP_UNIT_REJECTED


def test_official_structure_change_is_a_stable_parse_failure():
    try:
        parse_official_catalog("<html><body><h1>changed</h1></body></html>", year=2024, page_url=OFFICIAL_URL)
    except IeeeSpPaperParseError as error:
        assert error.code == "IEEE_SP_OFFICIAL_INVALID_RESPONSE"
    else:
        raise AssertionError("empty official catalogue must not be reported as completed")
