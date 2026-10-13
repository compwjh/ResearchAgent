import json
import os
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.leases import recover_expired
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.recovery_snapshots import load_recovery_snapshot
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import WorkspaceError, capture_snapshot, compare_snapshot
from scripts.sdd_tasks.workspace_observation import (
    WorkspaceObservationError,
    _decode_abandoned_observation_event,
    _decode_observation_event,
    _load_failed_run_baseline,
    _snapshot_values,
    _validate_snapshot_history_events,
    record_workspace_observation,
)
from tests.sdd_tasks.test_run_owner import _claimed, _rows
from tests.sdd_tasks.test_selection import GATE


def _now(offset=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


def _payload(snapshot):
    return {"schema": "sdd-workspace-observation/v1", "snapshot": _snapshot_values(snapshot)}


def _fail_run(conn, run_id, payloads, *, event_time=None):
    stamp = event_time or _now()
    ended = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=1))
    conn.execute("UPDATE runs SET state='failed',ended_at=? WHERE run_id=?",
                 (ended.isoformat().replace("+00:00", "Z"), run_id))
    for sequence, payload in enumerate(payloads, 2):
        value = payload if isinstance(payload, str) else json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                     (run_id, sequence, stamp, "workspace_observation", value))
    return stamp


def _recorded_failed(state):
    root, canonical, task, database, _, owner, claim = state
    canonical_task = parse_task(canonical / task.path.relative_to(root))
    with closing(connect(database)) as conn:
        original = load_recovery_snapshot(conn, claim.run_id, canonical_task, root)
        snapshot = capture_snapshot(root, canonical_task)
        record_workspace_observation(conn, claim.run_id, owner, snapshot, now=_now())
        stamp = conn.execute("SELECT timestamp FROM events WHERE run_id=? AND event_type=?",
                             (claim.run_id, "workspace_observation")).fetchone()[0]
        ended = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=1))
        conn.execute("UPDATE runs SET state='failed',ended_at=? WHERE run_id=?",
                     (ended.isoformat().replace("+00:00", "Z"), claim.run_id))
    return canonical_task, original


def _abandon_after_observation(state, *, partial):
    root, canonical, task, database, child, owner, claim = state
    with closing(connect(database)) as conn:
        baseline = load_recovery_snapshot(conn, claim.run_id, task, root)
        observed = capture_snapshot(root, task)
        record_workspace_observation(conn, claim.run_id, owner, observed, now=_now())
        if partial:
            (canonical / "scripts/sdd_tasks/ignored.txt").write_text(
                "partial recovery\n", encoding="utf-8")
        child.terminate()
        child.wait(timeout=10)
        recovery_time = _now()
        conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?", (_now(-1), claim.run_id))
        decision = compare_snapshot(baseline, capture_snapshot(root, task))
        with maintenance_lock(root):
            report = recover_expired(conn, claim.run_id, False, decision, now=recovery_time)
    return baseline, report


