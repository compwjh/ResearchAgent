"""Read-only snapshots of a registered worktree's real Git index."""
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Sequence

from . import atomic
from .journal_fields import validate_object_id, validate_paths

_MODES = {"100644", "100755", "120000", "160000"}


class GitIndexError(ValueError):
    pass


def _git(root: Path, *args: str, allow_difference: bool = False) -> bytes:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(["git", "-C", os.fspath(root), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env)
        if result.returncode == 1 and allow_difference:
            raise GitIndexError("GIT_TARGET_PRESTAGED")
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, result.args)
        return result.stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitIndexError("GIT_INDEX_COMMAND_FAILED") from exc


def _line_path(raw: bytes) -> str:
    if not raw.endswith(b"\n"):
        raise GitIndexError("GIT_INDEX_PATH_INVALID")
    return os.fsdecode(raw[:-1])


def _registered(root: Path) -> bool:
    data = _git(root, "worktree", "list", "--porcelain", "-z")
    return data.count(b"worktree " + os.fsencode(root) + b"\0") == 1


def _index_state(path: Path):
    parent = fd = -1
    try:
        parent = atomic._open_directory(path.parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GitIndexError("GIT_INDEX_NOT_REGULAR")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        before_stamp = (before.st_dev, before.st_ino, before.st_mode, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns)
        after_stamp = (after.st_dev, after.st_ino, after.st_mode, after.st_size,
                       after.st_mtime_ns, after.st_ctime_ns)
        if before_stamp != after_stamp:
            raise GitIndexError("GIT_INDEX_CHANGED_DURING_READ")
        return digest.hexdigest(), after_stamp
    except GitIndexError:
        raise
    except OSError as exc:
        raise GitIndexError("GIT_INDEX_UNSAFE_OR_UNREADABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if parent >= 0:
            os.close(parent)


def _parse_index(data: bytes):
    if data and not data.endswith(b"\0"):
        raise GitIndexError("GIT_INDEX_ENTRIES_INVALID")
    entries, seen = [], set()
    try:
        for record in data[:-1].split(b"\0") if data else ():
            header, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
            entry = {"path": path, "stage": int(stage), "mode": mode, "object_id": object_id}
            if mode not in _MODES or entry["stage"] not in range(4):
                raise ValueError("mode_or_stage")
            validate_object_id(object_id, "index.object_id")
            identity = (raw_path, entry["stage"])
            if identity in seen:
                raise ValueError("duplicate")
            seen.add(identity)
            entries.append(entry)
    except (UnicodeError, ValueError) as exc:
        raise GitIndexError("GIT_INDEX_ENTRIES_INVALID") from exc
    return entries


def read_index_snapshot(worktree: Path, committed_paths: Sequence[str], *, original_head: str) -> dict:
    """Capture the exact initial index state, rejecting target staging and races."""
    try:
        root = Path(worktree).resolve(strict=True)
        if not root.is_dir() or not _registered(root):
            raise GitIndexError("GIT_WORKTREE_UNREGISTERED")
        if not isinstance(committed_paths, Sequence) or isinstance(committed_paths, (str, bytes)):
            raise GitIndexError("GIT_INDEX_TARGETS_INVALID")
        paths = validate_paths(list(committed_paths), "committed_paths")
        validate_object_id(original_head, "original_head")
    except GitIndexError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise GitIndexError("GIT_INDEX_INPUT_INVALID") from exc
    top = _line_path(_git(root, "rev-parse", "--show-toplevel"))
    if os.fsencode(top) != os.fsencode(root):
        raise GitIndexError("GIT_WORKTREE_ROOT_MISMATCH")
    git_dir = _line_path(_git(root, "rev-parse", "--absolute-git-dir"))
    index_path = _line_path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    expected_index = os.path.join(git_dir, "index")
    if not os.path.isabs(index_path) or os.path.normpath(index_path) != os.path.normpath(expected_index):
        raise GitIndexError("GIT_INDEX_PATH_MISMATCH")
    index = Path(index_path)
    head_before = _line_path(_git(root, "rev-parse", "HEAD"))
    if head_before != original_head:
        raise GitIndexError("GIT_HEAD_CHANGED")
    initial_hash, initial_stat = _index_state(index)
    entries = _parse_index(_git(root, "ls-files", "--stage", "-z"))
    targets = set(paths)
    if any(entry["stage"] for entry in entries if entry["path"] in targets):
        raise GitIndexError("GIT_TARGET_UNMERGED")
    if paths:
        _git(root, "diff-index", "--cached", "--quiet", original_head, "--",
             *[":(literal)" + path for path in paths], allow_difference=True)
    final_hash, final_stat = _index_state(index)
    head_after = _line_path(_git(root, "rev-parse", "HEAD"))
    if (initial_hash, initial_stat) != (final_hash, final_stat) or head_after != original_head:
        raise GitIndexError("GIT_INDEX_OR_HEAD_CHANGED")
    targets_set = set(paths)
    committed = sorted((entry for entry in entries if entry["path"] in targets_set),
                       key=lambda entry: (entry["path"].encode("utf-8"), entry["stage"]))
    others = sorted((entry for entry in entries if entry["path"] not in targets_set),
                    key=lambda entry: (entry["path"].encode("utf-8"), entry["stage"]))
    encoded = json.dumps(others, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {"git_index_path": index_path, "index_sha256": initial_hash, "committed_entries": committed,
            "other_entries_sha256": hashlib.sha256(encoded).hexdigest()}
