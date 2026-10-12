"""Repository-wide paths and maintenance locking for SDD runtime data."""

import os
import stat
import subprocess
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Iterator, Tuple

from .atomic import _open_directory

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on unsupported platforms
    fcntl = None


def repository_paths(repo_root: Path) -> Tuple[Path, Path]:
    """Return the first registered worktree and the absolute Git common dir."""
    root = Path(repo_root).resolve()
    try:
        listing = subprocess.run(
            ["git", "worktree", "list", "--porcelain"], cwd=str(root),
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout
        first = next(line[9:] for line in listing.splitlines() if line.startswith("worktree "))
        common_text = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"], cwd=str(root),
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError, StopIteration) as exc:
        raise ValueError("repository_paths: git worktree metadata unavailable") from exc
    common = Path(common_text)
    if not common.is_absolute():
        common = root / common
    return Path(first).resolve(), common.resolve()


@contextmanager
def maintenance_lock(repo_root: Path) -> Iterator[None]:
    """Hold a process lock shared by every worktree of this repository."""
    if os.name != "posix" or fcntl is None:
        raise RuntimeError("unsupported_platform: maintenance lock requires POSIX fcntl")
    _, common_dir = repository_paths(repo_root)
    common_fd = _open_directory(common_dir)
    lock_dir_fd = lock_fd = -1
    acquired = False
    try:
        with suppress(FileExistsError):
            os.mkdir("sdd", 0o700, dir_fd=common_fd)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        lock_dir_fd = os.open("sdd", directory_flags, dir_fd=common_fd)
        if not stat.S_ISDIR(os.fstat(lock_dir_fd).st_mode):
            raise OSError("path_escape: lock directory is not a directory")
        lock_fd = os.open(
            "ledger.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600,
            dir_fd=lock_dir_fd,
        )
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise OSError("path_escape: lock is not a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        acquired = True

        def verify_paths() -> None:
            pinned_dir = os.fstat(lock_dir_fd)
            current_dir = os.stat("sdd", dir_fd=common_fd, follow_symlinks=False)
            current_lock = os.stat("ledger.lock", dir_fd=lock_dir_fd, follow_symlinks=False)
            if ((pinned_dir.st_dev, pinned_dir.st_ino) != (current_dir.st_dev, current_dir.st_ino) or
                    (lock_stat.st_dev, lock_stat.st_ino) != (current_lock.st_dev, current_lock.st_ino) or
                    not stat.S_ISDIR(current_dir.st_mode) or not stat.S_ISREG(current_lock.st_mode)):
                raise OSError("path_escape: maintenance lock path was replaced")

        verify_paths()
        try:
            yield
        finally:
            verify_paths()
    finally:
        if acquired:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        if lock_fd >= 0:
            os.close(lock_fd)
        if lock_dir_fd >= 0:
            os.close(lock_dir_fd)
        os.close(common_fd)


def runtime_root(repo_root: Path) -> Path:
    """Return the main worktree runtime path without creating it."""
    main_root, _ = repository_paths(repo_root)
    return main_root / ".sdd" / "runtime"
