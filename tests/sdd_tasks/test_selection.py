import json
import multiprocessing
import os
import secrets
import tempfile
import unittest
import uuid
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.claims import ClaimError
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import OwnerIdentity, current_owner
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_catalog import _git
from tests.sdd_tasks.test_claim_validation import _candidate

GATE = "spec-016.cloud-stage-authorized"
NOW = "2026-10-11T12:00:00Z"


def _fixture(directory):
    root, canonical, task, snapshot, db, _ = _candidate(directory)
    db.unlink()
    rebuild(db, root)
    return root, canonical, task, snapshot, db


def _rows(db):
    with closing(connect(db)) as conn:
        return tuple((table, tuple(tuple(row) for row in conn.execute(
            "SELECT * FROM {} ORDER BY rowid".format(table))))
                     for table in ("tasks", "dependencies", "runs", "events", "leases"))


def _owner(executor, pid):
    base = current_owner(executor, pid=pid)
    return OwnerIdentity(executor, base.host_id, pid, base.process_started_at, secrets.token_hex(32))


def _next(root, db, task, gates, snapshots, owner=None, lease_minutes=120):
    with closing(connect(db)) as conn, maintenance_lock(root):
        return claim_next(conn, [task], gates, workspace_snapshots=snapshots,
                          ide="codex", owner=owner or _owner("slice", os.getpid()),
                          now=NOW, lease_minutes=lease_minutes)


def _claim_worker(db, root, task, snapshot, owner, barrier, output):
    try:
        with closing(connect(Path(db))) as conn:
            barrier.wait(timeout=30)
            with maintenance_lock(Path(root)):
                claim = claim_next(conn, [task], {GATE}, workspace_snapshots={
                    task.metadata["task_id"]: snapshot}, ide="codex", owner=owner, now=NOW)
        output.put(("ok", None if claim is None else claim.run_id,
                    None if claim is None else claim.owner.token))
    except BaseException as exc:
        output.put(("error", type(exc).__name__, str(exc)))


def _reject_event(conn, run_id, stamp, snapshot):
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 ("missing-run", 1, stamp, "workspace_snapshot", "{}"))


