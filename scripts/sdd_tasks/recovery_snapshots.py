"""Read-only verification of workspace snapshot events used for recovery."""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .atomic import contained
from .documents import TaskDefinition, _pairs, parse_task
from .lease_recovery import stored_owner
from .locks import repository_paths
from .workspace import WorkspaceError, WorkspaceSnapshot

_FIELDS = {"repo_root", "common_dir", "worktree_path", "spec_id", "task_id", "task_hash",
           "prompt_hash", "branch", "head", "status_records", "allowed_hashes", "captured_at"}
RecoverySnapshotError = WorkspaceError


def _uuid(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise RecoverySnapshotError("RECOVERY_EVENT_INVALID")
    return value

def _decode(value):
    try:
        return json.loads(value, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (TypeError, ValueError) as exc:
        raise RecoverySnapshotError("RECOVERY_EVENT_INVALID") from exc


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoverySnapshotError("RECOVERY_WORKTREE_INVALID") from exc


def _event(conn, run_id, kind, required):
    rows = conn.execute("SELECT payload_json FROM events WHERE run_id=? AND event_type=?",
                        (run_id, kind)).fetchall()
    if len(rows) != (1 if required else 0):
        raise RecoverySnapshotError("RECOVERY_EVENT_INVALID")
    return _decode(rows[0][0]) if rows else None


def _snapshot(payload, task, run, main, common, worktree):
    if (not isinstance(payload, dict) or set(payload) != {"schema", "source_run_id", "snapshot"} or
            payload["schema"] != "sdd-workspace-snapshot/v1"):
        raise RecoverySnapshotError("RECOVERY_EVENT_INVALID")
    source = payload["source_run_id"]
    if source is not None:
        source = _uuid(source)
    data, meta = payload["snapshot"], task.metadata
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_INVALID")
    expected = {"repo_root": str(main), "common_dir": str(common), "worktree_path": str(worktree),
                "spec_id": meta["spec_id"], "task_id": meta["task_id"],
                "task_hash": task.task_hash, "prompt_hash": task.prompt_hash, "branch": run["branch"]}
    if any(data.get(key) != value for key, value in expected.items()):
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_MISMATCH")
    head = run["base_commit"]
    if (not isinstance(head, str) or
            not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head) or data["head"] != head):
        raise RecoverySnapshotError("RECOVERY_BASE_MISMATCH")
    records, hashes, stamp = data["status_records"], data["allowed_hashes"], data["captured_at"]
    allowed = meta["allowed_paths"]
    if (not allowed or not isinstance(records, list) or
            any(not isinstance(item, str) for item in records) or
            not isinstance(hashes, dict) or not set(allowed).issubset(hashes) or
            any(not any(path == root or path.startswith(root + "/") for root in allowed)
                or (value is not None and
                    (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)))
                for path, value in hashes.items())):
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_INVALID")
    if records:
        raise RecoverySnapshotError("RECOVERY_BASELINE_DIRTY")
    try:
        for path in hashes:
            contained(worktree, path)
    except (OSError, ValueError) as exc:
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_INVALID") from exc
    try:
        parsed = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_INVALID") from exc
    if parsed.utcoffset() is None:
        raise RecoverySnapshotError("RECOVERY_SNAPSHOT_INVALID")
    return source, WorkspaceSnapshot(main, common, worktree, data["spec_id"], data["task_id"],
        data["task_hash"], data["prompt_hash"], data["branch"], head, tuple(records), dict(hashes), stamp)


