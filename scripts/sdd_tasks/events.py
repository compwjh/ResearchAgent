"""Append public run events transactionally to the local task ledger."""

import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from .event_logs import sync_event_log
from .leases import LeaseError, _main_root, _timestamp, _utc_text, _verify_events
from .owners import OwnerIdentity
from .result_schema import _scan
from .run_owner import resolve_run_owner
from .store import transaction

_PUBLIC_TYPES = frozenset({"observation", "evidence", "decision", "action", "result", "next_step"})
_OWNER_FIELDS = frozenset({"owner", "owner_token", "token", "executor_id", "host_id", "pid", "process_started_at"})


def _has_owner_fields(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key.casefold() in _OWNER_FIELDS or _has_owner_fields(item)
                   for key, item in value.items() if isinstance(key, str)) or any(
                       not isinstance(key, str) for key in value
                   )
    if isinstance(value, list):
        return any(_has_owner_fields(item) for item in value)
    return False


@dataclass(frozen=True)
class TaskEvent:
    run_id: str
    sequence: int
    timestamp: str
    event_type: str
    payload: Dict[str, Any]


def append_event(
    conn: sqlite3.Connection, run_id: str, owner: OwnerIdentity,
    event_type: str, payload: Dict[str, Any], *, now: str,
) -> TaskEvent:
    """Append one safe public event and extend its active lease in one transaction."""
    if not isinstance(event_type, str) or event_type not in _PUBLIC_TYPES:
        raise LeaseError("EVENT_TYPE_INVALID", "event_type")
    if not isinstance(payload, dict):
        raise LeaseError("EVENT_PAYLOAD_INVALID", "payload must be an object")
    try:
        _scan(payload)
        payload_json = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        )
        safe_payload = json.loads(payload_json)
        if not isinstance(safe_payload, dict):
            raise ValueError("payload must be an object")
        _scan(safe_payload)
        payload_json = json.dumps(
            safe_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        )
        payload_json = payload_json.encode("utf-8").decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LeaseError("EVENT_PAYLOAD_UNSAFE", "payload failed JSON or sensitive-content checks") from exc
    if not isinstance(owner, OwnerIdentity) or not isinstance(owner.token, str) or not owner.token:
        raise LeaseError("EVENT_OWNER_INVALID", "owner identity")
    if _has_owner_fields(safe_payload) or owner.token in payload_json:
        raise LeaseError("EVENT_PAYLOAD_UNSAFE", "payload contains private owner material")
    try:
        instant = _timestamp(now, "now")
        if instant.utcoffset() != timedelta(0):
            raise LeaseError("EVENT_TIME_INVALID", "now must be UTC")
        instant = instant.astimezone(timezone.utc)
        if instant > datetime.now(timezone.utc):
            raise LeaseError("EVENT_TIME_INVALID", "now cannot be in the future")
        stamp = _utc_text(instant)
        expires_at = _utc_text(instant + timedelta(minutes=120))
    except OverflowError as exc:
        raise LeaseError("LEASE_DURATION_INVALID", "event lease duration") from exc
    if conn.in_transaction:
        raise LeaseError("EVENT_TRANSACTION_ACTIVE", "append_event owns its transaction")
    try:
        with transaction(conn, immediate=True):
            persisted = resolve_run_owner(conn, run_id, owner.executor_id, owner.pid)
            if (persisted.executor_id != owner.executor_id or persisted.host_id != owner.host_id or
                    persisted.pid != owner.pid or persisted.process_started_at != owner.process_started_at or
                    not hmac.compare_digest(persisted.token.encode("utf-8"), owner.token.encode("utf-8"))):
                raise LeaseError("EVENT_OWNER_MISMATCH", run_id)
            lease = conn.execute(
                "SELECT task_id,run_id,refreshed_at,expires_at FROM leases WHERE run_id=?", (run_id,),
            ).fetchone()
            if lease is None or lease["run_id"] != run_id:
                raise LeaseError("EVENT_LEASE_MISSING", run_id)
            refreshed = _timestamp(lease["refreshed_at"], "lease.refreshed_at")
            expiry = _timestamp(lease["expires_at"], "lease.expires_at")
            if refreshed > instant or expiry <= instant:
                raise LeaseError("EVENT_LEASE_INACTIVE", run_id)
            sequence = _verify_events(conn, run_id)
            started = conn.execute(
                "UPDATE runs SET state='running',started_at=COALESCE(started_at,?) "
                "WHERE run_id=? AND state IN ('claimed','running') AND ended_at IS NULL",
                (stamp, run_id),
            )
            if started.rowcount != 1:
                raise LeaseError("EVENT_RUN_INACTIVE", run_id)
            updated = conn.execute(
                "UPDATE leases SET refreshed_at=?,expires_at=? WHERE task_id=? AND run_id=? AND owner_token=?",
                (stamp, expires_at, lease["task_id"], run_id, owner.token),
            )
            if updated.rowcount != 1:
                raise LeaseError("EVENT_OWNER_MISMATCH", run_id)
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                         (run_id, sequence, stamp, event_type, payload_json))
            event = TaskEvent(run_id, sequence, stamp, event_type, safe_payload)
    except LeaseError:
        raise
    except sqlite3.Error as exc:
        raise LeaseError("EVENT_STORE_ERROR", "could not append event") from exc
    try:
        sync_event_log(conn, run_id, _main_root(conn))
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise LeaseError("EVENT_LOG_SYNC_FAILED", "event is committed; local log can be rebuilt") from exc
    return event
