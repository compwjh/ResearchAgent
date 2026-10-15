import hashlib
import json
import os
import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.completion_service import fail_run
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_cli_completion import _invoke
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_completion_service import _draft
from tests.sdd_tasks.test_failure_history import _failed_run, _git
from tests.sdd_tasks.test_run_owner import _rows


def _next(root, base_commit=None):
    args = ["next", "--claim", "--ide", "codex", "--executor", "retry",
            "--owner-pid", str(os.getpid())]
    if base_commit is not None:
        args += ["--base-commit", base_commit]
    return _invoke(root, *args)


def _assert_prompt(test, root, task, data):
    expected_path = ".sdd/runtime/runs/{}/prompt.md".format(data["run_id"])
    test.assertEqual(data["prompt_path"], expected_path)
    rendered = (root / expected_path).read_bytes()
    test.assertEqual(hashlib.sha256(rendered).hexdigest(), data["rendered_prompt_hash"])
    values = {"RUN_ID": data["run_id"], "WORKTREE": data["worktree"],
              "BASE_COMMIT": data["base_commit"],
              "RESULT_PATH": ".sdd/runtime/runs/{}/result.json".format(data["run_id"]),
              "EVENT_PATH": ".sdd/runtime/runs/{}/events.jsonl".format(data["run_id"])}
    expected = task.prompt
    for name, value in values.items():
        expected = expected.replace("{{" + name + "}}", value)
    test.assertEqual(rendered.decode("utf-8"), expected)


class FailedCliTests(unittest.TestCase):
    def test_partial_failure_claim_uses_original_base_and_persists_prompt(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, failed, source, original_base = data[:7]
            source_bytes = source.read_bytes()
            wrong_base = "0" * 40 if original_base != "0" * 40 else "f" * 40
            with closing(connect(database)) as conn:
                rows = _rows(conn)
            code, rejected = _next(root, wrong_base)
            self.assertEqual((code, rejected["ok"], rejected["code"]),
                             (3, False, "CLAIM_BASE_COMMIT_INVALID"))
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(source.read_bytes(), source_bytes)

            code, body = _next(root)
            self.assertEqual((code, body["ok"], body["code"], body["data"]["attempt"]),
                             (0, True, "OK", 2))
            claim = body["data"]
            self.assertEqual((claim["base_commit"], claim["recovery_of"]),
                             (original_base, failed.run_id))
            _assert_prompt(self, root, task, claim)
            with closing(connect(database)) as conn:
                run = conn.execute("SELECT base_commit FROM runs WHERE run_id=?",
                                   (claim["run_id"],)).fetchone()
                event = json.loads(conn.execute(
                    "SELECT payload_json FROM events WHERE run_id=? AND event_type='workspace_snapshot'",
                    (claim["run_id"],),
                ).fetchone()[0])
            self.assertEqual((run[0], event["source_run_id"], event["snapshot"]["head"]),
                             (original_base, failed.run_id, original_base))
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertNotEqual(_git(worktree, "rev-parse", "HEAD"), original_base)

    def test_failure_without_source_change_claims_fresh_document_tip(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, _, _, failed = state
            source = worktree / SOURCE
            source_bytes = source.read_bytes()
            with closing(connect(database)) as conn, maintenance_lock(root):
                fail_run(conn, root, failed.run_id, failed.owner.executor_id, failed.owner.pid,
                         json.dumps(_draft(task, failed, outcome="failed", changed_files=[])))
            document_tip = _git(worktree, "rev-parse", "HEAD")
            code, body = _next(root)
            self.assertEqual((code, body["ok"], body["code"]), (0, True, "OK"))
            claim = body["data"]
            self.assertEqual((claim["base_commit"], claim["recovery_of"]), (document_tip, None))
            _assert_prompt(self, root, task, claim)
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
