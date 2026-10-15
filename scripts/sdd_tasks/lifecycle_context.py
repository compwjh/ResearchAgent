"""Resolve an active Task claim from its canonical ledger and worktree."""
import hmac
import sqlite3
from pathlib import Path

from .active_failed_recovery import load_active_failed_source
from .atomic import contained
from .catalog_status import _gate_context, _live_gate_task, _metadata
from .claims import Claim
from .documents import TaskDefinition
from .gates import load_satisfied_gates
from .leases import _timestamp
from .owners import OwnerIdentity
from .recovery_snapshots import _event, load_recovery_snapshot
from .run_owner import resolve_run_owner
from .spec_status import is_claimable, load_spec_status
from .workspace import WorkspaceSnapshot


class LifecycleContextError(ValueError):
    """An active run could not be bound to its canonical Task context."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _same_owner(actual: OwnerIdentity, expected: OwnerIdentity) -> bool:
    fields_match = (actual.executor_id == expected.executor_id and actual.host_id == expected.host_id and
                    actual.pid == expected.pid and actual.process_started_at == expected.process_started_at)
    try:
        token_match = hmac.compare_digest(actual.token.encode("utf-8"), expected.token.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False
    return fields_match and token_match


def _active_row(conn, run_id):
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None or row["state"] not in {"claimed", "running"} or row["ended_at"] is not None:
        raise LifecycleContextError("LIFECYCLE_RUN_NOT_ACTIVE")
    lease = conn.execute(
        "SELECT task_id,run_id,owner_token,claimed_at,refreshed_at,expires_at "
        "FROM leases WHERE run_id=?", (run_id,),
    ).fetchone()
    if (lease is None or lease["run_id"] != run_id or lease["task_id"] != row["task_id"] or
            lease["claimed_at"] != row["claimed_at"]):
        raise LifecycleContextError("LIFECYCLE_LEASE_MISMATCH")
    return row, lease


def _same_run_binding(before, after) -> bool:
    fields = ("task_id", "attempt", "ide", "executor_id", "claimed_at", "base_commit",
              "task_hash", "prompt_hash", "worktree", "branch", "agent_role")
    return all(before[field] == after[field] for field in fields)


def load_active_claim(
    conn: sqlite3.Connection, run_id: str, owner: OwnerIdentity, repo_root: Path,
) -> tuple[TaskDefinition, Claim, WorkspaceSnapshot]:
    """Load an active claim and its original baseline without mutating state."""
    if (not isinstance(conn, sqlite3.Connection) or not isinstance(run_id, str) or not run_id.strip() or
            not isinstance(owner, OwnerIdentity) or not isinstance(owner.token, str) or
            not isinstance(repo_root, Path)):
        raise LifecycleContextError("LIFECYCLE_INPUT_INVALID")
    try:
        main, roots = _gate_context(conn)
        supplied = repo_root.resolve(strict=True)
        row, lease = _active_row(conn, run_id)
        initial_row, initial_lease = row, lease
        task_row = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks WHERE task_id=?",
            (row["task_id"],),
        ).fetchone()
        if task_row is None:
            raise LifecycleContextError("LIFECYCLE_TASK_MISSING")
        metadata = _metadata(task_row)
        task = _live_gate_task(task_row, metadata, main, roots)
        if not is_claimable(load_spec_status(task, main)):
            raise LifecycleContextError("LIFECYCLE_SPEC_NOT_CLAIMABLE")
        satisfied = load_satisfied_gates(task, main)
        if not set(task.metadata["required_gates"]).issubset(satisfied):
            raise LifecycleContextError("LIFECYCLE_GATES_UNSATISFIED")

        canonical = contained(main, task.metadata["worktree"]["path"]).resolve(strict=True)
        if canonical not in roots or not canonical.is_dir():
            raise LifecycleContextError("LIFECYCLE_WORKTREE_UNREGISTERED")
        if supplied not in {main, canonical}:
            raise LifecycleContextError("LIFECYCLE_REPOSITORY_UNREGISTERED")
        expected = (task.metadata["task_id"], task.metadata["worktree"]["path"],
                    task.metadata["worktree"]["branch"], task.task_hash, task.prompt_hash,
                    task.metadata["agent_role"])
        actual = (row["task_id"], row["worktree"], row["branch"], row["task_hash"],
                  row["prompt_hash"], row["agent_role"])
        if actual != expected or row["executor_id"] != owner.executor_id:
            raise LifecycleContextError("LIFECYCLE_RUN_BINDING_MISMATCH")

        resolved_owner = resolve_run_owner(conn, run_id, owner.executor_id, owner.pid)
        if not _same_owner(resolved_owner, owner):
            raise LifecycleContextError("LIFECYCLE_OWNER_MISMATCH")
        snapshot_event = _event(conn, run_id, "workspace_snapshot", True)
        recovery_of = (snapshot_event.get("source_run_id")
                      if isinstance(snapshot_event, dict) else None)
        source = (conn.execute("SELECT state,task_id FROM runs WHERE run_id=?",
                               (recovery_of,)).fetchone()
                  if isinstance(recovery_of, str) else None)
        failed_source = None
        is_failed_retry = (source is not None and source["state"] == "failed" and
                           source["task_id"] == row["task_id"])
        if (source is not None and source["state"] == "abandoned" and
                source["task_id"] == row["task_id"]):
            from .failed_lineage import failed_retry_origin

            is_failed_retry = failed_retry_origin(conn, recovery_of, task, main) is not None
        if is_failed_retry:
            failed_source = load_active_failed_source(conn, run_id, task, main)
            baseline = failed_source.baseline
        else:
            baseline = load_recovery_snapshot(conn, run_id, task, main)
        if (baseline.repo_root != main or baseline.worktree_path != canonical or
                baseline.branch != row["branch"] or baseline.head != row["base_commit"] or
                baseline.task_id != task.metadata["task_id"] or
                baseline.task_hash != task.task_hash or baseline.prompt_hash != task.prompt_hash):
            raise LifecycleContextError("LIFECYCLE_BASELINE_MISMATCH")
        recovery_of = snapshot_event["source_run_id"]

        row, lease = _active_row(conn, run_id)
        if (not _same_run_binding(initial_row, row) or
                initial_lease["owner_token"] != lease["owner_token"]):
            raise LifecycleContextError("LIFECYCLE_RUN_CHANGED")
        final_owner = resolve_run_owner(conn, run_id, owner.executor_id, owner.pid)
        if not _same_owner(final_owner, owner):
            raise LifecycleContextError("LIFECYCLE_OWNER_MISMATCH")
        if type(row["attempt"]) is not int or row["attempt"] < 1 or not isinstance(row["ide"], str) or not row["ide"].strip():
            raise LifecycleContextError("LIFECYCLE_RUN_INVALID")
        if _timestamp(lease["expires_at"], "lease.expires_at") <= _timestamp(
                lease["refreshed_at"], "lease.refreshed_at"):
            raise LifecycleContextError("LIFECYCLE_LEASE_INACTIVE")
        claim = Claim(task, run_id, row["attempt"], row["ide"], final_owner, row["claimed_at"],
                      lease["expires_at"], canonical, row["branch"], row["base_commit"],
                      row["task_hash"], row["prompt_hash"], row["state"], recovery_of,
                      failed_source=failed_source)
        return task, claim, baseline
    except LifecycleContextError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise LifecycleContextError(getattr(exc, "code", "LIFECYCLE_CONTEXT_INVALID")) from exc
