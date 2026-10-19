import pytest

from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def test_preview_apply_rejects_stale_revision_without_writing_nodes(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, executor=None)
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    preview = service.create_preview(item.map_id, "owner-a", kind="topic", idempotency_key="p")
    store.update_map_details(item.map_id, "owner-a", expected_revision=0, name="changed")

    with pytest.raises(ValueError, match="revision conflict"):
        service.apply_preview(
            item.map_id,
            preview.preview_id,
            "owner-a",
            expected_revision=0,
            selected_candidate_ids=[],
            idempotency_key="a",
        )
    assert store.list_nodes(item.map_id, "owner-a") == []
