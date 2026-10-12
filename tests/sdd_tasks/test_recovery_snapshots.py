import json
import subprocess
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.recovery_snapshots import RecoverySnapshotError, load_recovery_snapshot
from scripts.sdd_tasks.store import connect, initialize
from scripts.sdd_tasks.workspace import capture_snapshot, snapshot_payload
from tests.sdd_tasks._fixtures import TASK_PATH, task_markdown

_BRANCH = "feature/spec-016-portable-task-ledger"
_TOKEN = "private-owner-token-for-fixture"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def _fixture(directory):
    root = Path(directory) / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    (root / ".gitignore").write_text(".worktrees/\n.sdd/runtime/\n", encoding="utf-8")
    (root / TASK_PATH).parent.mkdir(parents=True)
    (root / TASK_PATH).write_text(task_markdown(), encoding="utf-8")
    for folder in ("scripts/sdd_tasks", "tests/sdd_tasks"):
        (root / folder).mkdir(parents=True)
        (root / folder / "seed.txt").write_text("before\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "recovery snapshot fixture")
    base = _git(root, "rev-parse", "HEAD")
    worktree = root / ".worktrees/spec-016"
    worktree.parent.mkdir()
    _git(root, "worktree", "add", "-qb", _BRANCH, str(worktree), base)
    task = parse_task(worktree / TASK_PATH)
    before = capture_snapshot(root, task)
    db = connect(root / ".sdd/runtime/task-ledger.sqlite3")
    initialize(db)
    run_id = str(uuid.uuid4())
    owner = json.dumps({"executor_id": "exec", "host_id": "host", "pid": 123,
                        "process_started_at": "linux:boot:123", "token": _TOKEN},
                       sort_keys=True, separators=(",", ":"))
    meta = task.metadata
    db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", (meta["task_id"], TASK_PATH.as_posix(),
               "pending", 10, "2026-10-11T00:00:00Z", task.task_hash, task.prompt_hash,
               json.dumps(meta, sort_keys=True)))
    db.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (run_id, meta["task_id"], 1, "claimed", "codex", "exec", owner, meta["agent_role"],
                meta["worktree"]["path"], _BRANCH, base, task.task_hash, task.prompt_hash,
                "2026-10-11T00:00:00Z"))
    payload = json.dumps(snapshot_payload(before), sort_keys=True, separators=(",", ":"))
    db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
               (run_id, 1, "2026-10-11T00:00:00Z", "workspace_snapshot", payload))
    return root, worktree, task, before, db, run_id


def _rows(conn):
    return {table: tuple(tuple(row) for row in conn.execute("SELECT * FROM " + table))
            for table in ("tasks", "runs", "events", "leases")}


def _chain_run(conn, task, snapshot, run_id, *, state="abandoned", source=None, claim=True):
    meta = task.metadata
    owner = json.dumps({"executor_id": "exec", "host_id": "host", "pid": 123,
                        "process_started_at": "linux:boot:123", "token": _TOKEN},
                       sort_keys=True, separators=(",", ":"))
    conn.execute("INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
                 "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (run_id, meta["task_id"], 1, state, "codex", "exec", owner, meta["agent_role"],
                  meta["worktree"]["path"], _BRANCH, snapshot.head, task.task_hash, task.prompt_hash,
                  "2026-10-11T00:00:00Z"))
    payload = json.dumps(snapshot_payload(snapshot, source), sort_keys=True, separators=(",", ":"))
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 (run_id, 1, "2026-10-11T00:00:00Z", "workspace_snapshot", payload))
    if source is not None and claim:
        claim_data = json.dumps({"schema": "sdd-recovery-claim/v1", "recovery_of": source},
                                sort_keys=True, separators=(",", ":"))
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                     (run_id, 2, "2026-10-11T00:00:00Z", "recovery_claim", claim_data))


