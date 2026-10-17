import multiprocessing
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.catalog import status
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.newcli_recover import recover_from_cli
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_failed_retry_crash import _crash_failed_source_claim
from tests.sdd_tasks.test_failure_history import _failed_run


def _item(report, task_id):
    return next(item for name in ("eligible", "waiting") for item in report[name]
                if item["task_id"] == task_id)


class FailedRecoveryStatusTests(unittest.TestCase):
    def test_latest_failed_proof_controls_status(self):
        with tempfile.TemporaryDirectory() as temp, _failed_run(temp) as data:
            _, _, task, database, _, source = data[:6]
            with closing(connect(database)) as conn:
                report = status(conn)
            item = _item(report, task.metadata["task_id"])
            self.assertEqual(item["reasons"], ["recovery_ready:partial"])
            self.assertIn(item, report["eligible"])

            source.write_text("changed after failure\n", encoding="utf-8")
            with closing(connect(database)) as conn:
                report = status(conn)
            item = _item(report, task.metadata["task_id"])
            self.assertIn("recovery_invalid:RECOVERY_VALIDATION_FAILED", item["reasons"])
            self.assertIn(item, report["waiting"])
            self.assertNotIn(item, report["eligible"])

    def test_crash_recovered_failed_retry_is_ready_in_status(self):
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as temp:
            ready, crash = context.Queue(), context.Event()
            worker = context.Process(target=_crash_failed_source_claim,
                                     args=(temp, ready, crash))
            worker.start()
            try:
                message = ready.get(timeout=120)
                self.assertNotEqual(message[0], "error", message)
                root, _, database, run_id = message[:4]
                with closing(connect(database)) as conn, maintenance_lock(Path(root)):
                    self.assertEqual(conn.execute(
                        "UPDATE leases SET expires_at=? WHERE run_id=?",
                        ("2000-01-01T00:00:00Z", run_id),
                    ).rowcount, 1)
                    conn.commit()
                crash.set()
                worker.join(timeout=30)
                self.assertEqual(worker.exitcode, 86)
                self.assertEqual(recover_from_cli(Path(root), run_id), {
                    "run_id": run_id, "state": "abandoned", "action": "preserved_for_recovery"})
                with closing(connect(database)) as conn:
                    report = status(conn)
                item = _item(report, "spec-016-task-04")
                self.assertIn("recovery_ready:partial", item["reasons"])
                self.assertIn(item, report["eligible"])
            finally:
                crash.set()
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
                ready.close()


if __name__ == "__main__":
    unittest.main()
