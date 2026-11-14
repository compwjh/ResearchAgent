"""运行时默认任务策略接线：启用开关后分发点应自动激活服务端 scope。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.guard import hooks, runtime, service, store
from backend.app.guard.contracts import MUTATING_TOOLS, GuardOutcome, TaskScope
from backend.app.skills import tool_dispatch


@pytest.fixture(autouse=True)
def isolated_guard(tmp_path: Path):
    store.set_db_path(tmp_path / "guard.sqlite3")
    service.clear_scopes()
    service.set_guard_enabled(False)
    yield
    service.clear_scopes()
    service.set_guard_enabled(False)
    store.set_db_path(None)


def _import_args() -> dict:
    return {
        "operation": "import",
        "source_id": "usenix",
        "candidate": {"title": "A Study of Systems", "pdf_url": "https://www.usenix.org/system/files/paper.pdf"},
    }


def _stub_adapter(monkeypatch: pytest.MonkeyPatch, name: str, calls: list) -> None:
    monkeypatch.setitem(
        tool_dispatch._ADAPTERS,
        name,
        lambda args: calls.append(args) or tool_dispatch.DispatchResult(ok=True, name=name, output="ok"),
    )


def test_read_only_runs_without_manual_scope_or_bind(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(True)
    calls: list = []
    _stub_adapter(monkeypatch, "kb_search", calls)

    result = tool_dispatch.build_default_dispatch()("kb_search", {"query": "q"})

    assert result.ok is True
    assert calls == [{"query": "q"}]
    assert "SCOPE_MISSING" not in str(result.error)


def test_mutating_action_confirms_once_then_consumes(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(True)
    calls: list = []
    _stub_adapter(monkeypatch, "download_and_import_paper", calls)
    dispatch = tool_dispatch.build_default_dispatch()
    args = _import_args()

    first = dispatch("download_and_import_paper", args)
    assert first.ok is False
    assert "需要确认" in first.error
    assert calls == []

    owner = runtime.default_owner_id()
    pending = service.pending_actions(owner)[0]
    service.decide(
        pending["action_ref"], owner_id=owner, choice="allow",
        expected_args_hash=pending["args_hash"],
    )

    second = dispatch("download_and_import_paper", args)
    assert second.ok is True
    assert len(calls) == 1

    third = dispatch("download_and_import_paper", args)
    assert third.ok is False
    assert len(calls) == 1

    events = service.events(owner)["records"]
    assert any(item["reason_code"] == "ACTION_CONSUMED" for item in events)


def test_worker_tool_dispatch_consumes_authorization(monkeypatch: pytest.MonkeyPatch):
    from backend.app.paper_discovery.application.worker_tool import (
        PaperDiscoveryToolFacade,
        WorkerToolResult,
    )

    service.set_guard_enabled(True)
    calls: list = []

    def fake_import(self, source_id, candidate):
        calls.append((source_id, candidate))
        return WorkerToolResult(
            tool="paper_discovery", operation="import", source_id="usenix",
            status="completed", provenance={},
        )

    monkeypatch.setattr(PaperDiscoveryToolFacade, "import_candidate", fake_import)
    facade = PaperDiscoveryToolFacade()
    args = _import_args()

    first = facade.dispatch(args)
    assert first.status == "failed"
    assert first.error_code == "CONFIRMATION_REQUIRED"
    assert calls == []

    owner = runtime.default_owner_id()
    pending = service.pending_actions(owner)[0]
    service.decide(
        pending["action_ref"], owner_id=owner, choice="allow",
        expected_args_hash=pending["args_hash"],
    )

    second = facade.dispatch(args)
    assert second.status == "completed"
    assert len(calls) == 1
    events = service.events(owner)["records"]
    assert any(item["reason_code"] == "ACTION_CONSUMED" for item in events)


def test_guard_disabled_keeps_zero_behaviour_change(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    _stub_adapter(monkeypatch, "kb_search", calls)
    before = hooks.current()

    result = tool_dispatch.build_default_dispatch()("kb_search", {"query": "q"})

    assert result.ok is True
    assert calls == [{"query": "q"}]
    assert hooks.current() == before
    assert service.get_scope(runtime.DEFAULT_TASK_ID) is None
    assert service.pending_actions(runtime.default_owner_id()) == []
    assert service.events(runtime.default_owner_id())["records"] == []


def test_hooks_check_still_fails_closed_without_scope():
    service.set_guard_enabled(True)
    assert hooks.current().task_id == ""

    verdict = hooks.check("kb_search", {"query": "q"})

    assert verdict is not None
    assert verdict.outcome is GuardOutcome.DENY
    assert verdict.reason_code == "SCOPE_MISSING"


def test_ensure_active_does_not_override_explicit_context():
    service.set_guard_enabled(True)
    tokens = hooks.bind("owner-explicit", "task-explicit")
    try:
        assert runtime.ensure_active() is None
        current = hooks.current()
        assert current.owner_id == "owner-explicit"
        assert current.task_id == "task-explicit"
        assert service.get_scope("task-explicit") is None
    finally:
        hooks.reset(tokens)


def test_default_scope_permits_read_only_and_mutating_tools():
    scope = TaskScope(
        task_id="task",
        owner_id="owner",
        allowed_capabilities=runtime.default_capabilities(),
        allowed_hosts=runtime.default_hosts(),
        allow_read_only=True,
    )
    assert "kb_search" in tool_dispatch._ADAPTERS
    assert scope.permits("kb_search") is True
    assert all(scope.permits(name) for name in MUTATING_TOOLS)

    strict = TaskScope(task_id="task", owner_id="owner", allowed_capabilities=frozenset())
    assert strict.permits("kb_search") is False
