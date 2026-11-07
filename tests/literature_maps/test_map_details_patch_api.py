"""PATCH /api/literature-maps/{map_id} details contract.

The rename flow sends only ``{expected_revision, name}`` -- no ``project_id``.
``project_id`` is an optional tri-state field:

* absent        -> keep the stored project binding untouched
* explicit null -> clear the binding
* a string      -> validate ownership and bind

Because the route forwards ``project_id`` only when it was present in the
request body, the service must forward it to the store only when it is not its
own ``_UNSET`` sentinel; forwarding the sentinel leaks a bare ``object()`` into
the SQLite parameter list and the map looks unavailable (503).

The absent-key regression case below is the lock for that bug. The 409/404
cases keep the optimistic-lock and owner-isolation guarantees intact.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import (
    get_literature_map_service,
    reset_literature_map_runtime,
)
from backend.app.main import app

OWNER = "local-user"
PROJECT = "project-alpha"


@pytest.fixture
def client(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        yield TestClient(app)
    reset_literature_map_runtime()


def _bind_project(map_id):
    """Bind a project through the store, as map creation would have done."""
    service = get_literature_map_service()
    created = service.store.get_map(map_id, OWNER)
    assert created is not None
    service.store.update_map_details(
        map_id, OWNER, expected_revision=created.revision, project_id=PROJECT
    )
    return service.store.get_map(map_id, OWNER)


def _new_map(client, topic="rename"):
    created = client.post("/api/literature-maps", json={"topic": topic, "limit": 20})
    assert created.status_code == 202
    return created.json()["map_id"]


def _details(client, map_id):
    response = client.get(f"/api/literature-maps/{map_id}")
    assert response.status_code == 200
    return response.json()["map"]


def test_rename_without_project_id_keeps_binding_and_bumps_revision(client):
    map_id = _new_map(client)
    before = _bind_project(map_id)
    assert before.project_id == PROJECT
    assert before.name != "Renamed map"

    renamed = client.patch(
        f"/api/literature-maps/{map_id}",
        json={"expected_revision": before.revision, "name": "Renamed map"},
    )

    assert renamed.status_code == 200
    body = renamed.json()["map"]
    assert body["name"] == "Renamed map"
    assert body["revision"] == before.revision + 1
    # The absent key must not clear (nor rewrite) the stored project binding.
    assert body["project_id"] == PROJECT

    stored = _details(client, map_id)
    assert stored["name"] == "Renamed map"
    assert stored["project_id"] == PROJECT
    assert stored["revision"] == before.revision + 1


def test_explicit_null_project_id_clears_binding(client):
    map_id = _new_map(client)
    before = _bind_project(map_id)
    assert before.project_id == PROJECT

    cleared = client.patch(
        f"/api/literature-maps/{map_id}",
        json={"expected_revision": before.revision, "name": before.name, "project_id": None},
    )

    assert cleared.status_code == 200
    body = cleared.json()["map"]
    assert body["project_id"] is None
    assert body["revision"] == before.revision + 1
    assert _details(client, map_id)["project_id"] is None


def test_rename_with_unknown_project_id_is_rejected_and_leaves_map_untouched(client):
    map_id = _new_map(client)
    before = _details(client, map_id)

    rejected = client.patch(
        f"/api/literature-maps/{map_id}",
        json={
            "expected_revision": before["revision"],
            "name": "Should not apply",
            "project_id": "missing-project",
        },
    )

    assert rejected.status_code == 404
    assert rejected.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    after = _details(client, map_id)
    assert after["name"] == before["name"]
    assert after["revision"] == before["revision"]
    assert after["project_id"] is None


def test_rename_with_stale_expected_revision_conflicts_without_writing(client):
    map_id = _new_map(client)
    before = _details(client, map_id)

    conflict = client.patch(
        f"/api/literature-maps/{map_id}",
        json={"expected_revision": before["revision"] + 7, "name": "Too late"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "MAP_CONFLICT"
    after = _details(client, map_id)
    assert after["name"] == before["name"]
    assert after["revision"] == before["revision"]


def test_rename_missing_map_is_404(client):
    response = client.patch(
        "/api/literature-maps/does-not-exist",
        json={"expected_revision": 0, "name": "Ghost"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MAP_NOT_FOUND"


def test_rename_map_of_another_owner_is_404(client, tmp_path):
    map_id = _new_map(client)
    service = get_literature_map_service()
    foreign = service.store.create_map("other-owner", topic="foreign")

    response = client.patch(
        f"/api/literature-maps/{foreign.map_id}",
        json={"expected_revision": 0, "name": "Hijacked"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MAP_NOT_FOUND"
    assert service.store.get_map(foreign.map_id, "other-owner").name != "Hijacked"
    # Own map untouched by the foreign attempt.
    assert _details(client, map_id)["name"] != "Hijacked"
