"""Frozen Task metrics schema and filter validation."""

import re
from datetime import datetime, timezone
from typing import Any, Dict

METRIC_SCHEMA = "sdd-task-metrics/v1"
METRIC_SOURCES = frozenset({"canonical_summary", "ledger", "unavailable"})
METRIC_COLUMNS = (
    "spec_id", "run_id", "task_id", "attempt", "state", "outcome", "agent_role",
    "model", "claimed_at", "started_at", "ended_at", "duration_ms", "token_input",
    "token_output", "token_total", "token_usage_source", "tool_call_count",
    "changed_file_count", "additions", "deletions", "duration_source", "model_source",
    "tool_call_source", "change_source",
)
_FILTER_KEYS = frozenset({
    "spec_id", "task_id", "agent_role", "model", "outcome", "time_from", "time_to",
})
_TASK_ID = re.compile(r"spec-(\d{3})-task-\d{2}\Z")
_SPEC_ID = re.compile(r"\d{3}\Z")
_OUTCOMES = frozenset({"succeeded", "failed", "blocked"})


def _invalid(field: str) -> ValueError:
    return ValueError("METRICS_FILTER_INVALID:" + field)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(field)
    return value


def _time(value: Any, field: str) -> tuple:
    if not isinstance(value, str):
        raise _invalid(field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise _invalid(field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid(field)
    parsed = parsed.astimezone(timezone.utc)
    normalized = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return parsed, normalized


def validate_metrics_filters(filters: dict) -> Dict[str, Any]:
    """Validate filters; time_from is inclusive and time_to is exclusive."""
    if not isinstance(filters, dict):
        raise _invalid("object")
    unknown = set(filters) - _FILTER_KEYS
    if unknown or any(not isinstance(key, str) for key in filters):
        raise _invalid("unknown_key")
    result = {}
    if "spec_id" in filters:
        value = _text(filters["spec_id"], "spec_id")
        if not _SPEC_ID.fullmatch(value):
            raise _invalid("spec_id")
        result["spec_id"] = value
    if "task_id" in filters:
        value = _text(filters["task_id"], "task_id")
        if not _TASK_ID.fullmatch(value):
            raise _invalid("task_id")
        result["task_id"] = value
    if "agent_role" in filters:
        result["agent_role"] = _text(filters["agent_role"], "agent_role")
    if "model" in filters:
        value = filters["model"]
        result["model"] = None if value is None else _text(value, "model")
    if "outcome" in filters:
        value = _text(filters["outcome"], "outcome")
        if value not in _OUTCOMES:
            raise _invalid("outcome")
        result["outcome"] = value
    parsed_times = {}
    for key in ("time_from", "time_to"):
        if key in filters:
            parsed_times[key], result[key] = _time(filters[key], key)
    if ("time_from" in parsed_times and "time_to" in parsed_times and
            parsed_times["time_from"] >= parsed_times["time_to"]):
        raise _invalid("time_order")
    return result
