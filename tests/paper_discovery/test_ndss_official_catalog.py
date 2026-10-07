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
FIXTURE_2025 = Path(__file__).parents[1] / "fixtures" / "ndss" / "official-accepted-papers-2025.html"
OFFICIAL_URL = NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS[2024]
OFFICIAL_URL_2025 = NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS[2025]


def _body() -> bytes:
    return FIXTURE.read_bytes()


def _body_2025() -> bytes:
    return FIXTURE_2025.read_bytes()


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


def test_official_2025_fixture_reuses_listing_parser_without_inventing_fields():
    result = parse_official_catalog(_body_2025(), year=2025, page_url=OFFICIAL_URL_2025)

    assert [record.title for record in result.records] == [
        "”Who is Trying to Access My Account?” Exploring User Perceptions and Reactions to Risk-based Authentication Notifications",
        "“Where Are We On Cyber?” – A Qualitative Study On Boards’ Cybersecurity Risk Decision Making",
        "A Comprehensive Memory Safety Analysis of Bootloaders",
    ]
    assert [record.year for record in result.records] == [2025, 2025, 2025]
    assert result.records[0].authors == (
        "Tongxin Wei", "Ding Wang", "Yutong Li", "Yuehuan Wang",
    )
    assert result.records[0].article_url == (
        "https://www.ndss-symposium.org/ndss-paper/"
        "who-is-trying-to-access-my-account-exploring-user-perceptions-and-reactions-to-risk-based-authentication-notifications/"
    )
    assert all(record.doi == "" for record in result.records)
    assert all(record.abstract is None and record.keywords == () for record in result.records)
    assert all(record.pdf_url is None for record in result.records)
    assert hashlib.sha256(_body_2025()).hexdigest() == (
        "75d77e4c5c4aff058e51d738a94e553f28960b5afa148e586584a03317e244d3"
    )
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


def test_official_2025_route_fetches_html_without_pdf_probe():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.host == NDSS_OFFICIAL_HOST
        assert not request.url.path.endswith(".pdf")
        return httpx.Response(200, content=_body_2025(), headers={"ETag": '"official-2025-v1"'})

    source = _source(handler)
    result = source.sync_year(2025, route="official")

    assert calls == [OFFICIAL_URL_2025]
    assert result.error_code is None
    assert [record.year for record in result.records] == [2025, 2025, 2025]
    assert result.unit.unit_key == "ndss:2025:official"
    assert result.unit.content_hash == hashlib.sha256(_body_2025()).hexdigest()
    assert result.unit.etag == '"official-2025-v1"'
    assert result.unit.paper_count == len(result.records)


def test_official_discovery_exposes_only_evidence_backed_years():
    source = _source(lambda request: httpx.Response(500))
    units = source.discover_units({"years": [2024, 2025], "route": "official"})
    assert [unit.source_url for unit in units] == [OFFICIAL_URL, OFFICIAL_URL_2025]
    assert [unit.unit_key for unit in units] == ["ndss:2024:official", "ndss:2025:official"]
    assert source.discover_units({"years": [2023], "route": "official"}) == ()
    unavailable = source.sync_units({"years": [2023], "route": "official"})
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
