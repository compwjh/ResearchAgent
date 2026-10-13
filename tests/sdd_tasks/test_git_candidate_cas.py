import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import git_candidate_cas as cas
from scripts.sdd_tasks import git_reconciliation_index as reconciliation
from scripts.sdd_tasks.completion_journal import read_journal, write_journal
from scripts.sdd_tasks.git_candidate import create_candidate_commit
from scripts.sdd_tasks.git_candidate_cas import reconcile_candidate_ref
from scripts.sdd_tasks.git_expected_entries_io import GitExpectedEntriesError
from scripts.sdd_tasks.journal_fields import JournalError
from tests.sdd_tasks.test_git_candidate import _candidate_fixture, _git

TASK_BRANCH = "feature/spec-016-candidate-qa"


def _cas_fixture(directory):
    root, journal_path, _, _ = _candidate_fixture(directory)
    _git(root, "branch", "-m", TASK_BRANCH)
    (root / ".gitignore").write_text(".sdd/runtime/\n", encoding="utf-8")
    for path in (root / ".sdd/runtime", root / ".sdd/runtime/runs", journal_path.parent):
        path.chmod(0o700)
    reconciliation.prepare_reconciliation_index(root, journal_path)
    reconciliation.write_owned_index_image(root, journal_path)
    durable = read_journal(journal_path)
    candidate = create_candidate_commit(root, durable)
    pending = dict(durable, phase="commit_pending", candidate_commit_hash=candidate)
    write_journal(journal_path, pending, previous_phase="index_after_prepared")
    return root, journal_path, read_journal(journal_path)


def _cas_disk_state(root, journal_path, journal):
    index = Path(journal["index_before"]["git_index_path"])
    lock = index.with_name(index.name + ".lock")
    info = lock.stat()
    return {
        "refs": _git(root, "for-each-ref", "--format=%(refname) %(objectname)"),
        "index": index.read_bytes(),
        "lock": lock.read_bytes(),
        "lock_identity": (info.st_dev, info.st_ino),
        "journal": journal_path.read_bytes(),
    }


