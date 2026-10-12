import json
import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks.documents import parse_task_text
from scripts.sdd_tasks.eligibility import (
    database_blockers,
    eligible_candidates,
    rank_candidates,
)
from scripts.sdd_tasks.store import connect, initialize
from tests.sdd_tasks._fixtures import task_markdown

GATE = "spec-016.cloud-stage-authorized"
NOW = "2026-10-12T00:00:00Z"


def _task(number, status="pending", priority=100, created="2026-10-11T00:00:00Z",
          dependencies=(), gates=None, limit=2, migration=None):
    overrides = {"task_id": "spec-016-task-" + number, "title": "Task " + number,
                 "status": status, "priority": priority, "created_at": created,
                 "depends_on": list(dependencies), "max_attempts": limit}
    if gates is not None:
        overrides["required_gates"] = list(gates)
    if migration is not None:
        overrides["migration_state"] = migration
    path = Path("docs/sdd/plans/016/task-{}-fixture.md".format(number))
    return parse_task_text(task_markdown(metadata_overrides=overrides), path)


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.temp.name) / "ledger.sqlite3")
        initialize(self.conn)
        self.done = _task("01", "completed")
        self.other = _task("02", priority=90)
        self.task = _task("03", priority=80, dependencies=(self.done.metadata["task_id"],))
        self.dependent = _task("04", dependencies=(self.other.metadata["task_id"],), gates=())
        self.unverified = _task("05", gates=(), migration="unverified")
        self.tasks = (self.done, self.other, self.task, self.dependent, self.unverified)
        for task in self.tasks:
            meta = task.metadata
            self.conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", (
                meta["task_id"], task.path.as_posix(), meta["status"], meta["priority"],
                meta["created_at"], task.task_hash, task.prompt_hash,
                json.dumps(meta, sort_keys=True, separators=(",", ":"))))
        for task in self.tasks:
            self.conn.executemany("INSERT INTO dependencies VALUES (?,?)", (
                (task.metadata["task_id"], dep) for dep in task.metadata["depends_on"]))

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _run(self, task, attempt, state):
        meta = task.metadata
        self.conn.execute(
            "INSERT INTO runs(run_id,task_id,attempt,state,ide,executor_id,owner_json,agent_role,"
            "worktree,branch,base_commit,task_hash,prompt_hash,claimed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("run-{}-{}".format(meta["task_id"], attempt), meta["task_id"], attempt, state,
             "codex", "tester", "{}", "backend-dev", ".worktrees/spec-016", "feature/x",
             "a" * 40, task.task_hash, task.prompt_hash, NOW))
        return "run-{}-{}".format(meta["task_id"], attempt)

    def test_recovery_priority_and_offset_timestamps_are_deterministic(self):
        early = _task("02", priority=70, created="2026-10-10T03:00:00+03:00")
        same = _task("03", priority=70, created="2026-10-10T00:00:00Z")
        high = _task("01", priority=90)
        recovered = {early.metadata["task_id"], same.metadata["task_id"]}
        order = rank_candidates((high, same, early), recovered)
        self.assertEqual([item.metadata["task_id"] for item in order], [
            "spec-016-task-02", "spec-016-task-03", "spec-016-task-01"])
        self.assertEqual([item.metadata["task_id"] for item in rank_candidates((same, early, high))], [
            "spec-016-task-01", "spec-016-task-02", "spec-016-task-03"])

    def test_dependency_gate_scope_and_migration_blockers(self):
        wrong_gate = {"spec-017.cloud-stage-authorized"}
        blockers = database_blockers(self.conn, self.task, wrong_gate, NOW)
        self.assertIn("gate_unsatisfied:" + GATE, blockers)
        self.conn.execute("UPDATE tasks SET status='pending' WHERE task_id=?",
                          (self.done.metadata["task_id"],))
        blockers = database_blockers(self.conn, self.task, {GATE}, NOW)
        self.assertIn("dependency_not_completed:" + self.done.metadata["task_id"], blockers)
        dependent = database_blockers(self.conn, self.dependent, set(), NOW)
        self.assertIn("dependency_not_completed:" + self.other.metadata["task_id"], dependent)
        self.assertIn("migration_unverified", database_blockers(self.conn, self.unverified, set(), NOW))

    def test_active_run_and_active_or_expired_lease_refuse_eligibility(self):
        task_id = self.task.metadata["task_id"]
        self._run(self.task, 1, "claimed")
        self.assertIn("active_run", database_blockers(self.conn, self.task, {GATE}, NOW))
        self.conn.execute("UPDATE runs SET state='succeeded' WHERE task_id=?", (task_id,))
        run_id = "run-{}-1".format(task_id)
        for expiry, reason in (("2026-10-13T00:00:00Z", "active_lease"),
                               ("2026-10-11T00:00:00Z", "expired_lease_requires_recovery")):
            with self.subTest(reason=reason):
                self.conn.execute("DELETE FROM leases WHERE task_id=?", (task_id,))
                self.conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)",
                                  (task_id, run_id, "token", NOW, NOW, expiry))
                self.assertIn(reason, database_blockers(self.conn, self.task, {GATE}, NOW))

    def test_consecutive_failure_limit_resets_on_nonfailed_run(self):
        for attempt, state in ((1, "failed"), (2, "failed"), (3, "succeeded"), (4, "failed")):
            self._run(self.task, attempt, state)
        blockers = database_blockers(self.conn, self.task, {GATE}, NOW)
        self.assertNotIn("max_attempts_exhausted", blockers)
        self._run(self.task, 5, "failed")
        self.assertIn("max_attempts_exhausted", database_blockers(self.conn, self.task, {GATE}, NOW))

    def test_eligible_candidates_apply_sql_blockers(self):
        candidates = eligible_candidates(self.conn, (self.dependent, self.task), {GATE}, NOW)
        self.assertEqual([item.metadata["task_id"] for item in candidates], [self.task.metadata["task_id"]])


if __name__ == "__main__":
    unittest.main()
