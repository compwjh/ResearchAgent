"""regression: cleanup_snapshot 的只读连接必须在 with 退出时真正关闭。

历史缺陷：``_read_only_connection()`` 直接返回 ``sqlite3.Connection``，调用点
``with _read_only_connection(path) as connection:`` 走的是连接自带的
``__exit__``，它只 commit/rollback、**不 close**，只读快照每次计算都会泄漏
一个 sqlite FD（与 paper_discovery / task_store 同根因）。
"""

import contextlib
import sqlite3
from pathlib import Path

import pytest

# 本机精简 venv 缺 langchain_ollama，根 conftest 的 ollama 隔离 fixture 会在
# 收集阶段报错，导致本文件无法运行；此时显式跳过（而非静默通过）。
pytest.importorskip("langchain_ollama", reason="requires backend LLM deps")

from backend.app.research.application import cleanup_snapshot


class _RecordingConnection:
    """``sqlite3.connect`` 的替身：真实建连，额外记录 close 次数。"""

    def __init__(self, connection):
        self._connection = connection
        self.close_calls = 0

    def __getattr__(self, name):  # pragma: no cover - 逐项透传真实连接
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        if name in {"_connection", "close_calls"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._connection, name, value)

    def close(self):
        self.close_calls += 1
        self._connection.close()

    @property
    def is_closed(self):
        return self.close_calls > 0


@pytest.fixture()
def store_db(tmp_path):
    db_path = Path(tmp_path) / "snapshot.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE conversations(conversation_id TEXT, owner_id TEXT)")
        connection.execute(
            "INSERT INTO conversations(conversation_id, owner_id) VALUES ('c1', 'owner-a')"
        )
        connection.execute(
            "INSERT INTO conversations(conversation_id, owner_id) VALUES ('c2', 'owner-b')"
        )
    return db_path


def test_cleanup_snapshot_closes_connection_after_successful_operation(store_db, monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    assert cleanup_snapshot._table_count(store_db, "conversations", owner_id="owner-a") == 1
    assert cleanup_snapshot._table_count(store_db, "conversations") == 2

    assert len(opened) >= 2, f"仅观察到 {len(opened)} 个连接，补丁可能失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在正常退出后仍未关闭"
    )


def test_cleanup_snapshot_closes_connection_when_operation_raises(store_db, monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    # 不合并成一个 with：要单独验证 _read_only_connection() 自身的异常清理路径。
    with contextlib.ExitStack() as stack:
        stack.enter_context(pytest.raises(sqlite3.OperationalError, match="no such table"))
        connection = stack.enter_context(cleanup_snapshot._read_only_connection(store_db))
        connection.execute("SELECT * FROM missing_table_for_release_test")

    assert opened, "未观察到任何连接，补丁失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在异常退出后仍未关闭"
    )
