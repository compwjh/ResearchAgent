"""Symlink-safe path preparation for the explicit SQLite ledger connection."""

import os
import secrets
import stat
import sys
from contextlib import suppress
from pathlib import Path
from typing import Optional, Tuple


def open_parent(path: Path, create: bool = True) -> int:
    """Open a directory using dirfds; optionally create missing components as 0700."""
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ValueError("database_path_unsupported: safe directory descriptors unavailable")
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if ".." in path.parts:
        raise ValueError("database_path_invalid: parent traversal")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    current = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=current)
                child = os.open(part, flags, dir_fd=current)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ValueError("database_path_unsafe: parent is not a directory")
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _check_sidecars(parent_fd: int, name: str) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            info = os.stat(name + suffix, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("database_path_unsafe: sidecar is not a regular file")


def _publish_empty(parent_fd: int, name: str) -> Optional[Tuple[int, int]]:
    temporary = None
    descriptor = -1
    temporary_identity = None
    published_identity = None
    try:
        for _ in range(32):
            temporary = ".sdd-db-" + secrets.token_hex(12)
            try:
                descriptor = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=parent_fd,
                )
                break
            except FileExistsError:
                temporary = None
        if descriptor < 0:
            raise OSError("database_path_error: could not reserve staging file")
        info = os.fstat(descriptor)
        temporary_identity = (info.st_dev, info.st_ino)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        except FileExistsError:
            pass
        else:
            published_identity = temporary_identity
            os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temp_info = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
                if ((temp_info.st_dev, temp_info.st_ino) == temporary_identity):
                    os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
    return published_identity


def open_database_path(
    path: Path,
) -> Tuple[str, Path, int, Optional[int], Tuple[int, int]]:
    """Create parents/file safely; Linux keeps O_PATH, never an O_RDWR pin."""
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    if ".." in target.parts or not target.name or target.name in (".", ".."):
        raise ValueError("database_path_invalid: expected a file path without traversal")
    parent_fd = open_parent(target.parent)
    pin_fd = None
    try:
        _check_sidecars(parent_fd, target.name)
        try:
            existing = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            expected = _publish_empty(parent_fd, target.name)
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError("database_path_unsafe: database is not a regular file")
            expected = (existing.st_dev, existing.st_ino)
        if hasattr(os, "O_PATH") and sys.platform.startswith("linux"):
            pin_fd = os.open(target.name, os.O_PATH | os.O_NOFOLLOW, dir_fd=parent_fd)
            info = os.fstat(pin_fd)
        else:
            info = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("database_path_unsafe: database is not a regular file")
        identity = (info.st_dev, info.st_ino)
        if expected is not None and identity != expected:
            raise ValueError("database_path_changed: database entry was replaced")
        _check_sidecars(parent_fd, target.name)
        sqlite_path = f"/proc/self/fd/{pin_fd}" if pin_fd is not None else str(target)
        return sqlite_path, target, parent_fd, pin_fd, identity
    except BaseException:
        if pin_fd is not None:
            os.close(pin_fd)
        os.close(parent_fd)
        raise


def verify_database_path(
    path: Path, connection_path: str, parent_fd: int, pin_fd: Optional[int],
    identity: Tuple[int, int],
) -> None:
    """Compare requested and SQLite-resolved paths with the checked inode."""
    parent_stat = os.fstat(parent_fd)
    requested_parent = open_parent(path.parent, create=False)
    try:
        current_parent = os.fstat(requested_parent)
        entry = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if ((parent_stat.st_dev, parent_stat.st_ino) != (current_parent.st_dev, current_parent.st_ino) or
                not stat.S_ISREG(entry.st_mode) or (entry.st_dev, entry.st_ino) != identity):
            raise ValueError("database_path_changed: ledger path no longer matches pinned file")
    finally:
        os.close(requested_parent)
    if pin_fd is not None:
        pinned = os.fstat(pin_fd)
        if (pinned.st_dev, pinned.st_ino) != identity:
            raise ValueError("database_path_changed: pinned inode changed")
    _check_sidecars(parent_fd, path.name)
    resolved = Path(connection_path)
    sqlite_parent = open_parent(resolved.parent, create=False)
    try:
        resolved_parent = os.fstat(sqlite_parent)
        resolved_file = os.stat(resolved.name, dir_fd=sqlite_parent, follow_symlinks=False)
        if ((parent_stat.st_dev, parent_stat.st_ino) != (resolved_parent.st_dev, resolved_parent.st_ino) or
                not stat.S_ISREG(resolved_file.st_mode) or
                (resolved_file.st_dev, resolved_file.st_ino) != identity):
            raise ValueError("database_path_changed: SQLite opened a different file")
    finally:
        os.close(sqlite_parent)
