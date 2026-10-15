"""Recover one expired Task run without changing its worktree."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .completion_recovery import resume_dead_completion
from .lease_recovery import stored_owner
from .leases import LeaseError, _has_failed_retry_source, _live_task, recover_expired
from .locks import maintenance_lock, repository_paths
from .newcli_claim import _database
from .owners import OwnerStatus, observe_owner
from .recovery_snapshots import load_recovery_snapshot
from .store import connect
from .workspace import capture_snapshot, compare_snapshot


def recover_from_cli(repo_root: Path, run_id: str) -> dict:
    main, _ = repository_paths(repo_root)
    with maintenance_lock(main), closing(connect(_database(main))) as conn:
        result = resume_dead_completion(conn, repo_root, run_id)
        if result is not None:
            return {"run_id": run_id, "state": result["outcome"],
                    "action": "completion_resumed"}
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise LeaseError("LEASE_NOT_FOUND", "run does not exist")
        task = _live_task(conn, run, main)
        owner = stored_owner(run["owner_json"])
        observed = observe_owner(owner)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not _has_failed_retry_source(conn, run_id, task, main):
            before = load_recovery_snapshot(conn, run_id, task, main)
            current = capture_snapshot(main, task)
            decision = compare_snapshot(before, current)
        else:
            from .active_failed_recovery import (
                compare_active_failed_workspace,
                load_expired_failed_source,
            )

            proof = load_expired_failed_source(conn, run_id, task, main, now=now)
            current = capture_snapshot(main, task)
            decision = compare_active_failed_workspace(proof, current, task)
        report = recover_expired(conn, run_id, observed is not OwnerStatus.DEAD,
                                 decision, now=now)
        return {"run_id": report.run_id, "state": report.state, "action": report.action}
