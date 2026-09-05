import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.domain.paper_import_batch import (
    BATCH_COMPLETED,
    BATCH_FAILED,
    BATCH_WAITING_LOGIN,
    ITEM_COMPLETED,
    ITEM_DOWNLOADING,
    ITEM_FAILED,
    ITEM_INDEXING,
    ITEM_VALIDATING,
    ITEM_WAITING_LOGIN,
    PaperImportItem,
)
from backend.app.services.paper_import_batch_store import (
    IMPORT_INTERRUPTED,
    INVALID_STATE_TRANSITION,
    PaperImportBatchStore,
    PaperImportBatchStoreError,
)


def _store(tmp_path):
    return PaperImportBatchStore(tmp_path / "state.sqlite3")


def test_create_batch_is_persistent_and_counts_are_aggregated(tmp_path):
    store = _store(tmp_path)
    batch = store.create_batch("search-1", ["c1", "c2"])
    assert batch.total_count == 2
    assert batch.completed_count == 0
    assert [item.candidate_id for item in store.get_items(batch.batch_id)] == ["c1", "c2"]
    reopened = _store(tmp_path)
    assert reopened.get_batch(batch.batch_id).total_count == 2


def test_state_machine_uses_compare_and_set_and_login_resume(tmp_path):
    store = _store(tmp_path)
    batch = store.create_batch("search", ["candidate"])
    item = store.get_items(batch.batch_id)[0]
    store.claim_item(item.item_id, "worker", now="2026-01-01T00:00:00Z")
    assert store.get_item(item.item_id).status == ITEM_DOWNLOADING
    with pytest.raises(PaperImportBatchStoreError) as error:
        store.transition_item(item.item_id, ITEM_INDEXING, expected_state=ITEM_DOWNLOADING)
    assert error.value.code == INVALID_STATE_TRANSITION
    store.transition_item(item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING, lease_owner="worker", now="2026-01-01T00:01:00Z")
    assert store.get_batch(batch.batch_id).status == BATCH_WAITING_LOGIN
    store.resume_item(item.item_id, "worker", now="2026-01-01T00:02:00Z")
    store.transition_item(item.item_id, ITEM_VALIDATING, expected_state=ITEM_DOWNLOADING, lease_owner="worker", now="2026-01-01T00:03:00Z")
    store.transition_item(item.item_id, ITEM_INDEXING, expected_state=ITEM_VALIDATING, lease_owner="worker", now="2026-01-01T00:04:00Z")
    store.transition_item(item.item_id, ITEM_COMPLETED, expected_state=ITEM_INDEXING, lease_owner="worker", now="2026-01-01T00:05:00Z")
    assert store.get_batch(batch.batch_id).status == BATCH_COMPLETED


def test_retry_cancel_and_recovery_are_constrained(tmp_path):
    store = _store(tmp_path)
    batch = store.create_batch("search", ["c1", "c2"])
    first, second = store.get_items(batch.batch_id)
    store.claim_item(first.item_id, "w", now="2026-01-01T00:00:00Z", lease_seconds=10)
    store.recover_expired_leases(now="2026-01-01T00:01:00Z")
    assert store.get_item(first.item_id).error_code == IMPORT_INTERRUPTED
    assert store.retry_item(first.item_id)
    assert store.cancel_item(second.item_id)
    assert store.get_item(second.item_id).status == "cancelled"
    assert store.cancel_item(first.item_id)
    with pytest.raises(PaperImportBatchStoreError):
        store.cancel_item(first.item_id)
    # A cancelled item is terminal and cannot be claimed again; use a fresh
    # item to cover the failed terminal batch aggregation below.
    third_batch = store.create_batch("search", ["c3"])
    third = store.get_items(third_batch.batch_id)[0]
    store.claim_item(third.item_id, "w", now="2026-01-01T00:02:00Z")
    store.mark_failed(third.item_id, "DOWNLOAD_FAILED", lease_owner="w", now="2026-01-01T00:02:01Z")
    assert store.get_batch(third_batch.batch_id).status == BATCH_FAILED


