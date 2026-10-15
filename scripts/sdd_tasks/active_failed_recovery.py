"""Bind an active retry to its immediate failed partial source."""

import hmac
import sqlite3
import uuid
from pathlib import Path

from .atomic import contained, read_text
from .documents import TaskDefinition
from .failed_recovery import _stored_decision
from .failed_workspace import (
    VerifiedFailedWorkspace,
    _identity,
    _project,
    compare_verified_failed_workspace,
)
from .failure_history import (
    VerifiedFailureHistory,
    _git_state,
    _task_context,
    _verify_document_objects,
    _verify_failure_history_core,
)
from .lease_recovery import stored_owner
from .recovery_snapshots import _event, _snapshot, _uuid
from .run_owner import resolve_run_owner
from .workspace import RecoveryDecision, WorkspaceSnapshot
from .workspace_observation import _decode_observation_event


class ActiveFailedRecoveryError(ValueError):
    """An active retry is not bound to a valid immediate failed source."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _reject(code: str) -> None:
    raise ActiveFailedRecoveryError(code)


def _active_source_binding(conn, active_run_id, task, repo_root):
    """Return strict source bindings only; this is not complete history proof."""
    if (not isinstance(conn, sqlite3.Connection) or not isinstance(active_run_id, str) or
            type(task) is not TaskDefinition or not isinstance(repo_root, (Path, str))):
        _reject("ACTIVE_FAILED_ARGUMENT_INVALID")
    try:
        if str(uuid.UUID(active_run_id)) != active_run_id:
            _reject("ACTIVE_FAILED_ARGUMENT_INVALID")
    except (AttributeError, TypeError, ValueError):
        _reject("ACTIVE_FAILED_ARGUMENT_INVALID")

    try:
        active = conn.execute("SELECT * FROM runs WHERE run_id=?", (active_run_id,)).fetchone()
        if (active is None or active["state"] not in {"claimed", "running"} or
                active["ended_at"] is not None):
            _reject("ACTIVE_FAILED_RUN_NOT_ACTIVE")
        payload = _event(conn, active_run_id, "workspace_snapshot", True)
        if (not isinstance(payload, dict) or set(payload) != {"schema", "source_run_id", "snapshot"} or
                payload["schema"] != "sdd-workspace-snapshot/v1"):
            _reject("ACTIVE_FAILED_SNAPSHOT_INVALID")
        source_id = payload["source_run_id"]
        if not isinstance(source_id, str) or str(uuid.UUID(source_id)) != source_id:
            _reject("ACTIVE_FAILED_SOURCE_INVALID")
        claim = _event(conn, active_run_id, "recovery_claim", True)
        if (not isinstance(claim, dict) or set(claim) != {"schema", "recovery_of"} or
                claim["schema"] != "sdd-recovery-claim/v1" or claim["recovery_of"] != source_id):
            _reject("ACTIVE_FAILED_CLAIM_MISMATCH")
        source = conn.execute("SELECT * FROM runs WHERE run_id=?", (source_id,)).fetchone()
        if (source is None or source["task_id"] != active["task_id"] or
                source["state"] != "failed" or source["ended_at"] is None or
                conn.execute("SELECT 1 FROM leases WHERE run_id=?", (source_id,)).fetchone()):
            _reject("ACTIVE_FAILED_SOURCE_INVALID")

        main, worktree, baseline = _task_context(conn, source_id, task, Path(repo_root))
        active_fields = (active["task_id"], active["task_hash"], active["prompt_hash"],
                         active["worktree"], active["branch"], active["agent_role"],
                         active["base_commit"])
        expected_fields = (task.metadata["task_id"], task.task_hash, task.prompt_hash,
                           task.metadata["worktree"]["path"], task.metadata["worktree"]["branch"],
                           task.metadata["agent_role"], baseline.head)
        source_fields = (source["task_id"], source["task_hash"], source["prompt_hash"],
                         source["worktree"], source["branch"], source["agent_role"],
                         source["base_commit"])
        if active_fields != expected_fields or source_fields != expected_fields:
            _reject("ACTIVE_FAILED_BINDING_MISMATCH")
        active_owner = stored_owner(active["owner_json"])
        if active_owner.executor_id != active["executor_id"]:
            _reject("ACTIVE_FAILED_OWNER_INVALID")
        source_id_in_snapshot, copied = _snapshot(payload, task, active, main,
                                                   baseline.common_dir, worktree)
        if source_id_in_snapshot != source_id or copied != baseline:
            _reject("ACTIVE_FAILED_BASELINE_MISMATCH")
        latest = conn.execute(
            "SELECT run_id FROM runs WHERE task_id=? ORDER BY attempt DESC LIMIT 1",
            (active["task_id"],),
        ).fetchone()
        previous = conn.execute(
            "SELECT run_id FROM runs WHERE task_id=? AND attempt<? ORDER BY attempt DESC LIMIT 1",
            (active["task_id"], active["attempt"]),
        ).fetchone()
        if latest is None or latest["run_id"] != active_run_id or previous is None or previous["run_id"] != source_id:
            _reject("ACTIVE_FAILED_ATTEMPT_ORDER_INVALID")
        return main, worktree, active, source, baseline
    except ActiveFailedRecoveryError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise ActiveFailedRecoveryError("ACTIVE_FAILED_BINDING_INVALID") from exc


def _same_owner(actual, expected) -> bool:
    fields = ("executor_id", "host_id", "pid", "process_started_at")
    try:
        token_match = (isinstance(actual.token, str) and isinstance(expected.token, str) and
                       hmac.compare_digest(actual.token.encode("utf-8"), expected.token.encode("utf-8")))
    except (AttributeError, UnicodeError):
        return False
    return token_match and all(getattr(actual, field) == getattr(expected, field) for field in fields)


def _only_active_consumer(conn, task_id, source_id, active_run_id) -> None:
    consumers = []
    runs = conn.execute("SELECT run_id FROM runs WHERE task_id=?", (task_id,)).fetchall()
    for row in runs:
        run_id = row["run_id"]
        snapshot = _event(conn, run_id, "workspace_snapshot", True)
        if (not isinstance(snapshot, dict) or set(snapshot) != {"schema", "source_run_id", "snapshot"} or
                snapshot["schema"] != "sdd-workspace-snapshot/v1"):
            _reject("ACTIVE_FAILED_CONSUMPTION_INVALID")
        snapshot_source = snapshot["source_run_id"]
        if snapshot_source is not None:
            snapshot_source = _uuid(snapshot_source)
        claimed = _event(conn, run_id, "recovery_claim", snapshot_source is not None)
        claim_source = None
        if claimed is not None:
            if (not isinstance(claimed, dict) or set(claimed) != {"schema", "recovery_of"} or
                    claimed["schema"] != "sdd-recovery-claim/v1"):
                _reject("ACTIVE_FAILED_CONSUMPTION_INVALID")
            claim_source = _uuid(claimed["recovery_of"])
        if snapshot_source != claim_source:
            _reject("ACTIVE_FAILED_CONSUMPTION_INVALID")
        if snapshot_source == source_id:
            consumers.append(run_id)
    if consumers != [active_run_id]:
        _reject("ACTIVE_FAILED_SOURCE_CONSUMED")


def _bound_failed_proof(conn, task, repo_root, binding) -> VerifiedFailedWorkspace:
    """Prove failed-source history and current immutable documents for a bound run."""
    main, worktree, _active, source, baseline = binding
    try:
        verified = _verify_failure_history_core(conn, source["run_id"], task, repo_root)
        history_main, history_worktree, history_baseline, before, records, tips = verified
        if (history_main != main or history_worktree != worktree or history_baseline != baseline or
                not records or not tips or records[-1][0]["run_id"] != source["run_id"] or
                tips[-1][0] != source["run_id"] or before[0] != records[-1][3] or
                before[1] != task.metadata["worktree"]["branch"]):
            _reject("ACTIVE_FAILED_HISTORY_MISMATCH")
        excluded, latest_documents = _verify_document_objects(conn, worktree, task, records)
        observation = _decode_observation_event(
            conn, source["run_id"], task, main, expected_tip=tips[-1][1])
        history = VerifiedFailureHistory(tuple(tips), excluded, before[0])
        proof = VerifiedFailedWorkspace(
            source["run_id"], _identity(baseline), baseline, observation, history,
            baseline.head, tips[-1][1], before[0], tuple(task.metadata["allowed_paths"]),
            tuple(excluded),
        )
        decision = compare_verified_failed_workspace(proof, task)
        if not decision.recoverable or decision.kind != "partial":
            _reject("ACTIVE_FAILED_SOURCE_NOT_PARTIAL")
        stored = _stored_decision(conn, source["run_id"])
        if stored is not None and stored != decision.kind:
            _reject("ACTIVE_FAILED_DECISION_MISMATCH")
        for path, content in latest_documents.items():
            if read_text(contained(worktree, path)) != content:
                _reject("ACTIVE_FAILED_DOCUMENT_CHANGED")
        if _git_state(worktree) != before:
            _reject("ACTIVE_FAILED_WORKTREE_CHANGED")
        return proof
    except ActiveFailedRecoveryError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise ActiveFailedRecoveryError("ACTIVE_FAILED_PROOF_INVALID") from exc


def load_active_failed_source(conn, active_run_id, task, repo_root) -> VerifiedFailedWorkspace:
    """Prove an active partial retry's baseline and failed-source document tip."""
    try:
        binding = _active_source_binding(conn, active_run_id, task, repo_root)
        main, worktree, active, source, baseline = binding
        task_row = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                (task.metadata["task_id"],)).fetchone()
        if (task_row is None or task_row["status"] != "pending" or
                task.metadata.get("status") != "pending"):
            _reject("ACTIVE_FAILED_TASK_NOT_PENDING")
        owner = stored_owner(active["owner_json"])
        resolved = resolve_run_owner(conn, active_run_id, active["executor_id"], owner.pid)
        if not _same_owner(resolved, owner):
            _reject("ACTIVE_FAILED_OWNER_MISMATCH")
        leases = conn.execute("SELECT * FROM leases WHERE task_id=? OR run_id=?",
                              (active["task_id"], active_run_id)).fetchall()
        if (len(leases) != 1 or leases[0]["task_id"] != active["task_id"] or
                leases[0]["run_id"] != active_run_id or
                leases[0]["claimed_at"] != active["claimed_at"] or
                not isinstance(leases[0]["owner_token"], str) or
                not hmac.compare_digest(leases[0]["owner_token"].encode("utf-8"),
                                        owner.token.encode("utf-8"))):
            _reject("ACTIVE_FAILED_LEASE_MISMATCH")
        _only_active_consumer(conn, active["task_id"], source["run_id"], active_run_id)
        return _bound_failed_proof(conn, task, repo_root, binding)
    except ActiveFailedRecoveryError:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise ActiveFailedRecoveryError("ACTIVE_FAILED_PROOF_INVALID") from exc


