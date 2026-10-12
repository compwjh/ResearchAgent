import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.store import TaskRun, connect, initialize, transaction


def _connect_and_initialize(path):
    with closing(connect(path)) as conn:
        initialize(conn)


def _sentinel_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), isolation_level=None)) as conn:
        conn.execute("CREATE TABLE sentinel(value TEXT)")
        conn.execute("INSERT INTO sentinel VALUES ('keep')")
    return path.read_bytes()


class TaskStoreTests(unittest.TestCase):
    def test_connection_and_schema_v1(self):
        with tempfile.TemporaryDirectory() as directory, closing(
                connect(Path(directory) / "ledger.sqlite3")) as conn:
            initialize(conn)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"schema_migrations", "tasks", "dependencies", "runs", "events", "artifacts", "leases"})
            self.assertEqual(conn.execute("SELECT version FROM schema_migrations").fetchone()[0], 1)
            indexes = [row[1] for row in conn.execute("PRAGMA index_list(runs)") if row[2] and row[4]]
            self.assertEqual(len(indexes), 1)
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (indexes[0],)).fetchone()[0]
            predicate = " ".join(sql.casefold().split()).split(" where ", 1)[1]
            self.assertEqual(predicate.replace(" ", ""), "statein('claimed','running')")
            quoted = '"' + indexes[0].replace('"', '""') + '"'
            self.assertEqual([row[2] for row in conn.execute("PRAGMA index_info({})".format(quoted))], ["task_id"])
        self.assertTrue(TaskRun.__dataclass_params__.frozen)
        fields = ("run_id task_id attempt state ide executor_id owner agent_role model worktree branch "
                  "base_commit task_hash prompt_hash claimed_at started_at ended_at duration_ms result_doc "
                  "error_code error_summary")
        self.assertEqual(tuple(TaskRun.__dataclass_fields__), tuple(fields.split()))

    def test_unknown_version_preserves_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            with closing(sqlite3.connect(str(path), isolation_level=None)) as conn:
                conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
                conn.execute("INSERT INTO schema_migrations VALUES (99, 'future')")
                conn.execute("CREATE TABLE sentinel(value TEXT)")
                conn.execute("INSERT INTO sentinel VALUES ('keep')")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                _connect_and_initialize(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + "-wal").exists())
            self.assertFalse(Path(str(path) + "-shm").exists())
            with closing(sqlite3.connect(str(path))) as conn:
                self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
                self.assertEqual(conn.execute("SELECT value FROM sentinel").fetchone()[0], "keep")
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertEqual(tables, {"schema_migrations", "sentinel"})

    def test_initialize_rejects_matching_columns_without_constraints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            with closing(sqlite3.connect(":memory:")) as expected, closing(
                    sqlite3.connect(str(path), isolation_level=None)) as conn:
                initialize(expected)
                tables = expected.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                for (table,) in tables:
                    quoted = '"' + table.replace('"', '""') + '"'
                    columns = expected.execute("PRAGMA table_info({})".format(quoted))
                    definitions = ", ".join('"{}" {}'.format(row[1], row[2] or "BLOB")
                                             for row in columns)
                    conn.execute("CREATE TABLE {} ({})".format(quoted, definitions))
                conn.execute("INSERT INTO schema_migrations VALUES (1, 'fixture')")
            with self.assertRaisesRegex(ValueError, "schema_mismatch"):
                _connect_and_initialize(path)

    def test_initialize_rejects_existing_foreign_key_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            with closing(sqlite3.connect(str(path), isolation_level=None)) as conn:
                initialize(conn)
                conn.execute("PRAGMA foreign_keys=OFF")
                conn.execute("INSERT INTO dependencies VALUES ('orphan', 'missing')")
            with self.assertRaisesRegex(ValueError, "foreign_key_violation"):
                _connect_and_initialize(path)
            with closing(sqlite3.connect(str(path))) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM dependencies").fetchone()[0], 1)

    def test_connect_rejects_database_and_parent_symlinks_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, outside = Path(directory) / "root", Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            cases = []
            for name, target in (("file-internal", root / "internal.sqlite3"),
                                 ("file-external", outside / "external.sqlite3")):
                before = _sentinel_database(target)
                alias = root / (name + ".sqlite3")
                alias.symlink_to(target)
                cases.append((alias, target, before))
            for name, target_dir in (("parent-internal", root / "internal-dir"),
                                     ("parent-external", outside / "external-dir")):
                target = target_dir / "ledger.sqlite3"
                before = _sentinel_database(target)
                alias_dir = root / (name + "-link")
                alias_dir.symlink_to(target_dir, target_is_directory=True)
                cases.append((alias_dir / "ledger.sqlite3", target, before))
            for alias, target, before in cases:
                with self.subTest(alias=alias), self.assertRaises((ValueError, OSError)):
                    _connect_and_initialize(alias)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(before[:16], b"SQLite format 3\x00")
                for path in {alias, target}:
                    self.assertFalse(Path(str(path) + "-wal").exists())
                    self.assertFalse(Path(str(path) + "-shm").exists())

    def test_connect_accepts_empty_fresh_and_valid_reopened_database(self):
        with tempfile.TemporaryDirectory() as directory:
            fresh = Path(directory) / "fresh" / "ledger.sqlite3"
            _connect_and_initialize(fresh)
            _connect_and_initialize(fresh)
            empty = Path(directory) / "empty.sqlite3"
            empty.touch()
            _connect_and_initialize(empty)

    def test_transaction_commits_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory, closing(
                connect(Path(directory) / "ledger.sqlite3")) as conn:
            conn.execute("CREATE TABLE values_log(value TEXT)")
            with transaction(conn):
                conn.execute("INSERT INTO values_log VALUES ('commit')")
            with self.assertRaises(RuntimeError), transaction(conn):
                conn.execute("INSERT INTO values_log VALUES ('rollback')")
                raise RuntimeError("abort")
            self.assertEqual([r[0] for r in conn.execute("SELECT value FROM values_log")], ["commit"])

    def add_task(self, conn):
        conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", (
            "T1", "docs/task.md", "pending", 100, "2026-10-11T00:00:00Z", "a" * 64, "b" * 64, "{}"))

    def add_run(self, conn, run_id, state="claimed", attempt=1):
        conn.execute(
            "INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,worktree,"
            "branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, "T1", attempt, state, "codex", "exec", "{}", "tester", ".worktrees/spec-016",
             "feature/spec-016-ledger", "abc", "a" * 64, "b" * 64, "2026-10-11T00:00:00Z"))

    def drop_active_run_index(self, conn):
        name = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='runs' AND sql IS NOT NULL"
        ).fetchone()[0]
        quoted = '"' + name.replace('"', '""') + '"'
        conn.execute("DROP INDEX {}".format(quoted))
        return name

    def test_active_runs_are_unique_without_a_lease_and_terminal_attempts_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory, closing(
                connect(Path(directory) / "ledger.sqlite3")) as conn:
            initialize(conn)
            self.add_task(conn)
            self.add_run(conn, "R1", "succeeded", 1)
            self.add_run(conn, "R2", "failed", 2)
            self.assertEqual(conn.execute("SELECT count(*) FROM leases").fetchone()[0], 0)
            self.add_run(conn, "R3", "claimed", 3)
            with self.assertRaises(sqlite3.IntegrityError):
                self.add_run(conn, "R4", "running", 4)

    def test_connect_rejects_missing_active_run_index_without_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            with closing(connect(path)) as conn:
                initialize(conn)
                self.add_task(conn)
                self.add_run(conn, "R1", "succeeded", 1)
            with closing(sqlite3.connect(str(path), isolation_level=None)) as raw:
                index_name = self.drop_active_run_index(raw)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "schema_mismatch"):
                _connect_and_initialize(path)
            self.assertEqual(path.read_bytes(), before)
            with closing(sqlite3.connect(str(path))) as raw:
                self.assertEqual(raw.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)
                self.assertEqual(raw.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
                self.assertEqual(raw.execute("SELECT count(*) FROM sqlite_master WHERE name=?",
                                             (index_name,)).fetchone()[0], 0)

    def test_connect_rejects_duplicate_active_runs_from_database_without_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            with closing(connect(path)) as conn:
                initialize(conn)
                self.add_task(conn)
            with closing(sqlite3.connect(str(path), isolation_level=None)) as raw:
                self.drop_active_run_index(raw)
                self.add_run(raw, "R1", "claimed", 1)
                self.add_run(raw, "R2", "running", 2)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "schema_mismatch"):
                _connect_and_initialize(path)
            self.assertEqual(path.read_bytes(), before)
            with closing(sqlite3.connect(str(path))) as raw:
                states = [row[0] for row in raw.execute("SELECT state FROM runs ORDER BY run_id")]
                self.assertEqual(states, ["claimed", "running"])

    def test_lease_uniqueness_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as directory, closing(
                connect(Path(directory) / "ledger.sqlite3")) as conn:
            initialize(conn)
            self.add_task(conn)
            self.add_run(conn, "R1")
            self.add_run(conn, "R2", "succeeded", 2)
            lease = ("T1", "R1", "secret", "now", "now", "later")
            conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)", lease)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)", ("T1", "R2", "other", "n", "n", "l"))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)", ("missing", "missing", "x", "n", "n", "l"))

    def test_import_does_not_write_to_working_directory(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONPATH=str(root))
            result = subprocess.run([sys.executable, "-c", "import scripts.sdd_tasks.store"],
                                    cwd=directory, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
