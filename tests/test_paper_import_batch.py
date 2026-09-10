"""Task06 durable batch compensation contracts (isolated SQLite only)."""

import sqlite3

import pytest

from backend.app.paper_discovery.application.paper_import import PaperImportResult
from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchService,
    PaperImportBatchServiceError,
)
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore


def _candidate(candidate_id: str = "candidate-1") -> PaperCandidate:
    return PaperCandidate(candidate_id, "search-1", "Durable batch paper", "ccs", "CCS", year=2025)


def _service(tmp_path, importer, *, compensator=None):
    return PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "state.sqlite3"),
        importer=importer,
        compensator=compensator,
    )


def _create(service, candidate=None):
    candidate = candidate or _candidate()
    return service.create_batch(
        "search-1", [candidate.candidate_id],
        search_session=SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
        candidates=[candidate],
    )


def _capability():
    return {
        "owner": "attempt-owner",
        "token": "attempt-token",
        "document_id": "document-1",
        "stored_name": "document.pdf",
        "source_sha256": "a" * 64,
        "source_dev": 1,
        "source_ino": 2,
        "destination_collection": "papers-generation-1",
    }


def test_attempt_capability_and_snapshot_survive_restart_without_public_token(tmp_path):
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper-1", "document.pdf", "indexed"))
    batch = _create(service)
    item = service.store.get_items(batch.batch_id)[0]
    assert item.snapshot_hash and item.snapshot_json
    service.store.claim_item(item.item_id, "lease-owner")
    service.store.record_attempt_resource(item.item_id, _capability(), lease_owner="lease-owner", cleanup_status="cleanup_pending")

    reopened = PaperImportBatchStore(tmp_path / "state.sqlite3")
    restored = reopened.get_item(item.item_id)
    assert restored.attempt_owner == "attempt-owner"
    assert restored.resource_capability["document_id"] == "document-1"
    assert restored.resource_capability["destination_collection"] == "papers-generation-1"
    assert restored.to_dict().get("attempt_token") is None
    assert "attempt-token" not in restored.to_dict()
    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_import_attempts WHERE item_id=?", (item.item_id,)).fetchone()[0] == 1

    restarted = _service(tmp_path, lambda candidate, *_args: PaperImportResult(candidate["candidate_id"], "document.pdf", "indexed"))
    assert restarted._snapshots_for(batch.batch_id, None)["candidate-1"]["candidate_id"] == "candidate-1"


def test_failed_pending_retry_compensates_once_and_completed_never_reruns(tmp_path):
    calls = []
    cap = _capability()

    def importer(candidate, *_args):
        calls.append(candidate.candidate_id)
        if len(calls) == 1:
            return PaperImportResult(None, None, "failed", error_code="KB_IMPORT_FAILED", resource_capability=cap, cleanup_status="cleanup_pending")
        return PaperImportResult("paper-1", "document.pdf", "indexed")

    compensations = []
    service = _service(tmp_path, importer, compensator=lambda capability: compensations.append(capability["token"]) or "completed")
    batch = _create(service)
    item = service.run_batch(batch.batch_id).batch_id
    failed = service.store.get_items(item)[0]
    assert failed.status == "failed" and failed.cleanup_status == "cleanup_pending"
    service.retry_item(failed.item_id)
    assert service.store.get_item(failed.item_id).status == "completed"
    assert compensations == ["attempt-token"]
    service.process_item(failed.item_id)
    assert calls == ["candidate-1", "candidate-1"]


def test_cancel_and_expired_lease_keep_unknown_cleanup_pending(tmp_path):
    cap = _capability()
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", "document.pdf", "indexed"))
    batch = _create(service)
    item = service.store.get_items(batch.batch_id)[0]
    service.store.claim_item(item.item_id, "lease", now="2026-01-01T00:00:00Z", lease_seconds=1)
    service.store.record_attempt_resource(item.item_id, cap, lease_owner="lease", cleanup_status="cleanup_pending")
    cancelled = service.cancel_item(item.item_id)
    assert cancelled.status == "cancelled"
    assert cancelled.cleanup_status == "cleanup_pending"

    second = _create(_service(tmp_path / "second", lambda *_args: PaperImportResult("paper", None, "indexed")))
    other = _service(tmp_path / "second", lambda *_args: PaperImportResult("paper", None, "indexed"))
    other_item = other.store.get_items(second.batch_id)[0]
    other.store.claim_item(other_item.item_id, "dead", now="2026-01-01T00:00:00Z", lease_seconds=1)
    other.store.record_attempt_resource(other_item.item_id, cap, lease_owner="dead", cleanup_status="cleanup_pending")
    assert other.recover_expired_leases(now="2026-01-01T00:01:00Z") == 1
    assert other.store.get_item(other_item.item_id).cleanup_status == "cleanup_pending"


def test_snapshot_tamper_requires_rebuild(tmp_path):
    service = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    batch = _create(service)
    item = service.store.get_items(batch.batch_id)[0]
    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        connection.execute("UPDATE paper_import_items SET snapshot_json=? WHERE item_id=?", ('{"candidate_id":"forged","search_id":"search-1"}', item.item_id))
    restarted = _service(tmp_path, lambda *_args: PaperImportResult("paper", None, "indexed"))
    with pytest.raises(PaperImportBatchServiceError) as error:
        restarted.run_batch(batch.batch_id)
    assert error.value.code == "SNAPSHOT_REBUILD_REQUIRED"
