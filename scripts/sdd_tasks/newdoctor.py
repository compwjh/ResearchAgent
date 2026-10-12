"""Read-only repository health inspection for Task 05 doctor."""

import os
import stat
import warnings
from pathlib import Path
from typing import Any, Dict

from .atomic import contained, read_text
from .catalog import CatalogError, _scan, discover_worktrees
from .mirrors import MirrorError, validate_mirrors
from .newdb_paths import open_parent
from .summaries import SummaryError, scan_summaries
from .summary_import import SummaryImportError, validate_base_commits


def _legacy_count(roots) -> int:
    count = 0
    for root in roots:
        for path in sorted((root / "docs/sdd/plans").rglob("task-*.md")):
            try:
                count += "<!-- sdd-task-meta" not in read_text(path)
            except (OSError, UnicodeError, ValueError):
                continue
    return count


def _code(error: Exception) -> str:
    return getattr(error, "code", "DOCTOR_CHECK_FAILED")


def doctor(repo_root: Path) -> Dict[str, Any]:
    diagnostics, roots, tasks, duplicates = [], (), [], 0
    summaries, legacy = None, 0
    try:
        roots = discover_worktrees(Path(repo_root))
        legacy = _legacy_count(roots)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            tasks, duplicates = _scan(roots)
        for item in caught:
            code = str(item.message).split(":", 1)[0]
            if code != "legacy_tasks_ignored":
                diagnostics.append({"code": code})
        if legacy:
            diagnostics.append({"code": "legacy_tasks_ignored"})
        if not tasks:
            diagnostics.append({"code": "no_protocol_tasks"})
        for task, _ in tasks:
            owner = next(root for root in sorted(roots, key=lambda path: len(path.parts), reverse=True)
                         if root in task.path.resolve().parents)
            try:
                validate_mirrors(task, owner)
            except MirrorError as exc:
                diagnostics.append({"code": exc.code})
        try:
            summaries = scan_summaries(roots, tasks)
            validate_base_commits(roots[0], summaries)
        except (SummaryError, SummaryImportError) as exc:
            diagnostics.append({"code": _code(exc)})
    except (CatalogError, OSError, ValueError) as exc:
        diagnostics.append({"code": _code(exc)})

    present, schema_check = False, "not_initialized"
    if roots:
        try:
            database = contained(roots[0], ".sdd/runtime/task-ledger.sqlite3")
            info = database.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("DATABASE_PATH_UNSAFE")
            parent_fd = open_parent(database.parent, create=False)
            os.close(parent_fd)
            present, schema_check = True, "not_run_requires_status"
            diagnostics.append({"code": "ledger_status_required"})
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            schema_check = "unsafe"
            diagnostics.append({"code": "DATABASE_PATH_UNSAFE"})
    warning_codes = {"legacy_tasks_ignored", "stale_task_copies_ignored", "no_protocol_tasks", "ledger_status_required"}
    errors = {item["code"] for item in diagnostics} - warning_codes
    diagnostics = [{"code": code} for code in sorted({item["code"] for item in diagnostics})]
    return {
        "schema": "sdd-doctor/v1", "healthy": not errors,
        "worktree_count": len(roots), "task_count": len(tasks),
        "legacy_task_count": legacy, "duplicate_task_copies": duplicates,
        "summary_count": len(summaries) if summaries is not None else None,
        "ledger": {"present": present, "schema_check": schema_check},
        "diagnostics": diagnostics,
    }
