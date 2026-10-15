"""Private selection context for a verified failed-run recovery source."""

from dataclasses import dataclass
from typing import Optional

from .failed_recovery import (
    FailedRecoveryError,
    _capture,
    compare_failed_observation_current,
    load_failed_recovery_source,
)
from .failed_workspace import VerifiedFailedWorkspace, compare_verified_failed_workspace
from .workspace import RecoveryDecision, WorkspaceSnapshot


class FailedSelectionError(ValueError):
    """A failed source cannot provide a safe claim snapshot."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FailedClaimSource:
    proof: VerifiedFailedWorkspace
    decision: RecoveryDecision
    mode: str
    snapshot: WorkspaceSnapshot
    base_commit: str
    recovery_of: Optional[str]


def resolve_failed_source(conn, run_id, task, repo_root):
    """Choose exact original-baseline partial recovery or a fresh failed-source epoch."""
    try:
        row = conn.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is not None and row["state"] == "abandoned":
            from .failed_lineage import (
                FailedRetryLineageError,
                failed_retry_origin,
                load_abandoned_failed_retry_source,
            )

            try:
                if failed_retry_origin(conn, run_id, task, repo_root) is None:
                    raise FailedSelectionError("FAILED_SELECTION_NO_FAILED_ANCESTOR")
                source = load_abandoned_failed_retry_source(conn, run_id, task, repo_root)
            except FailedRetryLineageError as exc:
                raise FailedSelectionError(exc.code) from exc
            if source.decision.kind == "partial":
                return FailedClaimSource(
                    source.proof, source.decision, "partial", source.proof.baseline,
                    source.proof.original_base, source.proof.recovery_source_id,
                )
            if source.current.status_records:
                raise FailedSelectionError("FAILED_SELECTION_WORKSPACE_CHANGED")
            return FailedClaimSource(
                source.proof, source.decision, "unchanged", source.current,
                source.current.head, None,
            )
        proof = load_failed_recovery_source(conn, run_id, task, repo_root)
        decision = compare_verified_failed_workspace(proof, task)
        if not decision.recoverable or decision.kind not in {"partial", "unchanged"}:
            raise FailedSelectionError("FAILED_SELECTION_NOT_RECOVERABLE")
        if decision.kind == "partial":
            return FailedClaimSource(proof, decision, "partial", proof.baseline,
                                     proof.original_base, run_id)
        current = _capture(proof.baseline.repo_root, task, proof.baseline)
        current_decision = compare_failed_observation_current(proof, current, task)
        if (current_decision.kind != "unchanged" or current.status_records or
                current.head != proof.history.current_tip):
            raise FailedSelectionError("FAILED_SELECTION_WORKSPACE_CHANGED")
        return FailedClaimSource(proof, decision, "unchanged", current, current.head, None)
    except (FailedSelectionError, FailedRecoveryError):
        raise
    except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
        raise FailedSelectionError("FAILED_SELECTION_INVALID") from exc
