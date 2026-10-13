"""Replay a prepared completion journal while the caller holds the common lock."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .atomic import contained
from .catalog_status import _gate_context, _metadata
from .completion_journal import read_journal, recover_expected_documents, write_journal
from .documents import parse_task
from .git_candidate import create_candidate_commit
from .git_candidate_cas import _branch_ref, reconcile_candidate_ref
from .git_index_lock import acquire_owned_index_lock
from .git_reconciliation_index import (
    install_reconciled_index,
    prepare_reconciliation_index,
    write_owned_index_image,
)
from .journal_schema import validate_journal
from .ledger_finalize import _instant, _preflight_active, _target_task_status, finalize_ledger


class CompletionLifecycleError(ValueError):
    """A durable completion journal cannot be safely replayed."""


def _server_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bind_active(conn, journal, main, roots, task_branch):
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (journal["run_id"],)).fetchone()
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (journal["task_id"],)).fetchone()
    if run is None or row is None:
        raise CompletionLifecycleError("COMPLETION_BINDING_MISSING")
    meta = _metadata(dict(row))
    try:
        worktree = contained(main, meta["worktree"]["path"]).resolve(strict=True)
        directory = contained(worktree, "docs/sdd/plans/" + meta["spec_id"])
        files = sorted(directory.glob("task-{}-*.md".format(journal["task_id"][-2:])))
        task = parse_task(files[0]) if len(files) == 1 else None
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise CompletionLifecycleError("COMPLETION_TASK_BINDING_INVALID") from exc
    if (worktree not in roots or task is None or task.task_hash != journal["task_hash"] or
            task.prompt_hash != journal["prompt_hash"] or
            {k: v for k, v in task.metadata.items() if k != "status"} !=
            {k: v for k, v in meta.items() if k != "status"}):
        raise CompletionLifecycleError("COMPLETION_TASK_BINDING_MISMATCH")
    if (run["task_id"] != journal["task_id"] or run["task_hash"] != journal["task_hash"] or
            run["prompt_hash"] != journal["prompt_hash"] or run["base_commit"] != journal["base_commit"] or
            run["worktree"] != meta["worktree"]["path"] or
            run["branch"] != meta["worktree"]["branch"] or task_branch != run["branch"]):
        raise CompletionLifecycleError("COMPLETION_RUN_BINDING_MISMATCH")
    target = _target_task_status(conn, run, meta, journal["terminal_outcome"],
                                 transaction_required=False)
    if task.metadata["status"] not in {row["status"], target}:
        raise CompletionLifecycleError("COMPLETION_TASK_STATUS_MISMATCH")
    return worktree, run


def run_completion_journal(conn, journal_path: Path, task_branch: str, now: str) -> dict:
    """Resume only an existing valid journal; caller holds the common maintenance lock."""
    _instant(now, "now")
    main, roots = _gate_context(conn)
    path = Path(journal_path)
    run_id = path.parent.name
    try:
        canonical_id = str(uuid.UUID(run_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CompletionLifecycleError("COMPLETION_JOURNAL_PATH_INVALID") from exc
    expected = main / ".sdd/runtime/runs" / canonical_id / "completion.json"
    if canonical_id != run_id or path.absolute() != expected:
        raise CompletionLifecycleError("COMPLETION_JOURNAL_PATH_INVALID")
    journal = validate_journal(read_journal(path))
    if journal["run_id"] != run_id:
        raise CompletionLifecycleError("COMPLETION_RUN_MISMATCH")
    if journal["phase"] == "complete":
        return finalize_ledger(conn, path, now=_server_now())
    if journal["phase"] == "ledger_finalizing":
        state = conn.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if state is not None and state["state"] not in {"claimed", "running"}:
            return finalize_ledger(conn, path, now=_server_now())

    worktree, _ = _bind_active(conn, journal, main, roots, task_branch)
    while True:
        journal = validate_journal(read_journal(path))
        if journal["phase"] == "index_reconciled":
            _preflight_active(conn, journal, _server_now())
            install_reconciled_index(worktree, path, task_branch=task_branch)
            return finalize_ledger(conn, path, now=_server_now())
        if journal["phase"] == "ledger_finalizing":
            _preflight_active(conn, journal, _server_now())
            install_reconciled_index(worktree, path, task_branch=task_branch)
            return finalize_ledger(conn, path, now=_server_now())
        _branch_ref(worktree, journal["task_id"], task_branch)
        _preflight_active(conn, journal, _server_now())
        phase, stage = journal["phase"], journal["index_recovery_stage"]
        if phase in {"prepared", "docs_writing"}:
            recover_expected_documents(worktree, path)
        elif phase in {"docs_written", "index_locking"}:
            acquire_owned_index_lock(worktree, path)
            if phase == "index_locking":
                prepare_reconciliation_index(worktree, path)
        elif phase == "index_after_prepared" and stage == "reconciliation_index_durable":
            write_owned_index_image(worktree, path)
        elif phase == "index_after_prepared" and stage == "lock_index_durable":
            candidate = create_candidate_commit(worktree, journal)
            write_journal(path, dict(journal, phase="commit_pending",
                                     candidate_commit_hash=candidate), previous_phase=phase)
        elif phase == "commit_pending":
            candidate = reconcile_candidate_ref(worktree, journal, task_branch=task_branch)
            if candidate != journal["candidate_commit_hash"]:
                raise CompletionLifecycleError("COMPLETION_CANDIDATE_MISMATCH")
            write_journal(path, dict(journal, phase="committed", index_recovery_stage="ref_committed"),
                          previous_phase=phase)
        elif phase == "committed":
            install_reconciled_index(worktree, path, task_branch=task_branch)
        else:
            raise CompletionLifecycleError("COMPLETION_PHASE_INVALID")
