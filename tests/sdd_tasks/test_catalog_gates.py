import hashlib
import json
import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.catalog import CatalogError, rebuild, status
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_catalog import _db, _git, _repo

GATE = "spec-016.cloud-stage-authorized"
PROOF = "docs/sdd/gate-proof.txt"
TASK = "spec-016-task-04"


def _linked_repo(directory):
    root, _, _, _ = _repo(directory)
    canonical = root / ".worktrees/spec-016"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "--detach", str(canonical), "HEAD")
    return root, canonical


def _write_gate(root, state="passed", proof=True, raw=None):
    registry = root / "docs/sdd/gate-evidence.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        registry.write_text(raw, encoding="utf-8")
        return
    data = b"gate proof\n"
    if proof:
        target = root / PROOF
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    entry = {"gate_id": GATE, "status": state, "evidence": {
        "path": PROOF, "sha256": hashlib.sha256(data).hexdigest()}}
    registry.write_text(json.dumps({"schema": "sdd-gates/v1", "gates": [entry]}), encoding="utf-8")


def _status(db):
    with closing(connect(db)) as conn:
        return status(conn)


def _item(rows, task_id=TASK):
    return next(item for item in rows if item["task_id"] == task_id)


class CatalogGateTests(unittest.TestCase):
    def test_passed_canonical_evidence_makes_pending_task_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical = _linked_repo(td)
            _write_gate(canonical)
            db = _db(root)
            rebuild(db, root)
            self.assertEqual(_item(_status(db)["eligible"])["reasons"], [])

    def test_failed_or_missing_proof_keeps_task_waiting(self):
        for state, proof in (("failed", True), ("passed", False)):
            with self.subTest(state=state, proof=proof), tempfile.TemporaryDirectory() as td:
                root, canonical = _linked_repo(td)
                _write_gate(canonical, state, proof)
                db = _db(root)
                rebuild(db, root)
                item = _item(_status(db)["waiting"])
                self.assertIn("gate_unsatisfied:" + GATE, item["reasons"])

    def test_stale_main_pass_cannot_override_canonical_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical = _linked_repo(td)
            _write_gate(root)
            _write_gate(canonical, "failed")
            db = _db(root)
            rebuild(db, root)
            self.assertIn("gate_unsatisfied:" + GATE, _item(_status(db)["waiting"])["reasons"])

    def test_invalid_registry_is_a_catalog_error(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical = _linked_repo(td)
            _write_gate(canonical, raw='{"schema":"bad","gates":[]}')
            db = _db(root)
            rebuild(db, root)
            with self.assertRaises(CatalogError) as caught:
                _status(db)
            self.assertEqual(caught.exception.code, "gate_evidence_invalid")

    def test_canonical_task_hash_drift_is_a_catalog_error(self):
        from tests.sdd_tasks._fixtures import task_markdown

        with tempfile.TemporaryDirectory() as td:
            root, canonical = _linked_repo(td)
            _write_gate(canonical)
            db = _db(root)
            rebuild(db, root)
            source = canonical / "docs/sdd/plans/016/task-04-fixture.md"
            source.write_text("# Fixture\n> 当前状态：`待执行`\n\n" +
                              task_markdown({"title": "Changed"}), encoding="utf-8")
            with self.assertRaises(CatalogError) as caught:
                _status(db)
            self.assertEqual(caught.exception.code, "CANONICAL_TASK_HASH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
