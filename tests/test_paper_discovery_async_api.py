from tempfile import NamedTemporaryFile
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api import routes, routes_paper  # noqa: F401 - initialize facade before submodule
from backend.app.main import app
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper, SearchJob, SearchResult
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


def test_async_search_contract_is_202_and_rejects_client_urls():
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
            routes_paper, "submit_paper_catalog_search"
        ) as submit:
            client = TestClient(app)
            response = client.post("/api/papers/searches", json={
                "query": "agent security", "conference_ids": ["usenix-security"], "years": [2024],
                "source_url": "https://evil.example/list",
            })
            assert response.status_code == 422
            assert response.json()["code"] == "INVALID_SEARCH_REQUEST"
            response = client.post("/api/papers/searches", json={
                "query": "agent security", "conference_ids": ["usenix-security"], "years": [2024],
            })
            assert response.status_code == 202
            assert response.json()["status"] == "queued"
            assert response.json()["source_progress"][0]["message_code"] == "SOURCE_QUEUED"
            submit.assert_called_once_with(response.json()["search_id"])


def test_async_results_are_fixed_ten_item_pages():
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        job = SearchJob("async-1", "agent", ["usenix-security"], [2024],
                        status="running", expires_at="2099-01-01T00:00:00Z", created_at="2024-01-01T00:00:00Z")
        store.create_search_job(job)
        for rank in range(1, 22):
            paper_id = f"paper-{rank}"
            store.upsert_catalog_paper(CatalogPaper(
                paper_id, "usenix-security", 2024, f"Paper {rank}", f"paper {rank}",
                abstract="Official abstract", metadata_hash=f"hash-{rank}",
            ))
            store.save_search_result(SearchResult(
                "async-1", paper_id, rank, final_score=float(rank),
                snapshot={"catalog_paper_id": paper_id, "rank": rank, "title": f"Paper {rank}"},
            ))
        store.freeze_search_results("async-1", [], status="completed")
        with patch.object(routes_paper, "_paper_store", return_value=store):
            client = TestClient(app)
            first = client.get("/api/papers/searches/async-1/results?page=1")
            third = client.get("/api/papers/searches/async-1/results?page=3")
        assert first.status_code == 200
        assert first.json()["page_size"] == 10
        assert first.json()["total_pages"] == 3
        assert first.json()["has_next"] is True
        assert len(first.json()["items"]) == 10
        assert len(third.json()["items"]) == 1
