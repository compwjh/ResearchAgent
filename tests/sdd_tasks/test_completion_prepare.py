import hashlib
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.completion_prepare import prepare_completion_journal
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.git_index import read_index_snapshot
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.results import validate_result
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_result_schema import valid_result
from tests.sdd_tasks.test_run_owner import _rows
from tests.sdd_tasks.test_selection import GATE, _fixture

COMMAND = "python3 -c \"from pathlib import Path; assert Path('scripts/sdd_tasks/allowed.txt').is_file()\""
SOURCE = "scripts/sdd_tasks/allowed.txt"


@contextmanager
def _claimed_with_command(directory, owner_identity=None):
    root, canonical, task, _, database = _fixture(directory)
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + "\n.sdd/runtime/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "ignore private runtime"], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tip = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(canonical), "merge", "--ff-only", tip], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    metadata = dict(task.metadata, validation_commands=[COMMAND])
    relative = task.path.relative_to(root)
    source = canonical / relative
    contents = "# {}\n> 当前状态：`待执行`\n\n".format(metadata["title"]) + task_markdown(metadata)
    for repository in (root, canonical):
        (repository / relative).write_text(contents, encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", relative.as_posix()],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture validation command"],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    task = parse_task(source)
    rebuild(database, root)
    os.chmod(database.parent, 0o700)
    before = capture_snapshot(root, task)
    child = (None if owner_identity is not None else
             subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]))
    try:
        owner = owner_identity or current_owner("prepare-fixture", pid=child.pid)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with closing(connect(database)) as conn, maintenance_lock(root):
            claim = claim_next(conn, [task], {GATE}, workspace_snapshots={
                task.metadata["task_id"]: before}, ide="codex", owner=owner,
                now=now, lease_minutes=30)
        if claim is None:
            raise AssertionError("fixture Task was not claimed")
        yield root, canonical, task, database, before, child, claim
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
        if child is not None:
            child.wait(timeout=10)


def _tree_state(root):
    entries = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            value = ("link", path.readlink().as_posix())
        elif stat.S_ISREG(info.st_mode):
            value = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            value = ("directory", None)
        entries.append((relative, stat.S_IMODE(info.st_mode), value))
    return tuple(entries)


def _result(task, claim, before, after, *, command, outcome="succeeded"):
    data = valid_result()
    data.update(run_id=claim.run_id, task_id=task.metadata["task_id"],
                task_hash=task.task_hash, prompt_hash=task.prompt_hash,
                outcome=outcome,
                started_at=claim.claimed_at,
                ended_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                changed_files=[], artifacts=[], commands=[command], tests=[])
    if after.allowed_hashes[SOURCE] != before.allowed_hashes[SOURCE]:
        data["changed_files"] = [{"path": SOURCE, "change": "modified", "additions": 1,
                                  "deletions": 1, "sha256": after.allowed_hashes[SOURCE]}]
    return validate_result(data, task, claim, before, after)


class CompletionPrepareTests(unittest.TestCase):
    def test_success_proposal_binds_real_result_docs_source_and_index_without_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, before, _, claim = state
            source = worktree / SOURCE
            source.write_text("prepared source change\n", encoding="utf-8")
            after = capture_snapshot(root, task)
            argv = shlex.split(COMMAND)
            start = datetime.now(timezone.utc)
            ran = subprocess.run(argv, cwd=str(worktree), capture_output=True, check=False)
            ended = datetime.now(timezone.utc)
            self.assertEqual(ran.returncode, 0, ran.stderr.decode("utf-8", "replace"))
            receipt = {"argv": argv, "status": "executed", "exit_code": ran.returncode,
                       "duration_ms": max(1, int((ended - start).total_seconds() * 1000)),
                       "summary": "fixture validation command passed"}
            report = _result(task, claim, before, after, command=receipt)
            self.assertTrue(report.valid, report.errors)
            self.assertEqual(report.changed_paths, (SOURCE,))
            with closing(connect(database)) as conn:
                rows, files = _rows(conn), _tree_state(root)
                original_result = deepcopy(report.result)
                journal = prepare_completion_journal(task, claim, before, after, report, root)
                self.assertEqual(len(journal["expected_docs"]), 4)
                self.assertIn(SOURCE, journal["committed_paths"])
                self.assertEqual(set(journal["committed_paths"]) - {SOURCE},
                                 {doc["path"] for doc in journal["expected_docs"]})
                changed = journal["changed_paths"][0]
                self.assertEqual((changed["path"], changed["before_sha256"], changed["after_sha256"]),
                                 (SOURCE, before.allowed_hashes[SOURCE], after.allowed_hashes[SOURCE]))
                self.assertEqual(journal["expected_result"], original_result)
                anchor = next(item for item in journal["expected_git_entries"] if item["path"] == SOURCE)
                payload = b"prepared source change\n"
                blob = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
                self.assertEqual((anchor["mode"], anchor["object_id"]),
                                 ("100644", hashlib.sha1(blob).hexdigest()))
                self.assertEqual(read_index_snapshot(worktree, journal["committed_paths"],
                                                     original_head=after.head), journal["index_before"])
                report.result["summary"] = "mutated caller result after proposal"
                self.assertEqual(journal["expected_result"], original_result)
                self.assertEqual(_rows(conn), rows)
                self.assertEqual(_tree_state(root), files)

    def test_failed_summary_only_and_blocked_status_proposals_are_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, before, _, claim = state
            after = capture_snapshot(root, task)
            mirrors = {task.path.relative_to(worktree).as_posix(),
                       "docs/sdd/specs/016-portable-task-ledger.md", "docs/sdd/plans/016/README.md"}
            with closing(connect(database)) as conn:
                rows, files = _rows(conn), _tree_state(root)
                for outcome, target_status in (("failed", None), ("blocked", "blocked")):
                    receipt = {"argv": shlex.split(COMMAND), "status": "skipped", "exit_code": None,
                               "duration_ms": None, "summary": "not run for non-success outcome"}
                    report = _result(task, claim, before, after, command=receipt, outcome=outcome)
                    self.assertTrue(report.valid, report.errors)
                    proposal = prepare_completion_journal(
                        task, claim, before, after, report, root, target_task_status=target_status)
                    paths = {item["path"] for item in proposal["expected_docs"]}
                    summary_paths = {path for path in paths if path.startswith("docs/sdd/runs/")}
                    self.assertEqual(len(summary_paths), 1)
                    self.assertEqual(paths - summary_paths, mirrors if outcome == "blocked" else set())
                    self.assertEqual(set(proposal["committed_paths"]), paths)
                    self.assertEqual(proposal["changed_paths"], [])
                    if outcome == "blocked":
                        for item in proposal["expected_docs"]:
                            if item["path"] in mirrors:
                                self.assertIn("阻塞", item["content"])
                    self.assertEqual(_rows(conn), rows)
                    self.assertEqual(_tree_state(root), files)


if __name__ == "__main__":
    unittest.main()
