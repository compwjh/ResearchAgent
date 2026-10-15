"""Execution-backed validation for an active claimed Task run."""

import hashlib
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .active_failed_recovery import compare_active_failed_workspace, load_active_failed_source
from .atomic import _open_directory, atomic_write, contained
from .catalog import discover_worktrees
from .catalog_status import _live_gate_task, _metadata
from .claims import Claim
from .documents import TaskDefinition
from .failed_workspace import VerifiedFailedWorkspace
from .gates import load_satisfied_gates
from .internalvalidation_process import ValidationProcessError, run_one_validation
from .leases import _main_root
from .locks import repository_paths
from .owners import OwnerIdentity
from .recovery_snapshots import _event, load_recovery_snapshot
from .run_owner import resolve_run_owner
from .spec_status import is_claimable, load_spec_status
from .store import connect
from .workspace import WorkspaceSnapshot, capture_snapshot, compare_snapshot, snapshot_payload


class ValidationRunnerError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _ValidationContext:
    conn: sqlite3.Connection
    main: Path
    common: Path
    worktree: Path
    run: sqlite3.Row
    before: WorkspaceSnapshot
    failed_source: Optional[VerifiedFailedWorkspace] = None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _snapshot_sha256(snapshot: WorkspaceSnapshot, source_run_id: Optional[str]) -> str:
    payload = _canonical_json(snapshot_payload(snapshot, source_run_id))
    return hashlib.sha256(payload).hexdigest()


