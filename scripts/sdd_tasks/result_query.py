"""Read one fully validated terminal result from the rebuilt task ledger."""

import sqlite3
import uuid

from .atomic import contained, read_text
from .catalog_status import _gate_context, _live_gate_task, _metadata
from .result_schema import _scan
from .summaries import _blocks, _record
from .summary_import import validate_base_commits


class ResultQueryError(ValueError):
    """A terminal result is missing or cannot be validated safely."""

    code = "RESULT_NOT_AVAILABLE"

    def __init__(self) -> None:
        super().__init__(self.code)


_COLUMNS = (
    "run_id", "task_id", "attempt", "state", "ide", "executor_id", "agent_role",
    "model", "worktree", "branch", "base_commit", "task_hash", "prompt_hash",
    "claimed_at", "started_at", "ended_at", "duration_ms", "result_doc",
)


def result_for_run(conn: sqlite3.Connection, run_id: str) -> dict:
    """Return a canonical summary result after binding it to terminal ledger data."""
    try:
        if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
            raise ResultQueryError()
        columns = ",".join(_COLUMNS)
        run = conn.execute("SELECT {} FROM runs WHERE run_id=?".format(columns),
                           (run_id,)).fetchone()
        if run is None or run["state"] not in {"succeeded", "failed", "blocked"}:
            raise ResultQueryError()
        if not isinstance(run["result_doc"], str):
            raise ResultQueryError()
        taskrow = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks WHERE task_id=?",
            (run["task_id"],),
        ).fetchone()
        if taskrow is None:
            raise ResultQueryError()
        main, roots = _gate_context(conn)
        metadata = _metadata(dict(taskrow))
        task = _live_gate_task(dict(taskrow), metadata, main, roots)
        relative = "docs/sdd/runs/{}/task-{}/{}.md".format(
            metadata["spec_id"], metadata["task_id"][-2:], run_id)
        if run["result_doc"] != relative:
            raise ResultQueryError()
        authority = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        if authority not in roots:
            raise ResultQueryError()
        path = contained(authority, relative)
        content = read_text(path)
        _scan(content)
        result, summary_meta = _blocks(content, path)
        record = _record(result, summary_meta, task, relative, path)
        if any(record[key] != run[key] for key in _COLUMNS):
            raise ResultQueryError()
        validate_base_commits(main, [record])
        return result
    except ResultQueryError:
        raise
    except (AttributeError, IndexError, KeyError, OSError, sqlite3.Error,
            TypeError, UnicodeError, ValueError):
        raise ResultQueryError() from None
