"""Durably acquire the run-owned marker at Git's standard index.lock path."""
import secrets
from pathlib import Path

from .completion_journal import read_journal, write_journal
from .git_index import read_index_snapshot
from .git_index_lock_primitives import (
    GitIndexLockError,
    create_marker_temp,
    publish_marker_lock,
)
from .journal_fields import JournalError


def _snapshot(worktree: Path, journal: dict) -> dict:
    snapshot = read_index_snapshot(
        worktree, journal["committed_paths"], original_head=journal["original_head"]
    )
    before = journal["index_before"]
    if (snapshot["git_index_path"] != before["git_index_path"] or
            snapshot["committed_entries"] != before["committed_entries"]):
        raise GitIndexLockError("GIT_INDEX_TARGETS_CHANGED")
    return snapshot


def _observation(snapshot: dict) -> dict:
    return {key: snapshot[key] for key in
            ("index_sha256", "committed_entries", "other_entries_sha256")}


def _save(path: Path, journal: dict, **changes) -> dict:
    updated = dict(journal, **changes)
    write_journal(path, updated, previous_phase=journal["phase"])
    return read_journal(path)


def _marker(journal: dict) -> dict:
    return {"schema": "sdd-index-lock/v1", "run_id": journal["run_id"],
            "index_lock_owner_token": journal["index_lock_owner_token"],
            "index_before_sha256": journal["index_before"]["index_sha256"]}


def _new_temp(path: Path, journal: dict) -> dict:
    return _save(path, journal, index_lock_temp_path=".sdd-index-lock-" + secrets.token_hex(16))


def acquire_owned_index_lock(worktree: Path, journal_path: Path) -> dict:
    """Acquire or replay the durable lock marker, retaining the observed index."""
    path = Path(journal_path)
    journal = read_journal(path)
    if journal["phase"] == "docs_written":
        journal = _save(path, journal, phase="index_locking")
    elif journal["phase"] != "index_locking":
        raise JournalError("JOURNAL_LOCK_PHASE_INVALID")

    snapshot = _snapshot(worktree, journal)
    index = Path(snapshot["git_index_path"])
    temp = journal["index_lock_temp_path"]
    marker = _marker(journal)
    stage = journal["index_recovery_stage"]

    if stage == "not_acquired":
        if temp is None:
            journal = _new_temp(path, journal)
            temp = journal["index_lock_temp_path"]
        try:
            create_marker_temp(index, temp, marker)
        except GitIndexLockError as exc:
            if str(exc) not in {"GIT_LOCK_MARKER_MISMATCH", "GIT_LOCK_UNSAFE"}:
                raise
            journal = _new_temp(path, journal)
            temp = journal["index_lock_temp_path"]
            create_marker_temp(index, temp, marker)
        journal = _save(path, journal, index_recovery_stage="marker_temp_durable")
        stage = journal["index_recovery_stage"]
    elif stage == "marker_temp_durable":
        if journal["index_lock_identity"] is not None:
            raise JournalError("JOURNAL_LOCK_IDENTITY_EARLY")
        try:
            identity = publish_marker_lock(index, temp, marker)
        except GitIndexLockError as exc:
            if str(exc) != "GIT_LOCK_MARKER_MISSING":
                raise
            create_marker_temp(index, temp, marker)
            identity = publish_marker_lock(index, temp, marker)
        observed = _observation(_snapshot(worktree, journal))
        return _save(path, journal, index_lock_identity=identity,
                     index_observed_before=observed, index_recovery_stage="marker_durable")
    elif stage == "marker_durable":
        identity = journal["index_lock_identity"]
        if identity is None or journal["index_observed_before"] is None:
            raise JournalError("JOURNAL_LOCK_OBSERVATION_MISSING")
        publish_marker_lock(index, temp, marker, identity=identity)
        observed = _observation(_snapshot(worktree, journal))
        if observed != journal["index_observed_before"]:
            raise GitIndexLockError("GIT_INDEX_OBSERVATION_CHANGED")
        return journal
    else:
        raise JournalError("JOURNAL_LOCK_STAGE_INVALID")

    if stage != "marker_temp_durable":
        raise JournalError("JOURNAL_LOCK_TEMP_NOT_DURABLE")
    identity = publish_marker_lock(index, temp, marker)
    observed = _observation(_snapshot(worktree, journal))
    return _save(path, journal, index_lock_identity=identity,
                 index_observed_before=observed, index_recovery_stage="marker_durable")
