"""Pure validation helpers for an expired lease recovery attempt."""

import json
from typing import Any, Dict, List

from .owners import OwnerIdentity, OwnerStatus, observe_owner
from .workspace import RecoveryDecision, WorkspaceSnapshot, compare_snapshot


class RecoveryCheckError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _unique_object(pairs: List[Any]) -> Dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate owner field")
        value[key] = item
    return value


def stored_owner(owner_json: str) -> OwnerIdentity:
    """Decode the exact persisted OwnerIdentity shape without exposing its token."""
    try:
        data = json.loads(owner_json, object_pairs_hook=_unique_object)
    except (TypeError, ValueError) as exc:
        raise RecoveryCheckError("RECOVERY_OWNER_INVALID") from exc
    fields = {"executor_id", "host_id", "pid", "process_started_at", "token"}
    if (not isinstance(data, dict) or set(data) != fields or
            any(not isinstance(data[key], str) or not data[key]
                for key in fields - {"pid"}) or
            type(data["pid"]) is not int or data["pid"] < 1):
        raise RecoveryCheckError("RECOVERY_OWNER_INVALID")
    return OwnerIdentity(data["executor_id"], data["host_id"], data["pid"],
                         data["process_started_at"], data["token"])


def require_dead_owner(owner_json: str, observed_owner_alive: bool) -> OwnerIdentity:
    """Require both the caller observation and a fresh local identity check to agree."""
    if type(observed_owner_alive) is not bool:
        raise RecoveryCheckError("RECOVERY_OWNER_OBSERVATION_INVALID")
    owner = stored_owner(owner_json)
    actual = observe_owner(owner)
    if observed_owner_alive or actual is OwnerStatus.ALIVE:
        raise RecoveryCheckError("RECOVERY_OWNER_ALIVE")
    if actual is not OwnerStatus.DEAD:
        raise RecoveryCheckError("RECOVERY_OWNER_UNKNOWN")
    return owner


def verify_recovery_decision(
    before: WorkspaceSnapshot,
    current: WorkspaceSnapshot,
    decision: RecoveryDecision,
) -> RecoveryDecision:
    """Recompute the workspace decision and reject partial or forged summaries."""
    if (type(before) is not WorkspaceSnapshot or type(current) is not WorkspaceSnapshot or
            type(decision) is not RecoveryDecision):
        raise RecoveryCheckError("RECOVERY_WORKSPACE_INVALID")
    actual = compare_snapshot(before, current)
    if decision != actual:
        raise RecoveryCheckError("RECOVERY_DECISION_MISMATCH")
    if not actual.recoverable or actual.kind not in {"unchanged", "partial"}:
        raise RecoveryCheckError("RECOVERY_WORKSPACE_CONFLICT")
    return actual
