"""No-follow filesystem reads and filter-free Git hashing for journal anchors."""
import os
import stat
import subprocess

from . import atomic
from .journal_fields import validate_object_id

_ATTRS = ("filter", "working-tree-encoding", "text", "eol", "crlf", "ident")
_DROP_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


class GitExpectedEntriesError(ValueError):
    """A candidate path cannot be anchored to raw Git blob bytes safely."""


def git(root, *args, input_data=None, missing=False):
    env = os.environ.copy()
    for key in _DROP_ENV:
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(["git", "-C", os.fspath(root), *args], input=input_data,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except OSError as exc:
        raise GitExpectedEntriesError("GIT_EXPECTED_COMMAND_FAILED") from exc
    if missing and result.returncode == 1 and not result.stdout:
        return None
    if result.returncode:
        raise GitExpectedEntriesError("GIT_EXPECTED_COMMAND_FAILED")
    return result.stdout


def config(root, key, default):
    value = git(root, "config", "--bool", "--get", key, missing=True)
    if value is None:
        return default
    value = value.strip()
    if value not in {b"true", b"false"}:
        raise GitExpectedEntriesError("GIT_EXPECTED_CONFIG_INVALID")
    return value == b"true"


def check_attributes(root, paths):
    if not paths:
        return
    request = b"".join(path.encode("utf-8") + b"\0" for path in paths)
    data = git(root, "check-attr", "-z", "--stdin", *_ATTRS, input_data=request)
    fields = data.split(b"\0")
    if fields[-1] != b"":
        raise GitExpectedEntriesError("GIT_EXPECTED_ATTRIBUTES_INVALID")
    fields.pop()
    expected = {(path, attr) for path in paths for attr in _ATTRS}
    seen = set()
    for pos in range(0, len(fields), 3):
        try:
            path, attr, value = (fields[pos].decode("utf-8"), fields[pos + 1].decode("ascii"),
                                 fields[pos + 2].decode("utf-8"))
        except (IndexError, UnicodeError) as exc:
            raise GitExpectedEntriesError("GIT_EXPECTED_ATTRIBUTES_INVALID") from exc
        pair = (path, attr)
        if pair not in expected or pair in seen:
            raise GitExpectedEntriesError("GIT_EXPECTED_ATTRIBUTES_INVALID")
        seen.add(pair)
        if value not in {"unspecified", "unset"}:
            raise GitExpectedEntriesError("GIT_EXPECTED_CONVERSION_ACTIVE")
    if seen != expected:
        raise GitExpectedEntriesError("GIT_EXPECTED_ATTRIBUTES_INVALID")


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def source(root, relative):
    if (not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd or
            os.readlink not in os.supports_dir_fd):
        raise GitExpectedEntriesError("GIT_EXPECTED_PLATFORM_UNSAFE")
    parts = relative.split("/")
    try:
        parent = atomic._open_directory(root.joinpath(*parts[:-1]))
    except FileNotFoundError:
        return None, None, None, None
    fd = -1
    try:
        try:
            before = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return None, None, None, None
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED") from None
        if stat.S_ISLNK(before.st_mode):
            payload = os.readlink(os.fsencode(parts[-1]), dir_fd=parent)
            after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if stamp(before) != stamp(after):
                raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED")
            return "symlink", before.st_mode, payload, stamp(after)
        if not stat.S_ISREG(before.st_mode):
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_UNSAFE")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or stamp(opened) != stamp(before):
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if stamp(opened) != stamp(after):
            raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_CHANGED")
        return "regular", after.st_mode, b"".join(chunks), stamp(after)
    except GitExpectedEntriesError:
        raise
    except OSError as exc:
        raise GitExpectedEntriesError("GIT_EXPECTED_SOURCE_UNSAFE") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)


def mode(kind, fs_mode, old_mode, filemode):
    if kind == "symlink":
        return "120000"
    if kind != "regular":
        return old_mode if not filemode and old_mode in {"100644", "100755"} else "100644"
    if not filemode and old_mode in {"100644", "100755"}:
        return old_mode
    return "100755" if fs_mode & 0o111 else "100644"


def blob_oid(root, payload, oid_length):
    raw = git(root, "hash-object", "--stdin", input_data=payload).strip()
    try:
        oid = raw.decode("ascii")
        validate_object_id(oid, "expected_git_entries.object_id")
    except (UnicodeError, ValueError) as exc:
        raise GitExpectedEntriesError("GIT_EXPECTED_OBJECT_ID_INVALID") from exc
    if len(oid) != oid_length:
        raise GitExpectedEntriesError("GIT_EXPECTED_OBJECT_FORMAT_MISMATCH")
    return oid
