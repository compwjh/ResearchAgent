"""Structural walk of closed retries that descend from a failed Task run."""

import sqlite3
from pathlib import Path

from .atomic import contained
from .documents import TaskDefinition
from .lease_recovery import stored_owner
from .leases import _main_root
from .locks import repository_paths
from .recovery_snapshots import _event, _snapshot, _uuid
from .workspace import WorkspaceError
from .workspace_observation import _instant, _validate_snapshot_history_events


class FailedRetryLineageError(WorkspaceError):
    """A closed retry chain is malformed or not bound to one failed source."""


def _retry_claim(source, claim, run_id):
    return (source is not None and isinstance(claim, dict) and
            set(claim) == {"schema", "recovery_of"} and
            claim["schema"] == "sdd-recovery-claim/v1" and
            _uuid(claim["recovery_of"]) == source and source != run_id)


def _one_consumer(conn, task_id, source_id, child_id):
    consumers = []
    for row in conn.execute("SELECT run_id FROM runs WHERE task_id=?", (task_id,)):
        run_id = row["run_id"]
        snapshot = _event(conn, run_id, "workspace_snapshot", True)
        if (not isinstance(snapshot, dict) or set(snapshot) != {"schema", "source_run_id", "snapshot"} or
                snapshot["schema"] != "sdd-workspace-snapshot/v1"):
            raise FailedRetryLineageError("FAILED_RETRY_CONSUMPTION_INVALID")
        source = snapshot["source_run_id"]
        if source is not None:
            source = _uuid(source)
        claim = _event(conn, run_id, "recovery_claim", source is not None)
        if claim is not None and not _retry_claim(source, claim, run_id):
            raise FailedRetryLineageError("FAILED_RETRY_CONSUMPTION_INVALID")
        if source is not None:
            if _uuid(claim["recovery_of"]) != source:
                raise FailedRetryLineageError("FAILED_RETRY_CONSUMPTION_INVALID")
            if source == source_id:
                consumers.append(run_id)
    if consumers != [child_id]:
        raise FailedRetryLineageError("FAILED_RETRY_SOURCE_CONSUMED")


def _closed_retry_context(conn, closed_source_id, task, repo_root):
    """Return closed descendants, nearest failed anchor, and their decoded event payloads.

    Payload entries are `(run_id, snapshot, claim, observation, decision)` tuples,
    ordered from the supplied closed run back through its failed anchor.
    """
    try:
        if (not isinstance(conn, sqlite3.Connection) or type(task) is not TaskDefinition or
                not isinstance(repo_root, (Path, str))):
            raise FailedRetryLineageError("FAILED_RETRY_ARGUMENT_INVALID")
        main, common = repository_paths(Path(repo_root))
        if main != _main_root(conn):
            raise FailedRetryLineageError("FAILED_RETRY_AUTHORITY_MISMATCH")
        meta = task.metadata
        relative, branch, task_id = (meta["worktree"]["path"], meta["worktree"]["branch"],
                                     meta["task_id"])
        expected = (task_id, task.task_hash, task.prompt_hash, relative, branch, meta["agent_role"])
        cursor, seen, baseline = _uuid(closed_source_id), set(), None
        closed, payloads = [], []
        while True:
            if cursor in seen:
                raise FailedRetryLineageError("FAILED_RETRY_SOURCE_CYCLE")
            seen.add(cursor)
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (cursor,)).fetchone()
            if run is None or run["state"] not in {"abandoned", "failed"}:
                raise FailedRetryLineageError("FAILED_RETRY_SOURCE_INVALID")
            if not closed and run["state"] != "abandoned":
                raise FailedRetryLineageError("FAILED_RETRY_SOURCE_INVALID")
            actual = (run["task_id"], run["task_hash"], run["prompt_hash"], run["worktree"],
                      run["branch"], run["agent_role"])
            if actual != expected or not run["ended_at"]:
                raise FailedRetryLineageError("FAILED_RETRY_BINDING_MISMATCH")
            if type(run["attempt"]) is not int or run["attempt"] < 1:
                raise FailedRetryLineageError("FAILED_RETRY_ATTEMPT_INVALID")
            if stored_owner(run["owner_json"]).executor_id != run["executor_id"]:
                raise FailedRetryLineageError("FAILED_RETRY_OWNER_INVALID")
            if conn.execute("SELECT 1 FROM leases WHERE run_id=?", (cursor,)).fetchone():
                raise FailedRetryLineageError("FAILED_RETRY_LEASE_PRESENT")
            _validate_snapshot_history_events(conn, run)
            snapshot_payload = _event(conn, cursor, "workspace_snapshot", True)
            source, snapshot = _snapshot(snapshot_payload, task, run, main, common,
                                         contained(main, relative).resolve(strict=True))
            if baseline is not None and snapshot != baseline:
                raise FailedRetryLineageError("FAILED_RETRY_BASELINE_MISMATCH")
            baseline = snapshot
            claim = _event(conn, cursor, "recovery_claim", source is not None)
            if source is not None and not _retry_claim(source, claim, cursor):
                raise FailedRetryLineageError("FAILED_RETRY_CLAIM_MISMATCH")
            observations = conn.execute(
                "SELECT 1 FROM events WHERE run_id=? AND event_type='workspace_observation'",
                (cursor,),
            ).fetchall()
            observation = _event(conn, cursor, "workspace_observation", bool(observations))
            decisions = conn.execute(
                "SELECT payload_json FROM events WHERE run_id=? AND event_type='recovery_decision'",
                (cursor,),
            ).fetchall()
            decision = _event(conn, cursor, "recovery_decision", bool(decisions))
            if run["state"] == "failed":
                payloads.append((cursor, snapshot_payload, claim, observation, decision))
                return tuple(closed), cursor, tuple(payloads)
            if run["error_code"] != "OWNER_DEAD_LEASE_EXPIRED" or source is None:
                raise FailedRetryLineageError("FAILED_RETRY_ABANDONED_INVALID")
            pair = ((decision.get("action"), decision.get("decision"))
                    if isinstance(decision, dict) else None)
            if len(closed) and pair != ("preserved_for_recovery", "partial"):
                raise FailedRetryLineageError("FAILED_RETRY_DECISION_INVALID")
            parent = conn.execute("SELECT state,task_id,attempt,ended_at FROM runs WHERE run_id=?",
                                  (source,)).fetchone()
            if (parent is None or parent["task_id"] != task_id or
                    parent["state"] not in {"abandoned", "failed"} or
                    type(parent["attempt"]) is not int or run["attempt"] != parent["attempt"] + 1 or
                    not parent["ended_at"] or
                    _instant(parent["ended_at"], "parent.ended_at") >
                    _instant(run["claimed_at"], "child.claimed_at")):
                raise FailedRetryLineageError("FAILED_RETRY_ATTEMPT_ORDER_INVALID")
            _one_consumer(conn, task_id, source, cursor)
            closed.append(run)
            payloads.append((cursor, snapshot_payload, claim, observation, decision))
            cursor = source
    except FailedRetryLineageError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise FailedRetryLineageError(getattr(exc, "code", "FAILED_RETRY_CONTEXT_INVALID")) from exc
