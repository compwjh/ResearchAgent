"""Spec028 Task06: safe recovery API and executable UI contracts."""

from pathlib import Path

from backend.app.api.routes_research import recover_research_task
from backend.app.memory.repository import OWNER_ID
from backend.app.platform.bootstrap import override_provider
from backend.app.research.application.research_service import ResearchService, ResearchServiceError
from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore


ROOT = Path(__file__).resolve().parents[2]
OWNER = "owner-a"
NOW = "2026-09-16T00:00:00Z"


def _task(status: str = "interrupted") -> ResearchTask:
    return ResearchTask(
        "task-recover", OWNER, "conversation-1", "goal", "zh", "balanced", False,
        1, 60, status, 1, NOW, NOW,
    )


def _item(item_id: str, status: str) -> ResearchWorkItem:
    return ResearchWorkItem(
        item_id, "task-recover", 1, "search_catalog", "search-worker", "[]",
        '{"query":"x"}', status, 0, NOW, NOW,
    )


def test_recover_returns_scheduler_and_checkpoint_safe_summary(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task())
    store.create_work_items(
        "task-recover",
        [_item("task-recover:done", "completed"), _item("task-recover:unknown", "interrupted")],
    )
    service = ResearchService(store=store, executor=type("Executor", (), {"submit": lambda *_: None})())

    summary = service.recover("task-recover", OWNER)

    assert summary["status"] == "recovery_required"
    assert summary["task_status"] == "interrupted"
    assert summary["work_items"]["completed"] == 1
    assert summary["work_items"]["interrupted"] == 1
    assert summary["requires_checkpoint"] is True
    assert summary["scheduler"] == {"leases": 0, "reservations": 0}
    assert store.get_task("task-recover", OWNER).status == "interrupted"


def test_recover_reuses_checkpoint_validation_and_rejects_stale_digest(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task())
    store.create_work_items("task-recover", [_item("task-recover:unknown", "interrupted")])
    checkpoint = store.save_scheduler_checkpoint(
        "task-recover:unknown", 1, "task-recover:unknown", {"cursor": "p1"}
    )
    service = ResearchService(store=store, executor=type("Executor", (), {"submit": lambda *_: None})())

    summary = service.recover(
        "task-recover", OWNER,
        checkpoint={
            "task_id": "task-recover:unknown",
            "plan_version": 1,
            "node_id": "task-recover:unknown",
            "input_digest": checkpoint.input_digest,
        },
    )
    assert summary["checkpoint"] == {"provided": True, "validated": True}

    try:
        service.recover(
            "task-recover", OWNER,
            checkpoint={
                "task_id": "task-recover:unknown",
                "plan_version": 1,
                "node_id": "task-recover:unknown",
                "input_digest": "0" * 64,
            },
        )
    except ResearchServiceError as exc:
        assert exc.code == "INVALID_STATE_TRANSITION"
        assert exc.http_status == 409
    else:
        raise AssertionError("stale checkpoint must be rejected")


def test_recovery_ui_has_action_and_endpoint_contract():
    script = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "recover: 'recover'" in script
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/recover" in script
    assert "recover: new Set(['interrupted', 'recovery_required'])" in script
    assert "research-task-recover-button" in index
    assert "research-task-recover-button" in script


def test_recover_route_forwards_optional_checkpoint_and_returns_summary():
    seen = {}

    class Service:
        def recover(self, task_id, owner_id, *, checkpoint=None):
            seen.update(task_id=task_id, owner_id=owner_id, checkpoint=checkpoint)
            return {"research_task_id": task_id, "status": "recovery_required"}

    with override_provider("research_service", Service()):
        result = recover_research_task(
            "task-recover",
            type("Payload", (), {"checkpoint": {"plan_version": 1}})(),
        )

    assert result["status"] == "recovery_required"
    assert seen == {
        "task_id": "task-recover",
        "owner_id": OWNER_ID,
        "checkpoint": {"plan_version": 1},
    }
