import json
import tempfile
import unittest
import uuid
from contextlib import closing

from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_cli_claim import _invoke, _next
from tests.sdd_tasks.test_cli_recover import _process
from tests.sdd_tasks.test_selection import _fixture, _rows


class CliEventTests(unittest.TestCase):
    def test_live_owner_appends_all_frozen_events_as_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _, _, db = _fixture(temp)
            with (root / ".gitignore").open("a", encoding="utf-8") as ignore:
                ignore.write(".sdd/runtime/\n")
            child, _ = _process()
            try:
                claim_result, claim = _next(root, child.pid)
                self.assertEqual((claim_result.returncode, claim["code"]), (0, "OK"))
                run_id = claim["data"]["run_id"]
                log_path = root / ".sdd/runtime/runs" / run_id / "events.jsonl"
                with closing(connect(db)) as conn:
                    before_run = conn.execute(
                        "SELECT state,started_at,owner_json FROM runs WHERE run_id=?", (run_id,)
                    ).fetchone()
                    before_lease = conn.execute(
                        "SELECT refreshed_at,expires_at FROM leases WHERE run_id=?", (run_id,)
                    ).fetchone()
                    first_sequence = conn.execute(
                        "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (run_id,)
                    ).fetchone()[0]
                self.assertEqual((before_run["state"], before_run["started_at"]), ("claimed", None))
                owner_token = json.loads(before_run["owner_json"])["token"]
                responses = []
                for event_type in ("observation", "evidence", "decision", "action", "result", "next_step"):
                    payload = {"note": "EVENT_PAYLOAD_SENTINEL_" + event_type}
                    result, body = _invoke(
                        root, "event", "--run-id", run_id, "--executor", "fixture",
                        "--owner-pid", str(child.pid), "--type", event_type,
                        "--payload-json", json.dumps(payload),
                    )
                    self.assertEqual((result.returncode, body["ok"], body["code"], result.stderr),
                                     (0, True, "OK", ""))
                    self.assertEqual(set(body["data"]), {"run_id", "sequence", "timestamp", "event_type"})
                    self.assertEqual((body["data"]["run_id"], body["data"]["event_type"]),
                                     (run_id, event_type))
                    self.assertNotIn(payload["note"], result.stdout)
                    self.assertNotIn(str(root), result.stdout)
                    self.assertNotIn(owner_token, result.stdout)
                    responses.append((body["data"], payload))
                with closing(connect(db)) as conn:
                    run = conn.execute("SELECT state,started_at FROM runs WHERE run_id=?", (run_id,)).fetchone()
                    events = conn.execute(
                        "SELECT sequence,timestamp,event_type,payload_json FROM events "
                        "WHERE run_id=? ORDER BY sequence", (run_id,),
                    ).fetchall()
                    lease = conn.execute(
                        "SELECT refreshed_at,expires_at FROM leases WHERE run_id=?", (run_id,)
                    ).fetchone()
                public = events[-len(responses):]
                self.assertEqual((run["state"], run["started_at"]), ("running", responses[0][0]["timestamp"]))
                self.assertEqual([row["sequence"] for row in public],
                                 list(range(first_sequence, first_sequence + len(responses))))
                self.assertEqual([row["event_type"] for row in public],
                                 [item[0]["event_type"] for item in responses])
                self.assertEqual([json.loads(row["payload_json"]) for row in public],
                                 [item[1] for item in responses])
                self.assertEqual(lease["refreshed_at"], responses[-1][0]["timestamp"])
                self.assertGreater(lease["expires_at"], before_lease["expires_at"])
                records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([record["sequence"] for record in records],
                                 [row["sequence"] for row in events])
                self.assertEqual(records[-len(responses):][0]["payload"], responses[0][1])
                self.assertNotIn(owner_token, log_path.read_text(encoding="utf-8"))
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def test_invalid_owner_and_payloads_do_not_echo_or_mutate_ledger_or_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _, _, db = _fixture(temp)
            child, _ = _process()
            try:
                _, claim = _next(root, child.pid)
                run_id = claim["data"]["run_id"]
                log_path = root / ".sdd/runtime/runs" / run_id / "events.jsonl"
                before, log_before = _rows(db), (log_path.exists(), log_path.read_bytes() if log_path.exists() else b"")
                cases = (
                    ("other", "fixture-foreign", json.dumps({"note": "REFUSAL_SENTINEL"}),
                     "RUN_OWNER_MISMATCH", 4),
                    ("duplicate", "fixture", '{"item":1,"item":2}', "EVENT_PAYLOAD_INVALID", 2),
                    ("nan", "fixture", '{"item":NaN}', "EVENT_PAYLOAD_INVALID", 2),
                    ("array", "fixture", "[]", "EVENT_PAYLOAD_INVALID", 2),
                    ("credential", "fixture", json.dumps({"api_key": "EVENT_SECRET_SENTINEL"}),
                     "EVENT_PAYLOAD_UNSAFE", 6),
                    ("owner", "fixture", json.dumps({"owner_token": "EVENT_OWNER_SENTINEL"}),
                     "EVENT_PAYLOAD_UNSAFE", 6),
                    ("private_path", "fixture", json.dumps({"path": str(root / ".sdd/runtime/private")} ),
                     "EVENT_PAYLOAD_UNSAFE", 6),
                )
                for name, executor, raw_payload, code, exit_code in cases:
                    with self.subTest(case=name):
                        result, body = _invoke(
                            root, "event", "--run-id", run_id, "--executor", executor,
                            "--owner-pid", str(child.pid), "--type", "observation",
                            "--payload-json", raw_payload,
                        )
                        output = result.stdout + result.stderr
                        self.assertEqual((result.returncode, body["ok"], body["code"], body["data"]),
                                         (exit_code, False, code, None))
                        for sentinel in ("REFUSAL_SENTINEL", "EVENT_SECRET_SENTINEL", "EVENT_OWNER_SENTINEL",
                                         str(root)):
                            self.assertNotIn(sentinel, output)
                        self.assertEqual(_rows(db), before)
                        self.assertEqual((log_path.exists(), log_path.read_bytes() if log_path.exists() else b""),
                                         log_before)
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def test_invalid_json_precedes_missing_database_and_valid_event_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _, _, db = _fixture(temp)
            with (root / ".gitignore").open("a", encoding="utf-8") as ignore:
                ignore.write(".sdd/runtime/\n")
            child, _ = _process()
            try:
                run_id = str(uuid.uuid4())
                db.unlink()
                for sidecar in (db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
                    if sidecar.exists():
                        sidecar.unlink()
                for raw in ('{"item":1,"item":2}', '{"item":NaN}', '[]'):
                    result, body = _invoke(
                        root, "event", "--run-id", run_id, "--executor", "fixture",
                        "--owner-pid", str(child.pid), "--type", "observation", "--payload-json", raw,
                    )
                    self.assertEqual((result.returncode, body["code"], body["data"]),
                                     (2, "EVENT_PAYLOAD_INVALID", None))
                    self.assertNotIn(str(root), result.stdout + result.stderr)
                    self.assertFalse(db.exists())
                result, body = _invoke(
                    root, "event", "--run-id", run_id, "--executor", "fixture",
                    "--owner-pid", str(child.pid), "--type", "observation", "--payload-json", '{"item":1}',
                )
                self.assertEqual((result.returncode, body["code"], body["data"]),
                                 (3, "CATALOG_NOT_REBUILT", None))
                self.assertNotIn(str(root), result.stdout + result.stderr)
                self.assertFalse(db.exists())
                self.assertFalse(db.with_name(db.name + "-wal").exists())
                self.assertFalse(db.with_name(db.name + "-shm").exists())
                self.assertFalse((root / ".sdd/runtime/runs" / run_id).exists())
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
