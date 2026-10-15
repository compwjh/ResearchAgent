"""Build a complete, read-only completion-journal proposal."""
import copy
import hashlib
import secrets
from pathlib import Path

from .atomic import contained
from .claims import Claim
from .completion_journal import _document_hash
from .documents import TaskDefinition, parse_task
from .git_expected_entries import capture_expected_git_entries
from .git_index import read_index_snapshot
from .journal_schema import validate_journal
from .locks import repository_paths
from .mirrors import render_status_update, validate_mirrors
from .owners import OwnerIdentity
from .results import ValidationReport
from .run_docs import _summary_relative, build_summary
from .workspace import WorkspaceSnapshot, capture_snapshot, compare_snapshot


class CompletionPrepareError(ValueError):
    """A completion proposal cannot be safely prepared."""


def _owner(identity: OwnerIdentity) -> dict:
    return {"executor_id": identity.executor_id, "host_id": identity.host_id,
            "pid": identity.pid, "process_started_at": identity.process_started_at,
            "token": identity.token}


def _same_task(actual: TaskDefinition, expected: TaskDefinition) -> bool:
    return (actual.metadata == expected.metadata and actual.prompt == expected.prompt and
            actual.task_hash == expected.task_hash and actual.prompt_hash == expected.prompt_hash)


