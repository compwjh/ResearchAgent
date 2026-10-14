import hashlib
import json
import shlex
import subprocess
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from scripts.sdd_tasks.completion_journal import read_journal
from scripts.sdd_tasks.completion_service import CompletionServiceError, complete_run, fail_run
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.result_query import result_for_run
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_prepare import COMMAND, SOURCE, _claimed_with_command
from tests.sdd_tasks.test_result_schema import valid_result
from tests.sdd_tasks.test_run_owner import _rows


def _draft(task, claim, model="draft model", outcome="succeeded", changed_files=None):
    result = valid_result()
    result.update(
        run_id=claim.run_id, task_id=task.metadata["task_id"],
        task_hash=task.task_hash, prompt_hash=task.prompt_hash, outcome=outcome,
        model=model, changed_files=changed_files or [], artifacts=[], tests=[], decisions=[], risks=[],
        blockers=[], main_agent_actions=[], log_paths=[],
        started_at="2000-01-01T00:00:00Z", ended_at="2000-01-01T00:00:01Z",
        duration_ms=999999,
        commands=[{"argv": ["actor-command"], "status": "executed", "exit_code": 91,
                   "duration_ms": 876543, "summary": "actor command claim"}],
    )
    return result


def _changed_source(worktree):
    output = subprocess.run(["git", "-C", str(worktree), "diff", "--numstat", "--", SOURCE],
                            check=True, capture_output=True, text=True).stdout.strip()
    additions, deletions, path = output.split("\t")
    digest = (hashlib.sha256((worktree / SOURCE).read_bytes()).hexdigest()
              if (worktree / SOURCE).is_file() else None)
    return {"path": path, "change": "deleted" if digest is None else "modified",
            "additions": int(additions), "deletions": int(deletions), "sha256": digest}


