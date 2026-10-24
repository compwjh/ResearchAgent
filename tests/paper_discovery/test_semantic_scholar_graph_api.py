from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import SemanticScholarRequestLimiter
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SEMANTIC_SCHOLAR_METADATA_FIELDS,
    SemanticScholarGraphClient,
    SemanticScholarGraphPage,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


class _GraphClient:
    api_key = "test-key"

    def __init__(self):
        self.autocomplete_calls = []
        self.graph_calls = []

    def autocomplete(self, query, *, limit):
        self.autocomplete_calls.append((query, limit))
        return SemanticScholarRequestResult(payload={
            "matches": [
                {"id": "s2-a", "title": "A short title", "secret": "must not escape"},
                {"id": "s2-a", "title": "Duplicate title"},
                {"id": "s2-b", "title": "B short title"},
                {"id": "missing-title"},
            ],
        })

    def graph_edges(self, paper_id, relation, *, limit, offset):
        self.graph_calls.append((paper_id, relation, limit, offset))
        metadata = SemanticScholarMetadata(
            paper_id="target-1",
            title="Target paper",
            authors=("Ada Lovelace",),
            year=2024,
            doi="10.1000/target",
            abstract="A safe abstract.",
        )
        return SemanticScholarRequestResult(graph_page=SemanticScholarGraphPage(
            relation=relation,
            source_paper_id=paper_id,
            items=(metadata,),
            offset=offset,
            next_offset=offset + limit,
            total=101,
        ))


def _client():
    return TestClient(app)


def test_autocomplete_returns_short_stable_candidates_and_bounded_limit():
    client = _GraphClient()
    with patch("backend.app.api.routes_paper._paper_discovery_enabled", return_value=True), patch(
        "backend.app.api.routes_paper._semantic_scholar_graph_client", return_value=client
    ):
        response = _client().get("/api/papers/semantic-scholar/autocomplete", params={"query": "privacy", "limit": 5})

    assert response.status_code == 200
    assert response.json() == {
        "query": "privacy",
        "candidates": [
            {"paper_id": "s2-a", "title": "A short title"},
            {"paper_id": "s2-b", "title": "B short title"},
        ],
    }
    assert client.autocomplete_calls == [("privacy", 5)]


def test_graph_page_projects_stable_fields_without_provider_payload():
    client = _GraphClient()
    with patch("backend.app.api.routes_paper._paper_discovery_enabled", return_value=True), patch(
        "backend.app.api.routes_paper._semantic_scholar_graph_client", return_value=client
    ):
        response = _client().get(
            "/api/papers/semantic-scholar/s2-source/citations",
            params={"limit": 10, "offset": 20},
        )

    assert response.status_code == 200
    assert response.json() == {
        "relation": "citations",
        "source_paper_id": "s2-source",
        "items": [{
            "paper_id": "target-1",
            "title": "Target paper",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "doi": "10.1000/target",
            "arxiv_id": None,
            "abstract": "A safe abstract.",
            "venue": None,
            "fields_of_study": [],
            "citation_count": None,
            "source_url": None,
        }],
        "offset": 20,
        "next_offset": 30,
        "total": 101,
    }
    assert client.graph_calls == [("s2-source", "citations", 10, 20)]


def test_graph_api_rejects_relation_identifier_and_pagination_before_client_call():
    client = _GraphClient()
    with patch("backend.app.api.routes_paper._paper_discovery_enabled", return_value=True), patch(
        "backend.app.api.routes_paper._semantic_scholar_graph_client", return_value=client
    ):
        invalid_relation = _client().get("/api/papers/semantic-scholar/s2-source/download")
        invalid_id = _client().get("/api/papers/semantic-scholar/DOI:10.1000%23foo/citations")
        invalid_offset = _client().get(
            "/api/papers/semantic-scholar/s2-source/references", params={"offset": -1}
        )

    assert invalid_relation.status_code == 400
    assert invalid_relation.json()["code"] == "SEMANTIC_SCHOLAR_RELATION_UNSUPPORTED"
    assert invalid_id.status_code == 400
    assert invalid_id.json()["code"] == "SEMANTIC_SCHOLAR_IDENTIFIER_INVALID"
    assert invalid_offset.status_code == 400
    assert invalid_offset.json()["code"] == "SEMANTIC_SCHOLAR_PAGINATION_INVALID"
    assert client.graph_calls == []


