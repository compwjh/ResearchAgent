"""Bind an active retry to its immediate failed partial source."""

import sqlite3
import uuid
from pathlib import Path

from .documents import TaskDefinition
from .failure_history import _task_context
from .lease_recovery import stored_owner
from .recovery_snapshots import _event, _snapshot


class ActiveFailedRecoveryError(ValueError):
    """An active retry is not bound to a valid immediate failed source."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _reject(code: str) -> None:
    raise ActiveFailedRecoveryError(code)


def _active_source_binding(conn, active_run_id, task, repo_root):
    """Return strict source bindings only; this is not complete history proof."""
    if (not isinstance(conn, sqlite3.Connection) or not isinstance(active_run_id, str) or
            type(task) is not TaskDefinition or not isinstance(repo_root, (Path, str))):
        _reject("ACTIVE_FAILED_ARGUMENT_INVALID")
    try:
        if str(uuid.UUID(active_run_id)) != active_run_id:
            _reject("ACTIVE_FAILED_ARGUMENT_INVALID")
    except (AttributeError, TypeError, ValueError):
        _reject("ACTIVE_FAILED_ARGUMENT_INVALID")

    try:
        active = conn.execute("SELECT * FROM runs WHERE run_id=?", (active_run_id,)).fetchone()
        if (active is None or active["state"] not in {"claimed", "running"} or
                active["ended_at"] is not None):
            _reject("ACTIVE_FAILED_RUN_NOT_ACTIVE")
        payload = _event(conn, active_run_id, "workspace_snapshot", True)
        if (not isinstance(payload, dict) or set(payload) != {"schema", "source_run_id", "snapshot"} or
                payload["schema"] != "sdd-workspace-snapshot/v1"):
            _reject("ACTIVE_FAILED_SNAPSHOT_INVALID")
        source_id = payload["source_run_id"]
        if not isinstance(source_id, str) or str(uuid.UUID(source_id)) != source_id:
            _reject("ACTIVE_FAILED_SOURCE_INVALID")
        claim = _event(conn, active_run_id, "recovery_claim", True)
        if (not isinstance(claim, dict) or set(claim) != {"schema", "recovery_of"} or
                claim["schema"] != "sdd-recovery-claim/v1" or claim["recovery_of"] != source_id):
            _reject("ACTIVE_FAILED_CLAIM_MISMATCH")
        source = conn.execute("SELECT * FROM runs WHERE run_id=?", (source_id,)).fetchone()
        if (source is None or source["task_id"] != active["task_id"] or
                source["state"] != "failed" or source["ended_at"] is None or
                conn.execute("SELECT 1 FROM leases WHERE run_id=?", (source_id,)).fetchone()):
            _reject("ACTIVE_FAILED_SOURCE_INVALID")

        main, worktree, baseline = _task_context(conn, source_id, task, Path(repo_root))
        active_fields = (active["task_id"], active["task_hash"], active["prompt_hash"],
                         active["worktree"], active["branch"], active["agent_role"],
                         active["base_commit"])
        expected_fields = (task.metadata["task_id"], task.task_hash, task.prompt_hash,
                           task.metadata["worktree"]["path"], task.metadata["worktree"]["branch"],
                           task.metadata["agent_role"], baseline.head)
        source_fields = (source["task_id"], source["task_hash"], source["prompt_hash"],
                         source["worktree"], source["branch"], source["agent_role"],
                         source["base_commit"])
        if active_fields != expected_fields or source_fields != expected_fields:
            _reject("ACTIVE_FAILED_BINDING_MISMATCH")
        active_owner = stored_owner(active["owner_json"])
        if active_owner.executor_id != active["executor_id"]:
            _reject("ACTIVE_FAILED_OWNER_INVALID")
        source_id_in_snapshot, copied = _snapshot(payload, task, active, main,
                                                   baseline.common_dir, worktree)
        if source_id_in_snapshot != source_id or copied != baseline:
            _reject("ACTIVE_FAILED_BASELINE_MISMATCH")
        latest = conn.execute(
            "SELECT run_id FROM runs WHERE task_id=? ORDER BY attempt DESC LIMIT 1",
            (active["task_id"],),
        ).fetchone()
        previous = conn.execute(
            "SELECT run_id FROM runs WHERE task_id=? AND attempt<? ORDER BY attempt DESC LIMIT 1",
            (active["task_id"], active["attempt"]),
        ).fetchone()
        if latest is None or latest["run_id"] != active_run_id or previous is None or previous["run_id"] != source_id:
            _reject("ACTIVE_FAILED_ATTEMPT_ORDER_INVALID")
        return main, worktree, active, source, baseline
    except ActiveFailedRecoveryError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise ActiveFailedRecoveryError("ACTIVE_FAILED_BINDING_INVALID") from exc
