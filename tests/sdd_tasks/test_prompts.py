import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.catalog import CatalogError, rebuild
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.prompts import PromptError, render_prompt
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot, snapshot_payload
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_recovery_claim import _claim as recovery_claim
from tests.sdd_tasks.test_recovery_claim import _dead_owner, _recover, _seed
from tests.sdd_tasks.test_selection import _fixture

GATE = "spec-016.cloud-stage-authorized"
NOW = "2026-10-12T00:00:00Z"


def _template(task):
    return "\n".join((
        "Role: " + task.metadata["agent_role"],
        'Read: ["scripts/sdd_tasks"]',
        "Allowed paths: [\"scripts/sdd_tasks\", \"tests/sdd_tasks\"]",
        "Forbidden: Do not push, merge, reset, stash, or clean.",
        'Validation: ["python3 -m unittest tests.sdd_tasks.test_store"]',
        "Result: Run {{RUN_ID}} in {{WORKTREE}} at {{BASE_COMMIT}}; "
        "write {{RESULT_PATH}} and append {{EVENT_PATH}}.",
        "Return schema: sdd-run-result/v1", "Return a brief handoff summary.",
    ))


def _install_template(root, canonical, db, task, template):
    relative = Path("docs/sdd/plans/016/task-04-fixture.md")
    content = "# {}\n> 当前状态：`待执行`\n\n{}".format(
        task.metadata["title"], task_markdown(task.metadata, prompt=template))
    for repository in (root, canonical):
        (repository / relative).write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", relative.as_posix()],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "update Prompt fixture"],
                       check=True, capture_output=True)
    rebuild(db, root)
    live = parse_task(canonical / relative)
    return live, capture_snapshot(root, live)


def _claim(root, db, task, snapshot, owner=None):
    owner = owner or current_owner("prompt-render-tests", pid=os.getpid())
    with closing(connect(db)) as conn, maintenance_lock(root):
        return claim_next(conn, [task], {GATE}, workspace_snapshots={
            task.metadata["task_id"]: snapshot}, ide="codex", owner=owner, now=NOW)


