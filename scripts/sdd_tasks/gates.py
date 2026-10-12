import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Set

from .atomic import _open_directory, contained
from .documents import TaskDefinition, parse_task


class GateEvidenceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__("{}: {}".format(code, detail))

def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result

def _constant(value: str) -> None:
    raise ValueError("invalid JSON constant: " + value)

def _read_bytes(root: Path, relative: str) -> bytes:
    target = contained(root, relative)
    parent_fd = file_fd = -1
    try:
        parent_fd = _open_directory(target.parent)
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        file_fd = os.open(target.name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise OSError("gate evidence is not a regular file")
        with os.fdopen(file_fd, "rb") as source:
            file_fd = -1
            return source.read()
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if parent_fd >= 0:
            os.close(parent_fd)

def _registered(root: Path) -> list:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateEvidenceError("GIT_DISCOVERY_FAILED", str(exc)) from exc
    paths = [Path(line[9:]).resolve() for line in result.stdout.splitlines()
             if line.startswith("worktree ")]
    if not paths or root not in paths:
        raise GateEvidenceError("WORKTREE_LIST_INVALID", str(root))
    return paths

def _canonical_task(root: Path, task: TaskDefinition):
    task_id = task.metadata["task_id"]
    number = task_id.rsplit("-", 1)[1]
    try:
        contained(root, "docs/sdd/plans/" + task.metadata["spec_id"])
    except ValueError as exc:
        raise GateEvidenceError("CANONICAL_TASK_UNSAFE", str(exc)) from exc
    candidates = sorted((root / "docs/sdd/plans" / task.metadata["spec_id"])
                       .glob("task-{}-*.md".format(number)))
    if not candidates:
        raise GateEvidenceError("CANONICAL_TASK_MISSING", task_id)
    if len(candidates) != 1:
        raise GateEvidenceError("CANONICAL_TASK_AMBIGUOUS", task_id)
    source = candidates[0]
    try:
        contained(root, source.relative_to(root).as_posix())
        current = parse_task(source)
    except (ValueError, OSError) as exc:
        raise GateEvidenceError("CANONICAL_TASK_INVALID", str(exc)) from exc
    if current.task_hash != task.task_hash or current.prompt_hash != task.prompt_hash:
        raise GateEvidenceError("CANONICAL_TASK_HASH_MISMATCH", task_id)
    return current

def load_satisfied_gates(task: TaskDefinition, repo_root: Path) -> Set[str]:
    root = Path(repo_root).resolve()
    roots = _registered(root)
    main = roots[0]
    try:
        expected = contained(main, task.metadata["worktree"]["path"]).resolve()
    except (KeyError, TypeError, ValueError) as exc:
        raise GateEvidenceError("CANONICAL_WORKTREE_INVALID", str(exc)) from exc
    if expected not in roots:
        raise GateEvidenceError("CANONICAL_WORKTREE_UNREGISTERED", str(expected))
    if not expected.is_dir():
        raise GateEvidenceError("CANONICAL_WORKTREE_MISSING", str(expected))
    canonical = _canonical_task(expected, task)
    registry_path = "docs/sdd/gate-evidence.json"
    try:
        raw = _read_bytes(expected, registry_path)
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as exc:
        raise GateEvidenceError("gate_evidence_invalid", str(exc)) from exc
    try:
        registry = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise GateEvidenceError("gate_evidence_invalid", str(exc)) from exc
    if (not isinstance(registry, dict) or set(registry) != {"schema", "gates"} or
            registry.get("schema") != "sdd-gates/v1" or
            not isinstance(registry.get("gates"), list)):
        raise GateEvidenceError("gate_evidence_invalid", "invalid registry schema")
    return _matching_gates(registry["gates"], canonical, expected)

def _matching_gates(entries: list, task: TaskDefinition, root: Path) -> Set[str]:
    spec = task.metadata["spec_id"]
    required = set(task.metadata["required_gates"])
    seen, satisfied = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"gate_id", "status", "evidence"}:
            raise GateEvidenceError("gate_evidence_invalid", "invalid gate entry")
        gate_id, status, evidence = entry["gate_id"], entry["status"], entry["evidence"]
        if (not isinstance(gate_id, str) or
                not re.fullmatch(r"spec-\d{3}\.[a-z0-9]+(?:-[a-z0-9]+)*", gate_id) or
                not gate_id.startswith("spec-{}.".format(spec)) or gate_id in seen):
            raise GateEvidenceError("gate_evidence_invalid", "invalid or duplicate gate_id")
        seen.add(gate_id)
        if status not in ("passed", "pending", "failed"):
            raise GateEvidenceError("gate_evidence_invalid", "invalid gate status")
        if not isinstance(evidence, dict) or set(evidence) != {"path", "sha256"}:
            raise GateEvidenceError("gate_evidence_invalid", "invalid evidence object")
        try:
            path = contained(root, evidence["path"]).relative_to(root).as_posix()
        except (ValueError, TypeError) as exc:
            raise GateEvidenceError("gate_evidence_invalid", str(exc)) from exc
        digest = evidence["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GateEvidenceError("gate_evidence_invalid", "invalid evidence sha256")
        if gate_id not in required or status != "passed":
            continue
        try:
            payload = _read_bytes(root, path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise GateEvidenceError("gate_evidence_invalid", str(exc)) from exc
        if hashlib.sha256(payload).hexdigest() == digest:
            satisfied.add(gate_id)
    return satisfied
