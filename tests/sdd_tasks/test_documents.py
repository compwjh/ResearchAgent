import json
import re
import unittest

from scripts.sdd_tasks.documents import TaskDocumentError, parse_task_text
from tests.sdd_tasks._fixtures import (
    DEFAULT_PROMPT,
    META_BEGIN,
    PROMPT_BEGIN,
    PROMPT_END,
    TASK_PATH,
    task_markdown,
    task_metadata,
)


class TaskDocumentTests(unittest.TestCase):
    def parse(self, **kwargs):
        return parse_task_text(task_markdown(**kwargs), TASK_PATH)

    def rejects(self, text):
        with self.assertRaises(ValueError):
            parse_task_text(text, TASK_PATH)

    def rejects_code(self, text, code):
        with self.assertRaises(TaskDocumentError) as caught:
            parse_task_text(text, TASK_PATH)
        self.assertEqual(caught.exception.code, code)

    def test_valid_parse_and_hashes_are_stable(self):
        first, again = self.parse(), self.parse()
        self.assertEqual(first.metadata["task_id"], "spec-016-task-04")
        self.assertEqual(first.prompt, DEFAULT_PROMPT + "\n")
        self.assertEqual(first.path, TASK_PATH)
        self.assertEqual(first.task_hash, again.task_hash)
        self.assertEqual(first.prompt_hash, again.prompt_hash)
        self.assertRegex(first.task_hash, re.compile(r"^[0-9a-f]{64}$"))
        self.assertRegex(first.prompt_hash, re.compile(r"^[0-9a-f]{64}$"))

    def test_status_does_not_change_task_hash(self):
        self.assertEqual(self.parse().task_hash, self.parse(metadata_overrides={"status": "completed"}).task_hash)

    def test_prompt_and_allowed_paths_change_hashes(self):
        base = self.parse()
        prompt = self.parse(prompt=DEFAULT_PROMPT + " Return findings.")
        paths = self.parse(metadata_overrides={"allowed_paths": ["scripts/sdd_tasks"]})
        self.assertNotEqual(prompt.prompt_hash, base.prompt_hash)
        self.assertNotEqual(prompt.task_hash, base.task_hash)
        self.assertNotEqual(paths.prompt_hash, base.prompt_hash)
        self.assertNotEqual(paths.task_hash, base.task_hash)

    def test_duplicate_json_key_and_corrupt_json_are_rejected(self):
        raw = json.dumps(task_metadata())[:-1] + ',"schema_version":1}'
        self.rejects(task_markdown(raw_metadata=raw))
        self.rejects(task_markdown(raw_metadata="{"))

    def test_missing_or_duplicate_markers_are_rejected(self):
        text = task_markdown()
        malformed = (
            text.replace(META_BEGIN + "\n", "", 1),
            text.replace(PROMPT_END, "", 1),
            text.replace(META_BEGIN, META_BEGIN + "\n" + META_BEGIN, 1),
            text.replace(PROMPT_BEGIN, PROMPT_BEGIN + "\n" + PROMPT_BEGIN, 1),
        )
        for sample in malformed:
            with self.subTest(sample=sample[:40]):
                self.rejects(sample)

    def test_missing_prompt_unknown_placeholder_and_unknown_field(self):
        self.rejects(task_markdown(prompt=" \n "))
        self.rejects(task_markdown(prompt="Use {{UNLISTED_TOKEN}}."))
        self.rejects(task_markdown(prompt="Use {{RUN_ID}."))
        self.rejects(task_markdown(metadata_overrides={"extra": True}))

    def test_boolean_is_not_accepted_as_integer(self):
        self.rejects(task_markdown(metadata_overrides={"priority": True}))

    def test_task_id_and_spec_id_must_match(self):
        for change in ({"task_id": "spec-017-task-04"}, {"spec_id": "017"}):
            with self.subTest(change=change):
                self.rejects(task_markdown(metadata_overrides=change))

    def test_allowed_paths_reject_escape_absolute_and_backslash(self):
        for path in ("../outside", "/etc/passwd", "scripts\\sdd_tasks"):
            with self.subTest(path=path):
                self.rejects(task_markdown(metadata_overrides={"allowed_paths": [path]}))
        for path in ("nul\x00path", "bad:name", "bad|name", "bad?name", "bad[name]"):
            with self.subTest(path=path):
                self.rejects(task_markdown(metadata_overrides={"allowed_paths": [path]}))

    def test_timestamp_requires_timezone(self):
        self.rejects(task_markdown(metadata_overrides={"created_at": "2026-10-11T00:00:00"}))


    def test_schema_version_requires_exact_integer_one(self):
        for version in (None, True, 1.0, "1", 2):
            with self.subTest(version=version):
                self.rejects_code(task_markdown(metadata_overrides={"schema_version": version}),
                                  "unsupported_schema_version")
        missing = task_metadata()
        missing.pop("schema_version")
        self.rejects_code(task_markdown(raw_metadata=json.dumps(missing)), "unsupported_schema_version")
        for change in ({"max_attempts": True}, {"prompt_version": True}):
            with self.subTest(change=change):
                self.rejects(task_markdown(metadata_overrides=change))

    def test_required_gates_are_spec_qualified_lower_kebab_ids(self):
        for gate in ("spec-017.cloud-stage-authorized", "cloud-stage-authorized",
                     "spec-016.Cloud-stage", "spec-016.trailing-", "spec-016..bad", "spec-016.bad_name"):
            with self.subTest(gate=gate):
                self.rejects(task_markdown(metadata_overrides={"required_gates": [gate]}))

    def test_sensitive_title_and_full_prompt_are_rejected(self):
        title = task_markdown(metadata_overrides={"title": "Bearer sample-secret"})
        self.rejects_code(title, "TASK_SENSITIVE_CONTENT")
        for value in ("Bearer sample-secret", "Private file /home/alice/notes.txt", "raw stdout: captured text"):
            with self.subTest(value=value):
                self.rejects_code(task_markdown(prompt=DEFAULT_PROMPT + "\n" + value),
                                  "TASK_SENSITIVE_CONTENT")

    def test_legacy_history_absolute_path_outside_prompt_is_preserved(self):
        history = "Legacy human history mentions /home/old-user/project/file.txt.\n\n"
        text = history + task_markdown()
        parsed = parse_task_text(text, TASK_PATH)
        self.assertIn(history, text)
        self.assertEqual(parsed.prompt, DEFAULT_PROMPT + "\n")

    def test_each_mandatory_field_is_required(self):
        required = [
            "schema_version", "task_id", "spec_id", "title", "status", "created_at",
            "depends_on", "required_gates", "agent_role", "required_capabilities",
            "allowed_paths", "worktree", "prompt_version", "return_schema",
            "expected_artifacts", "validation_commands",
        ]
        for field in required:
            meta = task_metadata()
            meta.pop(field)
            with self.subTest(field=field):
                self.rejects(task_markdown(raw_metadata=json.dumps(meta)))

    def test_nonobject_json_and_nested_duplicate_key_are_rejected(self):
        self.rejects(task_markdown(raw_metadata="[]"))
        raw = json.dumps(task_metadata())
        fragment = '"path": ".worktrees/spec-016"'
        self.rejects(task_markdown(raw_metadata=raw.replace(fragment, fragment + ", " + fragment, 1)))

    def test_worktree_dependencies_and_artifact_containment_are_rejected(self):
        changes = (
            {"worktree": {"path": ".worktrees/spec-016"}},
            {"depends_on": ["spec-016-task-03", "spec-016-task-03"]},
            {"expected_artifacts": ["backend/private.txt"]},
        )
        for change in changes:
            with self.subTest(change=change):
                self.rejects(task_markdown(metadata_overrides=change))

    def test_prompt_contract_fences_and_template_edges(self):
        base = DEFAULT_PROMPT
        invalid = (
            base.replace('Read: ["scripts/sdd_tasks"]\n', "", 1),
            base.replace("Allowed paths:", 'Read: ["scripts/sdd_tasks"]\nAllowed paths:', 1),
            base.replace("Role: backend-dev\nRead:", 'Read: ["scripts/sdd_tasks"]\nRole:', 1),
            base.replace("Forbidden: Do not push, merge, reset, stash, or clean.", "Forbidden: ", 1),
            base.replace("Role: backend-dev", "Role: analyst", 1),
            base.replace('"tests/sdd_tasks"]', '"other"]', 1),
            base.replace("test_store\"]", "other\"]", 1),
            base.replace("Validation: [", "Validation: none\n# Validation: [", 1),
            base.replace("{{RESULT_PATH}}", "{{RUN_ID}}", 1),
            base.replace("Return schema: sdd-run-result/v1", "Return schema: other", 1),
            base + "{{", base + "}}",
        )
        for prompt in invalid:
            with self.subTest(prompt=prompt[:30]):
                self.rejects(task_markdown(prompt=prompt))
        fenced = "```text\n" + base + "\n```"
        self.parse(prompt=fenced)
        self.rejects(task_markdown(prompt=fenced[:-4]))
        self.rejects(task_markdown(prompt=fenced + "\nextra prose"))
        self.rejects(task_markdown(prompt="```python\n" + base + "\n```"))
        for forbidden in ("none", "无", "空"):
            prompt = base.replace("Forbidden: Do not push, merge, reset, stash, or clean.",
                                  "Forbidden: " + forbidden)
            with self.subTest(forbidden=forbidden):
                self.rejects(task_markdown(prompt=prompt))
        self.parse(metadata_overrides={"validation_commands": []})
        self.rejects(task_markdown(metadata_overrides={"allowed_paths": []}))


if __name__ == "__main__":
    unittest.main()
