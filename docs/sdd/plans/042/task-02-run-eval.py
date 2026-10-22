#!/usr/bin/env python3
"""Compatibility wrapper for the canonical Spec-042 evaluation CLI.

The historical path remains runnable for old notes and commands, but it no
longer owns a second evaluation implementation. New usage should call
``python -m backend.eval_042.cli`` from the repository root.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "../../../../"))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.eval_042.cli import main as _canonical_main  # noqa: E402


def _value_after(arguments: list[str], option: str) -> str | None:
    for index, argument in enumerate(arguments):
        if argument == option:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                return None
            return arguments[index + 1]
        if argument.startswith(f"{option}="):
            value = argument.split("=", 1)[1]
            return value if value and not value.startswith("-") else None
    return None


def _remove_option(arguments: list[str], option: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == option:
            index += 2
            continue
        if argument.startswith(f"{option}="):
            index += 1
            continue
        result.append(argument)
        index += 1
    return result


def _absolute_from_repo(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_REPO_ROOT, path)


def _translate_legacy_args(arguments: list[str]) -> list[str]:
    """Map the old ``--out`` summary-file option to the report directory."""
    translated = list(arguments)
    legacy_out_present = any(
        argument == "--out" or argument.startswith("--out=")
        for argument in translated
    )
    legacy_out = _value_after(translated, "--out")
    legacy_out_invalid = legacy_out_present and legacy_out is None
    if legacy_out is not None:
        translated = _remove_option(translated, "--out")
        if "--output-dir" not in translated and not any(
            argument.startswith("--output-dir=") for argument in translated
        ):
            translated.extend(
                ["--output-dir", os.path.dirname(_absolute_from_repo(legacy_out))]
            )

    has_dataset = "--dataset" in translated or any(
        argument.startswith("--dataset=") for argument in translated
    )
    has_export = "--export" in translated
    if not legacy_out_invalid and not has_dataset and not has_export:
        translated.extend(
            [
                "--dataset",
                os.path.join(_REPO_ROOT, "docs/sdd/plans/042/task-02-eval-dataset.json"),
            ]
        )
    if not any(
        argument == "--output-dir" or argument.startswith("--output-dir=")
        for argument in translated
    ):
        translated.extend(
            ["--output-dir", os.path.join(_REPO_ROOT, "docs/sdd/plans/042")]
        )
    return translated


def main(argv: list[str] | None = None) -> int:
    return _canonical_main(
        _translate_legacy_args(list(sys.argv[1:] if argv is None else argv))
    )


if __name__ == "__main__":
    raise SystemExit(main())