class CompletionServiceTests(unittest.TestCase):
    def test_success_reruns_declared_command_and_binds_server_metadata(self):
        for database_model in (None, "database model"):
            with self.subTest(database_model=database_model), tempfile.TemporaryDirectory() as temp, \
                    _claimed_with_command(temp) as state:
                root, _, task, database, _, _, claim = state
                run_dir = root / ".sdd/runtime/runs" / claim.run_id
                with closing(connect(database)) as conn, maintenance_lock(root):
                    conn.execute("UPDATE runs SET model=? WHERE run_id=?",
                                 (database_model, claim.run_id))
                    self.assertFalse(run_dir.exists())
                    result = complete_run(conn, root, claim.run_id,
                                          claim.owner.executor_id, claim.owner.pid,
                                          json.dumps(_draft(task, claim)))
                    stored = conn.execute(
                        "SELECT state,started_at,ended_at FROM runs WHERE run_id=?",
                        (claim.run_id,),
                    ).fetchone()
                    events = [row[0] for row in conn.execute(
                        "SELECT payload_json FROM events WHERE run_id=?", (claim.run_id,))]
                    observations = [row[0] for row in conn.execute(
                        "SELECT timestamp FROM events WHERE run_id=? AND event_type='workspace_observation'",
                        (claim.run_id,))]
                    status = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                          (task.metadata["task_id"],)).fetchone()[0]
                self.assertEqual(result["outcome"], "succeeded")
                self.assertEqual(result["model"], database_model or "draft model")
                self.assertEqual(result["started_at"], claim.claimed_at)
                self.assertNotEqual(result["ended_at"], "2000-01-01T00:00:01Z")
                self.assertNotEqual(result["duration_ms"], 999999)
                self.assertEqual(result["commands"][0]["argv"], shlex.split(COMMAND))
                self.assertEqual((result["commands"][0]["status"],
                                  result["commands"][0]["exit_code"]), ("executed", 0))
                self.assertNotIn("actor-command", json.dumps(result) + "".join(events))
                self.assertEqual(len(observations), 1)
                self.assertLessEqual(observations[0], result["ended_at"])
                self.assertEqual((stored["state"], status), ("succeeded", "completed"))
                self.assertIsNotNone(stored["ended_at"])

    def test_invalid_raw_json_or_sensitive_content_fails_before_side_effects(self):
        for case in ("malformed", "sensitive", "duplicate", "nan"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, \
                    _claimed_with_command(temp) as state:
                root, _, task, database, _, _, claim = state
                draft = json.dumps(_draft(task, claim))
                raw = {
                    "malformed": "{bad json",
                    "sensitive": json.dumps(dict(_draft(task, claim),
                                                  summary="Authorization: Bearer example")),
                    "duplicate": draft.replace('"schema": "sdd-run-result/v1"',
                                                '"schema": "sdd-run-result/v1", "schema": "sdd-run-result/v1"'),
                    "nan": draft.replace('"duration_ms": 999999', '"duration_ms": NaN'),
                }[case]
                run_dir = root / ".sdd/runtime/runs" / claim.run_id
                with closing(connect(database)) as conn, maintenance_lock(root):
                    before = _rows(conn)
                    with patch("scripts.sdd_tasks.completion_service.run_validations") as run, \
                            patch("scripts.sdd_tasks.completion_service.record_workspace_observation") as observation:
                        with self.assertRaises(CompletionServiceError) as caught:
                            complete_run(conn, root, claim.run_id, claim.owner.executor_id,
                                         claim.owner.pid, raw)
                        self.assertEqual(caught.exception.code, "COMPLETION_RESULT_INVALID")
                        run.assert_not_called()
                        observation.assert_not_called()
                    self.assertEqual(_rows(conn), before)
                    self.assertFalse(run_dir.exists())

    def test_failed_validation_can_be_published_after_complete_refusal(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, _, _, claim = state
            source = worktree / SOURCE
            source.unlink()
            changed = _changed_source(worktree)
            run_dir = root / ".sdd/runtime/runs" / claim.run_id
            with closing(connect(database)) as conn, maintenance_lock(root):
                before = _rows(conn)
                with self.assertRaises(CompletionServiceError) as caught:
                    complete_run(conn, root, claim.run_id, claim.owner.executor_id,
                                 claim.owner.pid, json.dumps(_draft(task, claim)))
                self.assertEqual(caught.exception.code, "COMPLETION_VALIDATION_FAILED")
                self.assertEqual(_rows(conn), before)
                self.assertFalse((run_dir / "completion.json").exists())
                receipt_path = run_dir / "validation" / "receipt.json"
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertFalse(receipt["valid"])
                self.assertEqual(receipt["commands"][0]["status"], "executed")
                self.assertNotEqual(receipt["commands"][0]["exit_code"], 0)
                result = fail_run(conn, root, claim.run_id, claim.owner.executor_id,
                                  claim.owner.pid, json.dumps(_draft(task, claim, outcome="failed",
                                                                    changed_files=[changed])))
                self.assertEqual(result_for_run(conn, claim.run_id), result)
                run = conn.execute("SELECT state FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()
                lease_count = conn.execute("SELECT count(*) FROM leases WHERE run_id=?",
                                           (claim.run_id,)).fetchone()[0]
                observations = conn.execute(
                    "SELECT count(*) FROM events WHERE run_id=? AND event_type='workspace_observation'",
                    (claim.run_id,),
                ).fetchone()[0]
            journal = read_journal(run_dir / "completion.json")
            head_source = subprocess.run(["git", "-C", str(worktree), "show", "HEAD:" + SOURCE],
                                         check=True, capture_output=True).stdout
            self.assertEqual(result["changed_files"], [changed])
            self.assertEqual((changed["change"], changed["sha256"], changed["additions"]),
                             ("deleted", None, 0))
            self.assertEqual((run["state"], lease_count, observations), ("failed", 0, 1))
            self.assertFalse(source.exists())
            self.assertEqual(head_source, b"baseline\n")
            self.assertEqual(len(journal["committed_paths"]), 1)
            self.assertTrue(journal["committed_paths"][0].startswith("docs/sdd/runs/"))
            self.assertNotIn(SOURCE, journal["committed_paths"])

    def test_failed_outcome_keeps_successfully_validated_source_unstaged(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, _, _, claim = state
            source = worktree / SOURCE
            source.write_text("partial source change\n", encoding="utf-8")
            changed = _changed_source(worktree)
            run_dir = root / ".sdd/runtime/runs" / claim.run_id
            with closing(connect(database)) as conn, maintenance_lock(root):
                result = fail_run(conn, root, claim.run_id, claim.owner.executor_id,
                                  claim.owner.pid, json.dumps(_draft(task, claim, outcome="failed",
                                                                    changed_files=[changed])))
                receipt = json.loads((run_dir / "validation" / "receipt.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(result_for_run(conn, claim.run_id), result)
            journal = read_journal(run_dir / "completion.json")
            head_source = subprocess.run(["git", "-C", str(worktree), "show", "HEAD:" + SOURCE],
                                         check=True, capture_output=True).stdout
            staged = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--name-only",
                                     "--", SOURCE], check=True, capture_output=True, text=True).stdout
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(result["changed_files"], [changed])
            self.assertTrue(receipt["valid"])
            self.assertEqual((receipt["commands"][0]["status"],
                              receipt["commands"][0]["exit_code"]), ("executed", 0))
            self.assertEqual(source.read_text(encoding="utf-8"), "partial source change\n")
            self.assertEqual(head_source, b"baseline\n")
            self.assertEqual(staged, "")
            self.assertEqual(len(journal["committed_paths"]), 1)
            self.assertNotIn(SOURCE, journal["committed_paths"])

    def test_existing_journal_replay_ignores_raw_input_and_does_not_validate_again(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, _, task, database, _, _, claim = state
            raw = json.dumps(_draft(task, claim))
            with closing(connect(database)) as conn, maintenance_lock(root):
                original = complete_run(conn, root, claim.run_id, claim.owner.executor_id,
                                        claim.owner.pid, raw)
                run_dir = root / ".sdd/runtime/runs" / claim.run_id
                journal = run_dir / "completion.json"
                journal_bytes, rows = journal.read_bytes(), _rows(conn)
                with patch("scripts.sdd_tasks.completion_service.run_validations") as validate, \
                        patch("scripts.sdd_tasks.completion_service.record_workspace_observation") as observe:
                    replay = complete_run(conn, root, claim.run_id, claim.owner.executor_id,
                                          claim.owner.pid, "malformed ignored replay input")
                    validate.assert_not_called()
                    observe.assert_not_called()
                self.assertEqual(replay, original)
                self.assertEqual(result_for_run(conn, claim.run_id), original)
                self.assertEqual(_rows(conn), rows)
                self.assertEqual(journal.read_bytes(), journal_bytes)

    def test_wrong_principal_refuses_before_raw_parsing_or_side_effects(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, _, _, database, _, _, claim = state
            run_dir = root / ".sdd/runtime/runs" / claim.run_id
            with closing(connect(database)) as conn, maintenance_lock(root):
                before = _rows(conn)
                with patch("scripts.sdd_tasks.completion_service.run_validations") as validate, \
                        patch("scripts.sdd_tasks.completion_service.record_workspace_observation") as observe:
                    with self.assertRaises(CompletionServiceError) as caught:
                        complete_run(conn, root, claim.run_id, "wrong-principal",
                                     claim.owner.pid, "malformed ignored unauthorized input")
                    self.assertEqual(caught.exception.code, "COMPLETION_OWNER_MISMATCH")
                    validate.assert_not_called()
                    observe.assert_not_called()
                self.assertEqual(_rows(conn), before)
                self.assertFalse(run_dir.exists())


if __name__ == "__main__":
    unittest.main()
