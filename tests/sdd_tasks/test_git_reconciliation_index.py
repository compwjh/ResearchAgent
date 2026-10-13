import hashlib
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import git_reconciliation_index as reconciliation
from scripts.sdd_tasks.completion_journal import read_journal, write_journal
from scripts.sdd_tasks.git_candidate import create_candidate_commit
from scripts.sdd_tasks.git_candidate_cas import reconcile_candidate_ref
from scripts.sdd_tasks.git_index import _parse_index
from scripts.sdd_tasks.git_reconciliation_index import prepare_reconciliation_index
from tests.sdd_tasks import test_git_candidate as candidate_fixture

_TASK_BRANCH = "feature/spec-016-reconciliation-qa"


def _strict_candidate_fixture(directory, **options):
    real_worktree = candidate_fixture._worktree_fixture
    real_write = write_journal

    def prepare_ignored_baseline(path):
        root = real_worktree(path)
        (root / ".gitignore").write_text(".sdd/runtime/\n", encoding="utf-8")
        candidate_fixture._git(root, "add", ".gitignore")
        candidate_fixture._git(root, "commit", "-qm", "ignore private runtime")
        return root

    def write_private_journal(path, journal, **kwargs):
        for directory in (path.parents[2], path.parents[1], path.parent):
            directory.chmod(0o700)
        return real_write(path, journal, **kwargs)

    with patch.object(candidate_fixture, "_worktree_fixture", side_effect=prepare_ignored_baseline), \
            patch.object(candidate_fixture, "write_journal", side_effect=write_private_journal):
        return candidate_fixture._candidate_fixture(directory, **options)


