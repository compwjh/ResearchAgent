"""regression: PaperDiscoveryStore 的连接必须在 with 退出时真正关闭。

历史缺陷：``_connect()`` 直接返回 ``sqlite3.Connection``，36 处
``with self._connect() as connection:`` 走的是连接自带的 ``__exit__``，
它只 commit/rollback、**不 close**，FD 只能等 GC 回收；长时间运行的服务
因此累积上百个 state.sqlite3 / -wal FD，最终触发 ``Too many open files``。

断言方式：monkeypatch ``sqlite3.connect`` 记录本次打开的全部连接，
覆盖「正常退出」与「异常退出」两条路径，要求每个连接都被 close。
"""

import contextlib
import sqlite3

import pytest

from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


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


def test_store_closes_connection_after_successful_operation(tmp_path, monkeypatch):
    db_path = tmp_path / "state.sqlite3"
    PaperDiscoveryStore(db_path)
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    store = PaperDiscoveryStore(db_path)
    assert store.list_conferences(), "基础数据缺失，测试无效"

    assert opened, "未观察到任何连接，补丁失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在正常退出后仍未关闭"
    )


def test_store_closes_connection_when_operation_raises(tmp_path, monkeypatch):
    db_path = tmp_path / "state.sqlite3"
    PaperDiscoveryStore(db_path)
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    store = PaperDiscoveryStore(db_path)

    # 不合并成一个 with：要单独验证 _connect() 自身的异常清理路径。
    with contextlib.ExitStack() as stack:
        stack.enter_context(pytest.raises(sqlite3.OperationalError, match="no such table"))
        connection = stack.enter_context(store._connect())
        connection.execute("SELECT * FROM missing_table_for_release_test")

    assert opened, "未观察到任何连接，补丁失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在异常退出后仍未关闭"
    )
