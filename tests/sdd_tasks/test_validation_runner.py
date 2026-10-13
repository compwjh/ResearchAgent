import hashlib
import json
import os
import shlex
import tempfile
import time
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.validation_runner import ValidationRunnerError, _active_context, run_validations
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_metadata
from tests.sdd_tasks.test_catalog import _git, _repo
from tests.sdd_tasks.test_run_owner import _claimed, _rows

GATE = "spec-016.cloud-stage-authorized"


def _configured_claim(directory, commands):
    metadata = task_metadata({"validation_commands": commands})
    root, paths, _, metadata = _repo(directory, task4=metadata)
    (root / "scripts/sdd_tasks").mkdir(parents=True)
    (root / "scripts/sdd_tasks/allowed.txt").write_text("baseline\n", encoding="utf-8")
    with (root / ".gitignore").open("a", encoding="utf-8") as stream:
        stream.write(".sdd/runtime/\n")
    proof = b"gate proof\n"
    (root / "docs/sdd/gate-proof.txt").write_bytes(proof)
    entry = {"gate_id": GATE, "status": "passed", "evidence": {
        "path": "docs/sdd/gate-proof.txt", "sha256": hashlib.sha256(proof).hexdigest()}}
    (root / "docs/sdd/gate-evidence.json").write_text(
        json.dumps({"schema": "sdd-gates/v1", "gates": [entry]}), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "runner validation fixture")
    canonical = root / metadata["worktree"]["path"]
    canonical.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-b", metadata["worktree"]["branch"], str(canonical), "HEAD")
    task = parse_task(paths[metadata["task_id"]])
    snapshot = capture_snapshot(root, task)
    database = root / ".sdd/runtime/task-ledger.sqlite3"
    rebuild(database, root)
    os.chmod(database.parent, 0o700)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with closing(connect(database)) as conn, maintenance_lock(root):
        claim = claim_next(conn, [task], {GATE}, workspace_snapshots={
            task.metadata["task_id"]: snapshot}, ide="codex",
            owner=current_owner("validation-runner-test", pid=os.getpid()), now=now)
    if claim is None:
        raise AssertionError("runner fixture Task was not claimed")
    return root, canonical, task, database, claim


