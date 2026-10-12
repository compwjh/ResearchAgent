import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import snapshot_payload
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_cli_recover import _process, _seed
from tests.sdd_tasks.test_selection import _fixture, _rows

CODE_ROOT = Path(__file__).resolve().parents[2]
GATE = "spec-016.cloud-stage-authorized"


def _invoke(root, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CODE_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-m", "scripts.sdd_tasks", "--repo", str(root), *args],
                            cwd=str(root), env=env, capture_output=True, text=True)
    if len(result.stdout.splitlines()) != 1:
        raise AssertionError("CLI must emit one JSON line: " + result.stdout + result.stderr)
    return result, json.loads(result.stdout)


def _next(root, pid):
    return _invoke(root, "next", "--claim", "--ide", "codex", "--executor", "fixture",
                   "--owner-pid", str(pid))


def _add_lower_priority_candidate(root, task):
    metadata = dict(task.metadata)
    metadata.update({"task_id": "spec-017-task-01", "spec_id": "017",
                     "title": "Lower priority candidate",
                     "priority": 10, "required_gates": [],
                     "worktree": {"path": ".worktrees/spec-017",
                                  "branch": "feature/spec-017-lower", "mode": "per_spec",
                                  "base_rule": "explicit_commit"}})
    relative = Path("docs/sdd/plans/017/task-01-lower.md")
    document = root / relative
    spec = root / "docs/sdd/specs/017-lower-candidate.md"
    document.parent.mkdir(parents=True)
    readme = document.parent / "README.md"
    row_spec = "| 01 | Lower priority candidate | [Task](../plans/017/task-01-lower.md) | 03 | 待执行 |\n"
    row_readme = "| 01 | Lower priority candidate | [Task](./task-01-lower.md) | 03 | 待执行 |\n"
    header = "| NN | Task | 文档 | 依赖 | 状态 |\n|---|---|---|---|---|\n"
    gates = root / "docs/sdd/gate-evidence.json"
    gate_registry = json.loads(gates.read_text(encoding="utf-8"))
    gate_registry["gates"] = []
    gates.write_text(json.dumps(gate_registry), encoding="utf-8")
    spec.write_text("# Spec 017 fixture\n\n## 状态\n\n**当前状态：`已确认`**\n\n" +
                    header + row_spec, encoding="utf-8")
    readme.write_text("# Tasks\n\n" + header + row_readme, encoding="utf-8")
    document.write_text("# Lower priority candidate\n> 当前状态：`待执行`\n\n" +
                        task_markdown(metadata), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", relative.as_posix(),
                    "docs/sdd/specs/017-lower-candidate.md", readme.relative_to(root).as_posix(),
                    gates.relative_to(root).as_posix()], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "add lower candidate"],
                   check=True, capture_output=True)
    worktree = root / metadata["worktree"]["path"]
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-b",
                    metadata["worktree"]["branch"], str(worktree), "HEAD"], check=True,
                   capture_output=True)
    return worktree, metadata["task_id"]


