"""J7 transaction bindings for terminal completion-ledger finalization."""

import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .completion_journal import read_journal, write_journal
from .journal_schema import validate_journal
from .owners import OwnerIdentity, OwnerStatus, observe_owner
from .store import transaction

_OWNER_FIELDS = {"executor_id", "host_id", "pid", "process_started_at", "token"}
_PUBLIC_EVENTS = {"observation", "evidence", "decision", "action", "result", "next_step"}


class LedgerFinalizeError(ValueError):
    """A journal and ledger row cannot be finalized as the same terminal run."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_INVALID")
        result[key] = value
    return result


def _instant(value, field):
    if not isinstance(value, str):
        raise LedgerFinalizeError("LEDGER_FINALIZE_TIME_INVALID:" + field)
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TIME_INVALID:" + field) from exc
    if instant.utcoffset() != timedelta(0):
        raise LedgerFinalizeError("LEDGER_FINALIZE_TIME_INVALID:" + field)
    return instant.astimezone(timezone.utc)


def _owner(value):
    if not isinstance(value, str) or not value:
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_INVALID")
    try:
        parsed = json.loads(value, object_pairs_hook=_pairs)
    except (TypeError, ValueError) as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_INVALID") from exc
    if (not isinstance(parsed, dict) or set(parsed) != _OWNER_FIELDS or
            any(not isinstance(parsed[key], str) or not parsed[key] for key in _OWNER_FIELDS - {"pid"}) or
            type(parsed["pid"]) is not int or parsed["pid"] < 1):
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_INVALID")
    return parsed


def _same_owner(run, lease, expected):
    stored = _owner(run["owner_json"])
    if (any(stored[key] != expected[key] for key in _OWNER_FIELDS - {"token"}) or
            run["executor_id"] != expected["executor_id"] or
            not isinstance(lease["owner_token"], str) or
            not hmac.compare_digest(stored["token"].encode(), expected["token"].encode()) or
            not hmac.compare_digest(lease["owner_token"].encode(), expected["token"].encode())):
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_MISMATCH")
    return OwnerIdentity(stored["executor_id"], stored["host_id"], stored["pid"],
                         stored["process_started_at"], stored["token"])


def _validate_active_bindings(conn, journal, now):
    """Validate immutable run/task/owner/lease bindings inside BEGIN IMMEDIATE."""
    if not conn.in_transaction:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TRANSACTION_REQUIRED")
    if journal["phase"] not in {"index_reconciled", "ledger_finalizing"}:
        raise LedgerFinalizeError("LEDGER_FINALIZE_PHASE_INVALID")
    instant = _instant(now, "now")
    result, owner = journal["expected_result"], journal["owner"]
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (journal["task_id"],)).fetchone()
    lease = conn.execute("SELECT * FROM leases WHERE run_id=?", (journal["run_id"],)).fetchone()
    if run is None or task is None or lease is None:
        raise LedgerFinalizeError("LEDGER_FINALIZE_BINDING_MISSING")
    if (run["run_id"] != journal["run_id"] or run["task_id"] != journal["task_id"] or
            run["state"] not in {"claimed", "running"} or run["ended_at"] is not None or
            run["task_hash"] != journal["task_hash"] or run["prompt_hash"] != journal["prompt_hash"] or
            run["base_commit"] != journal["base_commit"] or
            result["run_id"] != run["run_id"] or result["task_id"] != run["task_id"] or
            result["task_hash"] != run["task_hash"] or result["prompt_hash"] != run["prompt_hash"] or
            result["outcome"] != journal["terminal_outcome"]):
        raise LedgerFinalizeError("LEDGER_FINALIZE_RUN_MISMATCH")
    try:
        metadata = json.loads(task["definition_json"], object_pairs_hook=_pairs)
    except (TypeError, ValueError) as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID") from exc
    worktree = metadata.get("worktree") if isinstance(metadata, dict) else None
    if (task["status"] != "pending" or not isinstance(metadata, dict) or
            not isinstance(worktree, dict) or
            metadata.get("status") != "pending" or metadata.get("task_id") != run["task_id"] or
            task["task_hash"] != journal["task_hash"] or task["prompt_hash"] != journal["prompt_hash"] or
            run["agent_role"] != metadata.get("agent_role") or
            run["worktree"] != worktree.get("path") or
            run["branch"] != worktree.get("branch")):
        raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_MISMATCH")
    if lease["task_id"] != run["task_id"]:
        raise LedgerFinalizeError("LEDGER_FINALIZE_LEASE_MISMATCH")
    identity = _same_owner(run, lease, owner)
    expiry = _instant(lease["expires_at"], "lease.expires_at")
    observed = observe_owner(identity)
    if expiry <= instant:
        if journal["phase"] != "ledger_finalizing" or observed is not OwnerStatus.DEAD:
            raise LedgerFinalizeError("LEDGER_FINALIZE_LEASE_EXPIRED")
    elif observed is not OwnerStatus.ALIVE:
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_NOT_ALIVE")
    if run["started_at"] is not None and not isinstance(run["started_at"], str):
        raise LedgerFinalizeError("LEDGER_FINALIZE_START_INVALID")
    events = conn.execute(
        "SELECT sequence,timestamp,event_type FROM events WHERE run_id=? ORDER BY sequence",
        (run["run_id"],),
    ).fetchall()
    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        raise LedgerFinalizeError("LEDGER_FINALIZE_EVENTS_INVALID")
    first = next((event for event in events if event["event_type"] in _PUBLIC_EVENTS), None)
    expected_start = first["timestamp"] if first is not None else run["claimed_at"]
    if (result["started_at"] != expected_start or
            (run["started_at"] is not None and run["started_at"] != expected_start) or
            (first is None and run["started_at"] is not None) or
            _instant(result["ended_at"], "result.ended_at") > instant):
        raise LedgerFinalizeError("LEDGER_FINALIZE_RESULT_TIME_MISMATCH")
    return {"run": run, "task": task, "lease": lease, "owner": identity,
            "metadata": metadata, "now": instant}


def _target_task_status(conn, run, metadata, outcome, *, transaction_required=True):
    if outcome == "succeeded":
        return "completed"
    if outcome == "blocked":
        return "blocked"
    if outcome != "failed" or (transaction_required and not conn.in_transaction):
        raise LedgerFinalizeError("LEDGER_FINALIZE_OUTCOME_INVALID")
    limit = metadata.get("max_attempts", 3)
    if type(limit) is not int or limit < 1:
        raise LedgerFinalizeError("LEDGER_FINALIZE_ATTEMPT_LIMIT_INVALID")
    failures = 1
    for previous in conn.execute(
            "SELECT state FROM runs WHERE task_id=? AND attempt<? ORDER BY attempt DESC,run_id DESC",
            (run["task_id"], run["attempt"])):
        if previous["state"] != "failed":
            break
        failures += 1
    return "blocked" if failures >= limit else "pending"


def _terminal_values(conn, bindings, journal):
    """Derive terminal ledger fields only from the validated journal result."""
    run, metadata = bindings["run"], bindings["metadata"]
    result, outcome = journal["expected_result"], journal["terminal_outcome"]
    if (type(run["attempt"]) is not int or run["attempt"] < 1 or
            not isinstance(run["ide"], str) or not run["ide"].strip() or
            run["executor_id"] != journal["owner"]["executor_id"] or
            (run["model"] is not None and result["model"] != run["model"]) or
            run["result_doc"] is not None):
        raise LedgerFinalizeError("LEDGER_FINALIZE_RESULT_BINDING_MISMATCH")
    spec_id = run["task_id"].split("-")[1]
    if metadata.get("spec_id") != spec_id:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_MISMATCH")
    result_path = "docs/sdd/runs/{}/task-{}/{}.md".format(
        spec_id, run["task_id"].rsplit("-", 1)[1], run["run_id"])
    changed = {item["path"] for item in journal["changed_paths"]}
    declared = [item["path"] for item in result["changed_files"]]
    if len(declared) != len(set(declared)) or set(declared) != changed:
        raise LedgerFinalizeError("LEDGER_FINALIZE_CHANGED_PATHS_MISMATCH")
    artifact_rows = _artifact_values(run, journal, changed)
    target_status = _target_task_status(conn, run, metadata, outcome)
    return {"run": (outcome, result["model"], result["started_at"], result["ended_at"],
                     result["duration_ms"], result_path, None, None),
            "task_status": target_status, "artifacts": artifact_rows}


def _artifact_values(run, journal, changed=None):
    committed = set(journal["committed_paths"])
    changed = changed if changed is not None else {item["path"] for item in journal["changed_paths"]}
    artifacts = journal["expected_result"]["artifacts"]
    paths = [item["path"] for item in artifacts]
    if len(paths) != len(set(paths)):
        raise LedgerFinalizeError("LEDGER_FINALIZE_ARTIFACTS_INVALID")
    rows = []
    for item in artifacts:
        included = item["path"] in committed
        if item["included_in_commit"] is not None and item["included_in_commit"] != included:
            raise LedgerFinalizeError("LEDGER_FINALIZE_ARTIFACT_MEMBERSHIP_MISMATCH")
        status = "committed" if included else "uncommitted" if item["path"] in changed else "unchanged"
        rows.append((run["run_id"], item["path"], item["kind"], item["sha256"], status, int(included)))
    return tuple(rows)


def _verify_artifacts(conn, run_id, expected):
    actual = tuple(tuple(row) for row in conn.execute(
        "SELECT run_id,path,kind,sha256,git_status,included_in_commit "
        "FROM artifacts WHERE run_id=? ORDER BY path", (run_id,)))
    if actual != tuple(sorted(expected, key=lambda row: row[1])):
        raise LedgerFinalizeError("LEDGER_FINALIZE_ARTIFACT_SET_MISMATCH")


def _write_artifacts(conn, run_id, expected):
    for row in expected:
        cursor = conn.execute(
            "INSERT INTO artifacts(run_id,path,kind,sha256,git_status,included_in_commit) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(run_id,path) DO NOTHING", row)
        if cursor.rowcount not in {0, 1}:
            raise LedgerFinalizeError("LEDGER_FINALIZE_ARTIFACT_WRITE_FAILED")
        if cursor.rowcount == 0:
            existing = conn.execute(
                "SELECT run_id,path,kind,sha256,git_status,included_in_commit "
                "FROM artifacts WHERE run_id=? AND path=?", row[:2]).fetchone()
            if existing is None or tuple(existing) != row:
                raise LedgerFinalizeError("LEDGER_FINALIZE_ARTIFACT_CONFLICT")
    _verify_artifacts(conn, run_id, expected)


def _validate_terminal_views(conn, journal, target_status):
    from .atomic import contained
    from .catalog_status import _gate_context, _live_gate_task, _metadata
    from .mirrors import validate_mirrors
    from .result_query import result_for_run

    try:
        taskrow = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks WHERE task_id=?",
            (journal["task_id"],)).fetchone()
        if taskrow is None or taskrow["status"] != target_status:
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_STATUS_MISMATCH")
        main, roots = _gate_context(conn)
        metadata = _metadata(dict(taskrow))
        task = _live_gate_task(dict(taskrow), metadata, main, roots)
        authority = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        if authority not in roots or task.metadata["status"] != target_status:
            raise LedgerFinalizeError("LEDGER_FINALIZE_CANONICAL_TASK_MISMATCH")
        validate_mirrors(task, authority)
        if result_for_run(conn, journal["run_id"]) != journal["expected_result"]:
            raise LedgerFinalizeError("LEDGER_FINALIZE_SUMMARY_MISMATCH")
    except LedgerFinalizeError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_CANONICAL_VIEW_INVALID") from exc


def _same_terminal_owner(run, expected):
    stored = _owner(run["owner_json"])
    if (any(stored[key] != expected[key] for key in _OWNER_FIELDS - {"token"}) or
            run["executor_id"] != expected["executor_id"] or
            not hmac.compare_digest(stored["token"].encode(), expected["token"].encode())):
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_MISMATCH")


def _validate_terminal_replay(conn, journal):
    if journal["phase"] != "ledger_finalizing" or conn.in_transaction:
        raise LedgerFinalizeError("LEDGER_FINALIZE_REPLAY_PHASE_INVALID")
    with transaction(conn):
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (journal["task_id"],)).fetchone()
        leases = conn.execute("SELECT task_id,run_id FROM leases WHERE task_id=? OR run_id=?",
                              (journal["task_id"], journal["run_id"])).fetchall()
        if run is None or task is None or leases:
            raise LedgerFinalizeError("LEDGER_FINALIZE_REPLAY_BINDING_MISSING")
        result = journal["expected_result"]
        try:
            metadata = json.loads(task["definition_json"], object_pairs_hook=_pairs)
        except (TypeError, ValueError) as exc:
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID") from exc
        if not isinstance(metadata, dict):
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID")
        worktree = metadata.get("worktree")
        spec_id = journal["task_id"].split("-")[1]
        if (not isinstance(worktree, dict) or metadata.get("spec_id") != spec_id or
                metadata.get("task_id") != journal["task_id"]):
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID")
        owner = journal["owner"]
        _same_terminal_owner(run, owner)
        expected_path = "docs/sdd/runs/{}/task-{}/{}.md".format(
            spec_id, journal["task_id"].rsplit("-", 1)[1], journal["run_id"])
        latest = conn.execute(
            "SELECT run_id FROM runs WHERE task_id=? ORDER BY attempt DESC,run_id DESC LIMIT 1",
            (journal["task_id"],)).fetchone()
        if (latest is None or latest["run_id"] != journal["run_id"] or
                run["state"] != journal["terminal_outcome"] or run["task_id"] != journal["task_id"] or
                run["task_hash"] != journal["task_hash"] or run["prompt_hash"] != journal["prompt_hash"] or
                run["base_commit"] != journal["base_commit"] or
                type(run["attempt"]) is not int or run["attempt"] < 1 or
                not isinstance(run["ide"], str) or not run["ide"].strip() or
                run["agent_role"] != metadata.get("agent_role") or
                run["worktree"] != worktree.get("path") or run["branch"] != worktree.get("branch") or
                run["model"] != result["model"] or run["started_at"] != result["started_at"] or
                run["ended_at"] != result["ended_at"] or run["duration_ms"] != result["duration_ms"] or
                run["result_doc"] != expected_path or run["error_code"] is not None or
                run["error_summary"] is not None or task["task_hash"] != journal["task_hash"] or
                task["prompt_hash"] != journal["prompt_hash"] or
                metadata.get("task_id") != journal["task_id"] or metadata.get("status") != task["status"]):
            raise LedgerFinalizeError("LEDGER_FINALIZE_TERMINAL_ROW_MISMATCH")
        target = _target_task_status(conn, run, metadata, journal["terminal_outcome"])
        if task["status"] != target:
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_STATUS_MISMATCH")
        _verify_artifacts(conn, run["run_id"], _artifact_values(run, journal))
        _validate_terminal_views(conn, journal, target)
    return result


def _validate_complete_replay(conn, journal):
    if journal["phase"] != "complete" or conn.in_transaction:
        raise LedgerFinalizeError("LEDGER_FINALIZE_REPLAY_PHASE_INVALID")
    from .result_query import result_for_run

    with transaction(conn):
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
        task = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?",
                            (journal["task_id"],)).fetchone()
        lease = conn.execute("SELECT run_id FROM leases WHERE run_id=?", (journal["run_id"],)).fetchone()
        if run is None or task is None or lease is not None:
            raise LedgerFinalizeError("LEDGER_FINALIZE_REPLAY_BINDING_MISSING")
        _same_terminal_owner(run, journal["owner"])
        result = journal["expected_result"]
        expected_path = "docs/sdd/runs/{}/task-{}/{}.md".format(
            journal["task_id"].split("-")[1], journal["task_id"].rsplit("-", 1)[1], journal["run_id"])
        if (run["state"] != journal["terminal_outcome"] or run["task_id"] != journal["task_id"] or
                run["task_hash"] != journal["task_hash"] or run["prompt_hash"] != journal["prompt_hash"] or
                run["base_commit"] != journal["base_commit"] or type(run["attempt"]) is not int or
                run["attempt"] < 1 or not isinstance(run["ide"], str) or not run["ide"].strip() or
                run["model"] != result["model"] or run["started_at"] != result["started_at"] or
                run["ended_at"] != result["ended_at"] or run["duration_ms"] != result["duration_ms"] or
                run["result_doc"] != expected_path or run["error_code"] is not None or
                run["error_summary"] is not None or task["task_hash"] != journal["task_hash"] or
                task["prompt_hash"] != journal["prompt_hash"]):
            raise LedgerFinalizeError("LEDGER_FINALIZE_TERMINAL_ROW_MISMATCH")
        _verify_artifacts(conn, run["run_id"], _artifact_values(run, journal))
        try:
            if result_for_run(conn, run["run_id"]) != result:
                raise LedgerFinalizeError("LEDGER_FINALIZE_SUMMARY_MISMATCH")
        except LedgerFinalizeError:
            raise
        except (OSError, TypeError, ValueError, UnicodeError) as exc:
            raise LedgerFinalizeError("LEDGER_FINALIZE_CANONICAL_VIEW_INVALID") from exc
    return result


def _preflight_active(conn, journal, now):
    """Check terminal bindings before the journal phase can advance."""
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (journal["task_id"],)).fetchone()
    lease = conn.execute("SELECT * FROM leases WHERE run_id=?", (journal["run_id"],)).fetchone()
    if run is None or task is None or lease is None:
        raise LedgerFinalizeError("LEDGER_FINALIZE_BINDING_MISSING")
    result = journal["expected_result"]
    if (run["state"] not in {"claimed", "running"} or run["ended_at"] is not None or
            run["task_id"] != journal["task_id"] or
            run["task_hash"] != journal["task_hash"] or run["prompt_hash"] != journal["prompt_hash"] or
            run["base_commit"] != journal["base_commit"] or
            result["run_id"] != run["run_id"] or result["task_id"] != run["task_id"] or
            result["task_hash"] != run["task_hash"] or result["prompt_hash"] != run["prompt_hash"] or
            result["outcome"] != journal["terminal_outcome"] or
            (run["model"] is not None and result["model"] != run["model"]) or
            task["status"] != "pending" or task["task_hash"] != journal["task_hash"] or
            task["prompt_hash"] != journal["prompt_hash"] or
            lease["task_id"] != run["task_id"] or lease["run_id"] != run["run_id"]):
        raise LedgerFinalizeError("LEDGER_FINALIZE_BINDING_MISMATCH")
    identity = _same_owner(run, lease, journal["owner"])
    expiry, instant = _instant(lease["expires_at"], "lease.expires_at"), _instant(now, "now")
    observed = observe_owner(identity)
    if expiry <= instant:
        if observed is not OwnerStatus.DEAD:
            raise LedgerFinalizeError("LEDGER_FINALIZE_LEASE_EXPIRED")
    elif observed is not OwnerStatus.ALIVE:
        raise LedgerFinalizeError("LEDGER_FINALIZE_OWNER_NOT_ALIVE")
    try:
        metadata = json.loads(task["definition_json"], object_pairs_hook=_pairs)
    except (TypeError, ValueError) as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID") from exc
    worktree = metadata.get("worktree") if isinstance(metadata, dict) else None
    task_id = journal["task_id"]
    if (not isinstance(metadata, dict) or not isinstance(worktree, dict) or
            metadata.get("status") != "pending" or metadata.get("task_id") != task_id or
            metadata.get("spec_id") != task_id.split("-")[1] or
            run["agent_role"] != metadata.get("agent_role") or
            run["worktree"] != worktree.get("path") or run["branch"] != worktree.get("branch")):
        raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_INVALID")
    events = conn.execute(
        "SELECT sequence,timestamp,event_type FROM events WHERE run_id=? ORDER BY sequence",
        (run["run_id"],),
    ).fetchall()
    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        raise LedgerFinalizeError("LEDGER_FINALIZE_EVENTS_INVALID")
    first = next((event for event in events if event["event_type"] in _PUBLIC_EVENTS), None)
    expected_start = first["timestamp"] if first is not None else run["claimed_at"]
    if (result["started_at"] != expected_start or
            (run["started_at"] is not None and run["started_at"] != expected_start) or
            (first is None and run["started_at"] is not None) or
            _instant(result["ended_at"], "result.ended_at") > _instant(now, "now")):
        raise LedgerFinalizeError("LEDGER_FINALIZE_RESULT_TIME_MISMATCH")
    return _target_task_status(conn, run, metadata, journal["terminal_outcome"],
                               transaction_required=False)


def _verify_expected_documents(conn, journal, target_status):
    from .atomic import contained, read_text
    from .catalog_status import _gate_context, _metadata
    from .documents import parse_task
    from .mirrors import render_status_update, validate_mirrors

    try:
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (journal["task_id"],)).fetchone()
        if row is None or row["status"] != "pending":
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_BINDING_MISMATCH")
        main, roots = _gate_context(conn)
        metadata = _metadata(dict(row))
        authority = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        if authority not in roots:
            raise LedgerFinalizeError("LEDGER_FINALIZE_CANONICAL_WORKTREE_INVALID")
        task = parse_task(contained(authority, row["source_path"]))
        canonical = {key: value for key, value in task.metadata.items() if key != "status"}
        stored = {key: value for key, value in metadata.items() if key != "status"}
        if (task.metadata["status"] != target_status or canonical != stored or
                task.task_hash != journal["task_hash"] or task.prompt_hash != journal["prompt_hash"]):
            raise LedgerFinalizeError("LEDGER_FINALIZE_CANONICAL_TASK_MISMATCH")
        if target_status == "pending":
            validate_mirrors(task, authority)
            status_docs = {}
        else:
            status_docs = render_status_update(task, target_status, authority)
        summary = "docs/sdd/runs/{}/task-{}/{}.md".format(
            metadata["spec_id"], metadata["task_id"][-2:], journal["run_id"])
        documents = {item["path"]: item for item in journal["expected_docs"]}
        if set(documents) != set(status_docs) | {summary}:
            raise LedgerFinalizeError("LEDGER_FINALIZE_DOCUMENT_SET_MISMATCH")
        for path, expected in status_docs.items():
            if documents[path]["content"] != expected:
                raise LedgerFinalizeError("LEDGER_FINALIZE_MIRROR_CONTENT_MISMATCH")
        for path, document in documents.items():
            content = document["content"]
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest != document["after_sha256"] or read_text(contained(authority, path)) != content:
                raise LedgerFinalizeError("LEDGER_FINALIZE_DOCUMENT_AFTER_HASH_MISMATCH")
    except LedgerFinalizeError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise LedgerFinalizeError("LEDGER_FINALIZE_DOCUMENTS_INVALID") from exc


def finalize_ledger(conn: sqlite3.Connection, journal_path: Path, *, now: str) -> dict:
    """Finalize a committed journal; caller holds the common lock and principal/recovery proof."""
    if not isinstance(conn, sqlite3.Connection) or conn.in_transaction:
        raise LedgerFinalizeError("LEDGER_FINALIZE_CONNECTION_INVALID")
    _instant(now, "now")
    path = Path(journal_path)
    journal = validate_journal(read_journal(path))
    from .catalog_status import _gate_context

    main, _ = _gate_context(conn)
    expected_path = main / ".sdd/runtime/runs" / journal["run_id"] / "completion.json"
    if path.resolve(strict=True) != expected_path:
        raise LedgerFinalizeError("LEDGER_FINALIZE_JOURNAL_PATH_INVALID")
    if journal["phase"] == "complete":
        return _validate_complete_replay(conn, journal)
    if journal["phase"] not in {"index_reconciled", "ledger_finalizing"}:
        raise LedgerFinalizeError("LEDGER_FINALIZE_PHASE_INVALID")
    row = conn.execute("SELECT state FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
    if row is None:
        raise LedgerFinalizeError("LEDGER_FINALIZE_BINDING_MISSING")
    if journal["phase"] == "index_reconciled" or row["state"] in {"claimed", "running"}:
        target_status = _preflight_active(conn, journal, now)
        _verify_expected_documents(conn, journal, target_status)
        if journal["phase"] == "index_reconciled":
            advanced = dict(journal, phase="ledger_finalizing")
            write_journal(path, advanced, previous_phase="index_reconciled")
            journal = read_journal(path)
    if row["state"] in {"claimed", "running"}:
        _finalize_active_transaction(conn, journal, now)
        result = _validate_terminal_replay(conn, journal)
    elif journal["phase"] == "ledger_finalizing":
        result = _validate_terminal_replay(conn, journal)
    else:
        raise LedgerFinalizeError("LEDGER_FINALIZE_RUN_STATE_INVALID")
    write_journal(path, dict(journal, phase="complete"), previous_phase="ledger_finalizing")
    return result


def _finalize_active_transaction(conn, journal, now):
    if conn.in_transaction:
        raise LedgerFinalizeError("LEDGER_FINALIZE_TRANSACTION_ACTIVE")
    with transaction(conn, immediate=True):
        bindings = _validate_active_bindings(conn, journal, now)
        values = _terminal_values(conn, bindings, journal)
        run = bindings["run"]
        terminal = values["run"]
        cursor = conn.execute(
            "UPDATE runs SET state=?,model=?,started_at=?,ended_at=?,duration_ms=?,result_doc=?,"
            "error_code=?,error_summary=? WHERE run_id=? AND task_id=? "
            "AND state IN ('claimed','running') AND ended_at IS NULL AND task_hash=? "
            "AND prompt_hash=? AND base_commit=? AND owner_json=? AND executor_id=? AND attempt=? AND ide=?",
            terminal + (run["run_id"], run["task_id"], run["task_hash"], run["prompt_hash"],
                        run["base_commit"], run["owner_json"], run["executor_id"], run["attempt"],
                        run["ide"]))
        if cursor.rowcount != 1:
            raise LedgerFinalizeError("LEDGER_FINALIZE_RUN_CAS_FAILED")
        metadata = dict(bindings["metadata"])
        metadata["status"] = values["task_status"]
        definition = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        task = bindings["task"]
        cursor = conn.execute(
            "UPDATE tasks SET status=?,definition_json=? WHERE task_id=? AND status='pending' "
            "AND task_hash=? AND prompt_hash=? AND definition_json=?",
            (values["task_status"], definition, task["task_id"], task["task_hash"],
             task["prompt_hash"], task["definition_json"]))
        if cursor.rowcount != 1:
            raise LedgerFinalizeError("LEDGER_FINALIZE_TASK_CAS_FAILED")
        cursor = conn.execute("DELETE FROM leases WHERE task_id=? AND run_id=? AND owner_token=?",
                              (run["task_id"], run["run_id"], bindings["owner"].token))
        if cursor.rowcount != 1:
            raise LedgerFinalizeError("LEDGER_FINALIZE_LEASE_CAS_FAILED")
        _write_artifacts(conn, run["run_id"], values["artifacts"])
        _validate_terminal_views(conn, journal, values["task_status"])
