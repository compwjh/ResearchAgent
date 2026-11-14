"""风险信号 → 执行防护对接契约测试（供另一条开发线对齐语义）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.guard import service, signals, sources, store
from backend.app.guard.contracts import GuardOutcome, TaskScope


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path):
    store.set_db_path(tmp_path / "guard.sqlite3")
    service.set_guard_enabled(True)
    service.clear_scopes()
    service.register_scope(TaskScope(
        task_id="task-1", owner_id="owner-1",
        allowed_capabilities=frozenset({"download_and_import_paper"}),
        allowed_hosts=frozenset({"usenix.org"}),
    ))
    yield
    service.clear_scopes()
    service.set_guard_enabled(False)
    store.set_db_path(None)


def _signal(**kwargs):
    base = {
        "source_kind": "pdf", "source_ref": "pdf:abc123",
        "label": 1, "score": 0.91,
        "model_version": "piguard-formal-v1", "detector_version": "3f284d8e",
        "window_index": 0, "window_count": 2,
    }
    base.update(kwargs)
    return signals.RiskSignal(**base)


def _args():
    return {"candidate": {"title": "P", "pdf_url": "https://www.usenix.org/p.pdf"}}


def test_validation_rejects_bad_signals():
    assert signals.validation_error(_signal(label=2)) == "label must be 0 (benign) or 1 (injection)"
    assert "score" in signals.validation_error(_signal(score=1.5))
    assert "source_kind" in signals.validation_error(_signal(source_kind="unknown"))
    assert "window" in signals.validation_error(_signal(window_index=5, window_count=2))
    assert signals.validation_error(_signal()) == ""


def test_benign_signal_never_grants_authority():
    """核心语义：label=0 也不能跳过单动作确认。"""
    signals.report(_signal(label=0, score=0.02), owner_id="owner-1", task_id="task-1")
    decision = service.authorize("download_and_import_paper", _args(), owner_id="owner-1", task_id="task-1")
    assert decision.outcome is GuardOutcome.REQUIRE_CONFIRMATION


def test_injection_signal_still_requires_confirmation_not_auto_deny():
    """信号是证据，不是裁决；有副作用动作仍走确认流程。"""
    signals.report(_signal(label=1), owner_id="owner-1", task_id="task-1")
    decision = service.authorize("download_and_import_paper", _args(), owner_id="owner-1", task_id="task-1")
    assert decision.outcome is GuardOutcome.REQUIRE_CONFIRMATION
    listed = service.pending_actions("owner-1")
    assert listed[0]["risk"]["label"] == 1
    assert listed[0]["risk"]["reason_code"] == signals.INJECTION_REASON


def test_detector_timeout_holds_sensitive_action():
    signals.report(_signal(timed_out=True), owner_id="owner-1", task_id="task-1")
    decision = service.authorize("download_and_import_paper", _args(), owner_id="owner-1", task_id="task-1")
    assert decision.outcome is GuardOutcome.DENY
    assert decision.reason_code == signals.HOLD_REASON


def test_uncovered_windows_hold_sensitive_action():
    signals.report(_signal(uncovered_windows=3), owner_id="owner-1", task_id="task-1")
    decision = service.authorize("download_and_import_paper", _args(), owner_id="owner-1", task_id="task-1")
    assert decision.reason_code == signals.HOLD_REASON


def test_mark_unavailable_holds_and_is_observable():
    result = signals.mark_unavailable(
        owner_id="owner-1", task_id="task-1", fault="MODEL_LOAD_FAILED",
        model_version="piguard-formal-v1",
    )
    assert result.requires_hold
    events = service.events("owner-1")["records"]
    assert any(e["reason_code"] == "DETECTOR_UNAVAILABLE" and e["status"] == "failed" for e in events)
    decision = service.authorize("download_and_import_paper", _args(), owner_id="owner-1", task_id="task-1")
    assert decision.reason_code == signals.HOLD_REASON


def test_events_never_carry_raw_content():
    signals.report(_signal(source_ref="pdf:deadbeef"), owner_id="owner-1", task_id="task-1")
    for event in service.events("owner-1")["records"]:
        assert event["module"] == "risk-detection"
        assert "text" not in event
        assert "prompt" not in event
        assert event["schema_version"] == "guard-event-v1"


def test_windows_are_bounded_and_sources_marked():
    text = "x" * 5000
    windows, uncovered = sources.split_windows(
        text, source_kind="web", document_id="doc-1", locator="p3",
    )
    assert windows
    assert all(w.window_count == len(windows) for w in windows)
    assert all(len(w.text) <= sources.MAX_WINDOW_TOKENS * 4 for w in windows)
    assert all(w.source_ref.startswith("web:") for w in windows)
    assert all(sources.is_untrusted(w.source_kind) for w in windows)
    assert not any(sources.can_grant_authority(w.source_kind) for w in windows)

    long_windows, uncovered_many = sources.split_windows(
        "y" * 2_000_000, source_kind="pdf", document_id="doc-2",
        max_windows=4,
    )
    assert len(long_windows) == 4
    assert uncovered_many > 0


def test_signal_kwargs_match_window():
    windows, _ = sources.split_windows("hello", source_kind="tool_result", document_id="d")
    kwargs = windows[0].signal_kwargs()
    assert kwargs["source_kind"] == "tool_result"
    assert kwargs["window_index"] == 0
    assert kwargs["window_count"] == 1
