import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Optional

from .atomic import read_text
from .result_schema import _scan

META = ("<!-- sdd-task-meta:v1:begin -->", "<!-- sdd-task-meta:v1:end -->")
PROMPT = ("<!-- sdd-task-prompt:v1:begin -->", "<!-- sdd-task-prompt:v1:end -->")
FIELDS = {"schema_version", "task_id", "spec_id", "title", "status", "priority", "created_at",
          "depends_on", "required_gates", "agent_role", "required_capabilities", "allowed_paths",
          "worktree", "max_attempts", "prompt_version", "return_schema", "expected_artifacts",
          "validation_commands", "migration_state"}
REQUIRED = FIELDS - {"priority", "max_attempts", "migration_state"}
VARS = {"RUN_ID", "WORKTREE", "BASE_COMMIT", "RESULT_PATH", "EVENT_PATH"}
PROMPT_LABELS = ("Role", "Read", "Allowed paths", "Forbidden", "Validation", "Result", "Return schema")

class TaskDocumentError(ValueError):
    def __init__(self, code: str, path: Path, field: Optional[str] = None,
                 detail: str = "invalid Task document") -> None:
        self.code, self.path, self.field = code, Path(path), field
        super().__init__("{} {}{}: {}".format(
            code, self.path, ":" + field if field else "", detail))

@dataclass(frozen=True)
class TaskDefinition:
    metadata: Dict[str, Any]
    prompt: str
    path: Path
    task_hash: str
    prompt_hash: str

def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result

def _bad(path: Path, field: Optional[str], detail: str) -> None:
    raise TaskDocumentError("TASK_DOCUMENT_INVALID", path, field, detail)

def _scan_task_content(value: Any, path: Path, field: str) -> None:
    try:
        _scan(value)
    except ValueError as exc:
        raise TaskDocumentError(
            "TASK_SENSITIVE_CONTENT", path, field, "sensitive content is forbidden"
        ) from exc

def _string(meta: dict, key: str, path: Path, nonempty: bool = True) -> str:
    value = meta.get(key)
    if not isinstance(value, str) or (nonempty and not value.strip()):
        _bad(path, key, "expected non-empty string")
    return value

def _strings(meta: dict, key: str, path: Path, unique: bool = False) -> list:
    value = meta.get(key)
    invalid = not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value)
    if invalid or (unique and len(value) != len(set(value))):
        _bad(path, key, "invalid or duplicate string array")
    return value

def _repo_path(value: str, path: Path, field: str) -> str:
    parts = value.split("/") if isinstance(value, str) else []
    windows = PureWindowsPath(value) if isinstance(value, str) else PureWindowsPath()
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value or
            PurePosixPath(value).is_absolute() or windows.is_absolute() or windows.drive or
            any(part in ("", ".", "..") or any(c in part for c in '*?[]:"<>|') for part in parts)):
        _bad(path, field, "expected safe repository-relative POSIX path")
    return value


def _prompt_blocks(prompt: str, path: Path) -> list:
    pattern = r"(?ms)^ {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n(.*?)^ {0,3}(`{3,}|~{3,})[ \t]*$"
    matches = list(re.finditer(pattern, prompt))
    fences = re.findall(r"(?m)^ {0,3}(?:`{3,}|~{3,})[^\r\n]*$", prompt)
    if not fences:
        return [prompt]
    if len(fences) != 2 * len(matches):
        _bad(path, "prompt", "unclosed fenced block")
    blocks, end = [], 0
    for match in matches:
        if (match.group(1)[0] != match.group(4)[0] or
                len(match.group(4)) < len(match.group(1))):
            _bad(path, "prompt", "fenced block markers do not match")
        if prompt[end:match.start()].strip():
            _bad(path, "prompt", "text outside fenced blocks is forbidden")
        if match.group(2).strip() not in {"text", "prompt"}:
            _bad(path, "prompt", "fenced blocks must use text or prompt language")
        blocks.append(match.group(3))
        end = match.end()
    if prompt[end:].strip():
        _bad(path, "prompt", "text outside fenced blocks is forbidden")
    return blocks