def _ignored(main: Path, relative: str) -> bool:
    try:
        result = subprocess.run(["git", "check-ignore", "--quiet", "--", relative],
                                cwd=str(main), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except OSError:
        return False


def _private_validation_paths(main: Path, run_id: str, command_count: int):
    base = ".sdd/runtime/runs/{}/validation".format(run_id)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    fd = -1
    try:
        fd = _open_directory(main / ".sdd/runtime")
        runtime = os.fstat(fd)
        if not stat.S_ISDIR(runtime.st_mode) or runtime.st_uid != os.geteuid() or stat.S_IMODE(runtime.st_mode) != 0o700:
            raise ValidationRunnerError("VALIDATION_RUNTIME_UNSAFE")
        receipt_rel = base + "/receipt.json"
        if not _ignored(main, ".sdd/runtime") or not _ignored(main, receipt_rel):
            raise ValidationRunnerError("VALIDATION_RUNTIME_NOT_IGNORED")
        for name in ("runs", run_id, "validation"):
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                pass
            child = os.open(name, flags, dir_fd=fd)
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o700):
                os.close(child)
                raise ValidationRunnerError("VALIDATION_RUNTIME_UNSAFE")
            os.close(fd)
            fd = child
        for _ in range(32):
            invocation = str(uuid.uuid4())
            invocation_rel = base + "/" + invocation
            logs = tuple((invocation_rel + "/command-{}.stdout".format(n),
                          invocation_rel + "/command-{}.stderr".format(n))
                         for n in range(1, command_count + 1))
            if (not _ignored(main, invocation_rel) or
                    any(not _ignored(main, path) for pair in logs for path in pair)):
                raise ValidationRunnerError("VALIDATION_RUNTIME_NOT_IGNORED")
            try:
                os.mkdir(invocation, 0o700, dir_fd=fd)
            except FileExistsError:
                continue
            os.fsync(fd)
            child = os.open(invocation, flags, dir_fd=fd)
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o700):
                os.close(child)
                raise ValidationRunnerError("VALIDATION_RUNTIME_UNSAFE")
            os.close(child)
            return (main / receipt_rel, main / invocation_rel,
                    tuple((main / left, main / right) for left, right in logs))
        raise ValidationRunnerError("VALIDATION_RUNTIME_UNSAFE")
    except ValidationRunnerError:
        raise
    except OSError as exc:
        raise ValidationRunnerError("VALIDATION_RUNTIME_UNSAFE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _active_context(task: TaskDefinition, claim: Claim, repo_root: Path) -> _ValidationContext:
    """Re-resolve the active claim, canonical Task, owner, and persisted baseline."""
    conn = None
    try:
        if (not isinstance(task, TaskDefinition) or not isinstance(claim, Claim) or
                not isinstance(claim.task, TaskDefinition) or
                not isinstance(claim.owner, OwnerIdentity) or claim.state not in {"claimed", "running"} or
                not isinstance(claim.run_id, str) or not re.fullmatch(
                    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", claim.run_id)):
            raise ValidationRunnerError("VALIDATION_CLAIM_INVALID")
        main, common = repository_paths(Path(repo_root))
        roots = discover_worktrees(main)
        supplied = Path(repo_root).resolve(strict=True)
        if not roots or roots[0] != main or supplied not in roots:
            raise ValidationRunnerError("VALIDATION_REPOSITORY_INVALID")
        database = contained(main, ".sdd/runtime/task-ledger.sqlite3")
        try:
            database_info = database.lstat()
        except FileNotFoundError as exc:
            raise ValidationRunnerError("VALIDATION_DATABASE_MISSING") from exc
        if not stat.S_ISREG(database_info.st_mode):
            raise ValidationRunnerError("VALIDATION_DATABASE_UNSAFE")
        conn = connect(database)
        if _main_root(conn) != main:
            raise ValidationRunnerError("VALIDATION_DATABASE_MISMATCH")
        row = conn.execute(
            "SELECT task_id,status,task_hash,prompt_hash,definition_json FROM tasks WHERE task_id=?",
            (task.metadata.get("task_id"),),
        ).fetchone()
        if row is None:
            raise ValidationRunnerError("VALIDATION_TASK_MISSING")
        metadata = _metadata(row)
        canonical_task = _live_gate_task(row, metadata, main, roots)
        if (canonical_task.metadata != task.metadata or canonical_task.prompt != task.prompt or
                canonical_task.task_hash != task.task_hash or
                canonical_task.prompt_hash != task.prompt_hash or
                claim.task.metadata != task.metadata or claim.task.task_hash != task.task_hash or
                claim.task.prompt_hash != task.prompt_hash):
            raise ValidationRunnerError("VALIDATION_TASK_MISMATCH")
        if not is_claimable(load_spec_status(canonical_task, main)):
            raise ValidationRunnerError("VALIDATION_SPEC_NOT_CLAIMABLE")
        satisfied = load_satisfied_gates(canonical_task, main)
        if not set(canonical_task.metadata["required_gates"]).issubset(satisfied):
            raise ValidationRunnerError("VALIDATION_GATES_UNSATISFIED")
        owner = resolve_run_owner(conn, claim.run_id, claim.owner.executor_id, claim.owner.pid)
        if owner != claim.owner:
            raise ValidationRunnerError("VALIDATION_OWNER_MISMATCH")
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()
        if run is None or run["state"] not in {"claimed", "running"} or run["ended_at"] is not None:
            raise ValidationRunnerError("VALIDATION_RUN_NOT_ACTIVE")
        relative = task.metadata["worktree"]["path"]
        worktree = contained(main, relative).resolve(strict=True)
        expected = (task.metadata["task_id"], claim.attempt, claim.base_commit,
                    task.task_hash, task.prompt_hash, relative, claim.branch)
        actual = (run["task_id"], run["attempt"], run["base_commit"], run["task_hash"],
                  run["prompt_hash"], run["worktree"], run["branch"])
        if (actual != expected or claim.worktree_path.resolve(strict=True) != worktree or
                claim.branch != task.metadata["worktree"]["branch"] or worktree not in roots):
            raise ValidationRunnerError("VALIDATION_BINDING_MISMATCH")
        snapshot_event = _event(conn, claim.run_id, "workspace_snapshot", True)
        recovery_of = (snapshot_event.get("source_run_id")
                      if isinstance(snapshot_event, dict) else None)
        source = (conn.execute("SELECT state,task_id FROM runs WHERE run_id=?",
                               (recovery_of,)).fetchone()
                  if isinstance(recovery_of, str) else None)
        failed_source = None
        if (source is not None and source["state"] == "failed" and
                source["task_id"] == run["task_id"]):
            failed_source = load_active_failed_source(conn, claim.run_id, canonical_task, main)
            if (claim.failed_source is not None and claim.failed_source != failed_source):
                raise ValidationRunnerError("VALIDATION_FAILED_SOURCE_MISMATCH")
            before = failed_source.baseline
        else:
            if claim.failed_source is not None:
                raise ValidationRunnerError("VALIDATION_FAILED_SOURCE_MISMATCH")
            before = load_recovery_snapshot(conn, claim.run_id, canonical_task, main)
        if (before.head != claim.base_commit or before.worktree_path != worktree or
                before.common_dir != common):
            raise ValidationRunnerError("VALIDATION_BASELINE_MISMATCH")
        return _ValidationContext(conn, main, common, worktree, run, before, failed_source)
    except ValidationRunnerError:
        if conn is not None:
            conn.close()
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        if conn is not None:
            conn.close()
        raise ValidationRunnerError(getattr(exc, "code", "VALIDATION_CONTEXT_INVALID")) from exc


def run_validations(task: TaskDefinition, claim: Claim, repo_root: Path, *,
                    timeout_seconds: int = 300) -> Tuple[Tuple[Dict[str, Any], ...], Dict[str, Any]]:
    """Run canonical validation commands and persist a private, execution-backed receipt."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValidationRunnerError("VALIDATION_TIMEOUT_INVALID")
    context = _active_context(task, claim, repo_root)
    try:
        raw_commands = task.metadata.get("validation_commands")
        if not isinstance(raw_commands, list):
            raise ValidationRunnerError("VALIDATION_COMMANDS_INVALID")
        parsed = []
        try:
            for raw in raw_commands:
                if not isinstance(raw, str):
                    raise ValueError("command type")
                argv = shlex.split(raw, posix=True)
                if not argv or any(not item or "\x00" in item for item in argv):
                    raise ValueError("empty argv")
                parsed.append(argv)
        except ValueError as exc:
            raise ValidationRunnerError("VALIDATION_COMMANDS_INVALID") from exc

        receipt_path, _, log_pairs = _private_validation_paths(
            context.main, claim.run_id, len(parsed))
        started_at, started = _utc_now(), time.monotonic()
        commands, command_logs = [], []
        for sequence, argv in enumerate(parsed, 1):
            stdout_path, stderr_path = log_pairs[sequence - 1]
            try:
                record = run_one_validation(argv, context.worktree, stdout_path, stderr_path,
                                            timeout_seconds)
            except ValidationProcessError as exc:
                raise ValidationRunnerError(exc.code) from exc
            commands.append({"argv": argv, "status": record.status, "exit_code": record.exit_code,
                             "duration_ms": record.duration_ms, "summary": record.summary})
            command_logs.append({
                "sequence": sequence,
                "stdout_path": stdout_path.relative_to(context.main).as_posix(),
                "stdout_sha256": record.stdout.sha256,
                "stdout_truncated": record.stdout.truncated,
                "stderr_path": stderr_path.relative_to(context.main).as_posix(),
                "stderr_sha256": record.stderr.sha256,
                "stderr_truncated": record.stderr.truncated,
            })

        after = capture_snapshot(context.main, task)
        scope = (compare_active_failed_workspace(context.failed_source, after, task)
                 if context.failed_source is not None else compare_snapshot(context.before, after))
        ended_at, duration_ms = _utc_now(), int((time.monotonic() - started) * 1000)
        receipt = {
            "schema": "sdd-validation-receipt/v1", "run_id": claim.run_id,
            "task_id": task.metadata["task_id"], "task_hash": task.task_hash,
            "prompt_hash": task.prompt_hash, "base_commit": claim.base_commit,
            "branch": claim.branch, "worktree": context.worktree.relative_to(context.main).as_posix(),
            "before_snapshot_sha256": _snapshot_sha256(context.before, claim.recovery_of),
            "validation_commands_sha256": hashlib.sha256(_canonical_json(raw_commands)).hexdigest(),
            "started_at": started_at, "ended_at": ended_at, "duration_ms": duration_ms,
            "commands": commands, "command_logs": command_logs,
            "after_snapshot_sha256": _snapshot_sha256(after, claim.recovery_of),
            "valid": scope.recoverable and all(
                row["status"] == "executed" and row["exit_code"] == 0 for row in commands),
        }
        receipt["receipt_sha256"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
        try:
            atomic_write(receipt_path, _canonical_json(receipt) + b"\n")
        except OSError as exc:
            raise ValidationRunnerError("VALIDATION_RECEIPT_WRITE_FAILED") from exc
        return tuple(commands), receipt
    finally:
        context.conn.close()