class CliClaimTests(unittest.TestCase):
    def test_real_cli_claims_once_then_reports_no_task_privately(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, task, snapshot, db = _fixture(td)
            result, body = _next(root, os.getpid())
            self.assertEqual((result.returncode, body["ok"], body["code"], result.stderr),
                             (0, True, "OK", ""))
            data, raw = body["data"], result.stdout
            self.assertEqual(data["task_id"], task.metadata["task_id"])
            self.assertEqual(data["worktree"], task.metadata["worktree"]["path"])
            self.assertEqual(data["branch"], snapshot.branch)
            self.assertEqual(data["base_commit"], snapshot.head)
            self.assertEqual(data["task_hash"], task.task_hash)
            self.assertRegex(data["prompt_hash"], r"^[0-9a-f]{64}$")
            self.assertIsNone(data["prompt_path"])
            self.assertNotEqual(uuid.UUID(data["run_id"]).int, 0)
            self.assertNotIn(str(root), raw)
            self.assertNotIn("owner", raw.lower())
            before = _rows(db)
            second, empty = _next(root, os.getpid())
            self.assertEqual((second.returncode, empty["code"]), (0, "NO_TASK"))
            self.assertIsInstance(empty["data"], dict)
            self.assertEqual(empty["data"]["eligible"], [])
            running = next(item for item in empty["data"]["running"]
                           if item["task_id"] == task.metadata["task_id"])
            self.assertEqual(set(running["reasons"]), {"run_state:claimed", "active_lease"})
            self.assertEqual(_rows(db), before)

    def test_gate_blocked_status_shows_reason_matrix(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, _, db = _fixture(td)
            registry = canonical / "docs/sdd/gate-evidence.json"
            evidence = json.loads(registry.read_text(encoding="utf-8"))
            evidence["gates"][0]["status"] = "failed"
            registry.write_text(json.dumps(evidence), encoding="utf-8")
            before = _rows(db)
            result, body = _invoke(root, "status", "--json")
            self.assertEqual((result.returncode, body["code"], result.stderr), (0, "OK", ""))
            row = next(item for item in body["data"]["waiting"] if item["task_id"] == task.metadata["task_id"])
            self.assertIn("gate_unsatisfied:" + GATE, row["reasons"])
            self.assertEqual(_rows(db), before)

    def test_dirty_worktree_and_bad_owner_create_no_run(self):
        for kind in ("dirty", "owner"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                root, canonical, _, _, db = _fixture(td)
                if kind == "dirty":
                    (canonical / "unrelated.txt").write_text("preserve\n", encoding="utf-8")
                before = _rows(db)
                result, body = _next(root, 2147483647 if kind == "owner" else os.getpid())
                if kind == "dirty":
                    self.assertEqual((result.returncode, body["code"]), (5, "workspace_worktree_dirty"))
                    self.assertEqual((canonical / "unrelated.txt").read_text(encoding="utf-8"), "preserve\n")
                else:
                    self.assertEqual((result.returncode, body["code"]), (4, "owner_process_not_alive"))
                self.assertEqual(_rows(db), before)

    def test_committed_pending_spec_prevents_cli_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, _, db = _fixture(td)
            spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace("已确认", "待确认", 1), encoding="utf-8")
            subprocess.run(["git", "-C", str(canonical), "add", "docs/sdd/specs/016-portable-task-ledger.md"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(canonical), "commit", "-qm", "pending Spec"], check=True)
            rebuild(db, root)
            before = _rows(db)
            result, body = _next(root, os.getpid())
            self.assertEqual((result.returncode, body["code"]), (0, "NO_TASK"))
            row = next(item for item in body["data"]["waiting"]
                       if item["task_id"] == task.metadata["task_id"])
            self.assertEqual(row["reasons"], ["spec_not_claimable:待确认"])
            self.assertEqual(_rows(db), before)

    def test_gate_blocked_dirty_priority_candidate_is_skipped_for_lower_eligible_task(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, _, db = _fixture(td)
            lower, lower_id = _add_lower_priority_candidate(root, task)
            rebuild(db, root)
            registry = canonical / "docs/sdd/gate-evidence.json"
            evidence = json.loads(registry.read_text(encoding="utf-8"))
            evidence["gates"][0]["status"] = "failed"
            registry.write_text(json.dumps(evidence), encoding="utf-8")
            unrelated = canonical / "unrelated.txt"
            unrelated.write_text("preserve\n", encoding="utf-8")

            result, body = _next(root, os.getpid())
            self.assertEqual((result.returncode, body["ok"], body["code"]), (0, True, "OK"))
            self.assertEqual((body["data"]["task_id"], body["data"]["worktree"]),
                             (lower_id, ".worktrees/spec-017"))
            self.assertEqual(body["data"]["branch"], "feature/spec-017-lower")
            runs = next(rows for table, rows in _rows(db) if table == "runs")
            leases = next(rows for table, rows in _rows(db) if table == "leases")
            self.assertEqual((len(runs), runs[0][1], runs[0][3]), (1, lower_id, "claimed"))
            self.assertEqual((len(leases), leases[0][0]), (1, lower_id))
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve\n")

            status_result, matrix = _invoke(root, "status", "--json")
            self.assertEqual((status_result.returncode, matrix["code"]), (0, "OK"))
            blocked = next(item for item in matrix["data"]["waiting"]
                           if item["task_id"] == task.metadata["task_id"])
            self.assertIn("gate_unsatisfied:" + GATE, blocked["reasons"])

    def test_real_cli_resumes_partial_expired_run_once_with_original_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root, canonical, task, before, db = _fixture(td)
            child, owner = _process()
            target = canonical / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial\n", encoding="utf-8")
            try:
                with closing(connect(db)) as conn:
                    parent = _seed(conn, task, before, owner)
                child.terminate()
                child.wait(timeout=10)
                recovery, recovered = _invoke(root, "recover", "--run-id", parent)
                self.assertEqual((recovery.returncode, recovered["code"],
                                  recovered["data"]["action"]),
                                 (0, "OK", "preserved_for_recovery"))

                result, claim = _next(root, os.getpid())
                self.assertEqual((result.returncode, claim["code"]), (0, "OK"))
                data = claim["data"]
                self.assertEqual((data["attempt"], data["recovery_of"], data["base_commit"],
                                  data["branch"]), (2, parent, before.head, before.branch))
                self.assertEqual(target.read_text(encoding="utf-8"), "partial\n")
                with closing(connect(db)) as conn:
                    runs = conn.execute("SELECT run_id,attempt,state,base_commit FROM runs ORDER BY attempt").fetchall()
                    event_rows = conn.execute(
                        "SELECT run_id,event_type,payload_json FROM events ORDER BY run_id,sequence").fetchall()
                self.assertEqual([(row[0], row[1], row[2], row[3]) for row in runs],
                                 [(parent, 1, "abandoned", before.head),
                                  (data["run_id"], 2, "claimed", before.head)])
                child_events = [json.loads(row[2]) for row in event_rows if row[0] == data["run_id"]]
                self.assertEqual(child_events[0]["source_run_id"], parent)
                self.assertEqual(child_events[0]["snapshot"], snapshot_payload(before)["snapshot"])
                self.assertEqual(child_events[1], {"schema": "sdd-recovery-claim/v1",
                                                   "recovery_of": parent})

                unchanged = _rows(db)
                repeated, empty = _next(root, os.getpid())
                self.assertEqual((repeated.returncode, empty["code"]), (0, "NO_TASK"))
                running = next(item for item in empty["data"]["running"]
                               if item["task_id"] == task.metadata["task_id"])
                self.assertEqual(set(running["reasons"]), {"run_state:claimed", "active_lease"})
                self.assertEqual(_rows(db), unchanged)
                self.assertEqual(target.read_text(encoding="utf-8"), "partial\n")
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
