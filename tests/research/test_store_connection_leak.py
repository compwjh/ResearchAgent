"""spec-037 Bug 9：ResearchStore 的 SQLite 连接必须被关闭（fd 泄漏回归测试）。

背景：``sqlite3.Connection`` 作为上下文管理器**只管理事务、不关闭连接**。此前
``_connect()`` 返回裸连接，而 89 个调用点全部写成 ``with self._connect() as conn:``，
导致连接只开不关，实测泄漏 8 万+ 文件句柄，最终所有新建 httpx Client 抛
``OSError: [Errno 24] Too many open files``（表现为 /api/health 500、模型库空白）。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from backend.app.research.infrastructure.research_store import ResearchStore

# 循环次数需足够大：若连接不关闭，句柄数会随调用次数线性增长，远超阈值。
CALLS = 300


def _open_fd_count() -> int:
    """当前进程打开的 fd 数（macOS/Linux 通用：读 /dev/fd）。"""
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:  # pragma: no cover - 极端环境下退化为不比较
        return -1


@pytest.fixture()
def store(tmp_path):
    return ResearchStore(tmp_path / "research.sqlite3")


def test_connect_closes_connection_on_success(store):
    """正常退出 ``with`` 后连接必须已关闭，再使用应抛 ProgrammingError。"""
    with store._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_connect_closes_connection_on_exception(store):
    """异常路径也必须关闭（``finally`` 保证），否则异常分支会持续泄漏。"""
    with pytest.raises(RuntimeError):
        with store._connect() as connection:
            connection.execute("SELECT 1")
            raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_repeated_calls_do_not_grow_open_fds(store):
    """连续 300 次读调用后，句柄数不应随调用次数增长（允许少量抖动）。"""
    before = _open_fd_count()
    for _ in range(CALLS):
        store.list_tasks(owner_id="owner-a")
    after = _open_fd_count()
    if before >= 0 and after >= 0:
        # 允许 20 个的抖动（其它惰性资源），但绝不能出现数百/数千级增长。
        assert after - before <= 20, f"fd 疑似泄漏：{before} -> {after}"


def test_repeated_failing_calls_do_not_grow_open_fds(store):
    """异常路径同样不泄漏：每次都让方法内部抛错。"""
    before = _open_fd_count()
    for index in range(CALLS):
        with pytest.raises(Exception):
            with store._connect() as connection:
                connection.execute("SELECT * FROM definitely_not_a_table")
    after = _open_fd_count()
    if before >= 0 and after >= 0:
        assert after - before <= 20, f"fd 疑似泄漏（异常路径）：{before} -> {after}"


def test_write_path_still_commits(store):
    """修复不得破坏事务语义：写入后重新连接仍能读到（即已提交）。"""
    from backend.app.research.domain.models import ResearchTask

    now = "2026-09-16T00:00:00Z"
    task = ResearchTask(
        research_task_id="task-leak-1",
        owner_id="owner-a",
        project_id=None,
        conversation_id="conv-1",
        goal="验证写入仍会提交",
        language="zh",
        quality_profile="balanced",
        review_plan_first=False,
        target_paper_count=12,
        soft_budget_seconds=1500,
        status="draft",
        current_plan_version=1,
        created_at=now,
        updated_at=now,
    )
    store.create_task(task)
    reloaded = store.get_task("task-leak-1", "owner-a")
    assert reloaded is not None
    assert reloaded.goal == "验证写入仍会提交"
