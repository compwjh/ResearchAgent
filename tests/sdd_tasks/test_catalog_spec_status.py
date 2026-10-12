import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.catalog import CatalogError, rebuild, status
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_catalog import _db, _git, _meta, _repo

SPEC = "docs/sdd/specs/016-portable-task-ledger.md"
TASK = "spec-016-task-04"


def _task4(state="pending"):
    meta = _meta("04", state, ("spec-016-task-03",))
    meta["required_gates"] = []
    return meta


def _linked(directory):
    task = _task4()
    root, _, _, _ = _repo(directory, task4=task)
    canonical = root / task["worktree"]["path"]
    canonical.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-q", "-b", task["worktree"]["branch"], str(canonical), "HEAD")
    database = _db(root)
    rebuild(database, root)
    return root, canonical, database


def _set_status(root, value):
    path = root / SPEC
    lines = path.read_text(encoding="utf-8").splitlines()
    indices = [i for i, line in enumerate(lines) if line.startswith("**当前状态：")]
    if len(indices) != 1:
        raise AssertionError("fixture must have one Spec status line")
    lines[indices[0]] = "**当前状态：`{}`**".format(value)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _status(database):
    with closing(connect(database)) as conn:
        return status(conn)


def _item(rows):
    return next(row for row in rows if row["task_id"] == TASK)


class CatalogSpecStatusTests(unittest.TestCase):
    def test_unconfirmed_waits_and_confirmed_becomes_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            _, canonical, database = _linked(td)
            _set_status(canonical, "待确认")
            waiting = _item(_status(database)["waiting"])
            self.assertIn("spec_not_claimable:待确认", waiting["reasons"])
            _set_status(canonical, "已确认")
            self.assertEqual(_item(_status(database)["eligible"])["reasons"], [])

    def test_main_stale_spec_does_not_override_canonical_status(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, database = _linked(td)
            _set_status(root, "待确认")
            _set_status(canonical, "实施中")
            self.assertEqual(_item(_status(database)["eligible"])["reasons"], [])

    def test_malformed_canonical_spec_fails_closed(self):
        variants = ("**当前状态：`未知`**", "## 状态\n\n**当前状态：`已确认`**\n\n## 状态")
        for malformed in variants:
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as td:
                _, canonical, database = _linked(td)
                (canonical / SPEC).write_text("# Spec\n\n" + malformed, encoding="utf-8")
                with self.assertRaises(CatalogError) as caught:
                    _status(database)
                self.assertEqual(caught.exception.code, "SPEC_STATUS_INVALID")

    def test_unregistered_canonical_view_errors_without_creating_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            task = _task4()
            root, _, _, _ = _repo(td, task4=task)
            database = _db(root)
            rebuild(database, root)
            with self.assertRaises(CatalogError) as caught:
                _status(database)
            self.assertEqual(caught.exception.code, "CANONICAL_WORKTREE_UNREGISTERED")
            self.assertFalse((root / task["worktree"]["path"]).exists())

    def test_completed_task_does_not_require_spec_status_or_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            task = _task4("completed")
            root, _, _, _ = _repo(td, task4=task)
            database = _db(root)
            rebuild(database, root)
            (root / SPEC).write_text("## 状态\n**当前状态：坏文档**", encoding="utf-8")
            self.assertEqual(_item(_status(database)["completed"])["task_status"], "completed")


if __name__ == "__main__":
    unittest.main()
