"""Disposable real-Git/SQLite regression smokes for Task 04."""

import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import closing
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))

from scripts.sdd_tasks import catalog
from scripts.sdd_tasks.catalog import CatalogError, rebuild, status
from scripts.sdd_tasks.store import connect, initialize
from tests.sdd_tasks.test_catalog import _db, _doc, _git, _repo

RUN = "123e4567-e89b-12d3-a456-426614174099"
TABLES = ("schema_migrations", "tasks", "dependencies", "runs", "events", "artifacts", "leases")
GATE = "spec-016.cloud-stage-authorized"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def initialize_worker(path, start, results):
    start.wait()
    try:
        with closing(connect(Path(path))) as conn:
            initialize(conn)
        results.put(("ok", "initialize"))
    except BaseException as exc:
        results.put(("error", repr(exc)))


def rebuild_worker(root, db, start, results):
    start.wait()
    try:
        result = rebuild(Path(db), Path(root))
        results.put(("ok", result.tasks, result.runs))
    except BaseException as exc:
        results.put(("error", repr(exc)))


def race_pair(target, args):
    context = mp.get_context("fork")
    start, results = context.Event(), context.Queue()
    workers = [context.Process(target=target, args=(*args, start, results)) for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    for worker in workers:
        worker.join(30)
        require(worker.exitcode == 0, "worker failed: {}".format(worker.exitcode))
    return [results.get(timeout=5) for _ in workers]


def snapshot(database):
    with closing(connect(database)) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        rows = {table: [tuple(row) for row in conn.execute(
            "SELECT * FROM {} ORDER BY rowid".format(table))] for table in TABLES}
    return mode, rows


def add_run(conn, root, task_id, task_hash, prompt_hash, state):
    base = _git(root, "rev-parse", "HEAD")
    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                  "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (RUN, task_id, 1, state, "codex", "smoke-executor", "{}", "tester",
                  ".worktrees/spec-016", "feature/spec-016-portable-task-ledger", base,
                  task_hash, prompt_hash, "2026-10-11T00:00:00Z"))


def write_gate(root, state="passed", proof=True, raw=None):
    registry = root / "docs/sdd/gate-evidence.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        registry.write_text(raw, encoding="utf-8")
        return
    payload = b"smoke gate proof\n"
    evidence = root / "docs/sdd/gate-proof.txt"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if proof:
        evidence.write_bytes(payload)
    elif evidence.exists():
        evidence.unlink()
    entry = {"gate_id": GATE, "status": state, "evidence": {
        "path": "docs/sdd/gate-proof.txt", "sha256": hashlib.sha256(payload).hexdigest()}}
    registry.write_text(json.dumps({"schema": "sdd-gates/v1", "gates": [entry]}), encoding="utf-8")


def read_status(database):
    with closing(connect(database)) as conn:
        return status(conn)


def fixture(directory, linked=False):
    root, paths, _, task = _repo(directory)
    canonical = root / ".worktrees/spec-016"
    if linked:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        _git(root, "worktree", "add", "--detach", str(canonical), "HEAD")
    return root, canonical, paths, task


def smoke_imports():
    with tempfile.TemporaryDirectory() as temp:
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        code = ("import scripts.sdd_tasks.atomic, scripts.sdd_tasks.catalog, "
                "scripts.sdd_tasks.catalog_status, scripts.sdd_tasks.gates, "
                "scripts.sdd_tasks.documents, scripts.sdd_tasks.locks, "
                "scripts.sdd_tasks.mirrors, scripts.sdd_tasks.newdb_paths, "
                "scripts.sdd_tasks.result_schema, scripts.sdd_tasks.schema_checks, "
                "scripts.sdd_tasks.store, scripts.sdd_tasks.summaries, "
                "scripts.sdd_tasks.summary_import, scripts.sdd_tasks.catalog_publish")
        child = subprocess.run([sys.executable, "-c", code], cwd=temp, env=env,
                               capture_output=True, text=True)
        require(child.returncode == 0, child.stderr)
        require(not list(Path(temp).iterdir()), "module import created runtime files")
    print("PASS import of every Task 04 module has no runtime side effects")


def smoke_gate_status():
    with tempfile.TemporaryDirectory() as temp:
        root, canonical, _, task = fixture(temp, linked=True)
        write_gate(canonical)
        database = _db(root)
        rebuild(database, root)
        eligible = read_status(database)["eligible"]
        require(any(row["task_id"] == task["task_id"] for row in eligible), "passed gate not eligible")
        write_gate(root)
        write_gate(canonical, "failed")
        waiting = read_status(database)["waiting"]
        require(any("gate_unsatisfied:" + GATE in row["reasons"] for row in waiting),
                "stale main pass overrode canonical failure")
        write_gate(canonical, proof=False)
        require(any("gate_unsatisfied:" + GATE in row["reasons"]
                    for row in read_status(database)["waiting"]), "missing proof treated as pass")
        write_gate(canonical, raw='{"schema":"bad","gates":[]}')
        try:
            read_status(database)
        except CatalogError as exc:
            require(exc.code == "gate_evidence_invalid", str(exc))
        else:
            raise AssertionError("invalid gate registry accepted")
        source = canonical / "docs/sdd/plans/016/task-04-fixture.md"
        source.write_text(_doc(dict(task, title="Changed")), encoding="utf-8")
        try:
            read_status(database)
        except CatalogError as exc:
            require(exc.code == "CANONICAL_TASK_HASH_MISMATCH", str(exc))
        else:
            raise AssertionError("canonical Task hash drift accepted")
    print("PASS canonical gate status, proof failures, and Task drift refusal")


