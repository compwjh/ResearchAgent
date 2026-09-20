#!/usr/bin/env python3
"""Check the repository test layout and behavior-based naming convention."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
NUMBERED_DELIVERY_ID = re.compile(r"(?:^|[_-])(?:spec|task)[-_]?\d+(?:[_-]|\.)", re.IGNORECASE)
TEST_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".tsx"}


def main() -> int:
    errors: list[str] = []
    for path in sorted(TESTS.iterdir()):
        if path.is_file() and path.suffix in TEST_SUFFIXES:
            errors.append(f"tests root contains test source: {path.relative_to(ROOT)}")

    for path in sorted(TESTS.rglob("*")):
        if not path.is_file() or path.suffix not in TEST_SUFFIXES:
            continue
        if NUMBERED_DELIVERY_ID.search(path.name):
            errors.append(f"test filename contains delivery id: {path.relative_to(ROOT)}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("test layout: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
