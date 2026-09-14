"""spec-038 P1：L1 文件记忆注入链与配置契约测试。

覆盖：
- 新增配置项 MEMORY_DIR / MEMORY_INJECT_MAX_CHARS 的默认值与解析
- 本阶段**不得**改动 CHAT_* 预算默认值（P3 范围，防冲突）
- compose_chat_prompt 叠加文件记忆快照（不破坏既有 DB 记忆段）
- 三处 routes 的 USER.md 注入 fail-open（缺文件返回空串、绝不抛异常）

全部离线可跑：不依赖 Ollama / reranker / 网络。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.chat.application.conversation_service import (
    compose_chat_prompt,
    file_memory_snapshot,
)
from backend.app.memory.markdown_store import MarkdownMemoryStore, read_user_memory_or_empty

# ------------------------------------------------------------------ 配置契约


def test_memory_config_defaults_are_task_specified():
    from backend.app.platform import config

    assert Path(config.MEMORY_DIR) == config.BASE_DIR / "data" / "memory"
    assert config.MEMORY_INJECT_MAX_CHARS == 6000


def test_chat_budget_defaults_after_p3_bump():
    """spec-038 P3 已上调部分 CHAT_* 预算默认值（P1 原「不得改」约束在 P3 解除）。

    - CHAT_TOTAL_TOKEN_BUDGET: 8000 → 20000
    - CHAT_RAG_BUDGET_CHARS:   6000 → 12000
    - CHAT_SUMMARY_BUDGET_CHARS: 1500 → 3000
    - CHAT_PROJECT_INSTR_CHARS: 5000（未变）
    - CHAT_COMPACT_TRIGGER_RATIO: 0.8（未变，明确不动）
    """
    from backend.app.platform import config

    assert config.CHAT_TOTAL_TOKEN_BUDGET == 20000
    assert config.CHAT_RAG_BUDGET_CHARS == 12000
    assert config.CHAT_SUMMARY_BUDGET_CHARS == 3000
    assert config.CHAT_PROJECT_INSTR_CHARS == 5000
    assert config.CHAT_COMPACT_TRIGGER_RATIO == 0.8


def test_memory_inject_max_chars_is_env_positive_number():
    """非法值回退默认并告警（沿用 _env_positive_number 惯例）。"""
    import importlib
    import os

    os.environ["MEMORY_INJECT_MAX_CHARS"] = "not-a-number"
    try:
        from backend.app.platform import config as config_module

        with pytest.warns(RuntimeWarning):
            reloaded = importlib.reload(config_module)
        assert reloaded.MEMORY_INJECT_MAX_CHARS == 6000
    finally:
        os.environ.pop("MEMORY_INJECT_MAX_CHARS", None)
        importlib.reload(config_module)


# ------------------------------------------------------------------ 注入链


def _memory(scope: str, statement: str):
    return SimpleNamespace(scope=scope, statement=statement)


def test_snapshot_section_is_appended_after_db_memory(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.write_user("画像UNIQUE")
    store.append_memory(scope="global", project_id=None, content="全局记忆UNIQUE")

    prompt = compose_chat_prompt(
        "问题",
        [],
        [_memory("project", "DB项目记忆")],
        "项目指令",
        [],
        memory_snapshot=store.load_snapshot(project_id=None, max_chars=6000),
    )
    assert "DB项目记忆" in prompt
    assert "画像UNIQUE" in prompt
    assert "全局记忆UNIQUE" in prompt
    # 既有顺序不变：项目指令 < DB 记忆 < 文件快照 < 问题
    assert (
        prompt.index("项目指令")
        < prompt.index("DB项目记忆")
        < prompt.index("画像UNIQUE")
        < prompt.index("问题")
    )


def test_no_snapshot_keeps_legacy_output_unchanged(tmp_path: Path, monkeypatch):
    """无 MD 文件时输出与改动前完全一致（回归保护）。"""
    monkeypatch.setattr(
        "backend.app.memory.markdown_store.MEMORY_DIR", tmp_path / "empty-memory"
    )
    baseline = compose_chat_prompt(
        "Q", [], [_memory("global", "G")], "I", [], memory_snapshot=""
    )
    assert "长期记忆" in baseline
    assert "L1 文件记忆" not in baseline


def test_file_memory_snapshot_is_fail_open_on_bad_project_id(tmp_path: Path):
    """非法 project_id 由注入链兜底：返回空串而非抛异常，绝不中断会话。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.write_user("画像")
    assert file_memory_snapshot("../evil", store=store) == ""
    # 合法 project_id 正常返回
    assert "画像" in file_memory_snapshot(None, store=store)


