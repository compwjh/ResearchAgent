import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from .atomic import _open_directory, contained
from .locks import repository_paths


class WorkspaceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WorkspaceSnapshot:
    repo_root: Path
    common_dir: Path
    worktree_path: Path
    spec_id: str
    task_id: str
    task_hash: str
    prompt_hash: str
    branch: str
    head: str
    status_records: Tuple[str, ...]
    allowed_hashes: Dict[str, Optional[str]]
    captured_at: str


@dataclass(frozen=True)
class RecoveryDecision:
    kind: str
    changed_paths: Tuple[str, ...]
    out_of_scope_paths: Tuple[str, ...]
    recoverable: bool
    error_code: Optional[str]


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("workspace_git_failed") from exc


def _digest(fd: int) -> str:
    digest = hashlib.sha256()
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _open_node(parent_fd: int, name: str, expected, directory: bool) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    if directory:
        flags |= os.O_DIRECTORY
    fd = os.open(name, flags, dir_fd=parent_fd)
    actual = os.fstat(fd)
    valid_type = stat.S_ISDIR(actual.st_mode) if directory else stat.S_ISREG(actual.st_mode)
    if not valid_type or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        os.close(fd)
        raise WorkspaceError("workspace_path_changed")
    return fd


def _hash_node(parent_fd: int, name: str, relative: str, result: dict) -> None:
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode):
        result[relative] = None
        fd = _open_node(parent_fd, name, info, True)
        try:
            _hash_tree(fd, relative, result)
        finally:
            os.close(fd)
    elif stat.S_ISREG(info.st_mode):
        fd = _open_node(parent_fd, name, info, False)
        try:
            result[relative] = _digest(fd)
        finally:
            os.close(fd)
    else:
        raise WorkspaceError("workspace_path_unsafe")


def _hash_tree(root_fd: int, prefix: str, result: dict) -> None:
    for name in sorted(os.listdir(root_fd)):
        relative = prefix + "/" + name if prefix else name
        _hash_node(root_fd, name, relative, result)


def _allowed_hashes(root: Path, allowed: list) -> Dict[str, Optional[str]]:
    result = {}
    for relative in allowed:
        try:
            path = contained(root, relative)
            parent_fd = _open_directory(path.parent)
            try:
                _hash_node(parent_fd, path.name, relative, result)
            finally:
                os.close(parent_fd)
        except FileNotFoundError:
            result[relative] = None
        except (OSError, ValueError) as exc:
            if isinstance(exc, WorkspaceError):
                raise
            raise WorkspaceError("workspace_path_unsafe") from exc
    return result


def capture_snapshot(repo_root: Path, task) -> WorkspaceSnapshot:
    main, common = repository_paths(repo_root)
    metadata = task.metadata
    relative = metadata["worktree"]["path"]
    try:
        worktree = contained(main, relative).resolve(strict=True)
        registered = {Path(line[9:]).resolve() for line in _git(main, "worktree", "list", "--porcelain").decode().splitlines() if line.startswith("worktree ")}
    except (OSError, ValueError) as exc:
        raise WorkspaceError("workspace_worktree_invalid") from exc
    if worktree not in registered:
        raise WorkspaceError("workspace_worktree_unregistered")
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    if branch != metadata["worktree"]["branch"]:
        raise WorkspaceError("workspace_branch_mismatch")
    status = _git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = tuple(item.decode("utf-8", "surrogateescape") for item in status.split(b"\0") if item)
    return WorkspaceSnapshot(main, common, worktree, metadata["spec_id"], metadata["task_id"], task.task_hash,
                             task.prompt_hash, branch, _git(worktree, "rev-parse", "HEAD").decode().strip(), records,
                             _allowed_hashes(worktree, metadata["allowed_paths"]), datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))


def _status_paths(records: Tuple[str, ...]) -> dict:
    result, index = {}, 0
    while index < len(records):
        item = records[index]
        if len(item) < 4 or item[2] != " ":
            raise WorkspaceError("workspace_status_invalid")
        code, path = item[:2], item[3:]
        result[path] = code
        if "R" in code or "C" in code:
            index += 1
            if index == len(records):
                raise WorkspaceError("workspace_status_invalid")
            result[records[index]] = code
        index += 1
    return result


def compare_snapshot(before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> RecoveryDecision:
    identity = ("repo_root", "common_dir", "worktree_path", "spec_id", "task_id", "task_hash",
                "prompt_hash", "branch", "head")
    if any(getattr(before, field) != getattr(after, field) for field in identity):
        return RecoveryDecision("conflict", (), (), False, "workspace_identity_mismatch")
    old_status, new_status = _status_paths(before.status_records), _status_paths(after.status_records)
    changed = {path for path in old_status.keys() | new_status.keys() if old_status.get(path) != new_status.get(path)}
    changed.update(path for path in before.allowed_hashes.keys() | after.allowed_hashes.keys() if before.allowed_hashes.get(path) != after.allowed_hashes.get(path))
    changed_paths = tuple(sorted(changed))
    hashes = {**before.allowed_hashes, **after.allowed_hashes}
    roots = {path for path, digest in hashes.items() if digest is None}
    roots.update(path for path in hashes if not any(path.startswith(parent + "/") for parent in roots))
    outside = tuple(path for path in changed_paths if not any(path == root or path.startswith(root + "/") for root in roots))
    if outside:
        return RecoveryDecision("out_of_scope", changed_paths, outside, False, "workspace_out_of_scope")
    kind = "partial" if changed_paths else "unchanged"
    return RecoveryDecision(kind, changed_paths, (), True, None)


def snapshot_payload(snapshot: WorkspaceSnapshot, source_run_id: Optional[str] = None) -> dict:
    values = {name: os.fspath(getattr(snapshot, name)) if name in {"repo_root", "common_dir", "worktree_path"} else getattr(snapshot, name) for name in snapshot.__dataclass_fields__}
    values["status_records"] = list(snapshot.status_records)
    values["allowed_hashes"] = dict(sorted(snapshot.allowed_hashes.items()))
    return {"schema": "sdd-workspace-snapshot/v1", "source_run_id": source_run_id, "snapshot": values}


def prepare_worktree(repo_root: Path, task, base_commit: str, *,
                     recovery_snapshot: Optional[WorkspaceSnapshot] = None) -> WorkspaceSnapshot:
    from .workspace_prepare import prepare_worktree as prepare
    return prepare(repo_root, task, base_commit, recovery_snapshot=recovery_snapshot)