class SelectionTests(unittest.TestCase):
    def test_two_processes_atomically_create_one_claim_lease_and_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            ctx = multiprocessing.get_context("spawn")
            barrier, output = ctx.Barrier(2), ctx.Queue()
            pid = os.getpid()
            owners = [_owner("atomic-{}".format(i), pid) for i in range(2)]
            self.assertEqual(len({owner.token for owner in owners}), 2)
            processes = [ctx.Process(target=_claim_worker, args=(str(db), str(root), task,
                         snapshot, owner, barrier, output)) for owner in owners]
            for process in processes:
                process.start()
            results = [output.get(timeout=60) for _ in processes]
            for process in processes:
                process.join(30)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sum(result[1] is not None for result in results if result[0] == "ok"), 1)
            self.assertEqual(sum(result[:2] == ("ok", None) for result in results), 1)
            self.assertFalse(any(result[0] == "error" for result in results), results)
            winner = next(result for result in results if result[1] is not None)
            with closing(connect(db)) as conn:
                runs = conn.execute("SELECT run_id,task_id,attempt,state,owner_json FROM runs").fetchall()
                leases = conn.execute("SELECT task_id,run_id,owner_token FROM leases").fetchall()
                events = conn.execute("SELECT run_id,sequence,event_type,payload_json FROM events").fetchall()
            self.assertEqual((len(runs), len(leases), len(events)), (1, 1, 1))
            self.assertEqual((runs[0][1], runs[0][2], runs[0][3]), (task.metadata["task_id"], 1, "claimed"))
            self.assertNotEqual(uuid.UUID(runs[0][0]).int, 0)
            self.assertEqual((leases[0][0], leases[0][1]), (runs[0][1], runs[0][0]))
            self.assertIn(leases[0][2], {owner.token for owner in owners})
            stored_owner = json.loads(runs[0][4])
            self.assertEqual((stored_owner["pid"], stored_owner["token"]), (pid, leases[0][2]))
            self.assertEqual((winner[1], winner[2]), (runs[0][0], leases[0][2]))
            self.assertEqual(stored_owner["process_started_at"], owners[0].process_started_at)
            self.assertEqual((events[0][0], events[0][1], events[0][2]), (runs[0][0], 1, "workspace_snapshot"))
            payload = json.loads(events[0][3])
            self.assertEqual(set(payload), {"schema", "source_run_id", "snapshot"})
            self.assertEqual(payload["schema"], "sdd-workspace-snapshot/v1")
            self.assertIsNone(payload["source_run_id"])
            self.assertEqual(set(payload["snapshot"]), set(snapshot.__dataclass_fields__))
            self.assertEqual(payload["snapshot"]["task_hash"], snapshot.task_hash)
            self.assertEqual(payload["snapshot"]["allowed_hashes"], snapshot.allowed_hashes)

    def test_blocked_dirty_and_task_drift_do_not_write_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, snapshot, db = _fixture(td)
            before = _rows(db)
            owner = _owner("blocked", os.getpid())
            with closing(connect(db)) as conn, maintenance_lock(root):
                self.assertIsNone(claim_next(conn, [task], set(), workspace_snapshots={}, ide="codex",
                                             owner=owner, now=NOW))
            self.assertEqual(_rows(db), before)
            for drift in ("dirty", "task"):
                with self.subTest(drift=drift), tempfile.TemporaryDirectory() as case:
                    root, canonical, task, snapshot, db = _fixture(case)
                    before = _rows(db)
                    if drift == "dirty":
                        (canonical / "unrelated.txt").write_text("untracked\n", encoding="utf-8")
                    else:
                        source = canonical / "docs/sdd/plans/016/task-04-fixture.md"
                        source.write_text("# Changed\n> 当前状态：`待执行`\n\n" +
                                          task_markdown({"title": "Changed"}), encoding="utf-8")
                    with closing(connect(db)) as conn, maintenance_lock(root), self.assertRaises(ClaimError):
                        claim_next(conn, [task], {GATE}, workspace_snapshots={
                            task.metadata["task_id"]: snapshot}, ide="codex",
                            owner=_owner(drift, os.getpid()), now=NOW)
                    self.assertEqual(_rows(db), before)

    def test_completed_active_and_gate_blockers_skip_missing_snapshots(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            task3 = parse_task(root / "docs/sdd/plans/016/task-03-fixture.md")
            before = _rows(db)
            self.assertIsNone(_next(root, db, task3, {GATE}, {}))
            self.assertIsNone(_next(root, db, task, set(), {}))
            self.assertEqual(_rows(db), before)
            claim = _next(root, db, task, {GATE}, {task.metadata["task_id"]: snapshot})
            self.assertIsNotNone(claim)
            before = _rows(db)
            self.assertIsNone(_next(root, db, task, {GATE}, {}))
            self.assertEqual(_rows(db), before)

    def test_failed_streak_and_unverified_migration_skip_before_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, _, db = _fixture(td)
            with closing(connect(db)) as conn:
                for attempt in range(1, 4):
                    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,"
                                 "agent_role,worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (str(uuid.uuid4()), task.metadata["task_id"], attempt, "failed", "codex",
                                  "fixture", "{}", task.metadata["agent_role"], task.metadata["worktree"]["path"],
                                  task.metadata["worktree"]["branch"], "base", task.task_hash, task.prompt_hash, NOW))
            before = _rows(db)
            self.assertIsNone(_next(root, db, task, {GATE}, {}))
            self.assertEqual(_rows(db), before)
        with tempfile.TemporaryDirectory() as td:
            root, _, task, _, db = _fixture(td)
            before = _rows(db)
            unverified = replace(task, metadata=dict(task.metadata, migration_state="unverified"))
            self.assertIsNone(_next(root, db, unverified, {GATE}, {}))
            self.assertEqual(_rows(db), before)

    def test_owner_and_lease_invalid_inputs_fail_without_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            before = _rows(db)
            owner = _owner("valid", os.getpid())
            invalid = (OwnerIdentity("empty", owner.host_id, owner.pid, owner.process_started_at, ""),
                       OwnerIdentity("remote", "sha256:" + "0" * 64, owner.pid,
                                     owner.process_started_at, secrets.token_hex(32)),
                       OwnerIdentity("dead", owner.host_id, 2147483647,
                                     owner.process_started_at, secrets.token_hex(32)))
            for identity in invalid:
                with self.subTest(owner=identity.executor_id), self.assertRaises(ClaimError) as caught:
                    _next(root, db, task, {GATE}, {task.metadata["task_id"]: snapshot}, identity)
                self.assertEqual(caught.exception.code, "CLAIM_OWNER_NOT_ALIVE")
            for lease in (True, 10 ** 100):
                with self.subTest(lease=type(lease).__name__), self.assertRaises(ClaimError) as caught:
                    _next(root, db, task, {GATE}, {task.metadata["task_id"]: snapshot}, owner, lease)
                self.assertEqual(caught.exception.code, "CLAIM_LEASE_INVALID")
            self.assertEqual(_rows(db), before)

    def test_committed_unconfirmed_canonical_spec_waits_with_fresh_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, _, db = _fixture(td)
            spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace("已确认", "待确认", 1),
                            encoding="utf-8")
            _git(canonical, "add", "docs/sdd/specs/016-portable-task-ledger.md")
            _git(canonical, "commit", "-qm", "fixture Spec status change")
            with closing(connect(db)) as conn:
                old_hash = conn.execute("SELECT task_hash FROM tasks WHERE task_id=?",
                                        (task.metadata["task_id"],)).fetchone()[0]
            rebuild(db, root)
            with closing(connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT task_hash FROM tasks WHERE task_id=?",
                                              (task.metadata["task_id"],)).fetchone()[0], old_hash)
            current = capture_snapshot(root, task)
            before = _rows(db)
            self.assertEqual(old_hash, task.task_hash)
            self.assertIsNone(_next(root, db, task, {GATE}, {task.metadata["task_id"]: current}))
            self.assertEqual(_rows(db), before)

    def test_catalog_hash_drift_errors_even_when_gate_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            with closing(connect(db)) as conn:
                conn.execute("UPDATE tasks SET task_hash=? WHERE task_id=?",
                             ("f" * 64, task.metadata["task_id"]))
            before = _rows(db)
            with self.assertRaises(ClaimError) as caught:
                _next(root, db, task, set(), {task.metadata["task_id"]: snapshot})
            self.assertEqual(caught.exception.code, "CLAIM_CATALOG_HASH_STALE")
            self.assertEqual(_rows(db), before)

    def test_snapshot_event_insert_failure_rolls_back_run_and_lease(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            before = _rows(db)
            with patch("scripts.sdd_tasks.selection._insert_event", side_effect=_reject_event), \
                    closing(connect(db)) as conn, maintenance_lock(root), \
                    self.assertRaises(ClaimError) as caught:
                claim_next(conn, [task], {GATE}, workspace_snapshots={
                    task.metadata["task_id"]: snapshot}, ide="codex",
                    owner=_owner("rollback", os.getpid()), now=NOW)
            self.assertEqual(caught.exception.code, "CLAIM_CONFLICT")
            self.assertEqual(_rows(db), before)


if __name__ == "__main__":
    unittest.main()
