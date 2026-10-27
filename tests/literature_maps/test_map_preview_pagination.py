from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_literature_maps
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarGraphPage,
    SemanticScholarMetadata,
    SemanticScholarRequestResult,
)


PAGINATION = {"version": 1, "page_size": 50, "max_candidates": 500}


class ScriptedGraphClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self.after_request = None

    def graph_edges(self, paper_id, relation, *, limit=20, offset=0, fields=None):
        self.calls.append((paper_id, relation, limit, offset))
        if self.after_request is not None:
            self.after_request()
        response = self.pages.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            return SemanticScholarRequestResult(code=response, retryable=True)
        items, next_offset, total = response
        return SemanticScholarRequestResult(
            graph_page=SemanticScholarGraphPage(
                relation,
                paper_id,
                tuple(items),
                offset,
                next_offset,
                total,
            )
        )


def _metadata(identifier: str, title: str | None = None):
    return SemanticScholarMetadata(identifier, title or identifier)


def _pagination_service(tmp_path, pages):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    client = ScriptedGraphClient(pages)
    service = LiteratureMapService(store=store, client=client, executor=None)
    map_item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    seed = MapPaper.new(map_item.map_id, semantic_scholar_id="s2-seed", title="Seed")
    store.add_nodes(map_item.map_id, "owner-a", [seed])
    preview = service.create_preview(
        map_item.map_id,
        "owner-a",
        kind="references",
        node_id=seed.node_id,
        idempotency_key="create-preview",
        pagination=PAGINATION,
    )
    return store, service, client, map_item, seed, preview


def _run_page(service, store, preview, owner="owner-a"):
    current, job = service.get_preview(preview.map_id, preview.preview_id, owner)
    return service.run_preview_page(job.job_id, owner)


def test_preview_pages_use_server_cursor_and_dedupe_even_when_page_is_empty(tmp_path):
    client_pages = [
        ([_metadata("s2-paper-a")], 50, None),
        ([_metadata("s2-paper-a", "Duplicate"), _metadata("s2-paper-b")], 100, 240),
        ([], 150, 240),
        ([], None, 240),
    ]
    store, service, client, map_item, seed, preview = _pagination_service(tmp_path, client_pages)

    assert preview.preview_revision == 1
    assert preview.pagination["state"] == "loading"
    assert preview.pagination["page_size"] == 50
    assert _run_page(service, store, preview).status == "completed"
    current, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert current.preview_revision == 2
    assert current.pagination["loaded_count"] == 1
    assert current.pagination["total"] is None
    assert current.pagination["has_more"] is True
    assert current.pagination["next_cursor"] == 50
    assert len(current.candidates) == 1

    command = service.load_more_preview(
        map_item.map_id,
        current.preview_id,
        "owner-a",
        expected_preview_revision=2,
        retry_failed=False,
        idempotency_key="next-page-1",
    )
    assert command["preview_revision"] == 3
    replay = service.load_more_preview(
        map_item.map_id,
        current.preview_id,
        "owner-a",
        expected_preview_revision=2,
        retry_failed=False,
        idempotency_key="next-page-1",
    )
    assert replay == command
    with pytest.raises(ValueError, match="MAP_IDEMPOTENCY_CONFLICT"):
        service.load_more_preview(
            map_item.map_id,
            current.preview_id,
            "owner-a",
            expected_preview_revision=3,
            retry_failed=False,
            idempotency_key="next-page-1",
        )
    assert _run_page(service, store, preview).status == "completed"
    current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert current.preview_revision == 4
    assert current.pagination["loaded_count"] == 2
    assert current.pagination["next_cursor"] == 100
    assert [call[2:] for call in client.calls] == [(50, 0), (50, 50)]

    for expected_revision in (4, 6):
        service.load_more_preview(
            map_item.map_id,
            current.preview_id,
            "owner-a",
            expected_preview_revision=expected_revision,
            retry_failed=False,
            idempotency_key=f"next-page-{expected_revision}",
        )
        assert _run_page(service, store, preview).status == "completed"
        current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert current.pagination["state"] == "exhausted"
    assert current.pagination["has_more"] is False
    assert current.pagination["total"] == 240
    assert [call[2:] for call in client.calls] == [(50, 0), (50, 50), (50, 100), (50, 150)]


