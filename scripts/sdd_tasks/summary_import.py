"""Validate and merge terminal TaskRuns reconstructed from summary documents."""

import subprocess
from pathlib import Path

_COLUMNS = ("run_id", "task_id", "attempt", "state", "ide", "executor_id", "owner_json",
            "agent_role", "model", "worktree", "branch", "base_commit", "task_hash",
            "prompt_hash", "claimed_at", "started_at", "ended_at", "duration_ms",
            "result_doc", "error_code", "error_summary")
_PRESERVE = {"owner_json", "error_code", "error_summary"}


class SummaryImportError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__("{}: {}".format(code, detail))


def validate_base_commits(repo_root: Path, records) -> None:
    for commit in sorted({row["base_commit"] for row in records}):
        try:
            result = subprocess.run(["git", "-C", str(repo_root), "cat-file", "-t", commit],
                                    capture_output=True, text=True, check=False)
        except OSError as exc:
            raise SummaryImportError("SUMMARY_BASE_COMMIT_INVALID", str(exc)) from exc
        if result.returncode or result.stdout.strip() != "commit":
            raise SummaryImportError("SUMMARY_BASE_COMMIT_INVALID", commit)


def merge_runs(conn, records) -> int:
    inserted = 0
    sql = "INSERT INTO runs ({}) VALUES ({})".format(
        ",".join(_COLUMNS), ",".join("?" for _ in _COLUMNS))
    for record in records:
        existing = conn.execute("SELECT * FROM runs WHERE run_id=?", (record["run_id"],)).fetchone()
        if existing is not None:
            if existing["state"] in {"claimed", "running"}:
                raise SummaryImportError("RUN_SUMMARY_ACTIVE_CONFLICT", record["run_id"])
            mismatch = [key for key in _COLUMNS if key not in _PRESERVE and existing[key] != record[key]]
            if mismatch:
                raise SummaryImportError("RUN_SUMMARY_CONFLICT", "{}: {}".format(record["run_id"], mismatch))
            continue
        conn.execute(sql, [record[key] for key in _COLUMNS])
        inserted += 1
    return inserted