def _git_index(root, index_path, *args):
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = os.fspath(index_path)
    return subprocess.run(["git", "-C", str(root), *args], env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _preserved_state(root, locked):
    index_path = Path(locked["index_before"]["git_index_path"])
    lock_path = index_path.with_name("index.lock")
    outsider = tuple(entry for entry in _parse_index(candidate_fixture._git(root, "ls-files", "--stage", "-z"))
                     if entry["path"] == "outsider.txt")
    return (candidate_fixture._git(root, "rev-parse", "HEAD"), index_path.read_bytes(),
            lock_path.read_bytes(), (lock_path.stat().st_dev, lock_path.stat().st_ino), outsider)


def _patch_dirfd_os(name, fail):
    stack = ExitStack()
    supported = set(os.supports_dir_fd)
    replacement = stack.enter_context(patch.object(reconciliation.os, name, side_effect=fail))
    stack.enter_context(patch.object(reconciliation.os, "supports_dir_fd", supported | {replacement}))
    return stack


def _publication_fault(kind, run_dir):
    if kind == "link":
        original = os.link

        def fail(source, destination, **kwargs):
            if destination == "index-after":
                raise OSError("injected link failure")
            return original(source, destination, **kwargs)

        return _patch_dirfd_os("link", fail), reconciliation.GitReconciliationError, "IMAGE_PUBLISH_FAILED"
    if kind == "unlink":
        original, fired = os.unlink, [False]

        def fail(name, **kwargs):
            if isinstance(name, str) and name.startswith(".index-after-") and not fired[0]:
                fired[0] = True
                raise OSError("injected unlink failure")
            return original(name, **kwargs)

        return _patch_dirfd_os("unlink", fail), reconciliation.GitReconciliationError, "IMAGE_PUBLISH_FAILED"
    if kind == "fsync":
        original, fired = os.fsync, [False]

        def fail(fd):
            path = Path(os.path.realpath("/proc/self/fd/{}".format(fd)))
            image = run_dir / "index-after"
            if (not fired[0] and path == run_dir and image.exists() and image.stat().st_nlink == 2):
                fired[0] = True
                raise OSError("injected directory fsync failure")
            return original(fd)

        return patch.object(reconciliation.os, "fsync", side_effect=fail), reconciliation.GitReconciliationError, "IMAGE_PUBLISH_FAILED"
    original, fired = reconciliation.write_journal, [False]

    def fail(path, journal, **kwargs):
        if journal.get("phase") == "index_after_prepared" and not fired[0]:
            fired[0] = True
            raise OSError("injected phase write failure")
        return original(path, journal, **kwargs)

    return patch.object(reconciliation, "write_journal", side_effect=fail), OSError, "injected phase write failure"


def _prepared_lock_fixture(directory):
    root, journal_path, _, locked = _strict_candidate_fixture(directory, with_exotic=True)
    prepared = prepare_reconciliation_index(root, journal_path)
    index_path = Path(locked["index_before"]["git_index_path"])
    return root, journal_path, prepared, index_path.with_name("index.lock"), index_path


def _committed_fixture(directory):
    root, journal_path, _, locked = _strict_candidate_fixture(directory, with_exotic=True)
    candidate_fixture._git(root, "branch", "-m", _TASK_BRANCH)
    prepare_reconciliation_index(root, journal_path)
    durable = reconciliation.write_owned_index_image(root, journal_path)
    candidate = create_candidate_commit(root, durable)
    pending = dict(durable, phase="commit_pending", candidate_commit_hash=candidate)
    write_journal(journal_path, pending, previous_phase="index_after_prepared")
    reconcile_candidate_ref(root, read_journal(journal_path), task_branch=_TASK_BRANCH)
    committed = dict(read_journal(journal_path), phase="committed", index_recovery_stage="ref_committed")
    write_journal(journal_path, committed, previous_phase="commit_pending")
    index_path = Path(locked["index_before"]["git_index_path"])
    return root, journal_path, read_journal(journal_path), index_path, index_path.with_name("index.lock"), candidate


def _install_fault(kind, index_path, lock_path, image):
    if kind == "rename":
        original = os.replace

        def fail_after_rename(source, destination, **kwargs):
            result = original(source, destination, **kwargs)
            if source == "index.lock" and destination == "index":
                raise OSError("injected rename completion fault")
            return result

        return patch.object(reconciliation.os, "replace", side_effect=fail_after_rename)
    if kind == "fsync":
        original = os.fsync
        fired = [False]

        def fail_after_rename(fd):
            path = Path(os.path.realpath("/proc/self/fd/{}".format(fd)))
            if (not fired[0] and path == index_path.parent and not lock_path.exists() and
                    index_path.read_bytes() == image):
                fired[0] = True
                raise OSError("injected install directory fsync fault")
            return original(fd)

        return patch.object(reconciliation.os, "fsync", side_effect=fail_after_rename)
    original = reconciliation.write_journal

    def fail_phase(path, journal, **kwargs):
        if journal.get("phase") == "index_reconciled":
            raise OSError("injected install phase write fault")
        return original(path, journal, **kwargs)

    return patch.object(reconciliation, "write_journal", side_effect=fail_phase)


class GitReconciliationIndexTests(unittest.TestCase):
    def test_prepare_publishes_private_target_image_without_touching_head_index_or_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, _, locked = _strict_candidate_fixture(directory, with_exotic=True)
            runtime, runs, run_dir = root / ".sdd/runtime", root / ".sdd/runtime/runs", journal_path.parent
            self.assertEqual([stat.S_IMODE(path.stat().st_mode) for path in (runtime, runs, run_dir)],
                             [0o700, 0o700, 0o700])
            ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--quiet", "--",
                                      os.fspath(Path(".sdd/runtime/runs") / locked["run_id"] / "index-after")])
            self.assertEqual(ignored.returncode, 0)
            head = candidate_fixture._git(root, "rev-parse", "HEAD")
            index_path = Path(locked["index_before"]["git_index_path"])
            index_before = index_path.read_bytes()
            lock_path = index_path.with_name("index.lock")
            marker_before = lock_path.read_bytes()
            marker_identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            entries_before = _parse_index(candidate_fixture._git(root, "ls-files", "--stage", "-z"))

            prepared = prepare_reconciliation_index(root, journal_path)

            self.assertEqual(prepared["phase"], "index_after_prepared")
            self.assertEqual(prepared["index_recovery_stage"], "reconciliation_index_durable")
            image_path = run_dir / "index-after"
            image = image_path.read_bytes()
            self.assertEqual(stat.S_IMODE(image_path.stat().st_mode), 0o600)
            self.assertEqual(image_path.stat().st_nlink, 1)
            self.assertEqual(prepared, read_journal(journal_path))
            self.assertEqual(prepared["index_after"]["index_sha256"], hashlib.sha256(image).hexdigest())
            self.assertEqual(prepared["index_after"]["other_entries_sha256"],
                             prepared["index_observed_before"]["other_entries_sha256"])
            expected = [{"path": entry["path"], "stage": 0, "mode": entry["mode"],
                         "object_id": entry["object_id"]}
                        for entry in prepared["expected_git_entries"] if entry["mode"] is not None]
            image_entries = _parse_index(_git_index(root, image_path, "ls-files", "--stage", "-z"))
            self.assertEqual([entry for entry in image_entries if entry["path"] in prepared["committed_paths"]],
                             expected)
            outsider_before = [entry for entry in entries_before if entry["path"] == "outsider.txt"]
            outsider_after = [entry for entry in image_entries if entry["path"] == "outsider.txt"]
            self.assertEqual(len(outsider_before), 1)
            self.assertEqual(outsider_after, outsider_before)
            self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD"), head)
            self.assertEqual(index_path.read_bytes(), index_before)
            self.assertEqual(lock_path.read_bytes(), marker_before)
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), marker_identity)

    def test_publication_faults_preserve_real_state_and_replay_once(self):
        for kind in ("link", "unlink", "fsync", "journal"):
            with self.subTest(fault=kind), tempfile.TemporaryDirectory() as directory:
                root, journal_path, _, locked = _strict_candidate_fixture(directory, with_exotic=True)
                state = _preserved_state(root, locked)
                fault, error, message = _publication_fault(kind, journal_path.parent)
                with fault, self.assertRaisesRegex(error, message):
                    prepare_reconciliation_index(root, journal_path)
                self.assertEqual(_preserved_state(root, locked), state)
                prepared = prepare_reconciliation_index(root, journal_path)
                self.assertEqual(prepared["phase"], "index_after_prepared")
                image_path = journal_path.parent / "index-after"
                self.assertEqual(stat.S_IMODE(image_path.stat().st_mode), 0o600)
                self.assertEqual(_preserved_state(root, locked), state)
                self.assertEqual(tuple(entry for entry in _parse_index(_git_index(
                    root, image_path, "ls-files", "--stage", "-z")) if entry["path"] == "outsider.txt"), state[4])

    def test_foreign_symlink_and_hardlinked_images_are_refused_without_state_change(self):
        for kind, error in (("foreign", "IMAGE_MISMATCH"), ("symlink", "IMAGE_UNREADABLE"),
                            ("hardlink", "IMAGE_UNSAFE")):
            with self.subTest(image=kind), tempfile.TemporaryDirectory() as directory:
                root, journal_path, _, locked = _strict_candidate_fixture(directory, with_exotic=True)
                state = _preserved_state(root, locked)
                image = journal_path.parent / "index-after"
                source = journal_path.parent / "foreign-image"
                source.write_bytes(b"foreign private image\n")
                source.chmod(0o600)
                if kind == "symlink":
                    image.symlink_to(source.name)
                elif kind == "hardlink":
                    os.link(source, image)
                else:
                    image.write_bytes(b"foreign private image\n")
                    image.chmod(0o600)
                with self.assertRaisesRegex(reconciliation.GitReconciliationError, error):
                    prepare_reconciliation_index(root, journal_path)
                self.assertEqual(_preserved_state(root, locked), state)
                self.assertTrue(image.is_symlink() if kind == "symlink" else image.exists())
                self.assertEqual(source.read_bytes(), b"foreign private image\n")
                if kind == "hardlink":
                    self.assertEqual(source.stat().st_nlink, 2)

    def test_partial_owned_lock_write_recovers_in_same_inode_and_stage_four_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, _, lock_path, index_path = _prepared_lock_fixture(directory)
            image = (journal_path.parent / "index-after").read_bytes()
            original_index = index_path.read_bytes()
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            original_write, fired = os.write, [False]

            def partial_then_fail(fd, content):
                if not fired[0]:
                    fired[0] = True
                    original_write(fd, content[:17])
                    raise OSError("injected partial lock write")
                return original_write(fd, content)

            with patch.object(reconciliation.os, "write", side_effect=partial_then_fail), \
                    self.assertRaisesRegex(reconciliation.GitReconciliationError, "LOCK_WRITE_FAILED"):
                reconciliation.write_owned_index_image(root, journal_path)
            self.assertEqual(read_journal(journal_path)["index_recovery_stage"], "reconciliation_index_durable")
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)
            self.assertNotEqual(lock_path.read_bytes(), image)
            completed = reconciliation.write_owned_index_image(root, journal_path)
            self.assertEqual(completed["index_recovery_stage"], "lock_index_durable")
            self.assertEqual(lock_path.read_bytes(), image)
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)
            self.assertEqual(reconciliation.write_owned_index_image(root, journal_path), completed)
            self.assertEqual(read_journal(journal_path), completed)
            self.assertEqual(index_path.read_bytes(), original_index)

    def test_owned_lock_fsync_failure_replays_exact_image_without_replacing_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, _, lock_path, index_path = _prepared_lock_fixture(directory)
            image = (journal_path.parent / "index-after").read_bytes()
            original_index = index_path.read_bytes()
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            original_fsync, fired = os.fsync, [False]

            def fail_owned_file(fd):
                info = os.fstat(fd)
                if not fired[0] and (info.st_dev, info.st_ino) == identity:
                    fired[0] = True
                    raise OSError("injected owned lock fsync failure")
                return original_fsync(fd)

            with patch.object(reconciliation.os, "fsync", side_effect=fail_owned_file), \
                    self.assertRaisesRegex(reconciliation.GitReconciliationError, "LOCK_WRITE_FAILED"):
                reconciliation.write_owned_index_image(root, journal_path)
            self.assertEqual(read_journal(journal_path)["index_recovery_stage"], "reconciliation_index_durable")
            self.assertEqual(lock_path.read_bytes(), image)
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)
            self.assertEqual(index_path.read_bytes(), original_index)
            completed = reconciliation.write_owned_index_image(root, journal_path)
            self.assertEqual(completed["index_recovery_stage"], "lock_index_durable")
            self.assertEqual(lock_path.read_bytes(), image)
            self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)

    def test_foreign_lock_inode_and_complete_foreign_content_are_refused(self):
        for kind, error in (("inode", "LOCK_IDENTITY_MISMATCH"), ("content", "LOCK_FOREIGN_CONTENT")):
            with self.subTest(foreign=kind), tempfile.TemporaryDirectory() as directory:
                root, journal_path, _, lock_path, index_path = _prepared_lock_fixture(directory)
                original_index = index_path.read_bytes()
                original_head = candidate_fixture._git(root, "rev-parse", "HEAD")
                image = (journal_path.parent / "index-after").read_bytes()
                owned = (lock_path.stat().st_dev, lock_path.stat().st_ino)
                foreign = b'{"schema":"sdd-index-lock/v1","foreign":true}\n'
                if kind == "inode":
                    replacement = lock_path.with_name("foreign-lock")
                    replacement.write_bytes(foreign)
                    replacement.chmod(0o600)
                    os.replace(replacement, lock_path)
                    self.assertNotEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), owned)
                else:
                    lock_path.write_bytes(foreign)
                before = lock_path.read_bytes()
                with self.assertRaisesRegex(reconciliation.GitReconciliationError, error):
                    reconciliation.write_owned_index_image(root, journal_path)
                self.assertEqual(lock_path.read_bytes(), before)
                self.assertEqual(index_path.read_bytes(), original_index)
                self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD"), original_head)
                self.assertEqual((journal_path.parent / "index-after").read_bytes(), image)
                self.assertEqual(read_journal(journal_path)["index_recovery_stage"], "reconciliation_index_durable")

    def test_install_consumes_owned_image_preserves_outsider_and_replays_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, committed, index_path, lock_path, candidate = _committed_fixture(directory)
            image_path = journal_path.parent / "index-after"
            image = image_path.read_bytes()
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            outsider = next(entry for entry in _parse_index(_git_index(
                root, image_path, "ls-files", "--stage", "-z")) if entry["path"] == "outsider.txt")

            installed = reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)

            self.assertEqual(installed["phase"], "index_reconciled")
            self.assertEqual(installed["index_recovery_stage"], "index_installed")
            self.assertEqual(installed, read_journal(journal_path))
            self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD").decode().strip(), candidate)
            self.assertEqual(index_path.read_bytes(), image)
            self.assertEqual(hashlib.sha256(index_path.read_bytes()).hexdigest(), committed["index_after"]["index_sha256"])
            self.assertFalse(lock_path.exists())
            self.assertEqual((index_path.stat().st_dev, index_path.stat().st_ino), identity)
            self.assertEqual(next(entry for entry in _parse_index(candidate_fixture._git(
                root, "ls-files", "--stage", "-z")) if entry["path"] == "outsider.txt"), outsider)
            replay = reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
            self.assertEqual(replay, installed)
            self.assertEqual(index_path.read_bytes(), image)
            self.assertEqual((index_path.stat().st_dev, index_path.stat().st_ino), identity)

    def test_post_rename_faults_replay_when_index_is_installed_and_lock_is_missing(self):
        for kind in ("rename", "fsync", "journal"):
            with self.subTest(fault=kind), tempfile.TemporaryDirectory() as directory:
                root, journal_path, committed, index_path, lock_path, candidate = _committed_fixture(directory)
                image = (journal_path.parent / "index-after").read_bytes()
                fault = _install_fault(kind, index_path, lock_path, image)
                with fault, self.assertRaisesRegex(OSError, "injected"):
                    reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
                self.assertEqual(index_path.read_bytes(), image)
                self.assertFalse(lock_path.exists())
                self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD").decode().strip(), candidate)
                self.assertEqual(read_journal(journal_path)["phase"], "committed")
                self.assertEqual(read_journal(journal_path)["index_recovery_stage"], "ref_committed")
                replay = reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
                self.assertEqual(replay["phase"], "index_reconciled")
                self.assertEqual(replay["index_recovery_stage"], "index_installed")
                self.assertEqual(index_path.read_bytes(), image)
                self.assertEqual(hashlib.sha256(image).hexdigest(), committed["index_after"]["index_sha256"])

    def test_ledger_finalizing_replay_proves_installed_index_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, journal_path, _, index_path, lock_path, candidate = _committed_fixture(directory)
            installed = reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
            finalizing = dict(installed, phase="ledger_finalizing")
            write_journal(journal_path, finalizing, previous_phase="index_reconciled")
            image = index_path.read_bytes()
            identity = (index_path.stat().st_dev, index_path.stat().st_ino)
            journal_bytes = journal_path.read_bytes()
            head = candidate_fixture._git(root, "rev-parse", "HEAD")
            self.assertEqual(head.decode().strip(), candidate)
            for _ in range(2):
                replay = reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
                self.assertEqual(replay, finalizing)
                self.assertEqual(index_path.read_bytes(), image)
                self.assertEqual((index_path.stat().st_dev, index_path.stat().st_ino), identity)
                self.assertFalse(lock_path.exists())
                self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD"), head)
                self.assertEqual(journal_path.read_bytes(), journal_bytes)

            oid = candidate_fixture._git(root, "hash-object", "-w", "--stdin",
                                          input=b"foreign staged outsider\n").decode().strip()
            index_path, foreign_index = candidate_fixture._replace_index(
                root, ["update-index", "--cacheinfo", "100644,{},outsider.txt".format(oid)])
            with self.assertRaisesRegex(reconciliation.GitReconciliationError,
                                        "GIT_RECONCILIATION_INSTALLED_STATE_CHANGED"):
                reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
            self.assertEqual(index_path.read_bytes(), foreign_index)
            self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD"), head)
            self.assertFalse(lock_path.exists())
            self.assertEqual(journal_path.read_bytes(), journal_bytes)
            self.assertEqual((journal_path.parent / "index-after").read_bytes(), image)

    def test_unknown_live_index_and_foreign_lock_are_refused_unchanged(self):
        for kind, error in (("index", "INDEX_CONFLICT"), ("lock", "LOCK_IDENTITY_MISMATCH")):
            with self.subTest(foreign=kind), tempfile.TemporaryDirectory() as directory:
                root, journal_path, _, index_path, lock_path, candidate = _committed_fixture(directory)
                original_lock = lock_path.read_bytes()
                image = (journal_path.parent / "index-after").read_bytes()
                if kind == "index":
                    oid = candidate_fixture._git(root, "hash-object", "-w", "--stdin",
                                                 input=b"foreign staged outsider\n").decode().strip()
                    index_path, foreign_index = candidate_fixture._replace_index(
                        root, ["update-index", "--cacheinfo", "100644,{},outsider.txt".format(oid)])
                    self.assertNotEqual(foreign_index, image)
                else:
                    replacement = lock_path.with_name("foreign-lock")
                    replacement.write_bytes(b'{"foreign":true}\n')
                    replacement.chmod(0o600)
                    os.replace(replacement, lock_path)
                    foreign_lock = lock_path.read_bytes()
                    self.assertNotEqual((lock_path.stat().st_dev, lock_path.stat().st_ino),
                                        (read_journal(journal_path)["index_lock_identity"]["device"],
                                         read_journal(journal_path)["index_lock_identity"]["inode"]))
                before_index = index_path.read_bytes()
                with self.assertRaisesRegex(reconciliation.GitReconciliationError, error):
                    reconciliation.install_reconciled_index(root, journal_path, task_branch=_TASK_BRANCH)
                self.assertEqual(index_path.read_bytes(), before_index)
                self.assertEqual(candidate_fixture._git(root, "rev-parse", "HEAD").decode().strip(), candidate)
                self.assertEqual((journal_path.parent / "index-after").read_bytes(), image)
                self.assertEqual(read_journal(journal_path)["phase"], "committed")
                if kind == "index":
                    self.assertEqual(lock_path.read_bytes(), original_lock)
                else:
                    self.assertEqual(lock_path.read_bytes(), foreign_lock)


if __name__ == "__main__":
    unittest.main()
