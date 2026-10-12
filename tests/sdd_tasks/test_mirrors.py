import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks import mirrors
from scripts.sdd_tasks.documents import parse_task_text
from tests.sdd_tasks._fixtures import task_markdown

LABELS = {"pending": "待执行", "blocked": "阻塞", "completed": "完成", "cancelled": "取消"}


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task_rel = Path("docs/sdd/plans/016/task-01-mirror-fixture.md")
        self.spec_rel = Path("docs/sdd/specs/016-portable-task-ledger.md")
        self.readme_rel = Path("docs/sdd/plans/016/README.md")
        for rel in (self.task_rel, self.spec_rel, self.readme_rel):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        self.task = self.write_task("pending")
        self.write_mirrors("pending")

    def tearDown(self):
        self.temp.cleanup()

    def write_task(self, status):
        metadata = {"task_id": "spec-016-task-01", "title": "Mirror fixture",
                    "depends_on": [], "status": status}
        text = "> 当前状态：{}\n\n".format(LABELS[status]) + task_markdown(metadata)
        (self.root / self.task_rel).write_text(text, encoding="utf-8")
        return parse_task_text(text, self.task_rel)

    def row(self, status, link):
        return "| 01 | Mirror fixture | [task-01]({}) | — | {} |".format(link, LABELS[status])

    def write_mirrors(self, status):
        spec = "\n".join(("| 编号 | 任务 | 思维链文档 | 依赖 | 状态 |", "|---|---|---|---|---|",
                           self.row(status, "../plans/016/task-01-mirror-fixture.md"), ""))
        readme = "\n".join(("| 编号 | 任务 | 文档 | 依赖 | 状态 |", "|---|---|---|---|---|",
                             self.row(status, "./task-01-mirror-fixture.md"), ""))
        (self.root / self.spec_rel).write_text(spec, encoding="utf-8")
        (self.root / self.readme_rel).write_text(readme, encoding="utf-8")

    def test_valid_three_mirrors(self):
        self.assertIsNone(mirrors.validate_mirrors(self.task, self.root))

    def test_duplicate_rows_wrong_links_and_status_disagreement_fail(self):
        readme = self.root / self.readme_rel
        original = readme.read_text(encoding="utf-8")
        readme.write_text(original + self.row("pending", "./task-01-mirror-fixture.md") + "\n", encoding="utf-8")
        with self.assertRaises(mirrors.MirrorError):
            mirrors.validate_mirrors(self.task, self.root)
        readme.write_text(original, encoding="utf-8")
        for path, old in ((self.root / self.spec_rel, "../plans/016/task-01-mirror-fixture.md"),
                          (readme, "./task-01-mirror-fixture.md")):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(old, "./task-02-wrong.md"), encoding="utf-8")
            with self.assertRaises(mirrors.MirrorError):
                mirrors.validate_mirrors(self.task, self.root)
            path.write_text(text, encoding="utf-8")
        spec = self.root / self.spec_rel
        text = spec.read_text(encoding="utf-8").replace("| 待执行 |", "| 阻塞 |")
        spec.write_text(text, encoding="utf-8")
        with self.assertRaises(mirrors.MirrorError):
            mirrors.validate_mirrors(self.task, self.root)

    def test_renderer_is_pure_and_changes_only_status(self):
        before = {p: (self.root / p).read_text(encoding="utf-8")
                  for p in (self.task_rel, self.spec_rel, self.readme_rel)}
        original = self.task
        for status, label in LABELS.items():
            rendered = mirrors.render_status_update(original, status, self.root)
            self.assertEqual(set(rendered), {p.as_posix() for p in before})
            task_text = rendered[self.task_rel.as_posix()]
            updated = parse_task_text(task_text, self.task_rel)
            self.assertEqual(updated.metadata["status"], status)
            self.assertEqual(updated.task_hash, original.task_hash)
            self.assertEqual(updated.prompt_hash, original.prompt_hash)
            self.assertEqual(task_text, before[self.task_rel].replace(
                "> 当前状态：待执行", "> 当前状态：" + label, 1).replace(
                '"status": "pending"', '"status": "' + status + '"', 1))
            self.assertIn("| {} |".format(label), rendered[self.spec_rel.as_posix()])
            self.assertIn("| {} |".format(label), rendered[self.readme_rel.as_posix()])
        self.assertEqual(before, {p: (self.root / p).read_text(encoding="utf-8") for p in before})

    def test_duplicate_task_status_line_fails(self):
        path = self.root / self.task_rel
        path.write_text(path.read_text(encoding="utf-8") + "> 当前状态：阻塞\n", encoding="utf-8")
        with self.assertRaises(mirrors.MirrorError):
            mirrors.validate_mirrors(self.task, self.root)

    def test_symlink_escape_is_rejected(self):
        self.make_spec_symlink_escape()
        with self.assertRaises(mirrors.MirrorError):
            mirrors.validate_mirrors(self.task, self.root)

    def test_internal_symlink_is_rejected(self):
        path = self.root / self.spec_rel
        target = self.root / "spec-mirror-copy.md"
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(mirrors.MirrorError):
            mirrors.validate_mirrors(self.task, self.root)

    def make_spec_symlink_escape(self):
        path = self.root / self.spec_rel
        outside = self.root.parent / (self.root.name + "-outside-spec-mirror.md")
        outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        path.unlink()
        path.symlink_to(outside)

    def test_renderer_rejects_symlink_escape(self):
        self.make_spec_symlink_escape()
        with self.assertRaises(mirrors.MirrorError):
            mirrors.render_status_update(self.task, "completed", self.root)


if __name__ == "__main__":
    unittest.main()
