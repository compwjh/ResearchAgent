import json
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace

from scripts.sdd_tasks.completion_service import fail_run
from scripts.sdd_tasks.failed_recovery import (
    FailedRecoveryError,
    compare_failed_observation_current,
    load_failed_recovery_source,
)
from scripts.sdd_tasks.failed_workspace import compare_verified_failed_workspace
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot
from scripts.sdd_tasks.workspace_observation import _load_failed_run_baseline
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_completion_service import _draft
from tests.sdd_tasks.test_failure_history import _failed_run, _git, _repo_state
from tests.sdd_tasks.test_run_owner import _rows


def _append_decisions(conn, run_id, payloads):
    """Inject public event shapes for defensive tests, without pretending a retry occurred."""
    ended = conn.execute("SELECT ended_at FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]
    sequence = conn.execute("SELECT max(sequence) FROM events WHERE run_id=?", (run_id,)).fetchone()[0] + 1
    for action, decision in payloads:
        payload = {"schema": "sdd-run-recovery/v1", "action": action, "decision": decision}
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                     (run_id, sequence, ended, "recovery_decision", json.dumps(payload)))
        sequence += 1
    conn.commit()


class FailedRecoveryTests(unittest.TestCase):
    def test_latest_failure_loads_original_baseline_and_partial_decision_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim, _, parent_tip, _, _ = data
            git_before = _repo_state(worktree)
            with closing(connect(database)) as conn:
                rows_before = _rows(conn)
                baseline = _load_failed_run_baseline(conn, claim.run_id, task, root)
                proof = load_failed_recovery_source(conn, claim.run_id, task, root)
                self.assertEqual(_rows(conn), rows_before)
            self.assertEqual(_repo_state(worktree), git_before)
            self.assertEqual(proof.baseline, baseline)
            self.assertEqual((proof.baseline.head, proof.observation.head), (parent_tip, parent_tip))
            self.assertEqual(proof.history.observation_tips, ((claim.run_id, parent_tip),))
            self.assertNotEqual(proof.history.current_tip, proof.baseline.head)
            decision = compare_verified_failed_workspace(proof, task)
            self.assertEqual((decision.kind, decision.changed_paths), ("partial", (SOURCE,)))

    def test_source_changed_after_terminal_observation_is_rejected_read_only(self):
        for staged in (False, True):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
                root, worktree, task, database, claim, source = data[:6]
                source.write_text("later source change\n", encoding="utf-8")
                if staged:
                    _git(worktree, "add", SOURCE)
                with closing(connect(database)) as conn:
                    rows_before, git_before = _rows(conn), _repo_state(worktree)
                    with self.assertRaises(FailedRecoveryError) as caught:
                        load_failed_recovery_source(conn, claim.run_id, task, root)
                    self.assertEqual(str(caught.exception), "FAILED_RECOVERY_WORKSPACE_CHANGED")
                    self.assertEqual(_rows(conn), rows_before)
                self.assertEqual(_repo_state(worktree), git_before)

    def test_failed_run_without_source_changes_loads_unchanged(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, _, _, claim = state
            with closing(connect(database)) as conn, maintenance_lock(root):
                result = fail_run(conn, root, claim.run_id, claim.owner.executor_id,
                                  claim.owner.pid, json.dumps(_draft(
                                      task, claim, outcome="failed", changed_files=[])))
            self.assertEqual(result["outcome"], "failed")
            git_before = _repo_state(worktree)
            with closing(connect(database)) as conn:
                rows_before = _rows(conn)
                proof = load_failed_recovery_source(conn, claim.run_id, task, root)
                self.assertEqual(_rows(conn), rows_before)
            self.assertEqual(_repo_state(worktree), git_before)
            self.assertEqual(proof.baseline.head, proof.observation.head)
            self.assertNotEqual(proof.history.current_tip, proof.baseline.head)
            decision = compare_verified_failed_workspace(proof, task)
            self.assertEqual((decision.kind, decision.changed_paths), ("unchanged", ()))

    def test_current_comparison_rejects_forged_identity_and_active_head(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, _, task, database, claim = data[:5]
            with closing(connect(database)) as conn:
                proof = load_failed_recovery_source(conn, claim.run_id, task, root)
            current = capture_snapshot(root, task)
            self.assertEqual(compare_failed_observation_current(proof, current, task).kind, "unchanged")
            forged = (replace(current, branch="forged-branch"),
                      replace(current, head=proof.observation.head))
            for snapshot in forged:
                with self.subTest(snapshot=snapshot), self.assertRaises(FailedRecoveryError):
                    compare_failed_observation_current(proof, snapshot, task)

    def test_stored_decision_accepts_match_and_rejects_mismatch_or_duplicate(self):
        cases = (
            ("match", (("preserved_for_recovery", "partial"),)),
            ("mismatch", (("requeued", "unchanged"),)),
            ("duplicate", (("preserved_for_recovery", "partial"),) * 2),
        )
        for case, payloads in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
                root, worktree, task, database, claim = data[:5]
                git_before = _repo_state(worktree)
                with closing(connect(database)) as conn:
                    _append_decisions(conn, claim.run_id, payloads)
                    rows_before = _rows(conn)
                    if case == "match":
                        proof = load_failed_recovery_source(conn, claim.run_id, task, root)
                        self.assertEqual(compare_verified_failed_workspace(proof, task).kind, "partial")
                    elif case == "mismatch":
                        with self.assertRaises(FailedRecoveryError) as caught:
                            load_failed_recovery_source(conn, claim.run_id, task, root)
                        self.assertEqual(str(caught.exception), "FAILED_RECOVERY_DECISION_MISMATCH")
                    else:
                        with self.assertRaises(FailedRecoveryError) as caught:
                            load_failed_recovery_source(conn, claim.run_id, task, root)
                        self.assertEqual(str(caught.exception), "FAILED_RECOVERY_SOURCE_INVALID")
                    self.assertEqual(_rows(conn), rows_before)
                self.assertEqual(_repo_state(worktree), git_before)