def _prompt_sections(block: str, path: Path) -> dict:
    lines = block.splitlines()
    found = [(i, label) for i, line in enumerate(lines) for label in PROMPT_LABELS
             if line.startswith(label + ":")]
    if any(not lines[i].startswith(label + ": ") for i, label in found):
        _bad(path, "prompt", "label spacing is invalid")
    labels = [(i, label, lines[i][len(label) + 2:]) for i, label in found]
    if [label for _, label, _ in labels] != list(PROMPT_LABELS):
        _bad(path, "prompt", "labels are missing, duplicated, or out of order")
    if any(not first.strip() for _, _, first in labels):
        _bad(path, "prompt", "label values must be on the label line")
    sections = {}
    for n, (start, label, first) in enumerate(labels):
        end = labels[n + 1][0] if n + 1 < len(labels) else len(lines)
        content = "\n".join([first] + lines[start + 1:end]).strip()
        sections[label] = (first, content)
    return sections


def _prompt_list(value: str, path: Path, field: str) -> list:
    try:
        result = json.loads(value)
    except ValueError as exc:
        _bad(path, field, "expected JSON string array: " + str(exc))
    if not isinstance(result, list) or any(not isinstance(x, str) or not x.strip() for x in result):
        _bad(path, field, "expected non-empty strings in JSON array")
    return result


def _check_prompt_variables(prompt: str, path: Path) -> None:
    tokens = re.findall(r"\{\{([^{}]*)\}\}", prompt)
    remainder = re.sub(r"\{\{[^{}]*\}\}", "", prompt)
    if any(token not in VARS for token in tokens) or "{{" in remainder or "}}" in remainder:
        _bad(path, "prompt", "unknown or malformed template variable")


def _check_prompt(prompt: str, meta: dict, path: Path) -> None:
    _check_prompt_variables(prompt, path)
    for block in _prompt_blocks(prompt, path):
        sections = _prompt_sections(block, path)
        first = {label: value[0] for label, value in sections.items()}
        if first["Role"].strip() != meta["agent_role"]:
            _bad(path, "prompt.Role", "Role must match agent_role")
        if first["Read"] != "none":
            read_paths = _prompt_list(first["Read"], path, "prompt.Read")
            if not read_paths:
                _bad(path, "prompt.Read", "use none or list read paths")
            for value in read_paths:
                _repo_path(value, path, "prompt.Read")
        if _prompt_list(first["Allowed paths"], path, "prompt.Allowed paths") != meta["allowed_paths"]:
            _bad(path, "prompt.Allowed paths", "must match metadata.allowed_paths")
        validation = first["Validation"]
        matches = (validation == "none" if not meta["validation_commands"] else
                   _prompt_list(validation, path, "prompt.Validation") == meta["validation_commands"])
        if not matches:
            _bad(path, "prompt.Validation", "must match metadata.validation_commands")
        if "{{RESULT_PATH}}" not in sections["Result"][1]:
            _bad(path, "prompt.Result", "must include {{RESULT_PATH}}")
        if first["Return schema"] != "sdd-run-result/v1":
            _bad(path, "prompt.Return schema", "unsupported return schema")
        forbidden = sections["Forbidden"][1].strip()
        if not forbidden or forbidden.lower() == "none" or forbidden in {"无", "空"}:
            _bad(path, "prompt.Forbidden", "must name at least one forbidden action")


def _has_unquoted_shell_syntax(command: str) -> bool:
    blocked = ";&|<>$`*?[]{}"
    quote, escaped, word_start = None, False, True
    for char in command:
        if escaped:
            escaped, word_start = False, False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote, word_start = char, False
        elif char.isspace():
            word_start = True
        elif char in blocked or (char == "~" and word_start):
            return True
        else:
            word_start = False
    return False

def parse_task(path: Path) -> TaskDefinition:
    path = Path(path)
    try:
        return parse_task_text(read_text(path), path)
    except TaskDocumentError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise TaskDocumentError("TASK_DOCUMENT_INVALID", path, None, str(exc)) from exc

