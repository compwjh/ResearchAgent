"""Task runtime observability API contracts."""

import json
from types import SimpleNamespace

from backend.app.api import routes_research


def _task():
    return SimpleNamespace(
        research_task_id="task-observe",
        status="running",
        current_plan_version=1,
        goal="safe goal",
        quality_profile="balanced",
        target_paper_count=5,
        language="zh",
        review_plan_first=False,
        project_id=None,
        conversation_id="conversation-1",
        search_id=None,
        created_at="2026-09-20T00:00:00Z",
        updated_at="2026-09-20T00:00:05Z",
        completed_at=None,
    )


def _work_item(*, status="waiting_retry", retry_count=2, model="qwen3.5:9b"):
    return SimpleNamespace(
        work_item_id="item-1",
        status=status,
        retry_count=retry_count,
        next_retry_at="2026-09-20T00:00:10Z" if status == "waiting_retry" else None,
        last_error_code="MODEL_TIMEOUT",
        error_code=None,
        updated_at="2026-09-20T00:00:05Z",
        resolved_model=model,
        provider=None,
    )


class _Store:
    def __init__(self):
        self.items = [_work_item()]

    def list_work_items(self, _task_id):
        return self.items

    def list_events(self, _task_id, *, limit=1000):
        assert limit == 1000
        return [
            SimpleNamespace(
                event_type="worker",
                safe_payload_json=json.dumps(
                    {
                        "event_type": "provider_fallback",
                        "work_item_id": "item-1",
                        "to_provider": "deepseek",
                        "to_model": "deepseek-chat",
                        "api_key": "must-not-be-returned",
                        "prompt": "must-not-be-returned",
                    }
                ),
            )
        ]


def test_task_list_summary_projects_retry_and_provider_observability(monkeypatch):
    task = _task()
    store = _Store()
    service = SimpleNamespace(list_tasks=lambda *_args, **_kwargs: ([task], "next"))
    monkeypatch.setattr(routes_research, "_store", lambda: store)
    monkeypatch.setattr(routes_research, "_service", lambda: service)

    result = routes_research.list_research_tasks(limit=20)
    observation = result["research_tasks"][0]["runtime_observability"]

    assert observation == {
        "waiting_retry": 1,
        "retry_count": 2,
        "next_retry_at": "2026-09-20T00:00:10Z",
        "last_error_code": "MODEL_TIMEOUT",
        "current_provider": "deepseek",
    }


def test_task_detail_uses_same_allowlisted_observability_shape(monkeypatch):
    task = _task()
    store = _Store()
    service = SimpleNamespace(get_task=lambda *_args, **_kwargs: task)
    store.get_current_plan = lambda _task_id: None
    store.get_session_by_task = lambda *_args: None
    monkeypatch.setattr(routes_research, "_store", lambda: store)
    monkeypatch.setattr(routes_research, "_service", lambda: service)

    result = routes_research.get_research_task(task.research_task_id)
    assert result["runtime_observability"]["current_provider"] == "deepseek"
    assert set(result["runtime_observability"]) == {
        "waiting_retry",
        "retry_count",
        "next_retry_at",
        "last_error_code",
        "current_provider",
    }
    assert "api_key" not in result["runtime_observability"]
    assert "prompt" not in result["runtime_observability"]


def test_observability_is_safe_when_retry_metadata_is_malformed(monkeypatch):
    task = _task()
    store = SimpleNamespace(
        list_work_items=lambda _task_id: [
            SimpleNamespace(
                work_item_id="item-1",
                status="running",
                retry_count="not-a-number",
                next_retry_at="secret-text",
                last_error_code="Authorization: Bearer secret",
                error_code=None,
                updated_at="not-a-time",
                resolved_model=None,
                provider="https://provider.invalid/token",
            )
        ],
        list_events=lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    observation = routes_research._task_summary(task)["runtime_observability"]
    assert observation == {
        "waiting_retry": 0,
        "retry_count": 0,
        "next_retry_at": None,
        "last_error_code": None,
        "current_provider": None,
    }