def test_failed_page_preserves_candidates_and_only_explicit_retry_reuses_failed_cursor(tmp_path):
    store, service, client, map_item, seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-first")], 50, 120), "SEMANTIC_SCHOLAR_RATE_LIMITED", ([_metadata("s2-second")], 100, 120)],
    )
    _run_page(service, store, preview)
    current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=current.preview_revision, retry_failed=False, idempotency_key="load-fails")
    _run_page(service, store, preview)
    failed, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert failed.pagination["state"] == "failed"
    assert failed.pagination["failed_cursor"] == 50
    assert failed.pagination["next_cursor"] == 50
    assert failed.pagination["last_error"] == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert failed.pagination["loaded_count"] == 1
    assert len(failed.candidates) == 1
    with pytest.raises(ValueError, match="MAP_PREVIEW_RETRY_REQUIRED"):
        service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=failed.preview_revision, retry_failed=False, idempotency_key="wrong-retry")
    with pytest.raises(ValueError, match="MAP_PREVIEW_RETRY_REQUIRED"):
        service.retry_job(map_item.map_id, job.job_id, "owner-a")

    service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=failed.preview_revision, retry_failed=True, idempotency_key="retry-page")
    _run_page(service, store, preview)
    retried, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert retried.pagination["state"] == "ready"
    assert retried.pagination["failed_cursor"] is None
    assert retried.pagination["next_cursor"] == 100
    assert retried.pagination["loaded_count"] == 2
    assert [call[3] for call in client.calls] == [0, 50, 50]


def test_repeated_source_cursor_fails_without_advancing_or_losing_prior_candidates(tmp_path):
    store, service, client, map_item, seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-first")], 50, None), ([_metadata("s2-second")], 50, None)],
    )
    _run_page(service, store, preview)
    ready, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=ready.preview_revision, retry_failed=False, idempotency_key="cycle")
    _run_page(service, store, preview)
    failed, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert failed.pagination["state"] == "failed"
    assert failed.pagination["last_error"] == "SEMANTIC_SCHOLAR_CURSOR_CYCLE"
    assert failed.pagination["next_cursor"] == 50
    assert failed.pagination["failed_cursor"] == 50
    assert failed.pagination["loaded_count"] == 1
    assert [candidate["identity_key"] for candidate in failed.candidates] == ["semantic_scholar:s2-first"]
    bad_page_cache_key = service._request_cache_key(
        provider="semantic_scholar",
        operation="references",
        identifier="s2-seed",
        filters={"limit": 50},
        page=50,
    )
    assert store.get_request_cache(bad_page_cache_key) is None


def test_explicit_retry_bypasses_existing_bad_page_cache_and_refreshes_only_that_page(tmp_path):
    store, service, client, map_item, _seed, preview = _pagination_service(
        tmp_path,
        [
            ([_metadata("s2-first")], 50, None),
            ([_metadata("s2-repaired")], 100, None),
        ],
    )
    _run_page(service, store, preview)
    ready, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    cache_key = service._request_cache_key(
        provider="semantic_scholar",
        operation="references",
        identifier="s2-seed",
        filters={"limit": 50},
        page=50,
    )
    bad_page = SemanticScholarGraphPage(
        "references",
        "s2-seed",
        (_metadata("s2-cached-bad"),),
        50,
        50,
        None,
    )
    assert store.put_request_cache(
        cache_key,
        service._graph_page_payload(bad_page),
        ttl_seconds=86400,
        status="success",
    )

    service.load_more_preview(
        map_item.map_id,
        preview.preview_id,
        "owner-a",
        expected_preview_revision=ready.preview_revision,
        retry_failed=False,
        idempotency_key="bad-cached-page",
    )
    _run_page(service, store, preview)
    failed, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert failed.pagination["state"] == "failed"
    assert failed.pagination["last_error"] == "SEMANTIC_SCHOLAR_CURSOR_CYCLE"
    assert [call[3] for call in client.calls] == [0]
    assert store.get_request_cache(cache_key)["next_offset"] == 50

    service.load_more_preview(
        map_item.map_id,
        preview.preview_id,
        "owner-a",
        expected_preview_revision=failed.preview_revision,
        retry_failed=True,
        idempotency_key="retry-bad-cache",
    )
    assert store.get_request_cache(cache_key) is None
    _run_page(service, store, preview)
    recovered, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert recovered.pagination["state"] == "ready"
    assert recovered.pagination["next_cursor"] == 100
    assert recovered.pagination["loaded_count"] == 2
    assert [candidate["identity_key"] for candidate in recovered.candidates] == [
        "semantic_scholar:s2-first",
        "semantic_scholar:s2-repaired",
    ]
    assert [call[3] for call in client.calls] == [0, 50]
    refreshed_cache = store.get_request_cache(cache_key)
    assert refreshed_cache["next_offset"] == 100
    first_page_cache_key = service._request_cache_key(
        provider="semantic_scholar",
        operation="references",
        identifier="s2-seed",
        filters={"limit": 50},
        page=0,
    )
    assert store.get_request_cache(first_page_cache_key)["next_offset"] == 50


