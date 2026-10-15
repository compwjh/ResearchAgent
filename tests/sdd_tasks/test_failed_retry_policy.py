import json
import multiprocessing
import os
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from scripts.sdd_tasks.active_failed_recovery import ActiveFailedRecoveryError
from scripts.sdd_tasks.lease_recovery import stored_owner
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.newcli_recover import recover_from_cli
from scripts.sdd_tasks.owners import OwnerStatus, observe_owner
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_failed_claim import _active_failed_claim
from tests.sdd_tasks.test_failed_retry_crash import _crash_failed_source_claim
from tests.sdd_tasks.test_failure_history import _repo_state
from tests.sdd_tasks.test_run_owner import _rows


def _git_state(worktree):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    status = subprocess.check_output(
        ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"],
        env=env,
    )
    diff = subprocess.check_output(["git", "-C", str(worktree), "diff", "--binary", "HEAD"],
                                   env=env)
    return _repo_state(worktree), status, diff


def _ledger_state(database):
    with closing(connect(database)) as conn:
        return _rows(conn)


def _assert_refused_unchanged(test, root, worktree, database, run_id, code):
    rows, git = _ledger_state(database), _git_state(worktree)
    with test.assertRaises(ActiveFailedRecoveryError) as caught:
        recover_from_cli(Path(root), run_id)
    test.assertEqual(caught.exception.code, code)
    test.assertEqual(_ledger_state(database), rows)
    test.assertEqual(_git_state(worktree), git)


class FailedRetryPolicyTests(unittest.TestCase):
    def test_live_failed_retry_owner_is_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as temp, _active_failed_claim(temp) as data:
            root, worktree, _, database, _, _, claim = data
            self.assertIs(observe_owner(claim.owner), OwnerStatus.ALIVE)
            _assert_refused_unchanged(self, root, worktree, database, claim.run_id,
                                      "RECOVERY_OWNER_ALIVE")

    def test_dead_unexpired_and_unknown_failed_retry_owners_are_refused_read_only(self):
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as temp:
            ready, crash = context.Queue(), context.Event()
            worker = context.Process(target=_crash_failed_source_claim,
                                     args=(temp, ready, crash))
            worker.start()
            try:
                message = ready.get(timeout=120)
                self.assertNotEqual(message[0], "error", message)
                root, canonical, database, run_id, _, _ = message
                crash.set()
                worker.join(timeout=30)
                self.assertEqual(worker.exitcode, 86)
                with closing(connect(database)) as conn:
                    row = conn.execute("SELECT owner_json FROM runs WHERE run_id=?",
                                       (run_id,)).fetchone()
                    owner_json = json.loads(row[0])
                    self.assertEqual(owner_json["pid"], worker.pid)
                    owner = stored_owner(row[0])
                    self.assertIs(observe_owner(owner), OwnerStatus.DEAD)
                    expiry = conn.execute("SELECT expires_at FROM leases WHERE run_id=?",
                                          (run_id,)).fetchone()[0]
                    parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                    self.assertGreater(parsed, datetime.now(timezone.utc))
                _assert_refused_unchanged(self, root, canonical, database, run_id,
                                          "ACTIVE_FAILED_LEASE_NOT_EXPIRED")

                owner_json["host_id"] = "remote-" + owner_json["host_id"]
                raw = json.dumps(owner_json, sort_keys=True, separators=(",", ":"))
                with closing(connect(database)) as conn, maintenance_lock(Path(root)):
                    conn.execute("UPDATE runs SET owner_json=? WHERE run_id=?", (raw, run_id))
                    conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?",
                                 ("2000-01-01T00:00:00Z", run_id))
                    conn.commit()
                self.assertIs(observe_owner(stored_owner(raw)), OwnerStatus.UNKNOWN)
                _assert_refused_unchanged(self, root, canonical, database, run_id,
                                          "RECOVERY_OWNER_UNKNOWN")
            finally:
                crash.set()
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
                ready.close()


if __name__ == "__main__":
    unittest.main()
