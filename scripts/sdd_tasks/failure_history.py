"""Read-only verification of private terminal failure commit history."""

import hashlib
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

from .atomic import contained, read_text
from .catalog import discover_worktrees
from .documents import TaskDefinition
from .git_index import GitIndexError, _index_state
from .git_reconciliation_index import _main_run_fd, _read_private_file, _verify_run_fd
from .journal_schema import validate_journal
from .lease_recovery import stored_owner
from .leases import _main_root
from .ledger_finalize import _target_task_status
from .mirrors import render_status_update
from .result_query import result_for_run
from .workspace_observation import _decode_observation_event, _load_failed_run_baseline


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
        roots = discover_worktrees(main)
        if not roots or roots[0] != main or supplied not in roots:
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


def _commit_record(worktree, oid):
    try:
        header, message = _git(worktree, "cat-file", "commit", oid).split(b"\n\n", 1)
        fields = [line.split(b" ", 1) for line in header.splitlines()]
        trees = [value for key, value in fields if key == b"tree"]
        parents = [value for key, value in fields if key == b"parent"]
        tree = trees[0].decode("ascii")
        parent = parents[0].decode("ascii")
        if (len(trees) != 1 or len(parents) != 1 or not _OID.fullmatch(tree) or
                not _OID.fullmatch(parent)):
            raise ValueError("commit must have one tree and one parent")
        message.decode("utf-8")
        return tree, parent, message
    except (UnicodeError, ValueError, IndexError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_COMMIT_INVALID") from exc


def _private_journal(main, worktree, run_id):
    path = main / ".sdd" / "runtime" / "runs" / run_id / "completion.json"
    pinned = -1
    try:
        canonical_main, pinned = _main_run_fd(worktree, path, run_id)
        if canonical_main != main:
            raise ValueError("journal belongs to another repository")
        journal = validate_journal(_strict_json(_read_private_file(pinned, "completion.json")))
        _verify_run_fd(main, run_id, pinned)
        return journal
    except (OSError, TypeError, ValueError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_JOURNAL_INVALID") from exc
    finally:
        if pinned >= 0:
            os.close(pinned)


def _verify_history_runs(conn, main, worktree, selected_run_id, task, base, chain):
    task_id, relative, branch = (task.metadata["task_id"], task.metadata["worktree"]["path"],
                                 task.metadata["worktree"]["branch"])
    verified, previous_end, previous_attempt, seen = [], None, 0, set()
    for position, (oid, parent) in enumerate(chain):
        tree, actual_parent, raw_message = _commit_record(worktree, oid)
        try:
            subject = raw_message.split(b"\n", 1)[0].decode("utf-8")
        except UnicodeError as exc:
            raise FailureHistoryError("FAILURE_HISTORY_COMMIT_INVALID") from exc
        match = _COMMIT_SUBJECT.fullmatch(subject)
        if (actual_parent != parent or match is None or match.group(2) != task_id or
                match.group(3) in seen or (match.group(1) == "blocked" and position != len(chain) - 1)):
            raise FailureHistoryError("FAILURE_HISTORY_COMMIT_BINDING_MISMATCH")
        outcome, run_id = match.group(1), match.group(3)
        seen.add(run_id)
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if (run is None or run["state"] != outcome or run["ended_at"] is None or
                conn.execute("SELECT 1 FROM leases WHERE run_id=?", (run_id,)).fetchone() or
                (run["task_id"], run["task_hash"], run["prompt_hash"], run["worktree"],
                 run["branch"], run["agent_role"], run["base_commit"]) !=
                (task_id, task.task_hash, task.prompt_hash, relative, branch,
                 task.metadata["agent_role"], base)):
            raise FailureHistoryError("FAILURE_HISTORY_RUN_BINDING_MISMATCH")
        if type(run["attempt"]) is not int or run["attempt"] <= previous_attempt:
            raise FailureHistoryError("FAILURE_HISTORY_ATTEMPT_ORDER_INVALID")
        journal = _private_journal(main, worktree, run_id)
        owner = stored_owner(run["owner_json"])
        result = result_for_run(conn, run_id)
        owner_value = {key: getattr(owner, key) for key in
                       ("executor_id", "host_id", "pid", "process_started_at", "token")}
        if (owner.executor_id != run["executor_id"] or not _same_owner(owner_value, journal["owner"]) or
                journal["phase"] != "complete" or journal["run_id"] != run_id or
                journal["task_id"] != task_id or journal["candidate_commit_hash"] != oid or
                journal["task_hash"] != task.task_hash or journal["prompt_hash"] != task.prompt_hash or
                journal["allowed_paths"] != task.metadata["allowed_paths"] or
                journal["original_head"] != parent or journal["base_commit"] != base or
                journal["terminal_outcome"] != outcome or journal["expected_result"] != result or
                raw_message not in {journal["commit_message"].encode("utf-8"),
                                    journal["commit_message"].encode("utf-8") + b"\n"}):
            raise FailureHistoryError("FAILURE_HISTORY_JOURNAL_BINDING_MISMATCH")
        started, ended = _instant(result["started_at"]), _instant(result["ended_at"])
        if (run["ended_at"] != result["ended_at"] or started > ended or
                (previous_end is not None and started < previous_end)):
            raise FailureHistoryError("FAILURE_HISTORY_TIME_ORDER_INVALID")
        previous_end, previous_attempt = ended, run["attempt"]
        verified.append((run, result, journal, oid, parent, tree, raw_message))
    if not verified or verified[-1][0]["run_id"] != selected_run_id:
        raise FailureHistoryError("FAILURE_HISTORY_SELECTED_RUN_INVALID")
    return tuple(verified)


def _verify_failure_history_core(conn, run_id, task, repo_root):
    main, worktree, baseline = _task_context(conn, run_id, task, repo_root)
    selected = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if selected is None or selected["state"] != "failed" or selected["ended_at"] is None:
        raise FailureHistoryError("FAILURE_HISTORY_SELECTED_RUN_INVALID")
    before = _git_state(worktree)
    if before[1] != task.metadata["worktree"]["branch"] or selected["base_commit"] != baseline.head:
        raise FailureHistoryError("FAILURE_HISTORY_BASE_OR_BRANCH_INVALID")
    chain = _first_parent_chain(worktree, before[0], selected["base_commit"])
    verified = _verify_history_runs(conn, main, worktree, run_id, task, selected["base_commit"], chain)
    tips = []
    for run, _result, _journal, _oid, parent, _tree, _message in verified:
        _decode_observation_event(conn, run["run_id"], task, main, expected_tip=parent)
        tips.append((run["run_id"], parent))
    after = _git_state(worktree)
    if after != before:
        raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_CHANGED")
    return main, worktree, baseline, before, verified, tuple(tips)


def _tree_entries(worktree, treeish):
    entries = {}
    try:
        for record in _git(worktree, "ls-tree", "-r", "-z", "--full-tree", treeish).split(b"\0"):
            if not record:
                continue
            header, raw_path = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split()
            path = raw_path.decode("utf-8")
            if path in entries or not _OID.fullmatch(oid):
                raise ValueError("duplicate or malformed tree entry")
            entries[path] = (mode, kind, oid)
    except (UnicodeError, ValueError) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_TREE_INVALID") from exc
    return entries


def _verify_document_history(conn, worktree, task, records):
    all_paths, latest = set(), {}
    for run, _result, journal, oid, parent, _tree, _message in records:
        target = _target_task_status(conn, run, task.metadata, journal["terminal_outcome"],
                                     transaction_required=False)
        summary = "docs/sdd/runs/{}/task-{}/{}.md".format(
            task.metadata["spec_id"], task.metadata["task_id"][-2:], run["run_id"])
        mirrors = render_status_update(task, target, worktree) if target != "pending" else {}
        docs = {item["path"]: item for item in journal["expected_docs"]}
        paths = set(mirrors) | {summary}
        expected_git = {item["path"]: item for item in journal["expected_git_entries"]}
        if (set(docs) != paths or set(journal["staged_paths"]) != paths or
                set(journal["committed_paths"]) != paths or set(expected_git) != paths):
            raise FailureHistoryError("FAILURE_HISTORY_DOCUMENT_SET_INVALID")
        before_tree, after_tree = _tree_entries(worktree, parent), _tree_entries(worktree, oid)
        changed = set()
        for path, doc in docs.items():
            content = doc["content"]
            if not isinstance(content, str) or (path in mirrors and content != mirrors[path]):
                raise FailureHistoryError("FAILURE_HISTORY_DOCUMENT_CONTENT_INVALID")
            payload = content.encode("utf-8")
            old, new = before_tree.get(path), after_tree.get(path)
            old_bytes = _git(worktree, "cat-file", "blob", old[2]) if old else None
            digest_before = hashlib.sha256(old_bytes).hexdigest() if old_bytes is not None else None
            digest_after = hashlib.sha256(payload).hexdigest()
            entry = expected_git[path]
            if (doc["before_sha256"] != digest_before or doc["after_sha256"] != digest_after or
                    new is None or new[1] != "blob" or entry != {
                        "path": path, "mode": new[0], "object_id": new[2]} or
                    _git(worktree, "cat-file", "blob", new[2]) != payload):
                raise FailureHistoryError("FAILURE_HISTORY_DOCUMENT_BLOB_INVALID")
            if (old is None or old != new):
                changed.add(path)
            latest[path] = content
            all_paths.add(path)
        actual = _git(worktree, "diff-tree", "--no-commit-id", "--name-only", "-r",
                      "--no-renames", "-z", parent, oid).split(b"\0")
        actual_paths = {item.decode("utf-8") for item in actual if item}
        if actual_paths != changed:
            raise FailureHistoryError("FAILURE_HISTORY_DIFF_PATHS_INVALID")
    for path, content in latest.items():
        if read_text(contained(worktree, path)) != content:
            raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_DOCUMENT_MISMATCH")
    return tuple(sorted(all_paths))


def verify_failed_run_history(conn, run_id, task, repo_root):
    """Return proof of a documents-only failed-run chain ending at current HEAD."""
    try:
        main, worktree, _baseline, before, records, tips = _verify_failure_history_core(
            conn, run_id, task, repo_root)
        excluded = _verify_document_history(conn, worktree, task, records)
        if _git_state(worktree) != before:
            raise FailureHistoryError("FAILURE_HISTORY_WORKTREE_CHANGED")
        return VerifiedFailureHistory(tips, excluded, before[0])
    except FailureHistoryError:
        raise
    except (OSError, TypeError, ValueError, KeyError, IndexError, sqlite3.Error) as exc:
        raise FailureHistoryError("FAILURE_HISTORY_INVALID") from exc
