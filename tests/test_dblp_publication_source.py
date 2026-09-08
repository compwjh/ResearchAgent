import httpx

from backend.app.paper_discovery.domain.paper_discovery import ConferenceSource
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.paper_discovery.infrastructure.dblp_publication_source import (
    DBLPPublicationSource,
    deduplicate_publications,
    filter_main_conference_records,
)

SOURCE = ConferenceSource("uss", "USENIX Security", "USENIX Security", "conf/uss", ["USENIX Security Symposium"])


def _item(title="Main", doi="10/a", key="conf/uss/main", venue="USENIX Security Symposium", kind="Conference and Workshop Papers"):
    return {"info": {"title": title, "doi": doi, "key": key, "venue": venue, "type": kind, "year": "2024"}}


def test_filter_rejects_mixed_stream_records_and_deduplicates_identities():
    kept = filter_main_conference_records([_item(), _item("SOUPS", "10/b", "conf/uss/soups", "SOUPS @ USENIX Security Symposium"), _item("Poster", "10/c")], SOURCE, 2024)
    assert [item["title"] for item in kept] == ["Main"]
    assert deduplicate_publications(kept + [{**kept[0], "doi": "https://doi.org/10/a", "key": "conf/uss/new"}]) == kept


def test_adapter_retries_and_returns_structured_failure_with_explicit_user_agent():
    seen, calls = [], [0]
    def handler(request):
        seen.append(request); calls[0] += 1
        return httpx.Response(429 if calls[0] == 1 else 200, json={"result": {"hits": {"hit": [_item()]}}})
    result = DBLPPublicationSource(retries=1, backoff=0, transport=httpx.MockTransport(handler), sleep=lambda _: None).search(SOURCE, "secure search", [2024])
    assert [row["title"] for row in result.records] == ["Main"]
    assert seen[0].headers["user-agent"] == DBLPPublicationSource.user_agent
    assert DBLPPublicationSource(retries=0, transport=httpx.MockTransport(lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))).search(SOURCE, "secure search", [2024]).error_code == "DBLP_UNAVAILABLE"


def test_multi_year_search_exposes_warning_years_without_promoting_partial_to_error():
    def handler(request):
        if "year:2023" in request.url.params["q"]:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"result": {"hits": {"hit": [_item()]}}})

    result = DBLPPublicationSource(
        retries=0, transport=httpx.MockTransport(handler)
    ).search(SOURCE, "secure search", [2023, 2024])

    assert len(result.records) == 1
    assert result.warnings == ("DBLP_TIMEOUT",)
    assert result.error_code is None
    assert result.failed_years == (2023,)


def test_search_encodes_query_while_retaining_server_controlled_filters():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"result": {"hits": {"hit": [_item()]}}})

    query = "llm agent/security? stream:conf/evil https://evil.test/?q=1"
    result = DBLPPublicationSource(transport=httpx.MockTransport(handler)).search(SOURCE, query, [2024])

    assert [row["title"] for row in result.records] == ["Main"]
    assert seen[0].url.host == "dblp.org"
    assert seen[0].url.params["q"] == f"{query} stream:{SOURCE.dblp_stream} year:2024"
    assert seen[0].url.params["q"].endswith("stream:conf/uss year:2024")


def test_query_cannot_bypass_stream_filter():
    seen = []

    def handler(request):
        seen.append(request)
        evil = _item("Evil", "10/evil", "conf/evil/main")
        return httpx.Response(200, json={"result": {"hits": {"hit": [_item(), evil]}}})

    result = DBLPPublicationSource(transport=httpx.MockTransport(handler)).search(SOURCE, "stream:conf/evil", [2024])

    assert [row["title"] for row in result.records] == ["Main"]
    assert seen[0].url.params["q"].endswith("stream:conf/uss year:2024")


def test_malformed_dblp_envelope_is_structured_invalid_response():
    for payload in ({}, {"result": {}}, {"result": {"hits": {}}}, {"result": {"hits": {"hit": {}}}}):
        result = DBLPPublicationSource(
            retries=0,
            transport=httpx.MockTransport(lambda _request, payload=payload: httpx.Response(200, json=payload)),
        ).search(SOURCE, "secure search", [2024])
        assert result.records == ()
        assert result.warnings == ("DBLP_INVALID_RESPONSE",)
        assert result.error_code == "DBLP_INVALID_RESPONSE"


def test_identity_normalization_keeps_cross_year_titles_and_normalizes_doi_variants():
    assert normalize_doi("HTTP://doi.org/10.1/ABC.") == "10.1/abc"
    assert normalize_doi("doi: 10.1/ABC.") == "10.1/abc"
    assert normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert normalize_title("Résumé: Same-Title") == "resumesametitle"
    first = _item("Same Title", "", "conf/uss/one")
    second = {**_item("Same-title", "", "conf/uss/two"), "info": {**_item("Same-title", "", "conf/uss/two")["info"], "year": "2023"}}
    assert len(deduplicate_publications([first, second], "uss")) == 2


def test_dblp_key_deduplication_is_scoped_to_year_and_conference():
    same_year_other_conference = {**_item(doi=""), "info": {**_item(doi="")["info"], "conference_id": "ccs", "venue": "ACM CCS"}}
    next_year = {**_item(doi=""), "info": {**_item(doi="")["info"], "year": "2023"}}
    assert len(deduplicate_publications([_item(doi=""), same_year_other_conference])) == 2
    assert len(deduplicate_publications([_item(doi=""), next_year], "uss")) == 2
