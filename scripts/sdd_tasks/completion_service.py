"""Owner-authenticated complete/fail service for Task06 run results."""

import hmac
import json
import os
import sqlite3
import stat
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from .atomic import _open_directory
from .catalog_status import _metadata
from .completion_lifecycle import run_completion_journal
from .git_reconciliation_index import (
    _git,
    _main_run_fd,
    _read_private_file,
    _verify_run_fd,
)
from .journal_schema import validate_journal
from .lease_recovery import stored_owner
from .owners import OwnerIdentity, OwnerStatus, observe_owner
from .result_schema import validate_summary_result

_OWNER_FIELDS = {"executor_id", "host_id", "pid", "process_started_at", "token"}


class CompletionServiceError(ValueError):
    """A Task06 result cannot be safely completed or failed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value):
    raise ValueError("invalid JSON constant")


def _instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise CompletionServiceError("COMPLETION_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise CompletionServiceError("COMPLETION_TIME_INVALID") from exc
    if parsed.utcoffset() != timedelta(0):
        raise CompletionServiceError("COMPLETION_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _server_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _elapsed_ms(started_at: str, ended_at: str) -> int:
    elapsed = (_instant(ended_at, "ended_at") - _instant(started_at, "started_at")).total_seconds()
    if elapsed < 0:
        raise CompletionServiceError("COMPLETION_TIME_REGRESSION")
    return int(elapsed * 1000)


def _validate_request(conn, repo_root, run_id, executor_id, owner_pid) -> str:
    if (not isinstance(conn, sqlite3.Connection) or conn.in_transaction or
            not isinstance(repo_root, Path) or not isinstance(run_id, str) or
            not isinstance(executor_id, str) or not executor_id.strip() or
            type(owner_pid) is not int or owner_pid < 1):
        raise CompletionServiceError("COMPLETION_INPUT_INVALID")
    try:
        canonical_id = str(uuid.UUID(run_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CompletionServiceError("COMPLETION_INPUT_INVALID") from exc
    if canonical_id != run_id:
        raise CompletionServiceError("COMPLETION_INPUT_INVALID")
    return canonical_id


def _parse_result(raw_result: Any) -> Dict[str, Any]:
    """Parse one strict result object without exposing actor-controlled details."""
    try:
        if isinstance(raw_result, bytes):
            raw_result = raw_result.decode("utf-8")
        if isinstance(raw_result, str):
            data = json.loads(raw_result, object_pairs_hook=_pairs,
                              parse_constant=_reject_json_constant)
        elif isinstance(raw_result, dict):
            encoded = json.dumps(raw_result, ensure_ascii=False, allow_nan=False)
            data = json.loads(encoded, object_pairs_hook=_pairs,
                              parse_constant=_reject_json_constant)
        else:
            raise ValueError("result must be JSON object")
        return dict(validate_summary_result(data))
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise CompletionServiceError("COMPLETION_RESULT_INVALID") from exc


def _owner_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value, object_pairs_hook=_pairs,
                               parse_constant=_reject_json_constant)
        except (TypeError, ValueError, RecursionError) as exc:
            raise CompletionServiceError("COMPLETION_OWNER_INVALID") from exc
    if (not isinstance(value, dict) or set(value) != _OWNER_FIELDS or
            any(not isinstance(value[key], str) or not value[key].strip()
                for key in _OWNER_FIELDS - {"pid"}) or
            type(value["pid"]) is not int or value["pid"] < 1):
        raise CompletionServiceError("COMPLETION_OWNER_INVALID")
    return value


def _same_owner(actual: OwnerIdentity, expected: Dict[str, Any]) -> bool:
    if (not isinstance(actual, OwnerIdentity) or
            any(getattr(actual, field) != expected[field]
                for field in _OWNER_FIELDS - {"token"})):
        return False
    try:
        return hmac.compare_digest(actual.token.encode("utf-8"), expected["token"].encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False


def _run_directory_present(main: Path, run_id: str) -> bool:
    """Inspect the private run path without creating directories or following links."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    current = -1
    try:
        try:
            current = _open_directory(main / ".sdd" / "runtime")
        except FileNotFoundError:
            return False
        info = os.fstat(current)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise CompletionServiceError("COMPLETION_RUNTIME_UNSAFE")
        for name in ("runs", run_id):
            try:
                child = os.open(name, flags, dir_fd=current)
            except FileNotFoundError:
                return False
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o700):
                os.close(child)
                raise CompletionServiceError("COMPLETION_RUNTIME_UNSAFE")
            os.close(current)
            current = child
        return True
    except CompletionServiceError:
        raise
    except OSError as exc:
        raise CompletionServiceError("COMPLETION_RUNTIME_UNSAFE") from exc
    finally:
        if current >= 0:
            os.close(current)


