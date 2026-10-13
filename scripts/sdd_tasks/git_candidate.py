"""Create an unreferenced candidate commit from verified completion anchors."""
from pathlib import Path

from .git_candidate_index import _git, build_candidate_tree
from .git_candidate_objects import store_verified_blobs
from .git_expected_entries_io import GitExpectedEntriesError, git
from .journal_fields import validate_object_id
from .journal_schema import validate_journal


def _verify_commit(root, oid, tree, parent, message):
    raw = _git(root, "cat-file", "commit", oid)
    headers, separator, body = raw.partition(b"\n\n")
    if not separator:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID")
    lines = headers.split(b"\n")
    if ([line for line in lines if line.startswith(b"tree ")] != [b"tree " + tree.encode("ascii")] or
            [line for line in lines if line.startswith(b"parent ")] != [b"parent " + parent.encode("ascii")]):
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID")
    if body not in {message, message + b"\n"}:
        raise GitExpectedEntriesError("GIT_CANDIDATE_MESSAGE_INVALID")


def create_candidate_commit(worktree: Path, journal: dict) -> str:
    """Create an unreferenced commit; caller proves owned-lock token and identity."""
    value = validate_journal(journal)
    if (value["phase"], value["index_recovery_stage"]) != ("index_after_prepared", "lock_index_durable"):
        raise GitExpectedEntriesError("GIT_CANDIDATE_PHASE_INVALID")
    root = Path(worktree).resolve(strict=True)
    head = value["original_head"]
    store_verified_blobs(root, value)
    tree = build_candidate_tree(root, value)
    if len(tree) != len(head):
        raise GitExpectedEntriesError("GIT_CANDIDATE_OBJECT_FORMAT_MISMATCH")
    store_verified_blobs(root, value)
    try:
        message = value["commit_message"].encode("utf-8")
    except UnicodeEncodeError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_MESSAGE_INVALID") from exc
    raw_oid = git(root, "commit-tree", tree, "-p", head, "-F", "-", input_data=message)
    if not raw_oid.endswith(b"\n") or raw_oid.count(b"\n") != 1:
        raise GitExpectedEntriesError("GIT_CANDIDATE_OBJECT_ID_INVALID")
    try:
        oid = raw_oid[:-1].decode("ascii")
        validate_object_id(oid, "candidate.commit")
    except (UnicodeError, ValueError) as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_OBJECT_ID_INVALID") from exc
    if len(oid) != len(head):
        raise GitExpectedEntriesError("GIT_CANDIDATE_OBJECT_FORMAT_MISMATCH")
    store_verified_blobs(root, value)
    _verify_commit(root, oid, tree, head, message)
    if git(root, "rev-parse", "HEAD").strip() != head.encode("ascii"):
        raise GitExpectedEntriesError("GIT_CANDIDATE_BASE_CHANGED")
    return oid
