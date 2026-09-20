"""Task03 backend contract tests (red first, then implementation)."""

import json
import sqlite3
from unittest.mock import patch

import pytest


def test_reasoning_filter_normalizes_protocol_markers_and_caps_codepoints():
    from backend.app.chat.application.reasoning import filter_reasoning

    value, truncated = filter_reasoning(["e", "\u0301<|assistant|>", "\x00\n", "🙂"])
    assert value == "é\n🙂"
    assert truncated is False
    value, truncated = filter_reasoning(["🙂" * 25_000])
    assert truncated is True
    assert len(value) == 20_000
    assert "中间思考已省略" in value


def test_event_envelope_assigns_monotonic_sequence_and_drops_terminal_events():
    from backend.app.chat.application.reasoning import EventSequencer

    sequencer = EventSequencer("assistant-1")
    first = json.loads(sequencer.emit("meta").split("data: ", 1)[1])
    second = json.loads(sequencer.emit("token", content="ok").split("data: ", 1)[1])
    done = json.loads(sequencer.emit("done", status="completed").split("data: ", 1)[1])
    assert [first["event_seq"], second["event_seq"], done["event_seq"]] == [1, 2, 3]
    assert sequencer.emit("token", content="late") == ""


def test_reasoning_effort_resolver_keeps_unsupported_high_unsupported_for_27b():
    from backend.app.platform.ollama import ReasoningCapabilities, resolve_reasoning_effort

    caps = ReasoningCapabilities("qwen3.8:27b", ("off", "low", "medium"), "off", "ollama_probe", "now", {"low": "e1"})
    with patch("backend.app.platform.ollama.probe_reasoning_capabilities", return_value=caps):
        assert resolve_reasoning_effort("qwen3.8:27b", "low").provider_value == "low"
        with pytest.raises(ValueError, match="REASONING_EFFORT_UNSUPPORTED"):
            resolve_reasoning_effort("qwen3.8:27b", "high")
        with pytest.raises(ValueError, match="REASONING_EFFORT_UNSUPPORTED"):
            resolve_reasoning_effort("qwen3.8:27b", "xhigh")


def test_observability_metadata_does_not_include_raw_reasoning():
    from backend.app.platform.observability.spans import _build_metadata, derive_metrics
    from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

    result = OllamaChatResult("answer", "secret chain", OllamaTimings(), False, 1, 2)
    metadata = _build_metadata(result, derive_metrics(result), model="m", route="direct", input_chars=1)
    assert "thinking" not in metadata
    assert metadata["reasoning_present"] is True
    assert metadata["reasoning_chars"] == len("secret chain")
    assert set(metadata) == {"model", "route", "reasoning_present", "reasoning_chars"}


def test_reasoning_filter_carries_split_template_markers():
    from backend.app.chat.application.reasoning import filter_reasoning_chunks

    value, truncated = filter_reasoning_chunks(["safe<|im_", "start|>secret", " tail"])
    assert value == "safesecret tail"
    assert truncated is False


def test_reasoning_filter_removes_wrappers_roles_and_controls_without_losing_text():
    from backend.app.chat.application.reasoning import filter_reasoning, filter_reasoning_chunks

    value, truncated = filter_reasoning(["合法<think>隐藏</think><analysis>分析</analysis><reasoning>推理</reasoning>", "[INST]指令[/INST]assistant:正文 user:内容 system:规则\x00\n"])
    assert value == "合法隐藏分析推理指令正文 内容 规则\n"
    assert truncated is False
    value, truncated = filter_reasoning_chunks(["keep<ana", "lysis>split</an", "alysis>tail<rea", "soning>ok</reasoning>"])
    assert value == "keepsplittailok"
    assert truncated is False


def test_event_sequencer_rejects_old_and_gap_sequences():
    from backend.app.chat.application.reasoning import EventSequencer

    sequencer = EventSequencer("a1")
    assert sequencer.accept({"event_seq": 1}) is True
    assert sequencer.accept({"event_seq": 1}) is False
    with pytest.raises(ValueError, match="EVENT_SEQUENCE_GAP"):
        sequencer.accept({"event_seq": 3})


def test_reasoning_probe_uses_ollama_chat_and_marks_xhigh_with_evidence(monkeypatch):
    from backend.app.platform import ollama

    class Response:
        def __init__(self, effort):
            self.status_code = 500 if effort == "high" else 200
            self.content = b"{}"
            self._body = {"message": {"content": "OK", "thinking": "draft" if effort not in {"off", "high"} else ""}}

        def json(self):
            return self._body

    calls = []
    def fake_post(url, *, json, timeout, trust_env):
        calls.append(json)
        return Response(json["think"] if isinstance(json["think"], str) else ("xhigh" if json["think"] else "off"))

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    caps = ollama.probe_reasoning_capabilities("m")
    assert len(calls) == 5 and "xhigh" in caps.supported_efforts
    assert caps.evidence_ids["xhigh"]
    assert "high" not in caps.supported_efforts


