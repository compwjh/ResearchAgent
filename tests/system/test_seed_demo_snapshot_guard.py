"""任务 U：seed 快照条件化 / 缺库可诊断 / 连接对称释放 / 同名不覆盖（TDD）。

对应评审 MEDIUM-6。全部用 ``tmp_path`` 构造最小 SQLite 库，不触碰真实 ``data/``、
不执行真实清理、不重新生成假数据。

RED → GREEN（2026-11-10）：任务 L 的实现无条件调用 ``snapshot_databases()``、
缺库即 ``raise FileNotFoundError``、``dst = sqlite3.connect(target)`` 位于 ``try``
之外、两库同名时 ``target`` 静默互相覆盖。本组用例在旧实现下逐条失败。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import seed_demo_research_reports as seed


def _make_db(path: Path, *, kind: str) -> None:
    with sqlite3.connect(path) as db:
        if kind == "research":
            db.execute(
                "CREATE TABLE research_tasks (research_task_id TEXT PRIMARY KEY, conversation_id TEXT)"
            )
            db.execute("CREATE TABLE research_reports (report_id TEXT PRIMARY KEY)")
        else:
            db.execute("CREATE TABLE conversations (conversation_id TEXT PRIMARY KEY)")


def test_snapshot_skips_missing_source_with_diagnostic(tmp_path, capsys):
    """源库缺失必须跳过并给出可诊断输出，不得硬失败中断 seed。"""
    research = tmp_path / "research.sqlite3"
    _make_db(research, kind="research")
    missing = tmp_path / "memory.sqlite3"  # 故意不创建：全新 checkout 场景

    snapshots = seed.snapshot_databases(research, missing, tmp_path / "backup")

    assert set(snapshots) == {"research"}, "缺库必须跳过该库快照而不是抛异常"
    assert snapshots["research"] == tmp_path / "backup" / "research.sqlite3"
    assert "skip memory" in capsys.readouterr().out, "跳过必须有可诊断输出"


def test_snapshot_avoids_silent_overwrite_when_names_collide(tmp_path):
    """两库同名时不得静默互相覆盖（评审 MEDIUM-6 第 4 点）。"""
    research = tmp_path / "a" / "shared.sqlite3"
    memory = tmp_path / "b" / "shared.sqlite3"
    research.parent.mkdir()
    memory.parent.mkdir()
    _make_db(research, kind="research")
    _make_db(memory, kind="memory")

    snapshots = seed.snapshot_databases(research, memory, tmp_path / "backup")

    assert snapshots["research"] != snapshots["memory"], "同名库快照不得指向同一路径"
    assert snapshots["research"].exists() and snapshots["memory"].exists()
    assert snapshots["research"].read_bytes() != b""


def test_snapshot_closes_source_when_target_connect_fails(tmp_path, monkeypatch):
    """回归清单第 10 条：dst 连接抛错时 src 必须被对称释放。"""
    research = tmp_path / "research.sqlite3"
    _make_db(research, kind="research")
    real_connect = sqlite3.connect
    opened = []
    calls = {"n": 0}

    def spy(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("cannot open target")
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(seed.sqlite3, "connect", spy)
    with pytest.raises(sqlite3.OperationalError, match="cannot open target"):
        seed.snapshot_databases(research, research, tmp_path / "backup")

    assert len(opened) == 1, "只有 src 连接被成功创建"
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1"), "src 必须在 finally 中被关闭"


def test_pending_seed_rows_only_true_for_seed_prefix(tmp_path):
    """快照条件化：只有存在 seed-demo- 前缀行才算「真正要清理」。"""
    research = tmp_path / "research.sqlite3"
    memory = tmp_path / "memory.sqlite3"
    _make_db(research, kind="research")
    _make_db(memory, kind="memory")
    with sqlite3.connect(memory) as db:
        db.execute("INSERT INTO conversations VALUES (?)", ("real-user-conversation",))

    assert seed._has_pending_seed_rows(research, memory) is False

    with sqlite3.connect(memory) as db:
        db.execute(
            "INSERT INTO conversations VALUES (?)",
            (seed.SEED_CONVERSATION_PREFIX + "conv-1",),
        )
    assert seed._has_pending_seed_rows(research, memory) is True


def test_pending_seed_rows_tolerates_missing_db(tmp_path, capsys):
    """缺库/表缺失时只读探测不得崩溃，且给出诊断。"""
    assert seed._has_pending_seed_rows(
        tmp_path / "missing-r.sqlite3", tmp_path / "missing-m.sqlite3"
    ) is False
    assert "skip probe" in capsys.readouterr().out


def _patched_main_env(tmp_path, monkeypatch):
    research = tmp_path / "research.sqlite3"
    memory = tmp_path / "memory.sqlite3"
    _make_db(research, kind="research")
    _make_db(memory, kind="memory")
    monkeypatch.setattr(seed, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(seed, "MEMORY_DB", memory)
    monkeypatch.setattr(seed, "ResearchStore", lambda: SimpleNamespace(database_path=str(research)))
    monkeypatch.setattr(seed, "clean", lambda store: 0)
    monkeypatch.setattr(seed, "generate", lambda store: None)
    monkeypatch.setattr(sys, "argv", ["seed_demo_research_reports.py"])
    return research, memory


def test_main_skips_snapshot_when_no_seed_rows(tmp_path, monkeypatch, capsys):
    """无条件快照会持续落两份完整 SQLite 且永不清理；无待删数据时必须跳过。"""
    _patched_main_env(tmp_path, monkeypatch)

    seed.main()

    assert "backup: skipped" in capsys.readouterr().out
    assert not (tmp_path / "backup").exists(), "无 seed 数据不得落盘快照"


def test_main_snapshots_when_seed_rows_exist(tmp_path, monkeypatch, capsys):
    """反向验证：确有 seed 数据时仍必须生成两库一致性快照（兜底不丢失）。"""
    _research, memory = _patched_main_env(tmp_path, monkeypatch)
    with sqlite3.connect(memory) as db:
        db.execute(
            "INSERT INTO conversations VALUES (?)",
            (seed.SEED_CONVERSATION_PREFIX + "conv-1",),
        )

    seed.main()

    out = capsys.readouterr().out
    assert "backup:" in out and "skipped" not in out
    snapshots = list((tmp_path / "backup").rglob("*.sqlite3"))
    assert len(snapshots) == 2, "两库都要有快照"
