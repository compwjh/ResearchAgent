import dataclasses
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing

from scripts.sdd_tasks.leases import recover_expired
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot, compare_snapshot, snapshot_payload
from tests.sdd_tasks.test_selection import _fixture

NOW = "2026-10-11T12:00:00Z"


def _owner_fields(owner):
    return json.dumps({"executor_id": owner.executor_id, "host_id": owner.host_id,
                       "pid": owner.pid, "process_started_at": owner.process_started_at,
                       "token": owner.token}, sort_keys=True, separators=(",", ":"))


def _dead_owner():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        owner = current_owner("executor", pid=child.pid)
        child.terminate()
        child.wait(timeout=10)
        return owner
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


def _recover(root, conn, run_id, decision, alive=False):
    with maintenance_lock(root):
        return recover_expired(conn, run_id, alive, decision, now=NOW)


def _seed(conn, task, snapshot, owner, expires):
    run_id, stamp = str(uuid.uuid4()), "2026-10-11T11:00:00Z"
    meta = task.metadata
    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                 "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (run_id, meta["task_id"], 1, "running", "codex", owner.executor_id,
                  _owner_fields(owner), meta["agent_role"], meta["worktree"]["path"],
                  snapshot.branch, snapshot.head, task.task_hash, task.prompt_hash, stamp))
    conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                 (meta["task_id"], run_id, owner.token, stamp, stamp, expires))
    payload = json.dumps(snapshot_payload(snapshot), sort_keys=True, separators=(",", ":"))
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 (run_id, 1, stamp, "workspace_snapshot", payload))
    return run_id


def _rows(conn, run_id):
    return tuple(tuple(row) for table in ("runs", "leases", "events")
                 for row in conn.execute("SELECT * FROM {} WHERE run_id=? ORDER BY rowid".format(table), (run_id,)))


