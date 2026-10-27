from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json

from backend.app.literature_maps.application.analysis import MapAnalysisService
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import SemanticScholarRequestResult


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, *args):
        self.calls.append((function, args))
        return None


def _queued_auxiliary_job(store, operation="preview_page", *, cursor=None):
    created = store.create_map("owner-a", topic="fuzzing")
    job = store.create_job(created.map_id, "owner-a", operation=operation)
    if cursor is not None:
        with store.transaction() as db:
            db.execute("UPDATE literature_map_jobs SET cursor_json=? WHERE job_id=?", (json.dumps(cursor), job.job_id))
    return created, job


def _queued_batch_job(store, *, map_item=None, label="batch-node"):
    created = map_item or store.create_map("owner-a", topic="fuzzing")
    seed = MapPaper.new(created.map_id, semantic_scholar_id=f"seed-{label}", title="Seed")
    node = MapPaper.new(created.map_id, semantic_scholar_id=f"paper-{label}", title="Candidate")
    store.add_nodes(created.map_id, "owner-a", [seed, node])
    job = store.create_job(created.map_id, "owner-a", operation="expand_batch")
    cursor = {
        "version": 1,
        "seed_node_id": seed.node_id,
        "preview_ids": [],
        "new_node_ids": [node.node_id],
        "items": {
            node.node_id: {
                "node_id": node.node_id,
                "status": "metadata_pending",
                "metadata_status": "pending",
                "attempts": 0,
                "error_code": None,
            }
        },
    }
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET step='metadata',cursor_json=?,counts_json=? WHERE job_id=?",
            (json.dumps(cursor), json.dumps({"added_count": 1, "existing_count": 0, "total": 1, "metadata_pending": 1, "analysis_queued": 0, "completed": 0, "failed": 0}), job.job_id),
        )
    return created, job, seed, node


def test_auxiliary_claim_is_single_owner_scoped_cas_with_private_token_and_lease(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _queued_auxiliary_job(store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: store.claim_auxiliary_job(
                    job.job_id,
                    created.map_id,
                    "owner-a",
                    operation="preview_page",
                ),
                range(2),
            )
        )

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    claimed_job, token = winners[0]
    assert token
    assert "worker_token" not in claimed_job.to_dict()
    assert store.claim_auxiliary_job(job.job_id, created.map_id, "owner-b", operation="preview_page") is None
    with store.connection() as db:
        row = db.execute("SELECT status,worker_token,lease_expires_at,attempts FROM literature_map_jobs WHERE job_id=?", (job.job_id,)).fetchone()
    assert row[0] == "running"
    assert row[1] == token
    assert row[3] == 1
    deadline = datetime.fromisoformat(row[2])
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    assert 290 <= remaining <= 300
    assert store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="expand_batch") is None
    assert store.auxiliary_job_can_write(
        job.job_id,
        created.map_id,
        "owner-b",
        operation="preview_page",
        worker_token=token,
    ) is False


def test_expired_auxiliary_token_cannot_write_or_finish_after_recovery(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _queued_auxiliary_job(store)
    claimed, old_token = store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="preview_page")
    assert claimed is not None
    with store.transaction() as db:
        db.execute("UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job.job_id,))

    recovered = store.recover_auxiliary_jobs("owner-a")

    assert [item.job_id for item in recovered] == [job.job_id]
    assert store.finish_auxiliary_job(
        job.job_id,
        created.map_id,
        "owner-a",
        operation="preview_page",
        worker_token=old_token,
        status="completed",
    ) is None
    try:
        with store.auxiliary_job_transaction(
            job.job_id,
            created.map_id,
            "owner-a",
            operation="preview_page",
            worker_token=old_token,
        ) as db:
            db.execute("UPDATE literature_maps SET name='late write' WHERE map_id=?", (created.map_id,))
    except ValueError as error:
        assert "lease" in str(error).lower()
    else:
        raise AssertionError("expired worker token unexpectedly qualified for a write")

    assert store.get_map(created.map_id, "owner-a").name == "fuzzing"
    new_claim = store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="preview_page")
    assert new_claim is not None
    assert new_claim[1] != old_token


