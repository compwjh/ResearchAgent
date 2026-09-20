"""Spec029/030/031 — intake SSE 终止帧健壮性（TDD 回归）。

覆盖两类根因：
1. ``_intake_stream`` 收尾段抛异常时仍补发 error + done，且服务端落库为终态；
2. ``_failed_message_stream`` 产出的每一帧都带 event_seq（首个 meta seq===1）。
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.api import routes_conversations as rc
from backend.app.api.routes_conversations import (
    _failed_message_stream,
    _intake_stream,
)


def _parse_frames(body):
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _make_intake_result(**overrides):
    session = overrides.pop("session", SimpleNamespace(to_dict=lambda: {"research_session_id": "s1"}))
    fields = overrides.pop("fields", [])
    base = {
        "status": "intake",
        "missing": [],
        "session": session,
        "fields": fields,
        "choices": [],
        "question": None,
        "activation": None,
        "error": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_convo_user_assistant():
    conversation = SimpleNamespace(project_id=None, conversation_id="c1")
    user = SimpleNamespace(
        message_id="u1", owner_id="owner-x", model="m", mode="normal", content="研究",
    )
    assistant = SimpleNamespace(message_id="a1")
    return conversation, user, assistant


def test_intake_stream_emits_terminal_frames_when_tail_write_fails():
    """根因1：收尾段 update_message 抛异常，仍要发出 error + done，不得「无终止帧」。"""
    repo = MagicMock()
    repo.update_message.side_effect = RuntimeError("sqlite lock")
    conversation, user, assistant = _fake_convo_user_assistant()
    result = _make_intake_result(status="intake")
    with patch.object(rc, "_ensure_research_session_plan", return_value=None):
        body = "".join(_intake_stream(repo, conversation, user, assistant, result, "m", "normal", "off"))
    events = _parse_frames(body)
    types = [e["type"] for e in events]
    assert "error" in types
    assert "done" in types
    assert types[-1] == "done"
    # 终止帧必须带 event_seq（前端按序校验）
    assert all("event_seq" in e for e in events)


def test_intake_stream_persists_terminal_status_when_tail_to_dict_fails():
    """根因1 + spec-024：已在收尾段把消息落库为 completed 后 to_dict 抛异常，
    不得把 completed 降级为 failed，但仍要补发 error + done。"""
    repo = MagicMock()
    conversation, user, assistant = _fake_convo_user_assistant()
    broken_session = SimpleNamespace(to_dict=MagicMock(side_effect=RuntimeError("to_dict boom")))
    result = _make_intake_result(status="intake", session=broken_session)
    with patch.object(rc, "_ensure_research_session_plan", return_value=None):
        body = "".join(_intake_stream(repo, conversation, user, assistant, result, "m", "normal", "off"))
    events = _parse_frames(body)
    types = [e["type"] for e in events]
    assert "error" in types
    assert "done" in types
    # 已完成落库不被覆盖：最后一次 update_message 仍是 completed（终态）
    update_calls = repo.update_message.call_args_list
    assert update_calls
    last = update_calls[-1]
    assert last.kwargs.get("status") == "completed"
    # 补发的 done 也保持 completed，而非 failed
    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["status"] == "completed"


def test_failed_message_stream_frames_carry_event_seq():
    """根因2：_failed_message_stream 每帧都带 event_seq，首个 meta seq===1。"""
    repo = MagicMock()
    conversation, user, assistant = _fake_convo_user_assistant()
    detail = {"code": "MODEL_UNAVAILABLE", "message": "模型不可用", "retryable": True}
    response = _failed_message_stream(repo, conversation, user, assistant, detail)

    async def drain():
        return "".join([chunk async for chunk in response.body_iterator])

    body = asyncio.run(drain())
    events = _parse_frames(body)
    assert events, "expected at least meta/error/done frames"
    # 每个帧都必须带 event_seq
    assert all("event_seq" in e for e in events)
    # 首个 meta 的 event_seq 必须为 1
    assert events[0]["type"] == "meta"
    assert events[0]["event_seq"] == 1
    # 序列连续
    assert [e["event_seq"] for e in events] == list(range(1, len(events) + 1))


def test_intake_stream_happy_path_ends_with_completed_done():
    """正常路径不受影响：仍发 done(status='completed')，且无 error。"""
    repo = MagicMock()
    conversation, user, assistant = _fake_convo_user_assistant()
    result = _make_intake_result(status="intake")
    with patch.object(rc, "_ensure_research_session_plan", return_value=None):
        body = "".join(_intake_stream(repo, conversation, user, assistant, result, "m", "normal", "off"))
    events = _parse_frames(body)
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "completed"
    assert "error" not in [e["type"] for e in events]


def test_intake_stream_reemit_failure_does_not_crash_only_persists():
    """补发终止帧时若连接已不可写（emit 抛异常），不二次崩溃，只落库。"""
    original_emit = rc.EventSequencer.emit

    def fake_emit(self, event_type, **payload):
        if event_type in ("error", "done"):
            raise RuntimeError("connection closed")
        return original_emit(self, event_type, **payload)

    repo = MagicMock()  # update_message 不抛错，使 durable_completed 置位
    conversation, user, assistant = _fake_convo_user_assistant()
    broken_session = SimpleNamespace(to_dict=MagicMock(side_effect=RuntimeError("to_dict boom")))
    result = _make_intake_result(status="intake", session=broken_session)
    with patch.object(rc.EventSequencer, "emit", fake_emit), patch.object(
        rc, "_ensure_research_session_plan", return_value=None
    ):
        # 不得抛出异常
        body = "".join(_intake_stream(repo, conversation, user, assistant, result, "m", "normal", "off"))
    events = _parse_frames(body)
    # 连接已不可写 → 补发的 error/done 未能送达，但生成器干净退出
    assert "error" not in [e["type"] for e in events]
    assert "done" not in [e["type"] for e in events]
    # 落库动作仍发生（finally 兜底持久化）
    assert repo.update_message.called
    assert repo.finalize_processing_steps.called
