"""Spec032 Task07: fixed official NDSS 2024 catalogue sample.

The fixture is a controlled, bounded subset derived from real entries on the official accepted-papers page.
Official discovery is metadata-only and never probes a PDF URL.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import httpx

from backend.app.paper_discovery.infrastructure.ndss_paper_parser import (
    NDSS_OFFICIAL_ABSTRACT_MISSING,
    NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS,
    NDSS_OFFICIAL_HOST,
    NDSS_OFFICIAL_INVALID_RESPONSE,
    NDSS_OFFICIAL_KEYWORDS_MISSING,
    NDSS_OFFICIAL_SOURCE_ID,
    NdssPaperParseError,
    parse_official_catalog,
)
from backend.app.paper_discovery.infrastructure.ndss_publication_source import (
    NDSS_UNIT_REJECTED,
    NdssPublicationSource,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ndss" / "official-accepted-papers-2024.html"
OFFICIAL_URL = NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS[2024]


def _body() -> bytes:
    return FIXTURE.read_bytes()


def _source(handler) -> NdssPublicationSource:
    return NdssPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: ["93.184.216.34"],
        rate_limit_seconds=0.0,
        sleep=lambda _seconds: None,
    )


def test_official_fixture_parses_metadata_with_explicit_missing_fields():
    result = parse_official_catalog(_body(), year=2024, page_url=OFFICIAL_URL)

    assert [record.title for record in result.records] == [
        "50 Shades of Support: A Device-Centric Analysis of Android Security Updates",
        "5G-Spector: An O-RAN Compliant Layer-3 Cellular Attack Detection Service",
        "A Duty to Forget, a Right to be Assured? Exposing Vulnerabilities in Machine Unlearning Services",
    ]
    assert len(result.records) == 3
    first = result.records[0]
    assert first.doi == ""
    assert first.year == 2024
    assert first.article_url == OFFICIAL_URL
    assert first.container_title == "2024 Network and Distributed System Security Symposium"
    assert first.authors == (
        "Abbas Acar", "Güliz Seray Tuncay", "Esteban Luques", "Harun Oz", "Ahmet Aris", "Selcuk Uluagac",
    )
    for field in ("title", "authors", "year", "container_title", "article_url"):
        assert first.provenance[field] == NDSS_OFFICIAL_SOURCE_ID
    assert first.abstract is None
    assert first.keywords == ()
    assert first.pdf_url is None
    assert set(result.warnings) == {NDSS_OFFICIAL_ABSTRACT_MISSING, NDSS_OFFICIAL_KEYWORDS_MISSING}


def test_official_route_fetches_html_and_records_content_hash_without_pdf_probe():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.host == NDSS_OFFICIAL_HOST
        assert not request.url.path.endswith(".pdf")
        return httpx.Response(200, content=_body(), headers={"ETag": '"official-v1"'})

    source = _source(handler)
    result = source.sync_year(2024, route="official")

    assert calls == [OFFICIAL_URL]
    assert result.error_code is None
    assert result.records
    assert result.unit.unit_key == "ndss:2024:official"
    assert result.unit.content_hash == hashlib.sha256(_body()).hexdigest()
    assert result.unit.etag == '"official-v1"'
    assert result.unit.paper_count == len(result.records)


def test_official_discovery_is_explicit_and_other_years_are_not_invented():
    source = _source(lambda request: httpx.Response(500))
    units = source.discover_units({"years": [2024], "route": "official"})
    assert len(units) == 1
    assert units[0].source_url == OFFICIAL_URL
    assert units[0].unit_key == "ndss:2024:official"
    assert source.discover_units({"years": [2025], "route": "official"}) == ()
    unavailable = source.sync_units({"years": [2025], "route": "official"})
    assert unavailable.status == "failed"
    assert unavailable.error_code == NDSS_UNIT_REJECTED


def test_official_unit_rejects_unallowlisted_host_and_pdf_content():
    calls: list[str] = []
    source = _source(lambda request: calls.append(str(request.url)) or httpx.Response(200, content=b"%PDF-1.7"))
    unit = source.discover_units({"years": [2024], "route": "official"})[0]
    rejected_url = dataclasses.replace(unit, source_url="https://evil.example/catalog.html")
    rejected = source.fetch_unit(rejected_url)
    assert rejected.error_code == NDSS_UNIT_REJECTED
    assert source.fetch_unit(unit).error_code == NDSS_UNIT_REJECTED
    assert calls == [OFFICIAL_URL]


def test_official_structure_change_is_a_stable_parse_failure():
    try:
        parse_official_catalog("<html><body><h1>changed</h1></body></html>", year=2024, page_url=OFFICIAL_URL)
    except NdssPaperParseError as error:
        assert error.code == NDSS_OFFICIAL_INVALID_RESPONSE
    else:
        raise AssertionError("empty official catalogue must not be reported as completed")