def test_file_memory_snapshot_respects_max_chars(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    for index in range(50):
        store.append_memory(scope="global", project_id=None, content=f"条目{index:03d}-{'y' * 50}")
    snapshot = file_memory_snapshot(None, max_chars=300, store=store)
    assert len(snapshot) <= 300
    assert "条目049" in snapshot


def test_compose_chat_messages_accepts_project_id_and_snapshot(tmp_path: Path):
    """回归：compose_chat_messages 必须透传 project_id / memory_snapshot。

    主对话链路（routes_conversations）走的是这个函数；若不透传会抛 TypeError，
    导致整轮生成失败（曾真实发生）。
    """
    from backend.app.chat.application.conversation_service import compose_chat_messages

    store = MarkdownMemoryStore(tmp_path / "memory")
    store.append_memory(scope="project", project_id="proj-a", content="项目记忆UNIQUE")

    messages = compose_chat_messages(
        "问题",
        [],
        [],
        None,
        None,
        system_rule="USER画像",
        project_id="proj-a",
        memory_snapshot=store.load_snapshot(project_id="proj-a", max_chars=6000),
    )
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "问题"}
    joined = "\n".join(item["content"] for item in messages)
    assert "USER画像" in joined
    assert "项目记忆UNIQUE" in joined


def test_compose_chat_messages_without_memory_files_is_unchanged(tmp_path: Path, monkeypatch):
    """无 MD 文件时消息结构不变（platform system + 可选 rule + user）。"""
    from backend.app.chat.application.conversation_service import compose_chat_messages

    monkeypatch.setattr(
        "backend.app.memory.markdown_store.MEMORY_DIR", tmp_path / "empty-memory"
    )
    plain = compose_chat_messages("Q", [], [], None, None)
    assert [item["role"] for item in plain] == ["system", "user"]
    with_rule = compose_chat_messages("Q", [], [], None, None, system_rule="R")
    assert [item["role"] for item in with_rule] == ["system", "system", "user"]



    """未显式传 memory_snapshot 时，compose 走真实读盘路径。"""
    memory_dir = tmp_path / "memory"
    store = MarkdownMemoryStore(memory_dir)
    store.write_user("磁盘画像UNIQUE")
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", memory_dir)

    prompt = compose_chat_prompt("Q", [], [], None, [])
    assert "磁盘画像UNIQUE" in prompt


# ------------------------------------------------------------- routes fail-open


def test_read_user_memory_or_empty_is_fail_open(tmp_path: Path):
    assert read_user_memory_or_empty() == "" or isinstance(
        read_user_memory_or_empty(), str
    )
    store = MarkdownMemoryStore(tmp_path / "memory")
    assert read_user_memory_or_empty(store) == ""
    store.write_user("  画像内容  ")
    assert read_user_memory_or_empty(store) == "画像内容"


def test_routes_inject_user_md_and_never_raise(tmp_path: Path, monkeypatch):
    """三处旧注入点改为读 USER.md：文件缺失时降级为空串（不抛异常）。"""
    from backend.app.api import routes_article, routes_chat, routes_conversations, routes_kb

    for module in (routes_chat, routes_article, routes_kb, routes_conversations):
        assert hasattr(module, "read_user_memory_or_empty")

    memory_dir = tmp_path / "memory"
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", memory_dir)
    # 文件缺失：返回空串，绝不抛异常
    assert read_user_memory_or_empty() == ""

    store = MarkdownMemoryStore(memory_dir)
    store.write_user("接口画像UNIQUE")
    assert read_user_memory_or_empty() == "接口画像UNIQUE"


def test_routes_no_longer_interrupt_on_system_rule_unavailable():
    """三处旧注入点不得再因系统规则失败而中断接口。"""
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1] / "backend" / "app" / "api"
    for name in ("routes_chat.py", "routes_article.py", "routes_kb.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "SYSTEM_RULE_UNAVAILABLE" not in source, name
