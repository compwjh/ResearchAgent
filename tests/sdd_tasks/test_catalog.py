import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.catalog import rebuild, status
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks._fixtures import task_markdown, task_metadata

_LABEL = {"pending": "待执行", "completed": "完成", "blocked": "阻塞", "cancelled": "取消"}

def _db(root):
    return root / ".sdd/runtime/task-ledger.sqlite3"

def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

def _meta(number, status, deps=()):
    return task_metadata({"task_id": "spec-016-task-" + number, "title": "Task " + number,
                          "status": status, "depends_on": list(deps)})

def _doc(meta):
    return "# {}\n> 当前状态：`{}`\n\n{}".format(meta["title"], _LABEL[meta["status"]], task_markdown(meta))

def _write_mirrors(root, paths, metas, spec_status="已确认"):
    spec, readme = [], []
    for meta in metas:
        name, state, tid = paths[meta["task_id"]].name, _LABEL[meta["status"]], meta["task_id"]
        number = tid[-2:]
        deps = ", ".join(item[-2:] for item in meta["depends_on"]) or "—"
        spec.append("| {} | {} | [Task](../plans/016/{}) | {} | {} |".format(number, meta["title"], name, deps, state))
        readme.append("| {} | {} | [Task](./{}) | {} | {} |".format(number, meta["title"], name, deps, state))
    base = root / "docs/sdd"
    header = "| NN | Task | 文档 | 依赖 | 状态 |\n|---|---|---|---|---|\n"
    current = "## 状态\n\n**当前状态：`{}`**\n\n".format(spec_status)
    (base / "specs/016-portable-task-ledger.md").write_text(
        "# Spec\n\n" + current + header + "\n".join(spec) + "\n")
    (base / "plans/016/README.md").write_text("# Tasks\n" + header + "\n".join(readme) + "\n")

def _repo(directory, task3=None, task4=None, duplicate=None):
    root = Path(directory) / "repo"
    root.mkdir()
    p = root / "docs/sdd/plans/016"
    p.mkdir(parents=True)
    (root / "docs/sdd/specs").mkdir(parents=True)
    (root / ".gitignore").write_text(".worktrees/\n")
    m3, m4 = task3 or _meta("03", "completed"), task4 or _meta("04", "pending", ("spec-016-task-03",))
    paths = {}
    for number, meta in (("03", m3), ("04", m4)):
        paths[meta["task_id"]] = p / ("task-" + number + "-fixture.md")
        paths[meta["task_id"]].write_text(_doc(meta))
    if duplicate:
        (p / duplicate[0]).write_text(_doc(duplicate[1]))
    _write_mirrors(root, paths, (m3, m4))
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "catalog fixture")
    return root, paths, m3, m4


class CatalogTests(unittest.TestCase):
    def test_missing_database_rebuild_is_persistent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            db = _db(root)
            first, again = rebuild(db, root), rebuild(db, root)
            self.assertEqual((first.tasks, first.runs, first.deduplicated, first.database), (2, 0, 0, db.resolve()))
            self.assertEqual((again.tasks, again.runs, again.deduplicated), (2, 0, 0))
            with closing(connect(db)) as conn:
                self.assertEqual(dict(conn.execute("SELECT task_id,status FROM tasks ORDER BY task_id").fetchall()[0]),
                                 {"task_id": "spec-016-task-03", "status": "completed"})

    def test_same_worktree_duplicate_is_rejected_even_with_same_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, m3, _ = _repo(td, duplicate=("task-03-copy.md", _meta("03", "completed")))
            with self.assertRaisesRegex(ValueError, "DUPLICATE_TASK_IN_WORKTREE"):
                rebuild(_db(root), root)

    def test_catalog_conflicts_reject_hash_status_dependency_and_cycle(self):
        cases = (
            (None, None, ("task-03-copy.md", _meta("03", "completed") | {"title": "Changed"})),
            (None, _meta("04", "pending", ("spec-016-task-99",)), None),
            (_meta("03", "completed", ("spec-016-task-04",)), None, None),
        )
        for i, (m3, m4, duplicate) in enumerate(cases):
            with self.subTest(case=i), tempfile.TemporaryDirectory() as td:
                root, _, _, _ = _repo(td, m3, m4, duplicate)
                with self.assertRaises(ValueError):
                    rebuild(_db(root), root)

    def test_failed_rebuild_keeps_existing_task_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, _ = _repo(td)
            db = _db(root)
            rebuild(db, root)
            with closing(connect(db)) as conn:
                before = [tuple(r) for r in conn.execute("SELECT task_id,status,task_hash FROM tasks ORDER BY task_id")]
            paths["spec-016-task-04"].write_text(_doc(_meta("04", "pending", ("spec-016-task-99",))))
            with self.assertRaises(ValueError):
                rebuild(db, root)
            with closing(connect(db)) as conn:
                after = [tuple(r) for r in conn.execute("SELECT task_id,status,task_hash FROM tasks ORDER BY task_id")]
            self.assertEqual(after, before)

    def test_unknown_schema_and_active_lease_preserve_database(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            db = _db(root)
            rebuild(db, root)
            with closing(connect(db)) as raw:
                raw.execute("UPDATE schema_migrations SET version=99")
            with self.assertRaises(ValueError):
                rebuild(db, root)
            raw = sqlite3.connect(str(db))
            try:
                with raw:
                    self.assertEqual(raw.execute("SELECT version FROM schema_migrations").fetchone()[0], 99)
                    raw.execute("UPDATE schema_migrations SET version=1")
            finally:
                raw.close()
            with closing(connect(db)) as conn:
                row = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id='spec-016-task-04'").fetchone()
                conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             ("R1", "spec-016-task-04", 1, "claimed", "codex", "exec", "{}", "tester", ".worktrees/spec-016", "feature/spec-016-x", "abc", row[0], row[1], "now"))
                conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)", ("spec-016-task-04", "R1", "token", "now", "now", "2099-01-01T00:00:00Z"))
                conn.execute("INSERT INTO events VALUES (?,?,?,?,?)", ("R1", 1, "now", "claimed", "{}"))
            with self.assertRaises(ValueError):
                rebuild(db, root)
            with closing(connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM events").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM leases").fetchone()[0], 1)

    def test_fixed_database_path_and_empty_status(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, _ = _repo(td)
            with self.assertRaisesRegex(ValueError, "DATABASE_PATH_INVALID"):
                rebuild(Path(td) / "wrong.sqlite3", root)
            self.assertFalse((root / ".sdd/runtime").exists())
            for path in paths.values():
                path.unlink()
            db = _db(root)
            rebuild(db, root)
            with closing(connect(db)) as conn:
                self.assertEqual(status(conn), {key: [] for key in (
                    "eligible", "waiting", "running", "blocked", "completed", "diagnostics")})

    def test_task_symlink_scan_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, _ = _repo(td)
            task = paths["spec-016-task-03"]
            target = root / "task-copy.md"
            target.write_text(task.read_text(encoding="utf-8"), encoding="utf-8")
            task.unlink()
            task.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "TASK_SYMLINK"):
                rebuild(_db(root), root)
