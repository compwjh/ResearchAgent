from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import get_literature_map_service, reset_literature_map_runtime
from backend.app.literature_maps.domain.models import MapEdge, MapPaper
from backend.app.main import app


def test_json_export_is_whitelisted_owner_scoped_and_directional(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        created = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20}).json()
        map_id = created["map_id"]
        service = get_literature_map_service()
        first = MapPaper.new(
            map_id,
            semantic_scholar_id="s2-a",
            title="A paper",
            authors=("A",),
            year=2024,
            venue="Venue",
            abstract="Abstract",
            keywords=("fuzzing",),
            citation_count=3,
            source_url="https://example.org/paper",
            provenance={
                "provider": "semantic_scholar",
                "source": "usenix",
                "official_page_url": "https://example.org/page",
                "catalog_snapshot": {"catalog_paper_id": "catalog-a", "authorization": "secret"},
                "prompt": "do not export",
                "internal_path": "/private/data",
            },
            position={"x": 1, "y": 2},
        )
        second = MapPaper.new(
            map_id,
            semantic_scholar_id="s2-b",
            title="B paper",
            provenance={"provider": "semantic_scholar"},
            position={"x": 3, "y": 4},
        )
        service.store.add_nodes(map_id, "local-user", [first, second])
        service.store.add_edges(
            map_id,
            "local-user",
            [
                MapEdge.new(
                    map_id,
                    "citation",
                    first.node_id,
                    second.node_id,
                    provenance={"provider": "semantic_scholar", "relation": "references", "source_paper_id": "s2-a", "prompt": "secret"},
                )
            ],
        )
        exported = client.get(f"/api/literature-maps/{map_id}/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/json")
        assert ".json" in exported.headers["content-disposition"]
        body = exported.json()
        assert set(body) == {"schema_version", "exported_at", "map", "groups", "nodes", "edges"}
        assert body["schema_version"] == "literature-map-export-v1"
        assert "owner_id" not in body["map"]
        assert body["map"]["map_id"] == map_id
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1
        assert body["edges"][0]["source_id"] == first.node_id
        assert body["edges"][0]["target_id"] == second.node_id
        assert body["nodes"][0]["provenance"]["provider"] == "semantic_scholar"
        assert body["nodes"][0]["provenance"]["catalog_snapshot"] == {"catalog_paper_id": "catalog-a"}
        serialized = exported.text
        assert "authorization" not in serialized
        assert "prompt" not in serialized
        assert "/private/data" not in serialized

        removed = service.remove_node(map_id, second.node_id, "local-user", expected_revision=0)
        assert removed["map"]["revision"] == 1
        reopened = client.get(f"/api/literature-maps/{map_id}/export")
        assert len(reopened.json()["nodes"]) == 1
        assert reopened.json()["edges"] == []
    reset_literature_map_runtime()


def test_edge_metadata_is_rejected_on_write_and_sanitized_on_export(tmp_path):
    from backend.app.literature_maps.application.service import LiteratureMapService
    from backend.app.literature_maps.infrastructure.store import LiteratureMapStore

    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing")
    first = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="A")
    second = MapPaper.new(item.map_id, semantic_scholar_id="s2-b", title="B")
    store.add_nodes(item.map_id, "owner-a", [first, second])
    polluted = MapEdge.new(
        item.map_id,
        "similarity",
        first.node_id,
        second.node_id,
        basis="/private/path",
        model_version="token=secret",
        content_hash="hiddenprompt",
    )
    with pytest.raises(ValueError, match="INVALID_EDGE_"):
        store.add_edges(item.map_id, "owner-a", [polluted])
    assert store.list_edges(item.map_id, "owner-a") == []

    valid = MapEdge.new(
        item.map_id,
        "similarity",
        first.node_id,
        second.node_id,
        basis="title_abstract",
        model_version="bge-m3",
        content_hash="a" * 64,
    )
    store.add_edges(item.map_id, "owner-a", [valid])
    with store.connection() as db:
        db.execute(
            "UPDATE literature_map_edges SET basis=?,model_version=?,content_hash=? WHERE edge_id=?",
            ("/private/path", "token=secret", "hiddenprompt", valid.edge_id),
        )
    export = LiteratureMapService(store=store, executor=None).export_map(item.map_id, "owner-a")
    edge = export["edges"][0]
    assert edge["basis"] is None
    assert edge["model_version"] is None
    assert edge["content_hash"] is None
    assert "/private/path" not in str(export)
    assert "token=secret" not in str(export)
    assert "hiddenprompt" not in str(export)
    reset_literature_map_runtime()
