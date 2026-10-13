"""Read-only nofollow checks for the baseline index and owned lock image."""
import hashlib
import os
import stat
from pathlib import Path

from . import atomic
from .git_expected_entries_io import GitExpectedEntriesError


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _file_hash(path: Path, expected_hash: str, *, identity=None, owned_lock=False) -> None:
    if (not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd or
            os.stat not in os.supports_dir_fd or os.stat not in os.supports_follow_symlinks):
        raise GitExpectedEntriesError("GIT_CANDIDATE_PLATFORM_UNSAFE")
    parent = fd = -1
    try:
        parent = atomic._open_directory(path.parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_UNSAFE")
        if owned_lock and (before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600 or
                           before.st_nlink != 1):
            raise GitExpectedEntriesError("GIT_CANDIDATE_LOCK_UNSAFE")
        if identity is not None and (before.st_dev != identity["device"] or before.st_ino != identity["inode"]):
            raise GitExpectedEntriesError("GIT_CANDIDATE_LOCK_IDENTITY_MISMATCH")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        path_after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if _stamp(before) != _stamp(after) or _stamp(after) != _stamp(path_after):
            raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_CHANGED")
        if digest.hexdigest() != expected_hash:
            raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_IMAGE_MISMATCH")
    except GitExpectedEntriesError:
        raise
    except OSError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_UNSAFE") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if parent >= 0:
            os.close(parent)


def verify_pending_index_images(journal: dict) -> None:
    """Bind the real index and lock to their durable exact byte images."""
    index_path = Path(journal["index_before"]["git_index_path"])
    lock_path = index_path.with_name(index_path.name + ".lock")
    _file_hash(index_path, journal["index_observed_before"]["index_sha256"])
    _file_hash(lock_path, journal["index_after"]["index_sha256"],
               identity=journal["index_lock_identity"], owned_lock=True)
