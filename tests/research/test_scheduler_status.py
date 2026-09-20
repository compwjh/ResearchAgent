"""Spec028 Task06: durable scheduler status endpoint contract."""

from backend.app.api.routes_research import get_research_scheduler_status
from backend.app.main import app
from backend.app.platform.bootstrap import override_provider
from backend.app.research.application.research_service import ResearchService
from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore
from fastapi.testclient import TestClient


NOW = "2999-01-01T00:00:00Z"


def _task(task_id: str, status: str) -> ResearchTask:
    return ResearchTask(
        task_id, "owner", f"conversation-{task_id}", "goal", "zh", "balanced", False,
        1, 60, status, 1, NOW, NOW,
    )


def _item(item_id: str, task_id: str, status: str) -> ResearchWorkItem:
    return ResearchWorkItem(
        item_id, task_id, 1, "search_catalog", "search-worker", "[]",
        '{"query":"x"}', status, 0, NOW, NOW,
    )


def test_scheduler_status_returns_queue_quota_and_safe_aggregate(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(_task("task-queued", "planning"))
    store.create_work_items("task-queued", [_item("item-queued", "task-queued", "queued")])
    store.create_task(_task("task-running", "running"))
    store.create_work_items("task-running", [_item("item-running", "task-running", "running")])
    store.claim_scheduler_lease("item-running", "worker-secret", now=NOW)
    store.reserve_resources("worker-1", "fast", 128, task_id="task-running", now=NOW)

    service = ResearchService(store=store, executor=type("Executor", (), {"submit": lambda *_: None})())
    with override_provider("research_service", service):
        result = get_research_scheduler_status()

    assert result["status"] == "ok"
    assert result["queue"] == {"queued": 1, "running": 1, "waiting_approval": 0, "paused": 0}
    assert result["quota"] == {"active_workers": 1, "reserved_bytes": 128}
    assert result["safety"] == {"active_leases": 1, "active_reservations": 1}
    assert "worker-secret" not in str(result)


def test_scheduler_status_is_registered_at_api_path():
    class Service:
        def scheduler_status(self):
            return {
                "status": "ok",
                "queue": {"queued": 0, "running": 0, "waiting_approval": 0, "paused": 0},
                "quota": {"active_workers": 0, "reserved_bytes": 0},
                "safety": {"active_leases": 0, "active_reservations": 0},
            }

    with override_provider("research_service", Service()):
        response = TestClient(app).get("/api/research-scheduler/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scheduler_status_returns_stable_503_when_service_unavailable():
    class FailingService:
        def scheduler_status(self):
            raise RuntimeError("store unavailable")

    with override_provider("research_service", FailingService()):
        response = TestClient(app, raise_server_exceptions=False).get("/api/research-scheduler/status")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "SOURCE_UNAVAILABLE", "message": "调度器状态暂时不可用"}
    }
