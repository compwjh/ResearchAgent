import httpx

from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate
from backend.app.paper_discovery.infrastructure.openalex_enricher import OpenAlexEnricher


def candidate(title="A Secure Paper", year=2024, doi=None):
    return PaperCandidate("candidate-1", "search-1", title, "ccs", "CCS", year=year, doi=doi)


def test_doi_is_exact_first_and_merges_optional_metadata_without_rerank():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": [{
            "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/ABC",
            "title": "A Secure Paper", "publication_year": 2024,
            "abstract_inverted_index": {"secure": [1], "paper": [0]},
            "open_access": {"is_oa": True, "oa_url": "https://example.test/paper.pdf"},
            "best_oa_location": {"pdf_url": "https://example.test/best.pdf", "landing_page_url": "https://example.test/paper"},
        }]})

    result = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich([candidate(doi="10.1000/abc")])
    enriched = result.candidates[0]
    assert len(seen) == 1
    assert seen[0].headers["user-agent"] == OpenAlexEnricher.user_agent
    assert seen[0].url.params["filter"] == "doi:10.1000/abc"
    assert enriched.abstract == "paper secure"
    assert enriched.pdf_url == "https://example.test/best.pdf"
    assert enriched.pdf_access == "public"
    assert enriched.rerank_score is None
    assert result.warnings == ()


def test_doi_miss_uses_title_similarity_and_year_instead_of_first_broad_result():
    calls = []

    def handler(request):
        calls.append(request.url.params)
        if "filter" in request.url.params:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [
            {"id": "W-wrong", "title": "A Secure Paper for Medicine", "publication_year": 2024},
            {"id": "W-right", "title": "A Secure Paper", "publication_year": 2024,
             "open_access": {"is_oa": False}},
        ]})

    result = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich([candidate(doi="10.1000/missing")])
    assert len(calls) == 2
    assert result.candidates[0].article_url == "W-right"
    assert result.warning_codes == ("OPENALEX_NO_HIT",)


def test_title_fallback_rejects_year_mismatch_and_returns_structured_no_hit():
    def handler(request):
        return httpx.Response(200, json={"results": [{
            "id": "W-wrong-year", "title": "A Secure Paper", "publication_year": 2023,
        }]})

    result = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich([candidate()])
    assert result.candidates[0].article_url is None
    assert result.warnings[0].code == "OPENALEX_NO_HIT"
    assert result.warnings[0].stage == "title"


def test_timeout_does_not_block_or_mutate_dblp_candidate_and_does_not_title_retry():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    original = candidate(doi="10.1000/slow")
    result = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich([original])
    assert len(calls) == 1
    assert result.candidates == (original,)
    assert result.warning_codes == ("OPENALEX_TIMEOUT",)
    assert result.error_code == "OPENALEX_UNAVAILABLE"


def test_rate_limit_server_error_and_invalid_json_are_structured():
    responses = [httpx.Response(429), httpx.Response(503), httpx.Response(200, content=b"not-json")]
    for response, expected in zip(responses, ("OPENALEX_RATE_LIMITED", "OPENALEX_HTTP_ERROR", "OPENALEX_INVALID_RESPONSE"), strict=False):
        result = OpenAlexEnricher(transport=httpx.MockTransport(lambda request, response=response: response)).enrich([candidate()])
        assert result.warning_codes == (expected,)
        assert result.candidates[0].title == "A Secure Paper"


def test_invalid_json_payload_shape_has_specific_code():
    result = OpenAlexEnricher(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {}}))).enrich([candidate()])
    assert result.warning_codes == ("OPENALEX_INVALID_RESPONSE",)


def test_malformed_locations_are_ignored_and_reported():
    def handler(request):
        return httpx.Response(200, json={"results": [{"doi": "10.1000/a", "locations": {"bad": True}}]})

    result = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich([candidate(doi="doi:10.1000/A.")])
    assert result.candidates[0].pdf_url is None
    assert result.warning_codes == ("OPENALEX_INVALID_LOCATIONS",)


def test_helper_preserves_structured_warning_and_error_code():
    values = OpenAlexEnricher(transport=httpx.MockTransport(lambda request: httpx.Response(503))).enrich_by_doi("10.1000/a")
    assert values == {}
    assert values.warnings[0].code == "OPENALEX_HTTP_ERROR"
    assert values.error_code == "OPENALEX_UNAVAILABLE"


def test_single_candidate_helper_returns_mapping_for_search_orchestration():
    def handler(request):
        return httpx.Response(200, json={"results": [{"doi": "10.1000/a", "abstract_inverted_index": {"hello": [0]}}]})

    values = OpenAlexEnricher(transport=httpx.MockTransport(handler)).enrich_by_doi("10.1000/A")
    assert values == {"doi": "10.1000/A", "abstract": "hello", "article_url": None, "pdf_url": None, "pdf_access": "unknown"}
