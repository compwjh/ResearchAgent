"""Export read-only metrics from ledger rows and validated terminal summaries."""

import csv
import io
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from .metrics_filters import METRIC_COLUMNS, METRIC_SCHEMA, validate_metrics_filters
from .result_query import ResultQueryError, result_for_run

_TASK_ID = re.compile(r"spec-(\d{3})-task-\d{2}\Z")
_STATES = frozenset({"claimed", "running", "succeeded", "failed", "blocked", "abandoned"})
_TERMINAL = frozenset({"succeeded", "failed", "blocked"})


class MetricsError(ValueError):
    """Metrics could not be exported from a consistent, validated ledger view."""


def _instant(value, field, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise MetricsError("METRICS_LEDGER_INVALID:" + field)
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise MetricsError("METRICS_LEDGER_INVALID:" + field) from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise MetricsError("METRICS_LEDGER_INVALID:" + field)
    return instant.astimezone(timezone.utc)


def _sum_changes(changes, field):
    values = [item[field] for item in changes]
    return None if any(value is None for value in values) else sum(values)


def export_metrics(conn: sqlite3.Connection, *, filters: dict, format: str) -> str:
    """Export fixed-schema JSON or CSV without reading private owner/event payloads."""
    if not isinstance(conn, sqlite3.Connection):
        raise MetricsError("METRICS_CONNECTION_INVALID")
    if not isinstance(format, str) or format not in {"json", "csv"}:
        raise MetricsError("METRICS_FORMAT_INVALID")
    selected = validate_metrics_filters(filters)
    from_time = _instant(selected["time_from"], "time_from") if "time_from" in selected else None
    to_time = _instant(selected["time_to"], "time_to") if "time_to" in selected else None
    query = ("SELECT run_id,task_id,attempt,state,agent_role,model,claimed_at,started_at,"
             "ended_at,duration_ms FROM runs ORDER BY claimed_at,run_id")
    rows = []
    for record in conn.execute(query):
        task_id = record["task_id"]
        match = _TASK_ID.fullmatch(task_id) if isinstance(task_id, str) else None
        if not match or not isinstance(record["run_id"], str):
            raise MetricsError("METRICS_LEDGER_INVALID:identity")
        try:
            canonical_run_id = str(uuid.UUID(record["run_id"]))
        except ValueError as exc:
            raise MetricsError("METRICS_LEDGER_INVALID:run_id") from exc
        if (canonical_run_id != record["run_id"] or
                type(record["attempt"]) is not int or record["attempt"] < 1 or
                record["state"] not in _STATES or not isinstance(record["agent_role"], str) or
                not record["agent_role"].strip() or
                (record["model"] is not None and
                 (not isinstance(record["model"], str) or not record["model"].strip()))):
            raise MetricsError("METRICS_LEDGER_INVALID:run")
        spec_id, state = match.group(1), record["state"]
        outcome = state if state in _TERMINAL else None
        if ("spec_id" in selected and selected["spec_id"] != spec_id or
                "task_id" in selected and selected["task_id"] != task_id or
                "agent_role" in selected and selected["agent_role"] != record["agent_role"] or
                "model" in selected and selected["model"] != record["model"] or
                "outcome" in selected and selected["outcome"] != outcome):
            continue
        claimed = _instant(record["claimed_at"], "claimed_at")
        started = _instant(record["started_at"], "started_at", True)
        ended = _instant(record["ended_at"], "ended_at", True)
        anchor = started or claimed
        if (from_time is not None and anchor < from_time) or (to_time is not None and anchor >= to_time):
            continue
        duration = record["duration_ms"]
        if duration is not None and (type(duration) is not int or duration < 0):
            raise MetricsError("METRICS_LEDGER_INVALID:duration_ms")
        if state in {"claimed", "running"} and (ended is not None or duration is not None):
            raise MetricsError("METRICS_LEDGER_INVALID:active_run")
        row = dict.fromkeys(METRIC_COLUMNS)
        row.update(spec_id=spec_id, run_id=record["run_id"], task_id=task_id,
                   attempt=record["attempt"], state=state, outcome=outcome,
                   agent_role=record["agent_role"], model=record["model"],
                   claimed_at=record["claimed_at"], started_at=record["started_at"],
                   ended_at=record["ended_at"], duration_ms=duration,
                   duration_source="ledger" if duration is not None else "unavailable",
                   model_source="ledger" if record["model"] is not None else "unavailable",
                   token_usage_source="unavailable", tool_call_source="unavailable",
                   change_source="unavailable")
        if state in _TERMINAL:
            try:
                result = result_for_run(conn, record["run_id"])
            except ResultQueryError as exc:
                raise MetricsError("METRICS_RESULT_UNAVAILABLE") from exc
            usage, changes = result["token_usage"], result["changed_files"]
            additions, deletions = (_sum_changes(changes, "additions"),
                                    _sum_changes(changes, "deletions"))
            row.update(outcome=result["outcome"], token_input=usage["input"],
                       token_output=usage["output"], token_total=usage["total"],
                       token_usage_source=usage["source"] or "unavailable",
                       tool_call_count=result["tool_call_count"], changed_file_count=len(changes),
                       additions=additions, deletions=deletions,
                       tool_call_source=("canonical_summary" if result["tool_call_count"] is not None
                                         else "unavailable"),
                       change_source=("canonical_summary" if additions is not None and
                                      deletions is not None else "unavailable"))
        rows.append((anchor, record["run_id"], row))
    payload_rows = [item[2] for item in sorted(rows, key=lambda item: (item[0], item[1]))]
    if format == "json":
        return json.dumps({"schema": METRIC_SCHEMA, "filters": selected,
                           "columns": list(METRIC_COLUMNS), "rows": payload_rows},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(METRIC_COLUMNS)
    writer.writerows([[row[column] for column in METRIC_COLUMNS] for row in payload_rows])
    return output.getvalue()
