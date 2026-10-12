"""Resolve a live run's already-persisted owner without changing the ledger."""

import hmac
import json
import sqlite3
from datetime import datetime, timezone

from .atomic import contained
from .catalog import discover_worktrees
from .catalog_status import _live_gate_task, _metadata
from .leases import LeaseError, _main_root, _owner_token, _timestamp
from .mirrors import validate_mirrors
from .owners import OwnerIdentity, OwnerStatus, observe_owner


def resolve_run_owner(
    conn: sqlite3.Connection, run_id: str, executor_id: str, owner_pid: int
) -> OwnerIdentity:
    """Return the current owner only when its active lease and canonical Task agree."""
    if (not isinstance(run_id, str) or not run_id.strip() or
            not isinstance(executor_id, str) or not executor_id.strip() or
            type(owner_pid) is not int or owner_pid < 1):
        raise LeaseError("RUN_OWNER_IDENTITY_INVALID", "run, executor, or PID")
    try:
        row = conn.execute(
            "SELECT l.task_id AS lease_task,l.run_id AS lease_run,l.owner_token,"
            "l.claimed_at AS lease_claimed_at,l.refreshed_at AS lease_refreshed_at,"
            "l.expires_at AS lease_expires_at,r.* FROM leases l "
            "JOIN runs r ON r.run_id=l.run_id WHERE l.run_id=?", (run_id,),
        ).fetchone()
        if row is None:
            raise LeaseError("RUN_OWNER_LEASE_NOT_FOUND", run_id)
        if (row["run_id"] != run_id or row["lease_run"] != run_id or
                row["lease_task"] != row["task_id"]):
            raise LeaseError("RUN_OWNER_LEASE_MISMATCH", run_id)
        if row["state"] not in {"claimed", "running"} or row["ended_at"] is not None:
            raise LeaseError("RUN_OWNER_NOT_ACTIVE", run_id)

        token = _owner_token(row["owner_json"], run_id)
        owner_json = json.loads(row["owner_json"])
        owner = OwnerIdentity(
            owner_json["executor_id"], owner_json["host_id"], owner_json["pid"],
            owner_json["process_started_at"], token,
        )
        lease_token = row["owner_token"]
        if (row["executor_id"] != executor_id or owner.executor_id != executor_id or
                owner.pid != owner_pid or not isinstance(lease_token, str) or
                not hmac.compare_digest(token.encode("utf-8"), lease_token.encode("utf-8"))):
            raise LeaseError("RUN_OWNER_MISMATCH", run_id)
        if observe_owner(owner) != OwnerStatus.ALIVE:
            raise LeaseError("RUN_OWNER_NOT_ALIVE", run_id)

        now = datetime.now(timezone.utc)
        claimed = _timestamp(row["claimed_at"], "run.claimed_at")
        lease_claimed = _timestamp(row["lease_claimed_at"], "lease.claimed_at")
        refreshed = _timestamp(row["lease_refreshed_at"], "lease.refreshed_at")
        expires = _timestamp(row["lease_expires_at"], "lease.expires_at")
        if (claimed != lease_claimed or refreshed < claimed or refreshed > now or
                expires <= refreshed or expires <= now):
            raise LeaseError("RUN_OWNER_LEASE_INACTIVE", run_id)

        main = _main_root(conn)
        roots = discover_worktrees(main)
        if not roots or roots[0] != main:
            raise LeaseError("RUN_OWNER_AUTHORITY_INVALID", run_id)
        task_row = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks "
            "WHERE task_id=?", (row["task_id"],),
        ).fetchone()
        if task_row is None:
            raise LeaseError("RUN_OWNER_TASK_NOT_FOUND", run_id)
        metadata = _metadata(task_row)
        if metadata.get("status") != "pending":
            raise LeaseError("RUN_OWNER_TASK_NOT_PENDING", run_id)
        task = _live_gate_task(task_row, metadata, main, roots)
        authority = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        validate_mirrors(task, authority)
        if (row["task_hash"] != task.task_hash or row["prompt_hash"] != task.prompt_hash or
                row["worktree"] != task.metadata["worktree"]["path"] or
                row["branch"] != task.metadata["worktree"]["branch"] or
                row["agent_role"] != task.metadata["agent_role"]):
            raise LeaseError("RUN_OWNER_TASK_MISMATCH", run_id)
        return owner
    except LeaseError:
        raise
    except sqlite3.Error as exc:
        raise LeaseError("RUN_OWNER_STORE_ERROR", "could not inspect run owner") from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LeaseError(getattr(exc, "code", "RUN_OWNER_VALIDATION_FAILED"), run_id) from exc
