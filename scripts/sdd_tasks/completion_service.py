"""Owner-authenticated complete/fail service for Task06 run results."""

import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from .owners import OwnerIdentity
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