def test_expired_auxiliary_token_cannot_persist_response_candidates_or_cursor(tmp_path):
    store, service, client, map_item, seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-late")], 50, 100)],
    )

    def expire_claimed_page():
        current, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
        if job.status == "running":
            with store.transaction() as db:
                db.execute("UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE job_id=?", (job.job_id,))

    client.after_request = expire_claimed_page
    _run_page(service, store, preview)
    current, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert current.preview_revision == 1
    assert current.candidates == []
    assert current.pagination["next_cursor"] == 0
    assert current.pagination["state"] == "loading"
    assert job.status == "running"


def test_valid_page_cache_survives_finish_crash_and_recovery_reuses_it(tmp_path, monkeypatch):
    store, service, client, map_item, _seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-after-crash")], 50, 100)],
    )
    original_finish = store.finish_preview_page

    def expire_before_finish(*args, **kwargs):
        job_id = args[0]
        with store.transaction() as db:
            db.execute(
                "UPDATE literature_map_jobs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE job_id=?",
                (job_id,),
            )
        return original_finish(*args, **kwargs)

    monkeypatch.setattr(store, "finish_preview_page", expire_before_finish)
    _run_page(service, store, preview)
    pending, pending_job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert pending_job.status == "running"
    assert pending.candidates == []
    assert [call[3] for call in client.calls] == [0]

    page_cache_key = service._request_cache_key(
        provider="semantic_scholar",
        operation="references",
        identifier="s2-seed",
        filters={"limit": 50},
        page=0,
    )
    assert store.get_request_cache(page_cache_key)["next_offset"] == 50
    monkeypatch.setattr(store, "finish_preview_page", original_finish)
    assert store.recover_auxiliary_jobs("owner-a")
    recovered_job = service.run_preview_page(pending_job.job_id, "owner-a")
    recovered, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert recovered_job.status == "completed"
    assert recovered.pagination["state"] == "ready"
    assert recovered.candidates[0]["identity_key"] == "semantic_scholar:s2-after-crash"
    assert [call[3] for call in client.calls] == [0]


