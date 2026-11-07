"""Store-level tests: deleting a map must drop its tag bindings.

The tag-binding table is newer than ``delete_map``; a soft delete only
touches the ``literature_maps`` row, so without an explicit cleanup the
binding rows survive as orphans.  Orphans would inflate the
``unbound_maps`` count reported by ``delete_tag`` and keep ``list_map_tags``
returning tags for an already-deleted map.  These tests pin that contract.
"""

import pytest

from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def _store(tmp_path):
    return LiteratureMapStore(tmp_path / "maps.sqlite3")


def _map(store, owner="owner-a", name="Fuzzing"):
    return store.create_map(owner, topic="fuzzing", name=name).map_id


def _binding_count(store, map_id):
    with store.connection() as db:
        return db.execute(
            "SELECT COUNT(*) FROM literature_map_tag_bindings WHERE map_id=?",
            (map_id,),
        ).fetchone()[0]


class TestDeleteMapClearsTagBindings:
    def test_delete_map_removes_its_tag_bindings_but_keeps_the_tag(self, tmp_path):
        store = _store(tmp_path)
        map_id = _map(store)
        tag = store.create_tag("owner-a", "Methods", "#111111")
        store.set_map_tags(map_id, "owner-a", [tag.tag_id])
        assert _binding_count(store, map_id) == 1

        assert store.delete_map(map_id, "owner-a") is True

        assert _binding_count(store, map_id) == 0
        # Deleting the map must not delete the tag itself.
        assert [t.tag_id for t in store.list_tags("owner-a")] == [tag.tag_id]
        with pytest.raises(LookupError, match="map not found"):
            store.list_map_tags(map_id, "owner-a")

    def test_delete_map_leaves_bindings_of_other_maps_intact(self, tmp_path):
        store = _store(tmp_path)
        doomed = _map(store, name="Doomed")
        kept = _map(store, name="Kept")
        tag = store.create_tag("owner-a", "Methods", "#111111")
        store.set_map_tags(doomed, "owner-a", [tag.tag_id])
        store.set_map_tags(kept, "owner-a", [tag.tag_id])

        assert store.delete_map(doomed, "owner-a") is True

        assert _binding_count(store, doomed) == 0
        assert _binding_count(store, kept) == 1
        assert store.list_map_tags(kept, "owner-a") == [
            {"tag_id": tag.tag_id, "name": "Methods", "color": "#111111"}
        ]

    def test_delete_tag_unbound_maps_excludes_already_deleted_maps(self, tmp_path):
        store = _store(tmp_path)
        alive = _map(store, name="Alive")
        deleted = _map(store, name="Deleted")
        tag = store.create_tag("owner-a", "Methods", "#111111")
        store.set_map_tags(alive, "owner-a", [tag.tag_id])
        store.set_map_tags(deleted, "owner-a", [tag.tag_id])

        assert store.delete_map(deleted, "owner-a") is True

        # Only the still-live map counts as unbound; the tombstoned map must
        # not inflate the number the API surfaces to the user.
        assert store.delete_tag("owner-a", tag.tag_id) == 1
        assert store.list_tags("owner-a") == []
