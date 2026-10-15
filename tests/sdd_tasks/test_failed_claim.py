import json
import os
import tempfile
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from scripts.sdd_tasks.active_failed_recovery import (
    ActiveFailedRecoveryError,
    load_active_failed_source,
)
from scripts.sdd_tasks.failed_selection import resolve_failed_source
from scripts.sdd_tasks.gates import load_satisfied_gates
from scripts.sdd_tasks.lifecycle_context import load_active_claim
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.validation_runner import run_validations
from scripts.sdd_tasks.workspace import capture_snapshot, snapshot_payload
from tests.sdd_tasks.test_completion_prepare import SOURCE
from tests.sdd_tasks.test_failure_history import _failed_run
from tests.sdd_tasks.test_run_owner import _rows


@contextmanager
def _active_failed_claim(directory):
    with _failed_run(directory) as data:
        root, worktree, task, database, failed = data[:5]
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        owner = current_owner("retry", pid=os.getpid())
        with closing(connect(database)) as conn, maintenance_lock(root):
            selected = resolve_failed_source(conn, failed.run_id, task, root)
            gates = load_satisfied_gates(task, root)
            claim = claim_next(conn, [task], gates, workspace_snapshots={
                task.metadata["task_id"]: selected.snapshot}, ide="codex", owner=owner, now=now)
        if claim is None:
            raise AssertionError("failed partial Task was not claimed")
        yield root, worktree, task, database, failed.run_id, selected, claim


class FailedClaimTests(unittest.TestCase):
    def test_public_partial_claim_rehydrates_and_runs_validations(self):
        with tempfile.TemporaryDirectory() as temp, _active_failed_claim(temp) as data:
            root, _, task, database, failed_id, selected, claim = data
            proof = selected.proof
            self.assertEqual((claim.base_commit, claim.recovery_of),
                             (proof.original_base, failed_id))
            head = capture_snapshot(root, task).head
            self.assertEqual(head, proof.active_claim_tip)
            self.assertNotEqual(head, claim.base_commit)
            self.assertEqual(claim.failed_source, proof)
            with closing(connect(database)) as conn, maintenance_lock(root):
                rows = _rows(conn)
                event = json.loads(conn.execute(
                    "SELECT payload_json FROM events WHERE run_id=? AND event_type='workspace_snapshot'",
                    (claim.run_id,),
                ).fetchone()[0])
                expected = snapshot_payload(selected.snapshot, failed_id)
                self.assertEqual(event, expected)
                active = load_active_failed_source(conn, claim.run_id, task, root)
                live, hydrated, baseline = load_active_claim(conn, claim.run_id, claim.owner, root)
                self.assertEqual((active, hydrated.failed_source, baseline), (proof, proof, selected.snapshot))
                self.assertEqual(live.metadata["task_id"], task.metadata["task_id"])
                self.assertEqual(_rows(conn), rows)

            with maintenance_lock(root):
                commands, receipt = run_validations(task, claim, root, timeout_seconds=20)
            self.assertTrue(receipt["valid"])
            self.assertEqual([(row["status"], row["exit_code"]) for row in commands],
                             [("executed", 0)])
            (claim.worktree_path / SOURCE).write_text("legal active retry change\n", encoding="utf-8")
            with closing(connect(database)) as conn, maintenance_lock(root):
                self.assertEqual(load_active_failed_source(conn, claim.run_id, task, root), proof)
                self.assertEqual(_rows(conn), rows)

    def test_duplicate_claim_is_blocked_and_tampered_source_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, _active_failed_claim(temp) as data:
            root, worktree, task, database, _, selected, claim = data
            with closing(connect(database)) as conn, maintenance_lock(root):
                rows = _rows(conn)
                second = claim_next(conn, [task], load_satisfied_gates(task, root),
                                    workspace_snapshots={task.metadata["task_id"]: selected.snapshot},
                                    ide="codex", owner=current_owner("retry-again", pid=os.getpid()),
                                    now=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
                self.assertIsNone(second)
                self.assertEqual(_rows(conn), rows)

            summary = worktree / selected.proof.excluded_paths[0]
            summary.write_text("forged source summary\n", encoding="utf-8")
            with closing(connect(database)) as conn, maintenance_lock(root), \
                    self.assertRaises(ActiveFailedRecoveryError):
                load_active_failed_source(conn, claim.run_id, task, root)


if __name__ == "__main__":
    unittest.main()