def test_paginated_preview_http_schema_is_strict_and_serializes_version(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    graph_client = ScriptedGraphClient([([_metadata("s2-http-paper")], 50, None)])
    service = LiteratureMapService(store=store, client=graph_client, executor=None)
    item = store.create_map(routes_literature_maps.OWNER_ID, topic="fuzzing")
    seed = MapPaper.new(item.map_id, semantic_scholar_id="s2-http-seed", title="Seed")
    store.add_nodes(item.map_id, routes_literature_maps.OWNER_ID, [seed])
    with patch.object(routes_literature_maps, "get_literature_map_service", return_value=service):
        client = TestClient(app)
        invalid = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "references", "node_id": seed.node_id, "pagination": {**PAGINATION, "offset": 50}},
        )
        assert invalid.status_code == 422
        boolean = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "references", "node_id": seed.node_id, "pagination": {**PAGINATION, "version": True}},
        )
        assert boolean.status_code == 422
        created = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "references", "node_id": seed.node_id, "pagination": PAGINATION, "idempotency_key": "http-paged"},
        )
        preview_id = created.json()["preview_id"] if created.status_code == 202 else "missing"
        if created.status_code == 202:
            service.run_preview_page(created.json()["job_id"], routes_literature_maps.OWNER_ID)
        repeated_create = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "references", "node_id": seed.node_id, "pagination": PAGINATION, "idempotency_key": "http-paged"},
        )
        conflicting_create = client.post(
            f"/api/literature-maps/{item.map_id}/previews",
            json={"kind": "references", "node_id": seed.node_id, "query": "different", "pagination": PAGINATION, "idempotency_key": "http-paged"},
        )
        loaded = client.get(f"/api/literature-maps/{item.map_id}/previews/{preview_id}")
        bad_load_more = client.post(
            f"/api/literature-maps/{item.map_id}/previews/{preview_id}/load-more",
            json={"expected_preview_revision": True, "retry_failed": False, "idempotency_key": "bad-revision"},
        )
        bad_retry_type = client.post(
            f"/api/literature-maps/{item.map_id}/previews/{preview_id}/load-more",
            json={"expected_preview_revision": 2, "retry_failed": 1, "idempotency_key": "bad-retry"},
        )
        current_revision = loaded.json()["preview"]["preview_revision"]
        queued = client.post(
            f"/api/literature-maps/{item.map_id}/previews/{preview_id}/load-more",
            json={"expected_preview_revision": current_revision, "retry_failed": False, "idempotency_key": "http-next"},
        )

    assert created.status_code == 202
    assert created.json()["preview"]["preview_revision"] == 1
    assert created.json()["preview"]["pagination"]["seed_identity_key"] == seed.identity_key
    assert created.json()["preview"]["pagination"]["state"] == "loading"
    assert repeated_create.status_code == 202
    assert repeated_create.json()["preview_id"] == created.json()["preview_id"]
    assert conflicting_create.status_code == 409
    assert conflicting_create.json()["detail"]["code"] == "MAP_IDEMPOTENCY_CONFLICT"
    assert loaded.status_code == 200
    assert loaded.json()["preview"]["pagination"]["state"] == "ready"
    assert bad_load_more.status_code == 422
    assert bad_retry_type.status_code == 422
    assert queued.status_code == 202
    assert queued.json()["preview_revision"] == current_revision + 1
    assert len(graph_client.calls) == 1


def test_candidate_cap_is_500_unique_records_and_blocks_another_page(tmp_path):
    pages = []
    for page_index in range(10):
        rows = [_metadata(f"s2-paper-{page_index * 50 + row_index}") for row_index in range(50)]
        pages.append((rows, (page_index + 1) * 50 if page_index < 9 else 500, None))
    store, service, client, map_item, seed, preview = _pagination_service(tmp_path, pages)

    _run_page(service, store, preview)
    current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    for page_index in range(1, 10):
        service.load_more_preview(
            map_item.map_id,
            preview.preview_id,
            "owner-a",
            expected_preview_revision=current.preview_revision,
            retry_failed=False,
            idempotency_key=f"cap-page-{page_index}",
        )
        _run_page(service, store, preview)
        current, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert current.pagination["state"] == "capped"
    assert current.pagination["limit_reached"] is True
    assert current.pagination["loaded_count"] == 500
    assert len(current.candidates) == 500
    with pytest.raises(ValueError, match="MAP_PREVIEW_LIMIT_REACHED"):
        service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=current.preview_revision, retry_failed=False, idempotency_key="after-cap")
    assert len(client.calls) == 10


def test_load_more_rejects_wrong_owner_map_and_changed_seed(tmp_path):
    store, service, client, map_item, seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-paper")], None, None)],
    )
    with pytest.raises(LookupError):
        service.load_more_preview(map_item.map_id, preview.preview_id, "owner-b", expected_preview_revision=1, retry_failed=False, idempotency_key="wrong-owner")
    with pytest.raises(LookupError):
        service.load_more_preview("another-map", preview.preview_id, "owner-a", expected_preview_revision=1, retry_failed=False, idempotency_key="wrong-map")

    service.remove_node(map_item.map_id, seed.node_id, "owner-a", expected_revision=0, idempotency_key="remove-seed")
    with pytest.raises(ValueError, match="MAP_SEED_UNAVAILABLE"):
        service.load_more_preview(map_item.map_id, preview.preview_id, "owner-a", expected_preview_revision=1, retry_failed=False, idempotency_key="removed-seed")
    assert client.calls == []


