"""Pure validators for nested Task06 completion-journal fields."""
import hashlib
import re
from pathlib import PurePosixPath, PureWindowsPath

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class JournalError(ValueError):
    """A completion-journal field is malformed or inconsistent."""


def _bad(field):
    raise JournalError("JOURNAL_INVALID: " + field)


def _object(value, fields, name):
    if not isinstance(value, dict) or set(value) != fields:
        _bad(name + ".fields")
    return value


def require_text(value, name, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        _bad(name + ".string")
    return value


def validate_hash(value, name, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _bad(name + ".sha256")


def validate_object_id(value, name):
    if not isinstance(value, str) or not _OID.fullmatch(value):
        _bad(name + ".object_id")


def validate_path(value, name):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _bad(name + ".path")
    parts, windows = value.split("/"), PureWindowsPath(value)
    if (PurePosixPath(value).is_absolute() or windows.is_absolute() or windows.drive or
            any(part in ("", ".", "..") or any(c in part for c in '*?[]:"<>|') for part in parts)):
        _bad(name + ".path")
    return value


def validate_paths(values, name):
    if not isinstance(values, list):
        _bad(name + ".array")
    paths = [validate_path(value, name) for value in values]
    if len(paths) != len(set(paths)):
        _bad(name + ".duplicate")
    return paths


def validate_owner(value):
    owner = _object(value, {"executor_id", "host_id", "pid", "process_started_at", "token"}, "owner")
    for key in ("executor_id", "host_id", "process_started_at", "token"):
        require_text(owner[key], "owner." + key)
    if type(owner["pid"]) is not int or owner["pid"] < 1:
        _bad("owner.pid")
    return owner


def validate_index_entries(values, name):
    if not isinstance(values, list):
        _bad(name + ".array")
    seen = set()
    for entry in values:
        _object(entry, {"path", "stage", "mode", "object_id"}, name + "[]")
        path = validate_path(entry["path"], name + ".path")
        if type(entry["stage"]) is not int or entry["stage"] not in range(4):
            _bad(name + ".stage")
        if not isinstance(entry["mode"], str) or entry["mode"] not in {"100644", "100755", "120000", "160000"}:
            _bad(name + ".mode")
        validate_object_id(entry["object_id"], name + ".object_id")
        if (path, entry["stage"]) in seen:
            _bad(name + ".duplicate")
        seen.add((path, entry["stage"]))


def validate_expected_git_entries(values, committed_paths, *, oid_length):
    if not isinstance(values, list):
        _bad("expected_git_entries.array")
    paths = []
    for entry in values:
        _object(entry, {"path", "mode", "object_id"}, "expected_git_entries[]")
        paths.append(validate_path(entry["path"], "expected_git_entries.path"))
        mode, object_id = entry["mode"], entry["object_id"]
        if mode is None and object_id is None:
            continue
        if not isinstance(mode, str) or mode not in {"100644", "100755", "120000"}:
            _bad("expected_git_entries.mode")
        validate_object_id(object_id, "expected_git_entries.object_id")
        if len(object_id) != oid_length:
            _bad("expected_git_entries.object_id_format")
    try:
        ordered = sorted(paths, key=lambda path: path.encode("utf-8"))
    except UnicodeEncodeError:
        _bad("expected_git_entries.path")
    if paths != ordered or len(paths) != len(committed_paths) or set(paths) != set(committed_paths):
        _bad("expected_git_entries.paths")


def validate_index_snapshot(value, name, *, initial=False):
    fields = {"index_sha256", "committed_entries", "other_entries_sha256"}
    if initial:
        fields.add("git_index_path")
    snapshot = _object(value, fields, name)
    if initial:
        git_path = require_text(snapshot["git_index_path"], name + ".git_index_path")
        if (not git_path.startswith("/") or "\\" in git_path or "\x00" in git_path or
                any(part in ("", ".", "..") for part in git_path[1:].split("/"))):
            _bad(name + ".git_index_path")
    validate_hash(snapshot["index_sha256"], name + ".index_sha256")
    validate_hash(snapshot["other_entries_sha256"], name + ".other_entries_sha256")
    validate_index_entries(snapshot["committed_entries"], name + ".committed_entries")
    return snapshot


def validate_changed_paths(values, allowed_paths):
    if not isinstance(values, list):
        _bad("changed_paths.array")
    allowed = validate_paths(allowed_paths, "allowed_paths")
    changed = set()
    for item in values:
        _object(item, {"path", "before_sha256", "after_sha256"}, "changed_paths[]")
        path = validate_path(item["path"], "changed_paths.path")
        if path in changed or not any(path == root or path.startswith(root + "/") for root in allowed):
            _bad("changed_paths.binding")
        changed.add(path)
        validate_hash(item["before_sha256"], "changed_paths.before", nullable=True)
        validate_hash(item["after_sha256"], "changed_paths.after", nullable=True)
        if item["before_sha256"] is None and item["after_sha256"] is None:
            _bad("changed_paths.hashes")
    return changed


def validate_expected_docs(values):
    if not isinstance(values, list):
        _bad("expected_docs.array")
    paths = set()
    for item in values:
        _object(item, {"path", "before_sha256", "content", "after_sha256"}, "expected_docs[]")
        path = validate_path(item["path"], "expected_docs.path")
        if path in paths:
            _bad("expected_docs.duplicate")
        paths.add(path)
        validate_hash(item["before_sha256"], "expected_docs.before", nullable=True)
        content = require_text(item["content"], "expected_docs.content", empty=True)
        validate_hash(item["after_sha256"], "expected_docs.after")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != item["after_sha256"]:
            _bad("expected_docs.content_hash")
    return paths


def validate_lock_temp_path(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or
            value in {".", ".."}):
        _bad("index_lock_temp_path")


def validate_lock_identity(value):
    identity = _object(value, {"device", "inode"}, "index_lock_identity")
    if any(type(identity[key]) is not int or identity[key] < 0 for key in identity):
        _bad("index_lock_identity")
    return identity
