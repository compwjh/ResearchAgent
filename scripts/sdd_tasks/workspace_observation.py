"""Persist a verified private workspace observation for an active run."""

import hmac
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .atomic import contained
from .catalog import discover_worktrees
from .documents import TaskDefinition, _pairs, parse_task
from .event_logs import sync_event_log
from .lease_recovery import stored_owner
from .leases import LeaseError, _live_task, _main_root, _timestamp, _utc_text
from .locks import repository_paths
from .owners import OwnerIdentity
from .recovery_snapshots import _event, _git, _snapshot, _uuid, load_recovery_snapshot
from .result_schema import _scan
from .run_owner import resolve_run_owner
from .store import transaction
from .workspace import WorkspaceError, WorkspaceSnapshot, capture_snapshot


class WorkspaceObservationError(WorkspaceError):
    """A run cannot safely record its private workspace observation."""


_OBSERVATION_FIELDS = {
    "repo_root", "common_dir", "worktree_path", "spec_id", "task_id", "task_hash",
    "prompt_hash", "branch", "head", "status_records", "allowed_hashes", "captured_at",
}


def _instant(value, field):
    try:
        instant = _timestamp(value, field)
    except (LeaseError, TypeError) as exc:
        raise WorkspaceObservationError("OBSERVATION_TIME_INVALID") from exc
    if instant.utcoffset() != timedelta(0):
        raise WorkspaceObservationError("OBSERVATION_TIME_INVALID")
    return instant.astimezone(timezone.utc)


def _snapshot_values(snapshot):
    values = {name: (str(getattr(snapshot, name)) if name in
              {"repo_root", "common_dir", "worktree_path"} else getattr(snapshot, name))
              for name in snapshot.__dataclass_fields__}
    values["status_records"] = list(snapshot.status_records)
    values["allowed_hashes"] = dict(sorted(snapshot.allowed_hashes.items()))
    return values


def _same_capture(left, right):
    return all(getattr(left, name) == getattr(right, name)
               for name in left.__dataclass_fields__ if name != "captured_at")


def _same_owner(left, right):
    return (left.executor_id == right.executor_id and left.host_id == right.host_id and
            left.pid == right.pid and left.process_started_at == right.process_started_at and
            hmac.compare_digest(left.token.encode("utf-8"), right.token.encode("utf-8")))


def _scan_observation_payload(payload, main, common, worktree):
    safe, snapshot = dict(payload), dict(payload["snapshot"])
    for field, root in (("repo_root", main), ("common_dir", common), ("worktree_path", worktree)):
        canonical = str(Path(root).resolve(strict=True))
        if not Path(canonical).is_absolute() or snapshot.get(field) != canonical:
            raise WorkspaceObservationError("OBSERVATION_PAYLOAD_UNSAFE")
        snapshot.pop(field)
    safe["snapshot"] = snapshot
    _scan(safe)