class ValidationContextTests(unittest.TestCase):
    def test_active_context_returns_real_baseline_without_ledger_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
            context = _active_context(task, claim, root)
            try:
                self.assertEqual(context.before.head, claim.base_commit)
                self.assertEqual(context.worktree, claim.worktree_path.resolve())
                self.assertEqual(_rows(context.conn), before)
            finally:
                context.conn.close()
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), before)

    def test_forged_task_claim_owner_pid_token_and_base_are_read_only_refusals(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
            attempts = (
                (task, replace(claim, branch=claim.branch + "-forged"), "VALIDATION_BINDING_MISMATCH"),
                (task, replace(claim, base_commit="0" * 40), "VALIDATION_BINDING_MISMATCH"),
                (task, replace(claim, attempt=claim.attempt + 1), "VALIDATION_BINDING_MISMATCH"),
                (task, replace(claim, owner=replace(claim.owner, pid=claim.owner.pid + 1)),
                 "RUN_OWNER_MISMATCH"),
                (task, replace(claim, owner=replace(claim.owner, token="f" * 64)),
                 "VALIDATION_OWNER_MISMATCH"),
                (replace(task, prompt=task.prompt + "forged"), claim, "VALIDATION_TASK_MISMATCH"),
            )
            for supplied_task, supplied_claim, code in attempts:
                with self.subTest(code=code), self.assertRaises(ValidationRunnerError) as caught:
                    _active_context(supplied_task, supplied_claim, root)
                self.assertEqual(caught.exception.code, code)
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), before)

    def test_missing_database_is_not_recreated(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, _, task, database, _, _, claim = state
            database.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(database) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            with self.assertRaises(ValidationRunnerError) as caught:
                _active_context(task, claim, root)
            self.assertEqual(caught.exception.code, "VALIDATION_DATABASE_MISSING")
            self.assertFalse(database.exists())
            self.assertFalse(Path(str(database) + "-wal").exists())
            self.assertFalse(Path(str(database) + "-shm").exists())

    def test_paused_spec_and_unsatisfied_gate_refuse_context(self):
        for change, code in (("spec", "VALIDATION_SPEC_NOT_CLAIMABLE"),
                             ("gate", "VALIDATION_GATES_UNSATISFIED")):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                root, canonical, task, _, _, _, claim = state
                if change == "spec":
                    path = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
                    path.write_text(path.read_text(encoding="utf-8").replace("已确认", "已完成", 1),
                                    encoding="utf-8")
                else:
                    path = canonical / "docs/sdd/gate-evidence.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["gates"][0]["status"] = "pending"
                    path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValidationRunnerError) as caught:
                    _active_context(task, claim, root)
                self.assertEqual(caught.exception.code, code)

    def test_run_validations_executes_all_declared_commands_and_binds_private_receipt(self):
        output_marker = "log-only-marker-9153"
        encoded = list(output_marker.encode("utf-8"))
        commands = [
            "python3 -c {}".format(shlex.quote(
                "from pathlib import Path;Path('scripts/sdd_tasks/first-ran.txt').write_text('yes')")),
            "python3 -c {}".format(shlex.quote(
                "import sys;sys.stdout.write(bytes({!r}).decode())".format(encoded))),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, claim = _configured_claim(temp, commands)
            rows, receipt = run_validations(task, claim, root, timeout_seconds=10)
            self.assertIsInstance(rows, tuple)
            self.assertEqual([row["argv"] for row in rows], [shlex.split(item) for item in commands])
            self.assertEqual([row["exit_code"] for row in rows], [0, 0])
            self.assertTrue(receipt["valid"])
            self.assertTrue((canonical / "scripts/sdd_tasks/first-ran.txt").is_file())
            self.assertEqual(receipt["validation_commands_sha256"], hashlib.sha256(
                json.dumps(commands, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")).hexdigest())
            unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
            self.assertEqual(receipt["receipt_sha256"], hashlib.sha256(json.dumps(
                unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest())
            receipt_path = root / ".sdd/runtime/runs" / claim.run_id / "validation/receipt.json"
            self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8")), receipt)
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            for record in receipt["command_logs"]:
                invocation = root / record["stdout_path"].rsplit("/", 1)[0]
                self.assertEqual(invocation.stat().st_mode & 0o777, 0o700)
                for stream in ("stdout", "stderr"):
                    log = root / record[stream + "_path"]
                    self.assertEqual(log.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(hashlib.sha256(log.read_bytes()).hexdigest(),
                                     record[stream + "_sha256"])
            output_log = root / receipt["command_logs"][1]["stdout_path"]
            self.assertEqual(output_log.read_text(encoding="utf-8"), output_marker)
            self.assertNotIn(output_marker, repr(receipt))

    def test_run_validations_records_nonzero_exit_and_still_runs_later_commands(self):
        commands = ["python3 -c {}".format(shlex.quote("raise SystemExit(7)")),
                    "python3 -c {}".format(shlex.quote(
                        "from pathlib import Path;Path('scripts/sdd_tasks/later-ran.txt').write_text('yes')"))]
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, claim = _configured_claim(temp, commands)
            rows, receipt = run_validations(task, claim, root, timeout_seconds=10)
            self.assertEqual([row["exit_code"] for row in rows], [7, 0])
            self.assertEqual([row["status"] for row in rows], ["executed", "executed"])
            self.assertEqual([row["summary"] for row in rows], ["validation failed", "validation passed"])
            self.assertFalse(receipt["valid"])
            self.assertTrue((canonical / "scripts/sdd_tasks/later-ran.txt").is_file())

    def test_run_validations_timeout_kills_child_logs_it_and_runs_next_command(self):
        child = ("from pathlib import Path;import time;"
                 "Path('scripts/sdd_tasks/child-started.txt').write_text('yes');"
                 "time.sleep(2);Path('scripts/sdd_tasks/late-child.txt').write_text('late')")
        parent = "\n".join((
            "from pathlib import Path",
            "import subprocess,sys,time",
            "subprocess.Popen([sys.executable,'-c',{}])".format(repr(child)),
            "deadline=time.monotonic()+0.5",
            "while not Path('scripts/sdd_tasks/child-started.txt').exists() and time.monotonic()<deadline:",
            "    time.sleep(0.01)",
            "print('parent-started',flush=True)",
            "time.sleep(30)",
        ))
        followup = "from pathlib import Path;Path('scripts/sdd_tasks/after-timeout.txt').write_text('yes')"
        commands = ["python3 -c {}".format(shlex.quote(parent)),
                    "python3 -c {}".format(shlex.quote(followup))]
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, claim = _configured_claim(temp, commands)
            rows, receipt = run_validations(task, claim, root, timeout_seconds=1)
            time.sleep(2.1)
            self.assertEqual([row["summary"] for row in rows],
                             ["validation timed out", "validation passed"])
            self.assertLess(rows[0]["exit_code"], 0)
            self.assertEqual(rows[1]["exit_code"], 0)
            self.assertFalse(receipt["valid"])
            self.assertTrue((canonical / "scripts/sdd_tasks/child-started.txt").is_file())
            self.assertFalse((canonical / "scripts/sdd_tasks/late-child.txt").exists())
            self.assertTrue((canonical / "scripts/sdd_tasks/after-timeout.txt").is_file())
            out = root / receipt["command_logs"][0]["stdout_path"]
            self.assertIn("parent-started", out.read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),
                             receipt["command_logs"][0]["stdout_sha256"])

    def test_run_validations_rejects_out_of_scope_command_changes(self):
        command = "python3 -c {}".format(shlex.quote(
            "from pathlib import Path;Path('unrelated.txt').write_text('outside')"))
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, claim = _configured_claim(temp, [command])
            rows, receipt = run_validations(task, claim, root, timeout_seconds=10)
            self.assertEqual((rows[0]["status"], rows[0]["exit_code"]), ("executed", 0))
            self.assertFalse(receipt["valid"])
            self.assertTrue((canonical / "unrelated.txt").is_file())

    def test_run_validations_refuses_symlinked_private_runtime_parent_before_execution(self):
        command = "python3 -c {}".format(shlex.quote(
            "from pathlib import Path;Path('scripts/sdd_tasks/should-not-run.txt').write_text('ran')"))
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, database, claim = _configured_claim(temp, [command])
            runtime = root / ".sdd/runtime"
            escaped = root / "escaped-runtime"
            escaped.mkdir()
            (runtime / "runs").symlink_to(escaped, target_is_directory=True)
            with closing(connect(database)) as conn:
                before = _rows(conn)
            with self.assertRaises(ValidationRunnerError) as caught:
                run_validations(task, claim, root, timeout_seconds=10)
            self.assertEqual(caught.exception.code, "VALIDATION_RUNTIME_NOT_IGNORED")
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), before)
            self.assertEqual(list(escaped.iterdir()), [])
            self.assertFalse((canonical / "scripts/sdd_tasks/should-not-run.txt").exists())
            self.assertFalse((runtime / "runs" / claim.run_id / "validation/receipt.json").exists())

    def test_run_validations_repeated_invocations_keep_distinct_log_directories(self):
        command = "python3 -c {}".format(shlex.quote("print('one invocation')"))
        with tempfile.TemporaryDirectory() as temp:
            root, _, task, _, claim = _configured_claim(temp, [command])
            _, first = run_validations(task, claim, root, timeout_seconds=10)
            first_path = root / first["command_logs"][0]["stdout_path"]
            _, second = run_validations(task, claim, root, timeout_seconds=10)
            second_path = root / second["command_logs"][0]["stdout_path"]
            self.assertNotEqual(first_path.parent, second_path.parent)
            self.assertTrue(first_path.is_file())
            self.assertTrue(second_path.is_file())
            latest = root / ".sdd/runtime/runs" / claim.run_id / "validation/receipt.json"
            self.assertEqual(json.loads(latest.read_text(encoding="utf-8")), second)
            self.assertEqual(first_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(second_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
