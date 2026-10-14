"""Resume an existing Task06 journal only after proving its owner is dead."""

import hmac
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .atomic import contained
from .catalog_status import _metadata
from .completion_lifecycle import run_completion_journal
from .completion_service import (
    CompletionServiceError,
    _instant,
    _owner_value,
    _read_existing_journal,
    _run_context,
    _same_owner,
)
from .documents import parse_task
from .lease_recovery import stored_owner
from .owners import OwnerStatus, observe_owner


class CompletionRecoveryError(ValueError):
    """An existing completion journal cannot be safely resumed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _reject(code: str) -> None:
    raise CompletionRecoveryError(code)


def _same_token(actual: object, expected: str) -> bool:
    try:
        return isinstance(actual, str) and hmac.compare_digest(
            actual.encode("utf-8"), expected.encode("utf-8"))
    except UnicodeError:
        return False


def resume_dead_completion(conn, repo_root: Path, run_id: str) -> Optional[dict]:
    """Resume an authenticated dead-owner journal; caller holds the common lock."""
    if (not isinstance(conn, sqlite3.Connection) or conn.in_transaction or
            not isinstance(repo_root, Path) or not isinstance(run_id, str)):
        _reject("RECOVER_INPUT_INVALID")
    try:
        canonical = str(uuid.UUID(run_id))
    except (AttributeError, TypeError, ValueError):
        _reject("RECOVER_INPUT_INVALID")
    if canonical != run_id:
        _reject("RECOVER_INPUT_INVALID")
    try:
        main, worktree, task_row, run = _run_context(conn, repo_root, canonical)
        journal = _read_existing_journal(main, canonical)
    except (CompletionServiceError, OSError, KeyError, TypeError, ValueError, sqlite3.Error):
        _reject("RECOVER_JOURNAL_OR_BINDING_INVALID")
    if journal is None:
        return None

    try:
        metadata = _metadata(dict(task_row))
        definition = parse_task(contained(worktree, task_row["source_path"]))
        canonical_metadata = {key: value for key, value in definition.metadata.items()
                              if key != "status"}
        stored_metadata = {key: value for key, value in metadata.items() if key != "status"}
        if (definition.task_hash != task_row["task_hash"] or
                definition.prompt_hash != task_row["prompt_hash"] or
                canonical_metadata != stored_metadata or
                journal["run_id"] != canonical or journal["task_id"] != run["task_id"] or
                run["task_id"] != task_row["task_id"] or
                journal["base_commit"] != run["base_commit"] or
                journal["task_hash"] != run["task_hash"] or
                journal["prompt_hash"] != run["prompt_hash"] or
                task_row["task_hash"] != run["task_hash"] or
                task_row["prompt_hash"] != run["prompt_hash"] or
                run["worktree"] != metadata["worktree"]["path"] or
                run["branch"] != metadata["worktree"]["branch"]):
            _reject("RECOVER_BINDING_MISMATCH")
        expected = _owner_value(journal["owner"])
        owner = stored_owner(run["owner_json"])
        if (run["executor_id"] != expected["executor_id"] or
                not _same_owner(owner, expected)):
            _reject("RECOVER_OWNER_MISMATCH")
    except CompletionRecoveryError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error):
        _reject("RECOVER_BINDING_OR_OWNER_INVALID")

    try:
        status = observe_owner(owner)
    except (OSError, TypeError, ValueError):
        _reject("RECOVER_OWNER_UNKNOWN")
    if status is OwnerStatus.ALIVE:
        _reject("RECOVER_OWNER_ALIVE")
    if status is not OwnerStatus.DEAD:
        _reject("RECOVER_OWNER_UNKNOWN")

    now = datetime.now(timezone.utc)
    try:
        leases = conn.execute("SELECT * FROM leases WHERE task_id=? OR run_id=?",
                              (run["task_id"], canonical)).fetchall()
    except sqlite3.Error:
        _reject("RECOVER_LEDGER_INVALID")
    active = run["state"] in {"claimed", "running"} and run["ended_at"] is None
    terminal = (run["state"] == journal["terminal_outcome"] and
                run["state"] in {"succeeded", "failed", "blocked"} and
                run["ended_at"] is not None)
    if active:
        if journal["phase"] == "complete" or len(leases) != 1:
            _reject("RECOVER_LEASE_MISMATCH")
        lease = leases[0]
        try:
            expiry = _instant(lease["expires_at"], "lease.expires_at")
        except (CompletionServiceError, TypeError, ValueError):
            _reject("RECOVER_LEASE_INVALID")
        if (lease["run_id"] != canonical or lease["task_id"] != run["task_id"] or
                lease["claimed_at"] != run["claimed_at"] or
                not _same_token(lease["owner_token"], owner.token)):
            _reject("RECOVER_LEASE_MISMATCH")
        if expiry > now:
            _reject("RECOVER_LEASE_UNEXPIRED")
    elif (not terminal or journal["phase"] not in {"ledger_finalizing", "complete"} or
          leases):
        _reject("RECOVER_TERMINAL_PROOF_INVALID")
    try:
        result = run_completion_journal(
            conn, main / ".sdd" / "runtime" / "runs" / canonical / "completion.json",
            run["branch"], now.isoformat().replace("+00:00", "Z"),
        )
    except (OSError, TypeError, ValueError, sqlite3.Error):
        _reject("RECOVER_COMPLETION_FAILED")
    if result != journal["expected_result"]:
        _reject("RECOVER_RESULT_MISMATCH")
    return result
