import copy
import json
import tempfile
import unittest

from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.summaries import SummaryError, scan_summaries
from tests.sdd_tasks.test_catalog import _git, _repo
from tests.sdd_tasks.test_result_schema import valid_result

RB, RE = "<!-- sdd-run-result:v1:begin -->", "<!-- sdd-run-result:v1:end -->"
MB, ME = "<!-- sdd-run-meta:v1:begin -->", "<!-- sdd-run-meta:v1:end -->"


class SummaryScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root, paths, _, metadata = _repo(self.temp.name)
        self.task = parse_task(paths[metadata["task_id"]])
        self.task_rel = paths[metadata["task_id"]].relative_to(self.root).as_posix()
        self.tasks = [(self.task, self.task_rel)]
        self.result = valid_result()
        self.result.update(task_id=self.task.metadata["task_id"], task_hash=self.task.task_hash,
                           prompt_hash=self.task.prompt_hash)
        self.meta = {"schema": "sdd-run-meta/v1", "run_id": self.result["run_id"],
                     "task_id": self.task.metadata["task_id"], "task_hash": self.task.task_hash,
                     "prompt_hash": self.task.prompt_hash, "attempt": 1, "ide": "codex",
                     "executor_id": "fixture-executor", "agent_role": self.task.metadata["agent_role"],
                     "model": None, "worktree": self.task.metadata["worktree"]["path"],
                     "branch": self.task.metadata["worktree"]["branch"],
                     "base_commit": _git(self.root, "rev-parse", "HEAD"),
                     "claimed_at": "2026-10-11T00:00:00Z"}
        self.rel = "docs/sdd/runs/016/task-04/{}.md".format(self.result["run_id"])

    def tearDown(self):
        self.temp.cleanup()

    def content(self, result=None, meta=None):
        return "\n".join((RB, json.dumps(result or self.result), RE, MB,
                           json.dumps(meta or self.meta), ME, "Summary fixture."))

    def write(self, text=None, root=None, rel=None):
        root, rel = root or self.root, rel or self.rel
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text or self.content(), encoding="utf-8")
        return path

    def reset(self):
        import shutil
        shutil.rmtree(self.root / "docs/sdd/runs", ignore_errors=True)

    def reject(self, text=None, rel=None, code=None):
        self.reset()
        self.write(text, rel=rel)
        with self.assertRaises(SummaryError) as caught:
            scan_summaries((self.root,), self.tasks)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_terminal_run_reconstructs_exact_persistent_fields(self):
        self.write()
        record, = scan_summaries((self.root,), self.tasks)
        expected = {"run_id": self.result["run_id"], "task_id": self.task.metadata["task_id"],
                    "attempt": 1, "state": "succeeded", "ide": "codex",
                    "executor_id": "fixture-executor", "owner_json": "{}",
                    "agent_role": self.task.metadata["agent_role"], "model": None,
                    "worktree": self.task.metadata["worktree"]["path"],
                    "branch": self.task.metadata["worktree"]["branch"], "base_commit": self.meta["base_commit"],
                    "task_hash": self.task.task_hash, "prompt_hash": self.task.prompt_hash,
                    "claimed_at": self.meta["claimed_at"], "started_at": self.result["started_at"],
                    "ended_at": self.result["ended_at"], "duration_ms": self.result["duration_ms"],
                    "result_doc": self.rel, "error_code": None, "error_summary": None}
        self.assertEqual(record, expected)

    def test_sensitive_narrative_outside_markers_is_rejected(self):
        safe = self.content().replace("Summary fixture.", "Implemented safely with no blockers.")
        self.write(safe)
        self.assertEqual(len(scan_summaries((self.root,), self.tasks)), 1)
        for narrative in ("Bearer sample-secret", "Private file /home/alice/notes.txt",
                          "raw stdout: captured text"):
            with self.subTest(narrative=narrative):
                self.reject(self.content().replace("Summary fixture.", narrative),
                            code="SUMMARY_SENSITIVE_CONTENT")

    def test_json_markers_schema_and_overlap_are_strict(self):
        base = self.content()
        dup = base.replace('"schema": "sdd-run-result/v1"',
                           '"schema": "sdd-run-result/v1", "schema": "sdd-run-result/v1"', 1)
        unknown = dict(self.meta, extra=True)
        missing = dict(self.meta)
        missing.pop("attempt")
        nested = "\n".join((RB, json.dumps(self.result), MB, json.dumps(self.meta), RE, ME))
        cases = (dup, self.content(meta=unknown), self.content(meta=missing),
                 base.replace(MB, "", 1), nested)
        for sample in cases:
            with self.subTest(sample=sample[:50]):
                self.reject(sample)

    def test_path_id_hash_model_role_branch_and_time_mismatches_fail(self):
        edits = (
            (lambda r, m: r.update(task_id="spec-016-task-03"), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: (r.update(task_hash="f" * 64), m.update(task_hash="f" * 64)), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: (r.update(prompt_hash="f" * 64), m.update(prompt_hash="f" * 64)), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: m.update(run_id="123e4567-e89b-12d3-a456-426614174001"), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: m.update(model="other-model"), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: m.update(agent_role="other-role"), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: m.update(branch="feature/spec-016-other"), "SUMMARY_BINDING_MISMATCH"),
            (lambda r, m: m.update(claimed_at="2026-10-11T00:02:00Z"), "SUMMARY_META_INVALID"),
        )
        for edit, code in edits:
            result, meta = copy.deepcopy(self.result), copy.deepcopy(self.meta)
            edit(result, meta)
            with self.subTest(edit=edit):
                self.reject(self.content(result, meta), code=code)
        self.reject(rel="docs/sdd/runs/016/task-03/{}.md".format(self.result["run_id"]),
                    code="SUMMARY_PATH_MISMATCH")
        result = copy.deepcopy(self.result)
        result["outcome"] = "running"
        self.reject(self.content(result, self.meta), code="SUMMARY_SCHEMA_INVALID")

    def test_summary_symlink_is_rejected(self):
        self.reset()
        path = self.write()
        outside = self.root.parent / (self.root.name + "-summary.md")
        outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(SummaryError, "SUMMARY_SYMLINK"):
            scan_summaries((self.root,), self.tasks)

    def test_duplicate_run_id_across_roots_deduplicates_only_identical_content(self):
        self.write()
        with tempfile.TemporaryDirectory() as second:
            other, _, _, _ = _repo(second)
            self.write(root=other)
            records = scan_summaries((self.root, other), self.tasks)
            self.assertEqual(len(records), 1)
            self.write("\n".join((self.content(), "different commentary")), root=other)
            with self.assertRaisesRegex(SummaryError, "RUN_ID_CONTENT_CONFLICT"):
                scan_summaries((self.root, other), self.tasks)


if __name__ == "__main__":
    unittest.main()
