"""Read-only scheduling status derived from the rebuilt task ledger."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .atomic import contained
from .claims import ClaimError
from .documents import TaskDocumentError, parse_task
from .eligibility import database_blockers
from .gates import GateEvidenceError, load_satisfied_gates
from .recovery_snapshots import load_recovery_snapshot
from .spec_status import SpecStatusError, is_claimable, load_spec_status
from .workspace import capture_snapshot, compare_snapshot


def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("invalid JSON constant: " + value)


def _metadata(row: dict) -> dict:
    from .catalog import CatalogError

    try:
        meta = json.loads(row["definition_json"], object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (TypeError, ValueError) as exc:
        raise CatalogError("CATALOG_DATA_INVALID", row["task_id"]) from exc
    if (not isinstance(meta, dict) or meta.get("task_id") != row["task_id"] or
            meta.get("status") != row["status"] or
            not isinstance(meta.get("required_gates"), list) or
            any(not isinstance(gate, str) for gate in meta["required_gates"]) or
            not isinstance(row["task_hash"], str) or
            not re.fullmatch(r"[0-9a-f]{64}", row["task_hash"]) or
            not isinstance(row["prompt_hash"], str) or
            not re.fullmatch(r"[0-9a-f]{64}", row["prompt_hash"])):
        raise CatalogError("CATALOG_DATA_INVALID", row["task_id"])
    canonical = {key: value for key, value in meta.items() if key not in {"status", "migration_state"}}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256((payload + "\n" + row["prompt_hash"]).encode("utf-8")).hexdigest()
    if actual != row["task_hash"]:
        raise CatalogError("CATALOG_DATA_INVALID", row["task_id"])
    return meta


def _gate_context(conn: sqlite3.Connection):
    from .catalog import CatalogError, discover_worktrees

    filename = next((row[2] for row in conn.execute("PRAGMA database_list")
                     if row[1] == "main"), "")
    database = Path(filename)
    if (not filename or not database.is_absolute() or database.name != "task-ledger.sqlite3" or
            database.parent.name != "runtime" or database.parent.parent.name != ".sdd"):
        raise CatalogError("GATE_DATABASE_PATH_INVALID", filename or "main database path unavailable")
    main = database.parents[2]
    if database != main / ".sdd/runtime/task-ledger.sqlite3" or main != main.resolve():
        raise CatalogError("GATE_DATABASE_PATH_INVALID", str(database))
    roots = discover_worktrees(main)
    if not roots or roots[0] != main:
        raise CatalogError("GATE_AUTHORITY_INVALID", str(main))
    return main, roots


def _live_gate_task(row: dict, meta: dict, main: Path, roots):
    from .catalog import CatalogError

    try:
        authority = contained(main, meta["worktree"]["path"]).resolve()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise CatalogError("CANONICAL_WORKTREE_INVALID", row["task_id"]) from exc
    if authority not in roots:
        raise CatalogError("CANONICAL_WORKTREE_UNREGISTERED", str(authority))
    if not authority.is_dir():
        raise CatalogError("CANONICAL_WORKTREE_MISSING", str(authority))
    number = row["task_id"].rsplit("-", 1)[1]
    try:
        directory = contained(authority, "docs/sdd/plans/" + meta["spec_id"])
        candidates = sorted(directory.glob("task-{}-*.md".format(number)))
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise CatalogError("CANONICAL_TASK_INVALID", row["task_id"]) from exc
    if not candidates:
        raise CatalogError("CANONICAL_TASK_MISSING", row["task_id"])
    if len(candidates) != 1:
        raise CatalogError("CANONICAL_TASK_AMBIGUOUS", row["task_id"])
    try:
        task = parse_task(candidates[0])
    except TaskDocumentError as exc:
        raise CatalogError(exc.code, str(exc)) from exc
    if (task.metadata["task_id"] != row["task_id"] or task.task_hash != row["task_hash"] or
            task.prompt_hash != row["prompt_hash"]):
        raise CatalogError("CANONICAL_TASK_HASH_MISMATCH", row["task_id"])
    if (task.metadata["status"] != row["status"] or
            task.metadata.get("migration_state") != meta.get("migration_state")):
        raise CatalogError("CANONICAL_TASK_STATE_DRIFT", row["task_id"])
    return task


def _recovery_reason(conn: sqlite3.Connection, task, main: Path):
    latest = conn.execute(
        "SELECT run_id,state FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id DESC LIMIT 1",
        (task.metadata["task_id"],),
    ).fetchone()
    if latest is None:
        return None
    if latest["state"] == "failed":
        return _failed_recovery_reason(conn, latest["run_id"], task, main)
    if latest["state"] != "abandoned":
        return None
    rows = conn.execute(
        "SELECT payload_json FROM events WHERE run_id=? AND event_type='recovery_decision'",
        (latest["run_id"],),
    ).fetchall()
    try:
        event = json.loads(rows[0][0], object_pairs_hook=_pairs, parse_constant=_constant) \
            if len(rows) == 1 else None
    except (TypeError, ValueError):
        event = None
    actions = {"requeued": "unchanged", "preserved_for_recovery": "partial"}
    action = event.get("action") if isinstance(event, dict) else None
    if (not isinstance(event, dict) or set(event) != {"schema", "action", "decision"} or
            event.get("schema") != "sdd-run-recovery/v1" or not isinstance(action, str) or
            action not in actions or actions[action] != event.get("decision")):
        return "recovery_invalid:RECOVERY_EVENT_INVALID"
    from .failed_lineage import FailedRetryLineageError, failed_retry_origin

    try:
        origin = failed_retry_origin(conn, latest["run_id"], task, main)
    except FailedRetryLineageError as exc:
        return "recovery_invalid:" + exc.code
    if origin is not None:
        return _failed_recovery_reason(conn, latest["run_id"], task, main)
    try:
        before = load_recovery_snapshot(conn, latest["run_id"], task, main)
        current = capture_snapshot(main, task)
        decision = compare_snapshot(before, current)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return "recovery_invalid:" + getattr(exc, "code", "RECOVERY_VALIDATION_FAILED")
    if (not decision.recoverable or decision.kind not in {"unchanged", "partial"} or
            (event["decision"] == "unchanged" and decision.kind != "unchanged")):
        return "recovery_workspace_conflict"
    return "recovery_ready:" + decision.kind


def _failed_recovery_reason(conn: sqlite3.Connection, run_id, task, main: Path):
    from .failed_selection import resolve_failed_source

    try:
        source = resolve_failed_source(conn, run_id, task, main)
    except ValueError as exc:
        return "recovery_invalid:" + getattr(exc, "code", "RECOVERY_VALIDATION_FAILED")
    return "recovery_ready:" + source.decision.kind


def status(conn: sqlite3.Connection) -> Dict[str, Any]:
    from .catalog import CatalogError

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"schema_migrations", "tasks", "dependencies", "runs", "leases"}
        if not required.issubset(tables):
            raise CatalogError("CATALOG_NOT_REBUILT", "task ledger schema is missing")
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
        if versions != [1]:
            raise CatalogError("CATALOG_NOT_REBUILT", "schema version is unavailable")
        cursor = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks"
        )
        columns = [column[0] for column in cursor.description]
        rows = [{name: row[index] for index, name in enumerate(columns)} for row in cursor]
        dependencies = {}
        for row in conn.execute("SELECT task_id,depends_on FROM dependencies"):
            dependencies.setdefault(row[0], []).append(row[1])
        runs = {}
        for task_id, state in conn.execute(
                "SELECT task_id,state FROM runs WHERE state IN ('claimed','running')"):
            runs.setdefault(task_id, set()).add(state)
        now = datetime.now(timezone.utc)
        now_text = now.isoformat().replace("+00:00", "Z")
        leases = {}
        for task_id, stamp in conn.execute("SELECT task_id,expires_at FROM leases"):
            try:
                expires = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if expires.utcoffset() is None:
                    raise ValueError("timezone required")
                leases[task_id] = "active" if expires > now else "expired"
            except (AttributeError, TypeError, ValueError):
                leases[task_id] = "invalid"
    except sqlite3.Error as exc:
        raise CatalogError("CATALOG_NOT_REBUILT", str(exc)) from exc

    data = {key: [] for key in ("eligible", "waiting", "running", "blocked", "completed", "diagnostics")}
    states = {row["task_id"]: row["status"] for row in rows}
    gate_context = None
    for row in rows:
        task_id, task_state = row["task_id"], row["status"]
        meta = _metadata(row)
        if task_state not in {"pending", "blocked", "completed", "cancelled"}:
            raise CatalogError("CATALOG_DATA_INVALID", task_id)
        live_task, spec_state = None, None
        if task_state == "pending":
            if gate_context is None:
                gate_context = _gate_context(conn)
            main, roots = gate_context
            live_task = _live_gate_task(row, meta, main, roots)
            try:
                spec_state = load_spec_status(live_task, main)
            except SpecStatusError as exc:
                raise CatalogError(exc.code, str(exc)) from exc
        item = {"task_id": task_id, "task_status": task_state, "reasons": []}
        if task_id in runs or leases.get(task_id) == "active":
            item["reasons"] = ["run_state:" + state for state in sorted(runs.get(task_id, ()))]
            if leases.get(task_id) == "active":
                item["reasons"].append("active_lease")
            if leases.get(task_id) == "expired":
                item["reasons"].append("expired_lease_requires_recovery")
            if leases.get(task_id) == "invalid":
                item["reasons"].append("lease_timestamp_invalid")
            data["running"].append(item)
        elif task_state == "completed":
            data["completed"].append(item)
        elif task_state == "blocked":
            item["reasons"].append("task_status:blocked")
            data["blocked"].append(item)
        elif task_state == "cancelled":
            data["diagnostics"].append({"task_id": task_id, "code": "cancelled"})
        else:
            satisfied = set()
            for dep in dependencies.get(task_id, ()):
                if states.get(dep) != "completed":
                    item["reasons"].append("dependency_not_completed:" + dep)
            if meta.get("migration_state") == "unverified":
                item["reasons"].append("migration_unverified")
            if not is_claimable(spec_state):
                item["reasons"].append("spec_not_claimable:" + spec_state)
            if meta["required_gates"]:
                try:
                    satisfied = load_satisfied_gates(live_task, main)
                except GateEvidenceError as exc:
                    raise CatalogError(exc.code, str(exc)) from exc
                except (OSError, ValueError) as exc:
                    raise CatalogError("GATE_AUTHORITY_INVALID", str(exc)) from exc
                item["reasons"].extend(
                    "gate_unsatisfied:" + gate for gate in live_task.metadata["required_gates"]
                    if gate not in satisfied
                )
            blockers = ()
            if leases.get(task_id) != "invalid":
                try:
                    blockers = database_blockers(conn, live_task, satisfied, now_text)
                except ClaimError as exc:
                    raise CatalogError(exc.code, task_id) from exc
            for reason in ("dependency_index_stale", "max_attempts_exhausted"):
                if reason in blockers and reason not in item["reasons"]:
                    item["reasons"].append(reason)
            if leases.get(task_id) == "expired":
                item["reasons"].append("expired_lease_requires_recovery")
            if leases.get(task_id) == "invalid":
                item["reasons"].append("lease_timestamp_invalid")
            recovery = _recovery_reason(conn, live_task, main)
            if recovery:
                item["reasons"].append(recovery)
            blocking = any(not reason.startswith("recovery_ready:") for reason in item["reasons"])
            data["waiting" if blocking else "eligible"].append(item)
    return data
