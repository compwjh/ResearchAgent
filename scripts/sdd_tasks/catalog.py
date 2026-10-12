import json
import os
import subprocess
import warnings
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from .catalog_publish import (
    create_stage,
    discard_stage,
    pin_runtime,
    publish_stage,
    verify_parent,
)
from .catalog_status import status as status
from .documents import TaskDocumentError, parse_task
from .locks import maintenance_lock, runtime_root
from .mirrors import MirrorError, validate_mirrors
from .store import connect, initialize, transaction
from .summaries import SummaryError, scan_summaries
from .summary_import import SummaryImportError, merge_runs, validate_base_commits


class CatalogError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")

@dataclass(frozen=True)
class RebuildReport:
    tasks: int
    runs: int
    deduplicated: int
    database: Path

def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatalogError("GIT_DISCOVERY_FAILED", str(exc)) from exc

def discover_worktrees(repo_root: Path) -> Tuple[Path, ...]:
    root = Path(repo_root).resolve()
    common = Path(_git(root, "rev-parse", "--git-common-dir"))
    common = (common if common.is_absolute() else root / common).resolve()
    listing = _git(root, "worktree", "list", "--porcelain")
    paths = tuple(Path(x[9:]).resolve() for x in listing.splitlines() if x.startswith("worktree "))
    if not paths or root not in paths:
        raise CatalogError("WORKTREE_LIST_INVALID", str(root))
    if not common.is_dir():
        raise CatalogError("WORKTREE_COMMON_DIR_MISMATCH", str(common))
    return paths

def _scan(roots):
    groups, legacy, stale, duplicates = {}, [], [], 0
    for root in roots:
        for path in sorted((root / "docs/sdd/plans").rglob("task-*.md")):
            try:
                current = path
                while current != root:
                    if current.is_symlink():
                        raise CatalogError("TASK_SYMLINK", str(current))
                    current = current.parent
                path.resolve(strict=True).relative_to(root)
                text = path.read_text(encoding="utf-8")
            except CatalogError:
                raise
            except (OSError, UnicodeError, ValueError) as exc:
                raise CatalogError("TASK_READ_FAILED", f"{path}: {exc}") from exc
            if "<!-- sdd-task-meta" not in text:
                legacy.append(str(path.resolve()))
                continue
            try:
                task = parse_task(path)
            except TaskDocumentError as exc:
                raise CatalogError(exc.code, str(exc)) from exc
            copies = groups.setdefault(task.metadata["task_id"], [])
            if copies and copies[0][0].task_hash != task.task_hash:
                raise CatalogError("TASK_HASH_CONFLICT", f"{path}: {task.metadata['task_id']}")
            if any(copy[2] == root for copy in copies):
                raise CatalogError("DUPLICATE_TASK_IN_WORKTREE", str(path))
            copies.append((task, path.relative_to(root).as_posix(), root))
            duplicates += len(copies) > 1
    selected = []
    for task_id, copies in groups.items():
        def state(copy):
            return copy[0].metadata["status"], copy[0].metadata.get("migration_state")

        chosen = copies[0]
        canonical = (roots[0] / chosen[0].metadata["worktree"]["path"]).resolve()
        authority = [x for x in copies if x[2] == canonical]
        if len(authority) > 1:
            raise CatalogError("DUPLICATE_TASK_IN_WORKTREE", task_id)
        if canonical in roots and authority:
            chosen = authority[0]
            stale.extend(str(x[0].path) for x in copies if x is not chosen)
        elif len({state(x) for x in copies}) > 1:
            raise CatalogError("TASK_STATUS_CONFLICT", f"{task_id}: " + ", ".join(str(x[0].path) for x in copies))
        selected.append((chosen[0], chosen[1]))
    for label, paths in (("legacy_tasks_ignored", legacy), ("stale_task_copies_ignored", stale)):
        if paths:
            warnings.warn(label + ": " + ", ".join(paths), RuntimeWarning, stacklevel=2)
    _validate_graph(selected)
    return selected, duplicates

def _validate_graph(tasks):
    by_id = {t.metadata["task_id"]: t for t, _ in tasks}
    for task in by_id.values():
        missing = set(task.metadata["depends_on"]) - by_id.keys()
        if missing:
            raise CatalogError("MISSING_DEPENDENCY", f"{task.path}: {sorted(missing)}")
    stack, done = [], set()
    def visit(node):
        if node in stack:
            cycle = stack[stack.index(node):] + [node]
            raise CatalogError("DEPENDENCY_CYCLE", " -> ".join(f"{by_id[x].path} ({x})" for x in cycle))
        if node not in done:
            stack.append(node)
            for dep in by_id[node].metadata["depends_on"]:
                visit(dep)
            stack.pop()
            done.add(node)
    for node in by_id:
        visit(node)

