import multiprocessing
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.completion_journal import read_journal
from scripts.sdd_tasks.completion_recovery import CompletionRecoveryError, resume_dead_completion
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import OwnerStatus
from scripts.sdd_tasks.result_query import result_for_run
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_crash_recovery import _crash_worker
from tests.sdd_tasks.test_completion_prepare import _claimed_with_command
from tests.sdd_tasks.test_run_owner import _rows


def _crashed_docs(directory):
    context = multiprocessing.get_context("fork")
    ready, request = context.Queue(), context.Queue()
    worker = context.Process(target=_crash_worker, args=(directory, ready, request))
    worker.start()
    try:
        message = ready.get(timeout=120)
        if message[0] != "ready":
            raise AssertionError(message)
        _, root, canonical, database, run_id = message
        request.put("documents")
        worker.join(120)
        if worker.exitcode != 86:
            raise AssertionError("crash worker exited {}".format(worker.exitcode))
        return Path(root), Path(canonical), Path(database), run_id
    finally:
        if worker.is_alive():
            worker.terminate()
        worker.join(10)


class CompletionRecoveryTests(unittest.TestCase):
    def test_missing_journal_is_read_only_and_malformed_journal_refuses(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, _, _, database, _, _, claim = state
            run_id = claim.run_id
            path = root / ".sdd/runtime/runs" / run_id / "completion.json"
            with closing(connect(database)) as conn, maintenance_lock(root):
                before = _rows(conn)
                self.assertIsNone(resume_dead_completion(conn, root, run_id))
                self.assertEqual(_rows(conn), before)
                path.parent.parent.mkdir(mode=0o700)
                path.parent.mkdir(mode=0o700)
                path.write_text("{partial", encoding="utf-8")
                original = path.read_bytes()
                with self.assertRaises(CompletionRecoveryError) as caught:
                    resume_dead_completion(conn, root, run_id)
                self.assertEqual(caught.exception.code, "RECOVER_JOURNAL_OR_BINDING_INVALID")
                self.assertEqual(_rows(conn), before)
                self.assertEqual(path.read_bytes(), original)

    def test_owner_status_and_unexpired_lease_refusals_leave_journal_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, database, run_id = _crashed_docs(temp)
            path = root / ".sdd/runtime/runs" / run_id / "completion.json"
            original = path.read_bytes()
            future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace(
                "+00:00", "Z")
            cases = ((OwnerStatus.ALIVE, "RECOVER_OWNER_ALIVE"),
                     (OwnerStatus.UNKNOWN, "RECOVER_OWNER_UNKNOWN"),
                     (OwnerStatus.DEAD, "RECOVER_LEASE_UNEXPIRED"))
            with closing(connect(database)) as conn, maintenance_lock(root):
                conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?", (future, run_id))
                before = _rows(conn)
                for status, code in cases:
                    with self.subTest(status=status), patch(
                            "scripts.sdd_tasks.completion_recovery.observe_owner", return_value=status):
                        with self.assertRaises(CompletionRecoveryError) as caught:
                            resume_dead_completion(conn, root, run_id)
                        self.assertEqual(caught.exception.code, code)
                        self.assertEqual(_rows(conn), before)
                        self.assertEqual(path.read_bytes(), original)

    def test_dead_expired_journal_recovers_and_terminal_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, database, run_id = _crashed_docs(temp)
            path = root / ".sdd/runtime/runs" / run_id / "completion.json"
            with closing(connect(database)) as conn, maintenance_lock(root):
                conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?",
                             ("2000-01-01T00:00:00Z", run_id))
                result = resume_dead_completion(conn, root, run_id)
                row = conn.execute("SELECT task_id,state FROM runs WHERE run_id=?",
                                   (run_id,)).fetchone()
                status = conn.execute("SELECT status FROM tasks WHERE task_id=?",
                                      (row["task_id"],)).fetchone()[0]
                self.assertEqual(result_for_run(conn, run_id), result)
                replayed = resume_dead_completion(conn, root, run_id)
                self.assertEqual(result_for_run(conn, run_id), replayed)
            self.assertEqual(read_journal(path)["phase"], "complete")
            self.assertEqual((row["state"], status), ("succeeded", "completed"))
