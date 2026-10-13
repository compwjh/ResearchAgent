"""Private, durable storage primitives for a reconciled Git index image."""
import hashlib
import json
import os
import secrets
import stat
import subprocess
import uuid
from contextlib import suppress
from pathlib import Path

from . import atomic
from .completion_journal import read_journal, write_journal
from .git_candidate_objects import check_source_anchors, store_verified_blobs
from .git_index import _parse_index, read_index_snapshot
from .git_index_lock import acquire_owned_index_lock

_DROP_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


class GitReconciliationError(ValueError):
    """A safe reconciliation image could not be verified or published."""


def _git(root, *args, index_file=None, input_bytes=None):
    env = os.environ.copy()
    for key in _DROP_ENV:
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if index_file is not None:
        env["GIT_INDEX_FILE"] = os.fspath(index_file)
    try:
        result = subprocess.run(["git", "-C", os.fspath(root), *args], input=input_bytes,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_COMMAND_FAILED") from exc
    if result.returncode:
        raise GitReconciliationError("GIT_RECONCILIATION_COMMAND_FAILED")
    return result.stdout


def _observation(snapshot):
    return {key: snapshot[key] for key in
            ("index_sha256", "committed_entries", "other_entries_sha256")}


def _index_snapshot(raw, ls_files, targets):
    entries = _parse_index(ls_files)
    wanted = set(targets)
    committed = sorted((item for item in entries if item["path"] in wanted),
                       key=lambda item: (item["path"].encode("utf-8"), item["stage"]))
    others = sorted((item for item in entries if item["path"] not in wanted),
                    key=lambda item: (item["path"].encode("utf-8"), item["stage"]))
    encoded = json.dumps(others, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {"index_sha256": hashlib.sha256(raw).hexdigest(), "committed_entries": committed,
            "other_entries_sha256": hashlib.sha256(encoded).hexdigest()}


def _registered_index_path(root, journal):
    top = _git(root, "rev-parse", "--show-toplevel")
    registry = _git(root, "worktree", "list", "--porcelain", "-z")
    index = _git(root, "rev-parse", "--path-format=absolute", "--git-path", "index")
    git_dir = _git(root, "rev-parse", "--absolute-git-dir")
    try:
        top = Path(os.fsdecode(top.rstrip(b"\n")))
        actual = Path(os.fsdecode(index.rstrip(b"\n")))
        expected = Path(os.fsdecode(git_dir.rstrip(b"\n"))) / "index"
        recorded = Path(journal["index_before"]["git_index_path"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_INDEX_PATH_INVALID") from exc
    if (top != root or registry.count(b"worktree " + os.fsencode(root) + b"\0") != 1 or
            not actual.is_absolute() or not recorded.is_absolute() or
            os.path.normpath(actual) != os.path.normpath(expected) or
            os.path.normpath(actual) != os.path.normpath(recorded)):
        raise GitReconciliationError("GIT_RECONCILIATION_INDEX_PATH_INVALID")
    return actual


def _verify_index_parent(index_path, pinned):
    current = -1
    try:
        current = atomic._open_directory(index_path.parent)
        first, second = os.fstat(pinned), os.fstat(current)
        if (first.st_dev, first.st_ino, first.st_mode, first.st_uid) != (
                second.st_dev, second.st_ino, second.st_mode, second.st_uid):
            raise GitReconciliationError("GIT_RECONCILIATION_INDEX_PARENT_CHANGED")
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_INDEX_PARENT_CHANGED") from exc
    finally:
        if current >= 0:
            os.close(current)


def _post_cas_index_snapshot(root, index_path, committed_paths, parent):
    _verify_index_parent(index_path, parent)
    before = _read_index_file(index_path)
    entries = _git(root, "ls-files", "--stage", "-z")
    after = _read_index_file(index_path)
    _verify_index_parent(index_path, parent)
    if before != after:
        raise GitReconciliationError("GIT_RECONCILIATION_INDEX_CHANGED")
    return _index_snapshot(before, entries, committed_paths)


def _main_run_fd(worktree, journal_path, run_id):
    """Pin the canonical main-worktree run directory named by the journal."""
    records = _git(worktree, "worktree", "list", "--porcelain", "-z").split(b"\0")
    if not records or not records[0].startswith(b"worktree "):
        raise GitReconciliationError("GIT_RECONCILIATION_MAIN_WORKTREE_INVALID")
    main = Path(os.fsdecode(records[0][len(b"worktree "):])).resolve(strict=True)
    expected = main / ".sdd" / "runtime" / "runs" / run_id / "completion.json"
    if Path(os.path.abspath(journal_path)) != expected:
        raise GitReconciliationError("GIT_RECONCILIATION_JOURNAL_PATH_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    parent = -1
    try:
        parent = atomic._open_directory(main / ".sdd" / "runtime")
        info = os.fstat(parent)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise GitReconciliationError("GIT_RECONCILIATION_RUNTIME_UNSAFE")
        for name in ("runs", run_id):
            child = os.open(name, flags, dir_fd=parent)
            info = os.fstat(child)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o700):
                os.close(child)
                raise GitReconciliationError("GIT_RECONCILIATION_RUNTIME_UNSAFE")
            os.close(parent)
            parent = child
        return main, parent
    except GitReconciliationError:
        if parent >= 0:
            os.close(parent)
        raise
    except OSError as exc:
        if parent >= 0:
            os.close(parent)
        raise GitReconciliationError("GIT_RECONCILIATION_RUNTIME_UNSAFE") from exc


def _verify_run_fd(main, run_id, pinned):
    current = -1
    try:
        current = atomic._open_directory(main / ".sdd" / "runtime" / "runs" / run_id)
        expected, actual = os.fstat(pinned), os.fstat(current)
        if (expected.st_dev, expected.st_ino, expected.st_uid, stat.S_IMODE(expected.st_mode)) != (
                actual.st_dev, actual.st_ino, actual.st_uid, stat.S_IMODE(actual.st_mode)):
            raise GitReconciliationError("GIT_RECONCILIATION_RUNTIME_CHANGED")
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_RUNTIME_CHANGED") from exc
    finally:
        if current >= 0:
            os.close(current)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_private_file(parent, name, *, links=1):
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        info = os.fstat(fd)
        path_info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != links or
                _stamp(info) != _stamp(path_info)):
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_UNSAFE")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        path_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _stamp(info) != _stamp(after) or _stamp(after) != _stamp(path_after):
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_CHANGED")
        return b"".join(chunks)
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_UNREADABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _read_index_file(path):
    parent = fd = -1
    try:
        parent = atomic._open_directory(path.parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1:
            raise GitReconciliationError("GIT_RECONCILIATION_INDEX_UNSAFE")
        chunks = []
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            chunks.append(part)
        after = os.fstat(fd)
        name_after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if _stamp(before) != _stamp(after) or _stamp(after) != _stamp(name_after):
            raise GitReconciliationError("GIT_RECONCILIATION_INDEX_CHANGED")
        return b"".join(chunks)
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_INDEX_UNREADABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if parent >= 0:
            os.close(parent)


def _new_image_temp(parent, content):
    for _ in range(32):
        name = ".index-after-" + secrets.token_hex(16)
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            break
        except FileExistsError:
            continue
    else:
        raise GitReconciliationError("GIT_RECONCILIATION_TEMP_UNAVAILABLE")
    try:
        view = memoryview(content)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short image write")
            view = view[count:]
        os.fsync(fd)
        os.fsync(parent)
        return name
    except OSError as exc:
        with suppress(OSError):
            os.unlink(name, dir_fd=parent)
            os.fsync(parent)
        raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_WRITE_FAILED") from exc
    finally:
        os.close(fd)


def _publish_image(parent, temporary, content):
    try:
        try:
            existing = os.stat("index-after", dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is None:
            try:
                os.link(temporary, "index-after", src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
                os.fsync(parent)
            except FileExistsError:
                existing = os.stat("index-after", dir_fd=parent, follow_symlinks=False)
        if existing is not None and existing.st_nlink == 2:
            aliases = []
            for name in os.listdir(parent):
                if not name.startswith(".index-after-"):
                    continue
                item = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (item.st_dev, item.st_ino) == (existing.st_dev, existing.st_ino):
                    aliases.append(name)
            if len(aliases) != 1 or _read_private_file(parent, "index-after", links=2) != content:
                raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_UNSAFE")
            if _read_private_file(parent, aliases[0], links=2) != content:
                raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_MISMATCH")
            os.unlink(aliases[0], dir_fd=parent)
            os.fsync(parent)
        elif existing is not None and _read_private_file(parent, "index-after") != content:
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_MISMATCH")
        try:
            os.unlink(temporary, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            pass
        if _read_private_file(parent, "index-after") != content:
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_CHANGED")
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_PUBLISH_FAILED") from exc


def _secure_temp_mode(parent, name):
    fd = -1
    try:
        fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(fd)
        path_info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1 or
                (before.st_dev, before.st_ino) != (path_info.st_dev, path_info.st_ino)):
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_UNSAFE")
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        os.fsync(parent)
        after, named = os.fstat(fd), os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _stamp(after) != _stamp(named) or stat.S_IMODE(after.st_mode) != 0o600 or after.st_nlink != 1:
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_CHANGED")
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_UNSAFE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def prepare_reconciliation_index(worktree: Path, journal_path: Path) -> dict:
    """Build and durably record the private target-adjusted index image."""
    root, path = Path(worktree).resolve(strict=True), Path(journal_path)
    run_id, temporary = path.parent.name, None
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError("noncanonical run id")
    except ValueError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_JOURNAL_PATH_INVALID") from exc
    main, parent = _main_run_fd(root, path, run_id)
    try:
        journal = read_journal(path)
        if journal["run_id"] != run_id:
            raise GitReconciliationError("GIT_RECONCILIATION_RUN_MISMATCH")
        journal = acquire_owned_index_lock(root, path)
        if (journal["phase"], journal["index_recovery_stage"]) != ("index_locking", "marker_durable"):
            raise GitReconciliationError("GIT_RECONCILIATION_PHASE_INVALID")
        _git(main, "check-ignore", "--quiet", "--", ".sdd/runtime/runs/{}/index-after".format(run_id))
        store_verified_blobs(root, journal)
        before = read_index_snapshot(root, journal["committed_paths"], original_head=journal["original_head"])
        if (before["git_index_path"] != journal["index_before"]["git_index_path"] or
                _observation(before) != journal["index_observed_before"] or
                _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["original_head"]):
            raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
        raw = _read_index_file(Path(before["git_index_path"]))
        if _index_snapshot(raw, _git(root, "ls-files", "--stage", "-z"),
                           journal["committed_paths"]) != _observation(before):
            raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
        _verify_run_fd(main, run_id, parent)
        temporary = _new_image_temp(parent, raw)
        temp_path = main / ".sdd/runtime/runs" / run_id / temporary
        updates = []
        for item in journal["expected_git_entries"]:
            mode, oid = item["mode"], item["object_id"]
            header = "{} {} 0\t".format(mode or "0", oid or "0" * len(journal["original_head"]))
            updates.append(header.encode("ascii") + item["path"].encode("utf-8") + b"\0")
        _verify_run_fd(main, run_id, parent)
        _git(root, "update-index", "-z", "--index-info", index_file=temp_path, input_bytes=b"".join(updates))
        _verify_run_fd(main, run_id, parent)
        _secure_temp_mode(parent, temporary)
        image = _read_private_file(parent, temporary)
        after = _index_snapshot(image, _git(root, "ls-files", "--stage", "-z", index_file=temp_path),
                                journal["committed_paths"])
        expected = [{"path": item["path"], "stage": 0, "mode": item["mode"], "object_id": item["object_id"]}
                    for item in journal["expected_git_entries"] if item["mode"] is not None]
        if (after["committed_entries"] != expected or
                after["other_entries_sha256"] != journal["index_observed_before"]["other_entries_sha256"]):
            raise GitReconciliationError("GIT_RECONCILIATION_ENTRIES_MISMATCH")
        if _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["original_head"]:
            raise GitReconciliationError("GIT_RECONCILIATION_HEAD_CHANGED")
        current = read_index_snapshot(root, journal["committed_paths"], original_head=journal["original_head"])
        if _observation(current) != journal["index_observed_before"]:
            raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
        acquire_owned_index_lock(root, path)
        _verify_run_fd(main, run_id, parent)
        _publish_image(parent, temporary, image)
        temporary = None
        _verify_run_fd(main, run_id, parent)
        acquire_owned_index_lock(root, path)
        updated = dict(journal, phase="index_after_prepared", index_after=after,
                       index_recovery_stage="reconciliation_index_durable")
        write_journal(path, updated, previous_phase=journal["phase"])
        return read_journal(path)
    finally:
        if temporary is not None:
            with suppress(OSError):
                os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
        os.close(parent)


def _marker_bytes(journal):
    marker = {"schema": "sdd-index-lock/v1", "run_id": journal["run_id"],
              "index_lock_owner_token": journal["index_lock_owner_token"],
              "index_before_sha256": journal["index_before"]["index_sha256"]}
    return (json.dumps(marker, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _lock_identity(parent, fd, journal):
    info = os.fstat(fd)
    named = os.stat("index.lock", dir_fd=parent, follow_symlinks=False)
    expected = journal["index_lock_identity"]
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or
            (info.st_dev, info.st_ino) != (expected["device"], expected["inode"]) or
            _stamp(info) != _stamp(named)):
        raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IDENTITY_MISMATCH")
    return info


def _lock_bytes(parent, fd, journal):
    try:
        before = _lock_identity(parent, fd, journal)
        chunks = []
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            chunks.append(part)
        after = _lock_identity(parent, fd, journal)
        if _stamp(before) != _stamp(after):
            raise GitReconciliationError("GIT_RECONCILIATION_LOCK_CHANGED")
        return b"".join(chunks)
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_LOCK_UNREADABLE") from exc


def _open_owned_lock(index_path, journal):
    parent = fd = -1
    try:
        index = Path(index_path)
        if not index.is_absolute() or index.name != "index":
            raise GitReconciliationError("GIT_RECONCILIATION_INDEX_PATH_INVALID")
        parent = atomic._open_directory(index.parent)
        fd = os.open("index.lock", os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        data = _lock_bytes(parent, fd, journal)
        return parent, fd, data
    except GitReconciliationError:
        if fd >= 0:
            os.close(fd)
        if parent >= 0:
            os.close(parent)
        raise
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        if parent >= 0:
            os.close(parent)
        raise GitReconciliationError("GIT_RECONCILIATION_LOCK_UNSAFE") from exc


def _write_owned_lock(parent, fd, journal, content):
    try:
        _lock_identity(parent, fd, journal)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        view = memoryview(content)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short lock write")
            view = view[count:]
        os.fsync(fd)
        os.fsync(parent)
        os.lseek(fd, 0, os.SEEK_SET)
        if _lock_bytes(parent, fd, journal) != content:
            raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IMAGE_MISMATCH")
    except GitReconciliationError:
        raise
    except OSError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_LOCK_WRITE_FAILED") from exc


def _complete_json(content):
    try:
        json.loads(content.decode("utf-8"))
        return True
    except (UnicodeError, ValueError):
        return False


def write_owned_index_image(worktree: Path, journal_path: Path) -> dict:
    """Write the durable image into this run's existing lock inode, then mark stage 4."""
    required = {os.open, os.stat, os.link, os.unlink}
    if not hasattr(os, "O_NOFOLLOW") or not required <= os.supports_dir_fd:
        raise GitReconciliationError("GIT_RECONCILIATION_UNSUPPORTED")
    root, path = Path(worktree).resolve(strict=True), Path(journal_path)
    run_id = path.parent.name
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError("noncanonical run id")
    except ValueError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_JOURNAL_PATH_INVALID") from exc
    main, run_fd = _main_run_fd(root, path, run_id)
    lock_parent = lock_fd = -1
    try:
        journal = read_journal(path)
        if (journal["run_id"] != run_id or journal["phase"] != "index_after_prepared" or
                journal["index_recovery_stage"] not in {"reconciliation_index_durable", "lock_index_durable"}):
            raise GitReconciliationError("GIT_RECONCILIATION_PHASE_INVALID")
        _git(main, "check-ignore", "--quiet", "--", ".sdd/runtime/runs/{}/index-after".format(run_id))
        image = _read_private_file(run_fd, "index-after")
        _verify_run_fd(main, run_id, run_fd)
        image_state = _index_snapshot(image, _git(root, "ls-files", "--stage", "-z",
                                                  index_file=main / ".sdd/runtime/runs" / run_id / "index-after"),
                                      journal["committed_paths"])
        expected = [{"path": item["path"], "stage": 0, "mode": item["mode"], "object_id": item["object_id"]}
                    for item in journal["expected_git_entries"] if item["mode"] is not None]
        if (image_state != journal["index_after"] or image_state["committed_entries"] != expected or
                image_state["other_entries_sha256"] != journal["index_observed_before"]["other_entries_sha256"]):
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_MISMATCH")
        index_path = Path(journal["index_before"]["git_index_path"])
        current = read_index_snapshot(root, journal["committed_paths"], original_head=journal["original_head"])
        if (current["git_index_path"] != str(index_path) or
                _observation(current) != journal["index_observed_before"] or
                _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["original_head"]):
            raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
        _verify_run_fd(main, run_id, run_fd)
        lock_parent, lock_fd, lock = _open_owned_lock(index_path, journal)
        marker = _marker_bytes(journal)
        if journal["index_recovery_stage"] == "lock_index_durable":
            if lock != image:
                raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IMAGE_MISMATCH")
        elif lock != image:
            if lock != marker and _complete_json(lock):
                raise GitReconciliationError("GIT_RECONCILIATION_LOCK_FOREIGN_CONTENT")
            if lock != marker:
                _lock_identity(lock_parent, lock_fd, journal)
            _write_owned_lock(lock_parent, lock_fd, journal, image)
        else:
            os.fsync(lock_fd)
            os.fsync(lock_parent)
        os.lseek(lock_fd, 0, os.SEEK_SET)
        if _lock_bytes(lock_parent, lock_fd, journal) != image:
            raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IMAGE_MISMATCH")
        current = read_index_snapshot(root, journal["committed_paths"], original_head=journal["original_head"])
        if (_observation(current) != journal["index_observed_before"] or
                _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["original_head"]):
            raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
        if journal["index_recovery_stage"] == "lock_index_durable":
            return journal
        updated = dict(journal, index_recovery_stage="lock_index_durable")
        write_journal(path, updated, previous_phase=journal["phase"])
        return read_journal(path)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if lock_parent >= 0:
            os.close(lock_parent)
        os.close(run_fd)


def install_reconciled_index(worktree: Path, journal_path: Path, *, task_branch: str) -> dict:
    """Atomically install the verified index image after the candidate ref CAS."""
    if (not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd or
            os.stat not in os.supports_dir_fd or os.rename not in os.supports_dir_fd):
        raise GitReconciliationError("GIT_RECONCILIATION_UNSUPPORTED")
    from .git_candidate_cas import _branch_ref, _verify_candidate

    root, path = Path(worktree).resolve(strict=True), Path(journal_path)
    run_id = path.parent.name
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError("noncanonical run id")
    except ValueError as exc:
        raise GitReconciliationError("GIT_RECONCILIATION_JOURNAL_PATH_INVALID") from exc
    main, run_fd = _main_run_fd(root, path, run_id)
    parent = lock_fd = -1
    try:
        journal = read_journal(path)
        phase_stage = (journal["phase"], journal["index_recovery_stage"])
        if phase_stage not in {("committed", "ref_committed"), ("index_reconciled", "index_installed"),
                               ("ledger_finalizing", "index_installed")}:
            raise GitReconciliationError("GIT_RECONCILIATION_PHASE_INVALID")
        _git(main, "check-ignore", "--quiet", "--", ".sdd/runtime/runs/{}/index-after".format(run_id))
        image = _read_private_file(run_fd, "index-after")
        image_path = main / ".sdd/runtime/runs" / run_id / "index-after"
        image_state = _index_snapshot(image, _git(root, "ls-files", "--stage", "-z", index_file=image_path),
                                      journal["committed_paths"])
        _verify_run_fd(main, run_id, run_fd)
        expected = [{"path": item["path"], "stage": 0, "mode": item["mode"], "object_id": item["object_id"]}
                    for item in journal["expected_git_entries"] if item["mode"] is not None]
        if (image_state != journal["index_after"] or image_state["committed_entries"] != expected or
                image_state["other_entries_sha256"] != journal["index_observed_before"]["other_entries_sha256"]):
            raise GitReconciliationError("GIT_RECONCILIATION_IMAGE_MISMATCH")
        index_path = _registered_index_path(root, journal)
        parent = atomic._open_directory(index_path.parent)
        _verify_index_parent(index_path, parent)
        _branch_ref(root, journal["task_id"], task_branch)
        if _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["candidate_commit_hash"]:
            raise GitReconciliationError("GIT_RECONCILIATION_HEAD_CONFLICT")
        _verify_candidate(root, journal)
        check_source_anchors(root, journal)
        before, after = journal["index_observed_before"], journal["index_after"]
        live = _post_cas_index_snapshot(root, index_path, journal["committed_paths"], parent)
        try:
            lock_fd = os.open("index.lock", os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                              dir_fd=parent)
            lock = _lock_bytes(parent, lock_fd, journal)
        except FileNotFoundError:
            lock = None
        if phase_stage in {("index_reconciled", "index_installed"), ("ledger_finalizing", "index_installed")}:
            if live != after or lock is not None:
                raise GitReconciliationError("GIT_RECONCILIATION_INSTALLED_STATE_CHANGED")
            _verify_index_parent(index_path, parent)
            return journal
        if live not in (before, after):
            raise GitReconciliationError("GIT_RECONCILIATION_INDEX_CONFLICT")
        if lock is None:
            if live != after:
                raise GitReconciliationError("GIT_RECONCILIATION_LOCK_MISSING")
        else:
            if lock != image:
                raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IMAGE_MISMATCH")
            _verify_index_parent(index_path, parent)
            _branch_ref(root, journal["task_id"], task_branch)
            if (_git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["candidate_commit_hash"] or
                    _post_cas_index_snapshot(root, index_path, journal["committed_paths"], parent) not in (before, after)):
                raise GitReconciliationError("GIT_RECONCILIATION_BASE_CHANGED")
            check_source_anchors(root, journal)
            _lock_identity(parent, lock_fd, journal)
            os.lseek(lock_fd, 0, os.SEEK_SET)
            if _lock_bytes(parent, lock_fd, journal) != image:
                raise GitReconciliationError("GIT_RECONCILIATION_LOCK_IMAGE_MISMATCH")
            os.replace("index.lock", "index", src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        _verify_index_parent(index_path, parent)
        if (_post_cas_index_snapshot(root, index_path, journal["committed_paths"], parent) != after or
                _git(root, "rev-parse", "HEAD").strip().decode("ascii") != journal["candidate_commit_hash"]):
            raise GitReconciliationError("GIT_RECONCILIATION_INSTALL_VERIFY_FAILED")
        _branch_ref(root, journal["task_id"], task_branch)
        check_source_anchors(root, journal)
        try:
            os.stat("index.lock", dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise GitReconciliationError("GIT_RECONCILIATION_LOCK_REMAINS")
        _verify_run_fd(main, run_id, run_fd)
        updated = dict(journal, phase="index_reconciled", index_recovery_stage="index_installed")
        write_journal(path, updated, previous_phase=journal["phase"])
        _verify_run_fd(main, run_id, run_fd)
        return read_journal(path)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if parent >= 0:
            os.close(parent)
        os.close(run_fd)
