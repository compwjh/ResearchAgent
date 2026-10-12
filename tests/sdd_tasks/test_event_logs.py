import json
import stat
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.event_logs import EventLogError, sync_event_log
from scripts.sdd_tasks.events import append_event
from scripts.sdd_tasks.leases import LeaseError
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_run_owner import _claimed, _rows


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _path(root, run_id):
    return root / ".sdd/runtime/runs" / run_id / "events.jsonl"


class EventLogTests(unittest.TestCase):
    def test_prefix_sync_replay_is_byte_stable_and_private(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, _, database, _, owner, claim = state
            path = _path(root, claim.run_id)
            with closing(connect(database)) as conn:
                sync_event_log(conn, claim.run_id, root)
                prefix = path.read_bytes()
                append_event(conn, claim.run_id, owner, "observation", {"note": "one"}, now=_now())
                complete = path.read_bytes()
                self.assertTrue(complete.startswith(prefix))
                self.assertEqual(len(complete.splitlines()), 2)
                self.assertEqual(sync_event_log(conn, claim.run_id, root), path)
                self.assertEqual(path.read_bytes(), complete)
            for directory in (root / ".sdd", root / ".sdd/runtime", root / ".sdd/runtime/runs",
                              path.parent):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_invalid_existing_logs_and_unignored_path_are_read_only(self):
        for case in ("foreign", "malformed", "symlink", "mode", "not_ignored"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, _, _, database, _, owner, claim = state
                path = _path(root, claim.run_id)
                target = Path(temp) / "outside.log"
                with closing(connect(database)) as conn:
                    append_event(conn, claim.run_id, owner, "observation", {"note": "good"}, now=_now())
                    if case == "foreign":
                        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                        records[-1]["payload"] = {"note": "foreign"}
                        path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) +
                                                 "\n" for row in records), encoding="utf-8")
                    elif case == "malformed":
                        path.write_bytes(b"{malformed}\n")
                    elif case == "symlink":
                        target.write_bytes(path.read_bytes())
                        path.unlink()
                        path.symlink_to(target)
                    elif case == "mode":
                        path.chmod(0o644)
                    elif case == "not_ignored":
                        ignore = root / ".gitignore"
                        ignore.write_text("\n".join(line for line in ignore.read_text(
                            encoding="utf-8").splitlines() if line != ".sdd/runtime/") + "\n",
                            encoding="utf-8")
                    before = _rows(conn)
                    original = target.read_bytes() if case == "symlink" else path.read_bytes()
                    with self.assertRaises(EventLogError):
                        sync_event_log(conn, claim.run_id, root)
                    self.assertEqual(_rows(conn), before)
                    if case == "symlink":
                        self.assertTrue(path.is_symlink())
                        self.assertEqual(target.read_bytes(), original)
                    else:
                        self.assertEqual(path.read_bytes(), original)

    def test_atomic_log_write_failure_keeps_committed_event_for_exact_replay(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, _, database, _, owner, claim = state
            path = _path(root, claim.run_id)
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with patch("scripts.sdd_tasks.event_logs.atomic_write", side_effect=OSError("injected")), \
                        self.assertRaises(LeaseError) as caught:
                    append_event(conn, claim.run_id, owner, "observation", {"note": "saved"}, now=_now())
                self.assertEqual(caught.exception.code, "EVENT_LOG_SYNC_FAILED")
                self.assertEqual(conn.execute("SELECT state FROM runs WHERE run_id=?",
                                              (claim.run_id,)).fetchone()[0], "running")
                self.assertEqual([row[0] for row in conn.execute(
                    "SELECT sequence FROM events WHERE run_id=? ORDER BY sequence", (claim.run_id,))], [1, 2])
                self.assertEqual(len(_rows(conn)["events"]), len(before["events"]) + 1)
                self.assertFalse(path.exists())
                sync_event_log(conn, claim.run_id, root)
                replay = path.read_bytes()
                sync_event_log(conn, claim.run_id, root)
                self.assertEqual(path.read_bytes(), replay)
                self.assertEqual(len(replay.splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
