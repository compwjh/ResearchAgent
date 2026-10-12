import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone

from scripts.sdd_tasks.leases import LeaseError
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.run_owner import resolve_run_owner
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_selection import _fixture

GATE = "spec-016.cloud-stage-authorized"


def _rows(conn):
    tables = ("schema_migrations", "tasks", "dependencies", "runs", "events", "artifacts", "leases")
    return {table: tuple(tuple(row) for row in conn.execute("SELECT * FROM " + table))
            for table in tables}


@contextmanager
def _claimed(directory):
    root, canonical, task, snapshot, database = _fixture(directory)
    ignore = root / ".gitignore"
    rules = ignore.read_text(encoding="utf-8").splitlines()
    if ".sdd/runtime/" not in rules:
        with ignore.open("a", encoding="utf-8") as stream:
            if rules and ignore.read_text(encoding="utf-8").endswith("\n") is False:
                stream.write("\n")
            stream.write(".sdd/runtime/\n")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        owner = current_owner("owner-fixture", pid=child.pid)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with closing(connect(database)) as conn, maintenance_lock(root):
            claim = claim_next(conn, [task], {GATE}, workspace_snapshots={
                task.metadata["task_id"]: snapshot}, ide="codex", owner=owner,
                now=now, lease_minutes=30)
        if claim is None:
            raise AssertionError("fixture Task was not claimed")
        yield root, canonical, task, database, child, owner, claim
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)


def _replace_identity(conn, run_id, field, value):
    row = conn.execute("SELECT owner_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
    identity = json.loads(row[0])
    identity[field] = value
    conn.execute("UPDATE runs SET owner_json=? WHERE run_id=?",
                 (json.dumps(identity, sort_keys=True, separators=(",", ":")), run_id))


class RunOwnerTests(unittest.TestCase):
    def test_valid_resolution_returns_persisted_private_identity_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, _, _, database, _, owner, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                resolved = resolve_run_owner(conn, claim.run_id, owner.executor_id, owner.pid)
                self.assertEqual(resolved, owner)
                self.assertEqual(resolved.token, owner.token)
                self.assertNotIn(owner.token, repr(resolved))
                self.assertEqual(_rows(conn), before)

    def test_identity_lease_process_and_canonical_refusals_are_read_only(self):
        cases = (
            ("executor", "RUN_OWNER_MISMATCH"), ("pid", "RUN_OWNER_MISMATCH"),
            ("binding", "RUN_OWNER_LEASE_MISMATCH"), ("token", "RUN_OWNER_MISMATCH"),
            ("remote", "RUN_OWNER_NOT_ALIVE"), ("dead", "RUN_OWNER_NOT_ALIVE"),
            ("reused_pid", "RUN_OWNER_NOT_ALIVE"),
            ("expired", "RUN_OWNER_LEASE_INACTIVE"), ("terminal", "RUN_OWNER_NOT_ACTIVE"),
            ("task_hash", "CANONICAL_TASK_HASH_MISMATCH"),
            ("mirror", "TASK_MIRROR_INVALID"),
        )
        for case, code in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, canonical, task, database, child, owner, claim = state
                with closing(connect(database)) as conn:
                    if case == "binding":
                        conn.execute("UPDATE leases SET task_id='spec-016-task-03' WHERE run_id=?",
                                     (claim.run_id,))
                    elif case == "token":
                        _replace_identity(conn, claim.run_id, "token", "different-private-token")
                    elif case == "remote":
                        _replace_identity(conn, claim.run_id, "host_id", "sha256:" + "0" * 64)
                    elif case == "reused_pid":
                        _replace_identity(conn, claim.run_id, "process_started_at", "old-process-start")
                    elif case == "expired":
                        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace(
                            "+00:00", "Z")
                        conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?", (old, claim.run_id))
                    elif case == "terminal":
                        conn.execute("UPDATE runs SET state='failed' WHERE run_id=?", (claim.run_id,))
                    elif case == "task_hash":
                        source = canonical / "docs/sdd/plans/016/task-04-fixture.md"
                        source.write_text("# Fixture\n> 当前状态：`待执行`\n\n" +
                                          task_markdown({"priority": 91}), encoding="utf-8")
                    elif case == "mirror":
                        spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
                        spec.write_text(spec.read_text(encoding="utf-8").replace(
                            "| 待执行 |", "| 完成 |", 1), encoding="utf-8")
                    before = _rows(conn)
                    executor, pid = owner.executor_id, owner.pid
                    if case == "executor":
                        executor = "other-executor"
                    if case == "pid":
                        pid += 1
                    if case == "dead":
                        child.terminate()
                        child.wait(timeout=10)
                    with self.assertRaises(LeaseError) as caught:
                        resolve_run_owner(conn, claim.run_id, executor, pid)
                    self.assertEqual(caught.exception.code, code)
                    self.assertEqual(_rows(conn), before)


if __name__ == "__main__":
    unittest.main()
