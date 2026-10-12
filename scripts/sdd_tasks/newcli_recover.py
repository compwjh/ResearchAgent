"""Recover one expired Task run without changing its worktree."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .lease_recovery import stored_owner
from .leases import LeaseError, _live_task, recover_expired
from .locks import maintenance_lock, repository_paths
from .newcli_claim import _database
from .owners import OwnerStatus, observe_owner
from .recovery_snapshots import load_recovery_snapshot
from .store import connect
from .workspace import capture_snapshot, compare_snapshot


def recover_from_cli(repo_root: Path, run_id: str) -> dict:
    main, _ = repository_paths(repo_root)
    with maintenance_lock(main), closing(connect(_database(main))) as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise LeaseError("LEASE_NOT_FOUND", "run does not exist")
        task = _live_task(conn, run, main)
        owner = stored_owner(run["owner_json"])
        observed = observe_owner(owner)
        before = load_recovery_snapshot(conn, run_id, task, main)
        current = capture_snapshot(main, task)
        decision = compare_snapshot(before, current)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        report = recover_expired(conn, run_id, observed is not OwnerStatus.DEAD,
                                 decision, now=now)
        return {"run_id": report.run_id, "state": report.state, "action": report.action}
