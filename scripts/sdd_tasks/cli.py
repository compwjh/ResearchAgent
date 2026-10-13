"""Small JSON command router for the Task 05 read-only and rebuild commands."""

import argparse
import json
import re
import stat
import sys
import warnings
from contextlib import closing
from pathlib import Path
from typing import Optional, Sequence

from .atomic import contained
from .catalog import CatalogError, rebuild
from .catalog_status import status
from .locks import runtime_root
from .newcli_claim import claim_from_cli
from .newcli_recover import recover_from_cli
from .newcli_results import metrics_from_cli, result_from_cli
from .newdoctor import doctor
from .store import connect


class _UsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def _emit(ok: bool, code: str, message: str, data: object) -> None:
    print(json.dumps({"ok": ok, "code": code, "message": message, "data": data},
                     sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _code(exc: Exception) -> str:
    value = getattr(exc, "code", None) or str(exc).split(":", 1)[0]
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) else "COMMAND_FAILED"


def _exit_code(code: str) -> int:
    normalized = code.upper()
    if normalized in {"COMMAND_FAILED", "DOCTOR_CHECK_FAILED", "GIT_DISCOVERY_FAILED"}:
        return 6
    if normalized in {"NEXT_NOT_READY", "RECOVER_NOT_READY"}:
        return 2
    if normalized in {"TASK_DOCUMENT_INVALID", "TASK_SENSITIVE_CONTENT", "UNSUPPORTED_SCHEMA_VERSION"}:
        return 2
    if "LEASE" in normalized or "OWNER" in normalized:
        return 4
    if any(word in normalized for word in ("WORKTREE", "WORKSPACE", "BASELINE", "DATABASE_PATH")):
        return 5
    if any(word in normalized for word in ("RESULT", "SUMMARY", "VALIDATION")):
        return 6
    if "JOURNAL" in normalized:
        return 7
    return 3


def _parser() -> _Parser:
    parser = _Parser(prog="sdd_tasks", add_help=False, allow_abbrev=False)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("-h", "--help", action="store_true")
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)
    commands.add_parser("doctor", add_help=False)
    commands.add_parser("rebuild", add_help=False)
    status_parser = commands.add_parser("status", add_help=False)
    status_parser.add_argument("--json", action="store_true", required=True)
    next_parser = commands.add_parser("next", add_help=False)
    next_parser.add_argument("--claim", action="store_true")
    next_parser.add_argument("--ide", required=True)
    next_parser.add_argument("--executor", required=True)
    next_parser.add_argument("--owner-pid", type=int, required=True)
    next_parser.add_argument("--base-commit")
    recover_parser = commands.add_parser("recover", add_help=False)
    recover_parser.add_argument("--run-id", required=True)
    result_parser = commands.add_parser("result", add_help=False)
    result_parser.add_argument("--json", action="store_true", required=True)
    result_parser.add_argument("--run-id", required=True)
    metrics_parser = commands.add_parser("metrics", add_help=False)
    metrics_parser.add_argument("--format", choices=("json", "csv"), required=True)
    return parser


def _existing_database(repo_root: Path) -> Path:
    database = runtime_root(repo_root) / "task-ledger.sqlite3"
    main = runtime_root(repo_root).parents[1]
    try:
        info = contained(main, ".sdd/runtime/task-ledger.sqlite3").lstat()
    except FileNotFoundError as exc:
        raise CatalogError("CATALOG_NOT_REBUILT", "run rebuild first") from exc
    except ValueError as exc:
        raise CatalogError("DATABASE_PATH_UNSAFE", "ledger path is unsafe") from exc
    if not stat.S_ISREG(info.st_mode):
        raise CatalogError("DATABASE_PATH_UNSAFE", "ledger must be a regular file")
    return database


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if args.help:
            _emit(True, "OK", "help", {"usage": parser.format_help()})
            return 0
        if args.command is None:
            raise _UsageError("command required")
        root = args.repo
        if args.command == "doctor":
            result = doctor(root)
            ok = result["healthy"]
            code = "OK" if ok else next(
                (item["code"] for item in result["diagnostics"]
                 if item["code"] not in {"legacy_tasks_ignored", "stale_task_copies_ignored",
                                          "no_protocol_tasks", "ledger_status_required"}),
                "DOCTOR_CHECK_FAILED",
            )
            _emit(ok, code, "repository check complete" if ok else "repository check failed", result)
            return 0 if ok else _exit_code(code)
        if args.command == "rebuild":
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                report = rebuild(runtime_root(root) / "task-ledger.sqlite3", root)
            for item in caught:
                code = str(item.message).split(":", 1)[0]
                print(code if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", code) else "REBUILD_DIAGNOSTIC",
                      file=sys.stderr)
            data = {"tasks": report.tasks, "runs": report.runs, "deduplicated": report.deduplicated,
                    "database": ".sdd/runtime/task-ledger.sqlite3"}
            _emit(True, "OK", "catalog rebuilt", data)
            return 0
        if args.command == "status":
            database = _existing_database(root)
            with closing(connect(database)) as connection:
                data = status(connection)
            _emit(True, "OK", "catalog status", data)
            return 0
        if args.command == "next" and args.claim:
            claim, reasons = claim_from_cli(root, args.ide, args.executor, args.owner_pid,
                                            args.base_commit)
            if claim is None:
                _emit(True, "NO_TASK", "no claim available", reasons)
            else:
                _emit(True, "OK", "claim created", claim)
            return 0
        if args.command == "recover":
            report = recover_from_cli(root, args.run_id)
            _emit(True, "OK", "recovery complete", report)
            return 0
        if args.command == "result":
            data = result_from_cli(_existing_database(root), args.run_id)
            _emit(True, "OK", "task result", data)
            return 0
        if args.command == "metrics":
            data = metrics_from_cli(_existing_database(root), args.format)
            _emit(True, "OK", "task metrics", data)
            return 0
        raise _UsageError("next requires --claim")
    except _UsageError:
        _emit(False, "USAGE_INVALID", "invalid command line", None)
        return 2
    except (CatalogError, ValueError, OSError) as exc:
        code = _code(exc)
        _emit(False, code, "operation failed", None)
        return _exit_code(code)
