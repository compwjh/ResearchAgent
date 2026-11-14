"""guard 事件 SSE 增量推送与端点接线测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_guard
from backend.app.guard import store
from backend.app.guard.contracts import EVENT_SCHEMA_VERSION
from backend.app.main import app
from backend.app.memory.repository import OWNER_ID

OWNER = "sse-owner"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store.set_db_path(tmp_path / "guard.sqlite3")
    monkeypatch.setattr(routes_guard.time, "sleep", lambda _seconds: None)
    yield
    store.set_db_path(None)


def _append(event_id: str, created_at: str) -> dict:
    record = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "reason_code": "TEST_EVENT",
        "created_at": created_at,
    }
    store.append_event({
        "event_id": event_id,
        "owner_id": OWNER,
        "payload": record,
        "created_at": created_at,
    })
    return record


def _frame_data(frame: str) -> dict:
    assert frame.startswith("id: ")
    assert "event: guard\n" in frame
    assert frame.endswith("\n\n")
    return json.loads(frame.split("data: ", 1)[1].rstrip("\n"))


def test_first_frame_format_dedup_and_generator_exit():
    e1 = _append("gev_1", "2026-01-01T00:00:01+00:00")
    e2 = _append("gev_2", "2026-01-01T00:00:02+00:00")
    stream = routes_guard.event_stream(OWNER, limit=50, poll_seconds=0, heartbeat_seconds=999)

    first = next(stream)
    assert first.startswith("id: gev_1\n")
    assert _frame_data(first) == {
        "type": "guard", "schema_version": EVENT_SCHEMA_VERSION, "record": e1,
    }

    second = next(stream)
    assert second.startswith("id: gev_2\n")
    assert _frame_data(second)["record"] == e2

    e3 = _append("gev_3", "2026-01-01T00:00:03+00:00")
    third = next(stream)
    assert third.startswith("id: gev_3\n")
    assert _frame_data(third)["record"] == e3
    assert "gev_1" not in third and "gev_2" not in third
    stream.close()


def test_last_event_id_incremental_and_unknown_cursor_replays_all():
    _append("gev_1", "2026-01-01T00:00:01+00:00")
    _append("gev_2", "2026-01-01T00:00:02+00:00")
    _append("gev_3", "2026-01-01T00:00:03+00:00")

    incremental = routes_guard.event_stream(
        OWNER, last_event_id="gev_2", limit=50, poll_seconds=0, heartbeat_seconds=999,
    )
    first = next(incremental)
    assert first.startswith("id: gev_3\n")
    incremental.close()

    replay = routes_guard.event_stream(
        OWNER, last_event_id="missing", limit=50, poll_seconds=0, heartbeat_seconds=999,
    )
    ids = [next(replay).splitlines()[0] for _ in range(3)]
    assert ids == ["id: gev_1", "id: gev_2", "id: gev_3"]
    replay.close()


def test_heartbeat_frame_on_idle():
    stream = routes_guard.event_stream(
        OWNER, limit=50, poll_seconds=0, heartbeat_seconds=0,
    )
    assert next(stream) == ": heartbeat\n\n"
    stream.close()


def test_stream_endpoint_headers_and_last_event_id(monkeypatch: pytest.MonkeyPatch):
    frame = (
        'id: gev_x\nevent: guard\n'
        'data: {"type": "guard", "schema_version": "guard-event-v1", "record": {}}\n\n'
    )
    captured: dict = {}

    def fake_stream(owner_id, *, last_event_id="", limit=50, **kwargs):
        captured.update(owner_id=owner_id, last_event_id=last_event_id, limit=limit)
        yield frame

    monkeypatch.setattr(routes_guard, "event_stream", fake_stream)
    client = TestClient(app)
    with client.stream("GET", "/api/guard/stream", headers={"last-event-id": "gev_x"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        assert "".join(response.iter_text()) == frame

    assert captured == {"owner_id": OWNER_ID, "last_event_id": "gev_x", "limit": 50}
