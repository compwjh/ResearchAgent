import os
import secrets
import stat
import sys
from contextlib import suppress
from pathlib import Path

from .atomic import contained
from .newdb_paths import open_parent


def pin_runtime(database: Path, main_root: Path):
    expected = Path(main_root) / ".sdd/runtime/task-ledger.sqlite3"
    if database != expected:
        raise ValueError("database_path_invalid: expected fixed main-worktree path")
    contained(main_root, ".sdd/runtime/task-ledger.sqlite3")
    if (not sys.platform.startswith("linux") or os.open not in os.supports_dir_fd or
            os.link not in os.supports_dir_fd):
        raise ValueError("database_path_unsupported: safe dirfd publication unavailable")
    parent_fd = open_parent(database.parent, create=True)
    try:
        try:
            info = os.stat(database.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return parent_fd, False
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("database_path_unsafe: database is not regular")
        return parent_fd, True
    except BaseException:
        os.close(parent_fd)
        raise

def create_stage(parent_fd: int):
    for _ in range(32):
        name = ".task-ledger-" + secrets.token_hex(12) + ".sqlite3"
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                         dir_fd=parent_fd)
            os.close(fd)
            return name
        except FileExistsError:
            continue
    raise OSError("database_path_stage_failed: could not reserve staging file")

def verify_parent(path: Path, parent_fd: int) -> None:
    current = open_parent(path, create=False)
    try:
        pinned, named = os.fstat(parent_fd), os.fstat(current)
        if (pinned.st_dev, pinned.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("database_path_changed: runtime directory was replaced")
    finally:
        os.close(current)

def publish_stage(parent_fd: int, name: str, database_name: str) -> None:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("database_path_unsafe: staging file")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.link(name, database_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)

def discard_stage(parent_fd: int, name: str) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        with suppress(FileNotFoundError):
            os.unlink(name + suffix, dir_fd=parent_fd)
