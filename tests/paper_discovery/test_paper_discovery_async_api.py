from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchServiceError
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


def test_server_snapshot_resolves_catalog_search():
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        paper_id = "cat-1"
        store.create_search_job(SearchJob(
            "async-1", "agent", ["usenix-security"], [2024],
            status="running", expires_at="2099-01-01T00:00:00Z",
        ))
        store.upsert_catalog_paper(CatalogPaper(
            paper_id, "usenix-security", 2024, "Paper", "paper",
            abstract="", metadata_hash="hash-1",
        ))
        store.save_search_result(SearchResult(
            "async-1", paper_id, 1, snapshot={
                "catalog_paper_id": paper_id,
                "title": "Paper",
                "year": 2024,
                "source_page_url": "https://www.usenix.org/conference/usenixsecurity24/presentation/x",
            },
        ))
        store.freeze_search_results("async-1", [], status="completed")
        with patch.object(routes_paper, "_paper_store", return_value=store):
            session, candidates = routes_paper._paper_server_snapshot("async-1", [paper_id])
        assert session.status == "completed"
        assert len(candidates) == 1
        assert candidates[0]["candidate_id"] == paper_id
        assert candidates[0]["search_id"] == "async-1"


def test_server_snapshot_catalog_search_not_found():
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        with patch.object(routes_paper, "_paper_store", return_value=store), pytest.raises(PaperImportBatchServiceError) as error:
            routes_paper._paper_server_snapshot("missing", ["cat-1"])
        assert error.value.code == "SEARCH_NOT_FOUND"


def test_async_search_invalid_years_carries_supported_range():
    client = TestClient(app)
    response = client.post("/api/papers/searches", json={
        "query": "agent security", "conference_ids": ["usenix-security"], "years": [2023, 2022],
    })
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_YEARS"
    # 仅在 INVALID_YEARS 分支下发合法范围，供前端渲染"仅支持 XXXX-XXXX"
    assert body["details"] == {"min_year": 1900, "max_year": datetime.now(timezone.utc).year}


def test_async_search_out_of_range_year_reports_invalid_years():
    client = TestClient(app)
    response = client.post("/api/papers/searches", json={
        "query": "agent security", "conference_ids": ["usenix-security"], "years": [1899],
    })
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_YEARS"
    assert response.json()["details"]["min_year"] == 1900


def test_async_search_ascending_multi_year_is_accepted():
    # 升序多年（如 2021-2025）不再误报"年份范围无效"，可正常发起检索。
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
            routes_paper, "submit_paper_catalog_search"
        ) as submit:
            client = TestClient(app)
            response = client.post("/api/papers/searches", json={
                "query": "agent security", "conference_ids": ["usenix-security"],
                "years": [2021, 2022, 2023, 2024, 2025],
            })
            assert response.status_code == 202
            assert response.json()["status"] == "queued"
            submit.assert_called_once()


def test_async_search_other_errors_do_not_leak_details():
    # 除 INVALID_YEARS 外，结构化 details 不应出现在其它错误响应中（向后兼容）。
    client = TestClient(app)
    response = client.post("/api/papers/searches", json={
        "query": "agent security", "conference_ids": ["unknown-conf"], "years": [2024],
    })
    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_CONFERENCE"
    assert "details" not in response.json()


def test_async_search_endpoint_remains_legacy_usenix_scope():
    """Spec032 Research searches use SearchWorker/CatalogSearchAdapter instead.

    The direct async endpoint is the pre-Spec032 USENIX snapshot contract; a
    non-USENIX source must not silently enter that graph and create a second
    multi-source search path.
    """
    with NamedTemporaryFile(suffix=".sqlite3") as database:
        store = PaperDiscoveryStore(database.name)
        with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
            routes_paper, "submit_paper_catalog_search"
        ) as submit:
            client = TestClient(app)
            response = client.post("/api/papers/searches", json={
                "query": "agent security", "conference_ids": ["ieee-sp"], "years": [2024],
            })

        assert response.status_code == 400
        assert response.json()["code"] == "UNSUPPORTED_CONFERENCE"
        submit.assert_not_called()
        assert store.list_search_ids() == []
