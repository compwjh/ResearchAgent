import json
import shlex
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from scripts.sdd_tasks.completion_service import CompletionServiceError, complete_run
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_prepare import COMMAND, _claimed_with_command
from tests.sdd_tasks.test_result_schema import valid_result
from tests.sdd_tasks.test_run_owner import _rows


def _draft(task, claim, model="draft model"):
    result = valid_result()
    result.update(
        run_id=claim.run_id, task_id=task.metadata["task_id"],
        task_hash=task.task_hash, prompt_hash=task.prompt_hash, outcome="succeeded",
        model=model, changed_files=[], artifacts=[], tests=[], decisions=[], risks=[],
        blockers=[], main_agent_actions=[], log_paths=[],
        started_at="2000-01-01T00:00:00Z", ended_at="2000-01-01T00:00:01Z",
        duration_ms=999999,
        commands=[{"argv": ["actor-command"], "status": "executed", "exit_code": 91,
                   "duration_ms": 876543, "summary": "actor command claim"}],
    )
    return result


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


if __name__ == "__main__":
    unittest.main()
