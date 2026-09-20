#!/usr/bin/env python3
"""Check that test basenames describe behavior instead of spec/task numbers.

The check is intentionally dependency-free so it can run before the test
environment is installed.  It scans test files recursively and exits non-zero
when a basename contains ``specNNN`` or ``taskNN`` (case-insensitive).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FORBIDDEN_NUMBER = re.compile(r"(?:spec|task)\d+", re.IGNORECASE)
TEST_EXTENSIONS = {".py", ".js", ".mjs", ".cjs"}


def find_violations(root: Path) -> list[Path]:
    """Return test files whose basename embeds a spec/task number."""

    violations: list[Path] = []
    for path in sorted(root.rglob("test_*")):
        if path.is_file() and path.suffix.lower() in TEST_EXTENSIONS:
            if FORBIDDEN_NUMBER.search(path.stem):
                violations.append(path)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path("tests"),
        help="test directory to scan (default: tests)",
    )
    args = parser.parse_args()
    root = args.root
    if not root.is_dir():
        parser.error(f"test directory does not exist: {root}")

    violations = find_violations(root)
    if violations:
        print("test naming violations (remove spec/task numbers):")
        for path in violations:
            print(f"- {path}")
        return 1

    print(f"test naming check passed: no spec/task numbers under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
