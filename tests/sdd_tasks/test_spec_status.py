import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.spec_status import SpecStatusError, is_claimable, load_spec_status, read_spec_status
from tests.sdd_tasks.test_catalog import _git, _repo


def _spec_text(state, suffix=""):
    return "# Spec 016\n\n## 状态\n\n**当前状态：`{}`{}**\n".format(state, suffix)


def _fixture(directory):
    root, paths, _, meta = _repo(directory)
    canonical = root / ".worktrees/spec-016"
    canonical.parent.mkdir(parents=True)
    _git(root, "worktree", "add", "-q", "-b", meta["worktree"]["branch"], str(canonical), "HEAD")
    task = parse_task(paths[meta["task_id"]])
    spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
    return root, task, spec


class SpecStatusTests(unittest.TestCase):
    def test_canonical_states_and_parenthetical_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root, task, spec = _fixture(directory)
            for state, allowed in (("已确认", True), ("实施中", True), ("待确认", False),
                                   ("已完成", False), ("阻塞", False)):
                suffix = "（2026-09-08；说明）" if state == "实施中" else ""
                spec.write_text(_spec_text(state, suffix), encoding="utf-8")
                self.assertEqual(read_spec_status(spec), state)
                self.assertEqual(load_spec_status(task, root), state)
                self.assertEqual(is_claimable(state), allowed)
            spec.write_text("# Spec 016\n\n## 状态\n\n**当前状态：已确认**\n", encoding="utf-8")
            self.assertEqual(read_spec_status(spec), "已确认")

    def test_missing_malformed_and_symlink_specs_fail_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, task, spec = _fixture(directory)
            spec.unlink()
            before_paths = set(root.rglob("*"))
            with self.assertRaises(SpecStatusError) as missing:
                load_spec_status(task, root)
            self.assertEqual(missing.exception.code, "SPEC_STATUS_INVALID")
            self.assertEqual(set(root.rglob("*")), before_paths)
            malformed = b"# Spec\n\n## Status\n\n**Current status: ???**\n"
            spec.write_bytes(malformed)
            with self.assertRaises(SpecStatusError) as invalid:
                load_spec_status(task, root)
            self.assertEqual(invalid.exception.code, "SPEC_STATUS_INVALID")
            self.assertEqual(spec.read_bytes(), malformed)
            for bad in ("# Spec\n\n## 状态\n\n**当前状态：已确认**\n\n## 状态\n",
                        "# Spec\n\n## 状态\n\n**当前状态：已确认**\n**当前状态：实施中**\n",
                        "# Spec\n\n## 状态\n\n```md\n**当前状态：已确认**\n```\n"):
                spec.write_text(bad, encoding="utf-8")
                with self.assertRaises(SpecStatusError) as duplicate:
                    load_spec_status(task, root)
                self.assertEqual(duplicate.exception.code, "SPEC_STATUS_INVALID")
                self.assertEqual(spec.read_text(encoding="utf-8"), bad)
            outside = Path(directory) / "outside.md"
            outside.write_text(_spec_text("已确认"), encoding="utf-8")
            target = outside.read_bytes()
            spec.unlink()
            spec.symlink_to(outside)
            with self.assertRaises(SpecStatusError) as linked:
                load_spec_status(task, root)
            self.assertEqual(linked.exception.code, "SPEC_STATUS_INVALID")
            self.assertTrue(spec.is_symlink())
            self.assertEqual(outside.read_bytes(), target)

    def test_unregistered_and_ambiguous_canonical_specs_fail_without_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root, paths, _, meta = _repo(directory)
            canonical = root / meta["worktree"]["path"]
            spec = canonical / "docs/sdd/specs/016-unregistered.md"
            spec.parent.mkdir(parents=True)
            spec.write_text(_spec_text("已确认"), encoding="utf-8")
            task = parse_task(paths[meta["task_id"]])
            with self.assertRaises(SpecStatusError) as caught:
                load_spec_status(task, root)
            self.assertEqual(caught.exception.code, "SPEC_STATUS_INVALID")
        with tempfile.TemporaryDirectory() as directory:
            root, task, spec = _fixture(directory)
            spec.write_text(_spec_text("已确认"), encoding="utf-8")
            extra = spec.with_name("016-secondary.md")
            extra.write_text(_spec_text("实施中"), encoding="utf-8")
            before = (spec.read_bytes(), extra.read_bytes())
            with self.assertRaises(SpecStatusError) as caught:
                load_spec_status(task, root)
            self.assertEqual(caught.exception.code, "SPEC_STATUS_INVALID")
            self.assertEqual((spec.read_bytes(), extra.read_bytes()), before)


if __name__ == "__main__":
    unittest.main()