def _damage(case, conn, root, worktree, task, run_id):
    target = worktree / "scripts/sdd_tasks/allowed.txt"
    if case == "lease_token":
        conn.execute("UPDATE leases SET owner_token='different' WHERE run_id=?", (run_id,))
    elif case == "lease_task":
        other = conn.execute("SELECT task_id FROM tasks WHERE task_id<>? ORDER BY task_id LIMIT 1",
                             (task.metadata["task_id"],)).fetchone()[0]
        conn.execute("UPDATE leases SET task_id=? WHERE run_id=?", (other, run_id))
    elif case == "run_hash":
        conn.execute("UPDATE runs SET task_hash=? WHERE run_id=?", ("0" * 64, run_id))
    elif case == "task_file":
        target = worktree / task.path.relative_to(root)
        target.write_text(target.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    elif case in {"base", "branch"}:
        raw = conn.execute("SELECT payload_json FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
        payload = json.loads(raw)
        payload["snapshot"]["head" if case == "base" else "branch"] = "0" * 40
        conn.execute("UPDATE events SET payload_json=? WHERE run_id=?",
                     (json.dumps(payload, sort_keys=True, separators=(",", ":")), run_id))
    elif case == "outside":
        target = worktree / "outside.txt"
        target.write_text("out of scope\n", encoding="utf-8")
    elif case == "nan":
        conn.execute("UPDATE events SET payload_json='NaN' WHERE run_id=?", (run_id,))
    else:
        conn.execute("UPDATE events SET sequence=2 WHERE run_id=?", (run_id,))
    return target


class LeaseRecoveryTests(unittest.TestCase):
    def test_live_active_and_remote_unknown_owners_refuse_without_writes(self):
        cases = ("active", "live", "remote")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                try:
                    owner = current_owner("executor", pid=child.pid)
                    if case == "remote":
                        owner = dataclasses.replace(owner, host_id="another-host")
                    with closing(connect(db)) as conn:
                        expiry = "2099-01-01T00:00:00Z" if case == "active" else "2000-01-01T00:00:00Z"
                        run_id = _seed(conn, task, before, owner, expiry)
                        if case != "live":
                            child.terminate()
                            child.wait(timeout=10)
                        current = capture_snapshot(root, task)
                        decision = compare_snapshot(before, current)
                        rows = _rows(conn, run_id)
                        with self.assertRaises(ValueError):
                            _recover(root, conn, run_id, decision)
                        self.assertEqual(_rows(conn, run_id), rows)
                        self.assertEqual((worktree / "scripts/sdd_tasks/allowed.txt").read_text(), "baseline\n")
                finally:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=10)

    def test_expired_dead_owner_unchanged_requeues_and_closes_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            owner = current_owner("executor", pid=child.pid)
            child.terminate()
            child.wait(timeout=10)
            try:
                with closing(connect(db)) as conn:
                    run_id = _seed(conn, task, before, owner, "2000-01-01T00:00:00Z")
                    decision = compare_snapshot(before, capture_snapshot(root, task))
                    report = _recover(root, conn, run_id, decision)
                    self.assertEqual((report.run_id, report.state, report.action),
                                     (run_id, "abandoned", "requeued"))
                    run = conn.execute("SELECT state,ended_at,error_code FROM runs WHERE run_id=?",
                                       (run_id,)).fetchone()
                    self.assertEqual(tuple(run), ("abandoned", NOW, run[2]))
                    self.assertTrue(run[2])
                    self.assertEqual(conn.execute("SELECT count(*) FROM leases WHERE run_id=?",
                                                  (run_id,)).fetchone()[0], 0)
                    event = conn.execute("SELECT event_type,payload_json FROM events WHERE run_id=? "
                                         "ORDER BY sequence DESC LIMIT 1", (run_id,)).fetchone()
                    self.assertEqual(event[0], "recovery_decision")
                    self.assertEqual(json.loads(event[1]), {"schema": "sdd-run-recovery/v1",
                                     "action": "requeued", "decision": "unchanged"})
                    self.assertEqual((worktree / "scripts/sdd_tasks/allowed.txt").read_text(), "baseline\n")
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)

    def test_partial_change_is_preserved_and_forged_decision_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            owner = current_owner("executor", pid=child.pid)
            child.terminate()
            child.wait(timeout=10)
            target = worktree / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial\n", encoding="utf-8")
            try:
                with closing(connect(db)) as conn:
                    run_id = _seed(conn, task, before, owner, "2000-01-01T00:00:00Z")
                    after = capture_snapshot(root, task)
                    decision = compare_snapshot(before, after)
                    rows = _rows(conn, run_id)
                    with self.assertRaises(ValueError):
                        _recover(root, conn, run_id, dataclasses.replace(decision, kind="unchanged"))
                    self.assertEqual(_rows(conn, run_id), rows)
                    report = _recover(root, conn, run_id, decision)
                    self.assertEqual((report.state, report.action), ("abandoned", "preserved_for_recovery"))
                    self.assertEqual(json.loads(conn.execute("SELECT payload_json FROM events WHERE run_id=? "
                                     "ORDER BY sequence DESC LIMIT 1", (run_id,)).fetchone()[0]),
                                     {"schema": "sdd-run-recovery/v1", "action": "preserved_for_recovery",
                                      "decision": "partial"})
                    self.assertEqual(conn.execute("SELECT count(*) FROM leases WHERE run_id=?",
                                                  (run_id,)).fetchone()[0], 0)
                    self.assertEqual(target.read_text(encoding="utf-8"), "partial\n")
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)

    def test_binding_baseline_task_and_event_corruption_refuse_without_writes(self):
        cases = ("lease_token", "lease_task", "run_hash", "task_file", "base", "branch",
                 "outside", "nan", "sequence")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                owner = _dead_owner()
                with closing(connect(db)) as conn:
                    run_id = _seed(conn, task, before, owner, "2000-01-01T00:00:00Z")
                    target = _damage(case, conn, root, worktree, task, run_id)
                    rows, contents = _rows(conn, run_id), target.read_bytes()
                    decision = compare_snapshot(before, capture_snapshot(root, task))
                    with self.assertRaises(ValueError):
                        _recover(root, conn, run_id, decision)
                    self.assertEqual(_rows(conn, run_id), rows)
                    self.assertEqual(target.read_bytes(), contents)

    def test_expiry_equality_is_expired_and_caller_transaction_is_refused(self):
        for in_transaction in (False, True):
            with self.subTest(in_transaction=in_transaction), tempfile.TemporaryDirectory() as temp:
                root, _, task, before, db = _fixture(temp)
                owner = _dead_owner()
                with closing(connect(db)) as conn:
                    run_id = _seed(conn, task, before, owner, NOW)
                    decision = compare_snapshot(before, capture_snapshot(root, task))
                    if in_transaction:
                        conn.execute("BEGIN")
                    rows = _rows(conn, run_id)
                    if in_transaction:
                        with self.assertRaises(ValueError):
                            _recover(root, conn, run_id, decision)
                        self.assertEqual(_rows(conn, run_id), rows)
                        conn.rollback()
                    else:
                        report = _recover(root, conn, run_id, decision)
                        self.assertEqual((report.state, report.action), ("abandoned", "requeued"))


if __name__ == "__main__":
    unittest.main()
