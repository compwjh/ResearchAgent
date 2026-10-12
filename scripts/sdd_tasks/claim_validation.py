"""Revalidate canonical repository authority before a Task claim."""

import re
import subprocess
from pathlib import Path
from typing import Optional, Set, Tuple

from .atomic import contained
from .catalog import CatalogError, discover_worktrees
from .claims import ClaimError
from .documents import TaskDefinition, TaskDocumentError, parse_task
from .gates import GateEvidenceError, load_satisfied_gates
from .mirrors import MirrorError, validate_mirrors
from .spec_status import SpecStatusError, load_spec_status


def validate_candidate(
    task: TaskDefinition, snapshot, repo_root: Path, satisfied_gates: Set[str],
    recovery_kind: Optional[str] = None,
) -> Tuple[TaskDefinition, Set[str], str]:
    """Return the live canonical Task, gates confirmed in both views, and Spec state."""
    task_id = task.metadata.get("task_id", "unknown")
    try:
        main = Path(repo_root).resolve(strict=True)
        roots = discover_worktrees(main)
        if not roots or roots[0] != main:
            raise ValueError("main worktree is not first in the registry")
        authority = contained(main, task.metadata["worktree"]["path"]).resolve(strict=True)
        if authority not in roots or not authority.is_dir():
            raise ValueError("canonical Task worktree is not registered")
        spec_id = task.metadata["spec_id"]
        number = task_id.rsplit("-", 1)[-1]
        directory = contained(authority, "docs/sdd/plans/" + spec_id)
        candidates = sorted(directory.glob("task-{}-*.md".format(number)))
        if len(candidates) != 1:
            raise ValueError("canonical Task must exist exactly once")
        live = parse_task(candidates[0])
        if (live.metadata["task_id"] != task_id or live.task_hash != task.task_hash or
                live.prompt_hash != task.prompt_hash):
            raise ClaimError("CLAIM_TASK_HASH_STALE", task_id)
        validate_mirrors(live, authority)
        spec_state = load_spec_status(live, main)
        gates = load_satisfied_gates(live, main)
        _validate_snapshot(live, snapshot, main, authority, roots, recovery_kind)
        return live, gates.intersection(satisfied_gates), spec_state
    except ClaimError:
        raise
    except TaskDocumentError as exc:
        raise ClaimError(exc.code, task_id) from exc
    except MirrorError as exc:
        raise ClaimError(exc.code, task_id) from exc
    except (CatalogError, GateEvidenceError, SpecStatusError) as exc:
        raise ClaimError(exc.code, task_id) from exc
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise ClaimError("CLAIM_AUTHORITY_INVALID", task_id) from exc


def _validate_snapshot(task, snapshot, main: Path, authority: Path, roots, recovery_kind=None) -> None:
    from .locks import repository_paths
    from .workspace import WorkspaceError, capture_snapshot, compare_snapshot

    main_root, common_dir = repository_paths(main)
    worktree = task.metadata["worktree"]
    values = (
        (Path(snapshot.repo_root).resolve(strict=True), main_root),
        (Path(snapshot.common_dir).resolve(strict=True), common_dir),
        (Path(snapshot.worktree_path).resolve(strict=True), authority),
        (snapshot.spec_id, task.metadata["spec_id"]),
        (snapshot.task_id, task.metadata["task_id"]),
        (snapshot.task_hash, task.task_hash),
        (snapshot.prompt_hash, task.prompt_hash),
        (snapshot.branch, worktree["branch"]),
    )
    if any(actual != expected for actual, expected in values):
        raise ClaimError("CLAIM_SNAPSHOT_MISMATCH", task.metadata["task_id"])
    if authority not in roots or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", snapshot.head):
        raise ClaimError("CLAIM_SNAPSHOT_INVALID", task.metadata["task_id"])
    if recovery_kind is None and snapshot.status_records:
        raise ClaimError("CLAIM_WORKTREE_DIRTY", task.metadata["task_id"])
    try:
        result = subprocess.run(
            ["git", "-C", str(authority), "rev-parse", "--show-toplevel", "HEAD"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        top, head = result.stdout.splitlines()
        branch = subprocess.run(
            ["git", "-C", str(authority), "branch", "--show-current"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(authority), "status", "--porcelain=v1", "-z",
             "--untracked-files=all"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ClaimError("CLAIM_GIT_IDENTITY_INVALID", task.metadata["task_id"]) from exc
    if (Path(top).resolve(strict=True) != authority or branch != snapshot.branch or
            head != snapshot.head):
        raise ClaimError("CLAIM_SNAPSHOT_STALE", task.metadata["task_id"])
    if status and recovery_kind is None:
        raise ClaimError("CLAIM_SNAPSHOT_STALE", task.metadata["task_id"])
    try:
        current = capture_snapshot(main, task)
    except WorkspaceError as exc:
        raise ClaimError(exc.code, task.metadata["task_id"]) from exc
    decision = compare_snapshot(snapshot, current)
    allowed = {"unchanged"} if recovery_kind is None else {recovery_kind}
    if (not decision.recoverable or decision.kind not in allowed or
            (recovery_kind is None and current.status_records)):
        raise ClaimError("CLAIM_SNAPSHOT_STALE", task.metadata["task_id"])
