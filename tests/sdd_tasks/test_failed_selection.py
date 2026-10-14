import json
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace

from scripts.sdd_tasks.completion_service import fail_run
from scripts.sdd_tasks.failed_recovery import FailedRecoveryError
from scripts.sdd_tasks.failed_selection import resolve_failed_source
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import WorkspaceError
from scripts.sdd_tasks.workspace_prepare import prepare_failed_worktree
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_completion_service import _draft
from tests.sdd_tasks.test_failure_history import _failed_run, _git, _repo_state
from tests.sdd_tasks.test_run_owner import _rows


class FailedSelectionTests(unittest.TestCase):
    def test_partial_selection_and_prepare_keep_original_baseline_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim, source, parent_tip = data[:7]
            with closing(connect(database)) as conn:
                rows, git_before = _rows(conn), _repo_state(worktree)
                selected = resolve_failed_source(conn, claim.run_id, task, root)
                prepared = prepare_failed_worktree(root, task, selected)
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_before)
            self.assertEqual((selected.mode, selected.decision.kind,
                              selected.decision.changed_paths), ("partial", "partial", (SOURCE,)))
            self.assertEqual((selected.base_commit, selected.recovery_of), (parent_tip, claim.run_id))
            self.assertIs(selected.snapshot, selected.proof.baseline)
            self.assertIs(prepared, selected.proof.baseline)
            self.assertEqual((prepared.head, git_before[0]), (parent_tip, selected.proof.active_claim_tip))
            self.assertEqual(source.read_text(encoding="utf-8"), "partial source change\n")
            self.assertEqual(_git(worktree, "show", "HEAD:" + SOURCE), "baseline")

    def test_no_source_failure_selects_fresh_document_tip_without_recovery_source(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, _, _, claim = state
            with closing(connect(database)) as conn, maintenance_lock(root):
                fail_run(conn, root, claim.run_id, claim.owner.executor_id, claim.owner.pid,
                         json.dumps(_draft(task, claim, outcome="failed", changed_files=[])))
            with closing(connect(database)) as conn:
                rows, git_before = _rows(conn), _repo_state(worktree)
                selected = resolve_failed_source(conn, claim.run_id, task, root)
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_before)
            self.assertEqual((selected.mode, selected.recovery_of), ("unchanged", None))
            self.assertEqual((selected.snapshot.head, selected.base_commit), (git_before[0], git_before[0]))
            self.assertEqual((worktree / SOURCE).read_text(encoding="utf-8"), "baseline\n")

    def test_source_changed_after_terminal_failure_is_rejected_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim, source = data[:6]
            source.write_text("changed after terminal\n", encoding="utf-8")
            with closing(connect(database)) as conn:
                rows, git_before = _rows(conn), _repo_state(worktree)
                with self.assertRaises(FailedRecoveryError) as caught:
                    resolve_failed_source(conn, claim.run_id, task, root)
                self.assertEqual(str(caught.exception), "FAILED_RECOVERY_WORKSPACE_CHANGED")
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_before)
            self.assertEqual(source.read_text(encoding="utf-8"), "changed after terminal\n")

    def test_prepare_rejects_forged_partial_source_fields_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            root, worktree, task, database, claim = data[:5]
            with closing(connect(database)) as conn:
                selected = resolve_failed_source(conn, claim.run_id, task, root)
                rows, git_before = _rows(conn), _repo_state(worktree)
            forged = (object(), replace(selected, mode="unchanged"),
                      replace(selected, snapshot=selected.proof.observation),
                      replace(selected, base_commit="0" * 40),
                      replace(selected, recovery_of="forged-source"))
            for source in forged:
                with self.subTest(source=source), self.assertRaises(WorkspaceError):
                    prepare_failed_worktree(root, task, source)
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), rows)
            self.assertEqual(_repo_state(worktree), git_before)


if __name__ == "__main__":
    unittest.main()
