"""Safe file primitives for publishing a complete owned Git index.lock marker."""
import json
import os
import re
import stat
from pathlib import Path

from . import atomic

_MARKER_FIELDS = {"schema", "run_id", "index_lock_owner_token", "index_before_sha256"}


class GitIndexLockError(ValueError):
    pass


def _marker_bytes(marker: dict) -> bytes:
    if (not isinstance(marker, dict) or set(marker) != _MARKER_FIELDS or
            not all(isinstance(marker[key], str) for key in _MARKER_FIELDS) or
            marker.get("schema") != "sdd-index-lock/v1" or
            not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", marker["run_id"]) or
            not re.fullmatch(r"[0-9a-f]{64}", marker["index_lock_owner_token"]) or
            not re.fullmatch(r"[0-9a-f]{64}", marker["index_before_sha256"])):
        raise GitIndexLockError("GIT_LOCK_MARKER_INVALID")
    return (json.dumps(marker, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _open_parent(index_path: Path, temp_basename: str):
    index = Path(index_path)
    if (not index.is_absolute() or index.name != "index" or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", temp_basename) or temp_basename in {".", "..", "index", "index.lock"}):
        raise GitIndexLockError("GIT_LOCK_PATH_INVALID")
    if not hasattr(os, "O_NOFOLLOW") or not {os.open, os.link, os.unlink} <= os.supports_dir_fd:
        raise GitIndexLockError("GIT_LOCK_UNSUPPORTED")
    try:
        return atomic._open_directory(index.parent)
    except OSError as exc:
        raise GitIndexLockError("GIT_INDEX_UNSAFE_OR_UNREADABLE") from exc


def _identity(parent: int, name: str):
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GitIndexLockError("GIT_LOCK_UNSAFE") from exc
    if not stat.S_ISREG(info.st_mode):
        raise GitIndexLockError("GIT_LOCK_UNSAFE")
    return {"device": info.st_dev, "inode": info.st_ino}


def _read_marker(parent: int, name: str, expected: bytes) -> dict:
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or
                stat.S_IMODE(before.st_mode) != 0o600):
            raise GitIndexLockError("GIT_LOCK_UNSAFE")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        first = (before.st_dev, before.st_ino, before.st_uid, stat.S_IMODE(before.st_mode), before.st_size,
                 before.st_mtime_ns, before.st_ctime_ns)
        last = (after.st_dev, after.st_ino, after.st_uid, stat.S_IMODE(after.st_mode), after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
        if first != last or b"".join(chunks) != expected:
            raise GitIndexLockError("GIT_LOCK_MARKER_MISMATCH")
        os.fsync(fd)
        return {"device": after.st_dev, "inode": after.st_ino}
    except OSError as exc:
        raise GitIndexLockError("GIT_LOCK_MARKER_UNREADABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def create_marker_temp(index_path: Path, temp_basename: str, marker: dict) -> None:
    """Create an exact marker with O_EXCL and fsync file plus directory."""
    payload = _marker_bytes(marker)
    parent = _open_parent(index_path, temp_basename)
    fd = -1
    try:
        existing = _identity(parent, temp_basename)
        if existing is not None:
            if _read_marker(parent, temp_basename, payload) != existing:
                raise GitIndexLockError("GIT_LOCK_TEMP_INODE_MISMATCH")
            os.fsync(parent)
            return
        try:
            fd = os.open(temp_basename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
        except FileExistsError:
            _read_marker(parent, temp_basename, payload)
            os.fsync(parent)
            return
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short marker write")
            view = view[count:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.fsync(parent)
    except OSError as exc:
        raise GitIndexLockError("GIT_LOCK_MARKER_CREATE_FAILED") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)


def publish_marker_lock(index_path: Path, temp_basename: str, marker: dict, identity=None) -> dict:
    """No-replace hardlink a durable marker into index.lock and retire its temp name."""
    payload = _marker_bytes(marker)
    parent = _open_parent(index_path, temp_basename)
    lock_name = "index.lock"
    try:
        lock_identity = _identity(parent, lock_name)
        temp_identity = _identity(parent, temp_basename)
        if lock_identity is None:
            if temp_identity is None:
                raise GitIndexLockError("GIT_LOCK_MARKER_MISSING")
            _read_marker(parent, temp_basename, payload)
            try:
                os.link(temp_basename, lock_name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            except FileExistsError:
                lock_identity = _identity(parent, lock_name)
            except OSError as exc:
                raise GitIndexLockError("GIT_LOCK_LINK_FAILED") from exc
            os.fsync(parent)
            lock_identity = _identity(parent, lock_name)
        if lock_identity is None or _read_marker(parent, lock_name, payload) != lock_identity:
            raise GitIndexLockError("GIT_LOCK_MARKER_MISMATCH")
        os.fsync(parent)
        if identity is not None and lock_identity != identity:
            raise GitIndexLockError("GIT_LOCK_IDENTITY_MISMATCH")
        if temp_identity is not None:
            if temp_identity != lock_identity or _read_marker(parent, temp_basename, payload) != lock_identity:
                raise GitIndexLockError("GIT_LOCK_TEMP_INODE_MISMATCH")
            os.unlink(temp_basename, dir_fd=parent)
            os.fsync(parent)
        return lock_identity
    except OSError as exc:
        raise GitIndexLockError("GIT_LOCK_PUBLISH_FAILED") from exc
    finally:
        os.close(parent)
