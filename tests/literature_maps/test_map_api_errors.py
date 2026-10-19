from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_literature_maps
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
