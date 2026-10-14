"""Read-only verification of private terminal failure commit history."""

import hmac
import json
import os
import re
import sqlite3
import subprocess
import uuid
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .atomic import contained
from .catalog import discover_worktrees
from .documents import TaskDefinition
from .git_index import GitIndexError, _index_state
from .leases import _main_root
from .workspace_observation import _load_failed_run_baseline


class FailureHistoryError(ValueError):
    """A failed run has no verifiable, documents-only terminal history."""


VerifiedFailureHistory = namedtuple(
    "VerifiedFailureHistory", "observation_tips excluded_paths current_tip")
_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_COMMIT_SUBJECT = re.compile(
    r"sdd: (failed|blocked) (spec-\d{3}-task-\d{2}) run "
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\Z")


def _git(root, *args, input_bytes=None):
    env = os.environ.copy()
    for key in _GIT_ENV:
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(["git", "-C", os.fspath(root), *args], input=input_bytes,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except OSError as exc:
        raise FailureHistoryError("FAILURE_HISTORY_GIT_UNAVAILABLE") from exc
    if result.returncode:
        raise FailureHistoryError("FAILURE_HISTORY_GIT_INVALID")
    return result.stdout


def _text(value):
    try:
        return value.decode("utf-8").rstrip("\n")
    except (AttributeError, UnicodeError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_GIT_INVALID") from exc


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("invalid JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (AttributeError, UnicodeError, ValueError, RecursionError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_JOURNAL_INVALID") from exc


def _same_owner(left, right):
    fields = ("executor_id", "host_id", "pid", "process_started_at")
    return (all(left.get(field) == right.get(field) for field in fields) and
            isinstance(left.get("token"), str) and isinstance(right.get("token"), str) and
            hmac.compare_digest(left["token"].encode("utf-8"), right["token"].encode("utf-8")))


def _task_context(conn, run_id, task, repo_root):
    if (not isinstance(conn, sqlite3.Connection) or type(task) is not TaskDefinition or not isinstance(run_id, str) or
            not isinstance(repo_root, (str, os.PathLike))):
        raise FailureHistoryError("FAILURE_HISTORY_ARGUMENT_INVALID")
    try:
        canonical_id = str(uuid.UUID(run_id))
        if canonical_id != run_id:
            raise ValueError("noncanonical UUID")
        main = _main_root(conn)
        supplied = Path(repo_root).resolve(strict=True)
        if supplied not in discover_worktrees(main):
            raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_INVALID")
        worktree = contained(main, task.metadata["worktree"]["path"]).resolve(strict=True)
        if supplied not in {main, worktree}:
            raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_INVALID")
        if Path(_text(_git(supplied, "rev-parse", "--show-toplevel"))).resolve(strict=True) != supplied:
            raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_INVALID")
        baseline = _load_failed_run_baseline(conn, run_id, task, main)
        if baseline.worktree_path != worktree or baseline.repo_root != main:
            raise FailureHistoryError("FAILURE_HISTORY_TASK_MISMATCH")
        return main, worktree, baseline
    except FailureHistoryError:
        raise
    except (OSError, TypeError, ValueError, KeyError, sqlite3.Error) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_CONTEXT_INVALID") from exc


def _instant(value):
    if not isinstance(value, str):
        raise FailureHistoryError("FAILURE_HISTORY_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise FailureHistoryError("FAILURE_HISTORY_TIME_INVALID") from exc
    if parsed.utcoffset() != timedelta(0):
        raise FailureHistoryError("FAILURE_HISTORY_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _git_state(worktree):
    head = _text(_git(worktree, "rev-parse", "HEAD"))
    branch = _text(_git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD"))
    if not _OID.fullmatch(head) or not branch:
        raise FailureHistoryError("FAILURE_HISTORY_GIT_INVALID")
    if _git(worktree, "ls-files", "--unmerged", "-z"):
        raise FailureHistoryError("FAILURE_HISTORY_INDEX_UNMERGED")
    index = Path(_text(_git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index")))
    if not index.is_absolute():
        raise FailureHistoryError("FAILURE_HISTORY_INDEX_INVALID")
    try:
        return head, branch, index, _index_state(index)
    except (GitIndexError, OSError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_INDEX_INVALID") from exc


def _first_parent_chain(worktree, tip, base):
    if not _OID.fullmatch(base):
        raise FailureHistoryError("FAILURE_HISTORY_BASE_INVALID")
    raw = _git(worktree, "rev-list", "--first-parent", "--parents", tip)
    descending, found = [], False
    try:
        lines = raw.decode("ascii").splitlines()
        for line in lines:
            fields = line.split()
            commit = fields[0]
            if not _OID.fullmatch(commit):
                raise ValueError("invalid commit id")
            if commit == base:
                found = True
                break
            if len(fields) != 2 or not _OID.fullmatch(fields[1]):
                raise ValueError("failure chain must be single-parent")
            descending.append((commit, fields[1]))
        if not found or not descending or descending[0][0] != tip:
            raise ValueError("base is not an ancestor of tip")
        for index in range(len(descending) - 1):
            if descending[index][1] != descending[index + 1][0]:
                raise ValueError("broken first-parent chain")
    except (UnicodeError, ValueError, IndexError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_CHAIN_INVALID") from exc
    return tuple(reversed(descending))
