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
        live, gates, spec_state, main, authority, roots = _canonical_candidate(
            task, repo_root, satisfied_gates,
        )
        _validate_snapshot(live, snapshot, main, authority, roots, recovery_kind)
        return live, gates, spec_state
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


def _canonical_candidate(task, repo_root, satisfied_gates):
    """Resolve canonical Task authority and preserve all live claim checks."""
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
        return live, gates.intersection(satisfied_gates), spec_state, main, authority, roots
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


def validate_failed_candidate(conn, task, source, repo_root, satisfied_gates):
    """Revalidate a typed failed-source proof and its current workspace for claiming."""
    import sqlite3

    from .failed_recovery import (
        _capture,
        _same_capture,
        compare_failed_observation_current,
        load_failed_recovery_source,
    )
    from .failed_selection import FailedClaimSource
    from .failed_workspace import VerifiedFailedWorkspace, compare_verified_failed_workspace
    from .workspace import WorkspaceSnapshot

    task_id = task.metadata.get("task_id", "unknown")
    if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
        raise ClaimError("CLAIM_TRANSACTION_REQUIRED", task_id)
    live, gates, spec_state, main, _authority, _roots = _canonical_candidate(
        task, repo_root, satisfied_gates,
    )
    task_id = live.metadata["task_id"]
    try:
        if (type(source) is not FailedClaimSource or
                source.mode not in {"partial", "unchanged"} or
                type(source.proof) is not VerifiedFailedWorkspace):
            raise ValueError("failed source type or mode is invalid")
        proof = load_failed_recovery_source(conn, source.proof.source_run_id, live, main)
        decision = compare_verified_failed_workspace(proof, live)
        if (proof != source.proof or decision != source.decision or
                source.mode != decision.kind or not decision.recoverable or
                type(source.snapshot) is not WorkspaceSnapshot):
            raise ValueError("failed source proof is stale")
        current = _capture(main, live, proof.baseline)
        if compare_failed_observation_current(proof, current, live).kind != "unchanged":
            raise ValueError("failed source workspace changed")
        if source.mode == "partial":
            valid_snapshot = source.snapshot == proof.baseline
            valid_claim = (source.base_commit == proof.original_base and
                           source.recovery_of == proof.source_run_id)
        else:
            valid_snapshot = (_same_capture(source.snapshot, current) and
                              not current.status_records)
            valid_claim = (source.base_commit == proof.active_claim_tip and
                           source.recovery_of is None)
        if not valid_snapshot or not valid_claim:
            raise ValueError("failed claim does not match its verified source")
        return live, gates, spec_state
    except ClaimError:
        raise
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as exc:
        raise ClaimError("CLAIM_FAILED_SOURCE_INVALID", task_id) from exc


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
