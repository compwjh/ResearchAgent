"""regression: platform.capability_store 的连接必须在 with 退出时真正关闭。

历史缺陷：``_connect()`` 直接返回 ``sqlite3.Connection``，调用点
``with _connect() as connection:`` 走的是连接自带的 ``__exit__``，它只
commit/rollback、**不 close**，SQLite FD 只能等 GC 回收；长跑服务反复读写
模型能力库会累积未释放的文件句柄（与 paper_discovery / task_store 同根因）。

断言方式：monkeypatch ``sqlite3.connect`` 记录本次打开的全部连接，覆盖
「正常退出」与「异常退出」两条路径，要求每个连接都被 close。
"""

import contextlib
import sqlite3
from pathlib import Path

import pytest

# 本机精简 venv 缺 langchain_ollama，根 conftest 的 ollama 隔离 fixture 会在
# 收集阶段报错，导致本文件无法运行；此时显式跳过（而非静默通过）。
pytest.importorskip("langchain_ollama", reason="requires backend LLM deps")

from backend.app.platform import capability_store


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
def injected_db(tmp_path, monkeypatch):
    db_path = Path(tmp_path) / "capabilities.sqlite3"
    capability_store.set_db_path(db_path)
    yield db_path
    capability_store.set_db_path(None)


def test_capability_store_closes_connection_after_successful_operation(injected_db, monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    capability_store.upsert_capabilities(
        "qwen-test",
        supported_efforts=("low", "high"),
        default_effort="low",
        source="probe",
        evidence={"probe": "ok"},
        probed_at="2026-01-01T00:00:00+00:00",
    )
    stored = capability_store.get_capabilities("qwen-test")
    assert stored is not None, "能力未写入，测试无效"
    assert stored["supported_efforts"] == ("low", "high")
    assert capability_store.get_capabilities("absent-model") is None

    assert len(opened) >= 3, f"仅观察到 {len(opened)} 个连接，补丁可能失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在正常退出后仍未关闭"
    )


def test_capability_store_closes_connection_when_operation_raises(injected_db, monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    # 不合并成一个 with：要单独验证 _connect() 自身的异常清理路径。
    with contextlib.ExitStack() as stack:
        stack.enter_context(pytest.raises(sqlite3.OperationalError, match="no such table"))
        connection = stack.enter_context(capability_store._connect())
        connection.execute("SELECT * FROM missing_table_for_release_test")

    assert opened, "未观察到任何连接，补丁失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在异常退出后仍未关闭"
    )
