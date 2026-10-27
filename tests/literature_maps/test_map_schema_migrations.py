import sqlite3

import pytest

from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def _create_legacy_map_with_preview(database):
    store = LiteratureMapStore(database)
    item = store.create_map("owner-a", topic="fuzzing")
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-legacy",
        title="Existing map node",
        position={"x": 12, "y": -7},
    )
    store.add_nodes(item.map_id, "owner-a", [node])
    preview, _, _ = store.create_preview(
        item.map_id,
        "owner-a",
        kind="references",
        base_revision=1,
        candidates=[{"candidate_id": "candidate-1", "title": "Saved candidate"}],
        node_id=node.node_id,
        status="completed",
        idempotency_key="legacy-preview",
    )
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(literature_map_previews)")}
        for column in ("preview_revision", "pagination_json"):
            if column in columns:
                db.execute(f"ALTER TABLE literature_map_previews DROP COLUMN {column}")
        db.execute("DELETE FROM literature_map_schema WHERE version > 7")
        db.commit()
    return store, item, node, preview


def test_schema_upgrade_adds_pagination_defaults_and_preserves_existing_rows(tmp_path):
    database = tmp_path / "maps.sqlite3"
    _legacy_store, item, node, preview = _create_legacy_map_with_preview(database)

    upgraded = LiteratureMapStore(database)
    upgraded.initialize()

    assert upgraded.schema_version == 8
    with upgraded.connection() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(literature_map_previews)")}
        row = db.execute(
            "SELECT preview_revision,pagination_json,candidates_json FROM literature_map_previews WHERE preview_id=?",
            (preview.preview_id,),
        ).fetchone()
    assert {"preview_revision", "pagination_json"} <= columns
    assert row[0] == 1
    assert row[1] is None
    assert row[2] == '[{"candidate_id":"candidate-1","title":"Saved candidate"}]'
    persisted_node = upgraded.get_node(item.map_id, node.node_id, "owner-a")
    assert persisted_node is not None
    assert persisted_node.title == "Existing map node"
    assert persisted_node.position == {"x": 12.0, "y": -7.0}


def test_schema_upgrade_failure_rolls_back_v8_columns_and_keeps_legacy_preview(tmp_path, monkeypatch):
    database = tmp_path / "maps.sqlite3"
    _legacy_store, item, node, preview = _create_legacy_map_with_preview(database)

    def fail_after_ddl(_db):
        raise RuntimeError("forced migration interruption")

    monkeypatch.setattr(LiteratureMapStore, "_repair_legacy_idempotency_bindings", staticmethod(fail_after_ddl))
    with pytest.raises(RuntimeError, match="forced migration interruption"):
        LiteratureMapStore(database)

    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(literature_map_previews)")}
        saved = db.execute(
            "SELECT candidates_json FROM literature_map_previews WHERE preview_id=?",
            (preview.preview_id,),
        ).fetchone()
        versions = {row[0] for row in db.execute("SELECT version FROM literature_map_schema")}
    assert not {"preview_revision", "pagination_json"} & columns
    assert saved is not None
    assert 8 not in versions

    monkeypatch.undo()
    upgraded = LiteratureMapStore(database)
    assert upgraded.schema_version == 8
    assert upgraded.get_node(item.map_id, node.node_id, "owner-a") is not None