class PromptRenderingTests(unittest.TestCase):
    def test_real_claim_renders_exact_whitelist_privately_without_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            template = _template(task)
            task, snapshot = _install_template(root, canonical, db, task, template)
            template = task.prompt
            claim = _claim(root, db, task, snapshot)
            self.assertIsNotNone(claim)
            runtime = root / ".sdd/runtime"
            with patch.dict(os.environ, {"PROMPT_TEST_ENV": "PROMPT_TEST_SECRET_SENTINEL"}):
                rendered = render_prompt(task, claim, snapshot, runtime)
            run_path = ".sdd/runtime/runs/" + claim.run_id
            values = {"RUN_ID": claim.run_id, "WORKTREE": task.metadata["worktree"]["path"],
                      "BASE_COMMIT": snapshot.head, "RESULT_PATH": run_path + "/result.json",
                      "EVENT_PATH": run_path + "/events.jsonl"}
            expected = template
            for name, value in values.items():
                expected = expected.replace("{{" + name + "}}", value)
            self.assertEqual(rendered.text, expected)
            self.assertEqual(rendered.template_hash,
                             hashlib.sha256(template.encode("utf-8")).hexdigest())
            self.assertEqual(rendered.template_hash, task.prompt_hash)
            self.assertEqual(rendered.rendered_hash,
                             hashlib.sha256(expected.encode("utf-8")).hexdigest())
            self.assertEqual(rendered.path, runtime / "runs" / claim.run_id / "prompt.md")
            self.assertEqual(rendered.path.read_text(encoding="utf-8"), expected)
            self.assertEqual(stat.S_IMODE((runtime / "runs" / claim.run_id).stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(rendered.path.stat().st_mode), 0o600)
            self.assertNotIn("PROMPT_TEST_SECRET_SENTINEL", rendered.text)
            self.assertEqual(sorted(path.name for path in rendered.path.parent.iterdir()), ["prompt.md"])

    def test_rejects_forged_bindings_stale_task_and_noncanonical_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, snapshot, db = _fixture(temp)
            claim = _claim(root, db, task, snapshot)
            runtime = root / ".sdd/runtime"
            for changed_claim, changed_snapshot in (
                    (replace(claim, base_commit="0" * 40), snapshot),
                    (claim, replace(snapshot, worktree_path=root))):
                with self.subTest(snapshot=changed_snapshot.worktree_path), self.assertRaises(PromptError) as caught:
                    render_prompt(task, changed_claim, changed_snapshot, runtime)
                self.assertEqual(caught.exception.code, "PROMPT_BINDING_MISMATCH")
            with self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, root / "outside-runtime")
            self.assertEqual(caught.exception.code, "PROMPT_RUNTIME_ROOT_INVALID")

            path = canonical / task.path.relative_to(root)
            path.write_text(path.read_text(encoding="utf-8").replace(
                "Return a brief handoff summary.", "Return a concise handoff summary."), encoding="utf-8")
            with self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, runtime)
            self.assertEqual(caught.exception.code, "CANONICAL_TASK_HASH_MISMATCH")

    def test_rejects_unknown_unresolved_and_sensitive_task_templates(self):
        cases = (("{{UNKNOWN}}", "TASK_DOCUMENT_INVALID"),
                 ("{{RUN_ID", "TASK_DOCUMENT_INVALID"),
                 ("sk-abcdefghijkl", "TASK_SENSITIVE_CONTENT"))
        for fragment, code in cases:
            with self.subTest(fragment=fragment), tempfile.TemporaryDirectory() as temp:
                root, canonical, task, _, db = _fixture(temp)
                with self.assertRaises(CatalogError) as caught:
                    _install_template(root, canonical, db, task, _template(task) + "\n" + fragment)
                self.assertEqual(caught.exception.code, code)

    def test_refuses_symlinked_private_run_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, task, snapshot, db = _fixture(temp)
            claim = _claim(root, db, task, snapshot)
            runtime, outside = root / ".sdd/runtime", Path(temp) / "outside"
            outside.mkdir()
            (runtime / "runs").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, runtime)
            self.assertEqual(caught.exception.code, "PROMPT_RUN_DIR_UNSAFE")
            self.assertEqual(list(outside.iterdir()), [])

    def test_partial_recovery_renders_from_preserved_original_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            task, before = _install_template(root, canonical, db, task, _template(task))
            with closing(connect(db)) as conn:
                parent = _seed(conn, task, before, _dead_owner())
            target = before.worktree_path / "scripts/sdd_tasks/allowed.txt"
            target.write_text("partial work\n", encoding="utf-8")
            report = _recover(root, db, task, parent, before)
            self.assertEqual((report.state, report.action), ("abandoned", "preserved_for_recovery"))
            claim = recovery_claim(root, db, task, before)
            self.assertEqual((claim.recovery_of, claim.base_commit), (parent, before.head))
            rendered = render_prompt(task, claim, before, root / ".sdd/runtime")
            expected = task.prompt
            relative = ".sdd/runtime/runs/" + claim.run_id
            values = {"RUN_ID": claim.run_id, "WORKTREE": task.metadata["worktree"]["path"],
                      "BASE_COMMIT": before.head, "RESULT_PATH": relative + "/result.json",
                      "EVENT_PATH": relative + "/events.jsonl"}
            for name, value in values.items():
                expected = expected.replace("{{" + name + "}}", value)
            self.assertEqual(rendered.text, expected)
            with closing(connect(db)) as conn:
                payload = conn.execute(
                    "SELECT payload_json FROM events WHERE run_id=? AND event_type='workspace_snapshot'",
                    (claim.run_id,)).fetchone()[0]
            snapshot_event = json.loads(payload)
            self.assertEqual(snapshot_event["source_run_id"], parent)
            self.assertEqual(snapshot_event["snapshot"], snapshot_payload(before)["snapshot"])
            self.assertEqual(target.read_text(encoding="utf-8"), "partial work\n")

    def test_paused_spec_after_claim_blocks_prompt_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            task, snapshot = _install_template(root, canonical, db, task, _template(task))
            claim = _claim(root, db, task, snapshot)
            spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
            source = spec.read_text(encoding="utf-8")
            self.assertIn("**当前状态：`已确认`**", source)
            spec.write_text(source.replace("**当前状态：`已确认`**",
                                           "**当前状态：`待确认`**", 1), encoding="utf-8")
            runtime = root / ".sdd/runtime"
            self.assertFalse((runtime / "runs").exists())
            with self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, runtime)
            self.assertEqual(caught.exception.code, "CLAIM_SNAPSHOT_STALE")
            self.assertFalse((runtime / "runs").exists())

    def test_nonclaimable_spec_and_missing_gate_guards_prevent_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            task, snapshot = _install_template(root, canonical, db, task, _template(task))
            claim = _claim(root, db, task, snapshot)
            runtime = root / ".sdd/runtime"
            with patch("scripts.sdd_tasks.prompts.load_satisfied_gates", return_value=set()), \
                    self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, runtime)
            self.assertEqual(caught.exception.code, "PROMPT_GATES_UNSATISFIED")
            with patch("scripts.sdd_tasks.prompts.validate_candidate",
                       return_value=(task, {GATE}, "待确认")), \
                    self.assertRaises(PromptError) as caught:
                render_prompt(task, claim, snapshot, runtime)
            self.assertEqual(caught.exception.code, "PROMPT_SPEC_NOT_CLAIMABLE")
            self.assertFalse((runtime / "runs").exists())


if __name__ == "__main__":
    unittest.main()
