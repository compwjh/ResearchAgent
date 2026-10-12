import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.catalog import discover_worktrees, rebuild
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_catalog import _db, _doc, _git, _repo, _write_mirrors


class CatalogWorktreeTests(unittest.TestCase):
    def test_registered_roots_and_canonical_completed_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, task3, task4 = _repo(td)
            link = root / task4["worktree"]["path"]
            link.parent.mkdir()
            _git(root, "worktree", "add", "-q", "-b", task4["worktree"]["branch"], str(link), "HEAD")
            self.assertEqual(set(discover_worktrees(root)), {root.resolve(), link.resolve()})
            done = dict(task4, status="completed")
            (link / paths[task4["task_id"]].relative_to(root)).write_text(_doc(done))
            mirrors = {key: link / path.relative_to(root) for key, path in paths.items()}
            _write_mirrors(link, mirrors, (task3, done))
            db = _db(root)
            report = rebuild(db, root)
            self.assertEqual(report.deduplicated, 2)
            with closing(connect(db)) as conn:
                status = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task4["task_id"],)).fetchone()[0]
            self.assertEqual(status, "completed")
            (link / paths[task4["task_id"]].relative_to(root)).write_text(_doc(task4))
            _write_mirrors(link, mirrors, (task3, task4))
            for rel in ("docs/sdd/specs/016-portable-task-ledger.md", "docs/sdd/plans/016/README.md"):
                path = root / rel
                path.write_text(path.read_text(encoding="utf-8").replace(
                    "task-04-fixture.md", "task-99-stale.md"), encoding="utf-8")
            report = rebuild(db, root)
            self.assertEqual(report.deduplicated, 2)
            with closing(connect(db)) as conn:
                status = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task4["task_id"],)).fetchone()[0]
            self.assertEqual(status, "pending")

    def test_status_conflict_without_registered_canonical_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, task3, task4 = _repo(td)
            link = root / ".worktrees/noncanonical"
            link.parent.mkdir()
            _git(root, "worktree", "add", "-q", "-b", "fixture/noncanonical", str(link), "HEAD")
            done = dict(task4, status="completed")
            (link / paths[task4["task_id"]].relative_to(root)).write_text(_doc(done))
            linked_paths = {key: link / path.relative_to(root) for key, path in paths.items()}
            _write_mirrors(link, linked_paths, (task3, done))
            with self.assertRaisesRegex(ValueError, "TASK_STATUS_CONFLICT"):
                rebuild(_db(root), root)
