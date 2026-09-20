"""Spec028 Task03: durable scheduler lease/recovery probes."""

from __future__ import annotations

import hashlib
import threading

from backend.app.research.application.scheduler import ResearchScheduler
from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore


NOW = "2026-09-16T00:00:00Z"


def _task(task_id: str, created: str = NOW) -> ResearchTask:
    return ResearchTask(task_id, "owner", f"conversation-{task_id}", "goal", "zh", "balanced", False, 1, 60, "planning", 1, created, created)


def _item(item_id: str, task_id: str) -> ResearchWorkItem:
    return ResearchWorkItem(item_id, task_id, 1, "search_catalog", "search-worker", "[]", '{"query":"x"}', "queued", 0, NOW, NOW)


def test_lease_claim_heartbeat_and_expired_takeover_are_token_cas(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    first = store.claim_lease("item", "owner-a", lease_seconds=10, now=NOW)
    assert first is not None and first.owner_token == "owner-a"
    assert store.claim_lease("item", "owner-b", now="2026-09-16T00:00:01Z") is None
    assert store.heartbeat_lease("item", "owner-b", now="2026-09-16T00:00:02Z") is None
    second = store.claim_lease("item", "owner-b", now="2026-09-16T00:00:11Z")
    assert second is not None and second.owner_token == "owner-b"
    assert store.heartbeat_lease("item", "owner-a", now="2026-09-16T00:00:12Z") is None


def test_claim_work_item_is_single_writer_and_reuses_existing_state_machine(tmp_path):
    path = tmp_path / "research.sqlite3"
    ResearchStore(path).create_task(_task("t"))
    store = ResearchStore(path)
    store.create_work_items("t", [_item("i", "t")])
    barrier = threading.Barrier(2)
    results = []

    def claim(token):
        barrier.wait()
        results.append(store.claim_work_item("i", token, now=NOW))

    threads = [threading.Thread(target=claim, args=(token,)) for token in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1
    assert store.get_work_item("i").status == "running"


def test_checkpoint_digest_is_durable_and_must_match_before_advance(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task("t"))
    store.create_work_items("t", [_item("i", "t")])
    checkpoint = store.save_checkpoint("i", 1, "i", {"cursor": "paper-1"})
    assert hashlib.sha256(checkpoint.state_json.encode()).hexdigest() == checkpoint.input_digest
    assert not store.advance_from_checkpoint("i", plan_version=2, input_digest=checkpoint.input_digest)
    assert store.advance_from_checkpoint("i", plan_version=1, input_digest=checkpoint.input_digest)


def test_scheduler_round_robin_and_resource_release(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    for task_id in ("task-a", "task-b"):
        store.create_task(_task(task_id))
        store.create_work_items(task_id, [_item(f"item-{task_id}", task_id)])
    scheduler = ResearchScheduler(store, lease_seconds=30)
    first = scheduler.claim_next("worker-a", now=NOW)
    second = scheduler.claim_next("worker-b", now=NOW)
    assert first is not None and second is not None
    assert first.work_item.research_task_id != second.work_item.research_task_id

    class Probe:
        def arbitrate(self, task_id, requested):
            return min(requested, 2), None

        def release(self, task_id):
            return None

    scheduler = ResearchScheduler(store, probe=Probe())
    assert scheduler.acquire_resources("task-a", 2, estimated_bytes=10)[0] == 2
    assert len(store.list_reservations(task_id="task-a")) == 2
    scheduler.release_resources("task-a")
    assert store.list_reservations(task_id="task-a") == []

