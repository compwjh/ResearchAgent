import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.sdd_tasks.events import append_event
from scripts.sdd_tasks.leases import LeaseError
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_run_owner import _claimed, _rows


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventTests(unittest.TestCase):
    def test_public_events_start_run_and_refresh_lease_in_sequence(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, _, _, database, _, owner, claim = state
            kinds = ("observation", "evidence", "decision", "action", "result", "next_step")
            with closing(connect(database)) as conn:
                initial = conn.execute("SELECT sequence,event_type FROM events WHERE run_id=?",
                                       (claim.run_id,)).fetchall()
                self.assertEqual([tuple(row) for row in initial], [(1, "workspace_snapshot")])
                appended = [append_event(conn, claim.run_id, owner, kind, {"note": kind}, now=_now())
                            for kind in kinds]
                self.assertEqual([event.sequence for event in appended], list(range(2, 8)))
                self.assertEqual([event.event_type for event in appended], list(kinds))
                run = conn.execute("SELECT state,started_at FROM runs WHERE run_id=?",
                                   (claim.run_id,)).fetchone()
                self.assertEqual((run["state"], run["started_at"]), ("running", appended[0].timestamp))
                lease = conn.execute("SELECT refreshed_at,expires_at FROM leases WHERE run_id=?",
                                     (claim.run_id,)).fetchone()
                expected = (datetime.fromisoformat(appended[-1].timestamp.replace("Z", "+00:00")) +
                            timedelta(minutes=120)).isoformat().replace("+00:00", "Z")
                self.assertEqual(lease["refreshed_at"], appended[-1].timestamp)
                self.assertEqual(lease["expires_at"], expected)
                self.assertEqual(conn.execute("SELECT started_at FROM runs WHERE run_id=?",
                                              (claim.run_id,)).fetchone()[0], appended[0].timestamp)

    def test_rejections_preserve_events_run_and_lease(self):
        cases = ("private_fields", "owner_token_text", "credential", "reserved_type",
                 "malformed_json", "nonobject", "future", "wrong_owner", "wrong_token",
                 "expired", "outer_transaction")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                _, _, _, database, _, owner, claim = state
                event_type, payload, now, identity = "observation", {"note": "safe"}, _now(), owner
                with closing(connect(database)) as conn:
                    if case == "private_fields":
                        payload = {"metadata": {"owner": {"pid": owner.pid}}}
                    elif case == "owner_token_text":
                        payload = {"note": owner.token}
                    elif case == "credential":
                        payload = {"api_key": "fixture-secret"}
                    elif case == "reserved_type":
                        event_type = "workspace_snapshot"
                    elif case == "malformed_json":
                        payload = {"value": {1, 2}}
                    elif case == "nonobject":
                        payload = []
                    elif case == "future":
                        now = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
                    elif case == "wrong_owner":
                        identity = replace(owner, process_started_at="other-process-start")
                    elif case == "wrong_token":
                        identity = replace(owner, token="other-private-token")
                    elif case == "expired":
                        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace(
                            "+00:00", "Z")
                        conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?", (old, claim.run_id))
                    elif case == "outer_transaction":
                        conn.execute("BEGIN")
                    before = _rows(conn)
                    with self.assertRaises(LeaseError):
                        append_event(conn, claim.run_id, identity, event_type, payload, now=now)
                    self.assertEqual(_rows(conn), before)
                    if conn.in_transaction:
                        conn.rollback()

    def test_event_insert_failure_rolls_back_start_lease_and_event(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, _, _, database, _, owner, claim = state
            with closing(connect(database)) as conn:
                conn.execute("CREATE TRIGGER reject_event BEFORE INSERT ON events "
                             "WHEN NEW.event_type='observation' BEGIN "
                             "SELECT RAISE(ABORT,'fixture failure'); END")
                before = _rows(conn)
                with self.assertRaises(LeaseError) as caught:
                    append_event(conn, claim.run_id, owner, "observation", {"note": "safe"}, now=_now())
                self.assertEqual(caught.exception.code, "EVENT_STORE_ERROR")
                self.assertEqual(_rows(conn), before)
                run = conn.execute("SELECT state,started_at FROM runs WHERE run_id=?",
                                   (claim.run_id,)).fetchone()
                self.assertEqual((run["state"], run["started_at"]), ("claimed", None))


if __name__ == "__main__":
    unittest.main()
