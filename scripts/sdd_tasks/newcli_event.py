"""Append one owner-authenticated public event from the Task CLI."""

import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .events import append_event
from .leases import LeaseError
from .locks import maintenance_lock, repository_paths
from .newcli_claim import _database
from .run_owner import resolve_run_owner
from .store import connect


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError


def _payload(raw: str) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (TypeError, ValueError, RecursionError) as exc:
        raise LeaseError("EVENT_PAYLOAD_INVALID", "payload must be a JSON object") from exc
    if not isinstance(value, dict):
        raise LeaseError("EVENT_PAYLOAD_INVALID", "payload must be a JSON object")
    return value


def event_from_cli(repo_root: Path, run_id: str, executor: str, owner_pid: int,
                   event_type: str, payload_json: str) -> dict:
    """Append a public event without exposing the persisted owner token."""
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError
    except (AttributeError, TypeError, ValueError) as exc:
        raise LeaseError("EVENT_RUN_ID_INVALID", "run_id must be a UUID") from exc
    payload = _payload(payload_json)
    main, _ = repository_paths(repo_root)
    with maintenance_lock(main), closing(connect(_database(main))) as conn:
        owner = resolve_run_owner(conn, run_id, executor, owner_pid)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event = append_event(conn, run_id, owner, event_type, payload, now=now)
    return {
        "run_id": event.run_id,
        "sequence": event.sequence,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
    }
