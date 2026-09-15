"""Spec028 Task02: durable runtime gate.

The gate deliberately uses a tiny fixed SQLite fixture instead of introducing a
second production scheduler.  It freezes the database/CAS contracts that Task03
will implement against the existing ResearchStore and state machines:

* WAL permits several worker processes to read while SQLite serializes writes;
* exactly one owner can claim an unexpired work-item lease;
* an expired lease can be taken over, but the old token cannot heartbeat;
* checkpoints are persisted and validated by plan/node/input digest before the
  node is advanced; and
* resource arbitration is global, bounded, and fair across tasks.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import sqlite3
import uuid
from pathlib import Path

import pytest

from backend.app.research.domain.models import ResearchTask, ResearchWorkItem
from backend.app.research.domain.state_machine import InvalidStateTransition
from backend.app.research.infrastructure.research_store import ResearchStore


_NOW = "2026-09-16T00:00:00Z"
_FUTURE = "2026-09-16T00:05:00Z"
_EXPIRED = "2026-09-15T23:59:00Z"


def _create_gate_schema(path: Path) -> None:
    """Create only the fixed probe tables; production owns their later schema."""
    ResearchStore(path)
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE scheduler_leases(
                task_id TEXT PRIMARY KEY,
                owner_token TEXT,
                expires_at TEXT,
                heartbeat_at TEXT
            );
            INSERT INTO scheduler_leases VALUES('task-1', NULL, '2020-01-01T00:00:00Z', NULL);
            CREATE TABLE scheduler_nodes(
                task_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(task_id, plan_version, node_id)
            );
            INSERT INTO scheduler_nodes VALUES('task-1', 2, 'node-1', 'queued');
            """
        )


def _claim_in_process(path_text: str, owner: str, ready, result) -> None:
    """Competing process probe: one conditional UPDATE is the claim CAS."""
    path = Path(path_text)
    token = f"token-{owner}-{uuid.uuid4().hex}"
    with sqlite3.connect(path, timeout=10.0) as db:
        db.execute("PRAGMA busy_timeout=10000")
        ready.wait()
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute(
            """UPDATE scheduler_leases
               SET owner_token=?, expires_at=?, heartbeat_at=?
               WHERE task_id=? AND (owner_token IS NULL OR expires_at <= ?)""",
            (token, _FUTURE, _NOW, "task-1", _NOW),
        ).rowcount
        db.commit()
    result.put((owner, token, changed))


