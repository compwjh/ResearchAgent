"""Private, read-only loader for a verified failed-run recovery source."""

import sqlite3
import uuid
from datetime import datetime, timezone

from .failed_workspace import (
    FailedWorkspaceError,
    VerifiedFailedWorkspace,
    _identity,
    compare_verified_failed_workspace,
)
from .failure_history import (
    FailureHistoryError,
    _git,
    _strict_json,
    _text,
    verify_failed_run_history,
)
from .recovery_snapshots import _event
from .workspace import WorkspaceSnapshot, _allowed_hashes
from .workspace_observation import (
    _decode_observation_event,
    _load_failed_run_baseline,
)


class FailedRecoveryError(ValueError):
    """A failed recovery source is stale, consumed, or lacks valid proof."""


def _canonical_uuid(value):
    return isinstance(value, str) and str(uuid.UUID(value)) == value


def _eligible_source(conn, run_id, task):
    if not _canonical_uuid(run_id):
        raise FailedRecoveryError("FAILED_RECOVERY_ARGUMENT_INVALID")
    meta = task.metadata
    task_id = meta["task_id"]
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    latest = conn.execute(
        "SELECT run_id,state FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    stored_task = conn.execute("SELECT task_hash,prompt_hash,status FROM tasks WHERE task_id=?",
                               (task_id,)).fetchone()
    if (run is None or latest is None or latest["run_id"] != run_id or
            latest["state"] != "failed" or run["state"] != "failed" or
            run["ended_at"] is None or stored_task is None or
            stored_task["status"] != "pending" or meta.get("status") != "pending" or
            (stored_task["task_hash"], stored_task["prompt_hash"]) !=
            (task.task_hash, task.prompt_hash) or
            conn.execute("SELECT 1 FROM leases WHERE task_id=? OR run_id=?",
                         (task_id, run_id)).fetchone()):
        raise FailedRecoveryError("FAILED_RECOVERY_SOURCE_INELIGIBLE")
    rows = conn.execute(
        "SELECT e.event_type,e.payload_json FROM runs r JOIN events e ON e.run_id=r.run_id "
        "WHERE r.task_id=? AND e.event_type IN ('workspace_snapshot','recovery_claim')",
        (task_id,),
    )
    for event_type, raw in rows:
        data = _strict_json(raw.encode("utf-8"))
        if event_type == "workspace_snapshot":
            if (not isinstance(data, dict) or set(data) != {"schema", "source_run_id", "snapshot"} or
                    data["schema"] != "sdd-workspace-snapshot/v1"):
                raise FailedRecoveryError("FAILED_RECOVERY_EVENTS_INVALID")
            source = data["source_run_id"]
            if source is not None and not _canonical_uuid(source):
                raise FailedRecoveryError("FAILED_RECOVERY_EVENTS_INVALID")
        else:
            if (not isinstance(data, dict) or set(data) != {"schema", "recovery_of"} or
                    data["schema"] != "sdd-recovery-claim/v1" or
                    not _canonical_uuid(data["recovery_of"])):
                raise FailedRecoveryError("FAILED_RECOVERY_EVENTS_INVALID")
            source = data["recovery_of"]
        if source == run_id:
            raise FailedRecoveryError("FAILED_RECOVERY_SOURCE_CONSUMED")
    return run


def _capture(main, task, baseline):
    worktree = baseline.worktree_path
    head = _text(_git(worktree, "rev-parse", "HEAD"))
    branch = _text(_git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD"))
    raw = _git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = tuple(item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item)
    return WorkspaceSnapshot(
        main, baseline.common_dir, worktree, task.metadata["spec_id"],
        task.metadata["task_id"], task.task_hash, task.prompt_hash, branch, head,
        records, _allowed_hashes(worktree, task.metadata["allowed_paths"]),
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _same_capture(left, right):
    return all(getattr(left, name) == getattr(right, name)
               for name in left.__dataclass_fields__ if name != "captured_at")


def load_failed_recovery_source(conn, run_id, task, repo_root):
    """Load one latest failed source after binding DB, observation, and Git proofs."""
    try:
        if not isinstance(conn, sqlite3.Connection):
            raise FailedRecoveryError("FAILED_RECOVERY_ARGUMENT_INVALID")
        _eligible_source(conn, run_id, task)
        baseline = _load_failed_run_baseline(conn, run_id, task, repo_root)
        first = _capture(baseline.repo_root, task, baseline)
        history = verify_failed_run_history(conn, run_id, task, repo_root)
        tips = dict(history.observation_tips)
        if run_id not in tips:
            raise FailedRecoveryError("FAILED_RECOVERY_OBSERVATION_MISSING")
        observation_tip = tips[run_id]
        observation = _decode_observation_event(
            conn, run_id, task, baseline.repo_root, expected_tip=observation_tip)
        proof = VerifiedFailedWorkspace(
            run_id, _identity(baseline), baseline, observation, history,
            baseline.head, observation_tip, history.current_tip,
            tuple(task.metadata["allowed_paths"]), history.excluded_paths,
        )
        decision = compare_verified_failed_workspace(proof, task)
        stored = _event(conn, run_id, "recovery_decision", False)
        if stored is not None:
            expected = {"requeued": "unchanged", "preserved_for_recovery": "partial"}
            if (not isinstance(stored, dict) or stored.get("schema") != "sdd-run-recovery/v1" or
                    stored.get("action") not in expected or
                    stored.get("decision") != expected[stored["action"]] or
                    stored["decision"] != decision.kind):
                raise FailedRecoveryError("FAILED_RECOVERY_DECISION_MISMATCH")
        last = _capture(baseline.repo_root, task, baseline)
        _eligible_source(conn, run_id, task)
        if (not _same_capture(first, last) or first.head != history.current_tip or
                last.head != history.current_tip):
            raise FailedRecoveryError("FAILED_RECOVERY_WORKSPACE_CHANGED")
        return proof
    except (FailedRecoveryError, FailureHistoryError, FailedWorkspaceError):
        raise
    except (OSError, TypeError, ValueError, KeyError, IndexError, sqlite3.Error) as exc:
        raise FailedRecoveryError("FAILED_RECOVERY_SOURCE_INVALID") from exc
