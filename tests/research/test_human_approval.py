"""Spec028 Task04: plan-version, pause/cancel CAS and checkpoint contracts."""

from __future__ import annotations

import threading

from backend.app.research.application.research_service import ResearchService
from backend.app.research.application.scheduler import ResearchScheduler
from backend.app.research.domain.models import ResearchPlan, ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore


OWNER = "owner-a"
NOW = "2026-09-16T00:00:00Z"


def _task(task_id: str = "task-1", *, status: str = "running", version: int = 1) -> ResearchTask:
    return ResearchTask(
        task_id, OWNER, "conversation-1", "goal", "zh", "balanced", False,
        1, 60, status, version, NOW, NOW,
    )


def _item(task_id: str = "task-1", item_id: str = "task-1:node-1", *, version: int = 1) -> ResearchWorkItem:
    return ResearchWorkItem(
        item_id, task_id, version, "search_catalog", "search-worker", "[]",
        '{"query":"x"}', "queued", 0, NOW, NOW,
    )


def test_pause_and_cancel_are_single_winner_cas(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task())
    store.create_work_items("task-1", [_item()])
    barrier = threading.Barrier(2)
    outcomes = []

    def pause():
        barrier.wait()
        outcomes.append(("pause", store.pause_task_cas("task-1", OWNER, expected_status="running")))

    def cancel():
        barrier.wait()
        outcomes.append(("cancel", store.cancel_task_cas("task-1", OWNER, expected_status="running")))

    threads = [threading.Thread(target=pause), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(value is not None for _, value in outcomes) == 1
    final = store.get_task("task-1", OWNER)
    assert final is not None and final.status in {"paused", "cancelled"}
    if final.status == "cancelled":
        assert store.get_work_item("task-1:node-1").status == "cancelled"


def test_plan_version_append_rejects_stale_pointer_without_overwrite(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task(status="planning"))
    plan = ResearchPlan(
        research_task_id="task-1", version=2, rationale_summary="new", facets_json="[]",
        status="proposed", created_at=NOW, planner_model="planner",
    )
    created = store.create_plan_version_cas(plan, OWNER, expected_current_version=1)
    assert created is not None
    # A stale callback sees the advanced pointer and is rejected without
    # replacing the immutable row.
    assert store.create_plan_version_cas(plan, OWNER, expected_current_version=1) is None
    saved = store.get_plan("task-1", 2)
    assert saved is not None and saved.rationale_summary == "new"


def test_research_service_pause_resume_reuses_single_state_machine(tmp_path):
    class Executor:
        def submit(self, *_args, **_kwargs):
            return None

    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task())
    store.create_work_items("task-1", [_item()])
    service = ResearchService(store=store, executor=Executor())
    paused = service.pause("task-1", OWNER)
    assert paused.status == "paused"
    resumed = service.resume("task-1", OWNER)
    assert resumed.status == "running"
    assert store.get_task("task-1", OWNER).status == "running"


def test_scheduler_checkpoint_interface_preserves_digest_and_plan_cas(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task(status="planning"))
    store.create_work_items("task-1", [_item()])
    scheduler = ResearchScheduler(store, recover_on_start=False)
    checkpoint = scheduler.save_checkpoint("task-1:node-1", 1, "task-1:node-1", {"cursor": "p1"})
    assert scheduler.get_checkpoint("task-1:node-1", 1, "task-1:node-1") == checkpoint
    assert not scheduler.advance_from_checkpoint(
        "task-1:node-1", plan_version=2, input_digest=checkpoint.input_digest
    )
    assert scheduler.advance_from_checkpoint(
        "task-1:node-1", plan_version=1, input_digest=checkpoint.input_digest
    )
