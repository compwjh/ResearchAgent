import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing

from scripts.sdd_tasks.claims import ClaimError
from scripts.sdd_tasks.leases import recover_expired
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot, compare_snapshot, snapshot_payload
from tests.sdd_tasks.test_selection import _fixture

GATE = "spec-016.cloud-stage-authorized"
NOW = "2026-10-11T12:00:00Z"


def _dead_owner():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        owner = current_owner("expired-executor", pid=child.pid)
        child.terminate()
        child.wait(timeout=10)
        return owner
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


def _seed(conn, task, snapshot, owner):
    run_id, stamp = str(uuid.uuid4()), "2026-10-11T11:00:00Z"
    meta = task.metadata
    identity = {"executor_id": owner.executor_id, "host_id": owner.host_id, "pid": owner.pid,
                "process_started_at": owner.process_started_at, "token": owner.token}
    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                 "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (run_id, meta["task_id"], 1, "running", "codex", owner.executor_id,
                  json.dumps(identity, sort_keys=True, separators=(",", ":")), meta["agent_role"],
                  meta["worktree"]["path"], snapshot.branch, snapshot.head, task.task_hash,
                  task.prompt_hash, stamp))
    conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                 (meta["task_id"], run_id, owner.token, stamp, stamp, "2000-01-01T00:00:00Z"))
    payload = json.dumps(snapshot_payload(snapshot), sort_keys=True, separators=(",", ":"))
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 (run_id, 1, stamp, "workspace_snapshot", payload))
    return run_id


def _recover(root, db, task, run_id, before):
    with closing(connect(db)) as conn, maintenance_lock(root):
        decision = compare_snapshot(before, capture_snapshot(root, task))
        return recover_expired(conn, run_id, False, decision, now=NOW)


def _claim(root, db, task, snapshot, *, fresh=False, owner=None):
    owner = owner or current_owner("resume-executor", pid=os.getpid())
    with closing(connect(db)) as conn, maintenance_lock(root):
        selected = capture_snapshot(root, task) if fresh else snapshot
        return claim_next(conn, [task], {GATE}, workspace_snapshots={task.metadata["task_id"]: selected},
                          ide="codex", owner=owner, now=NOW)


def _ledger(conn):
    return tuple((table, tuple(tuple(row) for row in conn.execute(
        "SELECT * FROM {} ORDER BY rowid".format(table))))
        for table in ("tasks", "dependencies", "runs", "events", "leases"))


