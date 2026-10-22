"""Canonical command-line entry point for the spec-042 offline evaluator.

The CLI is intentionally a thin adapter around :func:`runner.run`: it owns
argument parsing and safe terminal output, while the runner owns evaluation
semantics and report checkpoints.  It never prints trace payloads or judge
responses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from . import langfuse_export, runner
from .config import FALLBACK_JUDGE, PRIMARY_JUDGE, REPEATS
from .report import ReportWriter

_SUMMARY_KEYS = (
    "scored",
    "skipped",
    "unavailable",
    "written",
    "verified",
    "failed",
    "no_prior_context",
)
_URL_USERINFO_RE = re.compile(r"(?P<prefix>https?://)(?P<userinfo>[^/\s@]+)@", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<key>authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"password|secret|credential|token|key)(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(
    r"\b(?:sk|pk)-[A-Za-z0-9][A-Za-z0-9._-]*\b|\bBearer\s+\S+",
    re.IGNORECASE,
)


class _ArgumentError(ValueError):
    """An argparse error that can be handled without an immediate exit."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse includes unknown option values in ``message``.  Keep parse
        # failures useful to automation without echoing argv credentials or
        # other user-controlled values to stderr.
        raise _ArgumentError("invalid command-line arguments")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description="Run the local, loopback-only Spec-042 agent evaluation.",
        allow_abbrev=False,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", metavar="PATH", help="local EvalItem JSON array")
    source.add_argument(
        "--export",
        action="store_true",
        help="read traces from the existing local Langfuse exporter",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help="directory for report.json and report.md",
    )
    parser.add_argument("--task", choices=sorted(runner.KNOWN_TASKS), default="chat_quality")
    parser.add_argument("--primary", default=PRIMARY_JUDGE, metavar="MODEL")
    parser.add_argument("--fallback", default=FALLBACK_JUDGE, metavar="MODEL")
    parser.add_argument("--repeats", type=_positive_int, default=REPEATS, metavar="N")
    parser.add_argument("--max-items", type=_positive_int, default=None, metavar="N")
    return parser


def _safe_text(value: object, *, limit: int = 400) -> str:
    text = str(value)
    text = _URL_USERINFO_RE.sub(r"\g<prefix><redacted>@", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}<redacted>",
        text,
    )
    text = _SECRET_TOKEN_RE.sub("<redacted>", text)
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _output_dir_from_argv(argv: Sequence[str]) -> str | None:
    for index, arg in enumerate(argv):
        if arg == "--output-dir" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--output-dir="):
            return arg.split("=", 1)[1]
    return None


def _best_effort_failure_report(output_dir: str | None, error: object) -> dict[str, str]:
    """Create both failure projections when an error occurs before runner.run."""
    if not output_dir:
        return {}
    try:
        writer = ReportWriter(output_dir, metadata={"source": "cli"})
        writer.finish(
            "failed",
            errors=[
                {
                    "type": type(error).__name__,
                    "message": _safe_text(error),
                    "stage": "cli",
                }
            ],
        )
        return {"json": str(writer.json_path), "markdown": str(writer.markdown_path)}
    except Exception:
        return {}


def _safe_error_messages(errors: object) -> list[str]:
    messages: list[str] = []
    if isinstance(errors, Mapping):
        if "message" in errors:
            prefix = errors.get("type", "Error")
            messages.append(f"{_safe_text(prefix)}: {_safe_text(errors['message'])}")
        nested = errors.get("errors")
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
            for child in nested:
                messages.extend(_safe_error_messages(child))
    elif isinstance(errors, Sequence) and not isinstance(errors, (str, bytes, bytearray)):
        for child in errors:
            messages.extend(_safe_error_messages(child))
    elif errors:
        messages.append(_safe_text(errors))
    return messages


def _safe_summary(summary: object) -> dict[str, int]:
    if not isinstance(summary, Mapping):
        return {}
    result: dict[str, int] = {}
    for key in _SUMMARY_KEYS:
        value = summary.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            result[key] = value
    return result


def _emit_result(result: Mapping[str, Any]) -> int:
    exit_code = result.get("exit_code", 1)
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        exit_code = 1
    paths = result.get("report_paths")
    if not isinstance(paths, Mapping):
        paths = {}
    output = {
        "exit_code": exit_code,
        "status": result.get("status", "failed"),
        "report_json": result.get("report_json", paths.get("json")),
        "report_markdown": result.get("report_markdown", paths.get("markdown")),
        "summary": _safe_summary(result.get("summary")),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if exit_code != 0:
        report_json = output["report_json"] or "<unavailable>"
        report_markdown = output["report_markdown"] or "<unavailable>"
        print(
            "evaluation failed; reports: "
            f"json={_safe_text(report_json)} markdown={_safe_text(report_markdown)}",
            file=sys.stderr,
        )
        for message in _safe_error_messages(result.get("errors")):
            print(f"error: {message}", file=sys.stderr)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except _ArgumentError as exc:
        parser.print_usage(sys.stderr)
        paths = _best_effort_failure_report(_output_dir_from_argv(raw_argv), exc)
        detail = f"; reports: json={paths['json']} markdown={paths['markdown']}" if paths else ""
        print(f"argument error: {_safe_text(exc)}{detail}", file=sys.stderr)
        return 2

    try:
        export = None
        if args.export:
            export = lambda: langfuse_export.collect_eval_items(task=args.task)
        result = runner.run(
            dataset_path=args.dataset,
            output_dir=args.output_dir,
            task=args.task,
            primary=args.primary,
            fallback=args.fallback,
            repeats=args.repeats,
            max_items=args.max_items,
            export=export,
        )
    except Exception as exc:
        paths = _best_effort_failure_report(args.output_dir, exc)
        result = {
            "exit_code": 1,
            "status": "failed",
            "report_json": paths.get("json"),
            "report_markdown": paths.get("markdown"),
            "report_paths": paths,
            "summary": {},
            "errors": [{"type": type(exc).__name__, "message": _safe_text(exc)}],
        }
    return _emit_result(result)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
