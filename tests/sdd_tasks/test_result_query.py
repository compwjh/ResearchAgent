import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.result_query import ResultQueryError, result_for_run
from scripts.sdd_tasks.run_docs import write_summary
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.summaries import _RB, _RE, scan_summaries
from tests.sdd_tasks._fixtures import task_markdown
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


def _complete_task(root, canonical, database, task):
    metadata = dict(task.metadata, status="completed")
    path = canonical / task.path.relative_to(root)
    path.write_text("# {}\n> 当前状态：`完成`\n\n".format(metadata["title"]) +
                    task_markdown(metadata, prompt=task.prompt[:-1]), encoding="utf-8")
    encoded = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    with closing(connect(database)) as conn:
        conn.execute("UPDATE tasks SET status='completed',definition_json=? WHERE task_id=?",
                     (encoded, task.metadata["task_id"]))
    return path


def _replace_result_block(summary, content):
    document = summary.read_text(encoding="utf-8")
    begin = document.index(_RB) + len(_RB)
    end = document.index(_RE, begin)
    summary.write_text(document[:begin] + "\n" + content + "\n" + document[end:],
                       encoding="utf-8")


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

    def test_completed_task_status_keeps_definition_hash_binding_valid(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            expected, _ = _finish(root, canonical, task, database, claim)
            path = _complete_task(root, canonical, database, task)
            live = parse_task(path)
            self.assertEqual(live.metadata["status"], "completed")
            self.assertEqual(live.task_hash, task.task_hash)
            with closing(connect(database)) as conn:
                before, files = _rows(conn), _files(canonical)
                self.assertEqual(result_for_run(conn, claim.run_id), expected)
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)

    def test_malformed_duplicate_private_and_symlink_summaries_refuse_read_only(self):
        cases = ("malformed", "duplicate_json", "private_value", "symlink_parent")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, canonical, task, database, _, _, claim = state
                expected, summary = _finish(root, canonical, task, database, claim)
                outside = Path(temp) / "outside"
                with closing(connect(database)) as conn:
                    self.assertEqual(result_for_run(conn, claim.run_id), expected)
                if case == "malformed":
                    summary.write_text("partial summary\n", encoding="utf-8")
                elif case == "duplicate_json":
                    content = json.dumps(expected, sort_keys=True, ensure_ascii=False, indent=2)
                    content = content.replace('"schema": "sdd-run-result/v1",',
                                              '"schema": "sdd-run-result/v1",\n'
                                              '  "schema": "sdd-run-result/v1",', 1)
                    _replace_result_block(summary, content)
                elif case == "private_value":
                    unsafe = json.loads(json.dumps(expected))
                    unsafe["summary"] = "API_SECRET=private"
                    _replace_result_block(summary, json.dumps(
                        unsafe, sort_keys=True, ensure_ascii=False, indent=2))
                else:
                    summary.unlink()
                    summary.parent.rmdir()
                    outside.mkdir()
                    summary.parent.symlink_to(outside, target_is_directory=True)
                with closing(connect(database)) as conn:
                    before, files = _rows(conn), _files(canonical)
                    with self.assertRaises(ResultQueryError):
                        result_for_run(conn, claim.run_id)
                    self.assertEqual(_rows(conn), before)
                    self.assertEqual(_files(canonical), files)
                if case == "symlink_parent":
                    self.assertTrue(summary.parent.is_symlink())
                    self.assertEqual(tuple(outside.iterdir()), ())


if __name__ == "__main__":
    unittest.main()
