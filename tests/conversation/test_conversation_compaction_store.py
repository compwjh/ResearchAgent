"""Conversation segment and compaction repository migration tests.

仅覆盖本阶段交付的仓储能力：建表幂等、schema 校验、段写入与按 seq 读取、
跨会话/跨项目隔离、next_segment_start_message 四种情形、并发领用（部分唯一索引
原子抢锁）与终态后可再建新 job。装配消费与 worker 属第二阶段，不在本文件范围。
"""

from backend.app.memory.repository import MemoryRepository


def _make_repo(tmp_path):
    return MemoryRepository(tmp_path / "memory.sqlite3")


def test_tables_created_and_indexes_idempotent(tmp_path):
    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    repo.initialize()
    repo.initialize()  # 连续第二次初始化必须幂等（含索引）
    with repo.connection() as db:
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        indexes = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "conversation_segments" in tables
    assert "conversation_compaction_jobs" in tables
    assert "idx_conversation_segments_seq" in indexes
    assert "idx_compaction_job_active" in indexes


def test_compression_schema_survives_baseline_reset(tmp_path):
    """压缩相关表必须存在于重置后的新基线。

    直接断言基线表存在，保留「压缩能力未被基线重置误删」的校验意图。
    """
    repo = _make_repo(tmp_path)
    with repo.connection() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"conversation_segments", "conversation_compaction_jobs"} <= tables


def test_segment_write_and_seq_ordering(tmp_path):
    repo = _make_repo(tmp_path)
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id)
    m1 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m1", status="completed")
    m2 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m2", status="completed")
    m3 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m3", status="completed")
    s1 = repo.append_conversation_segment(
        conversation.conversation_id, "owner-a", project.project_id, 1,
        m1.message_id, m2.message_id, len("summary-1"), 10, "h1", "summary-1",
    )
    s2 = repo.append_conversation_segment(
        conversation.conversation_id, "owner-a", project.project_id, 2,
        m2.message_id, m3.message_id, len("summary-2"), 12, "h2", "summary-2",
    )
    assert s1.seq == 1 and s2.seq == 2
    assert s1.owner_id == "owner-a"
    assert s1.project_id == project.project_id
    assert s1.generator == "rule"
    segments = repo.list_conversation_segments(conversation.conversation_id, "owner-a", project.project_id)
    assert [s.seq for s in segments] == [1, 2]
    assert segments[0].segment_id == s1.segment_id
    assert segments[1].segment_id == s2.segment_id
    assert segments[1].to_message_id == m3.message_id
    assert segments[0].summary_text == "summary-1"


def test_cross_owner_and_project_isolation(tmp_path):
    repo = _make_repo(tmp_path)
    pA = repo.create_project("owner-a", "PA")
    pB = repo.create_project("owner-b", "PB")
    cA = repo.create_conversation("owner-a", pA.project_id)
    cB = repo.create_conversation("owner-b", pB.project_id)
    cU = repo.create_conversation("owner-a", None)  # 未绑定项目
    mA = repo.create_message(cA.conversation_id, "owner-a", "user", "a", status="completed")
    mB = repo.create_message(cB.conversation_id, "owner-b", "user", "b", status="completed")
    mU = repo.create_message(cU.conversation_id, "owner-a", "user", "u", status="completed")
    repo.append_conversation_segment(cA.conversation_id, "owner-a", pA.project_id, 1, mA.message_id, mA.message_id, 1, 1, "h", "A")
    repo.append_conversation_segment(cB.conversation_id, "owner-b", pB.project_id, 1, mB.message_id, mB.message_id, 1, 1, "h", "B")
    repo.append_conversation_segment(cU.conversation_id, "owner-a", None, 1, mU.message_id, mU.message_id, 1, 1, "h", "U")
    # A 取不到 B（跨 owner）
    assert repo.list_conversation_segments(cB.conversation_id, "owner-a", pB.project_id) == []
    # B 取不到 A（跨 owner）
    assert repo.list_conversation_segments(cA.conversation_id, "owner-b", pA.project_id) == []
    # 严格匹配项目：A 的会话用 B 的项目 id 查不到
    assert repo.list_conversation_segments(cA.conversation_id, "owner-a", pB.project_id) == []
    # A 正常取到自己的段
    assert len(repo.list_conversation_segments(cA.conversation_id, "owner-a", pA.project_id)) == 1
    # 未绑定项目的会话：project_id=None 才取到，指定项目则取不到
    assert len(repo.list_conversation_segments(cU.conversation_id, "owner-a", None)) == 1
    assert repo.list_conversation_segments(cU.conversation_id, "owner-a", pA.project_id) == []


