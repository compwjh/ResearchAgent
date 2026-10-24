import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app.chat.application.chat_runner import ChatRun
from backend.app.literature_maps.application.analysis import MapAnalysisError, MapAnalysisService
from backend.app.literature_maps.application import runtime as runtime_module
from backend.app.literature_maps.application.runtime import reset_literature_map_runtime
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure import store as store_module
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


def _chat_run(content: str) -> ChatRun:
    run = ChatRun(route="direct", events=iter(()))
    run.result = OllamaChatResult(
        content=content,
        thinking="",
        timings=OllamaTimings(),
        timings_available=False,
        first_token_ms=0,
        client_wall_ms=0,
        completed_normally=True,
    )
    return run


class _InlineExecutor:
    def submit(self, function, *args, **kwargs):
        return function(*args, **kwargs)


def _map_with_nodes(store: LiteratureMapStore):
    item = store.create_map("owner-a", topic="fuzzing")
    with_abstract = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-queue-abstract",
        title="Queue paper",
        abstract="A durable abstract.",
    )
    without_abstract = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-queue-missing",
        title="Missing abstract",
    )
    store.add_nodes(item.map_id, "owner-a", [with_abstract, without_abstract])
    return item, with_abstract, without_abstract


def test_analysis_queue_ensure_is_idempotent_and_skips_missing_abstract(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, with_abstract, _without_abstract = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None, model_runner=lambda **_: _chat_run("summary"))

    first = service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-1")
    repeated = service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-1")

    assert first["queue_job_id"] == repeated["queue_job_id"]
    assert first["counts"] == {"total": 2, "completed": 0, "queued": 1, "running": 0, "failed": 0, "skipped": 1}
    analyses = store.list_analyses(item.map_id, with_abstract.node_id, "owner-a")
    assert len(analyses) == 1
    assert analyses[0].evidence_level == "abstract"
    assert service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-2")["queue_job_id"] == first["queue_job_id"]
    assert len(store.list_analyses(item.map_id, with_abstract.node_id, "owner-a")) == 1


def test_automatic_enqueue_reconciles_after_model_configuration_changes(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="configuration")
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-config-fingerprint",
        title="Configuration paper",
        abstract="A durable abstract.",
    )
    store.add_nodes(item.map_id, "owner-a", [node])
    graph = LiteratureMapService(store=store, client=object(), executor=None)
    graph.analysis_service = MapAnalysisService(store=store, executor=None, model_runner=lambda **_: _chat_run("summary"))

    graph._enqueue_abstract_summaries(item.map_id, "owner-a")
    with patch("backend.app.literature_maps.application.analysis.MODEL_NAME", "changed-model"):
        graph._enqueue_abstract_summaries(item.map_id, "owner-a")

    analyses = store.list_analyses(item.map_id, node.node_id, "owner-a")
    by_version = {analysis.version: analysis.model_id for analysis in analyses}
    assert by_version == {1: "qwen3.8:27b", 2: "changed-model"}


def test_analysis_claim_requires_unique_persistent_worker_token_and_finish_fails_closed(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None, model_runner=lambda **_: _chat_run("summary"))
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-token")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]

    first = store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert first is not None
    assert first.worker_token
    assert store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a") is None
    assert store.finish_analysis(
        analysis.job_id,
        item.map_id,
        "owner-a",
        status="completed",
        worker_token="stale-token",
        result={"summary": "must not persist"},
    ) is None
    finished = store.finish_analysis(
        analysis.job_id,
        item.map_id,
        "owner-a",
        status="completed",
        worker_token=first.worker_token,
        result={"summary": "summary"},
    )
    assert finished is not None
    assert finished.status == "completed"