class WorkspaceObservationTests(unittest.TestCase):
    def test_active_owner_records_one_private_event_and_syncs_its_log(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, owner, claim = state
            snapshot = capture_snapshot(root, task)
            with closing(connect(database)) as conn:
                record_workspace_observation(conn, claim.run_id, owner, snapshot, now=_now())
                before_replay = _rows(conn)
                record_workspace_observation(conn, claim.run_id, owner, snapshot, now=_now())
                rows = conn.execute(
                    "SELECT sequence,event_type,payload_json FROM events WHERE run_id=? ORDER BY sequence",
                    (claim.run_id,),
                ).fetchall()
                self.assertEqual(_rows(conn), before_replay)
                self.assertEqual([(row[0], row[1]) for row in rows],
                                 [(1, "workspace_snapshot"), (2, "workspace_observation")])
                payload = json.loads(rows[1][2])
                self.assertEqual(payload, _payload(snapshot))
                self.assertNotIn(owner.token, rows[1][2])
            log = root / ".sdd/runtime/runs" / claim.run_id / "events.jsonl"
            self.assertTrue(log.is_file())
            self.assertNotIn(owner.token, log.read_text(encoding="utf-8"))

    def test_record_rejects_owner_time_and_snapshot_mismatches_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, owner, claim = state
            snapshot = capture_snapshot(root, task)
            cases = ((replace(owner, token="wrong-private-token"), snapshot, _now(),
                      "OBSERVATION_OWNER_MISMATCH"),
                     (owner, snapshot, _now(60), "OBSERVATION_TIME_IN_FUTURE"),
                     (owner, replace(snapshot, branch="feature/other"), _now(),
                      "OBSERVATION_BINDING_MISMATCH"))
            with closing(connect(database)) as conn:
                before = _rows(conn)
                for identity, captured, now, code in cases:
                    with self.subTest(code=code), self.assertRaises(WorkspaceObservationError) as error:
                        record_workspace_observation(conn, claim.run_id, identity, captured, now=now)
                    self.assertEqual(error.exception.code, code)
                    self.assertEqual(_rows(conn), before)
                with self.assertRaises(WorkspaceObservationError) as error:
                    record_workspace_observation(conn, claim.run_id, owner, snapshot,
                                                 now="2026-10-13T12:00:00+02:00")
                self.assertEqual(error.exception.code, "OBSERVATION_TIME_INVALID")
                self.assertEqual(_rows(conn), before)

    def test_record_refuses_a_snapshot_when_the_workspace_changes_after_capture(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, owner, claim = state
            snapshot = capture_snapshot(root, task)
            target = canonical / "scripts/sdd_tasks/seed.txt"
            target.write_text("changed after observation capture\n", encoding="utf-8")
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with self.assertRaises(WorkspaceObservationError) as error:
                    record_workspace_observation(conn, claim.run_id, owner, snapshot, now=_now())
                self.assertEqual(error.exception.code, "OBSERVATION_SNAPSHOT_MISMATCH")
                self.assertEqual(_rows(conn), before)

    def test_decoder_rejects_missing_duplicate_malformed_time_path_and_symlink_data(self):
        cases = ("missing", "duplicate", "duplicate_key", "constant", "fields", "time",
                 "canonical", "symlink", "status_path", "extra_owner")
        expected = {"missing": "OBSERVATION_EVENTS_INVALID", "duplicate": "OBSERVATION_EVENTS_INVALID",
                    "duplicate_key": "OBSERVATION_VALIDATION_FAILED",
                    "constant": "OBSERVATION_VALIDATION_FAILED", "fields": "OBSERVATION_PAYLOAD_INVALID",
                    "time": "OBSERVATION_TIME_INVALID", "canonical": "OBSERVATION_SNAPSHOT_MISMATCH",
                    "symlink": "OBSERVATION_VALIDATION_FAILED",
                    "status_path": "OBSERVATION_VALIDATION_FAILED",
                    "extra_owner": "OBSERVATION_PAYLOAD_INVALID"}
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, canonical, task, database, _, owner, claim = state
                snapshot = capture_snapshot(root, task)
                payload = _payload(snapshot)
                stamp = _now()
                payloads = [payload]
                if case == "missing":
                    payloads = []
                elif case == "duplicate":
                    payloads = [payload, payload]
                elif case == "duplicate_key":
                    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    key = '"schema":"sdd-workspace-observation/v1",'
                    payloads = [encoded.replace(key, key + key, 1)]
                elif case == "constant":
                    payloads = ['{"schema":NaN}']
                elif case == "fields":
                    payload["extra"] = True
                elif case == "time":
                    stamp = _now()
                    stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(
                        timezone(timedelta(hours=2))).isoformat()
                elif case == "canonical":
                    payload["snapshot"]["repo_root"] = str(root.parent)
                elif case == "symlink":
                    (canonical / "tests/sdd_tasks").mkdir(parents=True)
                    (canonical / "tests/sdd_tasks/link").symlink_to(
                        canonical / "docs/sdd/plans/016", target_is_directory=True)
                    payload["snapshot"]["allowed_hashes"]["tests/sdd_tasks/link/task-04-fixture.md"] = "a" * 64
                elif case == "status_path":
                    payload["snapshot"]["status_records"] = [str(root / "private-output.log")]
                elif case == "extra_owner":
                    payload["owner"] = {"pid": owner.pid, "token": owner.token}
                with closing(connect(database)) as conn:
                    _fail_run(conn, claim.run_id, payloads, event_time=stamp)
                    with self.assertRaises(WorkspaceObservationError) as error:
                        _decode_observation_event(conn, claim.run_id, task, root,
                                                  expected_tip=claim.base_commit)
                self.assertEqual(error.exception.code, expected[case])

    def test_recorded_observation_decodes_after_failure_and_keeps_its_original_snapshot(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, owner, claim = state
            snapshot = capture_snapshot(root, task)
            relative = "scripts/sdd_tasks/ignored.txt"
            original_hash = snapshot.allowed_hashes[relative]
            with closing(connect(database)) as conn:
                record_workspace_observation(conn, claim.run_id, owner, snapshot, now=_now())
                event = conn.execute(
                    "SELECT timestamp,payload_json FROM events WHERE run_id=? AND event_type=?",
                    (claim.run_id, "workspace_observation"),
                ).fetchone()
                payload = json.loads(event["payload_json"])
                values = payload["snapshot"]
                self.assertEqual((values["repo_root"], values["common_dir"],
                                  values["worktree_path"]),
                                 (str(snapshot.repo_root), str(snapshot.common_dir),
                                  str(snapshot.worktree_path)))
                (canonical / relative).write_text("changed after recorded snapshot\n", encoding="utf-8")
                ended = (datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")) +
                         timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
                conn.execute("UPDATE runs SET state='failed',ended_at=? WHERE run_id=?",
                             (ended, claim.run_id))
                conn.execute("UPDATE events SET payload_json='{}' WHERE run_id=? AND sequence=1",
                             (claim.run_id,))
                decoded = _decode_observation_event(conn, claim.run_id, task, root,
                                                    expected_tip=claim.base_commit)
                current = capture_snapshot(root, task)
            self.assertIs(type(decoded), type(snapshot))
            self.assertEqual(decoded, snapshot)
            self.assertEqual(decoded.allowed_hashes[relative], original_hash)
            self.assertNotEqual(current.allowed_hashes[relative], original_hash)

    def test_failed_baseline_reads_the_canonical_original_copy_without_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            canonical_task, original = _recorded_failed(state)
            relative = "scripts/sdd_tasks/ignored.txt"
            target = canonical / relative
            target.write_text("changed after terminal failure\n", encoding="utf-8")
            current = capture_snapshot(root, canonical_task)
            task_file = canonical / task.path.relative_to(root)
            log = root / ".sdd/runtime/runs" / claim.run_id / "events.jsonl"
            files_before = (task_file.read_bytes(), log.read_bytes(), target.read_bytes())
            with closing(connect(database)) as conn:
                rows_before = _rows(conn)
                initial_event = tuple(conn.execute(
                    "SELECT sequence,event_type,payload_json FROM events WHERE run_id=? AND sequence=1",
                    (claim.run_id,),
                ).fetchone())
                with self.assertRaises(WorkspaceObservationError) as error:
                    _load_failed_run_baseline(conn, claim.run_id, task, root)
                self.assertEqual(error.exception.code, "OBSERVATION_TASK_MISMATCH")
                baseline = _load_failed_run_baseline(conn, claim.run_id, canonical_task, root)
                self.assertEqual(_rows(conn), rows_before)
                self.assertEqual(tuple(conn.execute(
                    "SELECT sequence,event_type,payload_json FROM events WHERE run_id=? AND sequence=1",
                    (claim.run_id,),
                ).fetchone()), initial_event)
            self.assertEqual(baseline, original)
            self.assertNotEqual(baseline.allowed_hashes[relative], current.allowed_hashes[relative])
            self.assertEqual((task_file.read_bytes(), log.read_bytes(), target.read_bytes()), files_before)

    def test_failed_baseline_refuses_bad_history_bindings_read_only(self):
        cases = ("malformed_snapshot", "missing_observation", "duplicate_observation", "event_gap",
                 "bad_time", "run_hash", "owner", "self_cycle")
        expected = {"malformed_snapshot": "RECOVERY_EVENT_INVALID",
                    "missing_observation": "OBSERVATION_HISTORY_EVENTS_INVALID",
                    "duplicate_observation": "OBSERVATION_HISTORY_EVENTS_INVALID",
                    "event_gap": "OBSERVATION_HISTORY_EVENTS_INVALID",
                    "bad_time": "OBSERVATION_HISTORY_EVENTS_INVALID",
                    "run_hash": "OBSERVATION_HISTORY_BINDING_MISMATCH",
                    "owner": "OBSERVATION_HISTORY_OWNER_INVALID",
                    "self_cycle": "OBSERVATION_HISTORY_CYCLE"}
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, canonical, task, database, _, _, claim = state
                canonical_task, _ = _recorded_failed(state)
                task_file = canonical / task.path.relative_to(root)
                log = root / ".sdd/runtime/runs" / claim.run_id / "events.jsonl"
                files_before = (task_file.read_bytes(), log.read_bytes())
                with closing(connect(database)) as conn:
                    if case == "malformed_snapshot":
                        conn.execute("UPDATE events SET payload_json='not-json' WHERE run_id=? AND sequence=1",
                                     (claim.run_id,))
                    elif case == "missing_observation":
                        conn.execute("DELETE FROM events WHERE run_id=? AND event_type=?",
                                     (claim.run_id, "workspace_observation"))
                    elif case == "duplicate_observation":
                        event = conn.execute(
                            "SELECT timestamp,payload_json FROM events WHERE run_id=? AND event_type=?",
                            (claim.run_id, "workspace_observation"),
                        ).fetchone()
                        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                                     (claim.run_id, 3, event[0], "workspace_observation", event[1]))
                    elif case == "event_gap":
                        conn.execute("UPDATE events SET sequence=3 WHERE run_id=? AND sequence=2",
                                     (claim.run_id,))
                    elif case == "bad_time":
                        stamp = conn.execute(
                            "SELECT timestamp FROM events WHERE run_id=? AND event_type=?",
                            (claim.run_id, "workspace_observation"),
                        ).fetchone()[0]
                        ended = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) -
                                 timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
                        conn.execute("UPDATE runs SET ended_at=? WHERE run_id=?", (ended, claim.run_id))
                    elif case == "run_hash":
                        conn.execute("UPDATE runs SET task_hash=? WHERE run_id=?",
                                     ("e" * 64, claim.run_id))
                    elif case == "owner":
                        owner_json = conn.execute("SELECT owner_json FROM runs WHERE run_id=?",
                                                  (claim.run_id,)).fetchone()[0]
                        persisted = json.loads(owner_json)
                        persisted["executor_id"] = "different-executor"
                        conn.execute("UPDATE runs SET owner_json=? WHERE run_id=?",
                                     (json.dumps(persisted, sort_keys=True), claim.run_id))
                    else:
                        row = conn.execute("SELECT payload_json,timestamp FROM events WHERE run_id=? AND sequence=1",
                                           (claim.run_id,)).fetchone()
                        baseline_payload = json.loads(row[0])
                        baseline_payload["source_run_id"] = claim.run_id
                        conn.execute("UPDATE events SET payload_json=? WHERE run_id=? AND sequence=1",
                                     (json.dumps(baseline_payload, sort_keys=True), claim.run_id))
                        conn.execute("UPDATE events SET sequence=3 WHERE run_id=? AND sequence=2",
                                     (claim.run_id,))
                        claim_payload = json.dumps({"schema": "sdd-recovery-claim/v1",
                                                    "recovery_of": claim.run_id}, sort_keys=True)
                        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                                     (claim.run_id, 2, row[1], "recovery_claim", claim_payload))
                    rows_before = _rows(conn)
                    with self.assertRaises(WorkspaceError) as error:
                        _load_failed_run_baseline(conn, claim.run_id, canonical_task, root)
                    self.assertEqual(error.exception.code, expected[case])
                    self.assertEqual(_rows(conn), rows_before)
                self.assertEqual((task_file.read_bytes(), log.read_bytes()), files_before)

    def test_task05_abandons_dead_owner_after_private_observation(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, _, claim = state
            baseline, report = _abandon_after_observation(state, partial=False)
            self.assertEqual((report.run_id, report.state, report.action),
                             (claim.run_id, "abandoned", "requeued"))
            with closing(connect(database)) as conn:
                events = conn.execute(
                    "SELECT event_type,payload_json FROM events WHERE run_id=? ORDER BY sequence",
                    (claim.run_id,),
                ).fetchall()
                self.assertEqual([event[0] for event in events],
                                 ["workspace_snapshot", "workspace_observation", "recovery_decision"])
                self.assertEqual(json.loads(events[-1][1]), {
                    "schema": "sdd-run-recovery/v1", "action": "requeued", "decision": "unchanged"})
                self.assertEqual(load_recovery_snapshot(conn, claim.run_id, task, root), baseline)
                run = conn.execute("SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()
                _validate_snapshot_history_events(conn, run)
                decoded = _decode_abandoned_observation_event(
                    conn, claim.run_id, task, root, expected_tip=run["base_commit"])
                self.assertEqual((decoded.head, decoded.branch, decoded.allowed_hashes),
                                 (baseline.head, baseline.branch, baseline.allowed_hashes))

    def test_failed_baseline_copies_through_observed_abandoned_recovery_parent(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, parent = state
            baseline, report = _abandon_after_observation(state, partial=True)
            self.assertEqual((report.run_id, report.state, report.action),
                             (parent.run_id, "abandoned", "preserved_for_recovery"))
            owner = current_owner("recovery-child", pid=os.getpid())
            with closing(connect(database)) as conn:
                with maintenance_lock(root):
                    child = claim_next(conn, [task], {GATE}, workspace_snapshots={
                        task.metadata["task_id"]: baseline}, ide="codex", owner=owner, now=_now())
                self.assertIsNotNone(child)
                self.assertEqual(child.recovery_of, parent.run_id)
                observed = capture_snapshot(root, task)
                record_workspace_observation(conn, child.run_id, owner, observed, now=_now())
                stamp = conn.execute("SELECT timestamp FROM events WHERE run_id=? AND event_type=?",
                                     (child.run_id, "workspace_observation")).fetchone()[0]
                ended = datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=1)
                conn.execute("UPDATE runs SET state='failed',ended_at=? WHERE run_id=?",
                             (ended.isoformat().replace("+00:00", "Z"), child.run_id))
                canonical_task = parse_task(canonical / task.path.relative_to(root))
                copied = _load_failed_run_baseline(conn, child.run_id, canonical_task, root)
            self.assertEqual(copied, baseline)

    def test_abandoned_observation_rejects_malformed_payload_and_events_after_decision(self):
        cases = ("payload", "after_decision")
        expected = {"payload": "OBSERVATION_PAYLOAD_INVALID",
                    "after_decision": "OBSERVATION_HISTORY_DECISION_INVALID"}
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, _, task, database, _, _, claim = state
                _abandon_after_observation(state, partial=False)
                with closing(connect(database)) as conn:
                    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()
                    if case == "payload":
                        event = conn.execute("SELECT payload_json FROM events WHERE run_id=? AND event_type=?",
                                             (claim.run_id, "workspace_observation")).fetchone()
                        payload = json.loads(event[0])
                        payload["schema"] = "sdd-workspace-observation/v9"
                        conn.execute("UPDATE events SET payload_json=? WHERE run_id=? AND event_type=?",
                                     (json.dumps(payload, sort_keys=True), claim.run_id,
                                      "workspace_observation"))
                    else:
                        decision_time = conn.execute(
                            "SELECT timestamp FROM events WHERE run_id=? AND event_type=?",
                            (claim.run_id, "recovery_decision"),
                        ).fetchone()[0]
                        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                                     (claim.run_id, 4, decision_time, "diagnostic", "{}"))
                    before = _rows(conn)
                    with self.assertRaises(WorkspaceObservationError) as error:
                        if case == "payload":
                            _decode_abandoned_observation_event(
                                conn, claim.run_id, task, root, expected_tip=run["base_commit"])
                        else:
                            _validate_snapshot_history_events(conn, run)
                    self.assertEqual(error.exception.code, expected[case])
                    self.assertEqual(_rows(conn), before)
