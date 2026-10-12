"""Validate complete Task06 journal envelopes and their frozen phase order."""
import re
import uuid

from .journal_fields import (
    JournalError,
    require_text,
    validate_changed_paths,
    validate_expected_docs,
    validate_hash,
    validate_index_snapshot,
    validate_lock_identity,
    validate_lock_temp_path,
    validate_object_id,
    validate_owner,
    validate_paths,
)
from .result_schema import validate_summary_result

SCHEMA = "sdd-completion-journal/v1"
PHASES = ("prepared", "docs_writing", "docs_written", "index_locking", "index_after_prepared",
          "commit_pending", "committed", "index_reconciled", "ledger_finalizing", "complete")
INDEX_STAGES = ("not_acquired", "marker_temp_durable", "marker_durable", "reconciliation_index_durable",
                "lock_index_durable", "ref_committed", "index_installed")
FIELDS = {"schema", "run_id", "task_id", "owner", "base_commit", "original_head", "task_hash",
          "prompt_hash", "allowed_paths", "changed_paths", "expected_docs", "expected_result",
          "terminal_outcome", "committed_paths", "staged_paths", "index_before",
          "index_observed_before", "index_after", "index_lock_owner_token", "index_lock_temp_path",
          "index_lock_identity", "index_recovery_stage", "candidate_commit_hash", "commit_message", "phase"}
_STAGE_MIN_PHASE = (0, 3, 3, 4, 4, 6, 6)


def _bad(field):
    raise JournalError("JOURNAL_INVALID: " + field)


def _object(value, fields, name):
    if not isinstance(value, dict) or set(value) != fields:
        _bad(name + ".fields")
    return value


def validate_journal(data: object) -> dict:
    """Reject unknown/missing fields and invalid phase-specific nullables."""
    v = _object(data, FIELDS, "root")
    if v["schema"] != SCHEMA:
        _bad("schema")
    try:
        run_id = str(uuid.UUID(require_text(v["run_id"], "run_id")))
    except ValueError as exc:
        raise JournalError("JOURNAL_INVALID: run_id") from exc
    task_id = require_text(v["task_id"], "task_id")
    if run_id != v["run_id"] or not re.fullmatch(r"spec-\d{3}-task-\d{2}", task_id):
        _bad("run_or_task_id")
    result = v["expected_result"]
    try:
        result = validate_summary_result(result)
    except (TypeError, ValueError) as exc:
        raise JournalError("JOURNAL_INVALID: expected_result") from exc
    if (result["run_id"], result["task_id"], result["task_hash"], result["prompt_hash"], result["outcome"]) != (
            run_id, task_id, v["task_hash"], v["prompt_hash"], v["terminal_outcome"]):
        _bad("result_binding")
    validate_owner(v["owner"])
    for key in ("base_commit", "original_head"):
        validate_object_id(v[key], key)
    validate_hash(v["task_hash"], "task_hash")
    validate_hash(v["prompt_hash"], "prompt_hash")
    changed = validate_changed_paths(v["changed_paths"], v["allowed_paths"])
    docs = validate_expected_docs(v["expected_docs"])
    committed = validate_paths(v["committed_paths"], "committed_paths")
    staged = validate_paths(v["staged_paths"], "staged_paths")
    if set(committed) != set(staged) or not set(committed) <= changed | docs:
        _bad("committed_paths.binding")
    validate_index_snapshot(v["index_before"], "index_before", initial=True)
    observed, after = v["index_observed_before"], v["index_after"]
    if observed is not None:
        validate_index_snapshot(observed, "index_observed_before")
    if after is not None:
        validate_index_snapshot(after, "index_after")
    validate_hash(v["index_lock_owner_token"], "index_lock_owner_token")
    temp, identity = v["index_lock_temp_path"], v["index_lock_identity"]
    if temp is not None:
        validate_lock_temp_path(temp)
    if identity is not None:
        validate_lock_identity(identity)
    phase, stage = v["phase"], v["index_recovery_stage"]
    if phase not in PHASES or stage not in INDEX_STAGES:
        _bad("phase_or_index_recovery_stage")
    pn, sn = PHASES.index(phase), INDEX_STAGES.index(stage)
    candidate = v["candidate_commit_hash"]
    if candidate is not None:
        validate_object_id(candidate, "candidate_commit_hash")
    if pn < 3 and (stage != "not_acquired" or observed is not None or after is not None or temp is not None or identity is not None or candidate is not None):
        _bad("premature_index_state")
    if pn == 3 and (after is not None or candidate is not None):
        _bad("premature_index_state")
    if pn >= 4 and (observed is None or after is None):
        _bad("index_snapshots_required")
    if pn < 5 and candidate is not None:
        _bad("premature_candidate_hash")
    if pn >= 5 and candidate is None:
        _bad("candidate_commit_hash_required")
    if sn >= 1 and temp is None:
        _bad("index_lock_temp_path_required")
    if sn >= 2 and identity is None:
        _bad("index_lock_identity_required")
    if pn < _STAGE_MIN_PHASE[sn]:
        _bad("index_stage_phase_mismatch")
    if ((pn == 3 and sn > 2) or (pn == 4 and sn not in {3, 4}) or
            (pn == 5 and sn != 4) or (pn == 6 and sn not in {5, 6}) or (pn >= 7 and sn != 6)):
        _bad("index_stage_phase_mismatch")
    if pn >= 7 and stage != "index_installed":
        _bad("index_installed_required")
    require_text(v["commit_message"], "commit_message")
    return v


def validate_phase_transition(previous: str, current: str) -> None:
    """Allow an idempotent phase update or exactly one forward phase."""
    if (previous not in PHASES or current not in PHASES or
            PHASES.index(current) not in {PHASES.index(previous), PHASES.index(previous) + 1}):
        raise JournalError("JOURNAL_PHASE_REGRESSION")
