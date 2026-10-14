"""Owner-authenticated CLI adapters for Task06 complete/fail requests."""

import os
import stat
from contextlib import closing
from pathlib import Path

from .atomic import _open_directory, contained
from .completion_service import CompletionServiceError, complete_run, fail_run
from .locks import maintenance_lock, repository_paths
from .newcli_claim import _database
from .store import connect

_MAX_RESULT_BYTES = 1024 * 1024


class CompletionCliError(ValueError):
    """A Task06 CLI request cannot be safely served."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _read_result(repo_root: Path, result_path: Path) -> bytes:
    if not isinstance(result_path, Path) or result_path.is_absolute():
        raise CompletionCliError("COMPLETION_RESULT_FILE_INVALID")
    parent_fd = file_fd = -1
    try:
        source = contained(repo_root, result_path.as_posix())
        parent_fd = _open_directory(source.parent)
        file_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                          dir_fd=parent_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise CompletionCliError("COMPLETION_RESULT_FILE_INVALID")
        if info.st_size > _MAX_RESULT_BYTES:
            raise CompletionCliError("COMPLETION_RESULT_FILE_TOO_LARGE")
        chunks = []
        size = 0
        while size <= _MAX_RESULT_BYTES:
            chunk = os.read(file_fd, min(65536, _MAX_RESULT_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > _MAX_RESULT_BYTES:
            raise CompletionCliError("COMPLETION_RESULT_FILE_TOO_LARGE")
        return b"".join(chunks)
    except CompletionCliError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise CompletionCliError("COMPLETION_RESULT_FILE_INVALID") from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _finish_from_cli(repo_root: Path, run_id: str, executor: str, owner_pid: int,
                     result_path: Path, service) -> dict:
    supplied = Path(repo_root).resolve(strict=True)
    main, _ = repository_paths(supplied)
    with maintenance_lock(main), closing(connect(_database(main))) as conn:
        try:
            # The service authenticates/replays a matching durable journal before parsing input.
            return service(conn, supplied, run_id, executor, owner_pid, None)
        except CompletionServiceError as exc:
            if exc.code != "COMPLETION_RESULT_INVALID":
                raise
        raw_result = _read_result(supplied, result_path)
        return service(conn, supplied, run_id, executor, owner_pid, raw_result)


def complete_from_cli(repo_root: Path, run_id: str, executor: str, owner_pid: int,
                      result_path: Path) -> dict:
    """Complete one run, skipping draft reads when its journal already exists."""
    return _finish_from_cli(repo_root, run_id, executor, owner_pid, result_path, complete_run)


def fail_from_cli(repo_root: Path, run_id: str, executor: str, owner_pid: int,
                  result_path: Path) -> dict:
    """Fail one run, skipping draft reads when its journal already exists."""
    return _finish_from_cli(repo_root, run_id, executor, owner_pid, result_path, fail_run)
