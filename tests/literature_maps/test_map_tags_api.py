"""BE-2 API tests for map-tag endpoints and derived list ``tags``.

Covers the six tag endpoints plus the read-only ``tags`` derivation on
``GET /api/literature-maps`` and the ``skipped_items`` queue passthrough.
Owner isolation is enforced at the route layer (no cross-owner visibility).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import (
    get_literature_map_service,
    reset_literature_map_runtime,
)
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app

OWNER = "local-user"


def _make_client(tmp_path):
    reset_literature_map_runtime()
    env = {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}
    patcher = patch.dict("os.environ", env, clear=False)
    patcher.start()
    runner = patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job",
        autospec=True,
    )
    runner.start()
    client = TestClient(app)
    return client, patcher, runner


def _create_map(client):
    created = client.post("/api/literature-maps", json={"topic": "tagging", "limit": 20}).json()
    return created["map_id"]


def test_list_tags_empty_and_owner_isolated(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        empty = client.get("/api/literature-maps/tags")
        assert empty.status_code == 200
        assert empty.json()["tags"] == []

        # A tag owned by another owner must never surface under this owner.
        store = LiteratureMapStore(tmp_path / "maps.sqlite3")
        store.create_tag("other-owner", name="foreign", color="#ff0000")
        assert client.get("/api/literature-maps/tags").json()["tags"] == []
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_create_tag_success_default_color_and_duplicate_409(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        created = client.post("/api/literature-maps/tags", json={"name": "  RL  ", "color": "#12abef"})
        assert created.status_code == 201
        body = created.json()
        assert body["tag_id"]
        assert body["name"] == "RL"        # whitespace stripped
        assert body["color"] == "#12ABEF"  # normalized to upper hex

        no_color = client.post("/api/literature-maps/tags", json={"name": "NLP"})
        assert no_color.status_code == 201
        assert no_color.json()["color"] == "#8D80E6"  # brand default

        dup = client.post("/api/literature-maps/tags", json={"name": "RL", "color": "#000000"})
        assert dup.status_code == 409
        assert dup.json()["detail"]["code"] == "TAG_NAME_CONFLICT"
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_create_tag_validation_400(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        empty_name = client.post("/api/literature-maps/tags", json={"name": "  ", "color": "#123456"})
        assert empty_name.status_code in {400, 422}
        bad_color = client.post("/api/literature-maps/tags", json={"name": "X", "color": "red"})
        assert bad_color.status_code in {400, 422}
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_patch_tag_success_partial_and_validation(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        created = client.post("/api/literature-maps/tags", json={"name": "A", "color": "#111111"}).json()
        tag_id = created["tag_id"]

        patched = client.patch(f"/api/literature-maps/tags/{tag_id}", json={"name": "B", "color": "#222222"})
        assert patched.status_code == 200
        assert patched.json()["name"] == "B"
        assert patched.json()["color"] == "#222222"

        partial = client.patch(f"/api/literature-maps/tags/{tag_id}", json={"name": "C"})
        assert partial.status_code == 200
        assert partial.json()["name"] == "C"
        assert partial.json()["color"] == "#222222"

        bad = client.patch(f"/api/literature-maps/tags/{tag_id}", json={"color": "xyz"})
        assert bad.status_code in {400, 422}
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_patch_delete_missing_or_cross_owner_returns_404(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        store = LiteratureMapStore(tmp_path / "maps.sqlite3")
        foreign = store.create_tag("other-owner", name="foreign", color="#ff0000")

        # Cross-owner tag id -> 404 with the same code as a missing id (no
        # existence leak).
        patched = client.patch(f"/api/literature-maps/tags/{foreign.tag_id}", json={"name": "hijack"})
        assert patched.status_code == 404
        assert patched.json()["detail"]["code"] == "TAG_NOT_OWNED"

        deleted = client.request("DELETE", f"/api/literature-maps/tags/{foreign.tag_id}")
        assert deleted.status_code == 404
        assert deleted.json()["detail"]["code"] == "TAG_NOT_OWNED"

        # A tag id that does not exist at all for this owner is also 404 with
        # the same code.
        missing_patch = client.patch("/api/literature-maps/tags/does-not-exist", json={"name": "x"})
        assert missing_patch.status_code == 404
        assert missing_patch.json()["detail"]["code"] == "TAG_NOT_OWNED"

        missing_delete = client.request("DELETE", "/api/literature-maps/tags/does-not-exist")
        assert missing_delete.status_code == 404
        assert missing_delete.json()["detail"]["code"] == "TAG_NOT_OWNED"
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_delete_tag_unbinds_maps_and_clears_list(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        map_id = _create_map(client)
        created = client.post("/api/literature-maps/tags", json={"name": "T", "color": "#abcdef"}).json()
        tag_id = created["tag_id"]

        bound = client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": [tag_id]})
        assert bound.status_code == 200
        assert bound.json()["tags"][0]["tag_id"] == tag_id

        deleted = client.request("DELETE", f"/api/literature-maps/tags/{tag_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert deleted.json()["unbound_maps"] == 1

        # Tag is gone from the global list and from the map's derived tags.
        assert client.get("/api/literature-maps/tags").json()["tags"] == []
        maps = client.get("/api/literature-maps").json()["maps"]
        target = next(m for m in maps if m["map_id"] == map_id)
        assert target["tags"] == []
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def _create_tags(client, n, prefix="t"):
    return [
        client.post("/api/literature-maps/tags", json={"name": f"{prefix}{i}", "color": "#000000"}).json()["tag_id"]
        for i in range(n)
    ]


def test_put_map_tags_success_idempotent_limit_and_404(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        map_id = _create_map(client)
        three = _create_tags(client, 3, prefix="a")
        service = get_literature_map_service()
        before = service.store.get_map(map_id, OWNER).revision

        first = client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": three})
        assert first.status_code == 200
        assert [t["tag_id"] for t in first.json()["tags"]] == three
        assert [t["name"] for t in first.json()["tags"]] == ["a0", "a1", "a2"]

        # Idempotent: re-applying the same set keeps one binding per tag.
        second = client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": three})
        assert second.status_code == 200
        assert [t["tag_id"] for t in second.json()["tags"]] == three

        # PUT must not bump literature_maps.revision.
        after = service.store.get_map(map_id, OWNER).revision
        assert after == before

        # Map-not-found -> 404 (also exercises the 404 coverage path).
        missing = client.put("/api/literature-maps/does-not-exist/tags", json={"tag_ids": three})
        assert missing.status_code == 404

        # Binding limit: > 20 tags -> 422 (TAG_LIMIT).
        many = _create_tags(client, 21, prefix="b")
        over = client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": many})
        assert over.status_code == 422
        assert over.json()["detail"]["code"] == "TAG_LIMIT"
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_put_map_tags_rejects_cross_owner_tag_422(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        map_id = _create_map(client)
        store = LiteratureMapStore(tmp_path / "maps.sqlite3")
        foreign = store.create_tag("other-owner", name="foreign", color="#ff0000")

        resp = client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": [foreign.tag_id]})
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "TAG_NOT_FOUND"
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_list_maps_derives_tags_and_keeps_legacy_fields(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        map_id = _create_map(client)
        created = client.post("/api/literature-maps/tags", json={"name": "Tagged", "color": "#abcdef"}).json()
        client.put(f"/api/literature-maps/{map_id}/tags", json={"tag_ids": [created["tag_id"]]})

        maps = client.get("/api/literature-maps").json()["maps"]
        target = next(m for m in maps if m["map_id"] == map_id)
        # Legacy fields are preserved.
        assert "status" in target
        assert "node_count" in target
        # Derived tags reflect the binding.
        assert target["tags"] == [
            {"tag_id": created["tag_id"], "name": "Tagged", "color": "#ABCDEF"}
        ]

        # A map with no binding still carries tags: [].
        empty_map = _create_map(client)
        maps2 = client.get("/api/literature-maps").json()["maps"]
        empty_target = next(m for m in maps2 if m["map_id"] == empty_map)
        assert empty_target["tags"] == []
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()


def test_analysis_queue_returns_skipped_items(tmp_path):
    client, env_p, run = _make_client(tmp_path)
    try:
        map_id = _create_map(client)
        queue = client.get(f"/api/literature-maps/{map_id}/analysis-queue").json()
        assert "skipped_items" in queue
        assert isinstance(queue["skipped_items"], list)
    finally:
        run.stop()
        env_p.stop()
        reset_literature_map_runtime()
