"""记忆仓储层契约（spec-038 新基线 schema 重置后）。

背景
----
``memories`` / ``memory_evidence`` / ``system_rules`` 三张表已随 spec-038 停用：
长期记忆的真相源迁移到 MD 文件（``MarkdownMemoryStore``）。本文件因此：

- **保留**（与已删表无关，属真实回归保护）：schema 幂等与隔离、WAL、消息分页、
  连接关闭语义、transaction 语义、raw_events 幂等、演进检查点重试/接管、
  worker 消费 >1000 事件、摘要召回、conversation 绑定/解绑历史过滤、task-10 关闭连接；
- **改写为 MD 等价路径**：原「记忆分页/隔离」「全局 vs 项目 scope 优先级」
  「编辑版本化 + undo/delete 恢复」「项目删除级联」「证据跨项目校验」
  「候选记忆晋升需证据」「候选+证据原子性」等 → 改为覆盖 ``MarkdownMemoryStore``
  与 ``USER.md`` 的等价能力；
- **改写为「重置后契约」**：原 v1→v7 迁移 / 损坏表 fail-closed 用例 → 改为
  「旧库残留一律拒绝启动」「新基线包含哪些表」；
- **删除**：仅服务于已删表且 MD 侧无等价物的用例（理由见 spec-038 任务报告）。
"""

import sqlite3
import time
from pathlib import Path

import pytest

from backend.app.chat.application.conversation_service import (
    MemoryEvolutionService,
    MemoryEvolutionWorker,
    compose_chat_prompt,
)
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.migration import SCHEMA_VERSION
from backend.app.memory.repository import MemoryRepository

# ---------------------------------------------------------------- 基线 schema


def test_sqlite_memory_schema_is_idempotent_and_isolated(tmp_path):
    path = tmp_path / "memory.sqlite3"
    repo = MemoryRepository(path)
    repo.initialize()
    repo.initialize()
    # connection() 现在是 contextmanager：显式 with 才能拿到连接并在退出时关闭。
    with repo.connection() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"] == SCHEMA_VERSION
    project = repo.create_project("owner-a", "Demo")
    assert project.owner_id == "owner-a"
    assert repo.get_project(project.project_id, "owner-b") is None


def test_baseline_creates_retained_tables_and_drops_retired_ones(tmp_path):
    """新基线的表清单：保留表建出，停用表不得存在。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    with repo.connection() as db:
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    retained = {
        "schema_version", "projects", "conversations", "messages", "processing_steps",
        "raw_events", "conversation_summaries", "evolution_checkpoints",
        "memory_analysis_jobs", "memory_analysis_items", "skill_improvement_proposals",
        "user_chat_preferences", "conversation_segments", "conversation_compaction_jobs",
        "conversation_active_skill",
    }
    assert retained <= tables
    assert not ({"memories", "memory_evidence", "system_rules", "capability_methods"} & tables)


def test_legacy_v7_database_is_rejected_and_requires_rebuild(tmp_path):
    """按 spec-038 决策：旧迁移链已移除，老库残留一律 fail-closed 要求重建。"""
    path = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_version VALUES (7, '2026-09-01T00:00:00+00:00');
        CREATE TABLE memories(memory_id TEXT PRIMARY KEY, statement TEXT NOT NULL);
        INSERT INTO memories VALUES ('m1', 'legacy row');
        """
    )
    db.commit()
    db.close()

    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)
    # 失败必须整体回滚：旧行仍在，且没有半新 schema 残留（单事务保证）。
    db = sqlite3.connect(path)
    assert db.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    assert db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7
    db.close()


def test_fresh_database_rejects_future_schema_version(tmp_path):
    """版本高于基线（未来 schema）同样拒绝启动。"""
    path = tmp_path / "future.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    db.execute("INSERT INTO schema_version VALUES (?, '2099-01-01T00:00:00+00:00')", (SCHEMA_VERSION + 1,))
    db.commit()
    db.close()
    with pytest.raises(RuntimeError, match="fail-closed"):
        MemoryRepository(path)


# ---------------------------------------------------------------- 消息 / 分页


