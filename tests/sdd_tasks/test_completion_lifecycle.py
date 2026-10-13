import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.completion_journal import read_journal, write_journal
from scripts.sdd_tasks.completion_lifecycle import run_completion_journal
from scripts.sdd_tasks.completion_prepare import prepare_completion_journal
from scripts.sdd_tasks.events import append_event
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.result_query import result_for_run
from scripts.sdd_tasks.results import validate_result
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.validation_runner import run_validations
from scripts.sdd_tasks.workspace import capture_snapshot
from scripts.sdd_tasks.workspace_observation import record_workspace_observation
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_result_schema import valid_result


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CompletionLifecycleTests(unittest.TestCase):
    def test_real_validation_publication_dispatch_replay_and_rebuild(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, worktree, task, database, before, _, claim = state
            (worktree / SOURCE).write_text("validated source change\n", encoding="utf-8")
            with maintenance_lock(root):
                with closing(connect(database)) as conn:
                    event = append_event(conn, claim.run_id, claim.owner, "observation",
                                         {"note": "run declared validation"}, now=_now())
                commands, receipt = run_validations(task, claim, root, timeout_seconds=20)
                self.assertTrue(receipt["valid"], receipt["commands"])
                after = capture_snapshot(root, task)
                with closing(connect(database)) as conn:
                    record_workspace_observation(conn, claim.run_id, claim.owner, after, now=_now())
                counts = subprocess.run(["git", "-C", str(worktree), "diff", "--numstat",
                                         "--", SOURCE], check=True, capture_output=True).stdout
                additions, deletions, path = counts.decode("utf-8").strip().split("\t")
                self.assertEqual(path, SOURCE)
                changed = [{"path": SOURCE, "change": "modified", "additions": int(additions),
                            "deletions": int(deletions), "sha256": after.allowed_hashes[SOURCE]}]
                data = valid_result()
                data.update(run_id=claim.run_id, task_id=task.metadata["task_id"],
                            task_hash=task.task_hash, prompt_hash=task.prompt_hash,
                            outcome="succeeded", summary="Real validation runner completed",
                            started_at=event.timestamp, ended_at=receipt["ended_at"],
                            duration_ms=receipt["duration_ms"], changed_files=changed,
                            commands=list(commands), artifacts=[], tests=[],
                            log_paths=[path for item in receipt["command_logs"]
                                       for path in (item["stdout_path"], item["stderr_path"])])
                report = validate_result(data, task, claim, before, after)
                self.assertTrue(report.valid, report.errors)
                ended_at = _now()
                data.update(ended_at=ended_at, duration_ms=max(0, int((
                    datetime.fromisoformat(ended_at.replace("Z", "+00:00")) -
                    datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
                ).total_seconds() * 1000)))
                report = validate_result(data, task, claim, before, after)
                self.assertTrue(report.valid, report.errors)
                proposal = prepare_completion_journal(task, claim, before, after, report, root)
                journal_path = root / ".sdd/runtime/runs" / claim.run_id / "completion.json"
                write_journal(journal_path, proposal)
                with closing(connect(database)) as conn:
                    terminal = run_completion_journal(conn, journal_path, claim.branch, _now())
                    replayed = run_completion_journal(conn, journal_path, claim.branch, _now())
                    row = conn.execute("SELECT state,result_doc FROM runs WHERE run_id=?",
                                       (claim.run_id,)).fetchone()
                    task_row = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                            (task.metadata["task_id"],)).fetchone()
                    self.assertEqual(result_for_run(conn, claim.run_id), report.result)
                    self.assertEqual(conn.execute("SELECT count(*) FROM leases WHERE run_id=?",
                                                  (claim.run_id,)).fetchone()[0], 0)
                self.assertEqual((row["state"], task_row["status"]), ("succeeded", "completed"))
                self.assertEqual(terminal, report.result)
                self.assertEqual(replayed, report.result)
                journal = read_journal(journal_path)
                self.assertEqual(journal["phase"], "complete")
                head = subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
                branch_tip = subprocess.run(["git", "-C", str(worktree), "rev-parse",
                                             "refs/heads/" + claim.branch], check=True,
                                            capture_output=True, text=True).stdout.strip()
                tree = subprocess.run(["git", "-C", str(worktree), "write-tree"], check=True,
                                      capture_output=True, text=True).stdout.strip()
                committed_tree = subprocess.run(["git", "-C", str(worktree), "rev-parse",
                                                 "HEAD^{tree}"], check=True, capture_output=True,
                                                text=True).stdout.strip()
                status = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain"],
                                        check=True, capture_output=True).stdout
                source = subprocess.run(["git", "-C", str(worktree), "show", "HEAD:" + SOURCE],
                                        check=True, capture_output=True).stdout
                self.assertEqual((head, branch_tip, tree, status),
                                 (journal["candidate_commit_hash"], head, committed_tree, b""))
                self.assertEqual(source, b"validated source change\n")
            with self.assertWarnsRegex(RuntimeWarning, "stale_task_copies_ignored"):
                rebuilt = rebuild(database, root)
            self.assertEqual(rebuilt.runs, 1)
            with closing(connect(database)) as conn:
                self.assertEqual(result_for_run(conn, claim.run_id), report.result)


if __name__ == "__main__":
    unittest.main()
