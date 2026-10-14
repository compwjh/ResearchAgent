"""Pure comparison of a failed workspace under a verified document-history proof."""

import re
import uuid
from dataclasses import dataclass

from .documents import TaskDefinition
from .failure_history import VerifiedFailureHistory
from .journal_fields import validate_path
from .workspace import RecoveryDecision, WorkspaceError, WorkspaceSnapshot

_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class FailedWorkspaceError(WorkspaceError):
    """A failed workspace projection is malformed or lacks matching proof."""


@dataclass(frozen=True)
class VerifiedFailedWorkspace:
    """Ephemeral source data bound to its verified parent and document tips."""

    source_run_id: str
    task_identity: tuple
    baseline: WorkspaceSnapshot
    observation: WorkspaceSnapshot
    history: VerifiedFailureHistory
    original_base: str
    observation_tip: str
    active_claim_tip: str
    allowed_roots: tuple
    excluded_paths: tuple


def _identity(snapshot):
    return (str(snapshot.repo_root), str(snapshot.common_dir), str(snapshot.worktree_path),
            snapshot.spec_id, snapshot.task_id, snapshot.task_hash, snapshot.prompt_hash,
            snapshot.branch)


def _inside(path, roots):
    return any(path == root or path.startswith(root + "/") for root in roots)


def _strict_status(records):
    result, index = {}, 0
    while index < len(records):
        item = records[index]
        if len(item) < 4 or item[2] != " ":
            raise FailedWorkspaceError("FAILED_WORKSPACE_STATUS_INVALID")
        code, path = item[:2], item[3:]
        if path in result:
            raise FailedWorkspaceError("FAILED_WORKSPACE_STATUS_INVALID")
        result[path] = code
        if "R" in code or "C" in code:
            index += 1
            if index == len(records) or records[index] in result:
                raise FailedWorkspaceError("FAILED_WORKSPACE_STATUS_INVALID")
            result[records[index]] = code
        index += 1
    return result


def _project(snapshot, excluded, roots):
    records = snapshot.status_records
    if not isinstance(records, tuple) or any(not isinstance(item, str) for item in records):
        raise FailedWorkspaceError("FAILED_WORKSPACE_STATUS_INVALID")
    status = _strict_status(records)
    for path in status:
        validate_path(path, "status.path")
    hashes = snapshot.allowed_hashes
    if (not isinstance(hashes, dict) or not set(roots).issubset(hashes) or
            any(not isinstance(path, str) or not _inside(path, roots) or
                (value is not None and (not isinstance(value, str) or not _SHA.fullmatch(value)))
                for path, value in hashes.items())):
        raise FailedWorkspaceError("FAILED_WORKSPACE_HASHES_INVALID")
    projected_status, projected_hashes = dict(status), dict(hashes)
    for path in excluded:
        if path in projected_hashes and projected_hashes[path] is None:
            raise FailedWorkspaceError("FAILED_WORKSPACE_EXCLUSION_MARKER_INVALID")
        projected_status.pop(path, None)
        projected_hashes.pop(path, None)
    remaining = set(projected_hashes)
    markers = sorted((path for path, value in projected_hashes.items()
                      if value is None and path not in roots and
                      any(doc.startswith(path + "/") for doc in excluded)),
                     key=lambda path: path.count("/"), reverse=True)
    for marker in markers:
        if not any(path.startswith(marker + "/") for path in remaining):
            remaining.remove(marker)
    projected_hashes = {path: value for path, value in projected_hashes.items() if path in remaining}
    return projected_status, projected_hashes


def compare_verified_failed_workspace(proof, task):
    """Classify only verified failed-run changes, without modifying either snapshot."""
    if type(proof) is not VerifiedFailedWorkspace or type(task) is not TaskDefinition:
        raise FailedWorkspaceError("FAILED_WORKSPACE_ARGUMENT_INVALID")
    try:
        canonical_id = str(uuid.UUID(proof.source_run_id))
        base = proof.baseline
        observed = proof.observation
        if type(base) is not WorkspaceSnapshot or type(observed) is not WorkspaceSnapshot:
            raise FailedWorkspaceError("FAILED_WORKSPACE_IDENTITY_MISMATCH")
        roots = tuple(task.metadata["allowed_paths"])
        excluded = tuple(proof.excluded_paths)
        identity = _identity(base)
        expected = (str(base.repo_root), str(base.common_dir), str(base.worktree_path),
                    task.metadata["spec_id"], task.metadata["task_id"], task.task_hash,
                    task.prompt_hash, task.metadata["worktree"]["branch"])
        if (canonical_id != proof.source_run_id or type(proof.history) is not VerifiedFailureHistory or
                identity != expected or _identity(observed) != identity or
                proof.task_identity != identity or proof.allowed_roots != roots or
                not roots or len(roots) != len(set(roots))):
            raise FailedWorkspaceError("FAILED_WORKSPACE_IDENTITY_MISMATCH")
        for root in roots:
            validate_path(root, "allowed_root")
        for path in excluded:
            validate_path(path, "excluded_path")
        if (excluded != tuple(sorted(set(excluded))) or
                proof.history.excluded_paths != excluded or
                not _OID.fullmatch(proof.original_base) or base.head != proof.original_base or
                not _OID.fullmatch(proof.observation_tip) or observed.head != proof.observation_tip or
                proof.history.current_tip != proof.active_claim_tip or
                not _OID.fullmatch(proof.active_claim_tip) or
                not proof.history.observation_tips or
                proof.history.observation_tips[-1] != (proof.source_run_id, proof.observation_tip) or
                len({run_id for run_id, _tip in proof.history.observation_tips}) !=
                len(proof.history.observation_tips)):
            raise FailedWorkspaceError("FAILED_WORKSPACE_PROOF_MISMATCH")
        old_status, old_hashes = _project(base, excluded, roots)
        new_status, new_hashes = _project(observed, excluded, roots)
        changed = {path for path in old_status.keys() | new_status.keys()
                   if old_status.get(path) != new_status.get(path)}
        changed.update(path for path in old_hashes.keys() | new_hashes.keys()
                       if old_hashes.get(path) != new_hashes.get(path))
        changed_paths = tuple(sorted(changed))
        outside = tuple(path for path in changed_paths if not _inside(path, roots))
        if outside:
            return RecoveryDecision("out_of_scope", changed_paths, outside, False,
                                    "workspace_out_of_scope")
        return RecoveryDecision("partial" if changed_paths else "unchanged", changed_paths, (), True, None)
    except FailedWorkspaceError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FailedWorkspaceError("FAILED_WORKSPACE_INVALID") from exc
