import json
import os
import subprocess
import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.lifecycle_context import load_active_claim
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.run_owner import resolve_run_owner
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_cli_completion import _finish_args, _invoke
from tests.sdd_tasks.test_completion_prepare import SOURCE
from tests.sdd_tasks.test_completion_service import _changed_source, _draft
from tests.sdd_tasks.test_failure_history import _failed_run
from tests.sdd_tasks.test_run_owner import _rows


def _next(root):
    return _invoke(root, "next", "--claim", "--ide", "codex", "--executor", "retry",
                   "--owner-pid", str(os.getpid()))


def _active(root, database, payload):
    with closing(connect(database)) as conn, maintenance_lock(root):
        owner = resolve_run_owner(conn, payload["run_id"], "retry", os.getpid())
        return load_active_claim(conn, payload["run_id"], owner, root)[:2]


def _assert_source(test, database, payload, source_id, original_base):
    test.assertEqual((payload["base_commit"], payload["recovery_of"]), (original_base, source_id))
    with closing(connect(database)) as conn:
        event = {row[0]: json.loads(row[1]) for row in conn.execute(
            "SELECT event_type,payload_json FROM events WHERE run_id=? "
            "AND event_type IN ('workspace_snapshot','recovery_claim')", (payload["run_id"],))}
    test.assertEqual((event["workspace_snapshot"]["source_run_id"],
                      event["workspace_snapshot"]["snapshot"]["head"],
                      event["recovery_claim"]["recovery_of"]),
                     (source_id, original_base, source_id))


def _finish(root, worktree, task, claim, outcome, contents):
    (worktree / SOURCE).write_text(contents, encoding="utf-8")
    relative = ".sdd/runtime/runs/{}/result-draft.json".format(claim.run_id)
    result = _draft(task, claim, outcome=outcome,
                    changed_files=[_changed_source(worktree)])
    (root / relative).write_text(json.dumps(result), encoding="utf-8")
    command = "complete" if outcome == "succeeded" else "fail"
    return _invoke(root, command, *_finish_args(claim, relative))


class FailedLifecycleTests(unittest.TestCase):
    def test_failed_child_completes_and_old_failure_replay_preserves_new_run(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, failed, _, original_base = data[:7]
            code, body = _next(root)
            self.assertEqual((code, body["code"]), (0, "OK"))
            payload = body["data"]
            _assert_source(self, database, payload, failed.run_id, original_base)
            live, claim = _active(root, database, payload)
            self.assertEqual(claim.failed_source.source_run_id, failed.run_id)
            contents = "completed recovered source\n"
            code, completed = _finish(root, worktree, live, claim, "succeeded", contents)
            self.assertEqual((code, completed["ok"], completed["code"]), (0, True, "OK"))
            self.assertEqual(completed["data"]["outcome"], "succeeded")
            self.assertEqual((worktree / SOURCE).read_bytes(), contents.encode())
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(worktree), "show", "HEAD:" + SOURCE]), contents.encode())
            with closing(connect(database)) as conn:
                before = _rows(conn)
                self.assertEqual(conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                              (task.metadata["task_id"],)).fetchone()[0], "completed")
            replay = _invoke(root, "fail", *_finish_args(failed, "missing-result.json"))
            self.assertEqual((replay[0], replay[1]["ok"], replay[1]["code"]),
                             (0, True, "OK"))
            self.assertEqual(replay[1]["data"]["outcome"], "failed")
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), before)

    def test_three_failed_attempts_keep_immediate_source_and_block_task(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, failed, source, original_base = data[:7]
            baseline_bytes = subprocess.check_output(
                ["git", "-C", str(worktree), "show", original_base + ":" + SOURCE])
            source_id = failed.run_id
            for attempt, contents in ((2, "retry two source\n"), (3, "retry three source\n")):
                code, body = _next(root)
                self.assertEqual((code, body["ok"], body["code"]), (0, True, "OK"))
                payload = body["data"]
                self.assertEqual(payload["attempt"], attempt)
                _assert_source(self, database, payload, source_id, original_base)
                live, claim = _active(root, database, payload)
                self.assertEqual(claim.failed_source.source_run_id, source_id)
                code, result = _finish(root, worktree, live, claim, "failed", contents)
                self.assertEqual((code, result["ok"], result["code"]), (0, True, "OK"))
                self.assertEqual(result["data"]["outcome"], "failed")
                source_id = payload["run_id"]

            code, blocked = _next(root)
            self.assertEqual((code, blocked["code"]), (0, "NO_TASK"))
            self.assertEqual((worktree / SOURCE).read_text(encoding="utf-8"), "retry three source\n")
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(worktree), "show", "HEAD:" + SOURCE]), baseline_bytes)
            staged = subprocess.check_output(
                ["git", "-C", str(worktree), "diff", "--cached", "--name-only", "--", SOURCE],
                text=True)
            self.assertEqual(staged, "")
            with closing(connect(database)) as conn:
                runs = [tuple(row) for row in conn.execute(
                    "SELECT attempt,state FROM runs WHERE task_id=? ORDER BY attempt",
                    (task.metadata["task_id"],))]
                status = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                      (task.metadata["task_id"],)).fetchone()[0]
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)
            self.assertEqual((runs, status), ([(1, "failed"), (2, "failed"), (3, "failed")], "blocked"))


if __name__ == "__main__":
    unittest.main()