def _write(conn, tasks):
    sql = ("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(task_id) DO UPDATE SET "
        "source_path=excluded.source_path,status=excluded.status,priority=excluded.priority,"
        "created_at=excluded.created_at,task_hash=excluded.task_hash,prompt_hash=excluded.prompt_hash,"
        "definition_json=excluded.definition_json")
    conn.executemany(sql, [(t.metadata["task_id"], p, t.metadata["status"], t.metadata.get("priority", 100),
                            t.metadata["created_at"], t.task_hash, t.prompt_hash,
                            json.dumps(t.metadata, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":"))) for t, p in tasks])
    conn.executemany("DELETE FROM dependencies WHERE task_id=?", [(t.metadata["task_id"],) for t, _ in tasks])
    conn.executemany("INSERT INTO dependencies VALUES (?, ?)",
                     [(t.metadata["task_id"], d) for t, _ in tasks for d in t.metadata["depends_on"]])

def _active_lease(conn):
    now = datetime.now(timezone.utc)
    for task_id, stamp in conn.execute("SELECT task_id, expires_at FROM leases"):
        try:
            expires = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if expires.utcoffset() is None:
                raise ValueError("timezone required")
        except ValueError as exc:
            raise CatalogError("LEASE_TIMESTAMP_INVALID", task_id) from exc
        if expires > now:
            return task_id

def rebuild(db_path: Path, repo_root: Path) -> RebuildReport:
    with maintenance_lock(repo_root):
        roots = discover_worktrees(repo_root)
        database = runtime_root(repo_root) / "task-ledger.sqlite3"
        if Path(db_path) != database:
            raise CatalogError("DATABASE_PATH_INVALID", str(database))
        tasks, deduplicated = _scan(roots)
        for task, _ in tasks:
            owner = next(root for root in sorted(roots, key=lambda x: len(x.parts), reverse=True)
                         if root in task.path.resolve().parents)
            try:
                validate_mirrors(task, owner)
            except MirrorError as exc:
                raise CatalogError(exc.code, str(exc)) from exc
        try:
            summaries = scan_summaries(roots, tasks)
            validate_base_commits(repo_root, summaries)
            return _rebuild(database, tasks, deduplicated, summaries, roots[0])
        except (SummaryError, SummaryImportError) as exc:
            raise CatalogError(exc.code, str(exc)) from exc

def _rebuild(database: Path, tasks, deduplicated: int, summaries=(), main_root=None) -> RebuildReport:
    by_id = {t.metadata["task_id"]: t for t, _ in tasks}
    try:
        parent_fd, exists = pin_runtime(database, main_root)
    except (OSError, ValueError) as exc:
        raise CatalogError("DATABASE_PATH_UNSAFE", str(exc)) from exc
    try:
        if exists:
            verify_parent(database.parent, parent_fd)
            with closing(connect(database)) as conn:
                initialize(conn)
                with transaction(conn, immediate=True):
                    active = _active_lease(conn)
                    if active:
                        raise CatalogError("ACTIVE_LEASE", active)
                    missing = sorted({r[0] for r in conn.execute("SELECT task_id FROM tasks")} - by_id.keys())
                    if missing:
                        raise CatalogError("TASK_DEFINITION_MISSING", ", ".join(missing))
                    for row in conn.execute("SELECT task_id,task_hash FROM runs WHERE state IN('claimed','running')"):
                        if row["task_id"] in by_id and by_id[row["task_id"]].task_hash != row["task_hash"]:
                            raise CatalogError("RUN_HASH_DRIFT", row["task_id"])
                    _write(conn, tasks)
                    merge_runs(conn, summaries)
                runs = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
            verify_parent(database.parent, parent_fd)
        else:
            stage = create_stage(parent_fd)
            staging = database.parent / stage
            try:
                verify_parent(database.parent, parent_fd)
                with closing(connect(staging)) as conn:
                    initialize(conn)
                    with transaction(conn, immediate=True):
                        _write(conn, tasks)
                        runs = merge_runs(conn, summaries)
                    if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                        raise CatalogError("WAL_CHECKPOINT_BUSY", str(staging))
                verify_parent(database.parent, parent_fd)
                publish_stage(parent_fd, stage, database.name)
            except FileExistsError as exc:
                raise CatalogError("DATABASE_APPEARED", str(database)) from exc
            finally:
                discard_stage(parent_fd, stage)
    finally:
        os.close(parent_fd)
    return RebuildReport(len(tasks), runs, deduplicated, database)
