import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import snapshot_payload
from tests.sdd_tasks.test_selection import _fixture


def _process():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        return child, current_owner("cli-recover", pid=child.pid)
    except BaseException:
        child.terminate()
        child.wait(timeout=10)
        raise


def _seed(conn, task, before, owner):
    run_id, stamp = str(uuid.uuid4()), "2000-01-01T00:00:00Z"
    meta = task.metadata
    identity = {"executor_id": owner.executor_id, "host_id": owner.host_id, "pid": owner.pid,
                "process_started_at": owner.process_started_at, "token": owner.token}
    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                 "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (run_id, meta["task_id"], 1, "running", "codex", owner.executor_id,
                  json.dumps(identity, sort_keys=True, separators=(",", ":")), meta["agent_role"],
                  meta["worktree"]["path"], before.branch, before.head, task.task_hash, task.prompt_hash, stamp))
    conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                 (meta["task_id"], run_id, owner.token, stamp, stamp, stamp))
    payload = json.dumps(snapshot_payload(before), sort_keys=True, separators=(",", ":"))
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)", (run_id, 1, stamp, "workspace_snapshot", payload))
    return run_id


def _rows(db):
    with closing(connect(db)) as conn:
        return tuple((table, tuple(tuple(row) for row in conn.execute(
            "SELECT * FROM {} ORDER BY rowid".format(table))))
            for table in ("tasks", "dependencies", "runs", "events", "leases"))


def _cli(root, run_id):
    project = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(project), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "scripts.sdd_tasks", "--repo", str(root),
                           "recover", "--run-id", run_id], env=env, capture_output=True,
                          text=True, timeout=30)


class RecoverCliTests(unittest.TestCase):
    def test_dead_owner_recovers_unchanged_and_partial_without_rewriting_worktree(self):
        for partial in (False, True):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                child, owner = _process()
                target = worktree / "scripts/sdd_tasks/allowed.txt"
                if partial:
                    target.write_text("partial\n", encoding="utf-8")
                try:
                    with closing(connect(db)) as conn:
                        run_id = _seed(conn, task, before, owner)
                    child.terminate()
                    child.wait(timeout=10)
                    output = _cli(root, run_id)
                    body = json.loads(output.stdout)
                    action = "preserved_for_recovery" if partial else "requeued"
                    decision = "partial" if partial else "unchanged"
                    self.assertEqual((output.returncode, body["ok"], body["code"]), (0, True, "OK"))
                    self.assertEqual(body["data"], {"run_id": run_id, "state": "abandoned", "action": action})
                    self.assertNotIn(str(root), output.stdout)
                    self.assertNotIn(owner.token, output.stdout)
                    with closing(connect(db)) as conn:
                        run = conn.execute("SELECT state,ended_at,error_code FROM runs WHERE run_id=?",
                                           (run_id,)).fetchone()
                        lease_count = conn.execute("SELECT count(*) FROM leases WHERE run_id=?",
                                                   (run_id,)).fetchone()[0]
                        event = conn.execute("SELECT event_type,payload_json FROM events WHERE run_id=? "
                                             "ORDER BY sequence DESC LIMIT 1", (run_id,)).fetchone()
                    self.assertEqual((run[0], bool(run[1]), run[2]),
                                     ("abandoned", True, "OWNER_DEAD_LEASE_EXPIRED"))
                    self.assertEqual(lease_count, 0)
                    self.assertEqual(event[0], "recovery_decision")
                    self.assertEqual(json.loads(event[1]), {"schema": "sdd-run-recovery/v1",
                                     "action": action, "decision": decision})
                    self.assertEqual(target.read_text(encoding="utf-8"), "partial\n" if partial else "baseline\n")
                finally:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=10)

    def test_owner_and_workspace_refusals_preserve_rows_and_files(self):
        for case in ("live", "remote", "malformed", "outside"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db = _fixture(temp)
                child, owner = _process()
                watch = worktree / "scripts/sdd_tasks/allowed.txt"
                try:
                    with closing(connect(db)) as conn:
                        run_id = _seed(conn, task, before, owner)
                        if case == "remote":
                            row = conn.execute("SELECT owner_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
                            identity = json.loads(row[0])
                            identity["host_id"] = "different-host"
                            conn.execute("UPDATE runs SET owner_json=? WHERE run_id=?",
                                         (json.dumps(identity, sort_keys=True, separators=(",", ":")), run_id))
                        elif case == "malformed":
                            conn.execute("UPDATE events SET payload_json='NaN' WHERE run_id=?", (run_id,))
                        elif case == "outside":
                            watch = worktree / "outside.txt"
                            watch.write_text("preserve\n", encoding="utf-8")
                    if case != "live":
                        child.terminate()
                        child.wait(timeout=10)
                    rows, contents = _rows(db), watch.read_bytes()
                    output = _cli(root, run_id)
                    body = json.loads(output.stdout)
                    self.assertNotEqual(output.returncode, 0)
                    self.assertFalse(body["ok"])
                    self.assertIsNone(body["data"])
                    self.assertEqual(_rows(db), rows)
                    self.assertEqual(watch.read_bytes(), contents)
                finally:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
