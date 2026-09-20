"""Spec040 Task02/03: stable failure codes and durable retry scheduling."""

from datetime import datetime, timezone

from backend.app.research.application.agent_runtime import RetryPolicy, compute_retry_delay
from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore


NOW = "2026-09-20T00:00:00Z"


def _store_with_item(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        "task-1", "owner-a", "conversation-1", "goal", "zh", "balanced", False,
        1, 60, "running", 1, NOW, NOW,
    )
    store.create_task(task)
    item = ResearchWorkItem(
        "item-1", task.research_task_id, 1, "search_catalog", "search-worker",
        "[]", '{"query":"retry"}', "queued", 0, NOW, NOW,
    )
    store.create_work_items(task.research_task_id, [item])
    return store, task


def test_bounded_exponential_backoff_accepts_injected_random_source():
    policy = RetryPolicy(base_delay_seconds=2, max_delay_seconds=10, jitter_ratio=0.2)
    assert compute_retry_delay(1, policy=policy, random_source=lambda: 0.5) == 2
    assert compute_retry_delay(2, policy=policy, random_source=lambda: 0.5) == 4
    assert compute_retry_delay(20, policy=policy, random_source=lambda: 0.0) == 8


def test_waiting_retry_metadata_survives_restart_and_requeues_only_when_due(tmp_path):
    store, task = _store_with_item(tmp_path)
    waiting = store.schedule_work_item_retry(
        "item-1",
        error_code="RESOURCE_PROBE_FAILED",
        next_retry_at="2026-09-20T00:00:04Z",
    )
    assert waiting.status == "waiting_retry"
    assert waiting.retry_count == 1
    assert waiting.next_retry_at == "2026-09-20T00:00:04Z"
    assert waiting.last_error_code == "RESOURCE_PROBE_FAILED"

    restarted = ResearchStore(tmp_path / "research.sqlite3")
    assert restarted.get_work_item("item-1").status == "waiting_retry"
    assert restarted.requeue_due_work_items(now="2026-09-20T00:00:03Z") == 0
    assert restarted.requeue_due_work_items(now="2026-09-20T00:00:04Z") == 1
    assert restarted.get_work_item("item-1").status == "queued"


def test_due_work_item_has_single_atomic_claim(tmp_path):
    store, _task = _store_with_item(tmp_path)
    store.schedule_work_item_retry(
        "item-1", error_code="RESOURCE_PROBE_FAILED", next_retry_at=NOW,
    )
    store.requeue_due_work_items(now=NOW)
    first = store.claim_work_item("item-1", "worker-a", now=NOW)
    second = store.claim_work_item("item-1", "worker-b", now=NOW)
    assert first is not None
    assert second is None


def test_late_retry_cannot_reopen_completed_work_item(tmp_path):
    store, _task = _store_with_item(tmp_path)
    store.update_work_item_status("item-1", "running")
    completed = store.update_work_item_status("item-1", "completed", output_json='{"ok":true}')
    late = store.schedule_work_item_retry(
        "item-1", error_code="RESOURCE_PROBE_FAILED", next_retry_at=NOW,
    )
    assert late.status == "completed"
    assert late.output_json == completed.output_json
