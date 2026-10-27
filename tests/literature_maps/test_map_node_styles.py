from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import (
    get_literature_map_service,
    reset_literature_map_runtime,
)
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app


def _map_with_nodes(tmp_path, *, count=3, include_created_response=False):
    reset_literature_map_runtime()
    env = {
        "LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3"),
        "MEMORY_DB_PATH": str(tmp_path / "memory.sqlite3"),
        "PAPER_DISCOVERY_DB_PATH": str(tmp_path / "paper-discovery.sqlite3"),
        "KB_DIR": str(tmp_path / "kb"),
        "MEMORY_DIR": str(tmp_path / "memory"),
        "QDRANT_PATH": str(tmp_path / "qdrant"),
    }
    patcher = patch.dict("os.environ", env, clear=False)
    patcher.start()
    from backend.app.api import common

    common.article_settings.paper_discovery_db_path = env["PAPER_DISCOVERY_DB_PATH"]
    common.paper_discovery_store = None
    common.paper_discovery_store_path = None
    runner = patch("backend.app.literature_maps.application.service.LiteratureMapService.run_job", new=lambda *args, **kwargs: None)
    runner.start()
    client = TestClient(app)
    created = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20}).json()
    service = get_literature_map_service()
    nodes = [
        MapPaper.new(created["map_id"], semantic_scholar_id=f"s2-{index}", title=f"Paper {index}")
        for index in range(count)
    ]
    service.store.add_nodes(created["map_id"], "local-user", nodes)
    result = (client, created["map_id"], nodes, patcher, runner)
    return (*result, created) if include_created_response else result


def _close_runtime(patcher, runner):
    runner.stop()
    patcher.stop()
    from backend.app.api import common

    common.paper_discovery_store = None
    common.paper_discovery_store_path = None
    reset_literature_map_runtime()


def test_schema_upgrade_is_idempotent_and_preserves_existing_node_fields(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    store = LiteratureMapStore(database_path)
    item = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-legacy",
        title="Legacy title",
        position={"x": 11, "y": -4},
        group_id=None,
    )
    store.add_nodes(item.map_id, "owner-a", [node])

    reopened = LiteratureMapStore(database_path)
    reopened.initialize()
    assert reopened.schema_version == 7
    preserved = reopened.get_node(item.map_id, node.node_id, "owner-a")
    assert preserved is not None
    assert preserved.title == "Legacy title"
    assert preserved.position == {"x": 11, "y": -4}
    assert preserved.color_override is None


