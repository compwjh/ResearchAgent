import unittest

from scripts.sdd_tasks.result_schema import validate_summary_result


def valid_result():
    run_id = "123e4567-e89b-12d3-a456-426614174000"
    return {
        "schema": "sdd-run-result/v1", "run_id": run_id, "task_id": "spec-016-task-04",
        "task_hash": "a" * 64, "prompt_hash": "b" * 64, "outcome": "succeeded",
        "summary": "Implemented and verified the task ledger slice.",
        "changed_files": [{"path": "scripts/sdd_tasks/store.py", "change": "modified",
                            "additions": 3, "deletions": 1, "sha256": "c" * 64}],
        "artifacts": [{"path": "docs/sdd/runs/016/task-04/" + run_id + ".md",
                       "kind": "run-summary", "sha256": "d" * 64, "included_in_commit": None}],
        "commands": [{"argv": ["python3", "-m", "unittest", "tests.sdd_tasks.test_store"],
                       "status": "executed", "exit_code": 0, "duration_ms": 40,
                       "summary": "1 test passed"},
                      {"argv": ["optional-tool"], "status": "skipped", "exit_code": None,
                       "duration_ms": None, "summary": "Not configured"}],
        "tests": [{"name": "tests.sdd_tasks.test_store", "outcome": "passed",
                   "exit_code": 0, "summary": "1 test passed"}],
        "decisions": [{"decision": "Keep metrics unknown when unavailable.",
                       "evidence": "No token usage source was provided."}],
        "risks": [], "blockers": [], "main_agent_actions": [],
        "started_at": "2026-10-11T00:00:00Z", "ended_at": "2026-10-11T00:01:00Z",
        "duration_ms": 60000, "model": None,
        "token_usage": {"input": None, "output": None, "total": None, "source": None},
        "tool_call_count": None, "log_paths": [".sdd/runtime/runs/" + run_id + "/events.jsonl"],
    }


class ResultSchemaTests(unittest.TestCase):
    def reject(self, edit):
        data = valid_result()
        edit(data)
        with self.assertRaises(ValueError):
            validate_summary_result(data)

    def test_complete_result_and_unknown_metrics_are_valid(self):
        data = valid_result()
        self.assertIs(validate_summary_result(data), data)
        self.assertIsNone(data["model"])
        self.assertIsNone(data["token_usage"]["input"])
        self.assertIsNone(data["token_usage"]["output"])
        self.assertIsNone(data["token_usage"]["total"])
        self.assertIsNone(data["tool_call_count"])

    def test_partial_token_usage_stays_unknown_without_estimation(self):
        cases = (
            {"input": 8, "output": None, "total": None, "source": None},
            {"input": None, "output": 6, "total": None, "source": None},
            {"input": 8, "output": 6, "total": None, "source": None},
        )
        for usage in cases:
            with self.subTest(usage=usage):
                data = valid_result()
                data["token_usage"] = usage
                self.assertEqual(validate_summary_result(data)["token_usage"], usage)

    def test_known_token_total_must_match_known_inputs(self):
        self.reject(lambda data: data.update(token_usage={
            "input": 8, "output": 6, "total": 13, "source": None}))

    def test_empty_executed_or_skipped_command_argv_is_rejected(self):
        edits = (lambda data: data["commands"][0].update(argv=[]),
                 lambda data: data["commands"][1].update(argv=[]))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)

    def test_root_and_nested_fields_are_exact(self):
        edits = (lambda d: d.update(extra=True), lambda d: d.pop("summary"),
                 lambda d: d["commands"][0].update(extra=True),
                 lambda d: d["token_usage"].update(extra=None))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)

    def test_bool_is_not_an_integer(self):
        edits = (lambda d: d.update(duration_ms=True),
                 lambda d: d["commands"][0].update(exit_code=True),
                 lambda d: d["changed_files"][0].update(additions=False),
                 lambda d: d["token_usage"].update(input=True),
                 lambda d: d["artifacts"][0].update(included_in_commit=1))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)

    def test_uuid_hash_and_repo_relative_paths(self):
        edits = (lambda d: d.update(run_id="not-a-uuid"),
                 lambda d: d.update(task_hash="A" * 64),
                 lambda d: d["artifacts"][0].update(path="/Users/test/run.md"),
                 lambda d: d.update(log_paths=["../events.jsonl"]))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)

    def test_enums_time_and_command_exit_consistency(self):
        edits = (lambda d: d.update(outcome="unknown"),
                 lambda d: d["changed_files"][0].update(change="unknown"),
                 lambda d: d["commands"][0].update(status="unknown"),
                 lambda d: d["tests"][0].update(outcome="success"),
                 lambda d: d["commands"][0].update(exit_code=None),
                 lambda d: d["commands"][0].update(status="skipped", exit_code=0),
                 lambda d: d.update(ended_at="2026-10-10T23:59:59Z"))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)

    def test_sensitive_keys_values_and_absolute_paths_are_rejected(self):
        edits = (lambda d: d.update(password="example"),
                 lambda d: d.update(summary="Authorization: Bearer example"),
                 lambda d: d.update(summary="API_SECRET=example"),
                 lambda d: d.update(summary="working directory /home/alice/project"),
                 lambda d: d.update(summary="working directory C:\\Users\\alice\\repo"))
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject(edit)


if __name__ == "__main__":
    unittest.main()
