import subprocess
import tempfile
import unittest
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import replace

from scripts.sdd_tasks.active_failed_recovery import compare_active_failed_workspace
from scripts.sdd_tasks.failed_recovery import load_failed_recovery_source
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks.test_completion_prepare import SOURCE
from tests.sdd_tasks.test_failure_history import _failed_run


@contextmanager
def _active_source(directory):
    with _failed_run(directory) as data:
        main, worktree, task, database, claim, source = data[:6]
        with closing(connect(database)) as conn:
            proof = load_failed_recovery_source(conn, claim.run_id, task, main)
        yield main, worktree, task, source, proof


class ActiveFailedWorkspaceTests(unittest.TestCase):
    def test_active_changes_compare_to_original_baseline_and_restore_to_unchanged(self):
        with tempfile.TemporaryDirectory() as temp, _active_source(temp) as data:
            main, worktree, task, source, proof = data
            current = capture_snapshot(main, task)
            self.assertEqual(current.head, proof.active_claim_tip)
            decision = compare_active_failed_workspace(proof, current, task)
            self.assertEqual((decision.kind, decision.changed_paths), ("partial", (SOURCE,)))

            source.write_text("valid active retry source\n", encoding="utf-8")
            current = capture_snapshot(main, task)
            decision = compare_active_failed_workspace(proof, current, task)
            self.assertEqual((decision.kind, decision.changed_paths), ("partial", (SOURCE,)))

            baseline = subprocess.check_output(
                ["git", "-C", str(worktree), "show", proof.original_base + ":" + SOURCE]
            )
            source.write_bytes(baseline)
            current = capture_snapshot(main, task)
            decision = compare_active_failed_workspace(proof, current, task)
            self.assertEqual((decision.kind, decision.changed_paths), ("unchanged", ()))

    def test_new_out_of_scope_file_is_reported(self):
        with tempfile.TemporaryDirectory() as temp, _active_source(temp) as data:
            main, worktree, task, _, proof = data
            (worktree / "outside.txt").write_text("outside allowed roots\n", encoding="utf-8")
            decision = compare_active_failed_workspace(proof, capture_snapshot(main, task), task)
            self.assertEqual((decision.kind, decision.changed_paths, decision.out_of_scope_paths),
                             ("out_of_scope", ("outside.txt", SOURCE), ("outside.txt",)))

    def test_forged_head_branch_or_proof_conflicts_without_mutating_inputs(self):
        with tempfile.TemporaryDirectory() as temp, _active_source(temp) as data:
            main, _, task, _, proof = data
            current = capture_snapshot(main, task)
            before = deepcopy((task.metadata, proof, current))
            forged = (
                replace(current, head="f" * 40),
                replace(current, branch="forged-branch"),
            )
            forged_proof = replace(proof, allowed_roots=("outside",))
            for snapshot, candidate in ((forged[0], proof), (forged[1], proof),
                                        (current, forged_proof)):
                with self.subTest(snapshot=snapshot, proof=candidate):
                    self.assertEqual(compare_active_failed_workspace(candidate, snapshot, task).kind,
                                     "conflict")
            self.assertEqual((task.metadata, proof, current), before)