def test_analysis_queue_is_serial_and_pause_resume_controls_following_items(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing")
    nodes = [
        MapPaper.new(item.map_id, semantic_scholar_id=f"s2-serial-{index}", title=f"Paper {index}", abstract=f"Abstract {index}")
        for index in range(2)
    ]
    store.add_nodes(item.map_id, "owner-a", nodes)
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(kwargs["node"].node_id)
        return _chat_run(f"summary-{len(calls)}")

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-serial")
    paused = service.pause_analysis_queue(item.map_id, "owner-a", idempotency_key="pause-1")
    assert paused["state"] == "paused"
    assert service.run_analysis_queue(item.map_id, "owner-a") is None
    assert calls == []

    resumed = service.resume_analysis_queue(item.map_id, "owner-a", idempotency_key="resume-1")
    assert resumed["state"] == "active"
    service.run_analysis_queue(item.map_id, "owner-a")
    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "completed"
    assert queue["counts"] == {"total": 2, "completed": 2, "queued": 0, "running": 0, "failed": 0, "skipped": 0}
    assert len(calls) == 2


def test_analysis_queue_retry_reuses_failed_analysis_version(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    calls = {"count": 0}

    def runner(**_kwargs):
        calls["count"] += 1
        return _chat_run("") if calls["count"] == 1 else _chat_run("recovered")

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    first_queue = service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-retry")
    service.run_analysis_queue(item.map_id, "owner-a")
    failed = service.get_analysis_queue(item.map_id, "owner-a")
    assert failed["state"] == "partial"
    failed_analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    assert failed_analysis.status == "failed"
    retried = service.retry_analysis_queue(item.map_id, "owner-a", idempotency_key="retry-1")
    assert retried["counts"]["queued"] == 1
    service.run_analysis_queue(item.map_id, "owner-a")
    completed = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    assert completed.analysis_id == failed_analysis.analysis_id
    assert completed.version == failed_analysis.version == 1
    assert completed.status == "completed"
    assert service.get_analysis_queue(item.map_id, "owner-a")["queue_job_id"] == first_queue["queue_job_id"]


def test_due_transient_failure_is_requeued_automatically_and_pauses_are_respected(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    calls = {"count": 0}

    def runner(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise MapAnalysisError("MAP_MODEL_RATE_LIMITED", retryable=True, status=503)
        return _chat_run("recovered")

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-due")
    service.run_analysis_queue(item.map_id, "owner-a")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET next_retry_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )
    paused = service.pause_analysis_queue(item.map_id, "owner-a", idempotency_key="pause-due")
    assert paused["state"] == "paused"
    service.run_analysis_queue(item.map_id, "owner-a")
    assert calls["count"] == 1

    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET status='active' WHERE job_id=?",
            (paused["queue_job_id"],),
        )
    service.run_analysis_queue(item.map_id, "owner-a")
    assert calls["count"] == 2
    assert store.list_analyses(item.map_id, node.node_id, "owner-a")[0].status == "completed"

    # An exhausted child remains failed even when its persisted retry time is due.
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET status='failed',attempts=3,next_retry_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )
    before = calls["count"]
    service.run_analysis_queue(item.map_id, "owner-a")
    assert calls["count"] == before


def test_persisted_retry_deadline_wakes_existing_queue_executor(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    calls = {"count": 0}
    completed = threading.Event()

    def runner(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise MapAnalysisError("MAP_MODEL_RATE_LIMITED", retryable=True, status=503)
        completed.set()
        return _chat_run("automatically recovered")

    with ThreadPoolExecutor(max_workers=1) as executor, patch(
        "backend.app.literature_maps.infrastructure.store._retry_delay_seconds", return_value=0
    ):
        service = MapAnalysisService(store=store, executor=executor, queue_executor=executor, model_runner=runner)
        service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-wakeup")
        assert completed.wait(timeout=3)

    assert calls["count"] == 2
    assert store.list_analyses(item.map_id, node.node_id, "owner-a")[0].status == "completed"


def test_analysis_queue_pauses_on_configuration_failure_with_safe_action_code(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, _node, _ = _map_with_nodes(store)

    def runner(**_kwargs):
        raise MapAnalysisError("MAP_MODEL_AUTH_REQUIRED", "模型鉴权待配置", retryable=False, status=503)

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-config")
    service.run_analysis_queue(item.map_id, "owner-a")

    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "paused"
    assert queue["pause_reason"] == "MAP_MODEL_AUTH_REQUIRED"
    assert queue["counts"]["failed"] == 1
    assert queue["failed_items"][0]["error_code"] == "MAP_MODEL_AUTH_REQUIRED"


class _ProviderFailure(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_provider_auth_failure_is_classified_and_pauses_the_queue_atomically(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, _node, _ = _map_with_nodes(store)

    def runner(**_kwargs):
        raise _ProviderFailure("unauthorized", 401)

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-provider-auth")
    service.run_analysis_queue(item.map_id, "owner-a")

    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "paused"
    assert queue["pause_reason"] == "MAP_MODEL_AUTH_REQUIRED"
    assert queue["failed_items"][0]["error_code"] == "MAP_MODEL_AUTH_REQUIRED"


def test_provider_rate_limit_is_retryable_without_pausing_the_queue(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)

    def runner(**_kwargs):
        raise _ProviderFailure("too many requests", 429)

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-provider-rate")
    service.run_analysis_queue(item.map_id, "owner-a")

    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "partial"
    assert queue["pause_reason"] is None
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    assert analysis.error["code"] == "MAP_MODEL_RATE_LIMITED"
    assert analysis.error["retryable"] is True


def test_analysis_queue_removal_rejects_late_completion_and_drops_item(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None, model_runner=lambda **_: _chat_run("summary"))
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-remove")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    claimed = store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert claimed is not None
    current = store.get_map(item.map_id, "owner-a")
    assert current is not None
    store.remove_node(item.map_id, node.node_id, "owner-a", expected_revision=current.revision)

    assert store.finish_analysis(
        analysis.job_id,
        item.map_id,
        "owner-a",
        status="completed",
        worker_token=claimed.worker_token,
        result={"summary": "late"},
    ) is None
    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["counts"]["total"] == 1
    assert queue["counts"]["failed"] == 0
    removed_analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")
    assert len(removed_analysis) == 1
    assert removed_analysis[0].status == "failed"
    assert removed_analysis[0].error["code"] == "MAP_NODE_REMOVED"


def test_analysis_queue_recovery_only_requeues_expired_leases_and_rejects_late_finish(tmp_path):
    database = tmp_path / "maps.sqlite3"
    first_store = LiteratureMapStore(database)
    item, node, _ = _map_with_nodes(first_store)
    first_service = MapAnalysisService(store=first_store, executor=None)
    first_service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-recovery")
    analysis = first_store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    claimed = first_store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert claimed is not None

    calls: list[str] = []

    def runner(**_kwargs):
        calls.append("called")
        return _chat_run("recovered")

    rebuilt = MapAnalysisService(
        store=LiteratureMapStore(database),
        executor=_InlineExecutor(),
        model_runner=runner,
    )
    assert rebuilt.recover() == 0
    with first_store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET lease_expires_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )
    assert rebuilt.recover() == 1
    assert calls == ["called"]
    assert rebuilt.recover("owner-a") == 0
    assert rebuilt.get_analysis_queue(item.map_id, "owner-a")["state"] == "completed"


def test_analysis_finish_fails_closed_after_lease_expiry(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-expired")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    claimed = store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert claimed is not None
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET lease_expires_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )
    assert store.finish_analysis(
        analysis.job_id,
        item.map_id,
        "owner-a",
        status="completed",
        worker_token=claimed.worker_token,
        result={"summary": "late"},
    ) is None


def test_expired_child_recovery_keeps_a_paused_queue_as_paused(tmp_path):
    database = tmp_path / "maps.sqlite3"
    store = LiteratureMapStore(database)
    item, node, _ = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="ensure-paused-recovery")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    claimed = store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert claimed is not None
    assert service.pause_analysis_queue(item.map_id, "owner-a", idempotency_key="pause-recovery")["state"] == "paused"
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET lease_expires_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )

    calls: list[str] = []

    def runner(**_kwargs):
        calls.append("called")
        return _chat_run("must wait for resume")

    rebuilt = MapAnalysisService(store=LiteratureMapStore(database), executor=_InlineExecutor(), model_runner=runner)
    assert rebuilt.recover("owner-a") == 1
    assert calls == []
    queue = rebuilt.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "paused"
    assert queue["counts"]["queued"] == 1


def test_queue_children_release_shared_slots_for_other_map_work(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    first = store.create_map("owner-a", topic="first")
    second = store.create_map("owner-a", topic="second")
    first_node = MapPaper.new(first.map_id, semantic_scholar_id="s2-fair-first", title="First", abstract="Abstract")
    second_node = MapPaper.new(second.map_id, semantic_scholar_id="s2-fair-second", title="Second", abstract="Abstract")
    store.add_nodes(first.map_id, "owner-a", [first_node])
    store.add_nodes(second.map_id, "owner-a", [second_node])
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}
    calls_lock = threading.Lock()

    def runner(**_kwargs):
        with calls_lock:
            calls["count"] += 1
            if calls["count"] == 2:
                started.set()
        release.wait(timeout=3)
        return _chat_run("summary")

    with ThreadPoolExecutor(max_workers=2) as executor, ThreadPoolExecutor(max_workers=2) as queue_executor:
        service = MapAnalysisService(store=store, executor=executor, queue_executor=queue_executor, model_runner=runner)
        service.ensure_analysis_queue(first.map_id, "owner-a", idempotency_key="ensure-fair-first")
        service.ensure_analysis_queue(second.map_id, "owner-a", idempotency_key="ensure-fair-second")
        assert started.wait(timeout=3)
        graph_future = executor.submit(lambda: "graph/other-task-ran")
        assert graph_future.result(timeout=2) == "graph/other-task-ran"
        release.set()


def test_runtime_explicit_analysis_uses_general_slot_while_queue_child_runs(tmp_path):
    """The queue's single child slot must not serialize explicit analysis."""

    reset_literature_map_runtime()
    database = tmp_path / "maps.sqlite3"
    memory_database = tmp_path / "memory.sqlite3"
    first_started = threading.Event()
    first_finished = threading.Event()
    explicit_started = threading.Event()
    release = threading.Event()
    try:
        with patch.dict(
            "os.environ",
            {"LITERATURE_MAP_DB_PATH": str(database), "MEMORY_DB_PATH": str(memory_database)},
            clear=False,
        ):
            service = runtime_module.get_literature_map_service()
            store = service.store
            first = store.create_map("owner-a", topic="queued")
            second = store.create_map("owner-a", topic="explicit")
            first_node = MapPaper.new(first.map_id, semantic_scholar_id="s2-runtime-queue", title="Queued", abstract="Abstract")
            second_node = MapPaper.new(second.map_id, semantic_scholar_id="s2-runtime-explicit", title="Explicit", abstract="Abstract")
            store.add_nodes(first.map_id, "owner-a", [first_node])
            store.add_nodes(second.map_id, "owner-a", [second_node])

            def runner(**kwargs):
                if kwargs["node"].node_id == first_node.node_id:
                    first_started.set()
                    release.wait(timeout=3)
                    first_finished.set()
                else:
                    explicit_started.set()
                return _chat_run("summary")

            analysis = service.analysis_service
            analysis.model_runner = runner
            analysis.ensure_analysis_queue(first.map_id, "owner-a", idempotency_key="runtime-queue")
            assert first_started.wait(timeout=3)
            analysis.request_analysis(
                second.map_id,
                second_node.node_id,
                "owner-a",
                evidence_level="abstract",
                idempotency_key="runtime-explicit",
            )
            assert explicit_started.wait(timeout=1)
            release.set()
            assert first_finished.wait(timeout=3)
    finally:
        release.set()
        reset_literature_map_runtime()


def test_expired_queue_lease_wakes_real_scheduler_after_worker_loss(tmp_path):
    """An orphaned running child is reclaimed by the live scheduler timer."""

    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, _node, _ = _map_with_nodes(store)
    first_started = threading.Event()
    recovered = threading.Event()
    calls = {"count": 0}

    def runner(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            first_started.set()
            raise SystemExit("simulated lost worker")
        recovered.set()
        return _chat_run("recovered")

    with ThreadPoolExecutor(max_workers=1) as executor, patch.object(store_module, "_ANALYSIS_LEASE_SECONDS", -1):
        service = MapAnalysisService(store=store, executor=executor, queue_executor=executor, model_runner=runner)
        service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="lease-live-reaper")
        assert first_started.wait(timeout=3)
        # Only the simulated lost worker has an immediately expired lease;
        # the reclaimed worker receives the normal bounded lease.
        store_module._ANALYSIS_LEASE_SECONDS = 300
        assert recovered.wait(timeout=3)
        deadline = time.monotonic() + 3
        while service.get_analysis_queue(item.map_id, "owner-a")["state"] != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)

    assert calls["count"] == 2
    assert service.get_analysis_queue(item.map_id, "owner-a")["state"] == "completed"


def test_expired_lease_at_attempt_cap_becomes_terminal_failure(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node, _ = _map_with_nodes(store)
    service = MapAnalysisService(store=store, executor=None)
    service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="lease-attempt-cap")
    analysis = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    claimed = store.claim_analysis_job(analysis.job_id, item.map_id, "owner-a")
    assert claimed is not None
    with store.transaction() as db:
        db.execute(
            "UPDATE literature_map_jobs SET attempts=3,lease_expires_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", analysis.job_id),
        )

    assert service.recover("owner-a") == 0
    failed = store.list_analyses(item.map_id, node.node_id, "owner-a")[0]
    assert failed.status == "failed"
    assert failed.error["code"] == "MAP_ANALYSIS_LEASE_EXPIRED"
    queue = service.get_analysis_queue(item.map_id, "owner-a")
    assert queue["state"] == "partial"
    assert queue["counts"]["failed"] == 1


def test_analysis_service_shutdown_cancels_retry_wakeup_without_late_store_write(tmp_path):
    """Reset/shutdown must cancel daemon retry timers before their deadline."""

    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, _node, _ = _map_with_nodes(store)
    failed = threading.Event()

    def runner(**_kwargs):
        failed.set()
        raise MapAnalysisError("MAP_MODEL_RATE_LIMITED", retryable=True, status=503)

    with ThreadPoolExecutor(max_workers=1) as executor, patch(
        "backend.app.literature_maps.infrastructure.store._retry_delay_seconds", return_value=30
    ):
        service = MapAnalysisService(store=store, executor=executor, queue_executor=executor, model_runner=runner)
        service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="shutdown-retry-timer")
        assert failed.wait(timeout=3)
        deadline = time.monotonic() + 3
        while not service._queue_retry_wakeups and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service._queue_retry_wakeups

        original = store.requeue_due_analysis_jobs
        writes: list[tuple[str, str]] = []

        def tracked(map_id, owner_id):
            writes.append((map_id, owner_id))
            return original(map_id, owner_id)

        store.requeue_due_analysis_jobs = tracked
        service.shutdown()
        time.sleep(0.1)

    assert writes == []