def test_graph_api_redacts_provider_failures_and_missing_key():
    failed = SimpleNamespace(
        api_key="test-key",
        graph_edges=lambda *args, **kwargs: SemanticScholarRequestResult(
            code="SEMANTIC_SCHOLAR_UNAVAILABLE", retryable=True, payload="secret provider body"
        ),
    )
    with patch("backend.app.api.routes_paper._paper_discovery_enabled", return_value=True), patch(
        "backend.app.api.routes_paper._semantic_scholar_graph_client", return_value=failed
    ):
        response = _client().get("/api/papers/semantic-scholar/s2-source/references")

    assert response.status_code == 503
    assert response.json()["code"] == "SEMANTIC_SCHOLAR_UNAVAILABLE"
    assert "secret" not in response.text

    missing_key = SimpleNamespace(api_key="")
    with patch("backend.app.api.routes_paper._paper_discovery_enabled", return_value=True), patch(
        "backend.app.api.routes_paper._semantic_scholar_graph_client", return_value=missing_key
    ):
        response = _client().get(
            "/api/papers/semantic-scholar/autocomplete", params={"query": "privacy"}
        )
    assert response.status_code == 503
    assert response.json()["code"] == "SEMANTIC_SCHOLAR_AUTH_REQUIRED"


def _metadata_payload(*paper_ids):
    return {
        "total": len(paper_ids),
        "offset": 0,
        "next": None,
        "data": [{"paperId": paper_id, "title": f"Title {paper_id}"} for paper_id in paper_ids],
    }


def _http_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _graph_client(http_client):
    return SemanticScholarGraphClient(
        client=http_client,
        retries=0,
        rate_limiter=SemanticScholarRequestLimiter(interval_seconds=0),
    )


def test_relevance_search_uses_relevance_endpoint_and_keeps_provider_order():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_metadata_payload("provider-first", "provider-second"))

    with _http_client(handler) as http_client:
        result = _graph_client(http_client).search_relevance(
            "graph attention networks", limit=20, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS
        )

    assert result.code is None
    assert [item.paper_id for item in SemanticScholarGraphClient.parse_search_results(result.payload)] == [
        "provider-first",
        "provider-second",
    ]
    assert len(seen) == 1
    assert seen[0].url.path == "/graph/v1/paper/search"
    assert seen[0].url.params["query"] == "graph attention networks"
    assert seen[0].url.params["limit"] == "20"
    assert seen[0].url.params["fields"] == SEMANTIC_SCHOLAR_METADATA_FIELDS


def test_bulk_search_keeps_legacy_endpoint_and_bounded_parameters():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_metadata_payload("bulk-paper"))

    with _http_client(handler) as http_client:
        result = _graph_client(http_client).search_bulk(
            "graph attention networks", limit=50, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS
        )

    assert result.code is None
    assert len(seen) == 1
    assert seen[0].url.path == "/graph/v1/paper/search/bulk"
    assert seen[0].url.params["limit"] == "50"


def test_relevance_search_preserves_provider_error_mapping():
    def handler(request):
        return httpx.Response(429, json={"message": "rate limited"})

    with _http_client(handler) as http_client:
        result = _graph_client(http_client).search_relevance("graph attention networks")

    assert result.code == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert result.retryable is True


def test_relevance_search_preserves_server_error_mapping():
    def handler(request):
        return httpx.Response(503, json={"message": "temporarily unavailable"})

    with _http_client(handler) as http_client:
        result = _graph_client(http_client).search_relevance("graph attention networks")

    assert result.code == "SEMANTIC_SCHOLAR_UNAVAILABLE"
    assert result.retryable is True
