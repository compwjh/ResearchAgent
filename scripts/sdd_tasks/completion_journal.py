"""Strict durable JSON I/O and same-run update checks for completion journals."""
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Optional

from . import atomic
from .journal_fields import JournalError
from .journal_schema import INDEX_STAGES, validate_journal, validate_phase_transition

_MUTABLE = {"phase", "index_observed_before", "index_after", "index_lock_temp_path",
            "index_lock_identity", "index_recovery_stage", "candidate_commit_hash"}
_ONE_TIME = {"index_observed_before", "index_after", "index_lock_identity"}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise JournalError("JOURNAL_INVALID: duplicate_key")
        result[key] = value
    return result


def _constant(_value):
    raise JournalError("JOURNAL_INVALID: invalid_json_constant")


def _load(path: Path) -> dict:
    try:
        raw = atomic.read_text(Path(path))
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except FileNotFoundError:
        raise
    except JournalError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise JournalError("JOURNAL_READ_INVALID") from exc
    return validate_journal(value)


def read_journal(path: Path) -> dict:
    """Read a regular UTF-8 journal without following symlinks."""
    try:
        return _load(Path(path))
    except FileNotFoundError as exc:
        raise JournalError("JOURNAL_NOT_FOUND") from exc


def _check_update(old: dict, new: dict) -> None:
    validate_phase_transition(old["phase"], new["phase"])
    for key in old.keys() - _MUTABLE:
        if old[key] != new[key]:
            raise JournalError("JOURNAL_IMMUTABLE_FIELD_CHANGED: " + key)
    for key in _ONE_TIME:
        if old[key] is not None and old[key] != new[key]:
            raise JournalError("JOURNAL_FIELD_ALREADY_SET: " + key)
    if old["candidate_commit_hash"] is not None and old["candidate_commit_hash"] != new["candidate_commit_hash"]:
        raise JournalError("JOURNAL_CANDIDATE_HASH_CHANGED")
    if old["candidate_commit_hash"] is None and new["candidate_commit_hash"] is not None and new["phase"] != "commit_pending":
        raise JournalError("JOURNAL_CANDIDATE_PHASE_INVALID")
    if (old["index_lock_temp_path"] != new["index_lock_temp_path"] and
            (new["phase"] != "index_locking" or old["index_lock_identity"] is not None or
             new["index_lock_temp_path"] is None)):
        raise JournalError("JOURNAL_LOCK_TEMP_CHANGED")
    before, after = INDEX_STAGES.index(old["index_recovery_stage"]), INDEX_STAGES.index(new["index_recovery_stage"])
    if after not in {before, before + 1}:
        raise JournalError("JOURNAL_INDEX_STAGE_REGRESSION")


def write_journal(
    path: Path, data: dict, *, previous_phase: Optional[str] = None
) -> None:
    """Durably write a validated journal; callers serialize through maintenance_lock."""
    target, value = Path(path), validate_journal(data)
    try:
        current = _load(target)
    except FileNotFoundError:
        current = None
    if current is None:
        if previous_phase is not None or value["phase"] != "prepared":
            raise JournalError("JOURNAL_INITIAL_PHASE_INVALID")
    else:
        if previous_phase is not None and previous_phase != current["phase"]:
            raise JournalError("JOURNAL_PREVIOUS_PHASE_MISMATCH")
        _check_update(current, value)
    content = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    atomic.atomic_write(target, content)


def _document_hash(root: Path, relative: str):
    try:
        target = atomic.contained(root, relative)
        parent = atomic._open_directory(target.parent)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise JournalError("JOURNAL_DOCUMENT_UNSAFE") from exc
    try:
        try:
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                         dir_fd=parent)
        except FileNotFoundError:
            return None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise JournalError("JOURNAL_DOCUMENT_UNSAFE")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    return digest.hexdigest()
                digest.update(chunk)
        finally:
            os.close(fd)
    except JournalError:
        raise
    except OSError as exc:
        raise JournalError("JOURNAL_DOCUMENT_UNREADABLE") from exc
    finally:
        os.close(parent)


def _ensure_document_parent(root: Path, relative: str) -> None:
    try:
        base = Path(root).resolve(strict=True)
        target = atomic.contained(base, relative)
    except (OSError, ValueError) as exc:
        raise JournalError("JOURNAL_DOCUMENT_UNSAFE") from exc
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise JournalError("JOURNAL_DOCUMENT_UNSAFE")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    current = -1
    try:
        current = atomic._open_directory(base)
        for part in target.relative_to(base).parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=current)
                os.fsync(current)
                child = os.open(part, flags, dir_fd=current)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise JournalError("JOURNAL_DOCUMENT_UNSAFE")
            os.close(current)
            current = child
    except JournalError:
        raise
    except (OSError, ValueError) as exc:
        raise JournalError("JOURNAL_DOCUMENT_PARENT_CREATE_FAILED") from exc
    finally:
        if current >= 0:
            os.close(current)


def recover_expected_documents(repo_root: Path, journal_path: Path) -> dict:
    """Replay journaled document contents after validating every before/after hash."""
    try:
        root = Path(repo_root).resolve(strict=True)
        if not root.is_dir():
            raise JournalError("JOURNAL_WORKTREE_INVALID")
    except (OSError, ValueError) as exc:
        raise JournalError("JOURNAL_WORKTREE_INVALID") from exc
    journal = read_journal(Path(journal_path))
    phase = journal["phase"]
    if phase == "prepared":
        journal = dict(journal, phase="docs_writing")
        write_journal(journal_path, journal, previous_phase="prepared")
        journal = read_journal(journal_path)
        phase = journal["phase"]
    if phase not in {"docs_writing", "docs_written"}:
        raise JournalError("JOURNAL_DOCUMENT_PHASE_INVALID")

    documents = journal["expected_docs"]
    observed = {doc["path"]: _document_hash(root, doc["path"]) for doc in documents}
    for doc in documents:
        current = observed[doc["path"]]
        if current not in {doc["before_sha256"], doc["after_sha256"]}:
            raise JournalError("JOURNAL_DOCUMENT_STATE_UNKNOWN")
    if phase == "docs_written":
        if any(observed[doc["path"]] != doc["after_sha256"] for doc in documents):
            raise JournalError("JOURNAL_DOCUMENT_AFTER_HASH_MISMATCH")
        return journal

    for doc in documents:
        path = doc["path"]
        current = _document_hash(root, path)
        if current == doc["after_sha256"]:
            continue
        if current != doc["before_sha256"]:
            raise JournalError("JOURNAL_DOCUMENT_STATE_CHANGED")
        _ensure_document_parent(root, path)
        atomic.atomic_write(atomic.contained(root, path), doc["content"].encode("utf-8"))

    if any(_document_hash(root, doc["path"]) != doc["after_sha256"] for doc in documents):
        raise JournalError("JOURNAL_DOCUMENT_AFTER_HASH_MISMATCH")
    completed = dict(journal, phase="docs_written")
    write_journal(journal_path, completed, previous_phase="docs_writing")
    return read_journal(journal_path)
