"""Atomic fresh Task selection and lease creation."""

import json
import sqlite3
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence, Set

from .claim_validation import validate_candidate, validate_failed_candidate
from .claims import Claim, ClaimError
from .documents import TaskDefinition, _pairs
from .eligibility import _timestamp, database_blockers, rank_candidates
from .owners import OwnerIdentity, OwnerStatus, observe_owner
from .recovery_snapshots import load_recovery_snapshot
from .spec_status import is_claimable
from .store import transaction
from .workspace import WorkspaceSnapshot, capture_snapshot, compare_snapshot, snapshot_payload


def _main_root(conn: sqlite3.Connection) -> Path:
    row = next((item for item in conn.execute("PRAGMA database_list") if item[1] == "main"), None)
    if row is None or not row[2]:
        raise ClaimError("CLAIM_DATABASE_PATH_INVALID", "main database is unavailable")
    database = Path(row[2])
    if (not database.is_absolute() or database.name != "task-ledger.sqlite3" or
            database.parent.name != "runtime" or database.parent.parent.name != ".sdd"):
        raise ClaimError("CLAIM_DATABASE_PATH_INVALID", "main database path is not canonical")
    main = database.parents[2]
    if database != main / ".sdd/runtime/task-ledger.sqlite3" or main != main.resolve():
        raise ClaimError("CLAIM_DATABASE_PATH_INVALID", "main database path is not canonical")
    return main


def _insert_event(conn, run_id: str, stamp: str, snapshot, recovery_of=None) -> None:
    payload = json.dumps(snapshot_payload(snapshot, recovery_of), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 (run_id, 1, stamp, "workspace_snapshot", payload))
    if recovery_of:
        payload = json.dumps({"schema": "sdd-recovery-claim/v1", "recovery_of": recovery_of},
                             sort_keys=True, separators=(",", ":"))
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                     (run_id, 2, stamp, "recovery_claim", payload))