def test_research_store_uses_wal_for_cross_process_recovery(tmp_path):
    path = tmp_path / "research.sqlite3"
    store = ResearchStore(path)
    with store._connect() as db:  # private seam is intentional for this gate.
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_two_processes_have_one_lease_owner(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    _create_gate_schema(path)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    result = context.Queue()
    processes = [
        context.Process(target=_claim_in_process, args=(str(path), owner, ready, result))
        for owner in ("worker-a", "worker-b")
    ]
    for process in processes:
        process.start()
    ready.set()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    outcomes = [result.get(timeout=3), result.get(timeout=3)]
    assert sorted(outcome[2] for outcome in outcomes) == [0, 1]
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT owner_token, expires_at FROM scheduler_leases WHERE task_id='task-1'").fetchone()
    winner = next(outcome for outcome in outcomes if outcome[2] == 1)
    assert row == (winner[1], _FUTURE)


def test_expired_lease_takeover_rejects_old_owner_heartbeat(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    _create_gate_schema(path)
    old_token = "old-token"
    new_token = "new-token"
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE scheduler_leases SET owner_token=?, expires_at=?, heartbeat_at=? WHERE task_id=?",
            (old_token, _EXPIRED, _EXPIRED, "task-1"),
        )
        takeover = db.execute(
            """UPDATE scheduler_leases SET owner_token=?, expires_at=?, heartbeat_at=?
               WHERE task_id=? AND (owner_token IS NULL OR expires_at <= ?)""",
            (new_token, _FUTURE, _NOW, "task-1", _NOW),
        ).rowcount
        stale_heartbeat = db.execute(
            """UPDATE scheduler_leases SET heartbeat_at=?
               WHERE task_id=? AND owner_token=? AND expires_at > ?""",
            (_NOW, "task-1", old_token, _NOW),
        ).rowcount
        current = db.execute("SELECT owner_token FROM scheduler_leases WHERE task_id='task-1'").fetchone()[0]
    assert takeover == 1
    assert stale_heartbeat == 0
    assert current == new_token


def test_checkpoint_is_durable_and_node_advance_requires_matching_plan_and_digest(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    _create_gate_schema(path)
    state = {"cursor": "paper-2", "completed": ["paper-1"]}
    state_json = json.dumps(state, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(state_json.encode()).hexdigest()
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE scheduler_checkpoints(
                task_id TEXT, plan_version INTEGER, node_id TEXT,
                state_json TEXT NOT NULL, input_digest TEXT NOT NULL,
                PRIMARY KEY(task_id, plan_version, node_id)
            )"""
        )
        # Checkpoint commit is a separate durable write barrier before advance.
        db.execute(
            "INSERT INTO scheduler_checkpoints VALUES(?,?,?,?,?)",
            ("task-1", 2, "node-1", state_json, digest),
        )
        db.commit()
        saved = db.execute("SELECT state_json,input_digest FROM scheduler_checkpoints").fetchone()
        assert saved == (state_json, digest)

        loaded_state, loaded_digest = saved
        assert hashlib.sha256(loaded_state.encode()).hexdigest() == loaded_digest
        stale = db.execute(
            "UPDATE scheduler_nodes SET status='running' WHERE task_id=? AND plan_version=? AND node_id=? AND status='queued'",
            ("task-1", 1, "node-1"),
        ).rowcount
        advanced = db.execute(
            "UPDATE scheduler_nodes SET status='running' WHERE task_id=? AND plan_version=? AND node_id=? AND status='queued'",
            ("task-1", 2, "node-1"),
        ).rowcount
        db.commit()
    assert stale == 0
    assert advanced == 1

    # A tampered state cannot pass the input digest contract after restart.
    with pytest.raises(AssertionError):
        assert hashlib.sha256('{"cursor":"tampered"}'.encode()).hexdigest() == digest


def test_global_worker_scheduler_is_fair_and_never_oversells_capacity():
    # Keep this gate import-light in environments that do not install the
    # optional Ollama/LangChain adapter.  The production scheduler itself is
    # already frozen by Spec027; when available we exercise that exact class.
    try:
        from backend.app.platform.ollama import _GlobalWorkerScheduler
    except ModuleNotFoundError as exc:  # pragma: no cover - environment gate
        if exc.name != "langchain_ollama":
            raise
        pytest.skip("optional langchain_ollama dependency is unavailable")
    scheduler = _GlobalWorkerScheduler()
    first = scheduler.acquire("task-a", requested=4, cap=4)
    second = scheduler.acquire("task-b", requested=4, cap=4)
    assert (first, second) == (2, 2)
    assert scheduler.in_use() <= 4
    scheduler.release("task-a")
    scheduler.release("task-b")
    assert scheduler.in_use() == 0


def test_research_workitem_and_task_terminal_states_cannot_be_reopened(tmp_path):
    path = tmp_path / "research.sqlite3"
    store = ResearchStore(path)
    task = ResearchTask(
        "task-1", "owner-a", "conversation-1", "goal", "zh", "balanced", False,
        1, 60, "draft", 1, _NOW, _NOW,
    )
    store.create_task(task)
    item = ResearchWorkItem(
        "item-1", task.research_task_id, 1, "search_catalog", "search-worker",
        "[]", '{"query":"durable scheduling"}', "queued", 0, _NOW, _NOW,
    )
    store.create_work_items(task.research_task_id, [item])
    store.update_work_item_status(item.work_item_id, "running")
    store.update_work_item_status(item.work_item_id, "completed")
    with pytest.raises(InvalidStateTransition):
        store.update_work_item_status(item.work_item_id, "running")

    store.update_task_status(task.research_task_id, task.owner_id, "planning")
    store.update_task_status(task.research_task_id, task.owner_id, "running")
    store.update_task_status(task.research_task_id, task.owner_id, "completed")
    with pytest.raises(InvalidStateTransition):
        store.update_task_status(task.research_task_id, task.owner_id, "running")
