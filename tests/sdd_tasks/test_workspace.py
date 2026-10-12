import hashlib
import os
import signal
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.workspace import WorkspaceError, capture_snapshot, compare_snapshot
from tests.sdd_tasks._fixtures import TASK_PATH, task_markdown

_BRANCH = "feature/spec-016-portable-task-ledger"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def _fixture(directory):
    main = Path(directory) / "repo"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    _git(main, "config", "user.name", "Fixture")
    _git(main, "config", "user.email", "fixture@example.invalid")
    (main / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
    (main / TASK_PATH).parent.mkdir(parents=True)
    (main / TASK_PATH).write_text(task_markdown(), encoding="utf-8")
    for folder in ("scripts/sdd_tasks", "tests/sdd_tasks"):
        (main / folder).mkdir(parents=True)
        (main / folder / "seed.txt").write_text("seed\n", encoding="utf-8")
    (main / "scripts/sdd_tasks/rename-old.txt").write_text("rename\n", encoding="utf-8")
    outside = main / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    _git(main, "add", ".")
    _git(main, "commit", "-qm", "snapshot fixture")
    base = _git(main, "rev-parse", "HEAD")
    task = parse_task(main / TASK_PATH)
    (main / ".worktrees").mkdir()
    worktree = main / ".worktrees/spec-016"
    _git(main, "worktree", "add", "-qb", _BRANCH, str(worktree), base)
    outside.write_text("main worktree dirty\n", encoding="utf-8")
    return main, worktree, task, outside


class WorkspaceSnapshotTests(unittest.TestCase):
    def test_capture_is_registered_frozen_and_does_not_touch_main_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            main, worktree, task, outside = _fixture(temp)
            main_bytes = outside.read_bytes()
            snapshot = capture_snapshot(main, task)
            self.assertEqual(snapshot.worktree_path, worktree.resolve())
            self.assertEqual(snapshot.branch, _BRANCH)
            self.assertEqual(snapshot.head, _git(worktree, "rev-parse", "HEAD"))
            self.assertEqual(snapshot.status_records, ())
            self.assertIsNone(snapshot.allowed_hashes["tests/sdd_tasks"])
            self.assertEqual(snapshot.allowed_hashes["tests/sdd_tasks/seed.txt"],
                             hashlib.sha256(b"seed\n").hexdigest())
            self.assertEqual(compare_snapshot(snapshot, capture_snapshot(main, task)).kind, "unchanged")
            with self.assertRaises(FrozenInstanceError):
                snapshot.branch = "changed"
            self.assertEqual(outside.read_bytes(), main_bytes)

    def test_compare_reports_allowed_add_modify_and_staged_rename_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            main, worktree, task, _ = _fixture(temp)
            before = capture_snapshot(main, task)
            (worktree / "tests/sdd_tasks/seed.txt").write_text("changed\n", encoding="utf-8")
            (worktree / "tests/sdd_tasks/new.txt").write_text("new\n", encoding="utf-8")
            _git(worktree, "mv", "scripts/sdd_tasks/rename-old.txt", "scripts/sdd_tasks/rename-new.txt")
            after = capture_snapshot(main, task)
            result = compare_snapshot(before, after)
            self.assertEqual(result.kind, "partial")
            self.assertTrue({"tests/sdd_tasks/seed.txt", "tests/sdd_tasks/new.txt",
                             "scripts/sdd_tasks/rename-old.txt", "scripts/sdd_tasks/rename-new.txt"}
                            <= set(result.changed_paths))

    def test_compare_marks_unallowed_change_out_of_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            main, worktree, task, _ = _fixture(temp)
            before = capture_snapshot(main, task)
            (worktree / "outside.txt").write_text("outside changed\n", encoding="utf-8")
            result = compare_snapshot(before, capture_snapshot(main, task))
            self.assertEqual(result.kind, "out_of_scope")
            self.assertIn("outside.txt", result.out_of_scope_paths)
        with tempfile.TemporaryDirectory() as temp:
            main, worktree, task, _ = _fixture(temp)
            before = capture_snapshot(main, task)
            _git(worktree, "mv", "tests/sdd_tasks/seed.txt", "outside-renamed.txt")
            result = compare_snapshot(before, capture_snapshot(main, task))
            self.assertEqual(result.kind, "out_of_scope")
            self.assertTrue({"tests/sdd_tasks/seed.txt", "outside-renamed.txt"} <= set(result.changed_paths))
            self.assertIn("outside-renamed.txt", result.out_of_scope_paths)

    def test_compare_rejects_inconsistent_snapshot_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            main, _, task, _ = _fixture(temp)
            before = capture_snapshot(main, task)
            result = compare_snapshot(before, replace(before, branch="feature/other"))
            self.assertEqual((result.kind, result.error_code), ("conflict", "workspace_identity_mismatch"))

    def test_capture_hashes_safe_file_links_and_rejects_escapes_broken_links_and_fifo(self):
        with tempfile.TemporaryDirectory() as temp:
            main, worktree, task, _ = _fixture(temp)
            target = worktree / "scripts/sdd_tasks/seed.txt"
            link = worktree / "tests/sdd_tasks/link.txt"
            link.symlink_to(target)
            snapshot = capture_snapshot(main, task)
            self.assertEqual(snapshot.allowed_hashes["tests/sdd_tasks/link.txt"],
                             hashlib.sha256(target.read_bytes()).hexdigest())
            link.unlink()

            sentinel = Path(temp) / "outside-sentinel.txt"
            sentinel.write_text("outside\n", encoding="utf-8")
            link.symlink_to(sentinel)
            with self.assertRaises(WorkspaceError) as error:
                capture_snapshot(main, task)
            self.assertEqual(error.exception.code, "workspace_path_unsafe")
            link.unlink()

            link_dir = worktree / "tests/sdd_tasks/link-dir"
            link_dir.symlink_to(worktree / "scripts/sdd_tasks", target_is_directory=True)
            with self.assertRaises(WorkspaceError) as error:
                capture_snapshot(main, task)
            self.assertEqual(error.exception.code, "workspace_path_unsafe")
            link_dir.unlink()

            link.symlink_to(sentinel.with_name("missing-target.txt"))
            with self.assertRaises(WorkspaceError) as error:
                capture_snapshot(main, task)
            self.assertEqual(error.exception.code, "workspace_path_unsafe")
            link.unlink()

            fifo = worktree / "tests/sdd_tasks/pipe"
            os.mkfifo(fifo)
            previous = signal.signal(signal.SIGALRM,
                                      lambda *_: (_ for _ in ()).throw(AssertionError("FIFO scan blocked")))
            signal.alarm(3)
            try:
                with self.assertRaises(WorkspaceError) as error:
                    capture_snapshot(main, task)
                self.assertEqual(error.exception.code, "workspace_path_unsafe")
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")


if __name__ == "__main__":
    unittest.main()
