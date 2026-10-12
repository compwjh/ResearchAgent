"""Strict, filesystem-independent validation for sdd-run-result/v1 data."""

import re
import uuid
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Optional, Set

_ROOT = {
    "schema", "run_id", "task_id", "task_hash", "prompt_hash", "outcome", "summary",
    "changed_files", "artifacts", "commands", "tests", "decisions", "risks", "blockers",
    "main_agent_actions", "started_at", "ended_at", "duration_ms", "model",
    "token_usage", "tool_call_count", "log_paths",
}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TASK = re.compile(r"spec-\d{3}-task-\d{2}\Z")
_SECRET_KEY = re.compile(r"password|cookie|authorization|bearer|stdout|stderr|(?:api|access|refresh|client)[_.-]?(?:key|token|secret)", re.I)
_SECRET_VALUE = re.compile(r"\b(?:password|cookie|authorization|(?:api|access|refresh|client)[ _.-]?(?:key|token|secret))\b\s*[:=]\s*\S+|\bbearer\s+\S+|\b(?:sk-[\w-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[\w-]{10,})\b", re.I)
_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9_./:-])/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+|(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'<>]+")
_RAW_OUTPUT = re.compile(r"\b(?:raw[_ -]?)?(?:stdout|stderr)\s*[:=]", re.I)

def _bad(field: str, code: str = "RESULT_SCHEMA_INVALID") -> None:
    raise ValueError("{}: {}".format(code, field))

def _fields(value: Any, fields: Set[str], name: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _bad(name + ".fields")
    return value

def _text(value: Any, name: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        _bad(name + ".string")
    return value

def _count(value: Any, name: str, nullable: bool = False) -> Optional[int]:
    if nullable and value is None:
        return None
    if type(value) is not int or value < 0:
        _bad(name + ".integer")
    return value

def _hash(value: Any, name: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        _bad(name + ".sha256")

def _path(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _bad(name, "RESULT_PATH_ESCAPE")
    parts = value.split("/")
    windows = PureWindowsPath(value)
    if (PurePosixPath(value).is_absolute() or windows.is_absolute() or windows.drive or
            any(part in ("", ".", "..") or any(c in part for c in '*?[]:"<>|')
                for part in parts)):
        _bad(name, "RESULT_PATH_ESCAPE")

def _timestamp(value: Any, name: str) -> datetime:
    value = _text(value, name)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        _bad(name + ".iso8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _bad(name + ".timezone")
    return parsed

def _scan(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or _SECRET_KEY.search(key):
                _bad("sensitive_key", "RESULT_SENSITIVE_CONTENT")
            _scan(item)
    elif isinstance(value, list):
        for item in value:
            _scan(item)
    elif isinstance(value, str) and (
            _SECRET_VALUE.search(value) or _ABSOLUTE.search(value) or _RAW_OUTPUT.search(value)):
        _bad("sensitive_value", "RESULT_SENSITIVE_CONTENT")

def validate_summary_result(data: object) -> Dict[str, Any]:
    """Validate exact schema, strict values, and recursively reject unsafe content."""
    result = _fields(data, _ROOT, "root")
    schema, outcome = _text(result["schema"], "schema"), _text(result["outcome"], "outcome")
    if schema != "sdd-run-result/v1" or outcome not in {"succeeded", "failed", "blocked"}:
        _bad("schema_or_outcome")
    try:
        run_id = str(uuid.UUID(_text(result["run_id"], "run_id")))
    except (ValueError, AttributeError):
        _bad("run_id.uuid")
    if run_id != result["run_id"].lower() or not _TASK.fullmatch(_text(result["task_id"], "task_id")):
        _bad("run_id_or_task_id")
    _hash(result["task_hash"], "task_hash")
    _hash(result["prompt_hash"], "prompt_hash")
    _text(result["summary"], "summary")
    start, end = _timestamp(result["started_at"], "started_at"), _timestamp(result["ended_at"], "ended_at")
    if end < start:
        _bad("ended_at.order")
    _count(result["duration_ms"], "duration_ms")
    _count(result["tool_call_count"], "tool_call_count", True)
    if result["model"] is not None:
        _text(result["model"], "model")
    usage = _fields(result["token_usage"], {"input", "output", "total", "source"}, "token_usage")
    for key in ("input", "output", "total"):
        _count(usage[key], "token_usage." + key, True)
    if usage["source"] is not None:
        _text(usage["source"], "token_usage.source")
    if (usage["total"] is not None and usage["input"] is not None and
            usage["output"] is not None and
            usage["total"] != usage["input"] + usage["output"]):
        _bad("token_usage.total")
    for key in ("risks", "blockers", "main_agent_actions", "log_paths"):
        values = result[key]
        if not isinstance(values, list):
            _bad(key + ".array")
        for index, value in enumerate(values):
            _path(value, "{}.{}".format(key, index)) if key == "log_paths" else _text(value, "{}.{}".format(key, index))
    for key in ("changed_files", "artifacts", "commands", "tests", "decisions"):
        if not isinstance(result[key], list):
            _bad(key + ".array")
    for item in result["changed_files"]:
        item = _fields(item, {"path", "change", "additions", "deletions", "sha256"}, "changed_files")
        _path(item["path"], "changed_files.path")
        change = _text(item["change"], "changed_files.change")
        if change not in {"added", "modified", "deleted", "renamed"}:
            _bad("changed_files.change")
        _count(item["additions"], "changed_files.additions", True)
        _count(item["deletions"], "changed_files.deletions", True)
        if change == "deleted":
            if item["sha256"] is not None:
                _bad("changed_files.deleted_sha256")
        else:
            _hash(item["sha256"], "changed_files.sha256")
    for item in result["artifacts"]:
        item = _fields(item, {"path", "kind", "sha256", "included_in_commit"}, "artifacts")
        _path(item["path"], "artifacts.path")
        _text(item["kind"], "artifacts.kind")
        _hash(item["sha256"], "artifacts.sha256")
        if item["included_in_commit"] is not None and type(item["included_in_commit"]) is not bool:
            _bad("artifacts.included_in_commit.boolean")
    for item in result["commands"]:
        item = _fields(item, {"argv", "status", "exit_code", "duration_ms", "summary"}, "commands")
        if not isinstance(item["argv"], list) or not item["argv"]:
            _bad("commands.argv.array")
        for arg in item["argv"]:
            _text(arg, "commands.argv")
        status = _text(item["status"], "commands.status")
        if status == "executed":
            if type(item["exit_code"]) is not int:
                _bad("commands.exit_code")
        elif status == "skipped":
            if item["exit_code"] is not None:
                _bad("commands.skipped_exit_code")
        else:
            _bad("commands.status")
        _count(item["duration_ms"], "commands.duration_ms", True)
        _text(item["summary"], "commands.summary")
    for item in result["tests"]:
        item = _fields(item, {"name", "outcome", "exit_code", "summary"}, "tests")
        _text(item["name"], "tests.name")
        _text(item["summary"], "tests.summary")
        outcome, code = _text(item["outcome"], "tests.outcome"), item["exit_code"]
        if outcome not in {"passed", "failed", "skipped", "not_run"}:
            _bad("tests.outcome")
        if (outcome == "passed" and type(code) is not int or outcome == "passed" and code != 0 or
                outcome == "failed" and (type(code) is not int or code == 0) or
                outcome in {"skipped", "not_run"} and code is not None):
            _bad("tests.exit_code_consistency")
    for item in result["decisions"]:
        item = _fields(item, {"decision", "evidence"}, "decisions")
        _text(item["decision"], "decisions.decision")
        _text(item["evidence"], "decisions.evidence")
    _scan(result)
    return result
