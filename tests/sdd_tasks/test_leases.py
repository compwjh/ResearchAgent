import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.leases import LeaseError, refresh_lease
from scripts.sdd_tasks.store import connect, initialize, transaction

_NOW = "2026-10-11T01:00:00Z"


def _ledger(path, *, state="running", expires="2026-10-11T02:00:00Z",
            lease_task="T1", lease_run="R1", run_task="T1", owner_token="secret",
            json_token=None, owner_json=None):
    conn = connect(path)
    initialize(conn)
    for task_id in ("T1", "T2"):
        conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)",
                     (task_id, "task.md", "pending", 1, _NOW, "a" * 64, "b" * 64, "{}"))
    for run_id, task_id in (("R1", "T1"), ("R2", "T2")):
        token = json_token if run_id == lease_run and json_token is not None else owner_token
        owner = owner_json or json.dumps({"executor_id": "exec", "host_id": "host", "pid": 42,
            "process_started_at": "linux:boot:42", "token": token})
        conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                     "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (run_id, task_id, 1, state, "codex", "exec", owner, "tester", ".worktrees/spec-016",
                      "feature/spec-016-portable-task-ledger", "abc", "a" * 64, "b" * 64, _NOW))
    conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                 (lease_task, lease_run, owner_token, _NOW, _NOW, expires))
    return conn


def _rows(conn):
    return {table: tuple(tuple(row) for row in conn.execute("SELECT * FROM " + table))
            for table in ("tasks", "runs", "leases", "events")}


class LeaseRefreshTests(unittest.TestCase):
    def test_refresh_updates_only_matching_unexpired_active_owner(self):
        with tempfile.TemporaryDirectory() as temp, closing(_ledger(Path(temp) / "ledger.db")) as conn:
            self.assertEqual(refresh_lease(conn, "R1", "secret", now=_NOW, lease_minutes=30),
                             "2026-10-11T01:30:00Z")
            row = conn.execute("SELECT claimed_at,refreshed_at,expires_at FROM leases").fetchone()
            self.assertEqual(tuple(row), (_NOW, _NOW, "2026-10-11T01:30:00Z"))

    def test_rejections_preserve_database_rows(self):
        cases = (({}, "other", _NOW, 120, "LEASE_OWNER_MISMATCH"),
                 ({"expires": _NOW}, "secret", _NOW, 120, "LEASE_EXPIRED"),
                 ({"state": "succeeded"}, "secret", _NOW, 120, "LEASE_RUN_NOT_ACTIVE"),
                 ({"json_token": "other"}, "secret", _NOW, 120, "LEASE_OWNER_MISMATCH"),
                 ({"owner_json": "{}"}, "secret", _NOW, 120, "LEASE_OWNER_INVALID"),
                 ({}, "secret", "bad-time", 120, "LEASE_TIMESTAMP_INVALID"),
                 ({}, "secret", _NOW, 0, "LEASE_DURATION_INVALID"))
        for options, token, now, minutes, code in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp, \
                    closing(_ledger(Path(temp) / "ledger.db", **options)) as conn:
                before = _rows(conn)
                with self.assertRaises(LeaseError) as error:
                    refresh_lease(conn, "R1", token, now=now, lease_minutes=minutes)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(_rows(conn), before)

    def test_lease_must_bind_to_the_run_task(self):
        with tempfile.TemporaryDirectory() as temp, closing(
                _ledger(Path(temp) / "ledger.db", lease_run="R2")) as conn:
            before = _rows(conn)
            with self.assertRaises(LeaseError) as error:
                refresh_lease(conn, "R2", "secret", now=_NOW)
            self.assertEqual(error.exception.code, "LEASE_BINDING_MISMATCH")
            self.assertEqual(_rows(conn), before)

    def test_caller_transaction_is_refused_and_outer_rollback_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp, closing(_ledger(Path(temp) / "ledger.db")) as conn:
            before = _rows(conn)
            with self.assertRaises(RuntimeError), transaction(conn):
                conn.execute("UPDATE leases SET refreshed_at='changed'")
                with self.assertRaises(LeaseError) as error:
                    refresh_lease(conn, "R1", "secret", now=_NOW)
                self.assertEqual(error.exception.code, "LEASE_TRANSACTION_ACTIVE")
                raise RuntimeError("rollback caller transaction")
            self.assertEqual(_rows(conn), before)


if __name__ == "__main__":
    unittest.main()