def smoke_initialize_race():
    with tempfile.TemporaryDirectory() as temp:
        database = Path(temp) / "race.sqlite3"
        outcomes = race_pair(initialize_worker, (str(database),))
        require(all(item[0] == "ok" for item in outcomes), repr(outcomes))
        with closing(connect(database)) as conn:
            require(conn.execute("SELECT version FROM schema_migrations").fetchone()[0] == 1,
                    "initialize race schema")
    print("PASS concurrent SQLite initialize")


def smoke_rebuild_race():
    with tempfile.TemporaryDirectory() as temp:
        root, _, _, _ = fixture(temp)
        database = _db(root)
        outcomes = race_pair(rebuild_worker, (str(root), str(database)))
        require(all(item == ("ok", 2, 0) for item in outcomes), repr(outcomes))
        inode = database.stat().st_ino
        result = rebuild(database, root)
        require(result.tasks == 2 and database.stat().st_ino == inode, "rebuild publication/idempotence")
    print("PASS concurrent Git rebuild and no-replace publication")


def smoke_active_lease_preserves_wal():
    with tempfile.TemporaryDirectory() as temp:
        root, _, _, task = fixture(temp)
        database = _db(root)
        rebuild(database, root)
        with closing(connect(database)) as conn:
            row = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?",
                               (task["task_id"],)).fetchone()
            add_run(conn, root, task["task_id"], row[0], row[1], "claimed")
            conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                         (task["task_id"], RUN, "token", "now", "now", "2099-01-01T00:00:00Z"))
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)", (RUN, 1, "now", "claimed", "{}"))
        before, inode = snapshot(database), database.stat().st_ino
        try:
            rebuild(database, root)
        except CatalogError as exc:
            require(exc.code == "ACTIVE_LEASE", str(exc))
        else:
            raise AssertionError("active lease did not stop rebuild")
        require(snapshot(database) == before and database.stat().st_ino == inode,
                "active lease rebuild changed existing ledger")
        require(before[0].lower() == "wal", "existing ledger not in WAL mode")
    print("PASS WAL data and lease/event preservation on refused rebuild")


def smoke_running_hash_drift():
    with tempfile.TemporaryDirectory() as temp:
        root, _, paths, task = fixture(temp)
        database = _db(root)
        rebuild(database, root)
        with closing(connect(database)) as conn:
            row = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?",
                               (task["task_id"],)).fetchone()
            add_run(conn, root, task["task_id"], row[0], row[1], "running")
        before, inode = snapshot(database), database.stat().st_ino
        changed = dict(task, priority=task["priority"] - 1)
        paths[task["task_id"]].write_text(_doc(changed), encoding="utf-8")
        try:
            rebuild(database, root)
        except CatalogError as exc:
            require(exc.code == "RUN_HASH_DRIFT", str(exc))
        else:
            raise AssertionError("running hash drift did not stop rebuild")
        require(snapshot(database) == before and database.stat().st_ino == inode,
                "hash drift rebuild changed ledger")
    print("PASS running hash drift abort and DB preservation")


def smoke_bad_task_and_summary():
    with tempfile.TemporaryDirectory() as temp:
        root, _, paths, task = fixture(temp)
        database = _db(root)
        rebuild(database, root)
        before, inode = snapshot(database), database.stat().st_ino
        original = paths[task["task_id"]].read_text(encoding="utf-8")
        bad = original.replace('"schema_version": 1', '"schema_version": true', 1)
        paths[task["task_id"]].write_text(bad, encoding="utf-8")
        try:
            rebuild(database, root)
        except ValueError:
            pass
        else:
            raise AssertionError("bad Task schema accepted")
        require(snapshot(database) == before and database.stat().st_ino == inode,
                "bad Task schema changed DB")
        paths[task["task_id"]].write_text(original, encoding="utf-8")
        summary = root / "docs/sdd/runs/016/task-04/{}.md".format(RUN)
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text("<!-- sdd-run-result:v1:begin -->\n{}\n", encoding="utf-8")
        try:
            rebuild(database, root)
        except ValueError:
            pass
        else:
            raise AssertionError("bad summary accepted")
        require(snapshot(database) == before and database.stat().st_ino == inode,
                "bad summary changed DB")
    print("PASS malformed Task and summary preserve existing DB")


def smoke_raced_database_symlink():
    with tempfile.TemporaryDirectory() as temp:
        root, _, _, _ = fixture(temp)
        database = _db(root)
        database.parent.mkdir(parents=True)
        outside = Path(temp) / "keep.db"
        outside.write_bytes(b"keep outside")
        original = catalog.publish_stage

        def race_target(parent_fd, stage, name):
            os.symlink(str(outside), name, dir_fd=parent_fd)
            return original(parent_fd, stage, name)

        try:
            with patch("scripts.sdd_tasks.catalog.publish_stage", side_effect=race_target):
                rebuild(database, root)
        except CatalogError as exc:
            require(exc.code == "DATABASE_APPEARED", str(exc))
        else:
            raise AssertionError("publication race did not stop")
        require(database.is_symlink() and outside.read_bytes() == b"keep outside",
                "publication followed or replaced raced-in symlink")
    print("PASS raced-in DB symlink not followed or replaced")


def run():
    smoke_imports()
    smoke_gate_status()
    smoke_initialize_race()
    smoke_rebuild_race()
    smoke_active_lease_preserves_wal()
    smoke_running_hash_drift()
    smoke_bad_task_and_summary()
    smoke_raced_database_symlink()


if __name__ == "__main__":
    run()
