"""spec-038 P1 后半段：全局用户画像（原系统规则）后端契约 + scope 授权 + 角色。

背景
----
``system_rules`` 表已停用：全局用户画像的真相源改为 ``data/memory/USER.md``
（``MarkdownMemoryStore``）。``/api/system-rule`` 四个端点的**对外契约保持不变**
（同样的状态码与 payload 形状），仅底层实现从 SQLite 换成 MD 文件。

因此原用例中「断言 system_rules 表结构 / v7 版本号 / 表损坏 fail-closed」的部分
改写为「USER.md 读写 + 内容长度门控 + 路径隔离」；scope 授权与角色感知的用例
与实现无关，原样保留。
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes_kb import _kb_evidence_advisory
from backend.app.chat.application.conversation_service import (
    compose_chat_messages,
    has_explicit_global_intent,
    is_system_rule_intent,
)
from backend.app.main import app
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository, SystemRuleUnavailableError


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    """把 USER.md 的落盘位置隔离到 tmp，避免污染仓库 data/。"""
    target = tmp_path / "memory"
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", target)
    return target


def test_user_memory_is_read_write_bounded_and_owner_scoped(tmp_path: Path, memory_dir: Path):
    """原 `test_v7_system_rule_is_idempotent_owner_scoped_and_unicode_bounded` 的 MD 等价物。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    repo.initialize()  # 必须仍幂等
    assert repo.get_system_rule("owner-a").enabled is False

    saved = repo.upsert_system_rule("owner-a", "🙂" * 12000, False)
    assert len(saved.content) == 12000
    with pytest.raises(ValueError):
        repo.upsert_system_rule("owner-a", "x" * 12001, False)

    # 内容非空即视为 enabled（MD 模型下 enabled 由内容决定）。
    assert repo.get_system_rule("owner-a").enabled is True
    repo.set_system_rule_enabled("owner-a", False)
    assert repo.get_system_rule("owner-a").content == ""
    assert repo.get_system_rule("owner-a").enabled is False

    # 落盘确实在 USER.md（唯一真相源），且 MD store 读得到同一内容。
    repo.upsert_system_rule("owner-a", "只给结论", True)
    assert "只给结论" in MarkdownMemoryStore(memory_dir).read_user()


def test_system_rule_api_keeps_stable_400_409_and_204(tmp_path: Path, memory_dir: Path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"), patch.object(
        MemoryRepository, "_user_memory_store", staticmethod(lambda: MarkdownMemoryStore(memory_dir))
    ):
        client = TestClient(app)
        assert client.get("/api/system-rule").json()["enabled"] is False
        assert client.put("/api/system-rule", json={"content": "", "enabled": True}).status_code == 409
        assert client.put("/api/system-rule", json={"content": "x" * 12001, "enabled": False}).status_code == 400
        assert client.put("/api/system-rule", json={"content": "只给结论", "enabled": True}).status_code == 200
        assert client.patch("/api/system-rule", json={"enabled": False}).json()["enabled"] is False
        assert client.delete("/api/system-rule").status_code == 204
        # 删除后 USER.md 为空，画像不再注入。
        assert MarkdownMemoryStore(memory_dir).read_user().strip() == ""


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


def test_user_md_write_failure_is_stable_unavailable_error(tmp_path: Path):
    """原 `test_malformed_system_rule_row_returns_stable_unavailable_error` 的 MD 等价物：
    底层文件写入失败时，仓储与 API 都必须给出稳定的 SYSTEM_RULE_UNAVAILABLE（503）。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    with patch("backend.app.memory.markdown_store.MEMORY_DIR", tmp_path / "memory"), patch.object(
        MarkdownMemoryStore, "write_user", side_effect=OSError("disk full")
    ):
        with pytest.raises(SystemRuleUnavailableError, match="SYSTEM_RULE_UNAVAILABLE"):
            repo.upsert_system_rule("local-user", "只给结论", True)

        with patch("backend.app.api.routes_conversations._repo", return_value=repo):
            response = TestClient(app).put("/api/system-rule", json={"content": "只给结论", "enabled": True})
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