def compare_active_failed_workspace(proof, current, task) -> RecoveryDecision:
    """Compare the original baseline with an active capture at its proven document tip."""

    def conflict(code):
        return RecoveryDecision("conflict", (), (), False, code)

    if (type(proof) is not VerifiedFailedWorkspace or type(current) is not WorkspaceSnapshot or
            type(task) is not TaskDefinition):
        return conflict("ACTIVE_FAILED_COMPARISON_INPUT_INVALID")
    try:
        source = compare_verified_failed_workspace(proof, task)
        roots = tuple(task.metadata["allowed_paths"])
        if not source.recoverable or source.kind != "partial":
            return conflict("ACTIVE_FAILED_SOURCE_NOT_PARTIAL")
        if (proof.original_base != proof.baseline.head or
                proof.history.current_tip != proof.active_claim_tip or
                proof.allowed_roots != roots or _identity(current) != _identity(proof.baseline) or
                current.head != proof.active_claim_tip):
            return conflict("ACTIVE_FAILED_COMPARISON_MISMATCH")
        old_status, old_hashes = _project(proof.baseline, proof.excluded_paths, roots)
        new_status, new_hashes = _project(current, proof.excluded_paths, roots)
        changed = {path for path in old_status.keys() | new_status.keys()
                   if old_status.get(path) != new_status.get(path)}
        changed.update(path for path in old_hashes.keys() | new_hashes.keys()
                       if old_hashes.get(path) != new_hashes.get(path))
        changed_paths = tuple(sorted(changed))
        outside = tuple(path for path in changed_paths
                        if not any(path == root or path.startswith(root + "/") for root in roots))
        if outside:
            return RecoveryDecision("out_of_scope", changed_paths, outside, False,
                                    "workspace_out_of_scope")
        return RecoveryDecision("partial" if changed_paths else "unchanged",
                                changed_paths, (), True, None)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return conflict(getattr(exc, "code", "ACTIVE_FAILED_COMPARISON_INVALID"))
