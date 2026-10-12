import json
from pathlib import Path

TASK_PATH = Path("docs/sdd/plans/016/task-04-sqlite-task-ledger.md")
META_BEGIN = "<!-- sdd-task-meta:v1:begin -->"
META_END = "<!-- sdd-task-meta:v1:end -->"
PROMPT_BEGIN = "<!-- sdd-task-prompt:v1:begin -->"
PROMPT_END = "<!-- sdd-task-prompt:v1:end -->"

def task_metadata(overrides=None):
    value = {
        "schema_version": 1, "task_id": "spec-016-task-04", "spec_id": "016",
        "title": "Implement the task ledger", "status": "pending", "priority": 100,
        "created_at": "2026-10-11T00:00:00Z", "depends_on": ["spec-016-task-03"],
        "required_gates": ["spec-016.cloud-stage-authorized"], "agent_role": "backend-dev",
        "required_capabilities": ["read", "edit", "shell"],
        "allowed_paths": ["scripts/sdd_tasks", "tests/sdd_tasks"],
        "worktree": {"path": ".worktrees/spec-016", "branch": "feature/spec-016-portable-task-ledger",
                     "mode": "per_spec", "base_rule": "explicit_commit"},
        "max_attempts": 3, "prompt_version": 1, "return_schema": "sdd-run-result/v1",
        "expected_artifacts": [], "validation_commands": ["python3 -m unittest tests.sdd_tasks.test_store"],
    }
    value.update(overrides or {})
    return value


def _default_prompt(metadata):
    commands = metadata["validation_commands"]
    validation = json.dumps(commands, ensure_ascii=False) if commands else "none"
    return "\n".join((
        "Role: " + str(metadata.get("agent_role", "backend-dev")),
        'Read: ["scripts/sdd_tasks"]',
        "Allowed paths: " + json.dumps(metadata["allowed_paths"], ensure_ascii=False),
        "Forbidden: Do not push, merge, reset, stash, or clean.",
        "Validation: " + validation,
        "Result: Write the complete result JSON to {{RESULT_PATH}}.",
        "Return schema: sdd-run-result/v1", "Return a brief handoff summary.",
    ))


DEFAULT_PROMPT = _default_prompt(task_metadata())


def task_markdown(metadata_overrides=None, prompt=None, raw_metadata=None):
    metadata = task_metadata(metadata_overrides)
    raw = raw_metadata if raw_metadata is not None else json.dumps(metadata, ensure_ascii=False)
    if prompt is None:
        try:
            candidate = json.loads(raw)
        except ValueError:
            candidate = None
        if isinstance(candidate, dict) and {"agent_role", "allowed_paths", "validation_commands"} <= candidate.keys():
            metadata = candidate
        prompt = _default_prompt(metadata)
    return "\n".join((META_BEGIN, raw, META_END, "", PROMPT_BEGIN, prompt, PROMPT_END))
