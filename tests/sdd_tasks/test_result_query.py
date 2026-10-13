import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.result_query import ResultQueryError, result_for_run
from scripts.sdd_tasks.run_docs import write_summary
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.summaries import scan_summaries
from tests.sdd_tasks.test_run_docs import _result
from tests.sdd_tasks.test_run_owner import _claimed, _rows

_FIELDS = (
    "state", "ide", "executor_id", "agent_role", "model", "worktree", "branch",
    "base_commit", "task_hash", "prompt_hash", "claimed_at", "started_at", "ended_at",
    "duration_ms", "result_doc",
)


def _finish(root, canonical, task, database, claim):
    result = _result(task, claim)
    relative = Path("docs/sdd/runs/{}/task-{}/{}.md".format(
        task.metadata["spec_id"], task.metadata["task_id"][-2:], claim.run_id))
    (canonical / relative).parent.mkdir(parents=True)
    write_summary(task, claim, result, root)
    record = scan_summaries((canonical,), (task,))[0]
    assignments = ",".join(field + "=?" for field in _FIELDS)
    with closing(connect(database)) as conn:
        conn.execute("UPDATE runs SET " + assignments + " WHERE run_id=?",
                     tuple(record[field] for field in _FIELDS) + (claim.run_id,))
    return result, canonical / relative


def _files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and
            not {".git", ".sdd"}.intersection(path.relative_to(root).parts)}


class ResultQueryTests(unittest.TestCase):
    def test_terminal_result_is_read_only_and_matches_canonical_summary(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            expected, summary = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                before = _rows(conn)
                files = _files(canonical)
                self.assertEqual(result_for_run(conn, claim.run_id), expected)
                self.assertEqual(_rows(conn), before)
            self.assertEqual(_files(canonical), files)
            self.assertTrue(summary.is_file())

    def test_invalid_missing_and_active_runs_refuse_without_creating_summaries(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, canonical, _, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                files = _files(canonical)
                for run_id in ("invalid", "123e4567-e89b-12d3-a456-426614174999", claim.run_id):
                    with self.subTest(run_id=run_id), self.assertRaises(ResultQueryError):
                        result_for_run(conn, run_id)
                    self.assertEqual(_rows(conn), before)
                    self.assertEqual(_files(canonical), files)
            self.assertFalse((canonical / "docs/sdd/runs").exists())

    def test_ledger_binding_and_missing_summary_refuse_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            expected, summary = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                conn.execute("UPDATE runs SET model='different-model' WHERE run_id=?",
                             (claim.run_id,))
                before = _rows(conn)
                files = _files(canonical)
                with self.assertRaises(ResultQueryError):
                    result_for_run(conn, claim.run_id)
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)
                conn.execute("UPDATE runs SET model=? WHERE run_id=?",
                             (expected["model"], claim.run_id))
                summary.unlink()
                summary.parent.rmdir()
                summary.parent.parent.rmdir()
                summary.parent.parent.parent.rmdir()
                before = _rows(conn)
                files = _files(canonical)
                with self.assertRaises(ResultQueryError):
                    result_for_run(conn, claim.run_id)
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)
            self.assertFalse((canonical / "docs/sdd/runs").exists())


if __name__ == "__main__":
    unittest.main()
