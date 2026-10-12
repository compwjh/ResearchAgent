"""Read-only SQL checks and deterministic candidate ordering for claims."""

from datetime import datetime
from typing import Iterable, List, Set, Tuple

from .claims import ClaimError
from .documents import TaskDefinition


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ClaimError("CLAIM_TIMESTAMP_INVALID", field)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ClaimError("CLAIM_TIMESTAMP_INVALID", field) from exc
    if parsed.utcoffset() is None:
        raise ClaimError("CLAIM_TIMESTAMP_INVALID", field)
    return parsed


def rank_candidates(
    candidates: Iterable[TaskDefinition], recoverable_task_ids: Iterable[str] = (),
) -> List[TaskDefinition]:
    recovery = set(recoverable_task_ids)
    return sorted(candidates, key=lambda task: (
        task.metadata["task_id"] not in recovery,
        -task.metadata.get("priority", 100),
        _timestamp(task.metadata["created_at"], "created_at"),
        task.metadata["task_id"],
    ))


def database_blockers(
    conn, task: TaskDefinition, satisfied_gates: Set[str], now: str,
) -> Tuple[str, ...]:
    """Return current ledger blockers without changing rows or Task documents."""
    instant = _timestamp(now, "now")
    task_id = task.metadata["task_id"]
    row = conn.execute(
        "SELECT task_hash,prompt_hash,status FROM tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    if row is None:
        return ("task_missing_from_catalog",)
    blockers = []
    if row[0] != task.task_hash or row[1] != task.prompt_hash:
        blockers.append("task_hash_stale")
    if row[2] != "pending" or task.metadata["status"] != "pending":
        blockers.append("task_status_not_pending")
    if task.metadata.get("migration_state") == "unverified":
        blockers.append("migration_unverified")
    expected = set(task.metadata["depends_on"])
    indexed = {item[0] for item in conn.execute(
        "SELECT depends_on FROM dependencies WHERE task_id=?", (task_id,)
    )}
    if indexed != expected:
        blockers.append("dependency_index_stale")
    for dependency in sorted(expected):
        found = conn.execute("SELECT status FROM tasks WHERE task_id=?", (dependency,)).fetchone()
        if found is None:
            blockers.append("dependency_missing:" + dependency)
        elif found[0] != "completed":
            blockers.append("dependency_not_completed:" + dependency)
    for gate in task.metadata["required_gates"]:
        if gate not in satisfied_gates:
            blockers.append("gate_unsatisfied:" + gate)
    lease = conn.execute("SELECT expires_at FROM leases WHERE task_id=?", (task_id,)).fetchone()
    if lease is not None:
        expiry = _timestamp(lease[0], "lease.expires_at")
        blockers.append("active_lease" if expiry > instant else "expired_lease_requires_recovery")
    active = conn.execute(
        "SELECT 1 FROM runs WHERE task_id=? AND state IN ('claimed','running') LIMIT 1",
        (task_id,),
    ).fetchone()
    if active is not None and "active_lease" not in blockers:
        blockers.append("active_run")
    limit = task.metadata.get("max_attempts", 3)
    if type(limit) is not int or limit < 1:
        raise ClaimError("TASK_ATTEMPT_LIMIT_INVALID", task_id)
    failures = 0
    for run in conn.execute(
        "SELECT state FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id ASC", (task_id,)
    ):
        if run[0] != "failed":
            break
        failures += 1
    if failures >= limit:
        blockers.append("max_attempts_exhausted")
    return tuple(blockers)


def eligible_candidates(
    conn, candidates: Iterable[TaskDefinition], satisfied_gates: Set[str], now: str,
    recoverable_task_ids: Iterable[str] = (),
) -> List[TaskDefinition]:
    ordered = rank_candidates(candidates, recoverable_task_ids)
    return [task for task in ordered if not database_blockers(conn, task, satisfied_gates, now)]
