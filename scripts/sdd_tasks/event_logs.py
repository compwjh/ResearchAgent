"""Securely synchronize private JSONL event logs from the SQLite ledger."""

import json
import os
import sqlite3
import stat
import subprocess
import uuid
from pathlib import Path

from .atomic import _open_directory, atomic_write
from .leases import _main_root, _pairs, _reject_json_constant, _timestamp


class EventLogError(ValueError):
    """A private event log could not be safely synchronized."""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _run_directory(main: Path, run_id: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    fd = _open_directory(main)
    try:
        for name in (".sdd", "runtime", "runs", run_id):
            if name in ("runs", run_id):
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(name, flags, dir_fd=fd)
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o700):
                os.close(child)
                raise EventLogError("unsafe private runtime directory")
            os.close(fd)
            fd = child
        result, fd = fd, -1
        return result
    finally:
        if fd >= 0:
            os.close(fd)


def _read_log(directory_fd: int):
    name = "events.jsonl"
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None, b""
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or
            stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
        raise EventLogError("unsafe event log file")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise EventLogError("event log changed while opening")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            return (info.st_dev, info.st_ino), stream.read()
    finally:
        if fd >= 0:
            os.close(fd)


def sync_event_log(conn: sqlite3.Connection, run_id: str, repo_root: Path) -> Path:
    """Validate an existing log as a ledger prefix, then atomically append missing rows."""
    if conn.in_transaction:
        raise EventLogError("event log sync requires a committed ledger")
    try:
        if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
            raise EventLogError("invalid run id")
        main = _main_root(conn)
        supplied = Path(repo_root)
        if not supplied.is_absolute() or supplied.resolve(strict=True) != main:
            raise EventLogError("runtime root does not match ledger")
        relative = ".sdd/runtime/runs/{}/events.jsonl".format(run_id)
        ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", relative],
                                 cwd=str(main), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ignored.returncode != 0:
            raise EventLogError("event log path is not ignored")
        if conn.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is None:
            raise EventLogError("ledger run does not exist")
        rows = conn.execute(
            "SELECT sequence,timestamp,event_type,payload_json FROM events WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        records = []
        for sequence, row in enumerate(rows, 1):
            seq, stamp, event_type, payload_json = row
            if type(seq) is not int or seq != sequence or not isinstance(event_type, str) or not event_type:
                raise EventLogError("ledger event sequence is invalid")
            _timestamp(stamp, "event.timestamp")
            payload = json.loads(payload_json, object_pairs_hook=_pairs,
                                 parse_constant=_reject_json_constant)
            if not isinstance(payload, dict):
                raise EventLogError("ledger event payload is invalid")
            records.append({"run_id": run_id, "sequence": sequence, "timestamp": stamp,
                            "event_type": event_type, "payload": payload})
        directory_fd = _run_directory(main, run_id)
        try:
            identity, existing = _read_log(directory_fd)
            lines = []
            if existing:
                if not existing.endswith(b"\n") or b"\r" in existing:
                    raise EventLogError("event log framing is invalid")
                lines = existing[:-1].split(b"\n")
            if len(lines) > len(records):
                raise EventLogError("event log contains unknown rows")
            for index, line in enumerate(lines):
                logged = json.loads(line.decode("utf-8"), object_pairs_hook=_pairs,
                                    parse_constant=_reject_json_constant)
                expected = records[index]
                if (not isinstance(logged, dict) or set(logged) != set(expected) or
                        type(logged.get("sequence")) is not int or logged != expected or
                        _json(logged.get("payload")) != _json(expected["payload"])):
                    raise EventLogError("event log disagrees with ledger")
            path = main / relative
            if len(lines) < len(records):
                current = None
                try:
                    info = os.stat("events.jsonl", dir_fd=directory_fd, follow_symlinks=False)
                    current = (info.st_dev, info.st_ino)
                except FileNotFoundError:
                    pass
                if current != identity:
                    raise EventLogError("event log changed during synchronization")
                content = "".join(_json(record) + "\n" for record in records).encode("utf-8")
                atomic_write(path, content)
            return path
        finally:
            os.close(directory_fd)
    except EventLogError:
        raise
    except (OSError, ValueError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        raise EventLogError("event log synchronization failed") from exc
