"""Task10 backend contracts: v7 system rules, scope authorization and roles."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.chat.application.conversation_service import (
    has_explicit_global_intent,
    is_system_rule_intent,
)
from backend.app.api.routes_kb import _kb_evidence_advisory
from backend.app.chat.application.conversation_service import compose_chat_messages
from backend.app.main import app
from backend.app.memory.repository import MemoryRepository, SystemRuleUnavailableError


def test_v7_system_rule_is_idempotent_owner_scoped_and_unicode_bounded(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    repo.initialize()
    with repo.connection() as db:
        assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7
        assert {row["name"] for row in db.execute("PRAGMA table_info(system_rules)")} == {"owner_id", "content", "enabled", "updated_at"}
    assert repo.get_system_rule("owner-a").enabled is False
    saved = repo.upsert_system_rule("owner-a", "🙂" * 12000, False)
    assert len(saved.content) == 12000
    with pytest.raises(ValueError):
        repo.upsert_system_rule("owner-a", "x" * 12001, False)
    assert repo.get_system_rule("owner-b").content == ""
    repo.set_system_rule_enabled("owner-a", True)
    repo.clear_system_rule("owner-a")
    assert repo.get_system_rule("owner-a").enabled is False


def test_system_rule_api_uses_stable_400_409_and_204(tmp_path: Path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        assert client.get("/api/system-rule").json()["enabled"] is False
        assert client.put("/api/system-rule", json={"content": "", "enabled": True}).status_code == 409
        assert client.put("/api/system-rule", json={"content": "x" * 12001, "enabled": False}).status_code == 400
        assert client.put("/api/system-rule", json={"content": "只给结论", "enabled": True}).status_code == 200
        assert client.patch("/api/system-rule", json={"enabled": False}).json()["enabled"] is False
        assert client.delete("/api/system-rule").status_code == 204


def test_global_scope_requires_explicit_original_wording():
    assert has_explicit_global_intent("全局记住：以后所有项目都遵守先给结论")
    assert has_explicit_global_intent("remember this as a global preference")
    assert has_explicit_global_intent("所有对话都使用中文")
    assert has_explicit_global_intent("所有项目都遵守先给结论")
    assert not has_explicit_global_intent("记住我喜欢简洁回答")
    assert not has_explicit_global_intent("以后这个项目先给结论")
    assert not has_explicit_global_intent("全局搜索这篇论文")
    assert not has_explicit_global_intent("所有对话都不要保存")
    assert not has_explicit_global_intent("设为系统规则")
    assert is_system_rule_intent("请设为系统规则")


def test_role_aware_direct_payload_preserves_system_and_user_roles():
    from backend.app.chat.application import chat_runner
    from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

    class Stream:
        result = OllamaChatResult("ok", "", OllamaTimings(), False, 0, 0)

        def __iter__(self):
            yield {"type": "token", "content": "ok"}

    with patch.object(chat_runner, "chat_direct_stream", return_value=Stream()) as direct:
        list(chat_runner.run_chat("q", "m", route="direct", messages=[{"role": "system", "content": "rule"}, {"role": "user", "content": "q"}]))
    assert direct.call_args.args[0] == [{"role": "system", "content": "rule"}, {"role": "user", "content": "q"}]


def test_conversation_messages_are_role_aware_without_user_rule():
    messages = compose_chat_messages("当前问题", [], [], None, None)
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "当前问题"}
    assert "当前问题" not in messages[0]["content"]


def test_kb_advisory_never_contains_current_question():
    hit = type("Hit", (), {"file_name": "paper.md", "page": 2, "text": "evidence"})()
    advisory = _kb_evidence_advisory([hit])
    assert "evidence" in advisory
    assert "问题：" not in advisory


def test_corrupt_v7_system_rule_table_fails_closed(tmp_path: Path):
    path = tmp_path / "corrupt.sqlite3"
    repo = MemoryRepository(path)
    with repo.connection() as db:
        db.execute("DROP TABLE system_rules")
        db.execute("CREATE TABLE system_rules(owner_id TEXT PRIMARY KEY, content TEXT, enabled TEXT, updated_at INTEGER)")
    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)


def test_malformed_system_rule_row_returns_stable_unavailable_error(tmp_path: Path):
    path = tmp_path / "malformed-rule.sqlite3"
    repo = MemoryRepository(path)
    repo.upsert_system_rule("local-user", "只给结论", True)
    with repo.transaction() as db:
        db.execute("UPDATE system_rules SET updated_at=? WHERE owner_id=?", ("not-a-timestamp", "local-user"))
    with pytest.raises(SystemRuleUnavailableError, match="SYSTEM_RULE_UNAVAILABLE"):
        repo.get_system_rule("local-user")

    with patch("backend.app.api.routes_conversations._repo", return_value=repo):
        response = TestClient(app).get("/api/system-rule")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SYSTEM_RULE_UNAVAILABLE"


def test_observation_input_is_redacted_but_role_metadata_is_preserved():
    from backend.app.platform.observability import prompt_observation_metadata, redact_prompt_messages

    messages = [{"role": "system", "content": "secret rule"}, {"role": "user", "content": "secret question"}]
    assert redact_prompt_messages(messages) == [{"role": "system", "content": ""}, {"role": "user", "content": ""}]
    assert prompt_observation_metadata(messages, system_rule_enabled=True) == {
        "role_count": 2,
        "role_names": ["system", "user"],
        "char_counts": [11, 15],
        "system_rule_enabled": True,
    }
