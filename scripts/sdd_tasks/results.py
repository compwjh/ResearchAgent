"""Pure result validation against a claimed Task and observed workspace."""

import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from .atomic import contained
from .claims import Claim
from .documents import TaskDefinition, parse_task
from .locks import repository_paths
from .result_schema import validate_summary_result
from .workspace import WorkspaceSnapshot, _status_paths, capture_snapshot, compare_snapshot, hash_artifact


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    errors: Tuple[str, ...]
    result: Dict[str, Any]
    changed_paths: Tuple[str, ...]


def _add(errors: list, code: str) -> None:
    if code not in errors:
        errors.append(code)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)


def _file_hash(root: Path, relative: str) -> str:
    return hash_artifact(root, relative)


def validate_result(data: Dict[str, Any], task: TaskDefinition, claim: Claim,
                    before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> ValidationReport:
    """Validate output declarations and filesystem evidence; commands still need rerunning."""
    result = dict(data) if isinstance(data, dict) else {}
    try:
        result = validate_summary_result(data)
    except (TypeError, ValueError) as exc:
        code = str(exc).split(":", 1)[0]
        return ValidationReport(False, (code,), result, ())
    errors = []
    if (not isinstance(task, TaskDefinition) or not isinstance(claim, Claim) or
            not isinstance(claim.task, TaskDefinition) or not isinstance(before, WorkspaceSnapshot) or
            not isinstance(after, WorkspaceSnapshot)):
        return ValidationReport(False, ("RESULT_INPUT_INVALID",), result, ())
    if claim.state not in ("claimed", "running"):
        return ValidationReport(False, ("RESULT_CLAIM_STATE_INVALID",), result, ())
    if (result["run_id"] != claim.run_id or result["task_id"] != task.metadata["task_id"] or
            result["task_hash"] != task.task_hash or result["prompt_hash"] != task.prompt_hash or
            claim.task.metadata != task.metadata or claim.task.prompt != task.prompt or
            claim.task_hash != task.task_hash or claim.prompt_hash != task.prompt_hash):
        _add(errors, "RESULT_CLAIM_MISMATCH")
    changed_paths = ()
    try:
        main, common = repository_paths(before.repo_root)
        worktree = contained(main, task.metadata["worktree"]["path"]).resolve(strict=True)
        if (Path(before.repo_root).resolve(strict=True) != main or
                Path(before.common_dir).resolve(strict=True) != common or
                Path(before.worktree_path).resolve(strict=True) != worktree or
                Path(claim.worktree_path).resolve(strict=True) != worktree or
                before.task_id != task.metadata["task_id"] or before.spec_id != task.metadata["spec_id"] or
                before.task_hash != task.task_hash or before.prompt_hash != task.prompt_hash or
                before.branch != claim.branch or before.head != claim.base_commit):
            _add(errors, "RESULT_SNAPSHOT_MISMATCH")
        task_dir = contained(worktree, "docs/sdd/plans/" + task.metadata["spec_id"])
        task_files = sorted(task_dir.glob("task-{}-*.md".format(task.metadata["task_id"].rsplit("-", 1)[1])))
        if len(task_files) != 1:
            _add(errors, "RESULT_CANONICAL_TASK_INVALID")
        else:
            current = parse_task(contained(worktree, task_files[0].relative_to(worktree).as_posix()))
            if (current.metadata != task.metadata or current.task_hash != task.task_hash or
                    current.prompt_hash != task.prompt_hash):
                _add(errors, "RESULT_CANONICAL_TASK_STALE")
        observed = capture_snapshot(main, task)
        if compare_snapshot(after, observed).kind != "unchanged":
            _add(errors, "RESULT_AFTER_SNAPSHOT_STALE")
        decision = None
        if claim.failed_source is None:
            decision = compare_snapshot(before, observed)
        else:
            from .active_failed_recovery import compare_active_failed_workspace
            from .failed_workspace import VerifiedFailedWorkspace

            proof = claim.failed_source
            if (type(proof) is not VerifiedFailedWorkspace or
                    claim.recovery_of != proof.recovery_source_id or
                    claim.base_commit != proof.original_base or before != proof.baseline):
                _add(errors, "RESULT_FAILED_SOURCE_MISMATCH")
            else:
                decision = compare_active_failed_workspace(proof, observed, task)
        if decision is not None and not decision.recoverable:
            _add(errors, "RESULT_WORKSPACE_OUT_OF_SCOPE")
        old, new = before.allowed_hashes, observed.allowed_hashes
        changed_paths = ()
        if decision is not None:
            changed_paths = tuple(sorted(path for path in decision.changed_paths
                                         if isinstance(old.get(path), str) or
                                         isinstance(new.get(path), str)))
        rename_paths = {path for snap in (before, observed)
                        for path, code in _status_paths(snap.status_records).items()
                        if "R" in code or "C" in code}
        declared = {item["path"]: item for item in result["changed_files"]}
        if len(declared) != len(result["changed_files"]) or set(declared) != set(changed_paths):
            _add(errors, "RESULT_CHANGED_FILES_MISMATCH")
        for path in changed_paths:
            item = declared.get(path)
            if item is None:
                continue
            old_hash, new_hash = old.get(path), new.get(path)
            expected = ("deleted" if new_hash is None else
                        "renamed" if old_hash is None and path in rename_paths else
                        "added" if old_hash is None else "modified")
            expected_hash = None if expected == "deleted" else new_hash
            if item["change"] != expected or item["sha256"] != expected_hash:
                _add(errors, "RESULT_CHANGED_FILE_HASH_MISMATCH")
        expected_artifacts = set(task.metadata["expected_artifacts"])
        artifacts = {item["path"]: item for item in result["artifacts"]}
        if (len(artifacts) != len(result["artifacts"]) or
                not set(artifacts).issubset(expected_artifacts) or
                (result["outcome"] == "succeeded" and set(artifacts) != expected_artifacts)):
            _add(errors, "RESULT_ARTIFACTS_MISMATCH")
        missing_artifacts = expected_artifacts - set(artifacts)
        if (result["outcome"] != "succeeded" and any(
                not any(path in blocker for blocker in result["blockers"])
                for path in missing_artifacts)):
            _add(errors, "RESULT_MISSING_ARTIFACT_BLOCKER")
        for path, item in artifacts.items():
            if path in expected_artifacts and _file_hash(worktree, path) != item["sha256"]:
                _add(errors, "RESULT_ARTIFACT_HASH_MISMATCH")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        _add(errors, getattr(exc, "code", "RESULT_WORKSPACE_INVALID"))
    try:
        started, ended = _time(result["started_at"]), _time(result["ended_at"])
        claimed = _time(claim.claimed_at)
        if started < claimed:
            _add(errors, "RESULT_STARTED_BEFORE_CLAIM")
        if ended > datetime.now(timezone.utc):
            _add(errors, "RESULT_ENDED_IN_FUTURE")
    except (AttributeError, TypeError, ValueError):
        _add(errors, "RESULT_TIME_INVALID")
    try:
        for raw in task.metadata["validation_commands"]:
            argv = tuple(shlex.split(raw, posix=True))
            matches = [item for item in result["commands"] if tuple(item["argv"]) == argv]
            if len(matches) != 1:
                _add(errors, "RESULT_VALIDATION_COMMAND_MISSING")
            elif (result["outcome"] == "succeeded" and
                  (matches[0]["status"] != "executed" or matches[0]["exit_code"] != 0)):
                _add(errors, "RESULT_VALIDATION_COMMAND_FAILED")
    except (KeyError, TypeError, ValueError):
        _add(errors, "RESULT_VALIDATION_COMMAND_INVALID")
    if result["outcome"] == "succeeded" and any(item["outcome"] != "passed" for item in result["tests"]):
        _add(errors, "RESULT_TESTS_NOT_PASSED")
    return ValidationReport(not errors, tuple(errors), result, changed_paths)
