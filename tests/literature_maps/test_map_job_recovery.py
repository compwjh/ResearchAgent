import pytest

from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import SemanticScholarRequestResult


class InvalidClient:
    def search_bulk(self, query, *, limit=20, fields=None):
        raise ValueError("provider payload is malformed")


class RetryClient:
    def __init__(self):
        self.search_calls = 0
        self.graph_calls = 0

    def search_bulk(self, query, *, limit=20, fields=None):
        self.search_calls += 1
        return SemanticScholarRequestResult(payload={
            "data": [{
                "paperId": f"s2-{index}",
                "title": "Fuzzing vulnerability discovery",
                "abstract": "fuzzing",
                "year": 2024,
            } for index in range(20)]
        })

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        self.graph_calls += 1
        return SemanticScholarRequestResult(code="SEMANTIC_SCHOLAR_RATE_LIMITED", retryable=True)


def test_value_error_finishes_job_with_safe_error_event(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, client=InvalidClient(), executor=None)
    created = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)

    completed = service.run_job(created.job.job_id, "owner-a")
    events, _ = store.list_events(created.map.map_id, "owner-a")

    assert completed is not None
    assert completed.status == "failed"
    assert completed.failed_units[-1]["error_code"] == "MAP_JOB_INVALID_INPUT"
    assert events[-1].error_code == "MAP_JOB_INVALID_INPUT"


def test_retry_resumes_persisted_nodes_without_repeating_discovery(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = RetryClient()
    service = LiteratureMapService(
        store=store,
        client=client,
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    created = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)
    first = service.run_job(created.job.job_id, "owner-a")
    assert first is not None and first.status == "partial"
    assert client.search_calls == 1


def test_reference_budget_is_persisted_across_retries(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = RetryClient()
    service = LiteratureMapService(
        store=store,
        client=client,
        executor=None,
        embedder=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    created = service.create_map(owner_id="owner-a", topic="fuzzing", requested_count=20)
    service.run_job(created.job.job_id, "owner-a")
    assert store.get_job(created.job.job_id, created.map.map_id, "owner-a").counts["provider_request_count"] == 21

    for expected_total in (41, 60):
        service.retry_job(created.map.map_id, created.job.job_id, "owner-a")
        service.run_job(created.job.job_id, "owner-a")
        job = store.get_job(created.job.job_id, created.map.map_id, "owner-a")
        assert job is not None
        assert job.counts["provider_request_count"] == expected_total

    calls_at_budget = client.graph_calls
    service.retry_job(created.map.map_id, created.job.job_id, "owner-a")
    service.run_job(created.job.job_id, "owner-a")
    job = store.get_job(created.job.job_id, created.map.map_id, "owner-a")
    assert job is not None and job.counts["provider_request_count"] == 60
    assert client.graph_calls == calls_at_budget
    assert any(item["error_code"] == "MAP_GRAPH_BUDGET_EXCEEDED" for item in job.failed_units)

    with pytest.raises(ValueError, match="MAP_NO_RETRYABLE_UNITS"):
        service.retry_job(created.map.map_id, created.job.job_id, "owner-a")

    assert client.search_calls == 1


def test_stop_of_completed_job_is_idempotent(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    created = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    job = store.create_job(created.map_id, "owner-a", operation="create")
    assert store.claim_job(job.job_id, created.map_id, "owner-a") is not None
    assert store.finish_job(job.job_id, created.map_id, "owner-a", status="completed", map_status="ready", step="finished") is not None
    service = LiteratureMapService(store=store, executor=None)

    stopped = service.stop_job(created.map_id, job.job_id, "owner-a")

    assert stopped.status == "completed"
    assert store.get_map(created.map_id, "owner-a").status == "ready"


def test_retry_requeues_only_retryable_failed_units(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    service = LiteratureMapService(store=store, executor=None)
    created = store.create_map("owner-a", topic="fuzzing")
    job = store.create_job(created.map_id, "owner-a", operation="create")
    assert store.claim_job(job.job_id, created.map_id, "owner-a") is not None
    failed = store.update_job(
        job.job_id,
        created.map_id,
        "owner-a",
        status="failed",
        failed_units=[
            {"unit": "metadata", "error_code": "SEMANTIC_SCHOLAR_RATE_LIMITED", "retryable": True},
            {"unit": "references:node-a", "error_code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False},
        ],
        event_type="failed",
    )
    assert failed is not None

    retried = service.retry_job(created.map_id, job.job_id, "owner-a")

    assert retried.status == "queued"
    assert retried.failed_units == [{"unit": "metadata", "error_code": "SEMANTIC_SCHOLAR_RATE_LIMITED", "retryable": True}]
