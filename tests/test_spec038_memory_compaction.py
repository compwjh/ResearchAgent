"""spec-038 P3：L3 上下文压缩联动测试。

覆盖四大交付：
1. **flush_memories**：压缩前挂载；高置信度直写 MD、不确定走 pending；开关与 fail-open（失败不得阻断压缩）。
2. **LLM 重构摘要 + 规则降级**：``COMPACTION_SUMMARY_MODE=llm`` 走 LLM；超时/异常回落到 ``build_rule_summary``
   并记录 ``degraded_reason``；``mode=rule`` 完全走规则。
3. **工具输出裁剪**：旧步骤结构化塌缩为一行，最近 N 步保留原文。
4. **置信度分级判据**：``explicit`` + 高 confidence + scope 明确 → 直写；``ambiguous`` / 低 confidence → pending。

全部离线可跑：不连 Ollama / reranker；LLM 路径用 mock，降级路径用「不可达真实链路」覆盖。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.chat.application import context_compaction, conversation_service
from backend.app.chat.application.conversation_service import MemoryAnalysisWorker, MemoryIntent
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository


@pytest.fixture(autouse=True)
def _isolated_memory_dir(tmp_path, monkeypatch):
    """隔离默认 MEMORY_DIR：worker/压缩器缺省构造的 store 绝不落到真实 data/memory。

    两个 worker 与 CompactionWorker 在缺省参数下会自行构造 ``MarkdownMemoryStore()``；
    若不在测试层隔离，测试会污染仓库真实记忆目录（并影响依赖真实文件空的既有用例）。
    """
    sandbox = tmp_path / "default-memory"
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", str(sandbox))
    monkeypatch.setattr("backend.app.platform.config.MEMORY_DIR", sandbox)
    # 默认认为模型「可达」：mock 场景下由测试自己控制分类/摘要来源；
    # 真实降级用例会显式覆盖该探测或注入 ConnectionError。
    monkeypatch.setattr(context_compaction, "llm_available", lambda timeout=1.0: True)
    return sandbox


def _msg(role, content, mid=None, when=None):
    from datetime import datetime, timezone

    return SimpleNamespace(
        role=role,
        content=content,
        message_id=mid or f"m-{abs(hash(content))}",
        created_at=when or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


# ============================================================ 1. flush_memories


def test_flush_writes_high_confidence_memory_to_md(tmp_path: Path):
    """高置信度 + scope 明确 → 直写 MEMORY.md / projects/<id>.md。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    messages = [_msg("user", "请记住：所有项目都用中文回答", mid="u1")]

    with patch.object(
        conversation_service,
        "classify_memory_intent",
        return_value=MemoryIntent("explicit", "所有项目都用中文回答", "global", 0.95),
    ):
        written = context_compaction.flush_memories(messages, project_id=None, store=store)

    assert written >= 1
    assert "所有项目都用中文回答" in store.read_user() or "所有项目都用中文回答" in store.memory_path.read_text()
    assert store.list_pending() == []


def test_flush_ambiguous_goes_to_pending(tmp_path: Path):
    """不确定（ambiguous 或低置信度）→ 只写 PENDING.md，不落正式记忆。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    messages = [_msg("user", "我通常喜欢先给结论", mid="u1")]

    with patch.object(
        conversation_service,
        "classify_memory_intent",
        return_value=MemoryIntent("ambiguous", "喜欢先给结论", "project", 0.6),
    ):
        context_compaction.flush_memories(messages, project_id="proj-a", store=store)

    pending = store.list_pending()
    assert pending and "喜欢先给结论" in pending[0].content
    # 不得写进项目正式记忆
    assert "喜欢先给结论" not in store.read_project("proj-a")


def test_flush_disabled_writes_nothing(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path / "memory")
    messages = [_msg("user", "请记住：明天要交报告", mid="u1")]
    with patch.object(context_compaction, "FLUSH_MEMORIES_ENABLED", False), patch.object(
        conversation_service,
        "classify_memory_intent",
        return_value=MemoryIntent("explicit", "明天要交报告", "project", 0.99),
    ) as classifier:
        written = context_compaction.flush_memories(messages, project_id="proj-a", store=store)
    assert written == 0
    assert classifier.call_count == 0
    assert store.list_pending() == []


def test_flush_failure_is_fail_open(tmp_path: Path):
    """flush 内部异常绝不抛出（压缩必须继续）。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    messages = [_msg("user", "请记住点什么", mid="u1")]
    with patch.object(conversation_service, "classify_memory_intent", side_effect=RuntimeError("offline")):
        # 不抛异常即通过
        written = context_compaction.flush_memories(messages, project_id=None, store=store)
    assert written == 0