class RecoveryClaimTests(unittest.TestCase):
    def test_partial_recovery_claim_links_parent_and_copies_original_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            with closing(connect(db)) as conn:
                abandoned = _seed(conn, task, before, _dead_owner())
            target = worktree / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial\n", encoding="utf-8")
            report = _recover(root, db, task, abandoned, before)
            self.assertEqual((report.state, report.action), ("abandoned", "preserved_for_recovery"))
            claim = _claim(root, db, task, before)
            self.assertEqual((claim.attempt, claim.recovery_of), (2, abandoned))
            with closing(connect(db)) as conn:
                events = conn.execute("SELECT sequence,event_type,payload_json FROM events WHERE run_id=? "
                                      "ORDER BY sequence", (claim.run_id,)).fetchall()
            self.assertEqual([(row[0], row[1]) for row in events],
                             [(1, "workspace_snapshot"), (2, "recovery_claim")])
            snapshot_event, claim_event = (json.loads(row[2]) for row in events)
            self.assertEqual(snapshot_event["source_run_id"], abandoned)
            self.assertEqual(snapshot_event["snapshot"], snapshot_payload(before)["snapshot"])
            self.assertEqual(claim_event, {"schema": "sdd-recovery-claim/v1", "recovery_of": abandoned})
            self.assertEqual(target.read_text(encoding="utf-8"), "partial\n")

    def test_unchanged_requeue_claim_is_fresh_with_null_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            with closing(connect(db)) as conn:
                abandoned = _seed(conn, task, before, _dead_owner())
            report = _recover(root, db, task, abandoned, before)
            self.assertEqual((report.state, report.action), ("abandoned", "requeued"))
            claim = _claim(root, db, task, before, fresh=True)
            self.assertIsNone(claim.recovery_of)
            with closing(connect(db)) as conn:
                events = conn.execute("SELECT sequence,event_type,payload_json FROM events WHERE run_id=? "
                                      "ORDER BY sequence", (claim.run_id,)).fetchall()
            self.assertEqual([(row[0], row[1]) for row in events], [(1, "workspace_snapshot")])
            payload = json.loads(events[0][2])
            self.assertIsNone(payload["source_run_id"])
            self.assertEqual(payload["snapshot"]["status_records"], [])
            self.assertEqual(payload["snapshot"]["head"], before.head)
            self.assertEqual((worktree / "scripts/sdd_tasks/allowed.txt").read_text(), "baseline\n")

    def test_successive_partial_claims_keep_original_baseline_and_immediate_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            with closing(connect(db)) as conn:
                first = _seed(conn, task, before, _dead_owner())
            target = worktree / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial one\n", encoding="utf-8")
            _recover(root, db, task, first, before)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                owner = current_owner("second-executor", pid=child.pid)
                second_claim = _claim(root, db, task, before, owner=owner)
                with closing(connect(db)) as conn:
                    rows = _ledger(conn)
                self.assertEqual(second_claim.recovery_of, first)
                self.assertIsNone(_claim(root, db, task, before))
                with closing(connect(db)) as conn:
                    self.assertEqual(_ledger(conn), rows)
                    conn.execute("UPDATE leases SET expires_at='2000-01-01T00:00:00Z' WHERE run_id=?",
                                 (second_claim.run_id,))
                target.write_text("partial two\n", encoding="utf-8")
                child.terminate()
                child.wait(timeout=10)
                report = _recover(root, db, task, second_claim.run_id, before)
                self.assertEqual(report.action, "preserved_for_recovery")
                third_claim = _claim(root, db, task, before)
                self.assertEqual(third_claim.recovery_of, second_claim.run_id)
                with closing(connect(db)) as conn:
                    event_sets = {}
                    for run_id in (second_claim.run_id, third_claim.run_id):
                        event_sets[run_id] = [json.loads(row[0]) for row in conn.execute(
                            "SELECT payload_json FROM events WHERE run_id=? AND event_type='workspace_snapshot'",
                            (run_id,))]
                    claims = [json.loads(row[0]) for row in conn.execute(
                        "SELECT payload_json FROM events WHERE run_id=? AND event_type='recovery_claim'",
                        (third_claim.run_id,))]
                self.assertEqual(event_sets[second_claim.run_id][0]["source_run_id"], first)
                self.assertEqual(event_sets[third_claim.run_id][0]["source_run_id"], second_claim.run_id)
                self.assertEqual(event_sets[second_claim.run_id][0]["snapshot"],
                                 snapshot_payload(before)["snapshot"])
                self.assertEqual(event_sets[third_claim.run_id][0]["snapshot"],
                                 snapshot_payload(before)["snapshot"])
                self.assertEqual(claims, [{"schema": "sdd-recovery-claim/v1",
                                           "recovery_of": second_claim.run_id}])
                self.assertEqual(target.read_text(encoding="utf-8"), "partial two\n")
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)

    def test_malformed_recovery_classification_is_rejected_without_ledger_changes(self):
        payloads = (('{"schema":"sdd-run-recovery/v1","action":[],"decision":"unchanged"}'),
                    ('{"schema":"sdd-run-recovery/v1","action":"other","decision":"unchanged"}'),
                    ('{"schema":"sdd-run-recovery/v1","action":null,"decision":"unchanged"}'),
                    ('{"schema":"sdd-run-recovery/v1","action":"requeued","decision":NaN}'))
        for payload in payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                with closing(connect(db)) as conn:
                    abandoned = _seed(conn, task, before, _dead_owner())
                _recover(root, db, task, abandoned, before)
                with closing(connect(db)) as conn:
                    conn.execute("UPDATE events SET payload_json=? WHERE run_id=? AND event_type='recovery_decision'",
                                 (payload, abandoned))
                    rows = _ledger(conn)
                with self.assertRaises(ClaimError) as error:
                    _claim(root, db, task, before, fresh=True)
                self.assertEqual(error.exception.code, "CLAIM_RECOVERY_EVENT_INVALID")
                with closing(connect(db)) as conn:
                    self.assertEqual(_ledger(conn), rows)
                self.assertEqual((worktree / "scripts/sdd_tasks/allowed.txt").read_text(), "baseline\n")

    def test_current_dirty_snapshot_is_not_accepted_as_partial_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db = _fixture(temp)
            with closing(connect(db)) as conn:
                abandoned = _seed(conn, task, before, _dead_owner())
            target = worktree / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial\n", encoding="utf-8")
            _recover(root, db, task, abandoned, before)
            dirty = capture_snapshot(root, task)
            with closing(connect(db)) as conn:
                rows, contents = _ledger(conn), target.read_bytes()
            with self.assertRaises(ClaimError) as error:
                _claim(root, db, task, dirty)
            self.assertEqual(error.exception.code, "CLAIM_RECOVERY_SNAPSHOT_MISMATCH")
            with closing(connect(db)) as conn:
                self.assertEqual(_ledger(conn), rows)
            self.assertEqual(target.read_bytes(), contents)

    def test_terminal_failure_uses_fresh_rules_and_retains_dirty_conflict(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                with closing(connect(db)) as conn:
                    abandoned = _seed(conn, task, before, _dead_owner())
                _recover(root, db, task, abandoned, before)
                with closing(connect(db)) as conn:
                    conn.execute("UPDATE runs SET state='failed',ended_at=?,error_code='TEST_FAILURE' "
                                 "WHERE run_id=?", (NOW, abandoned))
                target = worktree / "scripts/sdd_tasks/allowed.txt"
                if dirty:
                    target.write_text("preserve\n", encoding="utf-8")
                    with closing(connect(db)) as conn:
                        rows, contents = _ledger(conn), target.read_bytes()
                    with self.assertRaises(ClaimError):
                        _claim(root, db, task, before, fresh=True)
                    with closing(connect(db)) as conn:
                        self.assertEqual(_ledger(conn), rows)
                    self.assertEqual(target.read_bytes(), contents)
                else:
                    claim = _claim(root, db, task, before, fresh=True)
                    self.assertIsNone(claim.recovery_of)
                    with closing(connect(db)) as conn:
                        event = conn.execute("SELECT payload_json FROM events WHERE run_id=? "
                                             "AND event_type='workspace_snapshot'", (claim.run_id,)).fetchone()[0]
                    self.assertIsNone(json.loads(event)["source_run_id"])


if __name__ == "__main__":
    unittest.main()
