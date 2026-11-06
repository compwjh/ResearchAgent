"""Backend-only store tests for Spec043 BE-1: map tag storage + queue skipped_items.

No HTTP layer is exercised here. These tests lock the contract that the
``LiteratureMapStore`` tag methods and the analysis-queue ``skipped_items``
projection must satisfy before the BE-2 routing layer is built.
"""

import json

import pytest

from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore, iso_now


def _store(tmp_path):
    return LiteratureMapStore(tmp_path / "maps.sqlite3")


def _map(store, owner="owner-a"):
    return store.create_map(owner, topic="fuzzing", name="Fuzzing").map_id


class TestTagLifecycle:
    def test_create_tag_strips_name_and_normalizes_color(self, tmp_path):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "  Methods  ", "#12abef")
        assert tag.name == "Methods"
        assert tag.color == "#12ABEF"
        assert tag.owner_id == "owner-a"
        assert tag.tag_id

        defaulted = store.create_tag("owner-a", "Results")
        assert defaulted.color == "#8D80E6"

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_create_tag_rejects_empty_or_whitespace_name(self, tmp_path, name):
        store = _store(tmp_path)
        with pytest.raises(ValueError, match="INVALID_TAG_NAME"):
            store.create_tag("owner-a", name)

    def test_create_tag_rejects_overlong_name(self, tmp_path):
        store = _store(tmp_path)
        with pytest.raises(ValueError, match="INVALID_TAG_NAME"):
            store.create_tag("owner-a", "x" * 81)

    @pytest.mark.parametrize("color", ["#zzz", "red", "#12345", "8d80e6", ""])
    def test_create_tag_rejects_illegal_color(self, tmp_path, color):
        store = _store(tmp_path)
        with pytest.raises(ValueError, match="INVALID_TAG_COLOR"):
            store.create_tag("owner-a", "Tag", color)

    def test_duplicate_name_same_owner_conflicts_case_insensitive(self, tmp_path):
        store = _store(tmp_path)
        store.create_tag("owner-a", "Methods")
        with pytest.raises(ValueError, match="TAG_NAME_CONFLICT"):
            store.create_tag("owner-a", "methods")
        # cross-owner is allowed and isolated
        other = store.create_tag("owner-b", "Methods")
        assert other.owner_id == "owner-b"
        assert {t.name for t in store.list_tags("owner-a")} == {"Methods"}

    def test_list_tags_owner_scoped(self, tmp_path):
        store = _store(tmp_path)
        store.create_tag("owner-a", "A")
        store.create_tag("owner-a", "B")
        store.create_tag("owner-b", "Secret")
        names = {t.name for t in store.list_tags("owner-a")}
        assert names == {"A", "B"}
        assert all(t.owner_id == "owner-a" for t in store.list_tags("owner-a"))
        assert store.list_tags("owner-c") == []

    def test_update_tag_rename_and_recolor(self, tmp_path):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "Methods", "#111111")
        updated = store.update_tag("owner-a", tag.tag_id, name="Results", color="#222222")
        assert updated.name == "Results"
        assert updated.color == "#222222"

    def test_update_tag_is_idempotent_when_unchanged(self, tmp_path):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "Methods", "#111111")
        same = store.update_tag("owner-a", tag.tag_id)
        assert same.name == "Methods"
        assert same.color == "#111111"

    def test_update_tag_name_conflict_raises(self, tmp_path):
        store = _store(tmp_path)
        store.create_tag("owner-a", "A")
        b = store.create_tag("owner-a", "B")
        with pytest.raises(ValueError, match="TAG_NAME_CONFLICT"):
            store.update_tag("owner-a", b.tag_id, name="a")

    def test_update_tag_not_found_or_unauthorized(self, tmp_path):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "A")
        with pytest.raises(LookupError, match="tag not found"):
            store.update_tag("owner-b", tag.tag_id, name="X")
        with pytest.raises(LookupError, match="tag not found"):
            store.update_tag("owner-a", "missing", name="X")

    @pytest.mark.parametrize("name,color", [("  ", None), (None, "#bad")])
    def test_update_tag_invalid_name_color(self, tmp_path, name, color):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "A")
        with pytest.raises(ValueError):
            store.update_tag("owner-a", tag.tag_id, name=name, color=color)


