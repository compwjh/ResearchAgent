from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
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
