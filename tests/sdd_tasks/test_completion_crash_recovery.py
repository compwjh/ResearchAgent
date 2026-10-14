import hashlib
import multiprocessing
import os
import subprocess
import tempfile
import traceback
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import completion_journal
from scripts.sdd_tasks.completion_journal import read_journal, write_journal
from scripts.sdd_tasks.completion_lifecycle import run_completion_journal
from scripts.sdd_tasks.completion_prepare import prepare_completion_journal
from scripts.sdd_tasks.events import append_event
from scripts.sdd_tasks.lifecycle_context import load_active_claim
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import OwnerIdentity, OwnerStatus, current_owner, observe_owner
from scripts.sdd_tasks.results import validate_result
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.validation_runner import run_validations
from scripts.sdd_tasks.workspace import capture_snapshot
from scripts.sdd_tasks.workspace_observation import record_workspace_observation
from tests.sdd_tasks.test_completion_prepare import SOURCE, _claimed_with_command
from tests.sdd_tasks.test_result_schema import valid_result


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _crash_worker(directory, ready, request):
    try:
        owner = current_owner("completion-crash-fixture", pid=os.getpid())
        with _claimed_with_command(directory, owner_identity=owner) as fixture:
            root, canonical, _, database, _, _, initial_claim = fixture
            ready.put(("ready", str(root), str(canonical), str(database), initial_claim.run_id))
            request.get(timeout=120)
            with closing(connect(database)) as conn, maintenance_lock(root):
                task, claim, before = load_active_claim(conn, initial_claim.run_id, owner, root)
                append_event(conn, claim.run_id, owner, "observation", {"summary": "fixture started"}, now=_utc())
                (claim.worktree_path / SOURCE).write_text("crash recovery fixture\n", encoding="utf-8")
                commands, receipt = run_validations(task, claim, root, timeout_seconds=20)
                after = capture_snapshot(root, task)
                record_workspace_observation(conn, claim.run_id, owner, after, now=_utc())
                stamp = conn.execute("SELECT timestamp FROM events WHERE run_id=? AND event_type='observation'",
                                     (claim.run_id,)).fetchone()[0]
                started = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                ended = datetime.now(timezone.utc)
                numstat = subprocess.run(["git", "diff", "--numstat", "--", SOURCE], cwd=claim.worktree_path,
                                         check=True, capture_output=True, text=True).stdout.split()
                data = valid_result()
                data.update(run_id=claim.run_id, task_id=task.metadata["task_id"],
                            task_hash=task.task_hash, prompt_hash=task.prompt_hash, outcome="succeeded",
                            started_at=stamp, ended_at=ended.isoformat().replace("+00:00", "Z"),
                            duration_ms=max(0, int((ended - started).total_seconds() * 1000)),
                            changed_files=[{"path": SOURCE, "change": "modified", "additions": int(numstat[0]),
                                            "deletions": int(numstat[1]),
                                            "sha256": after.allowed_hashes[SOURCE]}],
                            artifacts=[], commands=list(commands), tests=[],
                            log_paths=[".sdd/runtime/runs/{}/events.jsonl".format(claim.run_id)] +
                            [item[key] for item in receipt["command_logs"]
                             for key in ("stdout_path", "stderr_path")])
                report = validate_result(data, task, claim, before, after)
                if not report.valid:
                    raise AssertionError(report.errors)
                journal = prepare_completion_journal(task, claim, before, after, report, root)
                path = root / ".sdd/runtime/runs" / claim.run_id / "completion.json"
                write_journal(path, journal)
                real_atomic_write = completion_journal.atomic.atomic_write

                def crash_after_document(target, *args, **kwargs):
                    real_atomic_write(target, *args, **kwargs)
                    if Path(target) == claim.worktree_path / journal["expected_docs"][0]["path"]:
                        os._exit(86)

                with patch.object(completion_journal.atomic, "atomic_write", crash_after_document):
                    run_completion_journal(conn, path, claim.branch, _utc())
        os._exit(91)
    except BaseException:
        ready.put(("error", traceback.format_exc()))
        os._exit(90)


class CompletionCrashRecoveryTests(unittest.TestCase):
    def test_real_process_exit_after_one_expected_document_write_leaves_replayable_journal(self):
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as temp:
            ready, request = context.Queue(), context.Queue()
            process = context.Process(target=_crash_worker, args=(temp, ready, request))
            process.start()
            try:
                message = ready.get(timeout=120)
                self.assertEqual(message[0], "ready", message)
                _, root, canonical, database, run_id = message
                request.put("documents")
                process.join(120)
                self.assertFalse(process.is_alive(), "crash worker did not stop")
                if process.exitcode != 86:
                    try:
                        detail = ready.get_nowait()
                    except Exception:
                        detail = None
                    self.fail("crash worker exited {}; detail={!r}".format(process.exitcode, detail))
                path = Path(root) / ".sdd/runtime/runs" / run_id / "completion.json"
                journal = read_journal(path)
                self.assertEqual(journal["phase"], "docs_writing")
                self.assertEqual(len(journal["expected_docs"]), 4)
                for index, doc in enumerate(journal["expected_docs"]):
                    target = Path(canonical) / doc["path"]
                    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                    self.assertEqual(actual, doc["after_sha256"] if index == 0 else doc["before_sha256"])
                identity = OwnerIdentity(**journal["owner"])
                self.assertIs(observe_owner(identity), OwnerStatus.DEAD)
                with closing(connect(database)) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(10)


if __name__ == "__main__":
    unittest.main()
