#!/usr/bin/env python3
"""Task09 precise legacy ResearchTask cleanup.

Dry-run is the default.  Deletion requires both ``--execute`` and
``--confirm``; the ResearchStore performs selection, validation, deletion and
audit insertion in one transaction.  No backup is created by this command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.memory.repository import OWNER_ID
from backend.app.research.infrastructure.research_store import ResearchStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", default=OWNER_ID, help="owner scope (default: current owner)")
    parser.add_argument("--execute", action="store_true", help="perform the validated deletion")
    parser.add_argument("--confirm", action="store_true", help="required with --execute")
    parser.add_argument("--dry-run-id", help="cleanup_id returned by a prior dry-run")
    args = parser.parse_args()
    store = ResearchStore()
    if args.execute:
        report = store.execute_legacy_cleanup(args.owner_id, confirm=args.confirm, dry_run_id=args.dry_run_id)
    else:
        report = store.dry_run_legacy_cleanup(args.owner_id)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
