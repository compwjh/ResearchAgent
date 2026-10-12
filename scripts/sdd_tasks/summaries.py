"""Strict reader for rebuildable TaskRun summary documents."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Mapping

from .atomic import read_text
from .documents import TaskDefinition
from .result_schema import _scan, validate_summary_result

_RB, _RE = "<!-- sdd-run-result:v1:begin -->", "<!-- sdd-run-result:v1:end -->"
_MB, _ME = "<!-- sdd-run-meta:v1:begin -->", "<!-- sdd-run-meta:v1:end -->"
_META = {
    "schema", "run_id", "task_id", "task_hash", "prompt_hash", "attempt", "ide",
    "executor_id", "agent_role", "model", "worktree", "branch", "base_commit", "claimed_at",
}

class SummaryError(ValueError):
    def __init__(self, code: str, path: Path, detail: str) -> None:
        self.code, self.path = code, Path(path)
        super().__init__("{} {}: {}".format(code, path, detail))

def _pairs(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("duplicate JSON key: " + key)
        obj[key] = value
    return obj

def _constant(value): raise ValueError("invalid JSON constant: " + value)

def _blocks(text: str, path: Path):
    lines = text.splitlines()
    marks = (_RB, _RE, _MB, _ME)
    positions = [[i for i, line in enumerate(lines) if line == mark] for mark in marks]
    if any(text.count(mark) != 1 or len(positions[index]) != 1
           for index, mark in enumerate(marks)):
        raise SummaryError("SUMMARY_MARKERS_INVALID", path, "markers must each occur once on their own line")
    rb, re_, mb, me = (found[0] for found in positions)
    if rb >= re_ or mb >= me or not (re_ < mb or me < rb):
        raise SummaryError("SUMMARY_MARKERS_INVALID", path, "blocks overlap or are incomplete")
    parsed = []
    for begin, end in ((rb, re_), (mb, me)):
        try:
            value = json.loads("\n".join(lines[begin + 1:end]), object_pairs_hook=_pairs, parse_constant=_constant)
        except (ValueError, TypeError) as exc:
            raise SummaryError("SUMMARY_JSON_INVALID", path, str(exc)) from exc
        if not isinstance(value, dict):
            raise SummaryError("SUMMARY_JSON_INVALID", path, "expected one JSON object")
        parsed.append(value)
    return parsed

def _safe_chain(root: Path, path: Path) -> None:
    root = Path(root).resolve()
    path = Path(os.path.abspath(str(path)))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SummaryError("SUMMARY_PATH_INVALID", path, "outside registered root") from exc
    current = path
    while current != root:
        if current.is_symlink():
            raise SummaryError("SUMMARY_SYMLINK", path, str(current))
        current = current.parent

def _task_map(tasks) -> Dict[str, TaskDefinition]:
    source = tasks.values() if isinstance(tasks, Mapping) else tasks
    found = {}
    for item in source:
        task = item[0] if isinstance(item, tuple) else item
        task_id = task.metadata["task_id"]
        if task_id in found:
            raise SummaryError("TASK_DEFINITION_AMBIGUOUS", task.path, task_id)
        found[task_id] = task
    return found

def _record(result, meta, task, rel: str, path: Path) -> dict:
    if set(meta) != _META or meta.get("schema") != "sdd-run-meta/v1":
        raise SummaryError("SUMMARY_META_SCHEMA_INVALID", path, "unknown or missing metadata fields")
    try:
        _scan(meta)
        result = validate_summary_result(result)
    except ValueError as exc:
        raise SummaryError("SUMMARY_SCHEMA_INVALID", path, str(exc)) from exc
    for key in ("ide", "executor_id", "agent_role", "worktree", "branch", "base_commit", "claimed_at"):
        if not isinstance(meta[key], str) or not meta[key].strip():
            raise SummaryError("SUMMARY_META_INVALID", path, key)
    if (type(meta["attempt"]) is not int or meta["attempt"] < 1 or
            (meta["model"] is not None and not isinstance(meta["model"], str))):
        raise SummaryError("SUMMARY_META_INVALID", path, "attempt or model")
    if (meta["run_id"] != result["run_id"] or meta["task_id"] != result["task_id"] or
            meta["task_hash"] != result["task_hash"] or meta["prompt_hash"] != result["prompt_hash"]):
        raise SummaryError("SUMMARY_BINDING_MISMATCH", path, "result and metadata IDs/hashes differ")
    md = task.metadata
    if (result["task_id"] != md["task_id"] or result["task_hash"] != task.task_hash or
            result["prompt_hash"] != task.prompt_hash or meta["agent_role"] != md["agent_role"] or
            meta["worktree"] != md["worktree"]["path"] or meta["branch"] != md["worktree"]["branch"] or
            meta["model"] != result["model"]):
        raise SummaryError("SUMMARY_BINDING_MISMATCH", path, "summary does not match Task definition")
    if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", meta["base_commit"]):
        raise SummaryError("SUMMARY_META_INVALID", path, "base_commit")
    try:
        claimed = datetime.fromisoformat(meta["claimed_at"].replace("Z", "+00:00"))
        started = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))
        if claimed.utcoffset() is None or claimed > started:
            raise ValueError("claimed_at timezone/order")
    except ValueError as exc:
        raise SummaryError("SUMMARY_META_INVALID", path, "claimed_at") from exc
    number = md["task_id"][-2:]
    expected = "docs/sdd/runs/{}/task-{}/{}.md".format(md["spec_id"], number, result["run_id"])
    if rel != expected:
        raise SummaryError("SUMMARY_PATH_MISMATCH", path, expected)
    return {"run_id": result["run_id"], "task_id": result["task_id"], "attempt": meta["attempt"],
            "state": result["outcome"], "ide": meta["ide"], "executor_id": meta["executor_id"],
            "owner_json": "{}", "agent_role": meta["agent_role"], "model": meta["model"],
            "worktree": meta["worktree"], "branch": meta["branch"], "base_commit": meta["base_commit"],
            "task_hash": result["task_hash"], "prompt_hash": result["prompt_hash"],
            "claimed_at": meta["claimed_at"], "started_at": result["started_at"],
            "ended_at": result["ended_at"], "duration_ms": result["duration_ms"],
            "result_doc": rel, "error_code": None, "error_summary": None}

def scan_summaries(roots, tasks):
    """Parse and validate all summary files before a caller mutates the ledger."""
    by_task, by_run, records = _task_map(tasks), {}, []
    for root in roots:
        root = Path(root).resolve()
        base = root / "docs/sdd/runs"
        _safe_chain(root, base)
        if not base.is_dir():
            continue
        for directory, dirs, files in os.walk(str(base), followlinks=False):
            parent = Path(directory)
            for name in dirs:
                if (parent / name).is_symlink():
                    raise SummaryError("SUMMARY_SYMLINK", parent / name, "symlink directory")
            for name in files:
                path = parent / name
                if path.suffix != ".md":
                    continue
                _safe_chain(root, path)
                try:
                    content = read_text(path)
                    try:
                        _scan(content)
                    except ValueError as exc:
                        raise SummaryError(
                            "SUMMARY_SENSITIVE_CONTENT", path, "sensitive content is forbidden"
                        ) from exc
                    result, meta = _blocks(content, path)
                    task = by_task[meta.get("task_id")]
                    record = _record(result, meta, task, path.relative_to(root).as_posix(), path)
                except SummaryError:
                    raise
                except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
                    raise SummaryError("SUMMARY_READ_INVALID", path, str(exc)) from exc
                old = by_run.get(record["run_id"])
                if old:
                    if old[0] != content:
                        raise SummaryError("RUN_ID_CONTENT_CONFLICT", path, record["run_id"])
                    continue
                by_run[record["run_id"]] = (content, record)
                records.append(record)
    return tuple(records)