def _latest_abandoned(conn, task_id):
    row = conn.execute(
        "SELECT run_id,state FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return row if row is not None and row["state"] == "abandoned" else None


def _latest_failed(conn, task_id):
    row = conn.execute(
        "SELECT run_id,state FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return row if row is not None and row["state"] == "failed" else None


def _semantics_same(left, right):
    return (type(left) is WorkspaceSnapshot and type(right) is WorkspaceSnapshot and
            all(getattr(left, name) == getattr(right, name)
                for name in WorkspaceSnapshot.__dataclass_fields__ if name != "captured_at"))


def _check_recovery_event(conn, run_id):
    rows = conn.execute(
        "SELECT payload_json FROM events WHERE run_id=? AND event_type='recovery_decision'",
        (run_id,),
    ).fetchall()
    try:
        data = json.loads(rows[0][0], object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) \
            if len(rows) == 1 else None
    except (TypeError, ValueError):
        data = None
    valid = {"requeued": "unchanged", "preserved_for_recovery": "partial"}
    action = data.get("action") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or set(data) != {"schema", "action", "decision"} or
            data.get("schema") != "sdd-run-recovery/v1" or
            not isinstance(action, str) or action not in valid or
            valid[action] != data.get("decision")):
        raise ClaimError("CLAIM_RECOVERY_EVENT_INVALID", "recovery decision is invalid")
    return data["decision"]


def claim_next(
    conn: sqlite3.Connection, candidates: Sequence[TaskDefinition], satisfied_gates: Set[str],
    *, workspace_snapshots: Mapping[str, object], ide: str, owner: OwnerIdentity,
    now: str, lease_minutes: int = 120,
) -> Optional[Claim]:
    """Claim the highest-ranked fresh candidate; caller holds the common lock."""
    if conn.in_transaction:
        raise ClaimError("CLAIM_TRANSACTION_ACTIVE", "claim_next owns its transaction")
    if not isinstance(ide, str) or not ide.strip():
        raise ClaimError("CLAIM_IDE_INVALID", "ide must be a nonempty string")
    if type(lease_minutes) is not int or lease_minutes < 1:
        raise ClaimError("CLAIM_LEASE_INVALID", "lease_minutes must be a positive integer")
    if (not isinstance(owner, OwnerIdentity) or
            any(not isinstance(value, str) or not value.strip() for value in
                (owner.executor_id, owner.host_id, owner.process_started_at, owner.token)) or
            type(owner.pid) is not int or owner.pid <= 0 or
            observe_owner(owner) is not OwnerStatus.ALIVE):
        raise ClaimError("CLAIM_OWNER_NOT_ALIVE", "owner must be positively observed alive")
    instant = _timestamp(now, "now").astimezone(timezone.utc)
    claimed_at = instant.isoformat().replace("+00:00", "Z")
    try:
        expires_at = (instant + timedelta(minutes=lease_minutes)).isoformat().replace("+00:00", "Z")
    except OverflowError as exc:
        raise ClaimError("CLAIM_LEASE_INVALID", "lease expiry is outside supported time range") from exc
    main = _main_root(conn)
    result = None
    with transaction(conn, immediate=True):
        recovery_ids = {row[0] for row in conn.execute(
            "SELECT task_id FROM runs r WHERE state IN ('abandoned','failed') AND run_id=("
            "SELECT run_id FROM runs WHERE task_id=r.task_id ORDER BY attempt DESC,run_id DESC LIMIT 1)"
        )}
        seen = set()
        for candidate in rank_candidates(candidates, recovery_ids):
            task_id = candidate.metadata["task_id"]
            if task_id in seen:
                raise ClaimError("CLAIM_DUPLICATE_CANDIDATE", task_id)
            seen.add(task_id)
            row = conn.execute(
                "SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is not None and (row[0] != candidate.task_hash or row[1] != candidate.prompt_hash):
                raise ClaimError("CLAIM_CATALOG_HASH_STALE", task_id)
            if database_blockers(conn, candidate, satisfied_gates, claimed_at):
                continue
            abandoned = _latest_abandoned(conn, task_id)
            failed_retry = None
            if abandoned is not None:
                from .failed_lineage import FailedRetryLineageError, failed_retry_origin

                try:
                    if failed_retry_origin(conn, abandoned["run_id"], candidate, main) is not None:
                        failed_retry = abandoned["run_id"]
                        abandoned = None
                except FailedRetryLineageError as exc:
                    raise ClaimError(exc.code, task_id) from exc
            latest_failed = (_latest_failed(conn, task_id)
                             if abandoned is None and failed_retry is None else None)
            recovery_kind, recovery_of, failed_source, failed_candidate = None, None, None, None
            snapshot = workspace_snapshots.get(task_id)
            if abandoned is not None:
                run_id = abandoned["run_id"]
                prior_decision = _check_recovery_event(conn, run_id)
                try:
                    baseline = load_recovery_snapshot(conn, run_id, candidate, main)
                    current = capture_snapshot(main, candidate)
                    decision = compare_snapshot(baseline, current)
                except (OSError, TypeError, ValueError) as exc:
                    raise ClaimError(getattr(exc, "code", "CLAIM_RECOVERY_INVALID"), task_id) from exc
                if (not decision.recoverable or decision.kind not in {"unchanged", "partial"} or
                        (prior_decision == "unchanged" and decision.kind != "unchanged")):
                    continue
                if decision.kind == "partial":
                    if snapshot != baseline:
                        raise ClaimError("CLAIM_RECOVERY_SNAPSHOT_MISMATCH", task_id)
                    snapshot, recovery_kind, recovery_of = baseline, "partial", run_id
            elif failed_retry is not None or latest_failed is not None:
                from .failed_selection import FailedSelectionError, resolve_failed_source

                try:
                    failed_candidate = resolve_failed_source(
                        conn, failed_retry or latest_failed["run_id"], candidate, main,
                    )
                except FailedSelectionError as exc:
                    raise ClaimError(exc.code, task_id) from exc
                except ValueError as exc:
                    raise ClaimError("CLAIM_FAILED_SOURCE_INVALID", task_id) from exc
                if failed_candidate.mode == "partial":
                    if snapshot != failed_candidate.snapshot:
                        raise ClaimError("CLAIM_FAILED_SOURCE_STALE", task_id)
                    snapshot = failed_candidate.snapshot
                    recovery_of, failed_source = failed_candidate.recovery_of, failed_candidate.proof
                elif not _semantics_same(snapshot, failed_candidate.snapshot):
                    raise ClaimError("CLAIM_FAILED_SOURCE_STALE", task_id)
                else:
                    snapshot = failed_candidate.snapshot
            if snapshot is None:
                raise ClaimError("CLAIM_SNAPSHOT_MISSING", task_id)
            if failed_candidate is None:
                live, gates, spec_state = validate_candidate(
                    candidate, snapshot, main, satisfied_gates, recovery_kind,
                )
            else:
                live, gates, spec_state = validate_failed_candidate(
                    conn, candidate, failed_candidate, main, satisfied_gates,
                )
            if not is_claimable(spec_state):
                continue
            if database_blockers(conn, live, gates, claimed_at):
                continue
            if observe_owner(owner) is not OwnerStatus.ALIVE:
                raise ClaimError("CLAIM_OWNER_NOT_ALIVE", task_id)
            attempt = conn.execute(
                "SELECT COALESCE(MAX(attempt),0)+1 FROM runs WHERE task_id=?", (task_id,)
            ).fetchone()[0]
            run_id = str(uuid.uuid4())
            owner_json = json.dumps({
                "executor_id": owner.executor_id, "host_id": owner.host_id, "pid": owner.pid,
                "process_started_at": owner.process_started_at, "token": owner.token,
            }, sort_keys=True, separators=(",", ":"))
            try:
                conn.execute(
                    "INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,"
                    "agent_role,model,worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, task_id, attempt, "claimed", ide, owner.executor_id, owner_json,
                     live.metadata["agent_role"], None, live.metadata["worktree"]["path"],
                     snapshot.branch, snapshot.head, live.task_hash, live.prompt_hash, claimed_at),
                )
                conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                             (task_id, run_id, owner.token, claimed_at, claimed_at, expires_at))
                if recovery_of is None:
                    _insert_event(conn, run_id, claimed_at, snapshot)
                else:
                    _insert_event(conn, run_id, claimed_at, snapshot, recovery_of)
            except sqlite3.IntegrityError as exc:
                raise ClaimError("CLAIM_CONFLICT", task_id) from exc
            result = Claim(live, run_id, attempt, ide, owner, claimed_at, expires_at,
                           snapshot.worktree_path, snapshot.branch, snapshot.head,
                           live.task_hash, live.prompt_hash, "claimed", recovery_of, failed_source)
            break
    return result