def load_recovery_snapshot(conn, run_id: str, task: TaskDefinition, repo_root: Path) -> WorkspaceSnapshot:
    run_id = _uuid(run_id)
    try:
        main, common = repository_paths(repo_root)
        meta = task.metadata
        relative = meta["worktree"]["path"]
        worktree = contained(main, relative).resolve(strict=True)
        task_match = re.fullmatch(r"spec-(\d{3})-task-(\d{2})", meta["task_id"])
        if task_match is None or task_match.group(1) != meta["spec_id"]:
            raise RecoverySnapshotError("RECOVERY_TASK_MISMATCH")
        directory = contained(worktree, "docs/sdd/plans/" + meta["spec_id"])
        candidates = sorted(directory.glob("task-" + task_match.group(2) + "-*.md"))
        if len(candidates) != 1:
            raise RecoverySnapshotError("RECOVERY_TASK_AMBIGUOUS")
        task_file = contained(worktree, candidates[0].relative_to(worktree).as_posix())
        registered = {Path(line[9:]).resolve(strict=True) for line in
                      _git(main, "worktree", "list", "--porcelain").splitlines()
                      if line.startswith("worktree ")}
    except WorkspaceError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise RecoverySnapshotError("RECOVERY_WORKTREE_INVALID") from exc
    if worktree not in registered or not task_file.is_file():
        raise RecoverySnapshotError("RECOVERY_WORKTREE_UNREGISTERED")
    try:
        actual_task = parse_task(task_file)
    except (OSError, ValueError):
        raise RecoverySnapshotError("RECOVERY_TASK_MISMATCH") from None
    if (actual_task.metadata["task_id"] != meta["task_id"] or
            actual_task.task_hash != task.task_hash or
            actual_task.prompt_hash != task.prompt_hash):
        raise RecoverySnapshotError("RECOVERY_TASK_MISMATCH")
    if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") != meta["worktree"]["branch"]:
        raise RecoverySnapshotError("RECOVERY_BRANCH_MISMATCH")
    task_row = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?",
                            (meta["task_id"],)).fetchone()
    if task_row is None or (task_row["task_hash"], task_row["prompt_hash"]) != (
            task.task_hash, task.prompt_hash):
        raise RecoverySnapshotError("RECOVERY_TASK_MISMATCH")
    baseline, cursor, seen = None, run_id, set()
    while cursor is not None:
        if cursor in seen:
            raise RecoverySnapshotError("RECOVERY_SOURCE_CYCLE")
        seen.add(cursor)
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (cursor,)).fetchone()
        if run is None or run["state"] not in {"claimed", "running", "abandoned"}:
            raise RecoverySnapshotError("RECOVERY_RUN_INVALID")
        expected = (meta["task_id"], task.task_hash, task.prompt_hash, relative,
                    meta["worktree"]["branch"], meta["agent_role"])
        actual = (run["task_id"], run["task_hash"], run["prompt_hash"], run["worktree"],
                  run["branch"], run["agent_role"])
        if actual != expected:
            raise RecoverySnapshotError("RECOVERY_RUN_MISMATCH")
        if stored_owner(run["owner_json"]).executor_id != run["executor_id"]:
            raise RecoverySnapshotError("RECOVERY_OWNER_INVALID")
        source, snapshot = _snapshot(_event(conn, cursor, "workspace_snapshot", True),
                                    task, run, main, common, worktree)
        if baseline is not None and snapshot != baseline:
            raise RecoverySnapshotError("RECOVERY_BASELINE_MISMATCH")
        baseline = snapshot
        claim = _event(conn, cursor, "recovery_claim", source is not None)
        if source is None:
            break
        if (not isinstance(claim, dict) or set(claim) != {"schema", "recovery_of"} or
                claim["schema"] != "sdd-recovery-claim/v1" or
                _uuid(claim["recovery_of"]) != source or source == cursor):
            raise RecoverySnapshotError("RECOVERY_EVENT_INVALID")
        parent = conn.execute("SELECT state,task_id FROM runs WHERE run_id=?", (source,)).fetchone()
        if parent is None or (parent["state"], parent["task_id"]) != ("abandoned", meta["task_id"]):
            raise RecoverySnapshotError("RECOVERY_SOURCE_INVALID")
        cursor = source
    if _git(worktree, "rev-parse", "HEAD") != baseline.head:
        raise RecoverySnapshotError("RECOVERY_BASE_MISMATCH")
    return baseline