def test_node_style_patch_round_trips_through_graph_and_node_without_changing_group(tmp_path):
    client, map_id, nodes, patcher, runner = _map_with_nodes(tmp_path)
    try:
        service = get_literature_map_service()
        group = service.store.create_group(
            map_id,
            "local-user",
            expected_revision=0,
            name="Methods",
            color="#123456",
        )
        service.store.assign_node_group(
            map_id,
            "local-user",
            node_id=nodes[0].node_id,
            expected_revision=1,
            group_id=group.group_id,
        )
        response = client.patch(
            f"/api/literature-maps/{map_id}/node-styles",
            json={
                "expected_revision": 2,
                "node_ids": [nodes[0].node_id, nodes[1].node_id],
                "color_override": "#aBc123",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "literature-map-v1"
        assert body["revision"] == 3
        assert body["color_override"] == "#ABC123"
        assert body["node_ids"] == [nodes[0].node_id, nodes[1].node_id]
        assert [node["color_override"] for node in body["nodes"]] == ["#ABC123", "#ABC123"]

        graph = client.get(f"/api/literature-maps/{map_id}/graph")
        assert graph.status_code == 200
        assert graph.json()["schema_version"] == "literature-map-v1"
        graph_nodes = {node["node_id"]: node for node in graph.json()["nodes"]}
        assert graph_nodes[nodes[0].node_id]["color_override"] == "#ABC123"
        assert graph_nodes[nodes[2].node_id]["color_override"] is None
        single = client.get(f"/api/literature-maps/{map_id}/nodes/{nodes[0].node_id}")
        assert single.json()["schema_version"] == "literature-map-v1"
        assert single.json()["node"]["color_override"] == "#ABC123"
        assert single.json()["node"]["group_id"] == group.group_id
    finally:
        _close_runtime(patcher, runner)


def test_node_style_patch_is_validated_and_atomic_for_unknown_or_removed_nodes(tmp_path):
    client, map_id, nodes, patcher, runner = _map_with_nodes(tmp_path)
    try:
        missing_field = client.patch(
            f"/api/literature-maps/{map_id}/node-styles",
            json={"expected_revision": 0, "node_ids": [nodes[0].node_id]},
        )
        assert missing_field.status_code == 422

        duplicate = client.patch(
            f"/api/literature-maps/{map_id}/node-styles",
            json={
                "expected_revision": 0,
                "node_ids": [nodes[0].node_id, nodes[0].node_id],
                "color_override": None,
            },
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"]["code"] == "INVALID_NODE_IDS"

        service = get_literature_map_service()
        removed = service.store.remove_node(map_id, nodes[2].node_id, "local-user", expected_revision=0)
        assert removed["map"]["revision"] == 1
        failed = client.patch(
            f"/api/literature-maps/{map_id}/node-styles",
            json={
                "expected_revision": 1,
                "node_ids": [nodes[0].node_id, nodes[2].node_id],
                "color_override": "#FF0000",
            },
        )
        assert failed.status_code == 409
        assert failed.json()["detail"]["code"] == "MAP_NODE_REMOVED"
        assert service.store.get_node(map_id, nodes[0].node_id, "local-user").color_override is None
        assert service.store.get_map(map_id, "local-user").revision == 1
    finally:
        _close_runtime(patcher, runner)


def test_map_create_response_includes_default_node_style(tmp_path):
    client, map_id, _nodes, patcher, runner, created = _map_with_nodes(
        tmp_path, count=1, include_created_response=True
    )
    try:
        expected = {"fill_mode": "filled", "fill_opacity": 0.3}
        created_style = created["map"]["view_settings"]["node_style"]
        fetched_style = client.get(f"/api/literature-maps/{map_id}").json()["map"]["view_settings"]["node_style"]
        assert created_style == expected
        assert created_style == fetched_style
    finally:
        _close_runtime(patcher, runner)


@pytest.mark.parametrize("fill_opacity", [True, False], ids=["true", "false"])
def test_view_style_rejects_boolean_fill_opacity_over_http(tmp_path, fill_opacity):
    client, map_id, _nodes, patcher, runner = _map_with_nodes(tmp_path, count=1)
    try:
        response = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={
                "expected_revision": 0,
                "node_style": {"fill_mode": "filled", "fill_opacity": fill_opacity},
            },
        )
        assert response.status_code == 422
        current = client.get(f"/api/literature-maps/{map_id}").json()["map"]
        assert current["revision"] == 0
        assert current["view_settings"]["node_style"] == {"fill_mode": "filled", "fill_opacity": 0.3}
    finally:
        _close_runtime(patcher, runner)


def test_view_style_is_formal_defaulted_and_not_stored_in_filters(tmp_path):
    client, map_id, _nodes, patcher, runner = _map_with_nodes(tmp_path, count=1)
    try:
        initial = client.get(f"/api/literature-maps/{map_id}").json()["map"]["view_settings"]
        assert initial["node_style"] == {"fill_mode": "filled", "fill_opacity": 0.3}

        updated = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={
                "expected_revision": 0,
                "filters": {"year_start": 2020},
                "node_style": {"fill_mode": "outline", "fill_opacity": 1},
            },
        )
        assert updated.status_code == 200
        settings = updated.json()["map"]["view_settings"]
        assert settings["node_style"] == {"fill_mode": "outline", "fill_opacity": 1.0}
        assert settings["filters"] == {"year_start": 2020}
        assert "node_style" not in settings["filters"]

        hidden_style = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={"expected_revision": 1, "filters": {"node_style": {"fill_mode": "outline"}}},
        )
        assert hidden_style.status_code == 400
        assert hidden_style.json()["detail"]["code"] == "INVALID_NODE_STYLE"

        invalid = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={
                "expected_revision": 1,
                "node_style": {"fill_mode": "outline", "fill_opacity": 1.1},
            },
        )
        assert invalid.status_code == 422
        unknown = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={
                "expected_revision": 1,
                "node_style": {"fill_mode": "filled", "fill_opacity": 0.5, "recent_colors": []},
            },
        )
        assert unknown.status_code == 422
    finally:
        _close_runtime(patcher, runner)


def test_export_v2_whitelists_color_override_and_node_style(tmp_path):
    client, map_id, nodes, patcher, runner = _map_with_nodes(tmp_path, count=1)
    try:
        service = get_literature_map_service()
        styled = service.store.update_node_styles(
            map_id,
            "local-user",
            expected_revision=0,
            node_ids=[nodes[0].node_id],
            color_override="#aabbcc",
        )
        assert styled[0].color_override == "#AABBCC"
        view = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={
                "expected_revision": 1,
                "node_style": {"fill_mode": "outline", "fill_opacity": 0.75},
            },
        )
        assert view.status_code == 200
        export = client.get(f"/api/literature-maps/{map_id}/export")
        assert export.status_code == 200
        body = export.json()
        assert body["schema_version"] == "literature-map-export-v2"
        assert body["map"]["view_settings"]["node_style"] == {"fill_mode": "outline", "fill_opacity": 0.75}
        assert body["nodes"][0]["color_override"] == "#AABBCC"
        assert "owner_id" not in body["map"]
        serialized = export.text
        assert "recent_colors" not in serialized
        assert "preview" not in serialized
    finally:
        _close_runtime(patcher, runner)


def test_store_node_styles_rejects_cross_owner_and_too_many_nodes(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="A")
    store.add_nodes(item.map_id, "owner-a", [node])
    with pytest.raises(LookupError, match="map not found"):
        store.update_node_styles(
            item.map_id,
            "owner-b",
            expected_revision=0,
            node_ids=[node.node_id],
            color_override="#123456",
        )
    with pytest.raises(ValueError, match="INVALID_NODE_IDS"):
        store.update_node_styles(
            item.map_id,
            "owner-a",
            expected_revision=0,
            node_ids=[node.node_id] * 201,
            color_override=None,
        )
