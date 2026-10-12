import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.workspace import WorkspaceError, capture_snapshot, prepare_worktree
from tests.sdd_tasks._fixtures import TASK_PATH, task_markdown


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def _fixture(directory):
    root = Path(directory) / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    (root / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
    (root / TASK_PATH).parent.mkdir(parents=True)
    (root / TASK_PATH).write_text(task_markdown(), encoding="utf-8")
    for folder in ("scripts/sdd_tasks", "tests/sdd_tasks"):
        (root / folder).mkdir(parents=True)
        (root / folder / "seed.txt").write_text("seed\n", encoding="utf-8")
    outside = root / "outside.txt"
    outside.write_text("baseline\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "worktree fixture")
    base = _git(root, "rev-parse", "HEAD")
    return root, parse_task(root / TASK_PATH), base, outside


def _add(root, task, base, branch=None):
    path = root / task.metadata["worktree"]["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-qb", branch or task.metadata["worktree"]["branch"], str(path), base)
    return path


def _index(root):
    value = Path(_git(root, "rev-parse", "--git-path", "index"))
    return value if value.is_absolute() else (root / value).resolve()


class PrepareWorktreeTests(unittest.TestCase):
    def test_fresh_create_and_pristine_reuse_preserve_dirty_main(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, outside = _fixture(temp)
            outside.write_text("main dirty\n", encoding="utf-8")
            main_index = _index(root).read_bytes()
            first = prepare_worktree(root, task, base)
            second = prepare_worktree(root, task, base)
            self.assertEqual(first.worktree_path, root / ".worktrees/spec-016")
            self.assertEqual((first.branch, first.head, first.status_records),
                             (task.metadata["worktree"]["branch"], base, ()))
            self.assertEqual(second.worktree_path, first.worktree_path)
            self.assertEqual(second.head, base)
            self.assertEqual(_index(root).read_bytes(), main_index)
            self.assertEqual(outside.read_text(encoding="utf-8"), "main dirty\n")

    def test_existing_wrong_branch_or_head_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, _ = _fixture(temp)
            path = _add(root, task, base, "feature/spec-016-wrong")
            with self.assertRaises(WorkspaceError) as error:
                prepare_worktree(root, task, base)
            self.assertEqual(error.exception.code, "workspace_branch_mismatch")
            self.assertTrue(path.exists())
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, _ = _fixture(temp)
            (root / "later.txt").write_text("later\n", encoding="utf-8")
            _git(root, "add", "later.txt")
            _git(root, "commit", "-qm", "later base")
            path = _add(root, task, _git(root, "rev-parse", "HEAD"))
            with self.assertRaises(WorkspaceError) as error:
                prepare_worktree(root, task, base)
            self.assertEqual(error.exception.code, "workspace_base_commit_mismatch")
            self.assertTrue(path.exists())

    def test_fresh_dirty_worktree_is_refused_without_file_or_index_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, outside = _fixture(temp)
            outside.write_text("main dirty\n", encoding="utf-8")
            path = _add(root, task, base)
            file = path / "tests/sdd_tasks/seed.txt"
            file.write_text("keep dirty\n", encoding="utf-8")
            extra = path / "tests/sdd_tasks/untracked.txt"
            extra.write_text("keep untracked\n", encoding="utf-8")
            index = _index(path).read_bytes()
            with self.assertRaises(WorkspaceError) as error:
                prepare_worktree(root, task, base)
            self.assertEqual(error.exception.code, "workspace_worktree_dirty")
            self.assertEqual(file.read_text(encoding="utf-8"), "keep dirty\n")
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep untracked\n")
            self.assertEqual(_index(path).read_bytes(), index)

    def test_recovery_accepts_allowed_partial_without_replacing_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, outside = _fixture(temp)
            outside.write_text("main dirty\n", encoding="utf-8")
            path = _add(root, task, base)
            before = capture_snapshot(root, task)
            original = before.allowed_hashes["tests/sdd_tasks/seed.txt"]
            changed = path / "tests/sdd_tasks/seed.txt"
            changed.write_text("partial\n", encoding="utf-8")
            current = prepare_worktree(root, task, base, recovery_snapshot=before)
            self.assertEqual(before.allowed_hashes["tests/sdd_tasks/seed.txt"], original)
            self.assertNotEqual(current.allowed_hashes["tests/sdd_tasks/seed.txt"], original)
            self.assertEqual(changed.read_text(encoding="utf-8"), "partial\n")
            self.assertEqual(current.head, base)

    def test_recovery_refuses_out_of_scope_change_without_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, _ = _fixture(temp)
            path = _add(root, task, base)
            before = capture_snapshot(root, task)
            changed = path / "outside.txt"
            changed.write_text("outside partial\n", encoding="utf-8")
            with self.assertRaises(WorkspaceError) as error:
                prepare_worktree(root, task, base, recovery_snapshot=before)
            self.assertEqual(error.exception.code, "workspace_recovery_conflict")
            self.assertEqual(changed.read_text(encoding="utf-8"), "outside partial\n")

    def test_recovery_of_missing_canonical_worktree_does_not_recreate_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root, task, base, _ = _fixture(temp)
            path = _add(root, task, base)
            before = capture_snapshot(root, task)
            _git(root, "worktree", "remove", "--force", str(path))
            path.parent.rmdir()
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())
            with self.assertRaises(WorkspaceError) as error:
                prepare_worktree(root, task, base, recovery_snapshot=before)
            self.assertEqual(error.exception.code, "workspace_recovery_worktree_missing")
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())
            self.assertNotIn(str(path.resolve()), _git(root, "worktree", "list", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