class CandidateRefCASTests(unittest.TestCase):
    def test_expected_old_cas_replays_without_second_update_or_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            index_path = Path(journal["index_before"]["git_index_path"])
            index_before, lock_path = index_path.read_bytes(), index_path.with_name("index.lock")
            lock_before = lock_path.read_bytes()
            self.assertEqual(hashlib.sha256(lock_before).hexdigest(), journal["index_after"]["index_sha256"])
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            head = _git(root, "rev-parse", "HEAD").decode().strip()
            hook_dir = root / "hooks"
            hook_dir.mkdir()
            hook_marker = root / "hook-was-called"
            hook = hook_dir / "reference-transaction"
            hook.write_text(f"#!/bin/sh\ntouch '{hook_marker}'\n", encoding="utf-8")
            hook.chmod(0o755)
            _git(root, "config", "core.hooksPath", str(hook_dir))
            run_git, updates = cas._git, []

            def record_updates(worktree, *args, **kwargs):
                if args and args[0] == "update-ref":
                    updates.append(args)
                return run_git(worktree, *args, **kwargs)

            with patch.object(cas, "_git", side_effect=record_updates):
                first = reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
                replay = reconcile_candidate_ref(root, read_journal(journal_path), task_branch=TASK_BRANCH)
            self.assertEqual(first, journal["candidate_commit_hash"])
            self.assertEqual(replay, first)
            self.assertEqual(len(updates), 1)
            self.assertFalse(hook_marker.exists())
            self.assertEqual(_git(root, "rev-parse", "HEAD").decode().strip(), first)
            self.assertNotEqual(head, first)
            self.assertEqual(index_path.read_bytes(), index_before)
            self.assertEqual(lock_path.read_bytes(), lock_before)
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)

    def test_unexpected_head_refuses_without_changing_ref_index_or_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, journal = _cas_fixture(directory)
            index = Path(journal["index_before"]["git_index_path"])
            lock = index.with_name("index.lock")
            index_before, lock_before = index.read_bytes(), lock.read_bytes()
            tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
            other = _git(root, "commit-tree", tree, "-p", journal["original_head"],
                         "-m", "unexpected head").decode().strip()
            _git(root, "update-ref", "HEAD", other)
            refs = _git(root, "for-each-ref", "--format=%(refname) %(objectname)")
            with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_HEAD_CONFLICT"):
                reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
            self.assertEqual(_git(root, "for-each-ref", "--format=%(refname) %(objectname)"), refs)
            self.assertEqual(index.read_bytes(), index_before)
            self.assertEqual(lock.read_bytes(), lock_before)

    def test_expected_old_update_ref_race_preserves_competing_commit_and_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            index = Path(journal["index_before"]["git_index_path"])
            lock = index.with_name("index.lock")
            index_before, lock_before = index.read_bytes(), lock.read_bytes()
            identity = (lock.stat().st_dev, lock.stat().st_ino)
            original = journal["original_head"]
            current_git, raced = cas._git, []

            def race_before_compare(worktree, *args, **kwargs):
                if args and args[0] == "update-ref":
                    tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
                    competitor = _git(root, "commit-tree", tree, "-p", original,
                                      "-m", "concurrent branch update").decode().strip()
                    ref = args[1]
                    current_git(worktree, "update-ref", ref, competitor, original)
                    raced.append(competitor)
                return current_git(worktree, *args, **kwargs)

            with (patch.object(cas, "_git", side_effect=race_before_compare),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_REF_CAS_FAILED")):
                reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
            refs = _git(root, "for-each-ref", "--format=%(refname) %(objectname)").decode().strip()
            self.assertEqual(refs, f"refs/heads/{TASK_BRANCH} {raced[0]}")
            self.assertEqual(index.read_bytes(), index_before)
            self.assertEqual(lock.read_bytes(), lock_before)
            self.assertEqual(hashlib.sha256(lock_before).hexdigest(), journal["index_after"]["index_sha256"])
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
            self.assertEqual(read_journal(journal_path)["phase"], "commit_pending")

    def test_lock_image_drift_refuses_and_preserves_actual_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            lock = Path(journal["index_before"]["git_index_path"]).with_name("index.lock")
            lock.write_bytes(lock.read_bytes() + b"foreign-tail")
            before = _cas_disk_state(root, journal_path, journal)
            with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_INDEX_IMAGE_MISMATCH"):
                reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
            self.assertEqual(_cas_disk_state(root, journal_path, journal), before)

    def test_replaced_lock_inode_refuses_and_preserves_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            lock = Path(journal["index_before"]["git_index_path"]).with_name("index.lock")
            replacement = lock.with_name("replacement.lock")
            replacement.write_bytes(lock.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(lock)
            before = _cas_disk_state(root, journal_path, journal)
            with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_LOCK_IDENTITY_MISMATCH"):
                reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
            self.assertEqual(_cas_disk_state(root, journal_path, journal), before)

    def test_branch_root_and_unregistered_worktree_refusals_preserve_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            before = _cas_disk_state(root, journal_path, journal)
            cases = ((root, "feature/spec-016-other-candidate", "GIT_CANDIDATE_BRANCH_MISMATCH"),
                     (root / ".sdd/runtime", TASK_BRANCH, "GIT_CANDIDATE_WORKTREE_MISMATCH"))
            for worktree, branch, error in cases:
                with self.subTest(error=error), self.assertRaisesRegex(GitExpectedEntriesError, error):
                    reconcile_candidate_ref(worktree, journal, task_branch=branch)
                self.assertEqual(_cas_disk_state(root, journal_path, journal), before)
            git = cas._git

            def omit_worktree(worktree, *args, **kwargs):
                if args == ("worktree", "list", "--porcelain", "-z"):
                    return b""
                return git(worktree, *args, **kwargs)

            with (patch.object(cas, "_git", side_effect=omit_worktree),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_WORKTREE_UNREGISTERED")):
                reconcile_candidate_ref(root, journal, task_branch=TASK_BRANCH)
            self.assertEqual(_cas_disk_state(root, journal_path, journal), before)

    def test_partial_journal_refuses_before_git_state_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, journal = _cas_fixture(directory)
            partial = dict(read_journal(journal_path), index_after=None)
            before = _cas_disk_state(root, journal_path, journal)
            with self.assertRaisesRegex(JournalError, "JOURNAL_INVALID: index_snapshots_required"):
                reconcile_candidate_ref(root, partial, task_branch=TASK_BRANCH)
            self.assertEqual(_cas_disk_state(root, journal_path, journal), before)


if __name__ == "__main__":
    unittest.main()