def prepare_completion_journal(
    task: TaskDefinition, claim: Claim, before: WorkspaceSnapshot, after: WorkspaceSnapshot,
    report: ValidationReport, repo_root: Path, *, target_task_status: str = None,
) -> dict:
    """Freeze docs, index, and raw Git anchors without writing any state."""
    if (not isinstance(task, TaskDefinition) or not isinstance(claim, Claim) or
            not isinstance(before, WorkspaceSnapshot) or not isinstance(after, WorkspaceSnapshot) or
            not isinstance(report, ValidationReport) or not report.valid or
            not isinstance(repo_root, Path) or not isinstance(claim.owner, OwnerIdentity)):
        raise CompletionPrepareError("COMPLETION_PREPARE_INPUT_INVALID")
    try:
        main, common = repository_paths(repo_root)
        supplied = repo_root.resolve(strict=True)
        metadata = task.metadata
        worktree = contained(main, metadata["worktree"]["path"]).resolve(strict=True)
        if supplied not in {main, worktree} or metadata.get("status") != "pending":
            raise CompletionPrepareError("COMPLETION_PREPARE_ROOT_INVALID")
        if (before.repo_root != main or before.common_dir != common or before.worktree_path != worktree or
                after.repo_root != main or after.common_dir != common or after.worktree_path != worktree or
                before.head != claim.base_commit or before.branch != claim.branch or
                after.branch != claim.branch or claim.branch != metadata["worktree"]["branch"] or
                Path(claim.worktree_path).resolve(strict=True) != worktree or
                before.task_id != metadata["task_id"] or after.task_id != metadata["task_id"] or
                before.task_hash != task.task_hash or after.task_hash != task.task_hash or
                before.prompt_hash != task.prompt_hash or after.prompt_hash != task.prompt_hash or
                claim.task_hash != task.task_hash or claim.prompt_hash != task.prompt_hash or
                not _same_task(claim.task, task)):
            raise CompletionPrepareError("COMPLETION_PREPARE_BINDING_MISMATCH")
        outcome = report.result["outcome"]
        if outcome == "succeeded":
            if target_task_status not in {None, "completed"}:
                raise CompletionPrepareError("COMPLETION_PREPARE_STATUS_INVALID")
            target_task_status = "completed"
        elif outcome == "blocked":
            if target_task_status not in {None, "blocked"}:
                raise CompletionPrepareError("COMPLETION_PREPARE_STATUS_INVALID")
            target_task_status = "blocked"
        elif outcome == "failed":
            if target_task_status not in {None, "pending", "blocked"}:
                raise CompletionPrepareError("COMPLETION_PREPARE_STATUS_INVALID")
            if target_task_status == "pending":
                target_task_status = None
        else:
            raise CompletionPrepareError("COMPLETION_PREPARE_OUTCOME_INVALID")
        number = metadata["task_id"][-2:]
        directory = contained(worktree, "docs/sdd/plans/" + metadata["spec_id"])
        task_files = sorted(directory.glob("task-{}-*.md".format(number)))
        validate_mirrors(task, worktree)
        if len(task_files) != 1 or not _same_task(parse_task(task_files[0]), task):
            raise CompletionPrepareError("COMPLETION_PREPARE_TASK_CHANGED")
        expected_result = copy.deepcopy(report.result)
        summary_path = _summary_relative(task, claim)
        documents = {summary_path: build_summary(task, claim, expected_result)}
        doc_before_hashes = {}
        if target_task_status is not None:
            first = render_status_update(task, target_task_status, worktree)
            first_hashes = {path: _document_hash(worktree, path) for path in first}
            second = render_status_update(task, target_task_status, worktree)
            if (first != second or first_hashes !=
                    {path: _document_hash(worktree, path) for path in second}):
                raise CompletionPrepareError("COMPLETION_PREPARE_MIRRORS_CHANGED")
            documents.update(second)
            doc_before_hashes = first_hashes
        expected_docs = []
        for path, content in sorted(documents.items(), key=lambda item: item[0].encode("utf-8")):
            old_hash = (doc_before_hashes[path] if path in doc_before_hashes else
                        _document_hash(worktree, path))
            if path == summary_path and old_hash is not None:
                raise CompletionPrepareError("COMPLETION_PREPARE_SUMMARY_EXISTS")
            expected_docs.append({"path": path, "before_sha256": old_hash, "content": content,
                                  "after_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()})
        proof_changed_paths = None
        if claim.failed_source is not None:
            from .active_failed_recovery import compare_active_failed_workspace
            from .failed_workspace import VerifiedFailedWorkspace

            proof = claim.failed_source
            if (type(proof) is not VerifiedFailedWorkspace or
                    claim.recovery_of != proof.source_run_id or
                    claim.base_commit != proof.original_base or before != proof.baseline):
                raise CompletionPrepareError("COMPLETION_PREPARE_FAILED_SOURCE_MISMATCH")
            decision = compare_active_failed_workspace(proof, after, task)
            if not decision.recoverable:
                raise CompletionPrepareError("COMPLETION_PREPARE_FAILED_SOURCE_INVALID")
            proof_changed_paths = set(decision.changed_paths)
        changed = tuple(sorted(path for path in before.allowed_hashes.keys() | after.allowed_hashes.keys()
                               if before.allowed_hashes.get(path) != after.allowed_hashes.get(path) and
                               (isinstance(before.allowed_hashes.get(path), str) or
                                isinstance(after.allowed_hashes.get(path), str)) and
                               (proof_changed_paths is None or path in proof_changed_paths)))
        if changed != tuple(sorted(report.changed_paths)):
            raise CompletionPrepareError("COMPLETION_PREPARE_CHANGED_PATHS_MISMATCH")
        changed_paths = [{"path": path, "before_sha256": before.allowed_hashes.get(path),
                          "after_sha256": after.allowed_hashes.get(path)} for path in changed]
        source_paths = list(changed) if outcome == "succeeded" else []
        committed = sorted(set(source_paths) | set(documents), key=lambda path: path.encode("utf-8"))
        index_before = read_index_snapshot(worktree, committed, original_head=after.head)
        anchors = capture_expected_git_entries(worktree, committed, expected_docs=expected_docs,
                                               original_head=after.head)
        if read_index_snapshot(worktree, committed, original_head=after.head) != index_before:
            raise CompletionPrepareError("COMPLETION_PREPARE_INDEX_CHANGED")
        if compare_snapshot(after, capture_snapshot(main, task)).kind != "unchanged":
            raise CompletionPrepareError("COMPLETION_PREPARE_WORKSPACE_CHANGED")
        journal = {
            "schema": "sdd-completion-journal/v1", "run_id": claim.run_id,
            "task_id": metadata["task_id"], "owner": _owner(claim.owner),
            "base_commit": claim.base_commit, "original_head": after.head,
            "task_hash": task.task_hash, "prompt_hash": task.prompt_hash,
            "allowed_paths": list(metadata["allowed_paths"]), "changed_paths": changed_paths,
            "expected_docs": expected_docs, "expected_result": expected_result,
            "terminal_outcome": outcome, "expected_git_entries": anchors,
            "committed_paths": committed, "staged_paths": committed,
            "index_before": index_before, "index_observed_before": None, "index_after": None,
            "index_lock_owner_token": secrets.token_hex(32), "index_lock_temp_path": None,
            "index_lock_identity": None, "index_recovery_stage": "not_acquired",
            "candidate_commit_hash": None,
            "commit_message": "sdd: {} {} run {}".format(outcome, metadata["task_id"], claim.run_id),
            "phase": "prepared",
        }
        return validate_journal(journal)
    except CompletionPrepareError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CompletionPrepareError(getattr(exc, "code", "COMPLETION_PREPARE_INVALID")) from exc
