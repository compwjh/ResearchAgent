"""Verify or write Git blobs proven equal to immutable journal anchors."""
import hashlib
from pathlib import Path

from .completion_journal import _document_hash
from .git_expected_entries import capture_expected_git_entries
from .git_expected_entries_io import (
    GitExpectedEntriesError,
    blob_oid,
    check_attributes,
    config,
    git,
    mode,
    source,
)
from .git_index import read_index_snapshot
from .journal_fields import validate_paths
from .journal_schema import validate_journal


def _observation(snapshot):
    return {key: snapshot[key] for key in ("index_sha256", "committed_entries", "other_entries_sha256")}


def _check_base(root, journal):
    head = journal["original_head"]
    snapshot = read_index_snapshot(root, journal["committed_paths"], original_head=head)
    current_head = git(root, "rev-parse", "HEAD").strip()
    if (snapshot["git_index_path"] != journal["index_before"]["git_index_path"] or
            _observation(snapshot) != journal["index_observed_before"] or current_head != head.encode("ascii")):
        raise GitExpectedEntriesError("GIT_CANDIDATE_BASE_CHANGED")


def _check_docs(root, documents):
    for document in documents:
        try:
            actual = _document_hash(root, document["path"])
        except ValueError as exc:
            raise GitExpectedEntriesError("GIT_CANDIDATE_DOCUMENT_UNSAFE") from exc
        if actual != document["after_sha256"]:
            raise GitExpectedEntriesError("GIT_CANDIDATE_DOCUMENT_CHANGED")


def _check_entries(root, journal):
    entries = capture_expected_git_entries(
        root, journal["committed_paths"], expected_docs=journal["expected_docs"],
        original_head=journal["original_head"]
    )
    if entries != journal["expected_git_entries"]:
        raise GitExpectedEntriesError("GIT_CANDIDATE_ANCHOR_MISMATCH")


def store_verified_blobs(worktree: Path, journal: dict) -> None:
    """Write anchored blobs only; caller proves owned-lock token and identity."""
    value = validate_journal(journal)
    state = (value["phase"], value["index_recovery_stage"])
    if state not in {
        ("index_locking", "marker_durable"),
        ("index_after_prepared", "reconciliation_index_durable"),
        ("index_after_prepared", "lock_index_durable"),
    } or value["index_observed_before"] is None:
        raise GitExpectedEntriesError("GIT_CANDIDATE_PHASE_INVALID")
    root = Path(worktree).resolve(strict=True)
    documents = value["expected_docs"]
    docs_by_path = {item["path"]: item["content"] for item in documents}
    _check_base(root, value)
    _check_docs(root, documents)
    _check_entries(root, value)
    for item in value["expected_git_entries"]:
        if item["mode"] is None:
            continue
        path = item["path"]
        if path in docs_by_path:
            try:
                payload = docs_by_path[path].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise GitExpectedEntriesError("GIT_CANDIDATE_DOCUMENT_INVALID") from exc
        else:
            kind, _mode, payload, _stamp = source(root, path)
            if kind is None or payload is None:
                raise GitExpectedEntriesError("GIT_CANDIDATE_SOURCE_MISSING")
        if blob_oid(root, payload, len(value["original_head"])) != item["object_id"]:
            raise GitExpectedEntriesError("GIT_CANDIDATE_ANCHOR_MISMATCH")
        try:
            stored = git(root, "hash-object", "-w", "--stdin", input_data=payload).strip().decode("ascii")
        except UnicodeError as exc:
            raise GitExpectedEntriesError("GIT_CANDIDATE_OBJECT_ID_INVALID") from exc
        if stored != item["object_id"]:
            raise GitExpectedEntriesError("GIT_CANDIDATE_ANCHOR_MISMATCH")
    _check_docs(root, documents)
    _check_entries(root, value)
    _check_base(root, value)


def check_source_anchors(worktree: Path, journal: dict) -> None:
    """Verify anchored bytes and modes without assuming HEAD or the index baseline."""
    value = validate_journal(journal)
    root = Path(worktree).resolve(strict=True)
    paths = validate_paths(value["committed_paths"], "committed_paths")
    ordered = sorted(paths, key=lambda path: path.encode("utf-8"))
    old_modes = {item["path"]: item["mode"] for item in value["index_before"]["committed_entries"]}
    documents = value["expected_docs"]
    docs_by_path = {item["path"]: item["content"] for item in documents}
    filemode = config(root, "core.filemode", True)
    if config(root, "core.autocrlf", False):
        raise GitExpectedEntriesError("GIT_EXPECTED_CONVERSION_ACTIVE")
    check_attributes(root, ordered)
    _check_docs(root, documents)
    entries, states = [], {}
    for path in ordered:
        kind, fs_mode, raw, file_stamp = source(root, path)
        states[path] = (kind, fs_mode, file_stamp,
                        hashlib.sha256(raw).digest() if raw is not None else None)
        old_mode = old_modes.get(path)
        if path in docs_by_path:
            if kind == "symlink":
                raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_SYMLINK")
            try:
                payload = docs_by_path[path].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_INVALID") from exc
            item_mode = mode(kind or "missing", fs_mode, old_mode, filemode)
            oid = blob_oid(root, payload, len(value["original_head"]))
        elif kind is None:
            if old_mode is None:
                raise GitExpectedEntriesError("GIT_EXPECTED_NEW_PATH_MISSING")
            item_mode, oid = None, None
        else:
            item_mode = mode(kind, fs_mode, old_mode, filemode)
            oid = blob_oid(root, raw, len(value["original_head"]))
        entries.append({"path": path, "mode": item_mode, "object_id": oid})
    for path, previous in states.items():
        kind, fs_mode, raw, file_stamp = source(root, path)
        current = (kind, fs_mode, file_stamp,
                   hashlib.sha256(raw).digest() if raw is not None else None)
        if current != previous:
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED")
    check_attributes(root, ordered)
    if config(root, "core.filemode", True) != filemode or config(root, "core.autocrlf", False):
        raise GitExpectedEntriesError("GIT_EXPECTED_CONFIG_CHANGED")
    _check_docs(root, documents)
    if entries != value["expected_git_entries"]:
        raise GitExpectedEntriesError("GIT_CANDIDATE_ANCHOR_MISMATCH")
