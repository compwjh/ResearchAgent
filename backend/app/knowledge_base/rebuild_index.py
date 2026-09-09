"""Non-interactive Spec018 candidate rebuild maintenance command.

No option means a read-only dry-run.  A real replacement requires the explicit
``--confirm-replace`` switch and is intended for a stopped-service window.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.app.knowledge_base.infrastructure.candidate_index import QdrantCandidateIndexPort
from backend.app.knowledge_base.infrastructure.candidate_rebuild import CandidateRebuildService, RebuildError
from backend.app.knowledge_base.infrastructure.index import get_client
from backend.app.platform.config import EMBED_DIM, KB_META_PATH, KB_PAPERS_DIR, QDRANT_PATH


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and validate a Spec018 candidate index")
    parser.add_argument("--dry-run", action="store_true", help="parse and preflight only (default)")
    parser.add_argument("--confirm-replace", action="store_true", help="allow candidate writes and alias switch")
    parser.add_argument("--recover-stale-lock", metavar="RUN_ID")
    parser.add_argument("--resume-switch", metavar="RUN_ID")
    parser.add_argument("--resume-finalize", metavar="RUN_ID")
    parser.add_argument("--cleanup-failed", metavar="RUN_ID")
    parser.add_argument("--metadata-path", type=Path, default=KB_META_PATH)
    parser.add_argument("--papers-dir", type=Path, default=KB_PAPERS_DIR)
    parser.add_argument("--runtime-root", type=Path, default=Path(QDRANT_PATH).parent / "rebuild-runs")
    return parser


def main(argv: Any = None, *, index: Any = None, service_factory: Any = None) -> int:
    args = _parser().parse_args(argv)
    targets = [target for target in (args.resume_switch, args.resume_finalize, args.cleanup_failed) if target]
    if len(targets) > 1:
        print(json.dumps({"status": "failed", "error_code": "COMMAND_AMBIGUOUS"}, ensure_ascii=False, sort_keys=True))
        return 2
    if (targets or args.recover_stale_lock) and targets and not args.confirm_replace:
        print(json.dumps({"status": "failed", "error_code": "CONFIRM_REPLACE_REQUIRED"}, ensure_ascii=False, sort_keys=True))
        return 2
    if args.recover_stale_lock and (not targets or args.recover_stale_lock != targets[0]):
        print(json.dumps({"status": "failed", "error_code": "RECOVER_STALE_RUN_ID_REQUIRED"}, ensure_ascii=False, sort_keys=True))
        return 2
    if index is None:
        client = get_client()
        index = QdrantCandidateIndexPort(client, dense_dim=EMBED_DIM)
    factory = service_factory or CandidateRebuildService
    service = factory(
        metadata_path=args.metadata_path,
        papers_dir=args.papers_dir,
        runtime_root=args.runtime_root,
        index=index,
    )
    try:
        if args.resume_switch:
            result = service.resume_switch(args.resume_switch, recover_stale_lock=args.recover_stale_lock == args.resume_switch)
        elif args.resume_finalize:
            result = service.resume_finalize(args.resume_finalize, recover_stale_lock=args.recover_stale_lock == args.resume_finalize)
        elif args.cleanup_failed:
            result = service.cleanup_failed(args.cleanup_failed, recover_stale_lock=args.recover_stale_lock == args.cleanup_failed)
        else:
            if args.recover_stale_lock:
                raise RebuildError("RECOVER_STALE_RUN_ID_REQUIRED")
            result = service.run(dry_run=not args.confirm_replace or args.dry_run, confirm_replace=args.confirm_replace)
    except RebuildError as error:
        print(json.dumps({"status": "failed", "error_code": error.code}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
