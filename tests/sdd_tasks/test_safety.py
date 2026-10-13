import multiprocessing as mp
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.atomic import AtomicWriteError, atomic_write, contained, read_text, write_json
from scripts.sdd_tasks.locks import maintenance_lock, repository_paths, runtime_root

ROOT = Path(__file__).resolve().parents[2]


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _worktree(base):
    main = base / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "test@example.invalid")
    _git(main, "config", "user.name", "Test")
    (main / "README").write_text("fixture\n", encoding="utf-8")
    _git(main, "add", "README")
    _git(main, "commit", "-qm", "fixture")
    linked = base / "linked"
    _git(main, "worktree", "add", "-qb", "test-linked", str(linked))
    return main, linked


def _hold_lock(root, entered, release):
    with maintenance_lock(Path(root)):
        entered.set()
        release.wait()


def _wait_lock(root, entered):
    with maintenance_lock(Path(root)):
        entered.set()


class SafetyTests(unittest.TestCase):
    def test_import_has_no_directory_side_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ.copy()
            env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
            subprocess.run([sys.executable, "-c", "import scripts.sdd_tasks.atomic, scripts.sdd_tasks.locks, scripts.sdd_tasks.documents, scripts.sdd_tasks.summaries, scripts.sdd_tasks.mirrors"],
                           cwd=temp, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_worktree_paths_come_from_git_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            main, linked = _worktree(Path(temp))
            actual_main, common = repository_paths(linked)
            self.assertEqual(actual_main, main.resolve())
            self.assertEqual(common, (main / ".git").resolve())
            self.assertEqual(runtime_root(linked), main / ".sdd" / "runtime")
            self.assertFalse((main / ".sdd").exists())

    @unittest.skipUnless(os.name == "posix", "fcntl lock requires POSIX")
    def test_process_lock_and_owner_death_release(self):
        with tempfile.TemporaryDirectory() as temp:
            _, linked = _worktree(Path(temp))
            ctx = mp.get_context("fork")
            owner_ready, release, waiter_ready = ctx.Event(), ctx.Event(), ctx.Event()
            owner = ctx.Process(target=_hold_lock, args=(str(linked), owner_ready, release))
            waiter = ctx.Process(target=_wait_lock, args=(str(linked), waiter_ready))
            owner.start()
            try:
                self.assertTrue(owner_ready.wait(5))
                waiter.start()
                self.assertFalse(waiter_ready.wait(0.2))
                owner.terminate()
                owner.join(5)
                self.assertFalse(owner.is_alive())
                self.assertTrue(waiter_ready.wait(5))
                waiter.join(5)
                self.assertEqual(waiter.exitcode, 0)
            finally:
                for process in (owner, waiter):
                    if process.is_alive():
                        process.terminate()
                        process.join(5)

    @unittest.skipUnless(os.name == "posix", "symlinks and fcntl require POSIX")
    def test_maintenance_lock_rejects_symlink_locations(self):
        for kind in ("sdd", "internal", "external"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                main, linked = _worktree(Path(temp))
                common = main / ".git"
                sdd = common / "sdd"
                if kind == "sdd":
                    target = common / "redirect"
                    target.mkdir()
                    sdd.symlink_to(target, target_is_directory=True)
                else:
                    sdd.mkdir()
                    target = sdd / "target.lock" if kind == "internal" else Path(temp) / "outside.lock"
                    target.write_text("keep", encoding="utf-8")
                    (sdd / "ledger.lock").symlink_to(target)
                with self.assertRaises((ValueError, OSError)), maintenance_lock(linked):
                    pass
                if kind == "sdd":
                    self.assertEqual(list(target.iterdir()), [])
                else:
                    self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_failed_replace_preserves_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            path.write_text("old", encoding="utf-8")
            with patch("scripts.sdd_tasks.atomic.os.replace", side_effect=OSError("replace failed")), \
                    self.assertRaises(OSError):
                atomic_write(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(temp).glob(".sdd-atomic-*")), [])

    def test_atomic_write_modes_keep_default_private_and_require_exact_bool(self):
        with tempfile.TemporaryDirectory() as temp:
            private, executable = Path(temp) / "private.json", Path(temp) / "task.md"
            atomic_write(private, "private")
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
            atomic_write(executable, "task", executable=True)
            self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o700)
            for index, value in enumerate((0, 1, None, "yes")):
                target = Path(temp) / "invalid-{}".format(index)
                with self.subTest(value=value), self.assertRaises(TypeError):
                    atomic_write(target, "invalid", executable=value)
                self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == "posix", "symlinks require POSIX")
    def test_atomic_write_rejects_symlink_parents_and_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            inside, outside = root / "inside", Path(temp) / "outside"
            inside.mkdir(parents=True)
            outside.mkdir()
            internal_keep, external_keep = inside / "keep", outside / "keep"
            internal_keep.write_text("inside", encoding="utf-8")
            external_keep.write_text("outside", encoding="utf-8")
            (root / "internal-link").symlink_to(inside, target_is_directory=True)
            (root / "external-link").symlink_to(outside, target_is_directory=True)
            (root / "target-link").symlink_to(external_keep)
            for path in (root / "internal-link" / "payload", root / "external-link" / "payload",
                         root / "target-link"):
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                    atomic_write(path, "new")
            self.assertEqual(internal_keep.read_text(encoding="utf-8"), "inside")
            self.assertEqual(external_keep.read_text(encoding="utf-8"), "outside")
            self.assertFalse((inside / "payload").exists())
            self.assertFalse((outside / "payload").exists())

    def test_directory_fsync_failure_reports_replacement_without_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            path, real_fsync = Path(temp) / "ledger.json", os.fsync
            path.write_text("old", encoding="utf-8")

            def fail_directory(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("directory fsync failed")
                return real_fsync(fd)

            with patch("scripts.sdd_tasks.atomic.os.fsync", side_effect=fail_directory), \
                    self.assertRaises(AtomicWriteError) as failure:
                atomic_write(path, "new")
            self.assertTrue(failure.exception.replaced)
            self.assertEqual(failure.exception.phase, "fsync_directory")
            self.assertEqual(path.read_text(encoding="utf-8"), "new")

    def test_json_is_canonical_utf8_with_one_lf(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "value.json"
            write_json(path, {"z": "雪", "a": 1})
            self.assertEqual(path.read_bytes(), '{"a":1,"z":"雪"}\n'.encode("utf-8"))

    def test_contained_rejects_escape_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "outside").mkdir()
            (root / "link").symlink_to(root / "outside", target_is_directory=True)
            for value in ("../escape", "/absolute", "a\\b", "C:/drive", "link/file"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    contained(root, value)

    @unittest.skipUnless(os.name == "posix", "O_NOFOLLOW and FIFO require POSIX")
    def test_safe_read_rejects_internal_external_links_and_fifo(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            inside, outside = root / "inside", Path(temp) / "outside"
            inside.mkdir(parents=True)
            outside.mkdir()
            source, external = inside / "source", outside / "source"
            source.write_text("inside", encoding="utf-8")
            external.write_text("outside", encoding="utf-8")
            (root / "inside-parent").symlink_to(inside, target_is_directory=True)
            (root / "outside-parent").symlink_to(outside, target_is_directory=True)
            (inside / "inside-target").symlink_to(source)
            (inside / "outside-target").symlink_to(external)
            fifo = inside / "pipe"
            os.mkfifo(fifo)
            for path in (root / "inside-parent/source", root / "outside-parent/source",
                         inside / "inside-target", inside / "outside-target", fifo):
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                    read_text(path)

    def test_contained_allows_missing_components_and_symlink_root_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "root"
            real.mkdir()
            alias = Path(temp) / "root-alias"
            alias.symlink_to(real, target_is_directory=True)
            self.assertEqual(contained(real, "not-created/child"), real / "not-created/child")
            self.assertEqual(contained(alias, "not-created/child"), real / "not-created/child")


if __name__ == "__main__":
    unittest.main()
