from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import get_literature_map_service, reset_literature_map_runtime
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.main import app


def _client_with_map(tmp_path):
    reset_literature_map_runtime()
    env = {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}
    patcher = patch.dict("os.environ", env, clear=False)
    patcher.start()
    runner = patch("backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True)
    runner.start()
    client = TestClient(app)
    created = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20}).json()
    service = get_literature_map_service()
    node = MapPaper.new(created["map_id"], semantic_scholar_id="s2-a", title="A paper")
    service.store.add_nodes(created["map_id"], "local-user", [node])
    return client, created["map_id"], node, patcher, runner


def test_groups_use_map_revision_and_delete_only_unassigns_nodes(tmp_path):
    client, map_id, node, env_patcher, runner = _client_with_map(tmp_path)
    try:
        created = client.post(
            f"/api/literature-maps/{map_id}/groups",
            json={"expected_revision": 0, "name": "  Methods  ", "color": "#12abef"},
        )
        assert created.status_code == 200
        assert created.json()["revision"] == 1
        group = created.json()["groups"][0]
        assert group["name"] == "Methods"
        assert group["color"] == "#12ABEF"

        assigned = client.put(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/group",
            json={"expected_revision": 1, "group_id": group["group_id"]},
        )
        assert assigned.status_code == 200
        assert assigned.json()["revision"] == 2
        assert assigned.json()["node"]["group_id"] == group["group_id"]

        renamed = client.patch(
            f"/api/literature-maps/{map_id}/groups/{group['group_id']}",
            json={"expected_revision": 2, "name": "Results", "color": "#ABC123"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["revision"] == 3
        assert renamed.json()["groups"][0]["name"] == "Results"

        stale = client.request(
            "DELETE",
            f"/api/literature-maps/{map_id}/groups/{group['group_id']}",
            json={"expected_revision": 2},
        )
        assert stale.status_code == 409

        deleted = client.request(
            "DELETE",
            f"/api/literature-maps/{map_id}/groups/{group['group_id']}",
            json={"expected_revision": 3},
        )
        assert deleted.status_code == 200
        assert deleted.json()["revision"] == 4
        assert deleted.json()["groups"] == []
        assert client.get(f"/api/literature-maps/{map_id}/nodes/{node.node_id}").json()["node"]["group_id"] is None
    finally:
        runner.stop()
        env_patcher.stop()
        reset_literature_map_runtime()


def test_group_validation_and_removed_node_boundary(tmp_path):
    client, map_id, node, env_patcher, runner = _client_with_map(tmp_path)
    try:
        invalid = client.post(
            f"/api/literature-maps/{map_id}/groups",
            json={"expected_revision": 0, "name": " ", "color": "red"},
        )
        assert invalid.status_code in {400, 422}

        service = get_literature_map_service()
        removed = service.remove_node(map_id, node.node_id, "local-user", expected_revision=0)
        assert removed["map"]["revision"] == 1
        missing_group = client.put(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/group",
            json={"expected_revision": 1, "group_id": None},
        )
        assert missing_group.status_code in {400, 409}
    finally:
        runner.stop()
        env_patcher.stop()
        reset_literature_map_runtime()


def test_group_store_rejects_cross_map_group_and_revision_conflict(tmp_path):
    from backend.app.literature_maps.infrastructure.store import LiteratureMapStore

    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    first = store.create_map("owner-a", topic="one")
    second = store.create_map("owner-a", topic="two")
    group = store.create_group(first.map_id, "owner-a", expected_revision=0, name="Group", color="#ffffff")
    assert group.group_id
    with pytest.raises(LookupError):
        store.assign_node_group(second.map_id, "owner-a", node_id="missing", expected_revision=0, group_id=group.group_id)
    with pytest.raises(ValueError, match="revision conflict"):
        store.create_group(first.map_id, "owner-a", expected_revision=0, name="Stale", color="#000000")


def test_node_insert_rejects_cross_map_group_atomically(tmp_path):
    from backend.app.literature_maps.infrastructure.store import LiteratureMapStore

    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    first = store.create_map("owner-a", topic="one")
    second = store.create_map("owner-a", topic="two")
    foreign_group = store.create_group(second.map_id, "owner-a", expected_revision=0, name="Foreign", color="#ffffff")
    valid = MapPaper.new(first.map_id, semantic_scholar_id="s2-valid", title="Valid")
    invalid = MapPaper.new(first.map_id, semantic_scholar_id="s2-invalid", title="Invalid", group_id=foreign_group.group_id)

    with pytest.raises(LookupError, match="group not found"):
        store.add_nodes(first.map_id, "owner-a", [valid, invalid])
    assert store.list_nodes(first.map_id, "owner-a") == []

    preview, _job, _created = store.create_preview(
        first.map_id,
        "owner-a",
        kind="topic",
        base_revision=0,
        candidates=[{"candidate_id": "candidate-invalid"}],
    )
    with pytest.raises(LookupError, match="group not found"):
        store.apply_preview(
            first.map_id,
            "owner-a",
            preview_id=preview.preview_id,
            expected_revision=0,
            selected_candidate_ids=["candidate-invalid"],
            nodes=[invalid],
        )
    assert store.list_nodes(first.map_id, "owner-a") == []