def record_workspace_observation(
    conn: sqlite3.Connection, run_id: str, owner: OwnerIdentity,
    snapshot: WorkspaceSnapshot, *, now: str,
) -> None:
    """Record one owner-authenticated snapshot while its lease is active."""
    if (not isinstance(conn, sqlite3.Connection) or conn.in_transaction or
            not isinstance(owner, OwnerIdentity) or type(snapshot) is not WorkspaceSnapshot):
        raise WorkspaceObservationError("OBSERVATION_ARGUMENT_INVALID")
    instant = _instant(now, "now")
    if instant > datetime.now(timezone.utc):
        raise WorkspaceObservationError("OBSERVATION_TIME_IN_FUTURE")
    if _instant(snapshot.captured_at, "snapshot.captured_at") > instant:
        raise WorkspaceObservationError("OBSERVATION_TIME_INVALID")
    main = None
    try:
        with transaction(conn, immediate=True):
            persisted = resolve_run_owner(conn, run_id, owner.executor_id, owner.pid)
            if not _same_owner(persisted, owner):
                raise WorkspaceObservationError("OBSERVATION_OWNER_MISMATCH")
            main = _main_root(conn)
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            lease = conn.execute("SELECT * FROM leases WHERE run_id=?", (run_id,)).fetchone()
            if run is None or lease is None or run["state"] not in {"claimed", "running"} or run["ended_at"] is not None:
                raise WorkspaceObservationError("OBSERVATION_RUN_NOT_ACTIVE")
            task = _live_task(conn, run, main)
            snapshot_event = _event(conn, run_id, "workspace_snapshot", True)
            source_run_id = (snapshot_event.get("source_run_id")
                             if isinstance(snapshot_event, dict) else None)
            source = (conn.execute("SELECT state,task_id FROM runs WHERE run_id=?",
                                   (source_run_id,)).fetchone()
                      if isinstance(source_run_id, str) else None)
            failed_source = None
            expected_head = run["base_commit"]
            if (source is not None and source["state"] == "failed" and
                    source["task_id"] == run["task_id"]):
                from .active_failed_recovery import (
                    compare_active_failed_workspace,
                    load_active_failed_source,
                )

                failed_source = load_active_failed_source(conn, run_id, task, main)
                baseline = failed_source.baseline
                expected_head = failed_source.active_claim_tip
            else:
                baseline = load_recovery_snapshot(conn, run_id, task, main)
            captured = _instant(snapshot.captured_at, "snapshot.captured_at")
            lease_expiry = _instant(lease["expires_at"], "lease.expires_at")
            if (lease["task_id"] != run["task_id"] or lease_expiry <= instant or
                    _instant(lease["refreshed_at"], "lease.refreshed_at") > instant or
                    run["task_hash"] != task.task_hash or run["prompt_hash"] != task.prompt_hash or
                    run["base_commit"] != baseline.head or run["worktree"] != task.metadata["worktree"]["path"] or
                    run["branch"] != task.metadata["worktree"]["branch"] or
                    snapshot.task_id != run["task_id"] or snapshot.task_hash != run["task_hash"] or
                    snapshot.prompt_hash != run["prompt_hash"] or snapshot.head != expected_head or
                    snapshot.branch != run["branch"] or snapshot.repo_root != baseline.repo_root or
                    snapshot.common_dir != baseline.common_dir or snapshot.worktree_path != baseline.worktree_path or
                    captured < _instant(baseline.captured_at, "baseline.captured_at") or
                    _instant(run["claimed_at"], "run.claimed_at") > instant):
                raise WorkspaceObservationError("OBSERVATION_BINDING_MISMATCH")
            current = capture_snapshot(main, task)
            if not _same_capture(snapshot, current):
                raise WorkspaceObservationError("OBSERVATION_SNAPSHOT_MISMATCH")
            if (failed_source is not None and
                    not compare_active_failed_workspace(failed_source, current, task).recoverable):
                raise WorkspaceObservationError("OBSERVATION_WORKSPACE_OUT_OF_SCOPE")
            rows = conn.execute(
                "SELECT sequence,timestamp,event_type FROM events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
            if (not rows or [row["sequence"] for row in rows] != list(range(1, len(rows) + 1)) or
                    rows[0]["event_type"] != "workspace_snapshot"):
                raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
            claims = [row for row in rows if row["event_type"] == "recovery_claim"]
            if len(claims) > 1 or (claims and claims[0]["sequence"] != 2):
                raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
            previous = None
            for row in rows:
                event_time = _instant(row["timestamp"], "event.timestamp")
                if event_time > instant or (previous is not None and event_time < previous):
                    raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
                previous = event_time
            public = next((row for row in rows if row["event_type"] in
                           {"observation", "evidence", "decision", "action", "result", "next_step"}), None)
            if ((public is None and (run["state"] != "claimed" or run["started_at"] is not None)) or
                    (public is not None and (run["state"] != "running" or
                                             run["started_at"] != public["timestamp"]))):
                raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
            payload = {"schema": "sdd-workspace-observation/v1",
                       "snapshot": _snapshot_values(snapshot)}
            _scan_observation_payload(payload, main, baseline.common_dir, baseline.worktree_path)
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":"), allow_nan=False)
            if owner.token in payload_json:
                raise WorkspaceObservationError("OBSERVATION_PAYLOAD_UNSAFE")
            observations = conn.execute(
                "SELECT sequence,payload_json FROM events WHERE run_id=? AND event_type='workspace_observation'",
                (run_id,),
            ).fetchall()
            if observations:
                if (len(observations) != 1 or observations[0]["payload_json"] != payload_json or
                        observations[0]["sequence"] != rows[-1]["sequence"]):
                    raise WorkspaceObservationError("OBSERVATION_ALREADY_RECORDED")
            else:
                conn.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?)",
                    (run_id, len(rows) + 1, _utc_text(instant), "workspace_observation", payload_json),
                )
    except WorkspaceObservationError:
        raise
    except WorkspaceError:
        raise
    except LeaseError as exc:
        raise WorkspaceObservationError(getattr(exc, "code", "OBSERVATION_OWNER_INVALID")) from exc
    except sqlite3.Error as exc:
        raise WorkspaceObservationError("OBSERVATION_STORE_ERROR") from exc
    except (OSError, TypeError, ValueError, KeyError, UnicodeError) as exc:
        raise WorkspaceObservationError("OBSERVATION_VALIDATION_FAILED") from exc
    try:
        sync_event_log(conn, run_id, main)
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise WorkspaceObservationError("OBSERVATION_LOG_SYNC_FAILED") from exc


