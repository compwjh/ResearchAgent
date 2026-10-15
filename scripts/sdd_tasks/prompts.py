"""Secure Task Prompt rendering for claimed runs."""

import hashlib
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .atomic import _open_directory, atomic_write, contained
from .claim_validation import validate_candidate
from .claims import Claim
from .documents import TaskDefinition
from .gates import load_satisfied_gates
from .locks import repository_paths
from .result_schema import _scan
from .workspace import WorkspaceSnapshot


class PromptError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    path: Path
    template_hash: str
    rendered_hash: str


_VARIABLE = re.compile(r"\{\{([^{}]*)\}\}")
_ALLOWED = {"RUN_ID", "WORKTREE", "BASE_COMMIT", "RESULT_PATH", "EVENT_PATH"}
_HASH = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def _uuid(value: str) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _private_run_dir(runtime: Path, run_id: str) -> Path:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    fd = -1
    try:
        fd = _open_directory(runtime)
        root_info = os.fstat(fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid() or
                root_info.st_mode & 0o077):
            raise PromptError("PROMPT_RUN_DIR_UNSAFE")
        for name in ("runs", run_id):
            created = False
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
                created = True
            except FileExistsError:
                pass
            if created:
                os.fsync(fd)
            child = os.open(name, flags, dir_fd=fd)
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    info.st_mode & 0o077):
                os.close(child)
                raise PromptError("PROMPT_RUN_DIR_UNSAFE")
            os.close(fd)
            fd = child
        return runtime / "runs" / run_id
    except PromptError:
        raise
    except OSError as exc:
        raise PromptError("PROMPT_RUN_DIR_UNSAFE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def render_prompt(task: TaskDefinition, claim: Claim, snapshot: WorkspaceSnapshot,
                  runtime_root: Path) -> RenderedPrompt:
    """Validate bindings, render only frozen variables, and atomically persist it."""
    if (not isinstance(task, TaskDefinition) or not isinstance(claim, Claim) or
            not isinstance(claim.task, TaskDefinition) or not isinstance(task.metadata, dict) or
            not isinstance(snapshot, WorkspaceSnapshot)):
        raise PromptError("PROMPT_INPUT_INVALID")
    run_id = claim.run_id
    if (not _uuid(run_id) or type(claim.attempt) is not int or claim.attempt < 1 or
            claim.state != "claimed" or not isinstance(claim.base_commit, str) or
            not _HASH.fullmatch(claim.base_commit)):
        raise PromptError("PROMPT_CLAIM_INVALID")
    recovery = claim.recovery_of
    if recovery is not None and not _uuid(recovery):
        raise PromptError("PROMPT_CLAIM_INVALID")
    metadata = task.metadata
    if (claim.task.metadata.get("task_id") != metadata.get("task_id") or
            claim.task.metadata != metadata or claim.task.prompt != task.prompt or
            claim.task_hash != task.task_hash or claim.prompt_hash != task.prompt_hash or
            claim.task.task_hash != task.task_hash or claim.task.prompt_hash != task.prompt_hash or
            snapshot.task_id != metadata.get("task_id") or snapshot.spec_id != metadata.get("spec_id") or
            snapshot.task_hash != task.task_hash or snapshot.prompt_hash != task.prompt_hash or
            snapshot.branch != claim.branch or snapshot.head != claim.base_commit):
        raise PromptError("PROMPT_BINDING_MISMATCH")
    try:
        main, common = repository_paths(snapshot.repo_root)
        expected_worktree = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        if (main != Path(snapshot.repo_root).resolve(strict=True) or
                common != Path(snapshot.common_dir).resolve(strict=True) or
                expected_worktree != Path(snapshot.worktree_path).resolve(strict=True) or
                expected_worktree != Path(claim.worktree_path).resolve(strict=True) or
                claim.branch != metadata["worktree"]["branch"]):
            raise PromptError("PROMPT_BINDING_MISMATCH")
        runtime = contained(main, ".sdd/runtime")
        if (not Path(runtime_root).is_absolute() or Path(runtime_root) != runtime or
                runtime.resolve(strict=True) != Path(runtime_root).resolve(strict=True)):
            raise PromptError("PROMPT_RUNTIME_ROOT_INVALID")
        gates = load_satisfied_gates(task, main)
        if claim.failed_source is None:
            live, confirmed, spec_state = validate_candidate(
                task, snapshot, main, gates, "partial" if recovery is not None else None,
            )
        else:
            from .claim_validation import _canonical_candidate
            from .failed_recovery import _capture, compare_failed_observation_current
            from .failed_workspace import VerifiedFailedWorkspace, compare_verified_failed_workspace

            proof = claim.failed_source
            if (type(proof) is not VerifiedFailedWorkspace or
                    recovery != proof.source_run_id or claim.base_commit != proof.original_base or
                    snapshot != proof.baseline):
                raise PromptError("PROMPT_FAILED_SOURCE_INVALID")
            live, confirmed, spec_state, checked_main, _authority, _roots = _canonical_candidate(
                task, main, gates,
            )
            decision = compare_verified_failed_workspace(proof, live)
            current = _capture(checked_main, live, proof.baseline)
            if (not decision.recoverable or decision.kind != "partial" or
                    compare_failed_observation_current(proof, current, live).kind != "unchanged"):
                raise PromptError("PROMPT_FAILED_SOURCE_INVALID")
        if spec_state not in {"已确认", "实施中"}:
            raise PromptError("PROMPT_SPEC_NOT_CLAIMABLE")
        if not set(live.metadata["required_gates"]).issubset(confirmed):
            raise PromptError("PROMPT_GATES_UNSATISFIED")
    except PromptError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PromptError(getattr(exc, "code", "PROMPT_AUTHORITY_INVALID")) from exc
    template_hash = hashlib.sha256(live.prompt.encode("utf-8")).hexdigest()
    if template_hash != task.prompt_hash or template_hash != claim.prompt_hash:
        raise PromptError("PROMPT_HASH_MISMATCH")
    relative_run = ".sdd/runtime/runs/" + run_id
    values: Dict[str, str] = {
        "RUN_ID": run_id, "WORKTREE": metadata["worktree"]["path"],
        "BASE_COMMIT": claim.base_commit, "RESULT_PATH": relative_run + "/result.json",
        "EVENT_PATH": relative_run + "/events.jsonl",
    }
    matches = list(_VARIABLE.finditer(live.prompt))
    if any(match.group(1) not in _ALLOWED for match in matches):
        raise PromptError("PROMPT_VARIABLE_UNKNOWN")
    rendered = _VARIABLE.sub(lambda match: values[match.group(1)], live.prompt)
    if "{{" in rendered or "}}" in rendered:
        raise PromptError("PROMPT_VARIABLE_UNRESOLVED")
    try:
        _scan(rendered)
    except ValueError as exc:
        raise PromptError("PROMPT_SENSITIVE_CONTENT") from exc
    try:
        _private_run_dir(runtime, run_id)
        target = contained(main, relative_run + "/prompt.md")
        atomic_write(target, rendered)
    except PromptError:
        raise
    except (OSError, ValueError) as exc:
        raise PromptError("PROMPT_WRITE_FAILED") from exc
    return RenderedPrompt(rendered, target, template_hash,
                          hashlib.sha256(rendered.encode("utf-8")).hexdigest())
