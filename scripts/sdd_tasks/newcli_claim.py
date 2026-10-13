"""Orchestrate one safe CLI claim from the shared ledger."""

import re
import stat
import subprocess
import warnings
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from .atomic import contained
from .catalog import CatalogError, _scan, discover_worktrees
from .catalog_status import status
from .claims import ClaimError
from .documents import TaskDocumentError, parse_task_text
from .eligibility import database_blockers, rank_candidates
from .gates import load_satisfied_gates
from .locks import maintenance_lock, repository_paths, runtime_root
from .owners import current_owner
from .prompts import PromptError, render_prompt
from .recovery_snapshots import load_recovery_snapshot
from .selection import claim_next
from .spec_status import is_claimable, load_spec_status
from .store import connect
from .workspace import WorkspaceError, compare_snapshot, prepare_worktree


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatalogError("GIT_DISCOVERY_FAILED", "Git identity unavailable") from exc


def _database(root: Path) -> Path:
    path = contained(root, ".sdd/runtime/task-ledger.sqlite3")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise CatalogError("CATALOG_NOT_REBUILT", "run rebuild first") from exc
    except (OSError, ValueError) as exc:
        raise CatalogError("DATABASE_PATH_UNSAFE", "ledger path is unsafe") from exc
    if not stat.S_ISREG(info.st_mode):
        raise CatalogError("DATABASE_PATH_UNSAFE", "ledger must be a regular file")
    return path


def _source(roots: tuple, task) -> tuple:
    path = Path(task.path)
    for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
        try:
            return root, path.relative_to(root).as_posix()
        except ValueError:
            continue
    raise ClaimError("CLAIM_TASK_SOURCE_INVALID", task.metadata["task_id"])


def _matches_base(main: Path, base: str, relative: str, task) -> None:
    try:
        result = subprocess.run(["git", "-C", str(main), "show", base + ":" + relative],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        document = parse_task_text(result.stdout.decode("utf-8"), Path(relative))
    except (OSError, UnicodeError, subprocess.SubprocessError, TaskDocumentError) as exc:
        raise ClaimError("CANONICAL_TASK_MISSING", task.metadata["task_id"]) from exc
    if (document.metadata != task.metadata or document.task_hash != task.task_hash or
            document.prompt_hash != task.prompt_hash):
        raise ClaimError("CLAIM_TASK_HASH_STALE", task.metadata["task_id"])


def _payload(claim, prompt_path: str, rendered_prompt_hash: str) -> dict:
    return {
        "run_id": claim.run_id, "task_id": claim.task.metadata["task_id"],
        "attempt": claim.attempt, "worktree": claim.task.metadata["worktree"]["path"],
        "branch": claim.branch, "base_commit": claim.base_commit,
        "task_hash": claim.task_hash, "prompt_hash": claim.prompt_hash,
        "prompt_path": prompt_path, "rendered_prompt_hash": rendered_prompt_hash,
        "recovery_of": claim.recovery_of,
    }


def claim_from_cli(repo_root: Path, ide: str, executor: str, owner_pid: int,
                   base_commit: Optional[str] = None) -> Tuple[Optional[dict], Optional[dict]]:
    main, _ = repository_paths(repo_root)
    with maintenance_lock(main):
        database = _database(main)
        with closing(connect(database)) as conn:
            roots = discover_worktrees(main)
            if not roots or roots[0] != main:
                raise CatalogError("WORKTREE_LIST_INVALID", "main worktree is not canonical")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                entries, _ = _scan(roots)
            tasks = [task for task, _ in entries]
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            abandoned = {row[0] for row in conn.execute(
                "SELECT task_id FROM runs r WHERE state='abandoned' AND attempt=("
                "SELECT MAX(attempt) FROM runs WHERE task_id=r.task_id)")}
            for task in rank_candidates(tasks, abandoned):
                task_id = task.metadata["task_id"]
                if task.metadata["status"] != "pending":
                    continue
                row = conn.execute("SELECT task_hash,prompt_hash FROM tasks WHERE task_id=?",
                                   (task_id,)).fetchone()
                if row is None:
                    continue
                if (row[0], row[1]) != (task.task_hash, task.prompt_hash):
                    raise ClaimError("CLAIM_CATALOG_HASH_STALE", task_id)
                blockers = database_blockers(conn, task, set(), now)
                if any(not item.startswith("gate_unsatisfied:") for item in blockers):
                    continue
                canonical = contained(main, task.metadata["worktree"]["path"]).resolve()
                if canonical in roots and canonical.is_dir():
                    if not is_claimable(load_spec_status(task, main)):
                        continue
                    if task.metadata["required_gates"]:
                        prechecked_gates = load_satisfied_gates(task, main)
                        if any(gate not in prechecked_gates
                               for gate in task.metadata["required_gates"]):
                            continue
                baseline, snapshot = None, None
                if task_id in abandoned:
                    previous = conn.execute(
                        "SELECT run_id FROM runs WHERE task_id=? AND state='abandoned' "
                        "ORDER BY attempt DESC,run_id DESC LIMIT 1", (task_id,),
                    ).fetchone()
                    baseline = load_recovery_snapshot(conn, previous[0], task, main)
                    if base_commit is not None and base_commit != baseline.head:
                        raise ClaimError("CLAIM_BASE_COMMIT_INVALID", task_id)
                    base = baseline.head
                else:
                    base_root = canonical if canonical in roots else main
                    base = base_commit or _git(base_root, "rev-parse", "HEAD")
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
                    raise ClaimError("CLAIM_BASE_COMMIT_INVALID", task_id)
                _, relative = _source(roots, task)
                _matches_base(main, base, relative, task)
                owner = current_owner(executor, pid=owner_pid)
                try:
                    snapshot = prepare_worktree(main, task, base, recovery_snapshot=baseline)
                except WorkspaceError as exc:
                    if exc.code == "workspace_recovery_conflict":
                        continue
                    raise
                if baseline is not None:
                    decision = compare_snapshot(baseline, snapshot)
                    if not decision.recoverable or decision.kind not in {"unchanged", "partial"}:
                        continue
                    if decision.kind == "partial":
                        snapshot = baseline
                gates = load_satisfied_gates(task, main)
                claim = claim_next(conn, [task], gates, workspace_snapshots={task_id: snapshot},
                                   ide=ide, owner=owner, now=now)
                if claim is not None:
                    try:
                        rendered = render_prompt(claim.task, claim, snapshot, runtime_root(main))
                    except PromptError as exc:
                        raise CatalogError("CLAIM_PROMPT_RENDER_FAILED", "prompt persistence failed") from exc
                    prompt_path = rendered.path.relative_to(main).as_posix()
                    return _payload(claim, prompt_path, rendered.rendered_hash), None
            return None, status(conn)