def test_auxiliary_domain_write_rolls_back_when_lease_expires_before_finish(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _queued_auxiliary_job(store)
    claimed, token = store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="preview_page")
    assert claimed is not None

    try:
        with store.auxiliary_job_transaction(
            job.job_id,
            created.map_id,
            "owner-a",
            operation="preview_page",
            worker_token=token,
        ) as db:
            db.execute("UPDATE literature_maps SET name='late write' WHERE map_id=?", (created.map_id,))
            db.execute("UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job.job_id,))
            assert store.finish_auxiliary_job_tx(
                db,
                job.job_id,
                created.map_id,
                "owner-a",
                operation="preview_page",
                worker_token=token,
                status="completed",
            ) is None
    except ValueError as error:
        assert "lease" in str(error).lower()
    else:
        raise AssertionError("expired lease transaction unexpectedly committed")

    assert store.get_map(created.map_id, "owner-a").name == "fuzzing"
    assert store.get_job(job.job_id, created.map_id, "owner-a").status == "running"
    assert store.auxiliary_job_can_write(
        job.job_id,
        created.map_id,
        "owner-a",
        operation="preview_page",
        worker_token=token,
    ) is True


def test_auxiliary_recovery_allows_three_takeovers_then_fails_closed(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _queued_auxiliary_job(store)

    for _ in range(4):
        claimed = store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="preview_page")
        assert claimed is not None
        with store.transaction() as db:
            db.execute("UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job.job_id,))
        recovered = store.recover_auxiliary_jobs("owner-a")

    assert recovered == []
    failed = store.get_job(job.job_id, created.map_id, "owner-a")
    assert failed.status == "failed"
    assert failed.failed_units[-1]["error_code"] == "MAP_JOB_LEASE_EXHAUSTED"
    with store.connection() as db:
        row = db.execute("SELECT worker_token,lease_expires_at,attempts FROM literature_map_jobs WHERE job_id=?", (job.job_id,)).fetchone()
    assert row[0] is None and row[1] is None and row[2] == 4


def test_paused_queue_does_not_suppress_auxiliary_lease_exhaustion(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing")
    store.ensure_analysis_queue(created.map_id, "owner-a", idempotency_key="queue")
    created, job, _seed, _node = _queued_batch_job(store, map_item=created, label="lease-exhaustion")

    for attempt in range(4):
        claim = store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="expand_batch")
        assert claim is not None
        with store.transaction() as db:
            db.execute("UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job.job_id,))
        if attempt == 3:
            store.pause_analysis_queue(created.map_id, "owner-a", idempotency_key="pause-at-limit")
        recovered = store.recover_auxiliary_jobs("owner-a", map_id=created.map_id)
        if attempt < 3:
            assert [item.job_id for item in recovered] == [job.job_id]

    exhausted = store.get_job(job.job_id, created.map_id, "owner-a")
    assert recovered == []
    assert exhausted.status == "failed"
    assert exhausted.failed_units[-1]["error_code"] == "MAP_JOB_LEASE_EXHAUSTED"
    assert store.claim_auxiliary_job(job.job_id, created.map_id, "owner-a", operation="expand_batch") is None

    store.resume_analysis_queue(created.map_id, "owner-a", idempotency_key="resume-after-limit")

    assert store.get_job(job.job_id, created.map_id, "owner-a").status == "failed"
    assert store.recover_auxiliary_jobs("owner-a", map_id=created.map_id) == []


def test_recovery_routes_auxiliary_operations_to_typed_handlers_and_fails_unknown(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, page_job = _queued_auxiliary_job(store, "preview_page")
    _, batch_job, _seed, _node = _queued_batch_job(store, map_item=created, label="typed-recovery")
    unknown = store.create_job(created.map_id, "owner-a", operation="future_operation")
    executor = RecordingExecutor()
    service = LiteratureMapService(store=store, executor=executor)
    service.run_job = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("generic run_job fallback used"))

    service.recover("owner-a")

    assert [function.__name__ for function, _args in executor.calls] == ["run_preview_page", "run_expansion_batch"]
    assert executor.calls[0][1] == (page_job.job_id, "owner-a")
    assert executor.calls[1][1] == (batch_job.job_id, "owner-a")
    assert store.get_job(unknown.job_id, created.map_id, "owner-a").status == "failed"
    assert store.get_job(unknown.job_id, created.map_id, "owner-a").failed_units[-1]["error_code"] == "MAP_JOB_OPERATION_UNSUPPORTED"


def test_invalid_page_payload_and_metadata_batch_provider_failure_are_typed(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, page_job = _queued_auxiliary_job(store, "preview_page")
    _, batch_job, _seed, node = _queued_batch_job(store, map_item=created, label="provider-failure")
    service = LiteratureMapService(store=store, executor=None)
    class RateLimitedClient:
        def batch(self, identifiers, *, fields=None):
            return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_RATE_LIMITED", retryable=True)

    service.client = RateLimitedClient()

    page_result = service.run_preview_page(page_job.job_id, "owner-a")
    batch_result = service.run_expansion_batch(batch_job.job_id, "owner-a")

    assert page_result.status == "failed"
    assert batch_result.status == "partial"
    assert page_result.failed_units[-1]["error_code"] == "MAP_PREVIEW_PAGINATION_INVALID"
    assert batch_result.failed_units[-1]["error_code"] == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert batch_result.cursor["items"][node.node_id]["status"] == "metadata_failed"
    assert store.get_map(created.map_id, "owner-a").status == "generating"


def test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing")
    store.ensure_analysis_queue(created.map_id, "owner-a", idempotency_key="queue")
    store.pause_analysis_queue(created.map_id, "owner-a", idempotency_key="pause")
    _created, batch, _seed, _node = _queued_batch_job(store, map_item=created, label="resume-recovery")
    executor = RecordingExecutor()
    service = LiteratureMapService(store=store, executor=executor)
    analysis = MapAnalysisService(
        store=store,
        executor=None,
        queue_executor=None,
        auxiliary_recovery=service.recover_auxiliary_for_map,
    )

    assert store.recover_auxiliary_jobs("owner-a") == []
    assert store.get_job(batch.job_id, created.map_id, "owner-a").status == "paused"
    assert store.claim_auxiliary_job(batch.job_id, created.map_id, "owner-a", operation="expand_batch") is None

    analysis.resume_analysis_queue(created.map_id, "owner-a", idempotency_key="resume")

    assert [function.__name__ for function, _args in executor.calls] == ["run_expansion_batch"]
    assert executor.calls[0][1] == (batch.job_id, "owner-a")
    assert store.get_job(batch.job_id, created.map_id, "owner-a").status == "queued"
