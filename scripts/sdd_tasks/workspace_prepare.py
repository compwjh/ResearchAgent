"""Safe create-or-validate handling for task worktrees."""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from .atomic import contained
from .locks import repository_paths
from .newdb_paths import open_parent
from .workspace import WorkspaceError, WorkspaceSnapshot, _git, capture_snapshot, compare_snapshot


def _registered(root: Path) -> dict:
    result, path, branch = {}, None, None
    listing = _git(root, "worktree", "list", "--porcelain").decode("utf-8", "surrogateescape")
    for line in listing.splitlines() + [""]:
        if line.startswith("worktree "):
            if path is not None:
                result[Path(path).resolve()] = branch
            path, branch = line[9:], None
        elif line.startswith("branch "):
            branch = line[7:]
        elif not line and path is not None:
            result[Path(path).resolve()] = branch
            path, branch = None, None
    return result


def _common(worktree: Path) -> Path:
    value = Path(_git(worktree, "rev-parse", "--git-common-dir").decode().strip())
    return (value if value.is_absolute() else worktree / value).resolve()


def _verify_identity(snapshot: WorkspaceSnapshot, main: Path, common: Path,
                     worktree: Path, metadata: dict, base_commit: str,
                     task_hash: str, prompt_hash: str) -> None:
    expected = (main, common, worktree, metadata["spec_id"], metadata["task_id"],
                task_hash, prompt_hash, metadata["worktree"]["branch"], base_commit)
    actual = (snapshot.repo_root, snapshot.common_dir, snapshot.worktree_path,
              snapshot.spec_id, snapshot.task_id, snapshot.task_hash, snapshot.prompt_hash,
              snapshot.branch, snapshot.head)
    if actual != expected:
        raise WorkspaceError("workspace_recovery_identity_mismatch")


def prepare_worktree(repo_root: Path, task, base_commit: str, *,
                     recovery_snapshot: Optional[WorkspaceSnapshot] = None) -> WorkspaceSnapshot:
    main, common = repository_paths(repo_root)
    metadata = task.metadata
    branch = metadata["worktree"]["branch"]
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base_commit):
        raise WorkspaceError("workspace_base_commit_invalid")
    if _git(main, "rev-parse", "--verify", base_commit + "^{commit}").decode().strip() != base_commit:
        raise WorkspaceError("workspace_base_commit_invalid")
    try:
        path = contained(main, metadata["worktree"]["path"]).resolve()
    except (OSError, ValueError) as exc:
        raise WorkspaceError("workspace_worktree_path_invalid") from exc

    worktrees = _registered(main)
    exists = path in worktrees
    if recovery_snapshot is not None and not exists:
        raise WorkspaceError("workspace_recovery_worktree_missing")
    if exists and worktrees[path] != "refs/heads/" + branch:
        raise WorkspaceError("workspace_branch_mismatch")
    try:
        parent_fd = open_parent(path.parent, create=not exists)
        os.close(parent_fd)
    except OSError as exc:
        raise WorkspaceError("workspace_worktree_path_invalid") from exc
    if not exists:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise WorkspaceError("workspace_worktree_unregistered")
        if "refs/heads/" + branch in worktrees.values():
            raise WorkspaceError("workspace_branch_already_registered")
        ref = subprocess.run(["git", "-C", str(main), "show-ref", "--verify", "--quiet", "refs/heads/" + branch], check=False)
        if ref.returncode == 0:
            raise WorkspaceError("workspace_branch_already_exists")
        if ref.returncode != 1:
            raise WorkspaceError("workspace_git_failed")
        try:
            _git(main, "worktree", "add", "-b", branch, str(path), base_commit)
        except WorkspaceError as exc:
            raise WorkspaceError("workspace_worktree_create_failed") from exc
        worktrees = _registered(main)
        if worktrees.get(path) != "refs/heads/" + branch:
            raise WorkspaceError("workspace_worktree_registration_failed")

    if _common(path) != common:
        raise WorkspaceError("workspace_common_dir_mismatch")
    head = _git(path, "rev-parse", "HEAD").decode().strip()
    if head != base_commit:
        raise WorkspaceError("workspace_base_commit_mismatch")
    current = capture_snapshot(main, task)
    if recovery_snapshot is None:
        if current.status_records:
            raise WorkspaceError("workspace_worktree_dirty")
        return current
    _verify_identity(recovery_snapshot, main, common, path, metadata, base_commit,
                     task.task_hash, task.prompt_hash)
    decision = compare_snapshot(recovery_snapshot, current)
    if not decision.recoverable or decision.kind not in {"unchanged", "partial"}:
        raise WorkspaceError("workspace_recovery_conflict")
    return current
