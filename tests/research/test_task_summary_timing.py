"""研究任务列表 summary 的 started/completed/duration 字段契约（TDD）。

背景：seed 演示任务用三个相同时间戳伪造「已完成」，用户裁决清理；本用例锁定
列表 summary 必须给出诚实的耗时——无有效完成时间时 ``duration_ms`` 为 None，
绝不返回 0（0 会被前端渲染成「瞬间完成」的误导数据）。
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_research
from backend.app.main import app
from backend.app.platform.bootstrap import override_provider
from backend.app.research.domain.models import ResearchTask

_EMPTY_OBSERVABILITY = {
    "waiting_retry": 0,
    "retry_count": 0,
    "next_retry_at": None,
    "last_error_code": None,
    "current_provider": None,
}


@pytest.fixture(autouse=True)
def _stub_runtime_observability(monkeypatch):
    """列表 summary 的运行时遥测不属于本用例，打桩避免触碰真实 research_store。"""
    monkeypatch.setattr(
        routes_research,
        "_task_runtime_observability",
        lambda _task_id: dict(_EMPTY_OBSERVABILITY),
    )


def _task(*, created_at: str, completed_at: str | None, task_id: str = "task-1") -> ResearchTask:
    return ResearchTask(
        task_id, "owner", "conv-1", "目标", "zh", "balanced", False,
        1, 60, "completed" if completed_at else "running", 1,
        created_at, created_at, completed_at=completed_at,
    )


def test_summary_exposes_started_completed_duration_with_exact_value():
    summary = routes_research._task_summary(
        _task(created_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:30Z")
    )

    assert {"started_at", "completed_at", "duration_ms"} <= set(summary)
    assert summary["completed_at"] == "2026-01-01T00:01:30Z"
    assert summary["duration_ms"] == 90_000
    # 领域模型没有 started_at：必须诚实返回 None，不引用不存在的属性、不造值。
    assert summary["started_at"] is None


def test_summary_without_completion_returns_none_duration_not_zero():
    summary = routes_research._task_summary(
        _task(created_at="2026-01-01T00:00:00Z", completed_at=None)
    )

    assert summary["completed_at"] is None
    assert summary["duration_ms"] is None
    assert summary["duration_ms"] != 0
    assert summary["started_at"] is None


@pytest.mark.parametrize(
    "created_at, completed_at",
    [
        ("not-a-time", "2026-01-01T00:01:30Z"),
        ("2026-01-01T00:00:00Z", "not-a-time"),
        ("2026-01-01T00:02:00Z", "2026-01-01T00:01:00Z"),  # 时间倒挂
        ("", "2026-01-01T00:01:30Z"),
        ("2026-01-01T00:00:00Z", ""),
        ("2026-01-01T00:00:00Z", None),
    ],
)
def test_invalid_or_reversed_times_yield_none_not_zero(created_at, completed_at):
    summary = routes_research._task_summary(
        _task(created_at=created_at, completed_at=completed_at)
    )
    assert summary["duration_ms"] is None
    assert summary["duration_ms"] != 0


def test_offset_aware_created_at_yields_exact_wall_clock_duration():
    """MEDIUM-2：带 +08:00 偏移归一 UTC 后算真实墙钟差（非 None、非 0）。"""
    summary = routes_research._task_summary(
        _task(created_at="2026-01-01T08:00:00+08:00", completed_at="2026-01-01T00:01:30Z")
    )

    assert summary["duration_ms"] == 90_000
    assert summary["duration_ms"] is not None
    assert summary["duration_ms"] != 0


@pytest.mark.parametrize(
    "created_at, completed_at",
    [
        ("2026-01-01T00:00:00", "2026-01-01T00:00:05Z"),  # naive 起 / aware 止
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:05"),  # aware 起 / naive 止
    ],
)
def test_naive_and_aware_mix_never_raises_and_yields_exact_duration(created_at, completed_at):
    """MEDIUM-2：历史 naive UTC 与 aware UTC 混合不得抛 TypeError。"""
    summary = routes_research._task_summary(
        _task(created_at=created_at, completed_at=completed_at)
    )

    assert summary["duration_ms"] == 5_000
    assert isinstance(summary["duration_ms"], int)


def test_same_instant_in_different_timezones_yields_legitimate_zero():
    """MEDIUM-2：同一时刻的两种时区表示得到合法 0（不是「无有效时间」造的 0）。"""
    summary = routes_research._task_summary(
        _task(created_at="2026-01-01T08:00:00+08:00", completed_at="2026-01-01T00:00:00Z")
    )

    assert summary["duration_ms"] == 0
    assert summary["duration_ms"] is not None
    assert isinstance(summary["duration_ms"], int)


def test_duration_helper_parameter_and_docstring_reflect_created_at():
    """LOW-1：duration 以 created_at 起算，形参名与语义说明不得误写 started_at。"""
    signature = inspect.signature(routes_research._task_duration_ms)

    assert list(signature.parameters) == ["created_at", "completed_at"]
    assert "含等待的墙钟时长" in (routes_research._task_duration_ms.__doc__ or "")


def test_list_endpoint_summaries_include_timing_fields():
    """列表接口（而非仅私有 helper）也必须透出三个新字段。"""

    class Service:
        def list_tasks(self, owner_id, project_id=None, status=None, limit=20, cursor=None):
            return [
                _task(task_id="t-done", created_at="2026-01-01T00:00:00Z",
                      completed_at="2026-01-01T00:00:05Z"),
                _task(task_id="t-running", created_at="2026-01-01T00:00:00Z",
                      completed_at=None),
            ], None

    with override_provider("research_service", Service()):
        response = TestClient(app).get("/api/research-tasks")

    assert response.status_code == 200
    items = response.json()["research_tasks"]
    assert len(items) == 2
    for item in items:
        assert {"started_at", "completed_at", "duration_ms"} <= set(item)
    assert items[0]["duration_ms"] == 5_000
    assert items[1]["duration_ms"] is None