def test_batch_limit_and_identity_uniqueness(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(PaperImportBatchStoreError):
        store.create_batch("search", [str(i) for i in range(21)])
    store.create_batch("search", [PaperImportItem("i1", "x", "c1", doi="10/example")])
    with pytest.raises(sqlite3.IntegrityError):
        store.create_batch("search", [PaperImportItem("i2", "y", "c2", doi="10/example")])


def test_idempotency_key_returns_existing_batch(tmp_path):
    store = _store(tmp_path)
    first = store.create_batch("search", ["c1"], idempotency_key="same")
    second = store.create_batch("search", ["c2"], idempotency_key="same")
    assert second.batch_id == first.batch_id
    assert [item.candidate_id for item in store.get_items(first.batch_id)] == ["c1"]


def test_deduplicates_before_hard_limit_and_constructor_cannot_raise_limit(tmp_path):
    store = PaperImportBatchStore(tmp_path / "state.sqlite3", max_items=21)
    values = [f"c{i}" for i in range(20)] + ["c0"]
    assert store.create_batch("search", values).total_count == 20
    with pytest.raises(PaperImportBatchStoreError) as error:
        store.create_batch("search-2", [f"c{i}" for i in range(21)])
    assert error.value.code == "BATCH_LIMIT_EXCEEDED"


def test_failed_and_cancelled_identities_are_released_completed_is_not(tmp_path):
    store = _store(tmp_path)
    failed = store.create_batch("search", [PaperImportItem("f", "b1", "f", doi="10/reusable")], idempotency_key="reuse")
    failed_item = store.get_items(failed.batch_id)[0]
    store.claim_item(failed_item.item_id, "worker", now="2026-01-01T00:00:00Z")
    store.mark_failed(failed_item.item_id, "FAILED", lease_owner="worker", now="2026-01-01T00:01:00Z")
    replacement = store.create_batch("search", [PaperImportItem("r", "b2", "r", doi="10/reusable")], idempotency_key="reuse")
    assert replacement.batch_id != failed.batch_id

    cancelled = store.create_batch("search", [PaperImportItem("c", "b3", "c", dblp_key="conf/c")], idempotency_key="cancel")
    store.cancel_item(store.get_items(cancelled.batch_id)[0].item_id)
    assert store.create_batch("search", [PaperImportItem("c2", "b4", "c2", dblp_key="conf/c")], idempotency_key="cancel").batch_id != cancelled.batch_id

    done = store.create_batch("search", [PaperImportItem("d", "b5", "d", doi="10/completed")], idempotency_key="done")
    done_item = store.get_items(done.batch_id)[0]
    store.claim_item(done_item.item_id, "worker", now="2026-01-01T00:00:00Z")
    store.transition_item(done_item.item_id, ITEM_VALIDATING, expected_state=ITEM_DOWNLOADING, lease_owner="worker", now="2026-01-01T00:01:00Z")
    store.transition_item(done_item.item_id, ITEM_INDEXING, expected_state=ITEM_VALIDATING, lease_owner="worker", now="2026-01-01T00:02:00Z")
    store.transition_item(done_item.item_id, ITEM_COMPLETED, expected_state=ITEM_INDEXING, lease_owner="worker", paper_id="paper-done", now="2026-01-01T00:03:00Z")
    assert store.create_batch("search", ["other"], idempotency_key="done").batch_id == done.batch_id
    with pytest.raises(sqlite3.IntegrityError):
        store.create_batch("search", [PaperImportItem("d2", "b6", "d2", doi="10/completed")])


def test_null_title_components_are_part_of_identity(tmp_path):
    store = _store(tmp_path)
    store.create_batch("search", [PaperImportItem("one", "b1", "one", normalized_title="same")])
    with pytest.raises(sqlite3.IntegrityError):
        store.create_batch("search", [PaperImportItem("two", "b2", "two", normalized_title="same")])


def test_old_lease_owner_cannot_transition_or_fail_after_reclaim(tmp_path):
    store = _store(tmp_path)
    batch = store.create_batch("search", ["candidate"])
    item = store.get_items(batch.batch_id)[0]
    store.claim_item(item.item_id, "old", now="2026-01-01T00:00:00Z", lease_seconds=1)
    assert store.recover_expired_leases(now="2026-01-01T00:00:02Z") == 1
    store.retry_item(item.item_id)
    store.claim_item(item.item_id, "new", now="2026-01-01T00:00:03Z")
    with pytest.raises(PaperImportBatchStoreError):
        store.transition_item(item.item_id, ITEM_VALIDATING, expected_state=ITEM_DOWNLOADING, lease_owner="old", now="2026-01-01T00:00:03Z")
    with pytest.raises(PaperImportBatchStoreError):
        store.mark_failed(item.item_id, "OLD", lease_owner="old", now="2026-01-01T00:00:03Z")
    with pytest.raises(PaperImportBatchStoreError):
        store.mark_failed(item.item_id, "MISSING_OWNER", now="2026-01-01T00:00:03Z")


def test_concurrent_claim_retry_resume_and_recovery_return_stable_results(tmp_path):
    store = _store(tmp_path)

    def outcomes(function):
        with ThreadPoolExecutor(max_workers=8) as pool:
            def run(index):
                try:
                    return function(index)
                except PaperImportBatchStoreError as error:
                    return error
            return list(pool.map(run, range(8)))

    claim_batch = store.create_batch("claim", ["candidate"])
    claim_item = store.get_items(claim_batch.batch_id)[0]
    claim_results = outcomes(lambda index: store.claim_item(claim_item.item_id, f"worker-{index}"))
    assert sum(result is True for result in claim_results) == 1
    assert all(result is True or isinstance(result, PaperImportBatchStoreError) for result in claim_results)

    retry_batch = store.create_batch("retry", ["candidate"])
    retry_item = store.get_items(retry_batch.batch_id)[0]
    store.claim_item(retry_item.item_id, "worker", now="2026-01-01T00:00:00Z")
    store.mark_failed(retry_item.item_id, "FAILED", lease_owner="worker", now="2026-01-01T00:01:00Z")
    retry_results = outcomes(lambda _index: store.retry_item(retry_item.item_id))
    assert sum(result is True for result in retry_results) == 1
    assert all(result is True or isinstance(result, PaperImportBatchStoreError) for result in retry_results)

    resume_batch = store.create_batch("resume", ["candidate"])
    resume_item = store.get_items(resume_batch.batch_id)[0]
    store.claim_item(resume_item.item_id, "worker")
    store.transition_item(resume_item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING, lease_owner="worker")
    resume_results = outcomes(lambda index: store.resume_item(resume_item.item_id, f"worker-{index}"))
    assert sum(result is True for result in resume_results) == 1
    assert all(result is True or isinstance(result, PaperImportBatchStoreError) for result in resume_results)

    recover_batch = store.create_batch("recover", ["candidate"])
    recover_item = store.get_items(recover_batch.batch_id)[0]
    store.claim_item(recover_item.item_id, "worker", now="2026-01-01T00:00:00Z", lease_seconds=1)
    recovery_results = outcomes(lambda _index: store.recover_expired_leases(now="2026-01-01T00:00:02Z"))
    assert sum(result == 1 for result in recovery_results) == 1
    assert sum(result == 0 for result in recovery_results) == 7


def test_mixed_state_aggregation_and_lease_renewal_boundaries(tmp_path):
    store = _store(tmp_path)
    batch = store.create_batch("search", [f"c{i}" for i in range(5)])
    completed, waiting, failed, cancelled, queued = store.get_items(batch.batch_id)
    store.claim_item(completed.item_id, "w", now="2026-01-01T00:00:00Z")
    store.transition_item(completed.item_id, ITEM_VALIDATING, expected_state=ITEM_DOWNLOADING, lease_owner="w", now="2026-01-01T00:01:00Z")
    store.transition_item(completed.item_id, ITEM_INDEXING, expected_state=ITEM_VALIDATING, lease_owner="w", now="2026-01-01T00:02:00Z")
    store.transition_item(completed.item_id, ITEM_COMPLETED, expected_state=ITEM_INDEXING, lease_owner="w", now="2026-01-01T00:03:00Z")
    store.claim_item(waiting.item_id, "w", now="2026-01-01T00:00:00Z")
    store.transition_item(waiting.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING, lease_owner="w", now="2026-01-01T00:01:00Z")
    store.claim_item(failed.item_id, "w", now="2026-01-01T00:00:00Z")
    store.mark_failed(failed.item_id, "FAILED", lease_owner="w", now="2026-01-01T00:01:00Z")
    store.cancel_item(cancelled.item_id)
    status = store.get_batch(batch.batch_id)
    assert (status.total_count, status.completed_count, status.failed_count, status.waiting_login_count, status.cancelled_count) == (5, 1, 1, 1, 1)
    assert store.renew_lease(queued.item_id, "w", now="2026-01-01T00:00:00Z") is False

    lease_batch = store.create_batch("lease", ["candidate"])
    lease_item = store.get_items(lease_batch.batch_id)[0]
    store.claim_item(lease_item.item_id, "w", now="2026-01-01T00:00:00Z")
    assert store.renew_lease(lease_item.item_id, "w", now="2026-01-01T00:04:59Z") is False
    assert store.renew_lease(lease_item.item_id, "w", now="2026-01-01T00:05:00Z") is True


def test_schema_metadata_and_missing_columns_fail_fast(tmp_path):
    path = tmp_path / "state.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE paper_import_schema_meta(bad TEXT)")
    with pytest.raises(RuntimeError, match="malformed paper_import_schema_meta"):
        _store(tmp_path)

    path = tmp_path / "missing.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE paper_import_schema_meta(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO paper_import_schema_meta VALUES(1)")
        connection.execute("CREATE TABLE paper_import_batches(batch_id TEXT PRIMARY KEY, search_id TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    with pytest.raises(RuntimeError, match="paper_import_batches missing columns: idempotency_key"):
        PaperImportBatchStore(path)


def test_existing_invalid_state_fails_fast_before_schema_repair(tmp_path):
    path = tmp_path / "invalid-state.sqlite3"
    store = PaperImportBatchStore(path)
    batch = store.create_batch("search", ["candidate"])
    item = store.get_items(batch.batch_id)[0]
    with sqlite3.connect(path) as connection:
        # SQLite's test-only switch lets us model a corrupt pre-existing row
        # while retaining the production CHECK constraint in the table.
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE paper_import_items SET state='bogus' WHERE item_id=?", (item.item_id,))

    with pytest.raises(RuntimeError, match="contains invalid state values"):
        PaperImportBatchStore(path)


def test_existing_tables_require_primary_key_and_foreign_key_constraints(tmp_path):
    path = tmp_path / "invalid-constraints.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE paper_import_schema_meta(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO paper_import_schema_meta VALUES(1)")
        connection.execute(
            """CREATE TABLE paper_import_batches(
                batch_id TEXT NOT NULL,
                search_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','running','waiting_login','partial_success','completed','failed','cancelled')),
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE paper_import_items(
                item_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','downloading','waiting_login','validating','indexing','completed','failed','cancelled')),
                stored_name TEXT,
                paper_id TEXT,
                error_code TEXT,
                error_message TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                lease_owner TEXT,
                lease_expires_at TEXT,
                lease_renewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                doi TEXT,
                dblp_key TEXT,
                normalized_title TEXT,
                year INTEGER,
                conference_id TEXT,
                idempotency_key TEXT,
                UNIQUE(batch_id, candidate_id)
            )"""
        )

    with pytest.raises(RuntimeError, match="paper_import_batches.batch_id"):
        PaperImportBatchStore(path)
