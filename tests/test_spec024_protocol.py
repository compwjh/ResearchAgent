"""Spec024 Task02 protocol-only probes.

These tests model the frozen contract in an isolated fixture.  They do not
invoke or mutate the production database and deliberately do not implement a
v7 migration in ``backend/``.
"""

import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

import pytest


ENVELOPE_FIELDS = {"type", "message_id", "event_seq", "timestamp"}
TERMINAL = {"completed", "failed", "interrupted"}


def _accept_event(state, last_seq, event):
    """Reference client policy: duplicate/old drop, gap/terminal reject."""
    seq = event["event_seq"]
    if state in TERMINAL:
        return state, last_seq, "drop-terminal"
    if seq <= last_seq:
        return state, last_seq, "drop-old"
    if seq != last_seq + 1:
        return "failed", last_seq, "event-sequence-gap"
    next_state = event.get("state", state)
    if next_state == "done":
        next_state = event.get("status", "completed")
    return next_state, seq, "accepted"


def _filter_reasoning(chunks, limit=20_000):
    raw = "".join(chunks)
    raw = unicodedata.normalize("NFC", raw)
    raw = raw.replace("<|assistant|>", "").replace("<|endoftext|>", "")
    raw = "".join(ch for ch in raw if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    if len(raw) <= limit:
        return raw, False
    marker = "[…中间思考已省略…]"
    head = (limit - len(marker)) // 2
    tail = limit - len(marker) - head
    return raw[:head] + marker + raw[-tail:], True


def _make_v6_fixture(path: Path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(
        """
        CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_version VALUES (6, '2026-09-01T00:00:00+00:00');
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);
        CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id));
        CREATE TABLE messages(message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE);
        CREATE TABLE processing_steps(step_id TEXT PRIMARY KEY, message_id TEXT REFERENCES messages(message_id) ON DELETE CASCADE);
        CREATE TABLE raw_events(event_id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE CASCADE);
        CREATE TABLE conversation_summaries(summary_id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE CASCADE);
        CREATE TABLE evolution_checkpoints(checkpoint_id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE CASCADE);
        CREATE TABLE memories(memory_id TEXT PRIMARY KEY, statement TEXT NOT NULL);
        CREATE TABLE memory_evidence(memory_id TEXT REFERENCES memories(memory_id), conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL, message_id TEXT);
        CREATE TABLE memory_analysis_jobs(analysis_id TEXT PRIMARY KEY, user_message_id TEXT REFERENCES messages(message_id) ON DELETE CASCADE);
        CREATE TABLE memory_analysis_items(item_id TEXT PRIMARY KEY, analysis_id TEXT REFERENCES memory_analysis_jobs(analysis_id) ON DELETE CASCADE);
        CREATE TABLE system_rules(owner_id TEXT PRIMARY KEY, content TEXT NOT NULL);
        CREATE TABLE skill_improvement_proposals(proposal_id TEXT PRIMARY KEY, statement TEXT NOT NULL);
        INSERT INTO projects VALUES ('p1', 'owner-a');
        INSERT INTO conversations VALUES ('c1', 'p1');
        INSERT INTO messages VALUES ('m1', 'c1');
        INSERT INTO processing_steps VALUES ('s1', 'm1');
        INSERT INTO raw_events VALUES ('r1', 'c1');
        INSERT INTO conversation_summaries VALUES ('s2', 'c1');
        INSERT INTO evolution_checkpoints VALUES ('e1', 'c1');
        INSERT INTO memories VALUES ('mem1', 'retain me');
        INSERT INTO memory_evidence VALUES ('mem1', 'c1', 'm1');
        INSERT INTO memory_analysis_jobs VALUES ('j1', 'm1');
        INSERT INTO memory_analysis_items VALUES ('i1', 'j1');
        INSERT INTO system_rules VALUES ('owner-a', 'retain rule');
        INSERT INTO skill_improvement_proposals VALUES ('sp1', 'retain proposal');
        """
    )
    db.commit()
    db.close()


def _snapshot(db):
    tables = [
        "conversations", "messages", "processing_steps", "raw_events",
        "conversation_summaries", "evolution_checkpoints", "memory_analysis_jobs",
        "memory_analysis_items", "memory_evidence", "projects", "memories",
        "system_rules", "skill_improvement_proposals",
    ]
    counts = {name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in tables}
    schema = db.execute("SELECT max(version) FROM schema_version").fetchone()[0]
    return counts, schema


def _run_v7_contract(path: Path, fail_after=None):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    before = _snapshot(db)
    backup_path = path.with_suffix(".backup.sqlite3")
    backup = sqlite3.connect(backup_path)
    db.backup(backup)
    backup.close()
    backup_id = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    db.execute("BEGIN IMMEDIATE")
    stages = ["create-metadata", "alter-conversations", "alter-messages", "delete-derived", "delete-core", "null-evidence", "marker", "version"]
    try:
        db.execute("CREATE TABLE migration_markers(marker TEXT PRIMARY KEY, applied_at TEXT NOT NULL, before_counts_json TEXT NOT NULL, backup_id TEXT NOT NULL)")
        db.execute("CREATE TABLE user_chat_preferences(owner_id TEXT PRIMARY KEY, last_reasoning_effort TEXT NOT NULL DEFAULT 'xhigh', updated_at TEXT NOT NULL)")
        db.execute("INSERT INTO user_chat_preferences(owner_id, updated_at) VALUES ('owner-a', '2026-09-12T00:00:00+00:00')")
        if fail_after == "create-metadata": raise RuntimeError(fail_after)
        db.execute("ALTER TABLE conversations ADD COLUMN reasoning_effort TEXT NOT NULL DEFAULT 'xhigh'")
        if fail_after == "alter-conversations": raise RuntimeError(fail_after)
        for column in (
            "reasoning_content TEXT", "reasoning_status TEXT", "reasoning_started_at TEXT",
            "reasoning_completed_at TEXT", "first_reasoning_at TEXT",
            "first_answer_token_at TEXT", "reasoning_truncated INTEGER NOT NULL DEFAULT 0",
            "reasoning_chars INTEGER NOT NULL DEFAULT 0", "last_event_seq INTEGER NOT NULL DEFAULT 0",
        ):
            db.execute(f"ALTER TABLE messages ADD COLUMN {column}")
        if fail_after == "alter-messages": raise RuntimeError(fail_after)
        for table in ("processing_steps", "raw_events", "conversation_summaries", "evolution_checkpoints", "memory_analysis_items", "memory_analysis_jobs"):
            db.execute(f"DELETE FROM {table}")
        if fail_after == "delete-derived": raise RuntimeError(fail_after)
        db.execute("DELETE FROM messages")
        db.execute("DELETE FROM conversations")
        if fail_after == "delete-core": raise RuntimeError(fail_after)
        db.execute("UPDATE memory_evidence SET conversation_id=NULL, message_id=NULL")
        if fail_after == "null-evidence": raise RuntimeError(fail_after)
        db.execute("INSERT INTO migration_markers VALUES ('conversation_history_reset_v1', '2026-09-12T00:00:00+00:00', ?, ?)", (json.dumps(before[0], sort_keys=True), backup_id))
        if fail_after == "marker": raise RuntimeError(fail_after)
        db.execute("INSERT INTO schema_version VALUES (7, '2026-09-12T00:00:00+00:00')")
        if fail_after == "version": raise RuntimeError(fail_after)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return db, before, backup_id


def test_sse_event_sequence_reference_contract():
    event = {"type": "reasoning_delta", "message_id": "a1", "event_seq": 1, "timestamp": "2026-09-12T00:00:00Z", "content": "x"}
    assert ENVELOPE_FIELDS <= event.keys()
    state, seq, result = _accept_event("reasoning_running", 0, event)
    assert (state, seq, result) == ("reasoning_running", 1, "accepted")
    assert _accept_event(state, seq, event)[2] == "drop-old"
    assert _accept_event(state, seq, {**event, "event_seq": 3})[2] == "event-sequence-gap"
    state, seq, _ = _accept_event(state, seq, {**event, "event_seq": 2, "type": "done", "status": "completed", "state": "done"})
    assert (state, seq) == ("completed", 2)
    assert _accept_event(state, seq, {**event, "event_seq": 3})[2] == "drop-terminal"


def test_reasoning_filter_cross_chunk_nfc_control_and_codepoint_limit():
    filtered, truncated = _filter_reasoning(["e", "\u0301<|assistant|>", "\x00\n", "🙂"])
    assert filtered == "é\n🙂"
    assert truncated is False
    filtered, truncated = _filter_reasoning(["🙂" * 25_000])
    assert truncated is True
    assert len(filtered) == 20_000
    assert "中间思考已省略" in filtered


def test_v7_cleanup_matrix_commits_and_preserves_long_lived_rows(tmp_path):
    path = tmp_path / "v6.sqlite3"
    _make_v6_fixture(path)
    db, before, backup_id = _run_v7_contract(path)
    assert db.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 7
    assert db.execute("SELECT count(*) FROM migration_markers WHERE marker='conversation_history_reset_v1'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM conversations").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM memory_analysis_jobs").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    assert tuple(db.execute("SELECT conversation_id, message_id FROM memory_evidence").fetchone()) == (None, None)
    assert db.execute("SELECT count(*) FROM system_rules").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM skill_improvement_proposals").fetchone()[0] == 1
    assert db.execute("SELECT last_reasoning_effort FROM user_chat_preferences WHERE owner_id='owner-a'").fetchone()[0] == "xhigh"
    assert {row[1] for row in db.execute("PRAGMA table_info(messages)")} >= {
        "reasoning_content", "reasoning_status", "reasoning_started_at", "reasoning_completed_at",
        "first_reasoning_at", "first_answer_token_at", "reasoning_truncated", "reasoning_chars", "last_event_seq",
    }
    assert len(backup_id) == 64
    assert before[0]["projects"] == 1 and before[0]["memories"] == 1
    db.close()


@pytest.mark.parametrize("stage", ["create-metadata", "alter-conversations", "alter-messages", "delete-derived", "delete-core", "null-evidence", "marker", "version"])
def test_v7_cleanup_rollback_restores_each_injected_stage(tmp_path, stage):
    path = tmp_path / f"rollback-{re.sub(r'[^a-z]+', '-', stage)}.sqlite3"
    _make_v6_fixture(path)
    db = sqlite3.connect(path)
    before = _snapshot(db)
    db.close()
    with pytest.raises(RuntimeError, match=stage):
        _run_v7_contract(path, fail_after=stage)
    db = sqlite3.connect(path)
    assert _snapshot(db) == before
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='migration_markers'").fetchone() is None
    db.close()


def test_current_sse_helper_is_not_yet_v7_envelope():
    from backend.app.api.common import stream_event

    payload = json.loads(stream_event("token", content="x").split("data: ", 1)[1])
    assert set(payload) == {"type", "content"}


def test_current_paths_are_separated_for_reasoning_audit():
    graph_source = Path("backend/app/chat/application/chat_graph.py").read_text()
    runner_source = Path("backend/app/chat/application/chat_runner.py").read_text()
    direct_source = Path("backend/app/platform/ollama_direct.py").read_text()
    spans_source = Path("backend/app/platform/observability/spans.py").read_text()
    assert "message.get(\"thinking\")" in direct_source
    assert "additional_kwargs" not in graph_source
    assert 'thinking=""' in runner_source
    assert '"thinking": _truncate(result.thinking' in spans_source
