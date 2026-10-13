import hashlib
import os
import signal
import stat
import subprocess
import threading
import time
from collections import namedtuple
from contextlib import suppress
from pathlib import Path
from typing import Sequence

from .atomic import _open_directory

_LIMIT = 1024 * 1024
_CHUNK = 64 * 1024


class ValidationProcessError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


StreamRecord = namedtuple("StreamRecord", "sha256 truncated write_failed")
ProcessRecord = namedtuple("ProcessRecord", "status exit_code duration_ms summary stdout stderr")


def _new_log(path: Path) -> int:
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise ValidationProcessError("VALIDATION_LOG_PATH_INVALID")
    try:
        parent = _open_directory(path.parent)
    except OSError as exc:
        raise ValidationProcessError("VALIDATION_LOG_UNSAFE") from exc
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            mode = os.fstat(fd)
            if (not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.geteuid() or
                    mode.st_mode & 0o077):
                raise ValidationProcessError("VALIDATION_LOG_UNSAFE")
            os.fsync(parent)
        except BaseException:
            os.close(fd)
            raise
        return fd
    except OSError as exc:
        raise ValidationProcessError("VALIDATION_LOG_UNSAFE") from exc
    finally:
        os.close(parent)


def _drain(stream, fd: int, records: list) -> None:
    digest, kept, total, failed = hashlib.sha256(), 0, 0, False
    try:
        while chunk := stream.read(_CHUNK):
            total += len(chunk)
            digest.update(chunk)
            prefix = chunk[:max(0, _LIMIT - kept)]
            view = memoryview(prefix)
            while view:
                try:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
                except OSError:
                    failed = True
                    break
            kept += len(prefix)
    except Exception:
        failed = True
    finally:
        try:
            os.fsync(fd)
        except Exception:
            failed = True
        with suppress(OSError, ValueError):
            stream.close()
        try:
            os.close(fd)
        except OSError:
            failed = True
    records.append(StreamRecord(digest.hexdigest(), total > _LIMIT, failed))


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        with suppress(OSError):
            process.kill()
        raise ValidationProcessError("VALIDATION_PROCESS_CLEANUP_FAILED") from exc


def run_one_validation(argv: Sequence[str], cwd: Path, stdout_path: Path, stderr_path: Path,
                       timeout_seconds: int) -> ProcessRecord:
    """Execute one argv, drain both streams concurrently, and kill/reap its process group."""
    if (os.name != "posix" or type(timeout_seconds) is not int or
            not 1 <= timeout_seconds <= 3600 or not isinstance(argv, Sequence) or
            isinstance(argv, (str, bytes, bytearray)) or not argv or
            any(type(item) is not str or not item or "\x00" in item for item in argv)):
        raise ValidationProcessError("VALIDATION_PROCESS_INPUT_INVALID")
    cwd = Path(cwd)
    if not cwd.is_absolute():
        raise ValidationProcessError("VALIDATION_CWD_INVALID")
    directory = _open_directory(cwd)
    os.close(directory)
    stdout_fd = _new_log(Path(stdout_path))
    try:
        stderr_fd = _new_log(Path(stderr_path))
    except BaseException:
        os.close(stdout_fd)
        raise
    started = time.monotonic()
    empty = hashlib.sha256(b"").hexdigest()
    try:
        process = subprocess.Popen(list(argv), cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                   close_fds=True, start_new_session=True)
    except OSError:
        os.close(stdout_fd)
        os.close(stderr_fd)
        duration = int((time.monotonic() - started) * 1000)
        blank = StreamRecord(empty, False, False)
        return ProcessRecord("skipped", None, duration, "validation could not start", blank, blank)
    stdout_records, stderr_records = [], []
    readers = [threading.Thread(target=_drain, args=(process.stdout, stdout_fd, stdout_records)),
               threading.Thread(target=_drain, args=(process.stderr, stderr_fd, stderr_records))]
    streams = (process.stdout, process.stderr)
    descriptors = (stdout_fd, stderr_fd)
    try:
        for reader in readers:
            reader.start()
    except Exception as exc:
        with suppress(ValidationProcessError):
            _kill_group(process)
        with suppress(Exception):
            process.wait()
        for index, reader in enumerate(readers):
            stream, fd = streams[index], descriptors[index]
            if reader.ident is not None:
                reader.join()
            else:
                with suppress(OSError, ValueError):
                    stream.close()
                with suppress(OSError):
                    os.close(fd)
        raise ValidationProcessError("VALIDATION_STREAM_START_FAILED") from exc
    timed_out = False
    try:
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(process)
            exit_code = process.wait()
        _kill_group(process)
    finally:
        if process.poll() is None:
            _kill_group(process)
            process.wait()
        for reader in readers:
            reader.join()
    duration = int((time.monotonic() - started) * 1000)
    if len(stdout_records) != 1 or len(stderr_records) != 1:
        raise ValidationProcessError("VALIDATION_STREAM_CAPTURE_FAILED")
    stdout, stderr = stdout_records[0], stderr_records[0]
    if stdout.write_failed or stderr.write_failed:
        raise ValidationProcessError("VALIDATION_LOG_WRITE_FAILED")
    summary = ("validation timed out" if timed_out else
               "validation passed" if exit_code == 0 else "validation failed")
    return ProcessRecord("executed", exit_code, duration, summary, stdout, stderr)