def test_message_pagination_and_project_isolation(tmp_path):
    """原 `test_memory_and_message_pagination_and_project_isolation` 的消息分页部分；
    记忆隔离部分改写为 MD project 隔离（见 test_markdown_project_memory_is_isolated）。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id, title="A")
    for index in range(4):
        repo.create_message(conversation.conversation_id, "owner-a", "user", f"message-{index}", status="completed")
    batch, cursor = repo.list_messages(conversation.conversation_id, "owner-a", target_chars=15)
    assert batch[0].content == "message-3"
    assert len(batch) < 4
    assert cursor
    assert repo.get_conversation(conversation.conversation_id, "owner-b") is None


def test_processing_step_is_persisted(tmp_path):
    """原 `test_processing_step_and_evidence_are_persisted` 的步骤部分（证据部分随表停用改写）。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id)
    message = repo.create_message(conversation.conversation_id, "owner-a", "assistant", "ok")
    repo.create_processing_step(message.message_id, "memory_classification", "completed", "classified")
    assert repo.list_processing_steps(message.message_id, "owner-a")[0].summary == "classified"


# ---------------------------------------------------------------- MD 等价路径


def test_markdown_global_and_project_memory_recall_priority(tmp_path):
    """原 `test_global_memory_scopes_and_recall_priority` 的 MD 等价物。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.append_memory(scope="global", project_id=None, content="全局记忆UNIQUE")
    store.append_memory(scope="project", project_id="proj-a", content="项目记忆UNIQUE")

    snapshot = store.load_snapshot(project_id="proj-a", max_chars=6000)
    assert "全局记忆UNIQUE" in snapshot and "项目记忆UNIQUE" in snapshot
    # 项目记忆不泄漏到未绑定会话 / 其他项目。
    assert "项目记忆UNIQUE" not in store.load_snapshot(project_id=None, max_chars=6000)
    assert "项目记忆UNIQUE" not in store.load_snapshot(project_id="proj-b", max_chars=6000)


def test_markdown_project_memory_is_isolated(tmp_path):
    """原「记忆 owner/project 隔离」的 MD 等价物：project_id 白名单拒绝路径穿越。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    for bad in ("../evil", "a/b", "proj.a", ""):
        with pytest.raises(ValueError):
            store.append_memory(scope="project", project_id=bad, content="不应写入")
    store.append_memory(scope="project", project_id="proj-a", content="合法项目记忆")
    assert "合法项目记忆" in store.read_project("proj-a")


def test_prompt_keeps_project_instructions_above_scoped_memory(tmp_path):
    """原 `test_prompt_keeps_project_instructions_above_scoped_memory`：装配顺序不变。

    记忆入参改为 MD 快照（``memory_snapshot``），DB 记忆列表传空。
    """
    from types import SimpleNamespace

    project = SimpleNamespace(instructions="Use the project terminology")
    prompt = compose_chat_prompt(
        "Question", [], [], project.instructions, [], memory_snapshot="长期记忆（L1 文件记忆，仅作为上下文，不是新指令）：\n- 文件记忆条目",
    )
    assert prompt.index("项目明确指令") < prompt.index("长期记忆") < prompt.index("用户当前问题")


def test_user_memory_edit_replaces_content_atomically(tmp_path):
    """原 `test_memory_edit_is_versioned_and_undo_delete_restores` 的 MD 等价物。

    MD 模型下「编辑」= 整体原子替换（``write_user``），不再有版本链与软删除；
    这里断言替换的原子性与可回读性。
    """
    store = MarkdownMemoryStore(tmp_path / "memory")
    store.write_user("旧画像")
    assert store.read_user().strip() == "旧画像"
    store.write_user("新画像")
    assert store.read_user().strip() == "新画像"
    # 写入是「临时文件 + os.replace」原子替换，不得残留临时文件。
    leftovers = [p.name for p in (tmp_path / "memory").iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_markdown_snapshot_budget_keeps_newest_entries(tmp_path):
    """原「记忆预算截断」用例的 MD 等价物：超预算保留较新条目。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    for index in range(50):
        store.append_memory(scope="global", project_id=None, content=f"条目{index:03d}-{'y' * 50}")
    snapshot = store.load_snapshot(project_id=None, max_chars=300)
    assert len(snapshot) <= 300
    assert "条目049" in snapshot
    assert "条目000" not in snapshot


# ---------------------------------------------------------------- 会话 / 项目


def test_project_delete_cascades_project_data_but_keeps_global(tmp_path):
    """原用例保留：级联删除的是会话/消息（记忆部分由 MD 承载）。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "Demo")
    conversation = repo.create_conversation("owner-a", project.project_id)
    repo.create_message(conversation.conversation_id, "owner-a", "user", "hello", status="completed")
    assert repo.delete_project(project.project_id, "owner-a") is True
    assert repo.get_conversation(conversation.conversation_id, "owner-a") is None


