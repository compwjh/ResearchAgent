"""regression: article_assistant 的 TaskStore 必须在 with 退出时关闭连接。

历史缺陷：3 处 ``with sqlite3.connect(...)`` 依赖连接自带 ``__exit__``，
只提交事务不关闭连接；批量保存任务时会累积未释放的 sqlite FD。
"""

import sqlite3
from pathlib import Path

import pytest

from backend.app.article_assistant.domain.article import ArticleTask
from backend.app.article_assistant.infrastructure.task_store import TaskStore


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



def test_task_store_closes_every_connection(tmp_path, monkeypatch):
    db_path = Path(tmp_path) / "tasks.sqlite3"
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    store = TaskStore(db_path)
    store.save(ArticleTask(task_id="task-1", query="请下载论文", normalized_query="请下载论文", intent="download_paper", intent_confidence=0.9))
    assert store.get("task-1") is not None
    assert store.get("absent") is None

    assert len(opened) >= 4, f"仅观察到 {len(opened)} 个连接，补丁可能失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在退出后仍未关闭"
    )


def test_task_store_closes_connection_when_operation_raises(tmp_path, monkeypatch):
    db_path = Path(tmp_path) / "tasks.sqlite3"
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        connection = _RecordingConnection(real_connect(*args, **kwargs))
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    store = TaskStore(db_path)

    with pytest.raises(AttributeError):
        store.save(None)  # _to_dict(None) 失败 → 已建立的连接仍须关闭

    assert opened, "未观察到任何连接，补丁失效"
    assert all(connection.is_closed for connection in opened), (
        f"{sum(not c.is_closed for c in opened)}/{len(opened)} 个连接在异常退出后仍未关闭"
    )
