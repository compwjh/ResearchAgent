"""Spec025 Task03 第二阶段：规则摘要生成器 + 装配消费 + 异步压缩 worker 测试。

覆盖：
1. build_rule_summary：三段式输出、空消息、超长截断、可复现、content_hash 稳定。
2. 无段时 compose_chat_prompt 输出与现状逐字符一致（含 20 条上限、每条 2000、预算截断）。
3. 有段时：历史区含摘要、raw 条数 <= CHAT_RECENT_RAW_MESSAGES、被段覆盖消息不重复出现。
4. worker：入队->段写入->done；异常->failed 且线程存活；同会话连续两次 enqueue 只一个 job；
   冻结窗口外消息不纳入段；空会话不产生空段。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.chat.application import context_compaction
from backend.app.chat.application.context_compaction import (
    build_rule_summary,
    CompactionWorker,
    get_compaction_worker,
)
from backend.app.chat.application.conversation_service import (
    CHAT_RECENT_RAW_MESSAGES,
    _bounded_text,
    compose_chat_prompt,
    memory_prompt,
)
from backend.app.platform.config import CHAT_PROJECT_INSTR_CHARS, CHAT_SUMMARY_BUDGET_CHARS
from backend.app.memory.repository import MemoryRepository


def _msg(role, content, when=None, mid=None):
    return SimpleNamespace(
        role=role,
        content=content,
        created_at=when or datetime(2024, 1, 1, tzinfo=timezone.utc),
        message_id=mid or f"m-{abs(hash(content))}",
    )


# ---------------------------------------------------------------- build_rule_summary


def test_build_rule_summary_three_sections():
    messages = [
        _msg("user", "请处理这个任务。你必须每天备份数据。", mid="u1"),
        _msg("assistant", "好的。我们决定采用方案B。这是结论。", mid="a1"),
        _msg("user", "参考 https://example.com/doc.pdf 与文件 report.csv，表 conversation_segments 有 8000 token 预算。", mid="u2"),
    ]
    summary, char_count, est_tokens, content_hash = build_rule_summary(messages, CHAT_SUMMARY_BUDGET_CHARS)
    assert "【指令与约束】" in summary
    assert "【决策与结论】" in summary
    assert "【关键实体】" in summary
    # 指令句命中「必须」
    assert "你必须每天备份数据" in summary
    # 决策句命中「决定/采用」
    assert "我们决定采用方案B" in summary
    # 实体附 message_id 指针并去重
    assert "https://example.com/doc.pdf [u2]" in summary
    assert "report.csv [u2]" in summary
    assert "conversation_segments [u2]" in summary
    assert "8000 token [u2]" in summary
    # char_count / est_tokens 为被覆盖源文本的统计
    source = "\n".join(m.content for m in messages)
    assert char_count == len(source)
    assert est_tokens == context_compaction.estimate_tokens(source)


def test_build_rule_summary_empty_input():
    summary, char_count, est_tokens, content_hash = build_rule_summary([], CHAT_SUMMARY_BUDGET_CHARS)
    assert summary == ""
    assert char_count == 0
    assert est_tokens == 0
    assert content_hash == hashlib_sha256_empty()


def test_build_rule_summary_overlong_truncation():
    long_constraint = "禁止" + ("重复执行该操作" * 200)  # 远超 per（默认 500）
    messages = [_msg("user", long_constraint, mid="u-long")]
    summary, _, _, _ = build_rule_summary(messages, CHAT_SUMMARY_BUDGET_CHARS)
    section = _section_body(summary, "【指令与约束】")
    per = CHAT_SUMMARY_BUDGET_CHARS // 3
    # 超长截断并加省略标记
    assert section.endswith("…")
    assert len(section) <= per + 1


def test_build_rule_summary_reproducible_and_hash_stable():
    messages = [
        _msg("user", "你必须确认配置。", mid="u1"),
        _msg("assistant", "我们已确认并采用新流程。", mid="a1"),
    ]
    s1 = build_rule_summary(messages, CHAT_SUMMARY_BUDGET_CHARS)
    s2 = build_rule_summary(list(reversed(messages)), CHAT_SUMMARY_BUDGET_CHARS)  # 乱序输入仍按 (created_at, message_id) 稳定
    assert s1[0] == s2[0]
    assert s1[3] == s2[3]
    # 同一输入两次结果完全一致
    again = build_rule_summary(messages, CHAT_SUMMARY_BUDGET_CHARS)
    assert again == s1


def test_build_rule_summary_entity_dedup_across_messages():
    messages = [
        _msg("user", "见文件 report.csv 与 report.csv 重复提及。", mid="u1"),
        _msg("user", "再次见 report.csv。", mid="u2"),
    ]
    summary, _, _, _ = build_rule_summary(messages, CHAT_SUMMARY_BUDGET_CHARS)
    # report.csv 去重，只出现一次
    assert summary.count("report.csv") == 1


# --------------------------------------------------- compose_chat_prompt 等价回退


def _reference_compose(question, history, memories, project_instructions, summaries, *, history_budget_chars=6000):
    """复现改动前 compose_chat_prompt 的「无段」公式，用于逐字符一致性断言。"""
    sections = []
    if project_instructions and project_instructions.strip():
        sections.append("项目明确指令（优先级高于长期记忆）：\n" + _bounded_text(project_instructions.strip(), CHAT_PROJECT_INSTR_CHARS))
    remembered = memory_prompt(memories, summaries, summary_budget_chars=CHAT_SUMMARY_BUDGET_CHARS)
    if remembered:
        sections.append(remembered)
    prior = [m for m in reversed(history or []) if m.role in {"user", "assistant"} and m.content]
    if prior:
        history_text = "\n".join(f"{m.role}: {_bounded_text(m.content, 2000)}" for m in prior[-20:])
        sections.append("会话历史：\n" + _bounded_text(history_text, history_budget_chars))
    sections.append("用户当前问题：\n" + question)
    return "\n\n".join(sections)


def test_compose_no_segment_byte_identical_to_status_quo():
    history = [
        _msg("user", "历史用户消息", mid="h1"),
        _msg("assistant", "历史助手消息", mid="h2"),
    ]
    memories = [SimpleNamespace(scope="project", statement="项目记忆S")]
    project_instructions = "项目指令内容"
    question = "Q"

    actual_none = compose_chat_prompt(question, history, memories, project_instructions, None, segments=None)
    actual_empty = compose_chat_prompt(question, history, memories, project_instructions, None, segments=[])
    expected = _reference_compose(question, history, memories, project_instructions, None)
    assert actual_none == expected
    assert actual_empty == expected


def test_compose_no_segment_caps_prior_to_20_and_2000():
    # 25 条历史（与 list_context_messages 一致：最新在前），无段时只保留最后 20 条，每条 <= 2000
    history = [_msg("user", f"hist-{i}", mid=f"h{i}") for i in range(24, -1, -1)]
    out = compose_chat_prompt("Q", history, [], None, None, segments=None)
    idx = out.index("会话历史：\n")
    hist = out[idx + len("会话历史：\n"):]
    role_lines = [ln for ln in hist.split("\n") if ln.startswith("user: ") or ln.startswith("assistant: ")]
    assert len(role_lines) == 20
    assert all(len(ln) - len("user: ") <= 2000 for ln in role_lines)
    # 最早的 5 条被丢弃
    assert "hist-0" not in hist
    assert "hist-24" in hist


# ----------------------------------------------------- compose_chat_prompt 消费段


def test_compose_with_segment_injects_summary_raw_capped_no_duplicate(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-s", None)
    # 12 条消息：m1..m5 将被段覆盖，m6..m12 为最近原文
    covered = [_msg_through_repo(repo, conversation, "user", f"COVERED_M{i}_NO_CONSTRAINT", f"cm{i}") for i in range(1, 6)]
    recent = [_msg_through_repo(repo, conversation, "user", f"RECENT_M{i}", f"rm{i}") for i in range(6, 13)]
    repo.append_conversation_segment(
        conversation.conversation_id, "owner-s", None, 1,
        covered[0].message_id, covered[-1].message_id,
        len("summary-1"), 10, "hash-1", "段摘要内容 summary-1",
    )
    history = [m for m in repo.list_context_messages(conversation.conversation_id, "owner-s") if m.message_id != "x"]
    segments = repo.list_conversation_segments(conversation.conversation_id, "owner-s", None)
    out = compose_chat_prompt("Q", history, [], None, None, segments=segments)

    # 历史区含段摘要
    assert "会话历史摘要：" in out
    assert "段摘要内容 summary-1" in out
    # raw 条数 <= CHAT_RECENT_RAW_MESSAGES（此处正好 7 条 <= 10）
    idx = out.index("会话历史：\n")
    hist = out[idx + len("会话历史：\n"):]
    raw_part = hist.split("会话历史摘要：")[0]
    role_lines = [ln for ln in raw_part.split("\n") if ln.startswith("user: ") or ln.startswith("assistant: ")]
    assert len(role_lines) <= CHAT_RECENT_RAW_MESSAGES
    # 被段覆盖的消息不重复作为 raw 出现；且无约束词也不会进摘要
    assert "COVERED_M1_NO_CONSTRAINT" not in out
    # 最近原文保留
    assert "RECENT_M12" in out


# ---------------------------------------------------------------- worker


def test_worker_writes_segment_and_finishes_done(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-a", None)
    msgs = [
        repo.create_message(conversation.conversation_id, "owner-a", "user", f"用户{i} 必须处理该任务", status="completed")
        for i in range(1, 6)
    ]
    worker = CompactionWorker(repo).start()
    try:
        job = worker.enqueue(conversation.conversation_id, "owner-a", None, "manual")
        _wait_job_terminal(repo, job.job_id, "owner-a")
        finished = repo.get_compaction_job(job.job_id, "owner-a")
        assert finished.status == "done"
        segments = repo.list_conversation_segments(conversation.conversation_id, "owner-a", None)
        assert len(segments) == 1
        seg = segments[0]
        assert seg.seq == 1
        assert seg.from_message_id == msgs[0].message_id
        assert seg.to_message_id == msgs[-1].message_id
        assert seg.content_hash
        assert "【指令与约束】" in seg.summary_text
    finally:
        worker.stop()


def test_worker_failure_sets_failed_and_thread_alive(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-z", None)
    for i in range(3):
        repo.create_message(conversation.conversation_id, "owner-z", "user", f"m{i}", status="completed")
    worker = CompactionWorker(repo).start()
    try:
        with patch.object(context_compaction, "build_rule_summary", side_effect=RuntimeError("boom")):
            job = worker.enqueue(conversation.conversation_id, "owner-z", None, "manual")
            _wait_job_terminal(repo, job.job_id, "owner-a")
        finished = repo.get_compaction_job(job.job_id, "owner-z")
        assert finished.status == "failed"
        assert finished.error
        assert worker._thread.is_alive()
    finally:
        worker.stop()


def test_concurrent_enqueue_only_one_job(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-y", None)
    repo.create_message(conversation.conversation_id, "owner-y", "user", "a", status="completed")
    worker = CompactionWorker(repo)  # 不启动：只验证领用去重
    job1 = worker.enqueue(conversation.conversation_id, "owner-y", None, "manual")
    job2 = worker.enqueue(conversation.conversation_id, "owner-y", None, "manual")
    assert job2 is not None
    assert job2.job_id == job1.job_id
    count = repo.connection().execute(
        "SELECT COUNT(*) AS c FROM conversation_compaction_jobs WHERE conversation_id=?", (conversation.conversation_id,)
    ).fetchone()["c"]
    assert count == 1


def test_worker_respects_frozen_window(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-x", None)
    msgs = [
        repo.create_message(conversation.conversation_id, "owner-x", "user", f"msg-{i}", status="completed")
        for i in range(1, 6)
    ]
    worker = CompactionWorker(repo).start()
    try:
        job = worker.enqueue(conversation.conversation_id, "owner-x", None, "auto")
        assert job is not None, "首次入队必须领用到 job"
        # 入队之后追加的消息必须被冻结窗口排除
        extra = repo.create_message(conversation.conversation_id, "owner-x", "user", "EXTRA_AFTER_FREEZE", status="completed")
        _wait_job_terminal(repo, job.job_id, "owner-x")
    finally:
        worker.stop()
    segments = repo.list_conversation_segments(conversation.conversation_id, "owner-x", None)
    assert len(segments) == 1
    seg = segments[0]
    # 冻结窗口的 to 取入队时刻最后一条（m5），而非之后追加的 extra
    assert seg.to_message_id == msgs[-1].message_id
    assert "EXTRA_AFTER_FREEZE" not in seg.summary_text


def test_worker_empty_conversation_finishes_done_without_segment(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    conversation = repo.create_conversation("owner-e", None)
    worker = CompactionWorker(repo).start()
    try:
        job = worker.enqueue(conversation.conversation_id, "owner-e", None, "manual")
        assert job is not None, "首次入队必须领用到 job"
        _wait_job_terminal(repo, job.job_id, "owner-e")
        finished = repo.get_compaction_job(job.job_id, "owner-e")
        assert finished.status == "done"
        assert repo.list_conversation_segments(conversation.conversation_id, "owner-e", None) == []
    finally:
        worker.stop()


def test_get_compaction_worker_singleton(tmp_path):
    repo = MemoryRepository(tmp_path / "m.sqlite3")
    w1 = get_compaction_worker(repo)
    w2 = get_compaction_worker(repo)
    assert w1 is w2
    w1.stop()


# ---------------------------------------------------------------- helpers


def hashlib_sha256_empty() -> str:
    import hashlib
    return hashlib.sha256(b"").hexdigest()


def _wait_job_terminal(repo, job_id, owner, timeout=5):
    """轮询等待 job 进入终态（done/failed）；不入队不依赖 Queue.join 的 timeout。"""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = repo.get_compaction_job(job_id, owner)
        if job and job.status in {"done", "failed"}:
            return job
        time.sleep(0.02)
    return repo.get_compaction_job(job_id, owner)


def _section_body(summary: str, title: str) -> str:
    for section in summary.split("\n\n"):
        if section.startswith(title):
            return section[len(title) + 1:]
    return ""


def _msg_through_repo(repo, conversation, role, content, mid):
    return repo.create_message(conversation.conversation_id, "owner-s", role, content, status="completed")