def test_restart_recovery_routes_preview_page_to_typed_handler(tmp_path):
    store, first_service, _old_client, map_item, _seed, preview = _pagination_service(
        tmp_path,
        [],
    )
    restarted_client = ScriptedGraphClient([([_metadata("s2-recovered")], None, None)])

    class InlineExecutor:
        def submit(self, function, *args):
            return function(*args)

    restarted = LiteratureMapService(store=LiteratureMapStore(tmp_path / "maps.sqlite3"), client=restarted_client, executor=InlineExecutor())
    assert restarted.recover("owner-a") == 1
    recovered, job = restarted.get_preview(map_item.map_id, preview.preview_id, "owner-a")
    assert job.operation == "preview_page"
    assert job.status == "completed"
    assert recovered.pagination["state"] == "exhausted"
    assert recovered.candidates[0]["identity_key"] == "semantic_scholar:s2-recovered"
    assert restarted_client.calls == [("s2-seed", "references", 50, 0)]


def test_exhausted_lease_marks_preview_failed_and_requires_explicit_retry(tmp_path):
    store, service, _client, map_item, _seed, preview = _pagination_service(tmp_path, [])
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET status='running',worker_token='stale-token',lease_expires_at='2000-01-01T00:00:00Z',attempts=4 WHERE job_id=?",
            (preview.job_id,),
        )
    assert store.recover_auxiliary_jobs("owner-a") == []
    failed, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert job.status == "failed"
    assert failed.preview_revision == 2
    assert failed.pagination["state"] == "failed"
    assert failed.pagination["failed_cursor"] == 0
    assert failed.pagination["last_error"] == "MAP_JOB_LEASE_EXHAUSTED"
    retried = service.load_more_preview(
        map_item.map_id,
        preview.preview_id,
        "owner-a",
        expected_preview_revision=2,
        retry_failed=True,
        idempotency_key="manual-retry-after-exhaustion",
    )
    assert retried["preview_revision"] == 3
    assert retried["status"] == "loading"


def test_concurrent_load_more_creates_only_one_page_job(tmp_path):
    store, service, _client, map_item, _seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-first")], 50, 100)],
    )
    _run_page(service, store, preview)
    ready, _ = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    def enqueue(key):
        try:
            return service.load_more_preview(
                map_item.map_id,
                preview.preview_id,
                "owner-a",
                expected_preview_revision=ready.preview_revision,
                retry_failed=False,
                idempotency_key=key,
            )
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(enqueue, ("parallel-a", "parallel-b")))
    successes = [item for item in results if isinstance(item, dict)]
    failures = [item for item in results if isinstance(item, str)]
    assert len(successes) == 1
    assert failures == ["MAP_PREVIEW_BUSY"]
    with store.connection() as db:
        page_jobs = db.execute(
            "SELECT COUNT(*) FROM literature_map_jobs WHERE map_id=? AND operation='preview_page'",
            (map_item.map_id,),
        ).fetchone()[0]
    assert page_jobs == 2


def test_seed_removed_during_fetch_cannot_commit_candidates_or_cursor(tmp_path):
    store, service, client, map_item, seed, preview = _pagination_service(
        tmp_path,
        [([_metadata("s2-late-result")], 50, 100)],
    )

    client.after_request = lambda: service.remove_node(
        map_item.map_id,
        seed.node_id,
        "owner-a",
        expected_revision=0,
        idempotency_key="remove-seed-during-fetch",
    )
    _run_page(service, store, preview)
    current, job = service.get_preview(map_item.map_id, preview.preview_id, "owner-a")

    assert job.status == "failed"
    assert current.pagination["state"] == "failed"
    assert current.pagination["last_error"] == "MAP_SEED_UNAVAILABLE"
    assert current.pagination["next_cursor"] == 0
    assert current.candidates == []