def parse_task_text(text: str, path: Path) -> TaskDefinition:
    lines = text.splitlines(keepends=True)
    plain = [line.rstrip("\r\n") for line in lines]
    positions = [[i for i, line in enumerate(plain) if line == marker] for marker in META + PROMPT]
    if any(len(found) != 1 for found in positions):
        _bad(path, None, "each metadata and prompt marker must occur exactly once")
    mb, me, pb, pe = (found[0] for found in positions)
    if mb >= me or pb >= pe or not (me < pb or pe < mb):
        _bad(path, None, "markers are incomplete or overlapping")
    try:
        raw = "".join(lines[mb + 1:me])
        meta = json.loads(raw, object_pairs_hook=_pairs)
    except (ValueError, json.JSONDecodeError) as exc:
        _bad(path, "metadata", "invalid JSON: " + str(exc))
    if not isinstance(meta, dict):
        _bad(path, "metadata", "expected JSON object")
    if type(meta.get("schema_version")) is not int or meta["schema_version"] != 1:
        raise TaskDocumentError(
            "unsupported_schema_version", path, "schema_version",
            "expected integer schema version 1",
        )
    _scan_task_content(meta, path, "metadata")
    unknown, missing = set(meta) - FIELDS, REQUIRED - set(meta)
    if unknown or missing:
        _bad(path, sorted(unknown or missing)[0], "unknown field" if unknown else "required field missing")

    ints = {"priority": meta.get("priority", 100), "max_attempts": meta.get("max_attempts", 3),
            "prompt_version": meta.get("prompt_version")}
    for key, value in ints.items():
        if (type(value) is not int or
                (key in {"max_attempts", "prompt_version"} and value < 1)):
            _bad(path, key, "invalid integer value")
    if _string(meta, "status", path) not in {"pending", "blocked", "completed", "cancelled"}:
        _bad(path, "status", "invalid status")
    if "migration_state" in meta and _string(meta, "migration_state", path) not in {"unverified", "verified"}:
        _bad(path, "migration_state", "invalid migration state")
    task_id, spec_id = _string(meta, "task_id", path), _string(meta, "spec_id", path)
    if not re.fullmatch(r"spec-(\d{3})-task-\d{2}", task_id) or spec_id != task_id[5:8]:
        _bad(path, "task_id", "task_id and spec_id must match v1 format")
    _string(meta, "title", path)
    _string(meta, "agent_role", path)
    if meta.get("return_schema") != "sdd-run-result/v1":
        _bad(path, "return_schema", "unsupported schema")

    stamp = _string(meta, "created_at", path)
    try:
        parsed = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
    except ValueError as exc:
        _bad(path, "created_at", "invalid ISO 8601 time: " + str(exc))
    if parsed.utcoffset() is None:
        _bad(path, "created_at", "timezone required")
    deps = _strings(meta, "depends_on", path, True)
    if any(not re.fullmatch(r"spec-\d{3}-task-\d{2}", x) for x in deps):
        _bad(path, "depends_on", "invalid Task ID")
    gates = _strings(meta, "required_gates", path, True)
    gate_pattern = r"spec-" + re.escape(spec_id) + r"\.[a-z0-9]+(?:-[a-z0-9]+)*"
    if any(not re.fullmatch(gate_pattern, gate) for gate in gates):
        _bad(path, "required_gates", "invalid or cross-spec gate ID")
    _strings(meta, "required_capabilities", path, True)
    allowed = [_repo_path(x, path, "allowed_paths") for x in _strings(meta, "allowed_paths", path, True)]
    if not allowed:
        _bad(path, "allowed_paths", "at least one path is required")
    artifacts = [_repo_path(x, path, "expected_artifacts") for x in _strings(meta, "expected_artifacts", path, True)]
    if any(not any(a == root or a.startswith(root.rstrip("/") + "/") for root in allowed) for a in artifacts):
        _bad(path, "expected_artifacts", "artifact is outside allowed_paths")
    wt = meta.get("worktree")
    if not isinstance(wt, dict) or set(wt) != {"path", "branch", "mode", "base_rule"}:
        _bad(path, "worktree", "expected exact v1 worktree object")
    slug = r"[a-z0-9]+(?:-[a-z0-9]+)*"
    if (wt["path"] != ".worktrees/spec-" + spec_id or wt["mode"] != "per_spec" or
            wt["base_rule"] != "explicit_commit" or
            not isinstance(wt["branch"], str) or not re.fullmatch(r"feature/spec-" + spec_id + r"-" + slug, wt["branch"])):
        _bad(path, "worktree", "worktree does not match v1 spec mapping")
    commands = _strings(meta, "validation_commands", path)
    for command in commands:
        try:
            argv = shlex.split(command, posix=True)
        except ValueError:
            _bad(path, "validation_commands", "invalid shlex command")
        if not argv or _has_unquoted_shell_syntax(command):
            _bad(path, "validation_commands", "shell syntax or empty command is forbidden")

    prompt = "".join(lines[pb + 1:pe])
    _scan_task_content(prompt, path, "prompt")
    _check_prompt(prompt, meta, path)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    canonical = {key: value for key, value in meta.items() if key not in {"status", "migration_state"}}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    task_hash = hashlib.sha256((payload + "\n" + prompt_hash).encode("utf-8")).hexdigest()
    return TaskDefinition(meta, prompt, path, task_hash, prompt_hash)
