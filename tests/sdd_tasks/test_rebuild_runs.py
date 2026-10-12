import json
import subprocess
import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.catalog import rebuild, status
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_catalog import _db, _repo, _write_mirrors
from tests.sdd_tasks.test_result_schema import valid_result

RB, RE = "<!-- sdd-run-result:v1:begin -->", "<!-- sdd-run-result:v1:end -->"
MB, ME = "<!-- sdd-run-meta:v1:begin -->", "<!-- sdd-run-meta:v1:end -->"
RUN_ID = "123e4567-e89b-12d3-a456-426614174000"


def _summary(root, paths, meta, base=None, outcome="succeeded"):
    task = parse_task(paths[meta["task_id"]])
    result = valid_result()
    result.update(task_id=meta["task_id"], task_hash=task.task_hash,
                  prompt_hash=task.prompt_hash, outcome=outcome)
    runmeta = {"schema": "sdd-run-meta/v1", "run_id": RUN_ID,
               "task_id": meta["task_id"], "task_hash": task.task_hash,
               "prompt_hash": task.prompt_hash, "attempt": 1, "ide": "codex",
               "executor_id": "fixture-executor", "agent_role": meta["agent_role"],
               "model": None, "worktree": meta["worktree"]["path"],
               "branch": meta["worktree"]["branch"],
               "base_commit": base or subprocess.check_output(
                   ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
               "claimed_at": "2026-10-11T00:00:00Z"}
    path = root / "docs/sdd/runs/016/task-04/{}.md".format(RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((RB, json.dumps(result), RE, MB,
                              json.dumps(runmeta), ME, "fixture summary")), encoding="utf-8")
    return task, result, runmeta, path


def _snapshot(db):
    with closing(connect(db)) as conn:
        names = ("tasks", "dependencies", "runs", "events", "artifacts", "leases")
        return {name: [tuple(row) for row in conn.execute(
            "SELECT * FROM {} ORDER BY rowid".format(name))] for name in names}


class RebuildSummaryIntegrationTests(unittest.TestCase):
    def fixture(self, directory):
        root, paths, m3, m4 = _repo(directory)
        return root, paths, m3, m4, _db(root)

    def test_terminal_import_is_idempotent_and_does_not_complete_task(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, m4, db = self.fixture(td)
            rebuild(db, root)
            _, _, _, _ = _summary(root, paths, m4)
            first, again = rebuild(db, root), rebuild(db, root)
            self.assertEqual((first.runs, again.runs), (1, 1))
            with closing(connect(db)) as conn:
                run = conn.execute("SELECT state,owner_json,error_code,error_summary FROM runs").fetchone()
                state = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                     (m4["task_id"],)).fetchone()[0]
            self.assertEqual(tuple(run), ("succeeded", "{}", None, None))
            self.assertEqual(state, "pending")
    def test_bad_summary_never_creates_or_mutates_database(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, m4, db = self.fixture(td)
            _, _, _, path = _summary(root, paths, m4)
            path.write_text(path.read_text().replace(ME, ""), encoding="utf-8")
            with self.assertRaises(ValueError):
                rebuild(db, root)
            self.assertFalse(db.exists())
            path.unlink()
            rebuild(db, root)
            before = _snapshot(db)
            _summary(root, paths, m4)
            path.write_text(path.read_text().replace(ME, ""), encoding="utf-8")
            with self.assertRaises(ValueError):
                rebuild(db, root)
            self.assertEqual(_snapshot(db), before)

    def test_unknown_base_commit_rejected_without_run_import(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, m4, db = self.fixture(td)
            rebuild(db, root)
            missing = "0" * 40
            check = subprocess.run(["git", "-C", str(root), "cat-file", "-e",
                                    missing + "^{commit}"])
            self.assertNotEqual(check.returncode, 0)
            _summary(root, paths, m4, base=missing)
            before = _snapshot(db)
            with self.assertRaises(ValueError):
                rebuild(db, root)
            self.assertEqual(_snapshot(db), before)

    def test_existing_owner_error_and_events_survive_same_run_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, _, m4, db = self.fixture(td)
            rebuild(db, root)
            task, result, meta, _ = _summary(root, paths, m4, outcome="failed")
            with closing(connect(db)) as conn:
                conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (RUN_ID, m4["task_id"], 1, "failed", "codex", "fixture-executor",
                     '{"pid":7}', m4["agent_role"], None, meta["worktree"], meta["branch"],
                     meta["base_commit"], task.task_hash, task.prompt_hash, meta["claimed_at"],
                     result["started_at"], result["ended_at"], result["duration_ms"],
                     "docs/sdd/runs/016/task-04/{}.md".format(RUN_ID), "CHILD_FAILED", "diagnostic"))
                conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                             (RUN_ID, 1, meta["claimed_at"], "failed", '{}'))
            report = rebuild(db, root)
            self.assertEqual(report.runs, 1)
            with closing(connect(db)) as conn:
                run = conn.execute("SELECT owner_json,error_code,error_summary FROM runs").fetchone()
                event = conn.execute("SELECT count(*) FROM events").fetchone()[0]
            self.assertEqual(tuple(run), ('{"pid":7}', "CHILD_FAILED", "diagnostic"))
            self.assertEqual(event, 1)

    def test_active_and_expired_claimed_runs_conflict_with_terminal_summary(self):
        for expiry in ("2099-01-01T00:00:00Z", "2000-01-01T00:00:00Z"):
            with self.subTest(expiry=expiry), tempfile.TemporaryDirectory() as td:
                root, paths, _, m4, db = self.fixture(td)
                rebuild(db, root)
                task, _, meta, _ = _summary(root, paths, m4)
                with closing(connect(db)) as conn:
                    conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (RUN_ID, m4["task_id"], 1, "claimed", "codex", "fixture-executor", '{}',
                         m4["agent_role"], None, meta["worktree"], meta["branch"], meta["base_commit"],
                         task.task_hash, task.prompt_hash, meta["claimed_at"], None, None, None, None, None, None))
                    conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                        (m4["task_id"], RUN_ID, "token", meta["claimed_at"], meta["claimed_at"], expiry))
                with self.assertRaises(ValueError):
                    rebuild(db, root)

    def test_removed_pending_task_cannot_remain_scheduled(self):
        with tempfile.TemporaryDirectory() as td:
            root, paths, m3, m4, db = self.fixture(td)
            rebuild(db, root)
            paths[m4["task_id"]].unlink()
            _write_mirrors(root, paths, (m3,))
            before = _snapshot(db)
            try:
                rebuild(db, root)
            except ValueError:
                self.assertEqual(_snapshot(db), before)
                return
            with closing(connect(db)) as conn:
                live = status(conn)
            scheduled = {item["task_id"] for group in
                         ("eligible", "waiting", "running", "blocked") for item in live[group]}
            self.assertNotIn(m4["task_id"], scheduled)
