"""Spec050 Task03：三个分发收敛点的执行前校验集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.guard import hooks, service, store
from backend.app.guard.contracts import GuardOutcome, TaskScope
from backend.app.skills import tool_dispatch


@pytest.fixture(autouse=True)
def isolated_guard(tmp_path: Path):
    store.set_db_path(tmp_path / "guard.sqlite3")
    service.clear_scopes()
    service.set_guard_enabled(False)
    tokens = hooks.bind("owner-1", "task-1")
    yield
    hooks.reset(tokens)
    service.clear_scopes()
    service.set_guard_enabled(False)
    store.set_db_path(None)


def _scope():
    return TaskScope(
        task_id="task-1",
        owner_id="owner-1",
        allowed_capabilities=frozenset({"download_and_import_paper", "kb_search"}),
        allowed_hosts=frozenset({"usenix.org"}),
    )


def test_default_dispatch_unchanged_when_disabled(monkeypatch: pytest.MonkeyPatch):
    called = []
    monkeypatch.setitem(
        tool_dispatch._ADAPTERS, "kb_search",
        lambda args: called.append(args) or tool_dispatch.DispatchResult(ok=True, name="kb_search", output="ok"),
    )
    result = tool_dispatch.build_default_dispatch()("kb_search", {"query": "q"})
    assert result.ok is True
    assert called


def test_default_dispatch_blocks_unconfirmed_import(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(True)
    service.register_scope(_scope())
    called = []
    monkeypatch.setitem(
        tool_dispatch._ADAPTERS, "download_and_import_paper",
        lambda args: called.append(args) or tool_dispatch.DispatchResult(ok=True, name="download_and_import_paper"),
    )
    args = {"candidate": {"title": "P", "pdf_url": "https://www.usenix.org/p.pdf"}}
    result = tool_dispatch.build_default_dispatch()("download_and_import_paper", args)
    assert result.ok is False
    assert "需要确认" in result.error
    assert called == []
    assert len(service.pending_actions("owner-1")) == 1


def test_default_dispatch_executes_after_confirmation_and_consumes(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(True)
    service.register_scope(_scope())
    called = []
    monkeypatch.setitem(
        tool_dispatch._ADAPTERS, "download_and_import_paper",
        lambda args: called.append(args) or tool_dispatch.DispatchResult(ok=True, name="download_and_import_paper"),
    )
    dispatch = tool_dispatch.build_default_dispatch()
    args = {"candidate": {"title": "P", "pdf_url": "https://www.usenix.org/p.pdf"}}

    first = dispatch("download_and_import_paper", args)
    assert first.ok is False
    pending = service.pending_actions("owner-1")[0]
    service.decide(pending["action_ref"], owner_id="owner-1", choice="allow", expected_args_hash=pending["args_hash"])

    second = dispatch("download_and_import_paper", args)
    assert second.ok is True
    assert len(called) == 1

    third = dispatch("download_and_import_paper", args)
    assert third.ok is False
    assert len(called) == 1


def test_default_dispatch_records_failure_without_replay(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(True)
    service.register_scope(_scope())

    def boom(_args):
        raise RuntimeError("network down")

    monkeypatch.setitem(tool_dispatch._ADAPTERS, "download_and_import_paper", boom)
    dispatch = tool_dispatch.build_default_dispatch()
    args = {"candidate": {"title": "P", "pdf_url": "https://www.usenix.org/p.pdf"}}
    dispatch("download_and_import_paper", args)
    pending = service.pending_actions("owner-1")[0]
    service.decide(pending["action_ref"], owner_id="owner-1", choice="allow", expected_args_hash=pending["args_hash"])

    result = dispatch("download_and_import_paper", args)
    assert result.ok is False
    events = service.events("owner-1")["records"]
    assert any(e["reason_code"] == "RESULT_UNKNOWN" and e["status"] == "failed" for e in events)


def test_context_roundtrip_preserves_owner_and_task():
    tokens = hooks.bind("owner-x", "task-y")
    try:
        captured = hooks.current()
        assert captured.owner_id == "owner-x" and captured.task_id == "task-y"
        inner = hooks.bind(captured.owner_id, captured.task_id)
        try:
            assert hooks.current() == captured
        finally:
            hooks.reset(inner)
    finally:
        hooks.reset(tokens)
    assert hooks.current().owner_id == "owner-1"  # fixture 绑定的外层上下文


def test_check_returns_none_when_disabled():
    assert hooks.check("download_and_import_paper", {}) is None


def test_check_blocks_out_of_scope_when_enabled():
    service.set_guard_enabled(True)
    verdict = hooks.check("download_and_import_paper", {})
    assert verdict is not None
    assert verdict.outcome is GuardOutcome.DENY
    assert verdict.reason_code == "SCOPE_MISSING"
