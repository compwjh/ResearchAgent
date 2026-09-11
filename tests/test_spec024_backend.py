"""Task03 backend contract tests (red first, then implementation)."""

import json
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


def test_schema_v7_marker_and_restart_are_idempotent(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    with repo.connection() as db:
        assert db.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 7
        marker = db.execute("SELECT before_counts_json, backup_id FROM migration_markers WHERE marker='conversation_history_reset_v1'").fetchone()
        matrix = json.loads(marker[0])
        assert set(matrix) >= {"conversations", "messages", "memory_evidence", "projects", "memories", "system_rules", "skill_improvement_proposals"}
        assert all({"before", "after", "action", "foreign_key_result"} <= set(row) for row in matrix.values())
        assert len(marker[1]) == 64
    MemoryRepository(path)
    with repo.connection() as db:
        assert db.execute("SELECT count(*) FROM migration_markers WHERE marker='conversation_history_reset_v1'").fetchone()[0] == 1


def test_persisted_event_sequence_is_monotonic(tmp_path):
    from backend.app.memory.repository import MemoryRepository

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = repo.create_conversation("local-user")
    message = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="streaming")
    assert repo.record_event_seq(message.message_id, "local-user", 2)
    assert not repo.record_event_seq(message.message_id, "local-user", 1)
    assert repo.get_message(message.message_id, "local-user").last_event_seq == 2