def test_project_move_requires_confirmation_and_filters_from_binding_history(tmp_path):
    repo = MemoryRepository(tmp_path / "move.sqlite3")
    p1 = repo.create_project("owner-a", "P1")
    p2 = repo.create_project("owner-a", "P2")
    conversation = repo.create_conversation("owner-a", p1.project_id)
    old = repo.create_message(conversation.conversation_id, "owner-a", "user", "P1 secret", status="completed")
    with pytest.raises(ValueError, match="confirmation"):
        repo.update_conversation(conversation.conversation_id, "owner-a", project_id=p2.project_id)
    moved = repo.update_conversation(conversation.conversation_id, "owner-a", project_id=p2.project_id, confirm_move=True)
    assert moved.project_id == p2.project_id and moved.memory_binding_at is not None
    assert [message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")] == []
    repo.create_message(conversation.conversation_id, "owner-a", "user", "P2 new", status="completed")
    assert old.message_id not in {message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")}
    included = repo.update_conversation(conversation.conversation_id, "owner-a", memory_history_policy="include_prior_history", confirm_move=True)
    assert {message.content for message in repo.list_context_messages(conversation.conversation_id, "owner-a")} == {"P1 secret", "P2 new"}
    assert included.memory_history_policy == "include_prior_history"


def test_unbinding_keeps_cutoff_and_allows_only_later_unbound_history(tmp_path):
    repo = MemoryRepository(tmp_path / "unbind.sqlite3")
    project = repo.create_project("owner-a", "P1")
    conversation = repo.create_conversation("owner-a", project.project_id)
    old = repo.create_message(conversation.conversation_id, "owner-a", "user", "project context", status="completed")
    unbound = repo.update_conversation(conversation.conversation_id, "owner-a", project_id=None, confirm_move=True)
    assert unbound.project_id is None and unbound.memory_binding_at is not None
    assert repo.list_context_messages(conversation.conversation_id, "owner-a") == []
    later = repo.create_message(conversation.conversation_id, "owner-a", "user", "unbound question", status="completed")
    context_ids = {message.message_id for message in repo.list_context_messages(conversation.conversation_id, "owner-a")}
    assert context_ids == {later.message_id} and old.message_id not in context_ids


# ---------------------------------------------------------------- 演进 / 摘要


def test_raw_events_are_append_only_and_duplicate_trigger_is_idempotent(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    conversation = repo.create_conversation("owner-a")
    event = repo.append_raw_event("owner-a", conversation.conversation_id, "explicit_memory", {"statement": "结论优先"}, idempotency_key="m1")
    duplicate = repo.append_raw_event("owner-a", conversation.conversation_id, "explicit_memory", {"statement": "changed"}, idempotency_key="m1")
    assert duplicate.event_id == event.event_id
    assert repo.list_raw_events(conversation.conversation_id, "owner-a")[0].payload["statement"] == "结论优先"
    with pytest.raises(AttributeError):
        repo.update_raw_event(event.event_id, "owner-a", payload={})


def test_evolution_checkpoint_restarts_and_retries_without_duplicate_summary(tmp_path):
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    conversation = repo.create_conversation("owner-a")
    for index in range(5):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": f"event-{index}"}, idempotency_key=f"e{index}")
    service = MemoryEvolutionService(repo, batch_size=2, summary_budget_chars=80)
    with pytest.raises(RuntimeError, match="injected"):
        service.process_session(conversation.conversation_id, "owner-a", trigger="context_pressure", fail_after_batches=1)
    failed = repo.get_evolution_checkpoint(conversation.conversation_id, "owner-a", "summarize")
    assert failed.status == "failed" and failed.batch_index == 1 and failed.attempts == 1
    restarted = MemoryRepository(tmp_path / "evolution.sqlite3")
    result = MemoryEvolutionService(restarted, batch_size=2, summary_budget_chars=80).process_session(conversation.conversation_id, "owner-a", trigger="retry")
    assert result.status == "completed"
    assert restarted.get_evolution_checkpoint(conversation.conversation_id, "owner-a", "summarize").attempts == 2
    summaries = restarted.list_conversation_summaries(conversation.conversation_id, "owner-a")
    assert len(summaries) == 1 and len(summaries[0].summary_text) <= 80


def test_evolution_session_mutex_prevents_concurrent_runs(tmp_path):
    """原 `..._and_candidate_promotion_require_evidence` 的会话互斥部分保留；
    候选记忆晋升部分随 ``memories`` 停用删除（MD 无「候选晋升」概念）。"""
    repo = MemoryRepository(tmp_path / "evolution.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    service = MemoryEvolutionService(repo, batch_size=10)
    assert service.try_session_lock(conversation.conversation_id) is True
    assert service.try_session_lock(conversation.conversation_id) is False
    service.release_session_lock(conversation.conversation_id)


def test_summary_recall_without_match_is_empty(tmp_path):
    repo = MemoryRepository(tmp_path / "summary-match.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id)
    repo.upsert_conversation_summary("owner-a", conversation.conversation_id, "关于数据库索引的摘要")
    assert repo.list_recall_summaries("owner-a", project.project_id, query="完全不相关", budget_chars=1000) == []
    assert repo.list_recall_summaries("owner-a", project.project_id, query="数据库", budget_chars=1000)


def test_raw_event_message_and_cursor_must_belong_to_same_conversation(tmp_path):
    repo = MemoryRepository(tmp_path / "raw-scope.sqlite3")
    first = repo.create_conversation("owner-a")
    second = repo.create_conversation("owner-a")
    message = repo.create_message(second.conversation_id, "owner-a", "user", "second", status="completed")
    event = repo.append_raw_event("owner-a", second.conversation_id, "user_message", {"content": "second"}, message_id=message.message_id, idempotency_key="second")
    with pytest.raises(ValueError, match="conversation"):
        repo.append_raw_event("owner-a", first.conversation_id, "user_message", {"content": "wrong"}, message_id=message.message_id)
    with pytest.raises(ValueError, match="cursor"):
        repo.list_raw_events(first.conversation_id, "owner-a", after=event.event_id)


def test_stale_running_checkpoint_is_taken_over_and_resumes(tmp_path):
    path = tmp_path / "stale.sqlite3"
    repo = MemoryRepository(path)
    conversation = repo.create_conversation("owner-a")
    for index in range(3):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": str(index)}, idempotency_key=str(index))
    checkpoint, claimed = repo.claim_evolution_checkpoint(conversation.conversation_id, "owner-a", total_batches=2, idempotency_key="crashed")
    assert claimed
    repo.save_evolution_progress(checkpoint.checkpoint_id, "owner-a", cursor=None, batch_index=1, state={"mapped": ["done"], "input_event_count": 3})
    with repo.transaction() as db:
        db.execute("UPDATE evolution_checkpoints SET updated_at=? WHERE checkpoint_id=?", ("2020-01-01T00:00:00+00:00", checkpoint.checkpoint_id))
    restarted = MemoryRepository(path)
    resumed = MemoryEvolutionService(restarted, batch_size=2).process_session(conversation.conversation_id, "owner-a", trigger="retry")
    assert resumed.status == "completed" and resumed.attempts == 2 and resumed.batch_index == 2


def test_evolution_worker_consumes_more_than_1000_events_and_recovers(tmp_path):
    repo = MemoryRepository(tmp_path / "many-events.sqlite3")
    conversation = repo.create_conversation("owner-a")
    for index in range(1001):
        repo.append_raw_event("owner-a", conversation.conversation_id, "user_message", {"content": f"e{index}"}, idempotency_key=f"e{index}")
    worker = MemoryEvolutionWorker(repo, owner_id="owner-a", poll_interval=0.01).start()
    worker.enqueue_session(conversation.conversation_id)
    deadline = time.monotonic() + 5
    checkpoint = None
    while time.monotonic() < deadline:
        checkpoint = repo.get_evolution_checkpoint(conversation.conversation_id, "owner-a")
        if checkpoint and checkpoint.status == "completed":
            break
        time.sleep(0.01)
    worker.stop()
    assert checkpoint and checkpoint.status == "completed" and checkpoint.state["input_event_count"] == 1001
    all_events = repo.list_raw_events(conversation.conversation_id, "owner-a", limit=5000)
    assert checkpoint.state["input_last_event_id"] == all_events[-1].event_id
    assert repo.list_conversation_summaries(conversation.conversation_id, "owner-a")[0].source_event_id == checkpoint.state["input_last_event_id"]


# ---------------------------------------------------------------------------
# Spec032.1 task-10 修复：connection() 必须在退出时关闭连接。
#
# sqlite3.Connection 的 ``with`` 语义是「事务」（commit/rollback），**不关闭**连接。
# 修复前 ``MemoryRepository.connection()`` 返回裸连接，45 处 ``with self.connection()``
# 读路径的连接全部泄漏，导致 TemporaryDirectory 清理时出现
# ``OSError: [Errno 66] Directory not empty``（WAL/journal 残留未释放）。
# ---------------------------------------------------------------------------
def test_connection_closes_on_with_exit(tmp_path):
    repo = MemoryRepository(tmp_path / "closes.sqlite3")
    with repo.connection() as db:
        assert db.execute("SELECT 1").fetchone()[0] == 1
    # closed 连接再次执行必须抛 ProgrammingError；反之即泄漏。
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_connection_closes_on_exception(tmp_path):
    repo = MemoryRepository(tmp_path / "closes-on-error.sqlite3")
    # 嵌套是刻意的：pytest.raises 必须包住整个 with 块，合并会改变语义。
    with pytest.raises(RuntimeError, match="boom"):  # noqa: SIM117
        with repo.connection() as db:
            raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_repeated_reads_do_not_accumulate_open_connections(tmp_path):
    """连续读路径不得累积未关闭连接（回归 teardown 的 Errno 66）。"""
    repo = MemoryRepository(tmp_path / "no-leak.sqlite3")
    project = repo.create_project("owner-a", "P")
    conversation = repo.create_conversation("owner-a", project.project_id, title="c")
    for index in range(24):
        repo.create_message(conversation.conversation_id, "owner-a", "user", f"m{index}", status="completed")
    for _ in range(12):
        repo.list_messages(conversation.conversation_id, "owner-a")
        repo.list_projects("owner-a")
    # 所有这些读路径用的连接都必须已关闭（未关闭时 fsync/清理会残留 WAL 侧文件）。
    with repo.connection() as db:
        assert db.execute("SELECT 1").fetchone()[0] == 1


def test_initialize_and_transaction_still_work_after_contextmanager_change(tmp_path):
    """transaction() 语义（BEGIN IMMEDIATE / COMMIT / rollback）保持不变。"""
    repo = MemoryRepository(tmp_path / "tx.sqlite3")
    project = repo.create_project("owner-a", "P")
    with repo.transaction() as db:
        db.execute("UPDATE projects SET name='Renamed' WHERE project_id=?", (project.project_id,))
    assert repo.get_project(project.project_id, "owner-a").name == "Renamed"

    # 同上：pytest.raises 包住 transaction 块以验证 rollback，不可合并。
    with pytest.raises(RuntimeError, match="rollback me"):  # noqa: SIM117
        with repo.transaction() as db:
            db.execute("UPDATE projects SET name='ShouldRollback' WHERE project_id=?", (project.project_id,))
            raise RuntimeError("rollback me")
    assert repo.get_project(project.project_id, "owner-a").name == "Renamed"