class RecoverySnapshotTests(unittest.TestCase):
    def test_load_returns_original_before_snapshot_after_allowed_partial_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db, run_id = _fixture(temp)
            with closing(db):
                original = before.allowed_hashes["tests/sdd_tasks/seed.txt"]
                (worktree / "tests/sdd_tasks/seed.txt").write_text("partial\n", encoding="utf-8")
                loaded = load_recovery_snapshot(db, run_id, task, root)
                self.assertEqual(loaded, before)
                self.assertEqual(loaded.allowed_hashes["tests/sdd_tasks/seed.txt"], original)
                self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "partial\n")
                self.assertNotIn(_TOKEN, repr(loaded))

    def test_canonical_task_drift_and_dirty_original_baseline_are_rejected_read_only(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, _, db, run_id = _fixture(temp)
                with closing(db):
                    event = db.execute("SELECT payload_json FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
                    if dirty:
                        payload = json.loads(event)
                        payload["snapshot"]["status_records"] = [" M tests/sdd_tasks/seed.txt"]
                        db.execute("UPDATE events SET payload_json=? WHERE run_id=?",
                                   (json.dumps(payload, sort_keys=True), run_id))
                        expected = "RECOVERY_BASELINE_DIRTY"
                    else:
                        text = task.path.read_text(encoding="utf-8")
                        changed = text.replace("Implement the task ledger", "Altered task title")
                        self.assertNotEqual(text, changed)
                        task.path.write_text(changed, encoding="utf-8")
                        expected = "RECOVERY_TASK_MISMATCH"
                    db_before, file_before = _rows(db), task.path.read_bytes()
                    with self.assertRaises(RecoverySnapshotError) as error:
                        load_recovery_snapshot(db, run_id, task, root)
                    self.assertEqual(error.exception.code, expected)
                    self.assertEqual(_rows(db), db_before)
                    self.assertEqual(task.path.read_bytes(), file_before)
                    self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "before\n")

    def test_valid_two_run_chain_returns_exact_original_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db, first = _fixture(temp)
            with closing(db):
                db.execute("UPDATE runs SET state='abandoned' WHERE run_id=?", (first,))
                second = str(uuid.uuid4())
                _chain_run(db, task, before, second, state="claimed", source=first)
                (worktree / "tests/sdd_tasks/seed.txt").write_text("partial\n", encoding="utf-8")
                rows = _rows(db)
                self.assertEqual(load_recovery_snapshot(db, second, task, root), before)
                self.assertEqual(_rows(db), rows)
                self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "partial\n")

    def test_missing_or_malformed_recovery_source_and_claim_fail_read_only(self):
        cases = (("missing_parent", "absent", True, "RECOVERY_SOURCE_INVALID"),
                 ("bad_source", "not-a-uuid", True, "RECOVERY_EVENT_INVALID"),
                 ("missing_claim", "parent", False, "RECOVERY_EVENT_INVALID"),
                 ("bad_claim", "parent", True, "RECOVERY_EVENT_INVALID"))
        for case, source_kind, has_claim, expected in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, before, db, first = _fixture(temp)
                with closing(db):
                    db.execute("UPDATE runs SET state='abandoned' WHERE run_id=?", (first,))
                    source = str(uuid.uuid4()) if source_kind in {"absent", "parent"} else source_kind
                    if source_kind == "parent":
                        _chain_run(db, task, before, source, source=None)
                    current = str(uuid.uuid4())
                    _chain_run(db, task, before, current, state="claimed", source=source,
                               claim=has_claim)
                    if case == "bad_claim":
                        db.execute("UPDATE events SET payload_json='{}' WHERE run_id=? AND event_type='recovery_claim'",
                                   (current,))
                    rows = _rows(db)
                    with self.assertRaises(RecoverySnapshotError) as error:
                        load_recovery_snapshot(db, current, task, root)
                    self.assertEqual(error.exception.code, expected)
                    self.assertEqual(_rows(db), rows)
                    self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "before\n")

    def test_snapshot_hash_keys_reject_escape_and_symlink_components(self):
        for kind in ("escape", "symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root, worktree, task, _, db, run_id = _fixture(temp)
                with closing(db):
                    row = db.execute("SELECT payload_json FROM events WHERE run_id=?", (run_id,)).fetchone()
                    payload = json.loads(row[0])
                    if kind == "symlink":
                        key = "tests/sdd_tasks/link/seed.txt"
                        (worktree / "tests/sdd_tasks/link").symlink_to(
                            worktree / "scripts/sdd_tasks", target_is_directory=True)
                    else:
                        key = "../outside.txt"
                    payload["snapshot"]["allowed_hashes"][key] = "f" * 64
                    db.execute("UPDATE events SET payload_json=? WHERE run_id=?",
                               (json.dumps(payload, sort_keys=True), run_id))
                    rows = _rows(db)
                    with self.assertRaises(RecoverySnapshotError) as error:
                        load_recovery_snapshot(db, run_id, task, root)
                    self.assertEqual(error.exception.code, "RECOVERY_SNAPSHOT_INVALID")
                    self.assertEqual(_rows(db), rows)
                    self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "before\n")

    def test_three_run_recovery_cycle_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root, worktree, task, before, db, first = _fixture(temp)
            with closing(db):
                second, third = str(uuid.uuid4()), str(uuid.uuid4())
                db.execute("UPDATE runs SET state='abandoned' WHERE run_id=?", (first,))
                _chain_run(db, task, before, second, source=first)
                _chain_run(db, task, before, third, source=second)
                db.execute("UPDATE events SET payload_json=? WHERE run_id=? AND event_type='workspace_snapshot'",
                           (json.dumps(snapshot_payload(before, third), sort_keys=True,
                                       separators=(",", ":")), first))
                cycle_claim = json.dumps({"schema": "sdd-recovery-claim/v1", "recovery_of": third},
                                         sort_keys=True, separators=(",", ":"))
                db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                           (first, 2, "2026-10-11T00:00:00Z", "recovery_claim", cycle_claim))
                rows = _rows(db)
                with self.assertRaises(RecoverySnapshotError) as error:
                    load_recovery_snapshot(db, third, task, root)
                self.assertEqual(error.exception.code, "RECOVERY_SOURCE_CYCLE")
                self.assertEqual(_rows(db), rows)
                self.assertEqual((worktree / "tests/sdd_tasks/seed.txt").read_text(encoding="utf-8"), "before\n")

    def test_missing_event_and_snapshot_identity_or_schema_mismatches_fail_closed(self):
        cases = (
            ("missing", "", "RECOVERY_EVENT_INVALID"),
            ("task_hash", "c" * 64, "RECOVERY_SNAPSHOT_MISMATCH"),
            ("prompt_hash", "d" * 64, "RECOVERY_SNAPSHOT_MISMATCH"),
            ("head", "e" * 40, "RECOVERY_BASE_MISMATCH"),
            ("branch", "feature/other", "RECOVERY_SNAPSHOT_MISMATCH"),
            ("common_dir", "/other/common", "RECOVERY_SNAPSHOT_MISMATCH"),
            ("worktree_path", "/other/worktree", "RECOVERY_SNAPSHOT_MISMATCH"),
            ("repo_root", "/other/root", "RECOVERY_SNAPSHOT_MISMATCH"),
            ("task_id", "spec-999-task-01", "RECOVERY_SNAPSHOT_MISMATCH"),
            ("unknown_field", "unexpected", "RECOVERY_SNAPSHOT_INVALID"),
        )
        for field, value, code in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root, _, task, _, db, run_id = _fixture(temp)
                with closing(db):
                    if field == "missing":
                        db.execute("DELETE FROM events WHERE run_id=?", (run_id,))
                    else:
                        row = db.execute("SELECT payload_json FROM events WHERE run_id=?", (run_id,)).fetchone()
                        payload = json.loads(row[0])
                        if field == "unknown_field":
                            payload["snapshot"][field] = value
                        else:
                            payload["snapshot"][field] = value
                        db.execute("UPDATE events SET payload_json=? WHERE run_id=?",
                                   (json.dumps(payload, sort_keys=True), run_id))
                    with self.assertRaises(RecoverySnapshotError) as error:
                        load_recovery_snapshot(db, run_id, task, root)
                    self.assertEqual(error.exception.code, code)


if __name__ == "__main__":
    unittest.main()
