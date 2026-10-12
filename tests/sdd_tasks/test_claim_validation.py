import hashlib
import json
import sqlite3
import tempfile
import unittest

from scripts.sdd_tasks.claim_validation import validate_candidate
from scripts.sdd_tasks.claims import ClaimError
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_catalog import _git, _repo

GATE = "spec-016.cloud-stage-authorized"


def _candidate(directory):
    root, paths, _, meta = _repo(directory)
    allowed = root / "scripts/sdd_tasks"
    allowed.mkdir(parents=True)
    (allowed / "allowed.txt").write_text("baseline\n", encoding="utf-8")
    with (root / ".gitignore").open("a", encoding="utf-8") as ignore:
        ignore.write("scripts/sdd_tasks/ignored.txt\n")
    proof = b"gate proof\n"
    proof_path = root / "docs/sdd/gate-proof.txt"
    proof_path.write_bytes(proof)
    entry = {"gate_id": GATE, "status": "passed", "evidence": {
        "path": "docs/sdd/gate-proof.txt", "sha256": hashlib.sha256(proof).hexdigest()}}
    registry = root / "docs/sdd/gate-evidence.json"
    registry.write_text(json.dumps({"schema": "sdd-gates/v1", "gates": [entry]}), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "canonical fixture inputs")
    canonical = root / meta["worktree"]["path"]
    canonical.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-b", meta["worktree"]["branch"], str(canonical), "HEAD")
    ignored = canonical / "scripts/sdd_tasks/ignored.txt"
    ignored.write_text("baseline\n", encoding="utf-8")
    task = parse_task(paths[meta["task_id"]])
    snapshot = capture_snapshot(root, task)
    db = root / ".sdd/runtime/task-ledger.sqlite3"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE marker (value TEXT)")
        conn.execute("INSERT INTO marker VALUES ('unchanged')")
    return root, canonical, task, snapshot, db, db.read_bytes()


class ClaimValidationTests(unittest.TestCase):
    def test_clean_snapshot_returns_canonical_task_and_intersected_gates(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, snapshot, _, _ = _candidate(td)
            live, gates, state = validate_candidate(task, snapshot, root, {GATE, "spec-016.stale"})
            self.assertEqual((live.task_hash, live.path.parent), (task.task_hash, canonical / "docs/sdd/plans/016"))
            self.assertEqual(gates, {GATE})
            self.assertEqual(state, "已确认")

    def test_current_unrelated_or_allowed_dirty_file_rejects_snapshot(self):
        for relative in ("unrelated.txt", "scripts/sdd_tasks/ignored.txt"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as td:
                root, canonical, task, snapshot, _, _ = _candidate(td)
                target = canonical / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("changed\n", encoding="utf-8")
                if relative.endswith("ignored.txt"):
                    self.assertEqual(snapshot.status_records, ())
                    self.assertIn(relative, snapshot.allowed_hashes)
                with self.assertRaises(ClaimError) as caught:
                    validate_candidate(task, snapshot, root, {GATE})
                self.assertEqual(caught.exception.code, "CLAIM_SNAPSHOT_STALE")

    def test_definition_mirror_spec_and_gate_drift_reject_without_db_writes(self):
        cases = (("task", "CLAIM_TASK_HASH_STALE"), ("mirror", "TASK_MIRROR_INVALID"),
                 ("spec", "SPEC_STATUS_INVALID"), ("gate", "gate_evidence_invalid"))
        for change, code in cases:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as td:
                root, canonical, task, snapshot, db, before = _candidate(td)
                doc = canonical / "docs/sdd/plans/016/task-04-fixture.md"
                if change == "task":
                    doc.write_text("# Changed\n> 当前状态：`待执行`\n\n" +
                                   task_markdown({"title": "Changed"}), encoding="utf-8")
                elif change == "mirror":
                    path = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
                    path.write_text(path.read_text(encoding="utf-8").replace("| 待执行 |", "| 完成 |"),
                                    encoding="utf-8")
                elif change == "spec":
                    path = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
                    path.write_text(path.read_text(encoding="utf-8").replace("已确认", "未知"),
                                    encoding="utf-8")
                else:
                    (canonical / "docs/sdd/gate-evidence.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(ClaimError) as caught:
                    validate_candidate(task, snapshot, root, {GATE})
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
