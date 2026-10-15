"""Transactional lease renewal for the SDD task ledger."""

import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .atomic import contained
from .documents import TaskDocumentError, parse_task
from .lease_recovery import RecoveryCheckError, require_dead_owner, verify_recovery_decision
from .recovery_snapshots import _event, load_recovery_snapshot
from .store import transaction
from .workspace import RecoveryDecision, WorkspaceError, capture_snapshot


class LeaseError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__("{}: {}".format(code, detail))


@dataclass(frozen=True)
class RecoveryReport:
    run_id: str
    state: str
    action: str


def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate owner field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("invalid JSON constant")


def _owner_token(value: str, run_id: str) -> str:
    try:
        owner = json.loads(value, object_pairs_hook=_pairs)
    except (TypeError, ValueError) as exc:
        raise LeaseError("LEASE_OWNER_INVALID", run_id) from exc
    fields = {"executor_id", "host_id", "pid", "process_started_at", "token"}
    if (not isinstance(owner, dict) or set(owner) != fields or
            any(not isinstance(owner[key], str) or not owner[key] for key in fields - {"pid"}) or
            type(owner["pid"]) is not int or owner["pid"] < 1):
        raise LeaseError("LEASE_OWNER_INVALID", run_id)
    return owner["token"]


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LeaseError("LEASE_TIMESTAMP_INVALID", field)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LeaseError("LEASE_TIMESTAMP_INVALID", field) from exc
    if parsed.utcoffset() is None:
        raise LeaseError("LEASE_TIMESTAMP_INVALID", field)
    return parsed


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def refresh_lease(
    conn: sqlite3.Connection,
    run_id: str,
    owner_token: str,
    *,
    now: str,
    lease_minutes: int = 120,
) -> str:
    """Extend one unexpired claimed/running run's lease for its matching owner."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise LeaseError("LEASE_RUN_ID_INVALID", "run_id")
    if not isinstance(owner_token, str) or not owner_token:
        raise LeaseError("LEASE_OWNER_MISMATCH", run_id)
    if type(lease_minutes) is not int or lease_minutes < 1:
        raise LeaseError("LEASE_DURATION_INVALID", "lease_minutes")
    instant = _timestamp(now, "now")
    try:
        expires_at = _utc_text(instant + timedelta(minutes=lease_minutes))
    except OverflowError as exc:
        raise LeaseError("LEASE_DURATION_INVALID", "lease_minutes") from exc
    refreshed_at = _utc_text(instant)
    if conn.in_transaction:
        raise LeaseError("LEASE_TRANSACTION_ACTIVE", "refresh_lease requires its own transaction")
    try:
        with transaction(conn, immediate=True):
            row = conn.execute(
                "SELECT l.task_id,l.owner_token,l.expires_at,r.task_id,r.state,r.owner_json "
                "FROM leases AS l "
                "JOIN runs AS r ON r.run_id=l.run_id WHERE l.run_id=?", (run_id,),
            ).fetchone()
            if row is None:
                raise LeaseError("LEASE_NOT_FOUND", run_id)
            lease_task, stored_token, expiry_text = row[0], row[1], row[2]
            run_task, run_state, owner_json = row[3], row[4], row[5]
            if lease_task != run_task:
                raise LeaseError("LEASE_BINDING_MISMATCH", run_id)
            if (not isinstance(stored_token, str) or not hmac.compare_digest(
                    stored_token.encode("utf-8"), owner_token.encode("utf-8")) or
                    not hmac.compare_digest(_owner_token(owner_json, run_id).encode("utf-8"),
                                            owner_token.encode("utf-8"))):
                raise LeaseError("LEASE_OWNER_MISMATCH", run_id)
            expiry = _timestamp(expiry_text, "lease.expires_at")
            if expiry <= instant:
                raise LeaseError("LEASE_EXPIRED", run_id)
            if run_state not in {"claimed", "running"}:
                raise LeaseError("LEASE_RUN_NOT_ACTIVE", run_id)
            updated = conn.execute(
                "UPDATE leases SET refreshed_at=?,expires_at=? WHERE run_id=?",
                (refreshed_at, expires_at, run_id),
            )
            if updated.rowcount != 1:
                raise LeaseError("LEASE_NOT_FOUND", run_id)
    except sqlite3.Error as exc:
        raise LeaseError("LEASE_STORE_ERROR", "could not refresh lease") from exc
    return expires_at


def _main_root(conn: sqlite3.Connection) -> Path:
    row = next((item for item in conn.execute("PRAGMA database_list") if item[1] == "main"), None)
    if row is None or not row[2]:
        raise LeaseError("RECOVERY_DATABASE_PATH_INVALID", "main database is unavailable")
    database = Path(row[2])
    if (not database.is_absolute() or database.name != "task-ledger.sqlite3" or
            database.parent.name != "runtime" or database.parent.parent.name != ".sdd"):
        raise LeaseError("RECOVERY_DATABASE_PATH_INVALID", "main database path is not canonical")
    main = database.parents[2]
    if database != main / ".sdd/runtime/task-ledger.sqlite3" or main != main.resolve():
        raise LeaseError("RECOVERY_DATABASE_PATH_INVALID", "main database path is not canonical")
    return main


def _live_task(conn: sqlite3.Connection, run, main: Path):
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone()
    if row is None:
        raise LeaseError("RECOVERY_TASK_MISSING", run["task_id"])
    try:
        stored = json.loads(row["definition_json"], object_pairs_hook=_pairs)
        worktree = contained(main, stored["worktree"]["path"]).resolve(strict=True)
        task = parse_task(contained(worktree, row["source_path"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LeaseError("RECOVERY_TASK_INVALID", run["task_id"]) from exc
    if (task.metadata != stored or
            row["status"] != "pending" or task.metadata["status"] != "pending" or
            row["task_hash"] != task.task_hash or row["prompt_hash"] != task.prompt_hash or
            task.metadata["task_id"] != run["task_id"] or
            run["task_hash"] != task.task_hash or run["prompt_hash"] != task.prompt_hash or
            run["worktree"] != task.metadata["worktree"]["path"] or
            run["branch"] != task.metadata["worktree"]["branch"] or
            run["agent_role"] != task.metadata["agent_role"]):
        raise LeaseError("RECOVERY_TASK_MISMATCH", run["task_id"])
    return task


def _failed_source_run_id(conn, run_id, task_id):
    payload = _event(conn, run_id, "workspace_snapshot", True)
    source_id = payload.get("source_run_id") if isinstance(payload, dict) else None
    if not isinstance(source_id, str):
        return None
    source = conn.execute("SELECT state,task_id FROM runs WHERE run_id=?", (source_id,)).fetchone()
    return source_id if source is not None and (source["state"], source["task_id"]) == (
        "failed", task_id) else None


def _verify_events(conn: sqlite3.Connection, run_id: str) -> int:
    rows = conn.execute("SELECT sequence,timestamp,event_type,payload_json FROM events "
                        "WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
    if not rows or [row[0] for row in rows] != list(range(1, len(rows) + 1)):
        raise LeaseError("RECOVERY_EVENT_INVALID", run_id)
    for row in rows:
        if not isinstance(row[2], str) or not row[2].strip():
            raise LeaseError("RECOVERY_EVENT_INVALID", run_id)
        _timestamp(row[1], "event.timestamp")
        try:
            json.loads(row[3], object_pairs_hook=_pairs, parse_constant=_reject_json_constant)
        except (TypeError, ValueError) as exc:
            raise LeaseError("RECOVERY_EVENT_INVALID", run_id) from exc
    if any(row[2] == "recovery_decision" for row in rows):
        raise LeaseError("RECOVERY_EVENT_INVALID", run_id)
    return len(rows) + 1


def recover_expired(
    conn: sqlite3.Connection,
    run_id: str,
    observed_owner_alive: bool,
    decision: RecoveryDecision,
    *,
    now: str,
) -> RecoveryReport:
    """Abandon one expired run; caller must hold the common maintenance lock."""
    if conn.in_transaction:
        raise LeaseError("RECOVERY_TRANSACTION_ACTIVE", "recover_expired owns its transaction")
    instant = _timestamp(now, "now")
    if instant.utcoffset() != timedelta(0):
        raise LeaseError("RECOVERY_TIME_INVALID", "now must be UTC")
    instant = instant.astimezone(timezone.utc)
    stamp = _utc_text(instant)
    try:
        with transaction(conn, immediate=True):
            row = conn.execute(
                "SELECT l.task_id AS lease_task,l.run_id AS lease_run,l.owner_token,l.expires_at,"
                "r.* FROM leases l JOIN runs r ON r.run_id=l.run_id WHERE l.run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise LeaseError("LEASE_NOT_FOUND", run_id)
            if row["lease_task"] != row["task_id"] or row["lease_run"] != run_id:
                raise LeaseError("RECOVERY_LEASE_MISMATCH", run_id)
            if row["state"] not in {"claimed", "running"} or row["ended_at"] is not None:
                raise LeaseError("RECOVERY_RUN_NOT_ACTIVE", run_id)
            owner = require_dead_owner(row["owner_json"], observed_owner_alive)
            if (owner.executor_id != row["executor_id"] or
                    not isinstance(row["owner_token"], str) or
                    not hmac.compare_digest(owner.token.encode(), row["owner_token"].encode())):
                raise LeaseError("RECOVERY_OWNER_MISMATCH", run_id)
            expiry = _timestamp(row["expires_at"], "lease.expires_at")
            if expiry > instant or _timestamp(row["claimed_at"], "run.claimed_at") > instant:
                raise LeaseError("LEASE_NOT_EXPIRED", run_id)
            main = _main_root(conn)
            task = _live_task(conn, row, main)
            next_sequence = _verify_events(conn, run_id)
            current = capture_snapshot(main, task)
            if _failed_source_run_id(conn, run_id, row["task_id"]) is None:
                before = load_recovery_snapshot(conn, run_id, task, main)
                actual = verify_recovery_decision(before, current, decision)
            else:
                from .active_failed_recovery import (
                    compare_active_failed_workspace,
                    load_expired_failed_source,
                )

                proof = load_expired_failed_source(conn, run_id, task, main, now=now)
                actual = compare_active_failed_workspace(proof, current, task)
                if decision != actual:
                    raise RecoveryCheckError("RECOVERY_DECISION_MISMATCH")
                if not actual.recoverable or actual.kind not in {"unchanged", "partial"}:
                    raise RecoveryCheckError("RECOVERY_WORKSPACE_CONFLICT")
            action = "requeued" if actual.kind == "unchanged" else "preserved_for_recovery"
            conn.execute("UPDATE runs SET state='abandoned',ended_at=?,error_code=? "
                         "WHERE run_id=? AND state IN('claimed','running')",
                         (stamp, "OWNER_DEAD_LEASE_EXPIRED", run_id))
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise LeaseError("RECOVERY_RUN_NOT_ACTIVE", run_id)
            deleted = conn.execute("DELETE FROM leases WHERE run_id=? AND task_id=?",
                                   (run_id, row["task_id"]))
            if deleted.rowcount != 1:
                raise LeaseError("RECOVERY_LEASE_MISMATCH", run_id)
            payload = json.dumps({"schema": "sdd-run-recovery/v1", "action": action,
                                  "decision": actual.kind}, sort_keys=True, separators=(",", ":"))
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                         (run_id, next_sequence, stamp, "recovery_decision", payload))
    except LeaseError:
        raise
    except (RecoveryCheckError, WorkspaceError, TaskDocumentError) as exc:
        raise LeaseError(getattr(exc, "code", "RECOVERY_VALIDATION_FAILED"), run_id) from exc
    except sqlite3.Error as exc:
        raise LeaseError("LEASE_STORE_ERROR", "could not recover expired run") from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LeaseError(getattr(exc, "code", "RECOVERY_VALIDATION_FAILED"), run_id) from exc
    return RecoveryReport(run_id, "abandoned", action)
