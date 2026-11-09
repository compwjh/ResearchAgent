"""``scripts/seed_demo_research_reports.py`` 清理路径的回归测试（TDD）。

对应评审 LOW-4（本任务 C5）：``clean()`` 跨库非原子 + 备份形态。

覆盖：
- ``clean()`` 只删 ``seed-demo-`` 前缀、按 task_id 精确关联 research 库 5 表、
  两库一致、``len(ids)`` 返回值不变、幂等重跑；
- 两库 DELETE 收进单个连接 + ``ATTACH`` + 一个显式事务；
- ``snapshot_databases()`` 用 ``Connection.backup()`` 生成两份可读的一致性快照，
  且包含仍留在 WAL 中、尚未 checkpoint 回主库的已提交内容；
- 「先一致性备份 + ``--clean`` 幂等重跑」兜底：快照保留清理前状态，重跑为空操作。

所有库都由 ``tmp_path`` 构造；不调用 ``main()``、不触碰真实 ``data/``、
不执行清理脚本、不重新生成假数据。
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.research.infrastructure.research_store import ResearchStore
from scripts import seed_demo_research_reports as seed

_NOW = "2026-11-09T00:00:00Z"
RESEARCH_TABLES = (
    "research_tasks",
    "research_reports",
    "research_sessions",
    "research_agent_runs",
    "research_artifacts",
)


def _insert_task_bundle(db: sqlite3.Connection, task_id: str, conversation_id: str) -> None:
    """按 seed 脚本 ``generate()`` 的 5 表关联形态插入一个完整任务。"""
    session_id = f"{task_id}:session"
    run_id = f"{task_id}:run"
    db.execute(
        """INSERT INTO research_tasks(
               research_task_id, owner_id, conversation_id, goal, language,
               quality_profile, target_paper_count, soft_budget_seconds,
               status, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (task_id, OWNER_ID, conversation_id, "goal", "zh", "balanced", 1, 1,
         "completed", _NOW, _NOW),
    )
    db.execute(
        """INSERT INTO research_reports(
               report_id, research_task_id, plan_version, report_version,
               status, markdown, html, report_json, limitations_json, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (f"{task_id}:report", task_id, 1, 1, "completed", "# report",
         "<p>report</p>", "{}", "[]", _NOW),
    )
    db.execute(
        """INSERT INTO research_sessions(
               research_session_id, owner_id, conversation_id, trigger_message_id,
               plan_message_id, activity_message_id, final_message_id, intake_draft_id,
               research_task_id, current_plan_version, status, unread_state_json,
               created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id, OWNER_ID, conversation_id, f"{task_id}:trigger",
         None, None, None, f"{task_id}:intake", task_id, 1, "completed", "{}",
         _NOW, _NOW),
    )
    db.execute(
        """INSERT INTO research_agent_runs(
               agent_run_id, research_session_id, research_task_id, work_item_id, attempt,
               role, skill_name, skill_schema_version, skill_content_hash, resolved_model,
               reasoning_effort, provider, allowed_tools_json, status, model_loop_count,
               tool_call_count, input_hash, output_hash, generation, started_at, ended_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, session_id, task_id, f"{task_id}:work", 1, "synthesizer",
         "research-report-synthesis", "1", "hash", "model", "off", "", "[]",
         "completed", 0, 0, "", "", 0, _NOW, _NOW),
    )
    db.execute(
        """INSERT INTO research_artifacts(
               artifact_id, research_task_id, report_version, artifact_type,
               content, content_hash, generated_by_agent_run_id, created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (f"{task_id}:artifact", task_id, 1, "markdown", "content", "hash", run_id, _NOW),
    )


def _insert_conversation(db: sqlite3.Connection, conversation_id: str) -> None:
    db.execute(
        "INSERT INTO conversations(conversation_id, owner_id, created_at, updated_at) VALUES(?,?,?,?)",
        (conversation_id, OWNER_ID, _NOW, _NOW),
    )


def _task_ids(research: Path, table: str) -> set[str]:
    assert table in RESEARCH_TABLES, "测试只允许查询 5 张已知表"
    with sqlite3.connect(research) as db:
        return {str(row[0]) for row in db.execute(f"SELECT research_task_id FROM {table}")}


def _conversation_ids(memory: Path) -> set[str]:
    with sqlite3.connect(memory) as db:
        return {str(row[0]) for row in db.execute("SELECT conversation_id FROM conversations")}


def _counts(research: Path, memory: Path) -> dict[str, int]:
    result = {}
    for table in RESEARCH_TABLES:
        with sqlite3.connect(research) as db:
            result[table] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    with sqlite3.connect(memory) as db:
        result["conversations"] = db.execute("SELECT count(*) FROM conversations").fetchone()[0]
    return result


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    """两库都是真实的 WAL SQLite 库，MEMORY_DB 指向临时库，不触碰 data/。"""
    research = tmp_path / "research.sqlite3"
    memory = tmp_path / "memory.sqlite3"
    store = ResearchStore(database_path=research)
    MemoryRepository(memory)
    monkeypatch.setattr(seed, "MEMORY_DB", memory)
    return store, research, memory


def _seed_and_real_rows(research: Path, memory: Path) -> tuple[set[str], set[str]]:
    """2 个 seed 任务/会话 + 2 个真实任务/会话 + 3 个近似前缀但不应匹配的行。"""
    seed_task_ids = {"seed-task-aaaa", "seed-task-bbbb"}
    real_task_ids = {"a" * 32, "b" * 32}
    seed_convs = {seed.SEED_CONVERSATION_PREFIX + "conv-1", seed.SEED_CONVERSATION_PREFIX + "conv-2"}
    real_convs = set(real_task_ids) | {"seed-demoX", "xseed-demo-almost"}
    with sqlite3.connect(research) as db:
        for task_id, conv_id in zip(sorted(seed_task_ids), sorted(seed_convs), strict=True):
            _insert_task_bundle(db, task_id, conv_id)
        for task_id in sorted(real_task_ids):
            _insert_task_bundle(db, task_id, task_id)
        _insert_task_bundle(db, "near-miss-task", "seed-demoX")
    with sqlite3.connect(memory) as db:
        for conv_id in sorted(seed_convs | real_convs):
            _insert_conversation(db, conv_id)
    return seed_task_ids, seed_convs


def test_clean_deletes_only_seed_prefixed_rows_and_returns_len_ids(dbs):
    """只删 seed 前缀、5 表按 task_id 精确关联、两库一致、len(ids) 不变。"""
    store, research, memory = dbs
    seed_task_ids, _seed_convs = _seed_and_real_rows(research, memory)
    # SQLite LIKE 对 ASCII 大小写不敏感是既有语义，严格不变：大写前缀同样命中。
    with sqlite3.connect(memory) as db:
        _insert_conversation(db, "SEED-DEMO-upper")

    removed = seed.clean(store)

    assert removed == len(seed_task_ids) == 2
    surviving = {"a" * 32, "b" * 32, "near-miss-task"}
    for table in RESEARCH_TABLES:
        assert _task_ids(research, table) == surviving, table
    assert _conversation_ids(memory) == {
        "a" * 32, "b" * 32, "seed-demoX", "xseed-demo-almost",
    }


def test_clean_uses_one_connection_and_one_explicit_transaction(dbs, monkeypatch):
    """两库 DELETE 必须在单个 ATTACH 连接的同一个显式事务内。"""
    store, research, memory = dbs
    _seed_and_real_rows(research, memory)

    real_connect = sqlite3.connect
    traces: list[list[str]] = []
    active = {"on": True}

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        if active["on"]:
            statements: list[str] = []
            conn.set_trace_callback(statements.append)
            traces.append(statements)
        return conn

    monkeypatch.setattr(seed.sqlite3, "connect", spy)
    seed.clean(store)
    active["on"] = False

    assert len(traces) == 1, "两库 DELETE 必须共用同一个连接，而不是两个独立事务"
    statements = [s.upper() for s in traces[0]]
    assert any("ATTACH DATABASE" in s and "AS MEMORY" in s for s in statements)
    begin_at = next(i for i, s in enumerate(statements) if s.startswith("BEGIN"))
    commit_at = next(i for i, s in enumerate(statements) if s.startswith("COMMIT"))
    assert begin_at < commit_at
    deletes = [i for i, s in enumerate(statements) if s.lstrip().startswith("DELETE")]
    assert len(deletes) >= 6, "research 5 表与 memory.conversations 都要删"
    assert all(begin_at < i < commit_at for i in deletes), "两库 DELETE 必须在同一显式事务内"


def test_clean_is_idempotent_on_rerun(dbs):
    """--clean 幂等重跑：第二次返回 0 且两库计数不变。"""
    store, research, memory = dbs
    _seed_and_real_rows(research, memory)

    assert seed.clean(store) == 2
    after_first = _counts(research, memory)
    assert seed.clean(store) == 0
    assert _counts(research, memory) == after_first


def test_snapshot_databases_includes_wal_committed_rows_for_both_databases(dbs, tmp_path):
    """online backup 两库各一份可读快照，且含单文件 cp 漏掉的 WAL 已提交行。"""
    _store, research, memory = dbs
    _seed_and_real_rows(research, memory)

    # 两个保持打开的连接：写入已提交但尚未 checkpoint 回主库的 WAL 行。
    r_conn = sqlite3.connect(research)
    m_conn = sqlite3.connect(memory)
    try:
        r_conn.execute("PRAGMA wal_autocheckpoint=0")
        m_conn.execute("PRAGMA wal_autocheckpoint=0")
        _insert_task_bundle(r_conn, "wal-only-task", "seed-demo-wal-conv")
        r_conn.commit()
        _insert_conversation(m_conn, "seed-demo-wal-conv")
        m_conn.commit()

        wal_r = Path(str(research) + "-wal")
        wal_m = Path(str(memory) + "-wal")
        assert wal_r.exists() and wal_r.stat().st_size > 0, "必须构造出真实的 WAL 场景"
        assert wal_m.exists() and wal_m.stat().st_size > 0, "必须构造出真实的 WAL 场景"

        # 对照组：单文件 cp 只复制主库文件，看不到 WAL 中已提交的行。
        cp_r = tmp_path / "cp-research.sqlite3"
        cp_m = tmp_path / "cp-memory.sqlite3"
        shutil.copy(research, cp_r)
        shutil.copy(memory, cp_m)
        with sqlite3.connect(cp_r) as db:
            assert db.execute(
                "SELECT count(*) FROM research_tasks WHERE research_task_id='wal-only-task'"
            ).fetchone()[0] == 0
        with sqlite3.connect(cp_m) as db:
            assert db.execute(
                "SELECT count(*) FROM conversations WHERE conversation_id='seed-demo-wal-conv'"
            ).fetchone()[0] == 0

        backup_dir = tmp_path / "backup"
        snapshots = seed.snapshot_databases(research, memory, backup_dir)

        assert set(snapshots) == {"research", "memory"}
        assert snapshots["research"] == backup_dir / "research.sqlite3"
        assert snapshots["memory"] == backup_dir / "memory.sqlite3"
        for path in snapshots.values():
            assert path.exists() and path.stat().st_size > 0
        with sqlite3.connect(f"file:{snapshots['research']}?mode=ro", uri=True) as db:
            assert db.execute(
                "SELECT count(*) FROM research_tasks WHERE research_task_id='wal-only-task'"
            ).fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM research_tasks").fetchone()[0] == 6
        with sqlite3.connect(f"file:{snapshots['memory']}?mode=ro", uri=True) as db:
            assert db.execute(
                "SELECT count(*) FROM conversations WHERE conversation_id='seed-demo-wal-conv'"
            ).fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM conversations").fetchone()[0] == 7
    finally:
        r_conn.close()
        m_conn.close()


def test_snapshot_before_clean_preserves_pre_cleanup_state_and_rerun_is_noop(dbs, tmp_path):
    """「先一致性备份 + --clean 幂等重跑」兜底：快照是清理前状态，重跑为空操作。"""
    store, research, memory = dbs
    _seed_and_real_rows(research, memory)
    backup_dir = tmp_path / "backup"
    snapshots = seed.snapshot_databases(research, memory, backup_dir)

    assert seed.clean(store) == 2

    with sqlite3.connect(f"file:{snapshots['research']}?mode=ro", uri=True) as db:
        assert db.execute(
            "SELECT count(*) FROM research_tasks WHERE conversation_id LIKE 'seed-demo-%'"
        ).fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM research_tasks").fetchone()[0] == 5
    with sqlite3.connect(f"file:{snapshots['memory']}?mode=ro", uri=True) as db:
        assert db.execute(
            "SELECT count(*) FROM conversations WHERE conversation_id LIKE 'seed-demo-%'"
        ).fetchone()[0] == 2

    surviving = {"a" * 32, "b" * 32, "near-miss-task"}
    for table in RESEARCH_TABLES:
        assert _task_ids(research, table) == surviving, table
    assert _conversation_ids(memory) == {
        "a" * 32, "b" * 32, "seed-demoX", "xseed-demo-almost",
    }

    before = _counts(research, memory)
    assert seed.clean(store) == 0
    assert _counts(research, memory) == before
    with sqlite3.connect(f"file:{snapshots['research']}?mode=ro", uri=True) as db:
        assert db.execute("SELECT count(*) FROM research_tasks").fetchone()[0] == 5