class TestTagDeleteAndBindings:
    def test_delete_tag_unbinds_maps_atomically_and_returns_count(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        tag = store.create_tag("owner-a", "A")
        store.set_map_tags(map_id, "owner-a", [tag.tag_id])
        assert store.list_map_tags(map_id, "owner-a") == [
            {"tag_id": tag.tag_id, "name": "A", "color": "#8D80E6"}
        ]
        unbound = store.delete_tag("owner-a", tag.tag_id)
        assert unbound == 1
        assert store.list_tags("owner-a") == []
        assert store.list_map_tags(map_id, "owner-a") == []
        with pytest.raises(LookupError, match="tag not found"):
            store.delete_tag("owner-a", tag.tag_id)

    def test_delete_tag_unauthorized(self, tmp_path):
        store = _store(tmp_path)
        tag = store.create_tag("owner-a", "A")
        with pytest.raises(LookupError, match="tag not found"):
            store.delete_tag("owner-b", tag.tag_id)


class TestMapTagBindings:
    def test_set_map_tags_validates_existence_and_ownership(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        own = store.create_tag("owner-a", "Mine")
        other = store.create_tag("owner-b", "Theirs")
        with pytest.raises(ValueError, match="TAG_NOT_FOUND"):
            store.set_map_tags(map_id, "owner-a", ["nope"])
        with pytest.raises(ValueError, match="TAG_NOT_FOUND"):
            store.set_map_tags(map_id, "owner-a", [other.tag_id])
        with pytest.raises(LookupError, match="map not found"):
            store.set_map_tags("missing-map", "owner-a", [own.tag_id])

    def test_set_map_tags_returns_bound_tags_in_order_dedup(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        a = store.create_tag("owner-a", "A")
        b = store.create_tag("owner-a", "B")
        result = store.set_map_tags(map_id, "owner-a", [b.tag_id, a.tag_id, b.tag_id])
        assert result == [
            {"tag_id": b.tag_id, "name": "B", "color": "#8D80E6"},
            {"tag_id": a.tag_id, "name": "A", "color": "#8D80E6"},
        ]

    def test_set_map_tags_replaces_full_set(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        a = store.create_tag("owner-a", "A")
        b = store.create_tag("owner-a", "B")
        store.set_map_tags(map_id, "owner-a", [a.tag_id])
        store.set_map_tags(map_id, "owner-a", [b.tag_id])
        assert store.list_map_tags(map_id, "owner-a") == [
            {"tag_id": b.tag_id, "name": "B", "color": "#8D80E6"}
        ]

    def test_set_map_tags_limit_20(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        tag_ids = [store.create_tag("owner-a", f"T{i}").tag_id for i in range(21)]
        with pytest.raises(ValueError, match="TAG_LIMIT"):
            store.set_map_tags(map_id, "owner-a", tag_ids)
        # nothing bound when the limit trips
        assert store.list_map_tags(map_id, "owner-a") == []

    def test_set_map_tags_does_not_increment_revision(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        before = store.get_map(map_id, "owner-a").revision
        a = store.create_tag("owner-a", "A")
        store.set_map_tags(map_id, "owner-a", [a.tag_id])
        assert store.get_map(map_id, "owner-a").revision == before

    def test_list_map_tags_unauthorized_map(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        with pytest.raises(LookupError, match="map not found"):
            store.list_map_tags(map_id, "owner-b")


class TestRevisionUntouched:
    def test_tag_operations_do_not_increment_map_revision(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        before = store.get_map(map_id, "owner-a").revision
        tag = store.create_tag("owner-a", "A")
        store.set_map_tags(map_id, "owner-a", [tag.tag_id])
        store.update_tag("owner-a", tag.tag_id, name="B")
        store.list_map_tags(map_id, "owner-a")
        store.list_tags("owner-a")
        store.delete_tag("owner-a", tag.tag_id)
        after = store.get_map(map_id, "owner-a").revision
        assert before == after


class TestQueueSkippedItems:
    @staticmethod
    def _insert_queue(store, map_id, cursor):
        with store.connection() as db:
            db.execute(
                "INSERT INTO literature_map_jobs("
                "job_id,map_id,operation,status,step,cursor_json,counts_json,"
                "failed_units_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "qjob",
                    map_id,
                    "analysis_queue",
                    "completed",
                    "finished",
                    json.dumps(cursor),
                    json.dumps({}),
                    json.dumps([]),
                    iso_now(),
                    iso_now(),
                ),
            )

    def test_no_queue_returns_empty_skipped_items(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        queue = store.get_analysis_queue(map_id, "owner-a")
        assert queue["skipped_items"] == []
        assert "failed_items" in queue
        assert "counts" in queue

    def test_queue_skipped_items_contains_abstract_unavailable(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        cursor = {
            "items": {
                "n1": {
                    "node_id": "n1",
                    "status": "skipped",
                    "skip_reason": "MAP_ABSTRACT_UNAVAILABLE",
                    "retryable": False,
                },
                "n2": {
                    "node_id": "n2",
                    "status": "skipped",
                    "skip_reason": "MAP_FULLTEXT_UNAVAILABLE",
                    "retryable": True,
                },
                "n3": {"node_id": "n3", "status": "completed"},
            }
        }
        self._insert_queue(store, map_id, cursor)
        skipped = store.get_analysis_queue(map_id, "owner-a")["skipped_items"]
        by_node = {s["node_id"]: s for s in skipped}
        assert set(by_node) == {"n1", "n2"}
        assert by_node["n1"]["skip_reason"] == "MAP_ABSTRACT_UNAVAILABLE"
        assert by_node["n1"]["retryable"] is False
        assert by_node["n2"]["skip_reason"] == "MAP_FULLTEXT_UNAVAILABLE"
        assert by_node["n2"]["retryable"] is True
        # completed item is not reported as skipped
        assert "n3" not in by_node

    def test_skipped_item_includes_title_when_node_exists(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store, "owner-a")
        node = MapPaper.new(map_id, semantic_scholar_id="s2-x", title="Skipped Paper")
        store.add_nodes(map_id, "owner-a", [node])
        cursor = {
            "items": {
                "nX": {
                    "node_id": node.node_id,
                    "status": "skipped",
                    "skip_reason": "MAP_ABSTRACT_UNAVAILABLE",
                    "retryable": False,
                }
            }
        }
        self._insert_queue(store, map_id, cursor)
        skipped = store.get_analysis_queue(map_id, "owner-a")["skipped_items"]
        assert len(skipped) == 1
        assert skipped[0]["title"] == "Skipped Paper"
        assert skipped[0]["node_id"] == node.node_id
        assert skipped[0]["skip_reason"] == "MAP_ABSTRACT_UNAVAILABLE"
