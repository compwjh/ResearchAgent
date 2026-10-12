import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.gates import GateEvidenceError, load_satisfied_gates
from tests.sdd_tasks._fixtures import task_markdown

GATE = "spec-016.cloud-stage-authorized"
REGISTRY = "docs/sdd/gate-evidence.json"
PROOF = "docs/sdd/gate-proof.txt"


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _repo(directory, linked=True):
    main = Path(directory) / "main"
    main.mkdir()
    path = ".worktrees/spec-016" if linked else ".worktrees/unregistered"
    task_file = main / "docs/sdd/plans/016/task-04-fixture.md"
    task_file.parent.mkdir(parents=True)
    task_file.write_text("# Fixture\n> 当前状态：`待执行`\n\n" + task_markdown(), encoding="utf-8")
    _git(main, "init", "-q")
    _git(main, "config", "user.name", "Fixture")
    _git(main, "config", "user.email", "fixture@example.invalid")
    _git(main, "add", ".")
    _git(main, "commit", "-qm", "fixture")
    canonical = main / path
    if linked:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        _git(main, "worktree", "add", "--detach", str(canonical), "HEAD")
    return main, canonical, parse_task(task_file)


def _entry(status="passed", digest=None, path=PROOF, gate=GATE):
    return {"gate_id": gate, "status": status,
            "evidence": {"path": path, "sha256": digest or "0" * 64}}


def _write(root, entries, proof=b"proof\n"):
    target = root / PROOF
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(proof)
    entries = [dict(item) for item in entries]
    for item in entries:
        item["evidence"] = dict(item["evidence"])
        if item["evidence"]["path"] == PROOF and item["evidence"]["sha256"] == "0" * 64:
            item["evidence"]["sha256"] = hashlib.sha256(proof).hexdigest()
    registry = root / REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"schema": "sdd-gates/v1", "gates": entries}), encoding="utf-8")


class GateTests(unittest.TestCase):
    def test_only_canonical_registered_view_can_satisfy(self):
        with tempfile.TemporaryDirectory() as td:
            main, canonical, task = _repo(td)
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [])
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [_entry("pending")])
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [_entry("failed")])
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [_entry(digest="f" * 64)])
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [_entry(gate="spec-016.other-gate")])
            self.assertEqual(load_satisfied_gates(task, main), set())
            (canonical / PROOF).unlink()
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(main, [_entry()])
            _write(canonical, [_entry("failed")])
            self.assertEqual(load_satisfied_gates(task, main), set())
            _write(canonical, [_entry()])
            self.assertEqual(load_satisfied_gates(task, main), {GATE})

    def test_unregistered_canonical_view_does_not_default_to_pass(self):
        with tempfile.TemporaryDirectory() as td:
            main, _, task = _repo(td, linked=False)
            _write(main, [_entry()])
            with self.assertRaises(GateEvidenceError) as caught:
                load_satisfied_gates(task, main)
            self.assertEqual(caught.exception.code, "CANONICAL_WORKTREE_UNREGISTERED")

    def test_missing_worktree_or_task_and_hash_drift_raise_stable_errors(self):
        with tempfile.TemporaryDirectory() as td:
            main, canonical, task = _repo(td)
            shutil.rmtree(canonical)
            with self.assertRaises(GateEvidenceError) as caught:
                load_satisfied_gates(task, main)
            self.assertEqual(caught.exception.code, "CANONICAL_WORKTREE_MISSING")
        for mode, code in (("missing", "CANONICAL_TASK_MISSING"),
                           ("changed", "CANONICAL_TASK_HASH_MISMATCH")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as td:
                main, canonical, task = _repo(td)
                source = canonical / "docs/sdd/plans/016/task-04-fixture.md"
                if mode == "missing":
                    source.unlink()
                else:
                    source.write_text("# Fixture\n> 当前状态：`待执行`\n\n" +
                                      task_markdown({"title": "Changed"}), encoding="utf-8")
                with self.assertRaises(GateEvidenceError) as caught:
                    load_satisfied_gates(task, main)
                self.assertEqual(caught.exception.code, code)

    def test_malformed_schema_duplicate_keys_and_gate_ids_fail_closed(self):
        invalid = (
            '{"schema":"sdd-gates/v1","gates":[],"extra":0}',
            '{"schema":"sdd-gates/v1","schema":"sdd-gates/v1","gates":[]}',
        )
        for raw in invalid:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as td:
                main, canonical, task = _repo(td)
                target = canonical / REGISTRY
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(raw, encoding="utf-8")
                with self.assertRaises(GateEvidenceError) as caught:
                    load_satisfied_gates(task, main)
                self.assertEqual(caught.exception.code, "gate_evidence_invalid")
        with tempfile.TemporaryDirectory() as td:
            main, canonical, task = _repo(td)
            _write(canonical, [_entry(), _entry()])
            with self.assertRaisesRegex(GateEvidenceError, "gate_evidence_invalid"):
                load_satisfied_gates(task, main)

    def test_cross_spec_gate_and_unknown_fields_are_invalid(self):
        cases = (_entry(gate="spec-017.cloud-stage-authorized"),
                 _entry(path="../outside"), _entry(digest="bad"), dict(_entry(), extra="no"))
        for item in cases:
            with self.subTest(item=item), tempfile.TemporaryDirectory() as td:
                main, canonical, task = _repo(td)
                _write(canonical, [item])
                with self.assertRaisesRegex(GateEvidenceError, "gate_evidence_invalid"):
                    load_satisfied_gates(task, main)

    def test_registry_and_evidence_symlinks_are_rejected_without_following(self):
        for registry_link in (True, False):
            for internal in (True, False):
                with self.subTest(registry_link=registry_link, internal=internal), tempfile.TemporaryDirectory() as td:
                    main, canonical, task = _repo(td)
                    external = canonical / "inside.json" if internal else Path(td) / "outside.json"
                    external.write_text("untouched", encoding="utf-8")
                    if registry_link:
                        target = canonical / REGISTRY
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.symlink_to(external)
                    else:
                        proof = canonical / PROOF
                        proof.parent.mkdir(parents=True, exist_ok=True)
                        proof.symlink_to(external)
                        registry = canonical / REGISTRY
                        registry.parent.mkdir(parents=True, exist_ok=True)
                        registry.write_text(json.dumps({"schema": "sdd-gates/v1", "gates": [_entry()]}), encoding="utf-8")
                    with self.assertRaisesRegex(GateEvidenceError, "gate_evidence_invalid"):
                        load_satisfied_gates(task, main)
                    self.assertEqual(external.read_text(encoding="utf-8"), "untouched")


if __name__ == "__main__":
    unittest.main()
