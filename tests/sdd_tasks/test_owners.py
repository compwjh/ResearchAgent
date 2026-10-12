import subprocess
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from scripts.sdd_tasks.owners import OwnerStatus, current_owner, observe_owner


@unittest.skipUnless(sys.platform.startswith("linux"), "uses Linux process start identity")
class OwnerObservationTests(unittest.TestCase):
    def child(self):
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def test_real_child_live_exit_and_token_privacy(self):
        process = self.child()
        try:
            owner = current_owner("fixture-executor", pid=process.pid)
            self.assertEqual(observe_owner(owner), OwnerStatus.ALIVE)
            self.assertNotIn(owner.token, repr(owner))
            process.terminate()
            process.wait(timeout=5)
            self.assertEqual(observe_owner(owner), OwnerStatus.DEAD)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_live_pid_with_start_mismatch_and_remote_host_are_not_alive(self):
        process = self.child()
        try:
            owner = current_owner("fixture-executor", pid=process.pid)
            stamp = owner.process_started_at
            changed = stamp[:-1] + ("0" if stamp[-1] != "0" else "1")
            self.assertEqual(observe_owner(replace(owner, process_started_at=changed)), OwnerStatus.DEAD)
            self.assertEqual(observe_owner(replace(owner, host_id="remote-" + owner.host_id)), OwnerStatus.UNKNOWN)
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_malformed_owner_and_probe_os_error_are_unknown(self):
        process = self.child()
        try:
            owner = current_owner("fixture-executor", pid=process.pid)
            self.assertEqual(observe_owner(replace(owner, process_started_at="")), OwnerStatus.UNKNOWN)
            with patch("scripts.sdd_tasks.owners._process_start", side_effect=OSError("probe denied")):
                self.assertEqual(observe_owner(owner), OwnerStatus.UNKNOWN)
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
