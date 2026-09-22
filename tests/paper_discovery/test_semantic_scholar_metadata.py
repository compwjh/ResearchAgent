import httpx

from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import SemanticScholarRequestLimiter
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import SemanticScholarGraphClient


def _payload(title="Budget Recycling Differential Privacy"):
    return {
        "paperId": "s2-id",
        "title": title,
        "abstract": "A privacy abstract.",
        "authors": [{"name": "Ada Lovelace"}],
        "year": 2024,
        "externalIds": {"DOI": "10.1109/SP54263.2024.00212", "ArXiv": "2403.11445"},
        "venue": "IEEE Symposium on Security and Privacy",
        "fieldsOfStudy": ["Computer Science"],
        "citationCount": 7,
        "url": "https://www.semanticscholar.org/paper/s2-id",
    }


def _candidate(**overrides):
    value = {
        "catalog_paper_id": "catalog-1",
        "title": "Budget Recycling Differential Privacy",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "doi": "10.1109/SP54263.2024.00212",
    }
    value.update(overrides)
    return value


def test_batch_enriches_only_matching_catalog_metadata_and_uses_batch_contract():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[_payload()])

    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)), api_key="secret",
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    result = client.enrich([_candidate()])

    assert result[0].matched
    assert result[0].metadata.abstract == "A privacy abstract."
    assert result[0].metadata.citation_count == 7
    assert requests[0].method == "POST"
    assert requests[0].url.path.endswith("/paper/batch")
    assert requests[0].headers["x-api-key"] == "secret"
    assert requests[0].read().decode().startswith('{"ids"')


def test_batch_rejects_title_or_year_mismatch_without_returning_metadata():
    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[_payload(title="Unrelated")]))),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    result = client.enrich([_candidate(year=2023)])
    assert result[0].metadata is None
    assert result[0].code == "SEMANTIC_SCHOLAR_MATCH_UNCERTAIN"


def test_batch_accepts_semantic_scholar_paper_id_when_doi_is_missing():
    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[_payload()]))),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    candidate = _candidate(doi=None, arxiv_id=None, semantic_scholar_id="s2-id")
    assert client.enrich([candidate])[0].matched


def test_enrichment_reuses_batched_metadata_cache():
    calls = []

    def handler(_request):
        calls.append(True)
        return httpx.Response(200, json=[_payload()])

    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    assert client.enrich([_candidate()])[0].matched
    assert client.enrich([_candidate()])[0].matched
    assert len(calls) == 1


def test_metadata_clients_can_share_an_injected_rate_limiter():
    clock = {"value": 0.0}
    waits = []

    def now():
        return clock["value"]

    def sleep(seconds):
        waits.append(seconds)
        clock["value"] += seconds

    limiter = SemanticScholarRequestLimiter(now=now, sleep=sleep)
    response = httpx.Response(200, json=[_payload()])
    transport = httpx.MockTransport(lambda _request: response)
    first = SemanticScholarGraphClient(
        client=httpx.Client(transport=transport), rate_limiter=limiter,
    )
    second = SemanticScholarGraphClient(
        client=httpx.Client(transport=transport), rate_limiter=limiter,
    )
    assert first.enrich([_candidate()])[0].matched
    assert second.enrich([_candidate(catalog_paper_id="catalog-2")])[0].matched
    assert waits == [1.0]


def test_search_autocomplete_and_graph_edges_are_structured_and_bounded():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/paper/autocomplete"):
            return httpx.Response(200, json={"matches": [{"id": "s2-id", "title": "Budget Recycling"}]})
        if request.url.path.endswith("/citations"):
            return httpx.Response(200, json={"data": [{"citingPaper": _payload()}]})
        return httpx.Response(200, json={"data": [_payload()]})

    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    autocomplete = client.autocomplete("semanti")
    edges = client.graph_edges("s2-id", "citations", limit=5)
    assert autocomplete.payload["matches"][0]["id"] == "s2-id"
    assert edges.payload["data"][0]["citingPaper"]["paperId"] == "s2-id"
    assert edges.graph_page.relation == "citations"
    assert edges.graph_page.source_paper_id == "s2-id"
    assert edges.graph_page.items[0].paper_id == "s2-id"
    assert edges.graph_page.next_offset is None
    assert client.parse_search_results({"data": [_payload()]})[0].paper_id == "s2-id"
    assert seen[0].url.params["limit"] == "10"
    assert seen[1].url.params["limit"] == "5"
    assert seen[1].url.params["offset"] == "0"


