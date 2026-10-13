import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import git_index_lock_primitives as locks
from scripts.sdd_tasks.git_index_lock_primitives import GitIndexLockError

MARKER = {
    "schema": "sdd-index-lock/v1",
    "run_id": "123e4567-e89b-12d3-a456-426614174000",
    "index_lock_owner_token": "a" * 64,
    "index_before_sha256": "b" * 64,
}
TEMP_NAME = "sdd-index-lock-marker.tmp"


def _git(root, *args, input=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input)


def _fixture(directory):
    root = Path(directory) / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    blob = _git(root, "hash-object", "-w", "--stdin", input=b"tracked bytes\n").decode().strip()
    subprocess.run(["git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                    f"100644,{blob},tracked.txt"], check=True)
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir").decode().strip())
    index_path = git_dir / "index"
    return index_path, index_path.read_bytes()


def _payload(marker):
    return (json.dumps(marker, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


class GitIndexLockPrimitiveTests(unittest.TestCase):
    def test_marker_temp_is_canonical_private_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path, index_before = _fixture(directory)
            temp_path = index_path.with_name(TEMP_NAME)
            file_fsyncs = set()
            real_fsync = os.fsync

            def record_fsync(fd):
                info = os.fstat(fd)
                if stat.S_ISREG(info.st_mode):
                    file_fsyncs.add((info.st_dev, info.st_ino))
                return real_fsync(fd)

            with patch.object(locks.os, "fsync", side_effect=record_fsync):
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
                first = temp_path.stat()
                self.assertEqual(temp_path.read_bytes(), _payload(MARKER))
                self.assertEqual(stat.S_IMODE(first.st_mode), 0o600)
                self.assertIn((first.st_dev, first.st_ino), file_fsyncs)
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
            self.assertEqual((temp_path.stat().st_dev, temp_path.stat().st_ino),
                             (first.st_dev, first.st_ino))
            self.assertEqual(index_path.read_bytes(), index_before)

    def test_publish_hardlinks_complete_fsynced_marker_then_unlinks_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path, index_before = _fixture(directory)
            parent = index_path.parent
            temp_path = parent / TEMP_NAME
            lock_path = parent / "index.lock"
            file_fsyncs = set()
            directory_fsyncs = set()
            created_fsyncs = set()
            unlink_seen = []
            real_fsync, real_link, real_unlink = os.fsync, os.link, os.unlink

            def record_fsync(fd):
                info = os.fstat(fd)
                if stat.S_ISREG(info.st_mode):
                    file_fsyncs.add((info.st_dev, info.st_ino))
                elif stat.S_ISDIR(info.st_mode):
                    directory_fsyncs.add((info.st_dev, info.st_ino))
                return real_fsync(fd)

            def checked_link(source, target, **kwargs):
                source_path = parent / source
                info = source_path.stat()
                self.assertIn((info.st_dev, info.st_ino), created_fsyncs)
                self.assertEqual(source_path.read_bytes(), _payload(MARKER))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
                return real_link(source, target, **kwargs)

            def checked_unlink(name, **kwargs):
                if name == TEMP_NAME:
                    temp_info, lock_info = temp_path.stat(), lock_path.stat()
                    self.assertEqual((temp_info.st_dev, temp_info.st_ino),
                                     (lock_info.st_dev, lock_info.st_ino))
                    parent_info = parent.stat()
                    self.assertIn((parent_info.st_dev, parent_info.st_ino), directory_fsyncs)
                    unlink_seen.append(True)
                return real_unlink(name, **kwargs)

            supported = locks.os.supports_dir_fd | {checked_link, checked_unlink}
            with patch.object(locks.os, "fsync", side_effect=record_fsync), \
                    patch.object(locks.os, "supports_dir_fd", supported), \
                    patch.object(locks.os, "link", new=checked_link), \
                    patch.object(locks.os, "unlink", new=checked_unlink):
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
                created_fsyncs.update(file_fsyncs)
                identity = locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
            info = lock_path.stat()
            self.assertEqual(identity, {"device": info.st_dev, "inode": info.st_ino})
            self.assertEqual(lock_path.read_bytes(), _payload(MARKER))
            self.assertEqual(unlink_seen, [True])
            self.assertFalse(temp_path.exists())
            self.assertEqual(index_path.read_bytes(), index_before)

    def test_foreign_malformed_and_partial_temp_or_lock_bytes_are_preserved(self):
        foreign = dict(MARKER, index_lock_owner_token="c" * 64)
        for target, payload in (("temp", _payload(foreign)), ("temp", b"{partial"),
                                ("lock", _payload(foreign)), ("lock", b"{partial")):
            with self.subTest(target=target, payload=payload), tempfile.TemporaryDirectory() as directory:
                index_path, index_before = _fixture(directory)
                temp_path, lock_path = index_path.with_name(TEMP_NAME), index_path.with_name("index.lock")
                if target == "temp":
                    temp_path.write_bytes(payload)
                    temp_path.chmod(0o600)
                    with self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_MARKER_MISMATCH"):
                        locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
                    self.assertEqual(temp_path.read_bytes(), payload)
                else:
                    locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
                    lock_path.write_bytes(payload)
                    lock_path.chmod(0o600)
                    temp_before = temp_path.read_bytes()
                    with self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_MARKER_MISMATCH"):
                        locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
                    self.assertEqual(lock_path.read_bytes(), payload)
                    self.assertEqual(temp_path.read_bytes(), temp_before)
                self.assertEqual(index_path.read_bytes(), index_before)

    def test_partial_temp_write_is_left_intact_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path, _ = _fixture(directory)
            temp_path = index_path.with_name(TEMP_NAME)
            real_write = os.write

            def partial_then_fail(fd, data):
                real_write(fd, bytes(data)[:5])
                raise OSError("simulated process failure during marker write")

            with patch.object(locks.os, "write", side_effect=partial_then_fail), \
                    self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_MARKER_CREATE_FAILED"):
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
            partial = temp_path.read_bytes()
            self.assertEqual(partial, _payload(MARKER)[:5])
            with self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_MARKER_MISMATCH"):
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
            self.assertEqual(temp_path.read_bytes(), partial)
            self.assertFalse(index_path.with_name("index.lock").exists())

    def test_link_failure_keeps_fsynced_temp_for_safe_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path, index_before = _fixture(directory)
            temp_path, lock_path = index_path.with_name(TEMP_NAME), index_path.with_name("index.lock")
            locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
            temp_before = temp_path.read_bytes()
            def fail_link(_source, _target, **_kwargs):
                raise OSError("simulated link failure")

            supported = locks.os.supports_dir_fd | {fail_link}
            with patch.object(locks.os, "supports_dir_fd", supported), \
                    patch.object(locks.os, "link", new=fail_link), \
                    self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_LINK_FAILED"):
                locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
            self.assertEqual(temp_path.read_bytes(), temp_before)
            self.assertFalse(lock_path.exists())
            identity = locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
            info = lock_path.stat()
            self.assertEqual(identity, {"device": info.st_dev, "inode": info.st_ino})
            self.assertFalse(temp_path.exists())
            self.assertEqual(index_path.read_bytes(), index_before)

    def test_unlink_and_post_unlink_fsync_failures_replay_existing_lock(self):
        for failure in ("unlink", "directory_fsync"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                index_path, index_before = _fixture(directory)
                parent = index_path.parent
                temp_path, lock_path = parent / TEMP_NAME, parent / "index.lock"
                locks.create_marker_temp(index_path, TEMP_NAME, MARKER)
                real_unlink, real_fsync = os.unlink, os.fsync
                removed = []

                def fail_at_unlink(name, *, failure=failure, real_unlink=real_unlink,
                                   removed=removed, **kwargs):
                    if name == TEMP_NAME and failure == "unlink":
                        raise OSError("simulated unlink failure")
                    result = real_unlink(name, **kwargs)
                    if name == TEMP_NAME:
                        removed.append(True)
                    return result

                def fail_after_unlink_fsync(fd, *, failure=failure, removed=removed,
                                            real_fsync=real_fsync):
                    if (failure == "directory_fsync" and removed and
                            stat.S_ISDIR(os.fstat(fd).st_mode)):
                        raise OSError("simulated directory fsync failure")
                    return real_fsync(fd)

                supported = locks.os.supports_dir_fd | {fail_at_unlink}
                with patch.object(locks.os, "supports_dir_fd", supported), \
                        patch.object(locks.os, "unlink", new=fail_at_unlink), \
                        patch.object(locks.os, "fsync", side_effect=fail_after_unlink_fsync), \
                        self.assertRaisesRegex(GitIndexLockError, "GIT_LOCK_PUBLISH_FAILED"):
                    locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
                self.assertEqual(lock_path.read_bytes(), _payload(MARKER))
                if failure == "unlink":
                    self.assertTrue(temp_path.exists())
                    self.assertEqual((temp_path.stat().st_dev, temp_path.stat().st_ino),
                                     (lock_path.stat().st_dev, lock_path.stat().st_ino))
                else:
                    self.assertFalse(temp_path.exists())
                info = lock_path.stat()
                identity = locks.publish_marker_lock(index_path, TEMP_NAME, MARKER)
                self.assertEqual(identity, {"device": info.st_dev, "inode": info.st_ino})
                self.assertEqual(lock_path.read_bytes(), _payload(MARKER))
                self.assertFalse(temp_path.exists())
                self.assertEqual(index_path.read_bytes(), index_before)

    def test_invalid_marker_schema_is_rejected_before_creating_a_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path, index_before = _fixture(directory)
            invalid = []
            for field, value in (("schema", "wrong/v1"), ("run_id", "bad"),
                                 ("index_lock_owner_token", "A" * 64),
                                 ("index_before_sha256", "c" * 63)):
                candidate = dict(MARKER)
                candidate[field] = value
                invalid.append(candidate)
            invalid.append({key: value for key, value in MARKER.items() if key != "run_id"})
            invalid.append(dict(MARKER, unknown="field"))
            for candidate in invalid:
                with self.subTest(marker=candidate), self.assertRaisesRegex(
                        GitIndexLockError, "GIT_LOCK_MARKER_INVALID"):
                    locks.create_marker_temp(index_path, TEMP_NAME, candidate)
            self.assertFalse(index_path.with_name(TEMP_NAME).exists())
            self.assertEqual(index_path.read_bytes(), index_before)


if __name__ == "__main__":
    unittest.main()