def _decode_run_observation_event(
    conn: sqlite3.Connection, run_id: str, task: TaskDefinition, repo_root: Path,
    *, expected_tip: str, expected_state: str,
) -> WorkspaceSnapshot:
    """Decode one terminal observation after a caller validates expected_tip history.

    This checks the event envelope and canonical identities only; it does not prove
    the before-snapshot lineage or authorize failed-source recovery.
    """
    if (not isinstance(conn, sqlite3.Connection) or type(task) is not TaskDefinition or
            not isinstance(expected_state, str) or expected_state not in {"failed", "abandoned"} or
            not isinstance(expected_tip, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_tip)):
        raise WorkspaceObservationError("OBSERVATION_ARGUMENT_INVALID")
    try:
        main, common = repository_paths(Path(repo_root))
        if main != _main_root(conn):
            raise WorkspaceObservationError("OBSERVATION_AUTHORITY_MISMATCH")
        task_id = task.metadata["task_id"]
        match = re.fullmatch(r"spec-(\d{3})-task-(\d{2})", task_id)
        if match is None or task.metadata["spec_id"] != match.group(1):
            raise WorkspaceObservationError("OBSERVATION_TASK_INVALID")
        relative = task.metadata["worktree"]["path"]
        worktree = contained(main, relative).resolve(strict=True)
        if worktree not in discover_worktrees(main):
            raise WorkspaceObservationError("OBSERVATION_WORKTREE_UNREGISTERED")
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None or run is None or run["state"] != expected_state or run["ended_at"] is None:
            raise WorkspaceObservationError("OBSERVATION_FAILED_RUN_REQUIRED")
        stored = json.loads(row["definition_json"], object_pairs_hook=_pairs)
        task_path = contained(worktree, row["source_path"])
        actual = parse_task(task_path)
        if (not isinstance(stored, dict) or stored != actual.metadata or
                row["status"] not in {"pending", "blocked"} or actual.metadata["status"] != row["status"] or
                (row["task_hash"], row["prompt_hash"]) != (task.task_hash, task.prompt_hash) or
                (actual.task_hash, actual.prompt_hash) != (task.task_hash, task.prompt_hash) or
                {key: value for key, value in actual.metadata.items() if key != "status"} !=
                {key: value for key, value in task.metadata.items() if key != "status"}):
            raise WorkspaceObservationError("OBSERVATION_TASK_MISMATCH")
        if (run["task_id"] != task_id or run["task_hash"] != task.task_hash or
                run["prompt_hash"] != task.prompt_hash or run["worktree"] != relative or
                run["branch"] != task.metadata["worktree"]["branch"] or
                run["agent_role"] != task.metadata["agent_role"] or
                not isinstance(run["base_commit"], str) or
                not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", run["base_commit"])):
            raise WorkspaceObservationError("OBSERVATION_RUN_MISMATCH")
        events = conn.execute(
            "SELECT sequence,timestamp,event_type,payload_json FROM events WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        observations = [event for event in events if event["event_type"] == "workspace_observation"]
        if (not observations or len(observations) != 1 or
                [event["sequence"] for event in events] != list(range(1, len(events) + 1)) or
                events[0]["event_type"] != "workspace_snapshot"):
            raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
        claims = [event for event in events if event["event_type"] == "recovery_claim"]
        if len(claims) > 1 or (claims and claims[0]["sequence"] != 2):
            raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
        ended = _instant(run["ended_at"], "run.ended_at")
        previous = None
        for event in events:
            stamp = _instant(event["timestamp"], "event.timestamp")
            if ((event["event_type"] != "recovery_decision" and stamp > ended) or
                    (event["event_type"] == "recovery_decision" and stamp < ended) or
                    (previous is not None and stamp < previous)):
                raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
            previous = stamp
        observation = observations[0]
        decisions = [event for event in events if event["event_type"] == "recovery_decision"]
        if (len(decisions) > 1 or any(event["sequence"] < observation["sequence"] for event in decisions) or
                any(event["event_type"] != "recovery_decision" and
                    event["sequence"] > observation["sequence"] for event in events)):
            raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
        if decisions:
            decision = json.loads(decisions[0]["payload_json"], object_pairs_hook=_pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if (not isinstance(decision, dict) or set(decision) != {"schema", "action", "decision"} or
                    decision.get("schema") != "sdd-run-recovery/v1" or
                    (decision.get("action"), decision.get("decision")) not in
                    {("requeued", "unchanged"), ("preserved_for_recovery", "partial")}):
                raise WorkspaceObservationError("OBSERVATION_EVENTS_INVALID")
        payload = json.loads(observation["payload_json"], object_pairs_hook=_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (not isinstance(payload, dict) or set(payload) != {"schema", "snapshot"} or
                payload["schema"] != "sdd-workspace-observation/v1" or
                not isinstance(payload["snapshot"], dict) or set(payload["snapshot"]) != _OBSERVATION_FIELDS):
            raise WorkspaceObservationError("OBSERVATION_PAYLOAD_INVALID")
        data = payload["snapshot"]
        captured = _instant(data["captured_at"], "snapshot.captured_at")
        stamp = _instant(observation["timestamp"], "observation.timestamp")
        expected_paths = {"repo_root": str(main), "common_dir": str(common),
                          "worktree_path": str(worktree), "spec_id": task.metadata["spec_id"],
                          "task_id": task_id, "task_hash": task.task_hash,
                          "prompt_hash": task.prompt_hash, "branch": run["branch"], "head": expected_tip}
        if (any(data.get(key) != value for key, value in expected_paths.items()) or captured > stamp or
                captured < _instant(run["claimed_at"], "run.claimed_at") or
                not isinstance(data["status_records"], list) or
                any(not isinstance(item, str) for item in data["status_records"]) or
                not isinstance(data["allowed_hashes"], dict)):
            raise WorkspaceObservationError("OBSERVATION_SNAPSHOT_MISMATCH")
        allowed = task.metadata["allowed_paths"]
        hashes = data["allowed_hashes"]
        if (not set(allowed).issubset(hashes) or
                any(not isinstance(path, str) or
                    not any(path == root or path.startswith(root + "/") for root in allowed) or
                    (value is not None and (not isinstance(value, str) or
                     not re.fullmatch(r"[0-9a-f]{64}", value))) for path, value in hashes.items())):
            raise WorkspaceObservationError("OBSERVATION_SNAPSHOT_INVALID")
        for path in hashes:
            contained(worktree, path)
        _scan_observation_payload(payload, main, common, worktree)
        return WorkspaceSnapshot(main, common, worktree, data["spec_id"], task_id, task.task_hash,
                                 task.prompt_hash, run["branch"], expected_tip,
                                 tuple(data["status_records"]), dict(hashes), data["captured_at"])
    except WorkspaceObservationError:
        raise
    except (OSError, TypeError, ValueError, KeyError, sqlite3.Error) as exc:
        raise WorkspaceObservationError("OBSERVATION_VALIDATION_FAILED") from exc


def _decode_observation_event(conn, run_id, task, repo_root, *, expected_tip):
    """Decode one failed-run observation; the failed-state check stays strict."""
    return _decode_run_observation_event(conn, run_id, task, repo_root,
                                         expected_tip=expected_tip, expected_state="failed")


def _decode_abandoned_observation_event(conn, run_id, task, repo_root, *, expected_tip):
    return _decode_run_observation_event(conn, run_id, task, repo_root,
                                         expected_tip=expected_tip, expected_state="abandoned")


def _validate_snapshot_history_events(conn, run):
    events = conn.execute(
        "SELECT sequence,timestamp,event_type FROM events WHERE run_id=? ORDER BY sequence",
        (run["run_id"],),
    ).fetchall()
    if (not events or [item["sequence"] for item in events] != list(range(1, len(events) + 1)) or
            events[0]["event_type"] != "workspace_snapshot"):
        raise WorkspaceObservationError("OBSERVATION_HISTORY_EVENTS_INVALID")
    claims = [item for item in events if item["event_type"] == "recovery_claim"]
    observations = [item for item in events if item["event_type"] == "workspace_observation"]
    decisions = [item for item in events if item["event_type"] == "recovery_decision"]
    if (len(claims) > 1 or (claims and claims[0]["sequence"] != 2) or
            (run["state"] == "failed" and len(observations) != 1) or
            (run["state"] == "abandoned" and len(observations) > 1) or
            (run["state"] == "abandoned" and len(decisions) != 1) or
            (run["state"] == "failed" and len(decisions) > 1)):
        raise WorkspaceObservationError("OBSERVATION_HISTORY_EVENTS_INVALID")
    ended = _instant(run["ended_at"], "run.ended_at")
    previous = None
    for item in events:
        stamp = _instant(item["timestamp"], "event.timestamp")
        if ((item["event_type"] != "recovery_decision" and stamp > ended) or
                (item["event_type"] == "recovery_decision" and stamp < ended) or
                (previous is not None and stamp < previous)):
            raise WorkspaceObservationError("OBSERVATION_HISTORY_EVENTS_INVALID")
        previous = stamp
    decision = _event(conn, run["run_id"], "recovery_decision", bool(decisions))
    if decision is not None:
        pair = (decision.get("action"), decision.get("decision")) if isinstance(decision, dict) else None
        allowed = {("requeued", "unchanged"), ("preserved_for_recovery", "partial")}
        if (not isinstance(decision, dict) or set(decision) != {"schema", "action", "decision"} or
                decision.get("schema") != "sdd-run-recovery/v1" or pair not in allowed or
                decisions[0]["sequence"] != events[-1]["sequence"]):
            raise WorkspaceObservationError("OBSERVATION_HISTORY_DECISION_INVALID")
        if run["state"] == "abandoned" and _instant(decisions[0]["timestamp"], "decision.timestamp") != ended:
            raise WorkspaceObservationError("OBSERVATION_HISTORY_DECISION_INVALID")
    return events


def _load_failed_run_context(
    conn: sqlite3.Connection, run_id: str, task: TaskDefinition, repo_root: Path,
) -> tuple:
    """Return copied baseline and its ordered source ancestry for external proof."""
    try:
        main, common = repository_paths(Path(repo_root))
        if main != _main_root(conn):
            raise WorkspaceObservationError("OBSERVATION_AUTHORITY_MISMATCH")
        meta = task.metadata
        relative, branch, task_id = meta["worktree"]["path"], meta["worktree"]["branch"], meta["task_id"]
        worktree = contained(main, relative).resolve(strict=True)
        if worktree not in discover_worktrees(main):
            raise WorkspaceObservationError("OBSERVATION_WORKTREE_UNREGISTERED")
        match = re.fullmatch(r"spec-(\d{3})-task-(\d{2})", task_id)
        if match is None or match.group(1) != meta["spec_id"]:
            raise WorkspaceObservationError("OBSERVATION_TASK_INVALID")
        directory = contained(worktree, "docs/sdd/plans/" + meta["spec_id"])
        candidates = sorted(directory.glob("task-" + match.group(2) + "-*.md"))
        if len(candidates) != 1:
            raise WorkspaceObservationError("OBSERVATION_TASK_AMBIGUOUS")
        task_file = contained(worktree, candidates[0].relative_to(worktree).as_posix())
        actual_task = parse_task(task_file)
        task_row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        stored = json.loads(task_row["definition_json"], object_pairs_hook=_pairs) if task_row else None
        canonical = {key: value for key, value in actual_task.metadata.items() if key != "status"}
        supplied = {key: value for key, value in meta.items() if key != "status"}
        if (task_row is None or task_row["status"] not in {"pending", "blocked"} or
                task_row["task_hash"] != task.task_hash or task_row["prompt_hash"] != task.prompt_hash or
                stored != actual_task.metadata or
                Path(task.path).resolve(strict=True) != task_file.resolve(strict=True) or
                actual_task.task_hash != task.task_hash or actual_task.prompt_hash != task.prompt_hash or
                canonical != supplied):
            raise WorkspaceObservationError("OBSERVATION_TASK_MISMATCH")
        if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") != branch:
            raise WorkspaceObservationError("OBSERVATION_BRANCH_MISMATCH")
        expected = (task_id, task.task_hash, task.prompt_hash, relative, branch, meta["agent_role"])
        baseline, cursor, seen, ancestry = None, _uuid(run_id), set(), []
        while cursor is not None:
            if cursor in seen:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_CYCLE")
            seen.add(cursor)
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (cursor,)).fetchone()
            if (run is None or run["state"] not in {"failed", "abandoned"} or
                    (cursor == run_id and run["state"] != "failed")):
                raise WorkspaceObservationError("OBSERVATION_HISTORY_RUN_INVALID")
            actual = (run["task_id"], run["task_hash"], run["prompt_hash"], run["worktree"],
                      run["branch"], run["agent_role"])
            if actual != expected or not run["ended_at"]:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_BINDING_MISMATCH")
            if type(run["attempt"]) is not int or run["attempt"] < 1:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_ATTEMPT_ORDER_INVALID")
            if stored_owner(run["owner_json"]).executor_id != run["executor_id"]:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_OWNER_INVALID")
            _validate_snapshot_history_events(conn, run)
            source, snapshot = _snapshot(
                _event(conn, cursor, "workspace_snapshot", True), task, run, main, common, worktree)
            if baseline is not None and snapshot != baseline:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_BASELINE_MISMATCH")
            baseline = snapshot
            ancestry.append(run)
            claim = _event(conn, cursor, "recovery_claim", source is not None)
            if source is None:
                break
            if (not isinstance(claim, dict) or set(claim) != {"schema", "recovery_of"} or
                    claim["schema"] != "sdd-recovery-claim/v1" or _uuid(claim["recovery_of"]) != source):
                raise WorkspaceObservationError("OBSERVATION_HISTORY_CLAIM_INVALID")
            parent = conn.execute("SELECT state,task_id,attempt FROM runs WHERE run_id=?",
                                  (source,)).fetchone()
            if (parent is None or parent["task_id"] != task_id or
                    parent["state"] not in {"failed", "abandoned"}):
                raise WorkspaceObservationError("OBSERVATION_HISTORY_SOURCE_INVALID")
            if source in seen:
                raise WorkspaceObservationError("OBSERVATION_HISTORY_CYCLE")
            if (type(parent["attempt"]) is not int or
                    run["attempt"] != parent["attempt"] + 1):
                raise WorkspaceObservationError("OBSERVATION_HISTORY_ATTEMPT_ORDER_INVALID")
            cursor = source
        return baseline, tuple(reversed(ancestry))
    except WorkspaceObservationError:
        raise
    except WorkspaceError:
        raise
    except (OSError, TypeError, ValueError, KeyError, sqlite3.Error) as exc:
        raise WorkspaceObservationError("OBSERVATION_BASELINE_INVALID") from exc


def _load_failed_run_baseline(
    conn: sqlite3.Connection, run_id: str, task: TaskDefinition, repo_root: Path,
) -> WorkspaceSnapshot:
    """Return copied before data only; caller must separately prove failure history."""
    return _load_failed_run_context(conn, run_id, task, repo_root)[0]
