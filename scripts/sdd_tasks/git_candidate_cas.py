"""Compare-and-swap a journaled candidate onto its validated Task branch."""
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .git_candidate_cas_io import verify_pending_index_images
from .git_candidate_index import _verify_tree
from .git_candidate_objects import check_source_anchors
from .git_expected_entries_io import GitExpectedEntriesError
from .journal_fields import validate_object_id
from .journal_schema import validate_journal


def _git(root, *args, hooks_path=None):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    command = ["git", "-C", os.fspath(root)]
    if hooks_path is not None:
        command.extend(("-c", "core.hooksPath=" + os.fspath(hooks_path)))
    try:
        result = subprocess.run(command + list(args), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env)
    except OSError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_FAILED") from exc
    if result.returncode:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_FAILED")
    return result.stdout


def _text(root, *args):
    raw = _git(root, *args)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_INVALID")
    try:
        return raw[:-1].decode("ascii")
    except UnicodeError as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_INVALID") from exc


def _path_text(root, *args):
    raw = _git(root, *args)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMAND_INVALID")
    return os.fsdecode(raw[:-1])


def _context(root, journal):
    top = Path(_path_text(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top != root:
        raise GitExpectedEntriesError("GIT_CANDIDATE_WORKTREE_MISMATCH")
    registry = _git(root, "worktree", "list", "--porcelain", "-z")
    if registry.count(b"worktree " + os.fsencode(root) + b"\0") != 1:
        raise GitExpectedEntriesError("GIT_CANDIDATE_WORKTREE_UNREGISTERED")
    git_dir = _path_text(root, "rev-parse", "--absolute-git-dir")
    index_path = _path_text(root, "rev-parse", "--path-format=absolute", "--git-path", "index")
    expected = Path(git_dir) / "index"
    actual = Path(journal["index_before"]["git_index_path"])
    if (not expected.is_absolute() or not actual.is_absolute() or
            os.path.normpath(index_path) != os.path.normpath(os.fspath(expected)) or
            os.path.normpath(index_path) != os.path.normpath(os.fspath(actual))):
        raise GitExpectedEntriesError("GIT_CANDIDATE_INDEX_PATH_MISMATCH")


def _branch_ref(root, task_id, task_branch):
    spec = task_id.split("-")[1]
    if (not isinstance(task_branch, str) or
            not re.fullmatch(r"feature/spec-" + spec + r"-[a-z0-9]+(?:-[a-z0-9]+)*", task_branch)):
        raise GitExpectedEntriesError("GIT_CANDIDATE_TASK_BRANCH_INVALID")
    if _text(root, "check-ref-format", "--branch", task_branch) != task_branch:
        raise GitExpectedEntriesError("GIT_CANDIDATE_TASK_BRANCH_INVALID")
    ref = "refs/heads/" + task_branch
    if _text(root, "symbolic-ref", "-q", "HEAD") != ref:
        raise GitExpectedEntriesError("GIT_CANDIDATE_BRANCH_MISMATCH")
    return ref


def _verify_candidate(root, journal):
    oid, parent = journal["candidate_commit_hash"], journal["original_head"]
    validate_object_id(oid, "candidate_commit_hash")
    raw = _git(root, "cat-file", "commit", oid)
    headers, separator, body = raw.partition(b"\n\n")
    if not separator:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID")
    lines = headers.split(b"\n")
    trees = [line[5:] for line in lines if line.startswith(b"tree ")]
    parents = [line[7:] for line in lines if line.startswith(b"parent ")]
    if len(trees) != 1 or parents != [parent.encode("ascii")]:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID")
    try:
        tree = trees[0].decode("ascii")
        message = journal["commit_message"].encode("utf-8")
        validate_object_id(tree, "candidate.tree")
    except (UnicodeError, ValueError) as exc:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID") from exc
    if len(oid) != len(parent) or len(tree) != len(parent) or body not in {message, message + b"\n"}:
        raise GitExpectedEntriesError("GIT_CANDIDATE_COMMIT_INVALID")
    _verify_tree(root, tree, parent, journal["expected_git_entries"], journal["committed_paths"])


def _verify_state(root, journal, task_branch):
    _context(root, journal)
    _branch_ref(root, journal["task_id"], task_branch)
    verify_pending_index_images(journal)
    head = _text(root, "rev-parse", "HEAD")
    if head not in {journal["original_head"], journal["candidate_commit_hash"]}:
        raise GitExpectedEntriesError("GIT_CANDIDATE_HEAD_CONFLICT")
    _verify_candidate(root, journal)
    check_source_anchors(root, journal)
    verify_pending_index_images(journal)
    if (_text(root, "rev-parse", "HEAD") != head or
            _text(root, "symbolic-ref", "-q", "HEAD") != "refs/heads/" + task_branch):
        raise GitExpectedEntriesError("GIT_CANDIDATE_BASE_CHANGED")
    return head


def reconcile_candidate_ref(worktree: Path, journal: dict, *, task_branch: str) -> str:
    """CAS a durable commit_pending candidate; caller binds branch to canonical Task."""
    value = validate_journal(journal)
    if (value["phase"], value["index_recovery_stage"]) != ("commit_pending", "lock_index_durable"):
        raise GitExpectedEntriesError("GIT_CANDIDATE_PHASE_INVALID")
    root = Path(worktree).resolve(strict=True)
    branch_ref = _branch_ref(root, value["task_id"], task_branch)
    head = _verify_state(root, value, task_branch)
    candidate, original = value["candidate_commit_hash"], value["original_head"]
    if head == candidate:
        return candidate
    if head != original:
        raise GitExpectedEntriesError("GIT_CANDIDATE_HEAD_CONFLICT")
    try:
        with tempfile.TemporaryDirectory(prefix="sdd-no-hooks-") as hook_directory:
            _git(root, "update-ref", branch_ref, candidate, original, hooks_path=hook_directory)
    except GitExpectedEntriesError as exc:
        if _text(root, "rev-parse", "HEAD") != candidate:
            raise GitExpectedEntriesError("GIT_CANDIDATE_REF_CAS_FAILED") from exc
    if _verify_state(root, value, task_branch) != candidate:
        raise GitExpectedEntriesError("GIT_CANDIDATE_REF_CAS_FAILED")
    return candidate