def _read_existing_journal(main: Path, run_id: str):
    """Read a canonical journal through pinned private directories; absence is read-only."""
    path = main / ".sdd" / "runtime" / "runs" / run_id / "completion.json"
    if not _run_directory_present(main, run_id):
        return None
    try:
        _git(main, "check-ignore", "--quiet", "--", ".sdd/runtime/runs/{}/completion.json".format(run_id))
        _, parent = _main_run_fd(main, path, run_id)
        try:
            try:
                os.stat("completion.json", dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return None
            content = _read_private_file(parent, "completion.json")
            _verify_run_fd(main, run_id, parent)
        finally:
            os.close(parent)
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_reject_json_constant)
        return validate_journal(value)
    except CompletionServiceError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise CompletionServiceError("COMPLETION_JOURNAL_UNSAFE") from exc


def _authenticate_journal(
    conn: sqlite3.Connection, journal: Dict[str, Any], run, executor_id: str, owner_pid: int,
) -> str:
    """Bind an existing journal to its stored live owner and immutable ledger rows."""
    try:
        expected = _owner_value(journal["owner"])
        stored = stored_owner(run["owner_json"])
        if (expected["executor_id"] != executor_id or expected["pid"] != owner_pid or
                not _same_owner(stored, expected) or observe_owner(stored) is not OwnerStatus.ALIVE):
            raise CompletionServiceError("COMPLETION_OWNER_MISMATCH")
        if (journal["run_id"] != run["run_id"] or journal["task_id"] != run["task_id"] or
                run["executor_id"] != expected["executor_id"] or
                journal["base_commit"] != run["base_commit"] or
                journal["task_hash"] != run["task_hash"] or
                journal["prompt_hash"] != run["prompt_hash"]):
            raise CompletionServiceError("COMPLETION_JOURNAL_BINDING_MISMATCH")
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone()
        if task is None:
            raise CompletionServiceError("COMPLETION_JOURNAL_BINDING_MISMATCH")
        metadata = _metadata(dict(task))
        worktree = metadata.get("worktree")
        if (task["task_hash"] != journal["task_hash"] or
                task["prompt_hash"] != journal["prompt_hash"] or
                not isinstance(worktree, dict) or run["worktree"] != worktree.get("path") or
                run["branch"] != worktree.get("branch")):
            raise CompletionServiceError("COMPLETION_JOURNAL_BINDING_MISMATCH")

        lease = conn.execute("SELECT * FROM leases WHERE run_id=?", (run["run_id"],)).fetchone()
        if run["state"] in {"claimed", "running"} and run["ended_at"] is None:
            if (lease is None or lease["task_id"] != run["task_id"] or
                    lease["run_id"] != run["run_id"] or
                    not hmac.compare_digest(lease["owner_token"].encode("utf-8"),
                                            stored.token.encode("utf-8"))):
                raise CompletionServiceError("COMPLETION_JOURNAL_OWNER_MISMATCH")
        elif (lease is not None or run["state"] != journal["terminal_outcome"] or
              run["ended_at"] is None or journal["phase"] not in {"ledger_finalizing", "complete"}):
            raise CompletionServiceError("COMPLETION_JOURNAL_OUTCOME_MISMATCH")
        return run["branch"]
    except CompletionServiceError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise CompletionServiceError("COMPLETION_JOURNAL_BINDING_MISMATCH") from exc


def _replay_existing(
    conn: sqlite3.Connection, main: Path, run_id: str, executor_id: str, owner_pid: int,
    allowed_outcomes,
):
    journal = _read_existing_journal(main, run_id)
    if journal is None:
        return None
    if journal["run_id"] != run_id or journal["terminal_outcome"] not in allowed_outcomes:
        raise CompletionServiceError("COMPLETION_JOURNAL_OUTCOME_MISMATCH")
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if run is None:
        raise CompletionServiceError("COMPLETION_JOURNAL_BINDING_MISMATCH")
    branch = _authenticate_journal(conn, journal, run, executor_id, owner_pid)
    path = main / ".sdd" / "runtime" / "runs" / run_id / "completion.json"
    try:
        return run_completion_journal(conn, path, branch, _server_now())
    except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
        raise CompletionServiceError("COMPLETION_RECOVERY_REQUIRED") from exc
