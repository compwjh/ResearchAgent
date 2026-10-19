from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_literature_maps
from backend.app.literature_maps.application.import_bridge import LiteratureMapImportBridge
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app


class BrokenStore:
    def list_maps(self, owner_id: str, *, limit: int):
        raise RuntimeError("sqlite file=/secret/db.sqlite")


def test_list_maps_storage_failure_is_fixed_503_without_exception_text() -> None:
    service = SimpleNamespace(store=BrokenStore())
    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=service), pytest.raises(
        routes_literature_maps.HTTPException
    ) as raised:
        routes_literature_maps.list_literature_maps()

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "MAP_STORAGE_UNAVAILABLE",
        "message": "文献地图暂时不可用，请稍后重试",
        "retryable": True,
    }


def test_import_route_accepts_empty_body_and_never_passes_client_url_override() -> None:
    calls: list[tuple] = []

    class Service:
        def import_node(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"status": "queued", "document_id": None}

    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=Service()):
        response = routes_literature_maps.import_literature_map_node("map-1", "node-1")

    assert response["status"] == "queued"
    assert calls == [(('map-1', 'node-1', routes_literature_maps.OWNER_ID), {})]
    assert "source_url" not in routes_literature_maps.ImportRequest.model_fields


def test_import_route_exposes_only_allowlisted_resolver_diagnostics() -> None:
    class Service:
        def import_node(self, *args, **kwargs):
            return {
                "status": "failed",
                "download_status": "failed",
                "error_code": "PDF_NOT_FOUND",
                "resolver_code": "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
                "resolver_codes": ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"],
            }

    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=Service()):
        result = routes_literature_maps.import_literature_map_node("map-1", "node-1")

    assert result["error_code"] == "PDF_NOT_FOUND"
    assert result["resolver_code"] == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"
    assert result["resolver_codes"] == ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"]


def test_http_import_exposes_allowlisted_resolver_diagnostics() -> None:
    class Service:
        def import_node(self, *args, **kwargs):
            return {
                "status": "failed",
                "download_status": "failed",
                "error_code": "PDF_NOT_FOUND",
                "resolver_code": "ARXIV_IDENTITY_CONFLICT",
                "resolver_codes": ["ARXIV_IDENTITY_CONFLICT"],
            }

    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=Service()):
        response = TestClient(app).post(
            "/api/literature-maps/map-1/nodes/node-1/imports",
            json={},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["error_code"] == "PDF_NOT_FOUND"
    assert body["resolver_code"] == "ARXIV_IDENTITY_CONFLICT"
    assert body["resolver_codes"] == ["ARXIV_IDENTITY_CONFLICT"]


def test_http_import_round_trip_persists_diagnostics_in_sqlite_provenance(tmp_path) -> None:
    database_path = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(database_path)
    created = store.create_map(routes_literature_maps.OWNER_ID, topic="fuzzing")
    node = MapPaper.new(
        created.map_id,
        semantic_scholar_id="s2-a",
        title="A paper",
        source_url="https://www.semanticscholar.org/paper/s2-a",
        provenance={"provider": "semantic_scholar", "keep": "yes"},
    )
    store.add_nodes(created.map_id, routes_literature_maps.OWNER_ID, [node])
    outcome = {"status": "failed", "error_code": "PDF_NOT_FOUND"}
    source = {
        "pdf_url": "https://arxiv.org/pdf/1809.07041",
        "resolver_code": "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
        "resolver_codes": ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"],
        "provider_exception": "https://secret.example/key=bad",
    }
    bridge = LiteratureMapImportBridge(
        importer=lambda _snapshot, _url: outcome,
        store=store,
        owner_id=routes_literature_maps.OWNER_ID,
        source_resolver=lambda _node: source,
    )

    class Service:
        def import_node(self, map_id, node_id, owner_id):
            current = store.get_node(map_id, node_id, owner_id)
            assert current is not None
            return bridge.import_node(current, current.source_url)

        def node(self, map_id, node_id, owner_id):
            current = store.get_node(map_id, node_id, owner_id)
            assert current is not None
            return current

    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=Service()):
        posted = TestClient(app).post(f"/api/literature-maps/{created.map_id}/nodes/{node.node_id}/imports", json={})
        assert posted.status_code == 202
        assert posted.json()["resolver_code"] == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"
        fetched = TestClient(app).get(f"/api/literature-maps/{created.map_id}/nodes/{node.node_id}")

    assert fetched.status_code == 200
    fetched_node = fetched.json()["node"]
    assert fetched_node["provenance"]["import_diagnostics"]["error_code"] == "PDF_NOT_FOUND"
    assert fetched_node["provenance"]["provider"] == "semantic_scholar"
    assert fetched_node["provenance"]["keep"] == "yes"
    assert "secret.example" not in str(fetched_node)

    reopened = LiteratureMapStore(database_path)
    persisted = reopened.get_node(created.map_id, node.node_id, routes_literature_maps.OWNER_ID)
    assert persisted is not None
    assert persisted.provenance["import_diagnostics"]["resolver_codes"] == [
        "ARXIV_UNAVAILABLE",
        "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
    ]

    outcome.clear()
    outcome.update({"status": "indexed", "paper_id": "doc-1"})
    source.clear()
    source.update({"pdf_url": "https://arxiv.org/pdf/1809.07041"})
    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=Service()):
        retried = TestClient(app).post(f"/api/literature-maps/{created.map_id}/nodes/{node.node_id}/imports", json={})
        assert retried.status_code == 202
        fetched_after_retry = TestClient(app).get(f"/api/literature-maps/{created.map_id}/nodes/{node.node_id}")

    assert retried.json()["status"] == "indexed"
    assert "import_diagnostics" not in fetched_after_retry.json()["node"]["provenance"]
    reopened_again = LiteratureMapStore(database_path)
    persisted_after_retry = reopened_again.get_node(created.map_id, node.node_id, routes_literature_maps.OWNER_ID)
    assert persisted_after_retry is not None
    assert "import_diagnostics" not in persisted_after_retry.provenance


def test_http_storage_failure_has_no_raw_exception_text() -> None:
    service = SimpleNamespace(store=BrokenStore())
    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=service):
        response = TestClient(app).get("/api/literature-maps")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "MAP_STORAGE_UNAVAILABLE",
        "message": "文献地图暂时不可用，请稍后重试",
        "retryable": True,
    }
    assert "secret" not in response.text


def test_http_import_rejects_client_source_url_override() -> None:
    response = TestClient(app).post(
        "/api/literature-maps/map-1/nodes/node-1/imports",
        json={"source_url": "https://attacker.example.test/public.pdf"},
    )

    assert response.status_code == 422
    assert "source_url" in response.text


@pytest.mark.parametrize("field", ["source_ids", "conference_ids"])
def test_http_unknown_scope_from_real_service_is_fixed_400_without_raw_input(field: str) -> None:
    payload = {"topic": "topic", field: ["secret-unknown-scope"]}
    response = TestClient(app).post("/api/literature-maps", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_MAP_SCOPE",
        "message": "地图来源或会议范围不受支持，请选择服务端支持的范围",
        "retryable": False,
    }
    assert "secret-unknown-scope" not in response.text