def test_analysis_service_shutdown_cancels_lease_reaper_without_late_recovery_write(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, _node, _ = _map_with_nodes(store)
    started = threading.Event()

    def runner(**_kwargs):
        started.set()
        raise SystemExit("simulated worker loss")

    with ThreadPoolExecutor(max_workers=1) as executor, patch.object(store_module, "_ANALYSIS_LEASE_SECONDS", 30):
        service = MapAnalysisService(store=store, executor=executor, queue_executor=executor, model_runner=runner)
        service.ensure_analysis_queue(item.map_id, "owner-a", idempotency_key="shutdown-lease-timer")
        assert started.wait(timeout=3)
        deadline = time.monotonic() + 3
        while not service._analysis_lease_wakeups and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service._analysis_lease_wakeups

        original = store.recover_analysis_jobs
        recoveries: list[str | None] = []

        def tracked(owner_id=None):
            recoveries.append(owner_id)
            return original(owner_id)

        store.recover_analysis_jobs = tracked
        service.shutdown()
        time.sleep(0.1)

    assert recoveries == []


@pytest.mark.parametrize("finish_error", [False, True], ids=["success", "error"])
def test_runtime_reset_and_final_analysis_finish_are_atomic(tmp_path, finish_error):
    """A reset cannot return before an already-entered final finish commits."""

    reset_literature_map_runtime()
    database = tmp_path / "maps.sqlite3"
    memory_database = tmp_path / "memory.sqlite3"
    finish_entered = threading.Event()
    release_finish = threading.Event()
    reset_done = threading.Event()
    writes_after_reset: list[bool] = []
    reset_thread: threading.Thread | None = None
    try:
        with patch.dict(
            "os.environ",
            {"LITERATURE_MAP_DB_PATH": str(database), "MEMORY_DB_PATH": str(memory_database)},
            clear=False,
        ):
            service = runtime_module.get_literature_map_service()
            store = service.store
            item = store.create_map("owner-a", topic="finish race")
            node = MapPaper.new(
                item.map_id,
                semantic_scholar_id="s2-finish-race",
                title="Finish race",
                abstract="Abstract",
            )
            store.add_nodes(item.map_id, "owner-a", [node])
            analysis = service.analysis_service

            if finish_error:
                def runner(**_kwargs):
                    raise MapAnalysisError("MAP_MODEL_RATE_LIMITED", retryable=True, status=503)
            else:
                def runner(**_kwargs):
                    return _chat_run("summary")

            analysis.model_runner = runner
            original_finish = store.finish_analysis

            def blocked_finish(*args, **kwargs):
                finish_entered.set()
                release_finish.wait(timeout=3)
                writes_after_reset.append(reset_done.is_set())
                return original_finish(*args, **kwargs)

            store.finish_analysis = blocked_finish
            analysis.request_analysis(
                item.map_id,
                node.node_id,
                "owner-a",
                evidence_level="abstract",
                idempotency_key="finish-race",
            )
            assert finish_entered.wait(timeout=3)

            def reset_runtime():
                runtime_module.reset_literature_map_runtime()
                reset_done.set()

            reset_thread = threading.Thread(target=reset_runtime, daemon=True)
            reset_thread.start()
            # The final-finish wrapper is already entered.  With the
            # lifecycle lock held across the short CAS, reset must wait rather
            # than return and let this worker write afterwards.
            assert not reset_done.wait(timeout=0.1)
            release_finish.set()
            reset_thread.join(timeout=3)
            assert reset_done.is_set()
    finally:
        release_finish.set()
        if reset_thread is not None:
            reset_thread.join(timeout=3)
        reset_literature_map_runtime()

    assert writes_after_reset == [False]


def test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry(tmp_path, monkeypatch):
    database = tmp_path / "maps.sqlite3"
    LiteratureMapStore(database)
    with sqlite3.connect(database) as db:
        db.execute("DROP INDEX IF EXISTS idx_literature_map_jobs_analysis_claim")
        for column in ("worker_token", "lease_expires_at", "attempts", "next_retry_at"):
            db.execute(f"ALTER TABLE literature_map_jobs DROP COLUMN {column}")
        db.execute("DELETE FROM literature_map_schema WHERE version=?", (6,))
        db.execute(
            "INSERT OR IGNORE INTO literature_map_schema(version,applied_at) VALUES(?,?)",
            (5, "1970-01-01T00:00:00+00:00"),
        )
        db.commit()

    def fail_migration(_db):
        raise RuntimeError("migration interruption")

    monkeypatch.setattr(LiteratureMapStore, "_repair_legacy_idempotency_bindings", staticmethod(fail_migration))
    with pytest.raises(RuntimeError, match="migration interruption"):
        LiteratureMapStore(database)
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(literature_map_jobs)")}
        assert not {"worker_token", "lease_expires_at", "attempts", "next_retry_at"} & columns
        indexes = {row[1] for row in db.execute("PRAGMA index_list(literature_map_jobs)")}
        assert "idx_literature_map_jobs_analysis_claim" not in indexes
        assert db.execute("SELECT 1 FROM literature_map_schema WHERE version=6").fetchone() is None

    monkeypatch.undo()
    upgraded = LiteratureMapStore(database)
    assert upgraded.schema_version == 6
    LiteratureMapStore(database)


def test_analysis_queue_get_is_read_only_and_control_routes_are_owner_scoped(tmp_path):
    reset_literature_map_runtime()
    database = tmp_path / "maps.sqlite3"
    memory_database = tmp_path / "memory.sqlite3"
    with patch.dict(
        "os.environ",
        {"LITERATURE_MAP_DB_PATH": str(database), "MEMORY_DB_PATH": str(memory_database)},
        clear=False,
    ), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ), patch(
        "backend.app.literature_maps.application.analysis.MapAnalysisService.run_analysis_queue", autospec=True
    ):
        client = TestClient(app)
        created = client.post("/api/literature-maps", json={"topic": "queue api", "limit": 20})
        assert created.status_code == 202
        map_id = created.json()["map_id"]
        store = LiteratureMapStore(database)
        node = MapPaper.new(map_id, semantic_scholar_id="s2-api-queue", title="API queue", abstract="Abstract")
        store.add_nodes(map_id, "local-user", [node])

        before = client.get(f"/api/literature-maps/{map_id}/analysis-queue")
        assert before.status_code == 200
        assert before.json()["queue_job_id"] is None
        with store.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM literature_map_jobs WHERE operation='analysis_queue'").fetchone()[0] == 0

        ensured = client.post(
            f"/api/literature-maps/{map_id}/analysis-queue/ensure",
            json={"idempotency_key": "api-ensure"},
        )
        assert ensured.status_code == 202
        assert ensured.json()["state"] == "active"
        queue_job_id = ensured.json()["queue_job_id"]
        assert client.post(
            f"/api/literature-maps/{map_id}/analysis-queue/pause",
            json={"idempotency_key": "api-pause"},
        ).json()["state"] == "paused"
        assert client.post(
            f"/api/literature-maps/{map_id}/analysis-queue/resume",
            json={"idempotency_key": "api-resume"},
        ).json()["state"] == "active"
        assert client.get(f"/api/literature-maps/{map_id}/analysis-queue").json()["queue_job_id"] == queue_job_id
    reset_literature_map_runtime()


def test_view_label_mode_is_optional_and_defaults_for_legacy_rows(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="view")
    updated = store.update_view(
        item.map_id,
        "owner-a",
        expected_revision=0,
        positions=[],
        viewport=None,
        filters=None,
        layers=None,
        label_mode="neighbors",
    )
    assert updated.view_settings["label_mode"] == "neighbors"
    with store.transaction() as db:
        db.execute("UPDATE literature_maps SET view_json=? WHERE map_id=?", ('{"viewport":{"x":0,"y":0,"scale":1}}', item.map_id))
    legacy = store.get_map(item.map_id, "owner-a")
    assert legacy is not None
    assert legacy.view_settings.get("label_mode", "all") == "all"
