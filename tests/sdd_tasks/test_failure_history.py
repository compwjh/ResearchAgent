import json
import subprocess
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path

from scripts.sdd_tasks.completion_journal import read_journal
from scripts.sdd_tasks.completion_service import fail_run
from scripts.sdd_tasks.failure_history import FailureHistoryError, verify_failed_run_history
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.result_query import result_for_run
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_completion_service import _changed_source, _draft
from tests.sdd_tasks.test_run_owner import _rows


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _repo_state(worktree):
    index = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    objects = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "objects"))
    refs = _git(worktree, "for-each-ref", "--format=%(refname) %(objectname)")
    object_files = tuple(sorted(path.relative_to(objects).as_posix()
                                for path in objects.rglob("*") if path.is_file()))
    return _git(worktree, "rev-parse", "HEAD"), refs, index.read_bytes(), object_files


@contextmanager
def _failed_run(directory):
    with _claimed_with_command(directory) as state:
        root, worktree, task, database, _, _, claim = state
        source = worktree / SOURCE
        source.write_text("partial source change\n", encoding="utf-8")
        changed = _changed_source(worktree)
        parent_tip = _git(worktree, "rev-parse", "HEAD")
        run_dir = root / ".sdd/runtime/runs" / claim.run_id
        with closing(connect(database)) as conn, maintenance_lock(root):
            result = fail_run(conn, root, claim.run_id, claim.owner.executor_id, claim.owner.pid,
                              json.dumps(_draft(task, claim, outcome="failed",
                                                changed_files=[changed])))
            if result_for_run(conn, claim.run_id) != result:
                raise AssertionError("failed public result was not persisted")
        yield root, worktree, task, database, claim, source, parent_tip, result, run_dir


def _assert_proof_readonly(test, conn, root, worktree, claim, task, reject=False):
    rows, state = _rows(conn), _repo_state(worktree)
    if reject:
        with test.assertRaises(FailureHistoryError):
            verify_failed_run_history(conn, claim.run_id, task, root)
        proof = None
    else:
        proof = verify_failed_run_history(conn, claim.run_id, task, root)
    test.assertEqual(_rows(conn), rows)
    test.assertEqual(_repo_state(worktree), state)
    return proof, state


class FailureHistoryTests(unittest.TestCase):
    def test_failed_history_proves_docs_only_commit_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim, source, parent_tip, result, run_dir = data
            journal = read_journal(run_dir / "completion.json")
            self.assertEqual((result["outcome"], journal["phase"],
                              journal["terminal_outcome"]), ("failed", "complete", "failed"))
            self.assertEqual([item["path"] for item in result["changed_files"]], [SOURCE])
            self.assertNotIn(SOURCE, journal["committed_paths"])
            summary = "docs/sdd/runs/{}/task-{}/{}.md".format(
                task.metadata["spec_id"], task.metadata["task_id"][-2:], claim.run_id)
            self.assertEqual(source.read_text(encoding="utf-8"), "partial source change\n")
            self.assertEqual(_git(worktree, "show", "HEAD:" + SOURCE), "baseline")
            self.assertEqual(_git(worktree, "diff", "--name-only", "--", SOURCE), SOURCE)
            self.assertEqual(_git(worktree, "diff", "--cached", "--name-only", "--", SOURCE), "")
            with closing(connect(database)) as conn:
                rows, git_state = _rows(conn), _repo_state(worktree)
                proof = verify_failed_run_history(conn, claim.run_id, task, root)
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_state)
            self.assertEqual(proof.observation_tips, ((claim.run_id, parent_tip),))
            self.assertEqual(proof.excluded_paths, (summary,))
            self.assertEqual(proof.current_tip, git_state[0])

    def test_source_commit_is_rejected_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim = data[:5]
            _git(worktree, "add", SOURCE)
            _git(worktree, "commit", "-m", "unauthorized source commit")
            with closing(connect(database)) as conn:
                _assert_proof_readonly(self, conn, root, worktree, claim, task, reject=True)

    def test_tampered_private_expected_git_is_rejected_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim = data[:5]
            journal_path = data[-1] / "completion.json"
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            journal["expected_git_entries"][0]["object_id"] = "0" * 40
            journal_path.write_text(json.dumps(journal), encoding="utf-8")
            tampered = journal_path.read_bytes()
            with closing(connect(database)) as conn:
                _assert_proof_readonly(self, conn, root, worktree, claim, task, reject=True)
            self.assertEqual(journal_path.read_bytes(), tampered)

    def test_staged_source_is_preserved_by_read_only_proof(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim = data[:5]
            _git(worktree, "add", SOURCE)
            self.assertEqual(_git(worktree, "diff", "--cached", "--name-only", "--", SOURCE), SOURCE)
            with closing(connect(database)) as conn:
                proof, state = _assert_proof_readonly(self, conn, root, worktree, claim, task)
            self.assertEqual(proof.observation_tips, ((claim.run_id, data[6]),))
            self.assertEqual(proof.excluded_paths, ("docs/sdd/runs/016/task-04/{}.md".format(
                claim.run_id),))
            self.assertEqual(proof.current_tip, state[0])

    def test_tampered_summary_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim, _, _, _, _ = data
            summary = worktree / "docs/sdd/runs/016/task-04/{}.md".format(claim.run_id)
            summary.write_text("forged summary\n", encoding="utf-8")
            with closing(connect(database)) as conn:
                rows, git_state = _rows(conn), _repo_state(worktree)
                with self.assertRaises(FailureHistoryError):
                    verify_failed_run_history(conn, claim.run_id, task, root)
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_state)
