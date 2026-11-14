"""guard 动作确认流程的真实 HTTP 端到端测试（真实 sqlite，不 mock 内部函数）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.guard import hooks, runtime, service, signals, store
from backend.app.main import app
from backend.app.skills import tool_dispatch


@pytest.fixture(autouse=True)
def isolated_guard(tmp_path: Path):
    store.set_db_path(tmp_path / "guard.sqlite3")
    service.clear_scopes()
    service.set_guard_enabled(True)
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


def _stub_adapter(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    monkeypatch.setitem(
        tool_dispatch._ADAPTERS,
        "download_and_import_paper",
        lambda args: calls.append(args)
        or tool_dispatch.DispatchResult(ok=True, name="download_and_import_paper"),
    )


def _assert_no_sensitive_content(*payloads) -> None:
    text = json.dumps(payloads, ensure_ascii=False)
    for forbidden in (
        "Ignore previous instructions", "exfiltrate", "api_key", "password",
        "normalized_args", "pdf_url",
    ):
        assert forbidden not in text


def test_http_confirmation_flow_records_allowed_and_consumed(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    _stub_adapter(monkeypatch, calls)
    client = TestClient(app)
    dispatch = tool_dispatch.build_default_dispatch()

    first = dispatch("download_and_import_paper", _import_args())
    assert first.ok is False
    assert calls == []

    actions = client.get("/api/guard/actions")
    assert actions.status_code == 200
    records = actions.json()["records"]
    assert len(records) == 1
    pending = records[0]
    assert pending["status"] == "pending"

    decision = client.post(
        f"/api/guard/actions/{pending['action_ref']}/decision",
        json={"choice": "allow", "args_hash": pending["args_hash"]},
    )
    assert decision.status_code == 200
    assert decision.json()["reason_code"] == "ACTION_ALLOWED"

    second = dispatch("download_and_import_paper", _import_args())
    assert second.ok is True
    assert len(calls) == 1

    events = client.get("/api/guard/events")
    assert events.status_code == 200
    codes = {item["reason_code"] for item in events.json()["records"]}
    assert {"ACTION_ALLOWED", "ACTION_CONSUMED"} <= codes
    _assert_no_sensitive_content(actions.json(), decision.json(), events.json())


def test_http_detector_fault_blocks_and_events_are_queryable(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    _stub_adapter(monkeypatch, calls)
    signals.mark_unavailable(
        owner_id=runtime.default_owner_id(),
        task_id=runtime.DEFAULT_TASK_ID,
        fault="MODEL_LOAD_FAILED",
        model_version="test-detector",
    )
    client = TestClient(app)

    result = tool_dispatch.build_default_dispatch()("download_and_import_paper", _import_args())

    assert result.ok is False
    assert "GUARD_CHECK_UNAVAILABLE" in result.error
    assert calls == []
    events = client.get("/api/guard/events")
    assert events.status_code == 200
    codes = {item["reason_code"] for item in events.json()["records"]}
    assert {"GUARD_CHECK_UNAVAILABLE", "DETECTOR_UNAVAILABLE"} <= codes
    assert client.get("/api/guard/actions").json()["records"] == []
    _assert_no_sensitive_content(result.error, events.json())


def test_http_refresh_recovers_same_pending_and_history(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    _stub_adapter(monkeypatch, calls)
    first = tool_dispatch.build_default_dispatch()("download_and_import_paper", _import_args())
    assert first.ok is False

    client1 = TestClient(app)
    pending = client1.get("/api/guard/actions").json()["records"]
    history = client1.get("/api/guard/events").json()["records"]
    assert len(pending) == 1
    assert history

    client2 = TestClient(app)
    refreshed = client2.get("/api/guard/actions").json()["records"]
    assert refreshed[0]["action_ref"] == pending[0]["action_ref"]
    assert client2.get("/api/guard/events").json()["records"] == history

    decision = client2.post(
        f"/api/guard/actions/{pending[0]['action_ref']}/decision",
        json={"choice": "allow", "args_hash": pending[0]["args_hash"]},
    )
    assert decision.status_code == 200
    codes = {item["reason_code"] for item in client2.get("/api/guard/events").json()["records"]}
    assert "ACTION_ALLOWED" in codes
    _assert_no_sensitive_content(pending, history, refreshed, decision.json())


def test_http_rollback_restores_existing_behaviour(monkeypatch: pytest.MonkeyPatch):
    service.set_guard_enabled(False)
    calls: list = []
    _stub_adapter(monkeypatch, calls)
    client = TestClient(app)
    before = hooks.current()

    result = tool_dispatch.build_default_dispatch()("download_and_import_paper", _import_args())

    assert result.ok is True
    assert len(calls) == 1
    assert hooks.current() == before
    assert client.get("/api/guard/actions").json()["records"] == []
    assert client.get("/api/guard/events").json()["records"] == []
