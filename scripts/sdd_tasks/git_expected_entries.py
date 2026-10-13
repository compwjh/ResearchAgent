"""Freeze ordered Git blob and mode anchors before a completion journal."""
import hashlib
from pathlib import Path
from typing import Sequence

from .git_expected_entries_io import (
    GitExpectedEntriesError,
    blob_oid,
    check_attributes,
    config,
    mode,
    source,
)
from .git_index import read_index_snapshot
from .journal_fields import validate_path, validate_paths


def capture_expected_git_entries(
    worktree: Path, committed_paths: Sequence[str], *, expected_docs: Sequence[dict], original_head: str
) -> list[dict]:
    """Capture raw post-document blobs, rejecting transforms and concurrent drift."""
    if isinstance(committed_paths, (str, bytes)) or not isinstance(committed_paths, Sequence):
        raise GitExpectedEntriesError("GIT_EXPECTED_PATHS_INVALID")
    paths = validate_paths(list(committed_paths), "committed_paths")
    try:
        ordered = sorted(paths, key=lambda path: path.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise GitExpectedEntriesError("GIT_EXPECTED_PATHS_INVALID") from exc
    root = Path(worktree).resolve(strict=True)
    before = read_index_snapshot(root, paths, original_head=original_head)
    old_modes = {item["path"]: item["mode"] for item in before["committed_entries"]}
    if isinstance(expected_docs, (str, bytes)) or not isinstance(expected_docs, Sequence):
        raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_INVALID")
    committed = set(paths)
    docs = {}
    for document in expected_docs:
        if not isinstance(document, dict) or not isinstance(document.get("content"), str):
            raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_INVALID")
        path = validate_path(document.get("path"), "expected_git_entries.path")
        if path in docs or path not in committed:
            raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_INVALID")
        docs[path] = document["content"]
    filemode = config(root, "core.filemode", True)
    if config(root, "core.autocrlf", False):
        raise GitExpectedEntriesError("GIT_EXPECTED_CONVERSION_ACTIVE")
    check_attributes(root, ordered)
    entries, observed = [], {}
    for path in ordered:
        kind, fs_mode, raw, file_stamp = source(root, path)
        observed[path] = (kind, fs_mode, file_stamp,
                          hashlib.sha256(raw).digest() if raw is not None else None)
        old_mode = old_modes.get(path)
        if path in docs:
            if kind == "symlink":
                raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_SYMLINK")
            try:
                payload = docs[path].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise GitExpectedEntriesError("GIT_EXPECTED_DOCUMENT_INVALID") from exc
            item_mode, oid = mode(kind or "missing", fs_mode, old_mode, filemode), blob_oid(
                root, payload, len(original_head)
            )
        elif kind is None:
            if old_mode is None:
                raise GitExpectedEntriesError("GIT_EXPECTED_NEW_PATH_MISSING")
            item_mode, oid = None, None
        else:
            item_mode, oid = mode(kind, fs_mode, old_mode, filemode), blob_oid(
                root, raw, len(original_head)
            )
        entries.append({"path": path, "mode": item_mode, "object_id": oid})
    for path, previous in observed.items():
        kind, fs_mode, raw, file_stamp = source(root, path)
        current = (kind, fs_mode, file_stamp, hashlib.sha256(raw).digest() if raw is not None else None)
        if current != previous:
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED")
    check_attributes(root, ordered)
    if config(root, "core.filemode", True) != filemode or config(root, "core.autocrlf", False):
        raise GitExpectedEntriesError("GIT_EXPECTED_CONFIG_CHANGED")
    if read_index_snapshot(root, paths, original_head=original_head) != before:
        raise GitExpectedEntriesError("GIT_EXPECTED_INDEX_OR_HEAD_CHANGED")
    return entries
