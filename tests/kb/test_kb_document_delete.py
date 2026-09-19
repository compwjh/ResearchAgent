from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
)


def _document(tmp_path: Path):
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    result = application.create_uploaded_document(
        "delete.md",
        "text/markdown",
        b"# delete me\n",
        meta_path=meta,
        papers_dir=papers,
    )
    document = result["document"]
    finalizer = FinalizeBundleStore(tmp_path)
    finalizer.stage(
        "generation-test",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    finalizer.commit("generation-test")
    return document, meta, papers


def test_partial_vector_delete_is_pending_without_source_or_metadata_write(tmp_path):
    document, meta, papers = _document(tmp_path)
    source = papers / document["stored_name"]
    before_meta = meta.read_bytes()

    with patch.object(application.GenerationBoundIndexPort, "delete_document", side_effect=RuntimeError("vector unavailable")):
        result = application.delete_document(
            document["document_id"],
            meta_path=meta,
            papers_dir=papers,
            manifest_root=tmp_path / "data" / "kb",
            destination_collection="papers_rebuild_live",
        )

    assert result == {
        "document_id": document["document_id"],
        "status": "DELETE_PENDING",
        "error_code": "DELETE_PENDING",
        "tombstoned": False,
    }
    assert source.exists()
    assert meta.read_bytes() == before_meta
    assert not (tmp_path / "data" / "kb" / "tombstones").exists()


def test_delete_retry_is_idempotent_and_tombstone_owner_scoped(tmp_path):
    document, meta, papers = _document(tmp_path)
    manifest_root = tmp_path / "data" / "kb"

    original_tombstone = InspectionManifestStore.tombstone
    attempts = {"count": 0}

    def fail_after_first(self, document_id, chunker, *, reason, owner):
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise application.ManifestStoreError("TOMBSTONE_PENDING", status=503)
        return original_tombstone(self, document_id, chunker, reason=reason, owner=owner)

    with patch.object(application.GenerationBoundIndexPort, "delete_document", return_value=None), patch.object(
        InspectionManifestStore, "tombstone", new=fail_after_first
    ):
        pending = application.delete_document(
            document["document_id"],
            meta_path=meta,
            papers_dir=papers,
            manifest_root=manifest_root,
            destination_collection="papers_rebuild_live",
        )
    assert pending["status"] == "DELETE_PENDING"
    assert pending["tombstoned"] is True
    assert (manifest_root / "tombstones" / f"{document['document_id']}.json").exists()
    assert (papers / document["stored_name"]).exists()

    with patch.object(application.GenerationBoundIndexPort, "delete_document", return_value=None):
        completed = application.delete_document(
            document["document_id"],
            meta_path=meta,
            papers_dir=papers,
            manifest_root=manifest_root,
            destination_collection="papers_rebuild_live",
        )
    assert completed["status"] == "completed"
    assert completed["deleted"]["source"] is True
    assert not (papers / document["stored_name"]).exists()
    assert application.load_papers_strict(meta) == []
    tombstone = (manifest_root / "tombstones" / f"{document['document_id']}.json").read_text()
    assert '"owner": "document-api"' in tombstone


def test_tombstone_rejects_a_different_owner(tmp_path):
    document, _meta, _papers = _document(tmp_path)
    store = InspectionManifestStore(tmp_path / "data" / "kb")
    store.tombstone(document["document_id"], "v1", reason="document_deleted", owner="document-api")
    with pytest.raises(application.ManifestStoreError) as error:
        store.tombstone(document["document_id"], "v2", reason="retry", owner="other-owner")
    assert error.value.code == "TOMBSTONE_OWNER_MISMATCH"