# ============================================================ 2. LLM 摘要 + 降级


def test_llm_summary_used_when_mode_llm(tmp_path: Path):
    messages = [_msg("user", "你必须每天备份数据", mid="u1"), _msg("assistant", "好的", mid="a1")]

    class Run:
        events = iter([{"type": "token", "content": "【重构摘要】每天备份数据"}])

    with patch.object(context_compaction, "COMPACTION_SUMMARY_MODE", "llm"), patch.object(
        context_compaction, "run_chat", return_value=Run()
    ):
        summary, char_count, est_tokens, content_hash = context_compaction.build_compaction_summary(
            messages, 3000
        )
    assert "重构摘要" in summary
    assert char_count > 0 and content_hash


def test_llm_summary_falls_back_to_rule_when_unreachable():
    """Ollama 不可达 → 必须回落规则摘要，且不抛异常。

    用 ``ConnectionError`` 模拟真实的「11434 端口不可达」（本机 Ollama 未启动时
    ``run_chat`` 正是抛这类错误）；不 mock 降级逻辑本体，只 mock 网络调用。
    """
    messages = [_msg("user", "你必须每天备份数据", mid="u1")]
    with patch.object(context_compaction, "COMPACTION_SUMMARY_MODE", "llm"), patch.object(
        context_compaction, "run_chat", side_effect=ConnectionError("connection refused: 11434")
    ):
        summary, char_count, est_tokens, content_hash = context_compaction.build_compaction_summary(messages, 3000)
    assert "【指令与约束】" in summary  # 规则摘要特征
    assert char_count > 0 and est_tokens > 0 and content_hash


def test_llm_summary_skips_call_when_model_unreachable():
    """模型端口不可达 → 快速回落（不发起可能重试数十秒的调用）。"""
    messages = [_msg("user", "你必须每天备份数据", mid="u1")]
    with patch.object(context_compaction, "COMPACTION_SUMMARY_MODE", "llm"), patch.object(
        context_compaction, "llm_available", return_value=False
    ), patch.object(context_compaction, "run_chat") as run:
        summary, *_ = context_compaction.build_compaction_summary(messages, 3000)
    assert run.call_count == 0
    assert "【指令与约束】" in summary


