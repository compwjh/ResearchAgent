import json
import os
import tempfile
import unittest
import uuid
from contextlib import closing
from dataclasses import asdict

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot, snapshot_payload
from tests.sdd_tasks.test_catalog_spec_status import TASK, _item, _linked, _status


def _run(conn, task, attempt, state, base_commit=None):
    meta = task.metadata
    run_id = str(uuid.uuid4())
    owner = asdict(current_owner("fixture", pid=os.getpid()))
    conn.execute(
        "INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
        "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, meta["task_id"], attempt, state, "codex", "fixture",
         json.dumps(owner),
         meta["agent_role"], meta["worktree"]["path"], meta["worktree"]["branch"],
         base_commit or "a" * 40, task.task_hash, task.prompt_hash, "2026-10-12T00:00:00Z"),
    )
    return run_id


def _event(conn, run_id, sequence, kind, payload):
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)", (
        run_id, sequence, "2026-10-12T00:00:00Z", kind,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    ))


def _abandoned(conn, root, task, decision="unchanged", action="requeued"):
    before = capture_snapshot(root, task)
    run_id = _run(conn, task, 1, "abandoned", before.head)
    conn.execute("UPDATE runs SET ended_at=?,error_code=? WHERE run_id=?",
                 ("2026-10-12T00:00:00Z", "OWNER_DEAD_LEASE_EXPIRED", run_id))
    _event(conn, run_id, 1, "workspace_snapshot", snapshot_payload(before))
    _event(conn, run_id, 2, "recovery_decision", {
        "schema": "sdd-run-recovery/v1", "action": action, "decision": decision,
    })
    return run_id, before


def _rows(conn):
    tables = ("schema_migrations", "tasks", "dependencies", "runs", "events", "artifacts", "leases")
    return {table: tuple(tuple(row) for row in conn.execute("SELECT * FROM " + table))
            for table in tables}


class CatalogEligibilityTests(unittest.TestCase):
    def test_attempt_limit_waits_and_resets_after_nonfailed_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, database = _linked(temp)
            task = parse_task(canonical / "docs/sdd/plans/016/task-04-fixture.md")
            with closing(connect(database)) as conn:
                for attempt in range(1, 4):
                    _run(conn, task, attempt, "failed")
                waiting = _item(_status(database)["waiting"])
                self.assertIn("max_attempts_exhausted", waiting["reasons"])
                conn.execute("DELETE FROM runs WHERE task_id=?", (TASK,))
                for attempt, state in enumerate(("failed", "failed", "succeeded", "failed"), 1):
                    _run(conn, task, attempt, state)
                eligible = _item(_status(database)["eligible"])
                self.assertEqual(eligible["reasons"], [])

    def test_missing_and_extra_dependency_index_rows_are_reported_stale(self):
        for extra in (False, True):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temp:
                _, _, database = _linked(temp)
                with closing(connect(database)) as conn:
                    if extra:
                        conn.execute("INSERT INTO dependencies VALUES (?,?)", (TASK, TASK))
                    else:
                        conn.execute("DELETE FROM dependencies WHERE task_id=?", (TASK,))
                item = _item(_status(database)["waiting"])
                self.assertIn("dependency_index_stale", item["reasons"])

    def test_valid_latest_abandoned_recovery_is_informational_and_eligible(self):
        for kind, action, decision in (("unchanged", "requeued", "unchanged"),
                                       ("partial", "preserved_for_recovery", "partial")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root, canonical, database = _linked(temp)
                task = parse_task(canonical / "docs/sdd/plans/016/task-04-fixture.md")
                with closing(connect(database)) as conn:
                    _abandoned(conn, root, task, decision, action)
                    if kind == "partial":
                        target = canonical / "tests/sdd_tasks/recovery.py"
                        target.parent.mkdir(parents=True)
                        target.write_text("partial\n", encoding="utf-8")
                item = _item(_status(database)["eligible"])
                self.assertEqual(item["reasons"], ["recovery_ready:" + kind])

    def test_recovery_conflict_and_malformed_event_wait_without_database_writes(self):
        for malformed in (False, True):
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as temp:
                root, canonical, database = _linked(temp)
                task = parse_task(canonical / "docs/sdd/plans/016/task-04-fixture.md")
                with closing(connect(database)) as conn:
                    run_id, _ = _abandoned(conn, root, task)
                    if malformed:
                        conn.execute("UPDATE events SET payload_json=? WHERE run_id=? AND event_type=?",
                                     ('{"bad":true}', run_id, "recovery_decision"))
                    else:
                        (canonical / "outside.txt").write_text("keep\n", encoding="utf-8")
                    before = _rows(conn)
                    item = _item(_status(database)["waiting"])
                    expected = ("recovery_invalid:RECOVERY_EVENT_INVALID" if malformed
                                else "recovery_workspace_conflict")
                    self.assertIn(expected, item["reasons"])
                    self.assertEqual(_rows(conn), before)

    def test_latest_active_recovery_claim_hides_consumed_abandoned_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, database = _linked(temp)
            task = parse_task(canonical / "docs/sdd/plans/016/task-04-fixture.md")
            with closing(connect(database)) as conn:
                parent, before = _abandoned(conn, root, task)
                child = _run(conn, task, 2, "claimed", before.head)
                _event(conn, child, 1, "workspace_snapshot", snapshot_payload(before, parent))
                _event(conn, child, 2, "recovery_claim", {
                    "schema": "sdd-recovery-claim/v1", "recovery_of": parent,
                })
            report = _status(database)
            item = _item(report["running"])
            self.assertEqual(item["reasons"], ["run_state:claimed"])
            self.assertFalse(any(row["task_id"] == TASK for key in ("eligible", "waiting")
                                 for row in report[key]))


if __name__ == "__main__":
    unittest.main()
