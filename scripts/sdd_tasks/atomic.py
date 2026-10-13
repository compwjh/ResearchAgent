"""Durable file writes and repository-relative path containment."""

import hashlib
import json
import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Union


class AtomicWriteError(OSError):
    """Write failure with enough state for callers to recover after replace."""

    def __init__(self, phase: str, replaced: bool, expected_hash: str, cause: OSError):
        self.phase = phase
        self.replaced = replaced
        self.expected_hash = expected_hash
        super().__init__(f"atomic_write: {phase}: {cause}")


def _open_directory(path: Path) -> int:
    """Open an existing directory by walking from root without following links."""
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise OSError("unsupported_platform: safe directory descriptors unavailable")
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if ".." in path.parts:
        raise OSError("path_escape: parent traversal is not allowed")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    current = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            if part in ("", "."):
                continue
            child = os.open(part, flags, dir_fd=current)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise OSError("path_escape: parent is not a directory")
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def read_text(path: Path) -> str:
    """Read one regular UTF-8 file through a pinned, symlink-free parent."""
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise OSError("unsupported_platform: safe file descriptors unavailable")
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    parent_fd = file_fd = -1
    try:
        if not target.name or target.name in (".", ".."):
            raise OSError("path_escape: invalid file name")
        parent_fd = _open_directory(target.parent)
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        file_fd = os.open(target.name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise OSError("path_escape: source is not a regular file")
        with os.fdopen(file_fd, "r", encoding="utf-8", newline="") as source:
            file_fd = -1
            return source.read()
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def atomic_write(path: Path, content: Union[str, bytes], *, executable: bool = False) -> None:
    """Durably replace a regular file through a pinned, symlink-free directory."""
    if type(executable) is not bool:
        raise TypeError("executable must be a bool")
    temporary_mode = 0o700 if executable else 0o600
    payload = content.encode("utf-8") if isinstance(content, str) else content
    expected_hash = hashlib.sha256(payload).hexdigest()
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    parent_fd = temp_fd = -1
    temporary = None
    replaced = False
    phase = "open_parent"
    try:
        if not target.name or target.name in (".", ".."):
            raise OSError("path_escape: invalid target name")
        parent_fd = _open_directory(target.parent)
        phase = "inspect_target"
        try:
            existing = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent_fd)
        except FileNotFoundError:
            existing = -1
        if existing >= 0:
            try:
                if not stat.S_ISREG(os.fstat(existing).st_mode):
                    raise OSError("path_escape: target is not a regular file")
            finally:
                os.close(existing)
        phase = "create_temp"
        for _ in range(32):
            temporary = f".sdd-atomic-{secrets.token_hex(12)}"
            try:
                temp_fd = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    temporary_mode, dir_fd=parent_fd,
                )
                break
            except FileExistsError:
                temporary = None
        if temp_fd < 0:
            raise OSError("atomic_write: could not reserve temporary file")
        phase = "write_temp"
        os.fchmod(temp_fd, temporary_mode)
        with os.fdopen(temp_fd, "wb") as stream:
            temp_fd = -1
            stream.write(payload)
            stream.flush()
            phase = "fsync_file"
            os.fsync(stream.fileno())
        phase = "replace"
        os.replace(temporary, target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        replaced = True
        phase = "fsync_directory"
        os.fsync(parent_fd)
    except AtomicWriteError:
        raise
    except (OSError, ValueError) as exc:
        raise AtomicWriteError(phase, replaced, expected_hash, exc) from exc
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temporary is not None and parent_fd >= 0:
            with suppress(OSError):
                os.unlink(temporary, dir_fd=parent_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def write_json(path: Path, data: Any) -> None:
    """Write canonical UTF-8 JSON followed by one LF."""
    content = json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ) + "\n"
    atomic_write(path, content)


def contained(root: Path, relative: str) -> Path:
    """Return a strict POSIX relative path, rejecting symlink components."""
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise ValueError("path_escape: expected a contained relative path")
    parts = relative.split("/")
    windows = PureWindowsPath(relative)
    if (PurePosixPath(relative).is_absolute() or windows.is_absolute() or windows.drive or
            any(part in ("", ".", "..") or any(c in part for c in '*?[]:"<>|') for part in parts)):
        raise ValueError("path_escape: expected a contained relative path")
    base = Path(root).resolve()
    try:
        parent_fd = _open_directory(base)
    except OSError as exc:
        raise ValueError("path_escape: invalid root") from exc
    missing_parent = False
    try:
        for part in parts[:-1]:
            try:
                child = os.open(
                    part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                missing_parent = True
                break
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ValueError("path_escape: component is not a directory")
            os.close(parent_fd)
            parent_fd = child
        try:
            info = None if missing_parent else os.stat(
                parts[-1], dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            info = None
        if info is not None and stat.S_ISLNK(info.st_mode):
            raise ValueError("path_escape: symlink component")
    except OSError as exc:
        raise ValueError("path_escape: symlink or invalid component") from exc
    finally:
        os.close(parent_fd)
    return base.joinpath(*parts)
