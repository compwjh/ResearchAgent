"""Build and verify a candidate tree with an isolated temporary Git index."""
import os
import subprocess
import tempfile
from pathlib import Path

from .git_expected_entries_io import GitExpectedEntriesError
from .git_index import read_index_snapshot
from .journal_fields import validate_object_id
from .journal_schema import validate_journal

_DROP_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


def _git(root, *args, index_file=None):
    env = os.environ.copy()
    for key in _DROP_ENV:
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if index_file is not None:
        env["GIT_INDEX_FILE"] = os.fspath(index_file)
    try:
        result = subprocess.run(["git", "-C", os.fspath(root), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env)
    except OSError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_FAILED") from exc
    if result.returncode:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_FAILED")
    return result.stdout


def _observation(snapshot):
    return {key: snapshot[key] for key in ("index_sha256", "committed_entries", "other_entries_sha256")}


def _tree_entries(root, tree, paths, oid_length):
    data = _git(root, "ls-tree", "-r", "-z", "--full-tree", tree)
    if data and not data.endswith(b"\0"):
        raise GitExpectedEntriesError("GIT_CANDIDATE_TREE_ENTRY_INVALID")
    wanted = {path.encode("utf-8"): path for path in paths}
    found = {}
    for record in data[:-1].split(b"\0") if data else ():
        try:
            header, raw_path = record.split(b"\t", 1)
            fields = header.decode("ascii").split(" ")
            if len(fields) != 3 or any(not field for field in fields):
                raise ValueError("header")
            mode, kind, oid = fields
            validate_object_id(oid, "candidate.object_id")
        except (UnicodeError, ValueError) as exc:
            raise GitExpectedEntriesError("GIT_CANDIDATE_TREE_ENTRY_INVALID") from exc
        expected_kind = "commit" if mode == "160000" else "blob"
        if (mode not in {"100644", "100755", "120000", "160000"} or kind != expected_kind or
                len(oid) != oid_length):
            raise GitExpectedEntriesError("GIT_CANDIDATE_TREE_ENTRY_INVALID")
        if raw_path in wanted:
            if raw_path in found:
                raise GitExpectedEntriesError("GIT_CANDIDATE_TREE_ENTRY_INVALID")
            found[raw_path] = {"mode": mode, "object_id": oid}
    return {path: found[raw] for raw, path in wanted.items() if raw in found}


def _verify_tree(root, tree, original_head, entries, committed_paths):
    actual_entries = _tree_entries(root, tree, committed_paths, len(original_head))
    for expected in entries:
        actual = actual_entries.get(expected["path"])
        target = (None if expected["mode"] is None else
                  {"mode": expected["mode"], "object_id": expected["object_id"]})
        if actual != target:
            raise GitExpectedEntriesError("GIT_CANDIDATE_ANCHOR_MISMATCH")
    changed = _git(root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "-z",
                   original_head, tree)
    if changed and not changed.endswith(b"\0"):
        raise GitExpectedEntriesError("GIT_CANDIDATE_DIFF_INVALID")
    try:
        paths = [item.decode("utf-8") for item in changed[:-1].split(b"\0")] if changed else []
    except UnicodeError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_DIFF_INVALID") from exc
    if len(paths) != len(set(paths)) or not set(paths) <= set(committed_paths):
        raise GitExpectedEntriesError("GIT_CANDIDATE_PATHS_MISMATCH")


def build_candidate_tree(worktree: Path, journal: dict) -> str:
    """Apply immutable target anchors with a temporary index after pinning the real one."""
    value = validate_journal(journal)
    if value["phase"] != "index_after_prepared":
        raise GitExpectedEntriesError("GIT_CANDIDATE_PHASE_INVALID")
    entries, paths = value["expected_git_entries"], value["committed_paths"]
    expected_index = [{"path": item["path"], "stage": 0, "mode": item["mode"],
                       "object_id": item["object_id"]} for item in entries if item["mode"] is not None]
    if value["index_after"]["committed_entries"] != expected_index:
        raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_ANCHOR_MISMATCH")
    root = Path(worktree).resolve(strict=True)
    head = value["original_head"]
    before = read_index_snapshot(root, paths, original_head=head)
    if (before["git_index_path"] != value["index_before"]["git_index_path"] or
            _observation(before) != value["index_observed_before"] or
            _git(root, "rev-parse", "HEAD").strip().decode("ascii") != head):
        raise GitExpectedEntriesError("GIT_CANDIDATE_BASE_CHANGED")
    base_paths = {item["path"] for item in value["index_before"]["committed_entries"]}
    with tempfile.TemporaryDirectory(prefix="sdd-candidate-") as directory:
        index_file = Path(directory) / "index"
        _git(root, "read-tree", head, index_file=index_file)
        for item in entries:
            path = item["path"]
            if item["mode"] is None:
                if path not in base_paths:
                    raise GitExpectedEntriesError("GIT_CANDIDATE_DELETE_UNTRACKED")
                _git(root, "update-index", "--force-remove", "--", path, index_file=index_file)
            else:
                spec = f"{item['mode']},{item['object_id']},{path}"
                _git(root, "update-index", "--add", "--cacheinfo", spec, index_file=index_file)
        tree = _git(root, "write-tree", index_file=index_file).strip().decode("ascii")
        validate_object_id(tree, "candidate.tree")
        _verify_tree(root, tree, head, entries, paths)
    after = read_index_snapshot(root, paths, original_head=head)
    if (_observation(after) != _observation(before) or
            _git(root, "rev-parse", "HEAD").strip().decode("ascii") != head):
        raise GitExpectedEntriesError("GIT_CANDIDATE_BASE_CHANGED")
    return tree