def test_flush_skips_when_model_unreachable(tmp_path: Path):
    """模型不可达 → flush 直接跳过（返回 0，不写任何文件）。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    with patch.object(context_compaction, "llm_available", return_value=False), patch.object(
        conversation_service, "classify_memory_intent"
    ) as classifier:
        written = context_compaction.flush_memories([_msg("user", "记住要点", mid="u1")], project_id=None, store=store)
    assert written == 0
    assert classifier.call_count == 0


def test_llm_summary_falls_back_and_records_degraded_reason():
    messages = [_msg("user", "你必须每天备份数据", mid="u1")]
    recorded = []

    def _record(**kwargs):
        recorded.append(kwargs)

    with patch.object(context_compaction, "COMPACTION_SUMMARY_MODE", "llm"), patch.object(
        context_compaction, "run_chat", side_effect=RuntimeError("connection refused")
    ), patch.object(context_compaction, "record_event", _record, create=True):
        summary, *_ = context_compaction.build_compaction_summary(messages, 3000)
    assert "【指令与约束】" in summary
    assert any("degraded_reason" in (item.get("metadata") or {}) for item in recorded)


def test_rule_mode_never_calls_llm():
    messages = [_msg("user", "你必须每天备份数据", mid="u1")]
    with patch.object(context_compaction, "COMPACTION_SUMMARY_MODE", "rule"), patch.object(
        context_compaction, "run_chat"
    ) as run:
        summary, *_ = context_compaction.build_compaction_summary(messages, 3000)
    assert run.call_count == 0
    assert "【指令与约束】" in summary


# ============================================================ 3. 工具输出裁剪


def test_collapse_tool_outputs_keeps_recent_raw():
    steps = [
        SimpleNamespace(kind="tool", label="search", summary="A" * 200, status="completed", started_at=None),
        SimpleNamespace(kind="tool", label="read", summary="B" * 200, status="completed", started_at=None),
        SimpleNamespace(kind="tool", label="write", summary="C" * 200, status="completed", started_at=None),
    ]
    with patch.object(context_compaction, "CHAT_TOOL_OUTPUT_KEEP_RECENT", 1):
        rendered = context_compaction.collapse_tool_outputs(steps, keep_recent=1)
    assert "write" in rendered
    # 最近一步保留原文；更早步骤塌缩为一行摘要
    assert "C" * 200 in rendered
    assert "A" * 200 not in rendered
    assert "B" * 200 not in rendered


def test_collapse_tool_outputs_empty():
    assert context_compaction.collapse_tool_outputs([], keep_recent=2) == ""


# ============================================================ 4. 置信度分级（analysis worker）


def _job(repo, project_id=None, content="hello", owner="owner-a"):
    conversation, user, _ = repo.create_conversation_messages(owner, content, project_id, "model", "normal")
    return conversation, user, repo.create_memory_analysis_job(user.message_id, owner)


def test_high_confidence_explicit_writes_md(tmp_path: Path):
    messages = [_msg("user", "请记住：结论优先", mid="u1")]
    store = MarkdownMemoryStore(tmp_path / "memory")
    with patch.object(
        conversation_service, "classify_memory_intent",
        return_value=MemoryIntent("explicit", "结论优先", "project", 0.95),
    ):
        context_compaction.flush_memories(messages, project_id="proj-a", store=store)
    assert "结论优先" in store.read_project("proj-a")


def test_analysis_worker_high_confidence_auto_saves_to_md(tmp_path: Path):
    """MemoryAnalysisWorker：高置信度 explicit → 直写 MD，审计项记 auto_saved。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    store = MarkdownMemoryStore(tmp_path / "memory")
    project = repo.create_project("owner-a", "P")
    _, user, job = _job(repo, project.project_id, "请记住以后先给结论")
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a", memory_store=store)
    with patch.object(
        conversation_service, "classify_memory_intent",
        return_value=MemoryIntent("explicit", "以后先给结论", "project", 0.95),
    ):
        worker.process(job.analysis_id)
    items, _ = repo.list_memory_analysis_items(user.message_id, "owner-a")
    assert items and items[0].decision_status == "auto_saved"
    assert "以后先给结论" in store.read_project(project.project_id)


def test_analysis_worker_ambiguous_stays_pending(tmp_path: Path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    store = MarkdownMemoryStore(tmp_path / "memory")
    project = repo.create_project("owner-a", "P")
    _, user, job = _job(repo, project.project_id, "我通常喜欢先给结论")
    worker = MemoryAnalysisWorker(repo, owner_id="owner-a", memory_store=store)
    with patch.object(
        conversation_service, "classify_memory_intent",
        return_value=MemoryIntent("ambiguous", "喜欢先给结论", "project", 0.6),
    ):
        worker.process(job.analysis_id)
    items, _ = repo.list_memory_analysis_items(user.message_id, "owner-a")
    assert items and items[0].decision_status == "pending_confirmation"
    assert store.list_pending()