def test_graph_edges_parse_references_page_and_preserve_next_offset():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "data": [{"citedPaper": _payload(title="Referenced Paper")}],
            "offset": 100,
            "next": 101,
            "total": 200,
        })

    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )
    result = client.graph_edges("s2-id", "references", limit=500, offset=100)

    assert result.code is None
    assert result.graph_page.relation == "references"
    assert result.graph_page.offset == 100
    assert result.graph_page.next_offset == 101
    assert result.graph_page.total == 200
    assert result.graph_page.items[0].title == "Referenced Paper"
    assert seen[0].url.params["limit"] == "100"
    assert seen[0].url.params["offset"] == "100"


def test_graph_edges_accepts_empty_reference_envelopes_and_null_cited_papers():
    payloads = [
        {"offset": 0, "next": 0, "total": 0},
        {"offset": 0, "next": 0, "total": 0, "data": None},
        {"offset": 0, "next": 0, "total": 1, "data": [{"citedPaper": None}]},
    ]

    for payload in payloads:
        client = SemanticScholarGraphClient(
            client=httpx.Client(transport=httpx.MockTransport(
                lambda _request, payload=payload: httpx.Response(200, json=payload)
            )),
            rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
        )
        result = client.graph_edges("s2-id", "references")

        assert result.code is None
        assert result.graph_page.items == ()
        assert result.graph_page.next_offset is None


def test_graph_edges_rejects_unverified_graph_shape_and_pagination_types():
    payloads = [
        {"offset": 0, "next": 0, "total": 1},
        {"offset": 0, "next": 0, "total": 0, "data": {}},
        {"offset": 0, "next": "later", "total": 0, "data": []},
        {"offset": "0", "next": 0, "total": 0, "data": []},
        {"offset": 0, "next": 0, "total": "0", "data": []},
    ]

    for payload in payloads:
        client = SemanticScholarGraphClient(
            client=httpx.Client(transport=httpx.MockTransport(
                lambda _request, payload=payload: httpx.Response(200, json=payload)
            )),
            rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
        )
        result = client.graph_edges("s2-id", "references")

        assert result.code == "SEMANTIC_SCHOLAR_INVALID_RESPONSE"
        assert result.graph_page is None


def test_graph_edges_treats_next_zero_as_terminal_page_sentinel():
    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={
            "offset": 0,
            "next": 0,
            "total": 3,
            "data": [{"citedPaper": _payload(title="Referenced Paper")}],
        }))),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    result = client.graph_edges("s2-id", "references")

    assert result.code is None
    assert result.graph_page.next_offset == 1


def test_graph_edges_rejects_path_like_paper_ids_before_network_call():
    calls = []
    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request))),
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    result = client.graph_edges("DOI:10.1000/example/with/path", "citations")

    assert result.code == "SEMANTIC_SCHOLAR_IDENTIFIER_INVALID"
    assert calls == []


def test_graph_errors_return_stable_code_without_provider_payload():
    for status_code, expected_code in ((429, "SEMANTIC_SCHOLAR_RATE_LIMITED"), (503, "SEMANTIC_SCHOLAR_UNAVAILABLE")):
        client = SemanticScholarGraphClient(
            client=httpx.Client(transport=httpx.MockTransport(
                lambda _request, status_code=status_code: httpx.Response(
                    status_code, text="secret=must-not-be-returned"
                )
            )),
            api_key="secret-key",
            retries=0,
            rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
        )
        result = client.graph_edges("s2-id", "citations")
        assert result.code == expected_code
        assert result.payload is None
        assert result.graph_page is None


def test_graph_rate_limit_retry_honors_retry_after():
    sleeps = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "4"}, text="secret=provider"),
        httpx.Response(200, json={"data": [{"citingPaper": _payload()}]}),
    ]
    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: responses.pop(0))),
        retries=1,
        backoff=1.0,
        sleep=sleeps.append,
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    result = client.graph_edges("s2-id", "citations")

    assert result.code is None
    assert result.graph_page.items[0].paper_id == "s2-id"
    assert sleeps == [4.0]


def test_graph_retry_after_is_not_reused_after_network_failure():
    sleeps = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "4"}, text="secret=provider"),
        httpx.ConnectError("network down"),
        httpx.Response(200, json={"data": [{"citingPaper": _payload()}]}),
    ]

    def handler(request):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise httpx.ConnectError(str(response), request=request)
        return response

    client = SemanticScholarGraphClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=2,
        backoff=1.0,
        sleep=sleeps.append,
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )

    result = client.graph_edges("s2-id", "citations")

    assert result.code is None
    assert result.graph_page.items[0].paper_id == "s2-id"
    assert sleeps == [4.0, 2.0]


def test_graph_edges_rejects_arbitrary_relation():
    client = SemanticScholarGraphClient(rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0))
    assert client.graph_edges("s2-id", "download").code == "SEMANTIC_SCHOLAR_RELATION_UNSUPPORTED"
