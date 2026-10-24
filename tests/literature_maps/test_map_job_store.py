from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def _running_job(store):
    created, job, _ = store.create_map_with_job(
        "owner-a",
        topic="fuzzing",
        idempotency_key="request-1",
        params_hash="params-1",
    )
    claimed = store.claim_job(job.job_id, created.map_id, "owner-a")
    assert claimed is not None
    return created, claimed


def test_job_claim_and_checkpoint_are_compare_and_set(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    assert store.claim_job(job.job_id, created.map_id, "owner-a") is None
    checkpoint = store.save_unit_checkpoint(
        job.job_id,
        created.map_id,
        "owner-a",
        unit_key="discover:page:0",
        status="completed",
        payload={"accepted": 3},
    )
    assert checkpoint["status"] == "completed"
    assert store.get_unit_checkpoint(job.job_id, created.map_id, "owner-a", "discover:page:0")["payload"] == {"accepted": 3}
    assert store.completed_units(job.job_id, created.map_id, "owner-a") == {"discover:page:0"}


def test_completed_jobs_are_read_only_and_retry_is_single_cas_transition(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    completed = store.finish_job(job.job_id, created.map_id, "owner-a", status="completed", map_status="ready", event_type="completed", error_code="MAP_DONE")
    assert completed is not None and completed.status == "completed"
    assert store.job_can_write(job.job_id, created.map_id, "owner-a") is False
    stopped = store.stop_job(job.job_id, created.map_id, "owner-a")
    assert stopped is not None and stopped.status == "completed"
    failed_map = store.create_map("owner-a", topic="failed")
    failed_job = store.create_job(failed_map.map_id, "owner-a", operation="create")
    assert store.claim_job(failed_job.job_id, failed_map.map_id, "owner-a") is not None
    failed = store.update_job(failed_job.job_id, failed_map.map_id, "owner-a", status="failed", event_type="failed", error_code="MAP_PROVIDER_FAILED")
    assert failed is not None
    retried = store.retry_job(failed_job.job_id, failed_map.map_id, "owner-a")
    assert retried is not None and retried.status == "queued"
    assert store.retry_job(failed_job.job_id, failed_map.map_id, "owner-a") is None


def test_worker_writes_require_the_running_job_qualification(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    node = MapPaper.new(created.map_id, semantic_scholar_id="s2-a", title="A paper")
    store.add_nodes(created.map_id, "owner-a", [node], job_id=job.job_id)
    store.update_job(job.job_id, created.map_id, "owner-a", status="completed", event_type="completed")
    late_node = MapPaper.new(created.map_id, semantic_scholar_id="s2-b", title="Late paper")
    with pytest.raises(ValueError, match="job"):
        store.add_nodes(created.map_id, "owner-a", [late_node], job_id=job.job_id)


def test_event_error_codes_are_stable_and_not_raw_exception_text(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    store.update_job(
        job.job_id,
        created.map_id,
        "owner-a",
        status="failed",
        event_type="failed",
        error_code="RuntimeError: secret=abc",
    )
    events, _ = store.list_events(created.map_id, "owner-a")
    assert events[-1].error_code == "MAP_INTERNAL_ERROR"


def test_stop_then_late_finish_cannot_reopen_job_or_map(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    stopped = store.stop_job(job.job_id, created.map_id, "owner-a")
    assert stopped is not None and stopped.status == "stopped"
    assert store.update_job(job.job_id, created.map_id, "owner-a", status="completed", event_type="completed") is None
    assert store.finish_job(job.job_id, created.map_id, "owner-a", status="completed", map_status="ready") is None
    assert store.get_job(job.job_id, created.map_id, "owner-a").status == "stopped"
    assert store.get_map(created.map_id, "owner-a").status == "stopped"


def test_finish_then_stop_cannot_rewrite_ready_map(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)
    finished = store.finish_job(job.job_id, created.map_id, "owner-a", status="completed", map_status="ready")
    assert finished is not None and finished.status == "completed"
    assert store.stop_job(job.job_id, created.map_id, "owner-a").status == "completed"
    assert store.get_map(created.map_id, "owner-a").status == "ready"


def test_stop_and_finish_race_has_one_consistent_terminal_outcome(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created, job = _running_job(store)

    def stop():
        return store.stop_job(job.job_id, created.map_id, "owner-a")

    def finish():
        return store.finish_job(job.job_id, created.map_id, "owner-a", status="completed", map_status="ready")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda action: action(), (stop, finish)))
    final_job = store.get_job(job.job_id, created.map_id, "owner-a")
    final_map = store.get_map(created.map_id, "owner-a")
    assert final_job.status in {"stopped", "completed"}
    assert (final_job.status, final_map.status) in {("stopped", "stopped"), ("completed", "ready")}
