"""Saving a map view must mark `view_settings.view_initialized`.

The marker is evidence that the user explicitly saved a view at least once.
It is a store-internal key written by `update_view`, never a request field:
`PATCH /{map_id}/view` keeps its closed `extra="forbid"` body.
"""

import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import (
    get_literature_map_service,
    reset_literature_map_runtime,
)
from backend.app.main import app


@pytest.fixture
def client(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        yield TestClient(app)
    reset_literature_map_runtime()


def _new_map(client, topic="view flag"):
    created = client.post("/api/literature-maps", json={"topic": topic, "limit": 20})
    assert created.status_code == 202
    return created.json()["map_id"]


def _view(client, map_id, *, expected_revision, **body):
    return client.patch(
        f"/api/literature-maps/{map_id}/view",
        json={"expected_revision": expected_revision, **body},
    )


def _stored_view_json(map_id):
    """Read view_json straight from SQLite, bypassing service export."""
    store = get_literature_map_service().store
    with sqlite3.connect(store.database_path) as db:
        row = db.execute("SELECT view_json FROM literature_maps WHERE map_id=?", (map_id,)).fetchone()
    assert row is not None
    return row[0]


def test_update_view_marks_view_initialized(client):
    map_id = _new_map(client)

    response = _view(client, map_id, expected_revision=0, viewport={"x": 12, "y": -3, "scale": 1.75})
    assert response.status_code == 200
    assert response.json()["map"]["revision"] == 1

    fetched = client.get(f"/api/literature-maps/{map_id}")
    assert fetched.status_code == 200
    settings = fetched.json()["map"]["view_settings"]
    assert settings["view_initialized"] is True
    # The flag is internal: it never leaks into the exported filters bucket.
    assert "view_initialized" not in settings.get("filters", {})
    # Store-level, independent of the service projection.
    assert json.loads(_stored_view_json(map_id))["view_initialized"] is True


def test_update_view_keeps_existing_view_settings_keys(client):
    map_id = _new_map(client)

    first = _view(
        client,
        map_id,
        expected_revision=0,
        filters={"year_start": 2020},
        layers={"citation": False, "similarity": True},
        label_mode="neighbors",
        node_style={"fill_mode": "outline", "fill_opacity": 0.8},
    )
    assert first.status_code == 200
    before = first.json()["map"]["view_settings"]
    assert before == {
        "filters": {"year_start": 2020},
        "viewport": {"x": 0.0, "y": 0.0, "scale": 1.0},
        "layers": {"citation": False, "similarity": True},
        "label_mode": "neighbors",
        "node_style": {"fill_mode": "outline", "fill_opacity": 0.8},
        "view_initialized": True,
    }

    # A later save that only moves the viewport must not drop earlier keys.
    second = _view(client, map_id, expected_revision=1, viewport={"x": 5, "y": 6, "scale": 2})
    assert second.status_code == 200
    after = second.json()["map"]["view_settings"]
    assert after["viewport"] == {"x": 5.0, "y": 6.0, "scale": 2.0}
    assert after["filters"] == {"year_start": 2020}
    assert after["layers"] == {"citation": False, "similarity": True}
    assert after["label_mode"] == "neighbors"
    assert after["node_style"] == {"fill_mode": "outline", "fill_opacity": 0.8}
    assert after["view_initialized"] is True


def test_map_without_saved_view_has_no_view_initialized_key(client):
    map_id = _new_map(client)

    settings = client.get(f"/api/literature-maps/{map_id}").json()["map"]["view_settings"]
    assert "view_initialized" not in settings
    # Pre-existing defaults are untouched by the marker.
    assert settings["viewport"] == {"x": 0.0, "y": 0.0, "scale": 1.0}
    assert settings["label_mode"] == "all"
    assert settings["node_style"] == {"fill_mode": "filled", "fill_opacity": 0.3}
    assert "view_initialized" not in _stored_view_json(map_id)


def test_revision_conflict_rolls_back_and_does_not_mark_view_initialized(client):
    map_id = _new_map(client)

    conflict = _view(client, map_id, expected_revision=7, viewport={"x": 1, "y": 1, "scale": 1})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "MAP_CONFLICT"

    current = client.get(f"/api/literature-maps/{map_id}")
    assert current.status_code == 200
    assert current.json()["map"]["revision"] == 0
    assert "view_initialized" not in current.json()["map"]["view_settings"]
    assert "view_initialized" not in _stored_view_json(map_id)


def test_view_initialized_is_not_an_accepted_request_field(client):
    map_id = _new_map(client)

    rejected = _view(client, map_id, expected_revision=0, view_initialized=True)
    assert rejected.status_code == 422
    settings = client.get(f"/api/literature-maps/{map_id}").json()["map"]["view_settings"]
    assert "view_initialized" not in settings


def _export(client, map_id):
    response = client.get(f"/api/literature-maps/{map_id}/export")
    assert response.status_code == 200
    return response.json()


def test_export_omits_view_initialized_before_any_view_save(client):
    """The export whitelist emits the marker by presence, so a fresh map has no key."""
    map_id = _new_map(client)

    body = _export(client, map_id)
    settings = body["map"]["view_settings"]
    assert "view_initialized" not in settings
    # The rest of the whitelisted view settings is unaffected by the marker.
    assert settings == {
        "filters": {},
        "viewport": {"x": 0.0, "y": 0.0, "scale": 1.0},
        "layers": {"citation": True, "similarity": True},
        "label_mode": "all",
        "node_style": {"fill_mode": "filled", "fill_opacity": 0.3},
    }


def test_export_reports_view_initialized_after_view_save(client):
    map_id = _new_map(client)
    saved = _view(client, map_id, expected_revision=0, viewport={"x": 4, "y": 5, "scale": 2})
    assert saved.status_code == 200

    body = _export(client, map_id)
    settings = body["map"]["view_settings"]
    assert settings["view_initialized"] is True
    # The save is exported with its real values, not just the marker.
    assert settings["viewport"] == {"x": 4.0, "y": 5.0, "scale": 2.0}
    assert settings["label_mode"] == "all"
    assert settings["node_style"] == {"fill_mode": "filled", "fill_opacity": 0.3}
    # Envelope keys still line up with the export contract.
    assert body["schema_version"] == "literature-map-export-v2"
    assert body["map"]["map_id"] == map_id
    assert body["map"]["revision"] == 1
    assert body["nodes"] == []
    assert body["edges"] == []