def test_baseline_schema_marker_and_restart_are_idempotent(tmp_path):
    """新基线：版本标记为 SCHEMA_VERSION、停用表不再存在、默认偏好行已播种、重启幂等。

    原用例断言 v6→v7 的 ``migration_markers`` 迁移标记；spec-038 删除整条历史迁移链后
    该标记不复存在，故改为对新基线做等价校验，并保留「默认偏好行已播种」这条回归护栏
    （缺失会让 update_conversation_reasoning 把「effort 未变」误判为偏好变更）。
    """
    from backend.app.memory.migration import SCHEMA_VERSION
    from backend.app.memory.repository import MemoryRepository

    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    with repo.connection() as db:
        assert db.execute("SELECT max(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert not {"memories", "memory_evidence", "system_rules"} & tables
        assert db.execute("SELECT count(*) FROM user_chat_preferences WHERE owner_id='local-user'").fetchone()[0] == 1
    MemoryRepository(path)
    with repo.connection() as db:
        assert db.execute("SELECT count(*) FROM schema_version WHERE version=?", (SCHEMA_VERSION,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM user_chat_preferences WHERE owner_id='local-user'").fetchone()[0] == 1


def test_baseline_conversation_reasoning_check_survives_restart(tmp_path):
    """新基线：conversations 的 reasoning_effort CHECK 约束在重启后依然生效。

    原用例调用已被删除的 ``_is_schema_v7``（v1→v7 迁移链内部实现），
    改为直接对**重启后的实例**校验约束本身，保留原校验意图。
    """
    from backend.app.memory.repository import MemoryRepository

    path = tmp_path / "memory.sqlite3"
    MemoryRepository(path)
    restarted = MemoryRepository(path)
    with restarted.connection() as db:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone()[0].upper().replace(" ", "").replace("\n", "")
        assert "CHECK(REASONING_EFFORTIN('OFF','LOW','MEDIUM','HIGH','XHIGH'))" in sql
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO conversations(conversation_id, owner_id, title, created_at, updated_at, reasoning_effort) VALUES ('bad', 'owner', 'bad', 'now', 'now', 'invalid')")


def test_legacy_v7_check_repair_preserves_current_conversation_data(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    path = tmp_path / "legacy-v7.sqlite3"
    repo = MemoryRepository(path)
    conversation = repo.create_conversation("local-user", reasoning_effort="low")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "retained", status="completed")
    with repo.connection() as db:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone()[0]
        sql = sql.replace(", CHECK(reasoning_effort IN ('off','low','medium','high','xhigh'))", "")
        db.execute("PRAGMA writable_schema=ON")
        db.execute("UPDATE sqlite_master SET sql=? WHERE type='table' AND name='conversations'", (sql,))
        db.execute("PRAGMA writable_schema=OFF")
        db.execute("PRAGMA schema_version=211")
    restarted = MemoryRepository(path)
    assert restarted.get_conversation(conversation.conversation_id, "local-user").reasoning_effort == "low"
    assert restarted.get_message(user.message_id, "local-user").content == "retained"
    with restarted.connection() as db:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone()[0].upper().replace(" ", "").replace("\n", "")
        assert "CHECK(REASONING_EFFORTIN('OFF','LOW','MEDIUM','HIGH','XHIGH'))" in sql


def test_same_effort_updates_preserve_conversation_and_preference_timestamps(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    repo = MemoryRepository(tmp_path / "timestamps.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="low")
    fixed = "2026-01-01T00:00:00+00:00"
    with repo.transaction() as db:
        db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (fixed, conversation.conversation_id))
        db.execute("UPDATE user_chat_preferences SET last_reasoning_effort='low', updated_at=? WHERE owner_id=?", (fixed, "local-user"))
    updated, _, returned_at = repo.update_conversation_reasoning(conversation.conversation_id, "local-user", "low")
    assert updated.updated_at.isoformat() == fixed
    assert returned_at.isoformat() == fixed
    with repo.connection() as db:
        assert db.execute("SELECT updated_at FROM user_chat_preferences WHERE owner_id='local-user'").fetchone()[0] == fixed
    updated_again = repo.update_conversation(conversation.conversation_id, "local-user", reasoning_effort="low")
    assert updated_again.updated_at.isoformat() == fixed


def test_persisted_event_sequence_is_monotonic(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = repo.create_conversation("local-user")
    message = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="streaming")
    assert repo.record_event_seq(message.message_id, "local-user", 2)
    assert not repo.record_event_seq(message.message_id, "local-user", 1)
    assert repo.get_message(message.message_id, "local-user").last_event_seq == 2


def test_explicit_message_effort_updates_conversation_and_preference_atomically(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    repo = MemoryRepository(tmp_path / "message-preference.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="low")
    updated, user, assistant = repo.create_message_pair(
        conversation.conversation_id,
        "local-user",
        "hello",
        model="m",
        mode="normal",
        reasoning_effort="xhigh",
        update_preference=True,
    )
    assert updated.reasoning_effort == "xhigh"
    assert user.role == "user" and assistant.parent_message_id == user.message_id
    assert repo.get_last_reasoning_effort("local-user") == "xhigh"