def test_next_segment_start_message_cases(tmp_path):
    repo = _make_repo(tmp_path)
    conversation = repo.create_conversation("owner-a", None)
    m1 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m1", status="completed")
    m2 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m2", status="completed")
    m3 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m3", status="completed")
    m4 = repo.create_message(conversation.conversation_id, "owner-a", "user", "m4", status="completed")
    # 情形 1：无段 → 最早一条消息 id
    assert repo.next_segment_start_message(conversation.conversation_id, "owner-a") == m1.message_id
    # 情形 2：有段（覆盖到 m2）→ 下一条 m3
    repo.append_conversation_segment(conversation.conversation_id, "owner-a", None, 1, m1.message_id, m2.message_id, 1, 1, "h", "s1")
    assert repo.next_segment_start_message(conversation.conversation_id, "owner-a") == m3.message_id
    # 情形 4：边界（段覆盖到最后一条 m4）→ 返回 None
    repo.append_conversation_segment(conversation.conversation_id, "owner-a", None, 2, m3.message_id, m4.message_id, 1, 1, "h", "s2")
    assert repo.next_segment_start_message(conversation.conversation_id, "owner-a") is None
    # 情形 3：无消息的新会话 → 返回 None
    empty = repo.create_conversation("owner-a", None)
    assert repo.next_segment_start_message(empty.conversation_id, "owner-a") is None


def test_compaction_job_concurrent_claim_only_one_succeeds(tmp_path):
    repo = _make_repo(tmp_path)
    conversation = repo.create_conversation("owner-a", None)
    # 第一次领用成功
    job1 = repo.create_compaction_job(conversation.conversation_id, "owner-a", trigger="auto", est_tokens_before=100)
    assert job1 is not None
    assert job1.status == "queued"
    assert job1.trigger == "auto"
    assert job1.est_tokens_before == 100
    assert job1.finished_at is None
    # 第二次领用（同会话非终态）→ 部分唯一索引冲突，返回 None
    job2 = repo.create_compaction_job(conversation.conversation_id, "owner-a", trigger="auto", est_tokens_before=120)
    assert job2 is None
    # 终态后可再建新 job
    finished = repo.finish_compaction_job(job1.job_id, "owner-a", status="done", est_tokens_after=20)
    assert finished is not None
    assert finished.status == "done"
    assert finished.est_tokens_after == 20
    assert finished.finished_at is not None
    job3 = repo.create_compaction_job(conversation.conversation_id, "owner-a", trigger="manual", est_tokens_before=50)
    assert job3 is not None
    assert job3.status == "queued"
    # 失败收敛
    failed = repo.finish_compaction_job(job3.job_id, "owner-a", status="failed", error="boom")
    assert failed.status == "failed"
    assert failed.error == "boom"
    # 终态后可再建（证明部分唯一索引排除 done/failed）
    job4 = repo.create_compaction_job(conversation.conversation_id, "owner-a", trigger="auto", est_tokens_before=10)
    assert job4 is not None


def test_compaction_job_reads_and_isolation(tmp_path):
    repo = _make_repo(tmp_path)
    conversation = repo.create_conversation("owner-a", None)
    job = repo.create_compaction_job(conversation.conversation_id, "owner-a", trigger="manual", est_tokens_before=30)
    assert repo.get_compaction_job(job.job_id, "owner-a").job_id == job.job_id
    assert repo.get_compaction_job(job.job_id, "owner-b") is None  # 跨 owner 隔离
    latest = repo.get_latest_compaction_job(conversation.conversation_id, "owner-a")
    assert latest is not None and latest.job_id == job.job_id
    assert repo.get_latest_compaction_job("nonexistent", "owner-a") is None
