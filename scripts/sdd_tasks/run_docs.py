"""Build and durably write canonical Task run summaries."""

import json
import os
import uuid
from pathlib import Path

from .atomic import _open_directory, atomic_write, contained
from .catalog import discover_worktrees
from .claims import Claim
from .documents import TaskDefinition
from .locks import repository_paths
from .owners import OwnerIdentity
from .result_schema import _scan
from .summaries import _MB, _ME, _RB, _RE, SummaryError, _record


def _summary_relative(task: TaskDefinition, claim: Claim) -> str:
    task_id = task.metadata["task_id"]
    run_id = str(uuid.UUID(claim.run_id))
    if run_id != claim.run_id:
        raise ValueError("run_id must be a canonical UUID")
    return "docs/sdd/runs/{}/task-{}/{}.md".format(task.metadata["spec_id"], task_id[-2:], run_id)


def build_summary(task: TaskDefinition, claim: Claim, result: dict) -> str:
    """Render validated result and metadata blocks without filesystem writes."""
    relative = Path("docs/sdd/runs")
    try:
        if (not isinstance(task, TaskDefinition) or not isinstance(claim, Claim) or
                not isinstance(claim.task, TaskDefinition) or not isinstance(result, dict)):
            raise ValueError("expected TaskDefinition, Claim, and result object")
        relative = Path(_summary_relative(task, claim))
        metadata = task.metadata
        if (claim.state not in {"claimed", "running"} or type(claim.attempt) is not int or
                claim.attempt < 1 or not isinstance(claim.ide, str) or not claim.ide.strip() or
                claim.task.metadata != metadata or claim.task.prompt != task.prompt or
                claim.task.task_hash != task.task_hash or claim.task.prompt_hash != task.prompt_hash or
                claim.task_hash != task.task_hash or claim.prompt_hash != task.prompt_hash or
                task.metadata.get("task_id") != claim.task.metadata.get("task_id") or
                claim.branch != metadata["worktree"]["branch"] or
                not isinstance(claim.owner, OwnerIdentity) or
                not isinstance(claim.owner.token, str) or not claim.owner.token or
                not isinstance(claim.owner.executor_id, str) or not claim.owner.executor_id.strip()):
            raise ValueError("Task and Claim bindings are inconsistent")
        meta = {
            "schema": "sdd-run-meta/v1", "run_id": claim.run_id,
            "task_id": metadata["task_id"], "task_hash": task.task_hash,
            "prompt_hash": task.prompt_hash, "attempt": claim.attempt, "ide": claim.ide,
            "executor_id": claim.owner.executor_id, "agent_role": metadata["agent_role"],
            "model": result.get("model"), "worktree": metadata["worktree"]["path"],
            "branch": metadata["worktree"]["branch"], "base_commit": claim.base_commit,
            "claimed_at": claim.claimed_at,
        }
        _record(result, meta, task, relative.as_posix(), relative)
        content = "\n".join((
            _RB, json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False),
            _RE, "", _MB, json.dumps(meta, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False),
            _ME, "",
        ))
        _scan(content)
        if claim.owner.token and claim.owner.token in content:
            raise ValueError("private owner material is forbidden")
        content.encode("utf-8")
        return content
    except SummaryError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise SummaryError("SUMMARY_BUILD_INVALID", relative, "Task, Claim, or result is invalid") from exc


def write_summary(task: TaskDefinition, claim: Claim, result: dict, repo_root: Path) -> Path:
    """Atomically write the derived summary path after a journal authorizes the write."""
    content = build_summary(task, claim, result)
    relative = Path(_summary_relative(task, claim))
    try:
        main, _ = repository_paths(Path(repo_root))
        supplied = Path(repo_root).resolve(strict=True)
        worktree = contained(main, task.metadata["worktree"]["path"]).resolve(strict=True)
        roots = discover_worktrees(main)
        if (main not in roots or worktree not in roots or supplied not in {main, worktree} or
                Path(claim.worktree_path).resolve(strict=True) != worktree):
            raise ValueError("summary root is not the registered Task authority")
        target = contained(worktree, relative.as_posix())
        parent = _open_directory(target.parent)
        os.close(parent)
        atomic_write(target, content)
        return target
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, SummaryError):
            raise
        raise SummaryError("SUMMARY_WRITE_FAILED", relative, "canonical summary write failed") from exc
