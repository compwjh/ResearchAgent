"""事件表 retention：时间/行数触发的保守清理、fail-open 与按需 VACUUM 契约。

背景：三张事件表当前行数很小（raw_events 12 / processing_steps 74 /
research_events 66），retention 是**面向未来增长的风险缓解**，不是修复现有故障。
因此清理只作用于未来增长：不迁移、不主动删除现有历史数据；异常只记日志，
不得影响服务启动与业务读取。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform import config
from backend.app.research.domain.models import ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex


def _memory_stamp(moment: datetime) -> str:
    """memory 库时间格式（repository._now：UTC isoformat，+00:00）。"""
    return moment.isoformat()


def _research_stamp(moment: datetime) -> str:
    """research 库时间格式（research_store._utcnow：秒精度 + Z）。"""
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _seed_memory_events(repo, conversation_id, message_id, moments):
    """直接插行以精确控制 created_at/started_at，绕过写入侧的当前时钟。"""
    with repo.transaction() as db:
        for index, moment in enumerate(moments):
            stamp = _memory_stamp(moment)
            db.execute(
                "INSERT INTO raw_events(event_id, owner_id, conversation_id, message_id, "
                "event_kind, payload, idempotency_key, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (_uid(), OWNER_ID, conversation_id, message_id, "user_message", "{}", _uid(), stamp),
            )
            db.execute(
                "INSERT INTO processing_steps(step_id, message_id, kind, logical_sequence, "
                "label, status, summary, started_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (_uid(), message_id, "phase", index, f"label-{index}", "completed", "ok", stamp, stamp),
            )


def _fresh_memory_repo(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = repo.create_conversation(OWNER_ID)
    message = repo.create_message(conversation.conversation_id, OWNER_ID, "assistant", "ok")
    return repo, conversation.conversation_id, message.message_id


def test_memory_event_retention_prunes_expired_rows_and_keeps_business_reads(tmp_path):
    """极小时间阈值：超期行被清理，且既有业务读取接口仍可用。"""
    repo, conversation_id, message_id = _fresh_memory_repo(tmp_path)
    moments = [NOW - timedelta(days=200, minutes=i) for i in range(3)] + [
        NOW - timedelta(days=1, minutes=i) for i in range(3)
    ]
    _seed_memory_events(repo, conversation_id, message_id, moments)

    with repo.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM processing_steps").fetchone()[0] == 6

    deleted = repo.prune_event_tables(max_age_days=90, max_rows=100_000, now=NOW)
    assert deleted == {"raw_events": 3, "processing_steps": 3}

    with repo.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM processing_steps").fetchone()[0] == 3
    # fail-open 的业务含义：清理后读取接口照常工作，返回未超期的部分。
    assert len(repo.list_processing_steps(message_id, OWNER_ID)) == 3
    assert len(repo.list_raw_events(conversation_id, OWNER_ID)) == 3


def test_memory_event_retention_row_cap_trims_oldest_rows(tmp_path):
    """行数上限：全部行都在保留期内时，只按行数裁掉最旧的一部分。"""
    repo, conversation_id, message_id = _fresh_memory_repo(tmp_path)
    _seed_memory_events(
        repo, conversation_id, message_id,
        [NOW - timedelta(days=i, minutes=i) for i in range(6)],
    )

    deleted = repo.prune_event_tables(max_age_days=90, max_rows=2, now=NOW)
    assert deleted == {"raw_events": 4, "processing_steps": 4}

    steps = repo.list_processing_steps(message_id, OWNER_ID)
    assert {step.label for step in steps} == {"label-0", "label-1"}
    assert len(repo.list_raw_events(conversation_id, OWNER_ID)) == 2


def test_research_event_retention_prunes_expired_rows_and_keeps_replay(tmp_path):
    """research 库时间格式为 'Z'，cutoff 必须同格式，否则字符串比较会失效。"""
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(_uid(), OWNER_ID, _uid(), "goal", "zh", "balanced", False, 2, 60, "draft", 1, "now", "now")
    store.create_task(task)
    moments = [NOW - timedelta(days=200, minutes=i) for i in range(3)] + [
        NOW - timedelta(days=1, minutes=i) for i in range(3)
    ]
    with sqlite3.connect(store.database_path) as connection:
        for index, moment in enumerate(moments, start=1):
            connection.execute(
                "INSERT INTO research_events(research_task_id, event_seq, event_type, "
                "safe_payload_json, created_at) VALUES (?,?,?,?,?)",
                (task.research_task_id, index, "task", "{}", _research_stamp(moment)),
            )

    assert store.prune_events(max_age_days=90, max_rows=100_000, now=NOW) == 3
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM research_events").fetchone()[0] == 3
    assert len(store.list_events(task.research_task_id)) == 3


def test_event_retention_defaults_are_conservative_and_env_configurable():
    """默认是保守的长期保留，不因一次启动就裁掉现有历史数据。"""
    assert config.EVENT_RETENTION_ENABLED is True
    assert config.EVENT_RETENTION_MAX_AGE_DAYS >= 90
    assert config.EVENT_RETENTION_MAX_ROWS >= 1_000
    assert isinstance(config.EVENT_RETENTION_VACUUM, bool)


def test_event_retention_runner_is_fail_open_and_vacuums_only_after_deletions(tmp_path, monkeypatch):
    """单一编排入口：某库清理抛异常只记日志，另一库照常清理；有删除才 VACUUM。"""
    from backend.app.platform import retention

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    monkeypatch.setattr(repo, "prune_event_tables", lambda **_kwargs: {"raw_events": 2, "processing_steps": 0})

    def _locked(**_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "prune_events", _locked)
    vacuumed = []
    monkeypatch.setattr(retention, "_vacuum", lambda path: vacuumed.append(str(path)))

    summary = retention.run_event_retention(
        max_age_days=90, max_rows=100_000, now=NOW,
        memory_repository=repo, research_store=store,
    )
    assert summary["errors"] == ["research"]
    assert summary["deleted"]["memory"] == {"raw_events": 2, "processing_steps": 0}
    assert vacuumed == [str(repo.database_path)]


def test_event_retention_runner_skips_vacuum_when_nothing_deleted(tmp_path, monkeypatch):
    """无删除时不得执行 VACUUM（避免与长跑任务无谓争锁）。"""
    from backend.app.platform import retention

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    store = ResearchStore(tmp_path / "research.sqlite3")
    monkeypatch.setattr(repo, "prune_event_tables", lambda **_kwargs: {"raw_events": 0, "processing_steps": 0})
    monkeypatch.setattr(store, "prune_events", lambda **_kwargs: 0)
    vacuumed = []
    monkeypatch.setattr(retention, "_vacuum", lambda path: vacuumed.append(str(path)))

    summary = retention.run_event_retention(
        max_age_days=90, max_rows=100_000, now=NOW,
        memory_repository=repo, research_store=store,
    )
    assert summary["errors"] == []
    assert summary["deleted"] == {
        "memory": {"raw_events": 0, "processing_steps": 0},
        "research": 0,
    }
    assert vacuumed == []
