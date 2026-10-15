import json
import multiprocessing
import os
import tempfile
import traceback
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.lease_recovery import stored_owner
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.newcli_claim import claim_from_cli
from scripts.sdd_tasks.newcli_recover import recover_from_cli
from scripts.sdd_tasks.owners import OwnerStatus, observe_owner
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_prepare import SOURCE
from tests.sdd_tasks.test_failed_claim import _active_failed_claim


def _crash_failed_source_claim(directory, ready, crash):
    try:
        with _active_failed_claim(directory) as data:
            root, worktree, _, database, source_id, selected, claim = data
            ready.put((str(root), str(worktree.resolve()), str(database), claim.run_id,
                       source_id, selected.proof.original_base))
            if not crash.wait(timeout=120):
                os._exit(87)
            os._exit(86)
    except Exception as exc:
        ready.put(("error", repr(exc)))
        raise


class FailedRetryCrashTests(unittest.TestCase):
    def test_dead_failed_source_retry_recovers_through_partial_chain(self):
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as temp:
            ready, crash = context.Queue(), context.Event()
            worker = context.Process(target=_crash_failed_source_claim,
                                     args=(temp, ready, crash))
            worker.start()
            try:
                message = ready.get(timeout=120)
                self.assertNotEqual(message[0], "error", message)
                root, canonical, database, dead_run, source_id, original_base = message
                self.assertEqual(worker.exitcode, None)
                with closing(connect(database)) as conn, maintenance_lock(Path(root)):
                    row = conn.execute("SELECT owner_json FROM runs WHERE run_id=?",
                                       (dead_run,)).fetchone()
                    self.assertIsNotNone(row)
                    owner_json = json.loads(row[0])
                    self.assertEqual(owner_json["pid"], worker.pid)
                    before_event = conn.execute(
                        "SELECT payload_json FROM events WHERE run_id=? "
                        "AND event_type='workspace_snapshot'", (dead_run,),
                    ).fetchone()
                    original_event = json.loads(before_event[0])
                    self.assertEqual(original_event["source_run_id"], source_id)
                    self.assertEqual(original_event["snapshot"]["head"], original_base)
                    self.assertEqual(conn.execute(
                        "UPDATE leases SET expires_at=? WHERE run_id=?",
                        ("2000-01-01T00:00:00Z", dead_run),
                    ).rowcount, 1)
                    conn.commit()
                crash.set()
                worker.join(timeout=30)
                self.assertEqual(worker.exitcode, 86)
                owner_status = observe_owner(stored_owner(json.dumps(owner_json)))
                self.assertIs(owner_status, OwnerStatus.DEAD)
                self.assertFalse((Path(root) / ".sdd/runtime/runs" / dead_run /
                                  "completion.json").exists())

                try:
                    recovered = recover_from_cli(Path(root), dead_run)
                except Exception:
                    self.fail("recover_from_cli failed; owner_pid={}, owner_status={}, "
                              "failed_source_id={}, snapshot_head={}, original_base={}, "
                              "source_bytes={!r}\n{}".format(
                                  owner_json["pid"], owner_status.value, source_id,
                                  original_event["snapshot"]["head"], original_base,
                                  (Path(canonical) / SOURCE).read_bytes(),
                                  traceback.format_exc()))
                self.assertEqual(recovered, {"run_id": dead_run, "state": "abandoned",
                                             "action": "preserved_for_recovery"})
                next_claim, blockers = claim_from_cli(Path(root), "codex", "retry-after-crash",
                                                       os.getpid())
                self.assertIsNone(blockers)
                self.assertIsNotNone(next_claim)
                self.assertEqual((next_claim["recovery_of"], next_claim["base_commit"]),
                                 (dead_run, original_base))
                with closing(connect(database)) as conn:
                    after_event = conn.execute(
                        "SELECT payload_json FROM events WHERE run_id=? "
                        "AND event_type='workspace_snapshot'", (next_claim["run_id"],),
                    ).fetchone()
                    rehydrated = json.loads(after_event[0])
                self.assertEqual(rehydrated["source_run_id"], dead_run)
                self.assertEqual(rehydrated["snapshot"], original_event["snapshot"])
                self.assertEqual((Path(canonical) / SOURCE).read_bytes(),
                                 b"partial source change\n")
            finally:
                crash.set()
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
                ready.close()


if __name__ == "__main__":
    unittest.main()
