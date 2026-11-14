"""guard 动作与事件的 SQLite 持久化（Task03）。

沿用 `platform/capability_store.py` 的惯例：set_db_path 供测试注入、
每次连接显式关闭、事务语义、存储故障不抛出到业务主链路。
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from backend.app.platform.config import BASE_DIR

_DEFAULT_DB_PATH = BASE_DIR / "data" / "guard.sqlite3"
_db_path: Optional[Path] = None
_lock = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guard_actions(
    action_ref TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    normalized_args TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    target_summary TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guard_actions_owner ON guard_actions(owner_id, status);
CREATE TABLE IF NOT EXISTS guard_events(
    event_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guard_events_owner ON guard_events(owner_id, created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_db_path(path: Optional[Path]) -> None:
    """测试注入用：切换存储路径（None 恢复默认）。"""
    global _db_path
    with _lock:
        _db_path = Path(path) if path is not None else None


@contextlib.contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path or _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
    finally:
        connection.close()


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)


def create_action(record: dict[str, Any]) -> bool:
    """插入待确认动作；idempotency_key 冲突返回 False（不覆盖已有决策）。"""
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        existing = connection.execute(
            "SELECT 1 FROM guard_actions WHERE idempotency_key=?",
            (record["idempotency_key"],),
        ).fetchone()
        if existing is not None:
            return False
        connection.execute(
            "INSERT INTO guard_actions(action_ref, owner_id, task_id, tool_name,"
            " normalized_args, args_hash, target_summary, status, scope_version,"
            " idempotency_key, created_at, decided_at, consumed_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record["action_ref"], record["owner_id"], record["task_id"],
                record["tool_name"], json.dumps(record["normalized_args"], sort_keys=True),
                record["args_hash"], record["target_summary"], record["status"],
                record["scope_version"], record["idempotency_key"],
                record["created_at"], None, None,
            ),
        )
        return True


def get_action(action_ref: str) -> Optional[dict[str, Any]]:
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        row = connection.execute(
            "SELECT * FROM guard_actions WHERE action_ref=?", (action_ref,)
        ).fetchone()
    return dict(row) if row is not None else None


def update_action_status(action_ref: str, status: str, *, column: str) -> bool:
    """带状态前置条件的转换；返回是否真的更新了一行（CAS 语义）。"""
    if column not in {"decided_at", "consumed_at"}:
        raise ValueError("invalid timestamp column")
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        cursor = connection.execute(
            f"UPDATE guard_actions SET status=?, {column}=? WHERE action_ref=?",
            (status, utc_now(), action_ref),
        )
        return cursor.rowcount == 1


def list_actions(owner_id: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        if status is None:
            rows = connection.execute(
                "SELECT * FROM guard_actions WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
                (owner_id, max(1, min(int(limit), 200))),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM guard_actions WHERE owner_id=? AND status=?"
                " ORDER BY created_at DESC LIMIT ?",
                (owner_id, status, max(1, min(int(limit), 200))),
            ).fetchall()
    return [dict(row) for row in rows]


def append_event(event: dict[str, Any]) -> None:
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        connection.execute(
            "INSERT OR IGNORE INTO guard_events(event_id, owner_id, payload, created_at)"
            " VALUES(?,?,?,?)",
            (event["event_id"], event["owner_id"],
             json.dumps(event["payload"], sort_keys=True), event["created_at"]),
        )


def list_events(owner_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT payload FROM guard_events WHERE owner_id=?"
            " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (owner_id, max(1, min(int(limit), 200))),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            result.append(payload)
    return result


def delete_events_for_task(owner_id: str, task_id: str) -> None:
    """删除所属任务时清理事件（沿用项目留存规则）。"""
    with _lock, _connect() as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT event_id, payload FROM guard_events WHERE owner_id=?", (owner_id,)
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            if payload.get("task_id") == task_id:
                connection.execute(
                    "DELETE FROM guard_events WHERE event_id=?", (row["event_id"],)
                )
