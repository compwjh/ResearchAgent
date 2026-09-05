"""Single-paper import saga for security-paper discovery.

The orchestration boundary deliberately accepts a server-side candidate
snapshot.  It does not accept a URL, title, or conference name as separate
client-controlled inputs: the only conference value used for the readable
filename is the explicitly supplied server configuration value.
"""

from __future__ import annotations

import inspect
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from backend.app.core.article_settings import ArticleSettings
from backend.app.core.config import KB_PAPERS_DIR
from backend.app.services.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    DownloadResult,
    PaperDownloadError,
    download_candidate,
)
from backend.app.services.paper_import_identity import (
    PaperImportIdentity,
    _identities_match,
    build_paper_identity,
    filename_for_candidate,
)
from backend.app.services.kb.index import delete_paper_chunker, index_paper_chunker
from backend.app.services.kb.store import (
    CHUNKER_V1,
    STATUS_INDEXED,
    STATUS_INDEXING,
    PaperRecord,
    get_paper,
    load_papers,
    new_record,
    remove_paper,
    upsert_paper,
)
from backend.app.services.kb.tasks import run_index_task_sync


PAPER_ALREADY_EXISTS = "PAPER_ALREADY_EXISTS"
KB_IMPORT_FAILED = "KB_IMPORT_FAILED"

# Import errors cross both the single-item API and the durable batch store.
# Keep this table keyed by stable error codes so an exception's text can never
# become durable state or an API response (exception text may contain URLs or
# credentials supplied by a transport/library).
_SAFE_IMPORT_ERROR_MESSAGES = {
    PAPER_ALREADY_EXISTS: "论文已在知识库中",
    DOWNLOAD_BLOCKED: "下载地址被安全策略拒绝",
    DOWNLOAD_TIMEOUT: "下载超时，请稍后重试",
    INVALID_PDF: "下载内容不是有效 PDF",
    LOGIN_REQUIRED: "下载来源需要登录",
    PDF_NOT_FOUND: "PDF 不存在",
    PDF_TOO_LARGE: "PDF 超过大小限制",
    KB_IMPORT_FAILED: "论文导入失败",
}


def safe_import_error_message(code: object, fallback: object = None) -> str:
    """Return the fixed human-readable message for an import error code."""
    return _SAFE_IMPORT_ERROR_MESSAGES.get(str(code or ""), "论文导入失败")


def safe_import_error_code(code: object, fallback: str = KB_IMPORT_FAILED) -> str:
    """Keep persisted/API error codes within the documented stable set."""
    value = str(code or "")
    return value if value in _SAFE_IMPORT_ERROR_MESSAGES else fallback

# This lock only covers the short local commit section.  Download and index
# work are intentionally outside it, so neither network nor Qdrant calls run
# while competing import callers hold the local metadata lock.
_IMPORT_LOCK = threading.RLock()


class PaperImportError(RuntimeError):
    """Stable error at the import orchestration boundary."""

    def __init__(self, code: str, message: str = "论文导入失败", *, retryable: bool = False) -> None:
        self.code = code
        self.error_code = code
        self.message = safe_import_error_message(code, message)
        self.retryable = retryable
        super().__init__(self.message)


@dataclass(frozen=True)
class PaperImportResult:
    paper_id: Optional[str]
    stored_name: Optional[str]
    status: str
    error_code: Optional[str] = None
    message: Optional[str] = None
    existing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "stored_name": self.stored_name,
            "status": self.status,
            "error_code": self.error_code,
            "message": self.message,
            "existing": self.existing,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def _value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _record_identity(record: Mapping[str, Any]) -> PaperImportIdentity:
    return build_paper_identity(
        doi=record.get("doi"),
        dblp_key=record.get("dblp_key"),
        title=record.get("title"),
        year=record.get("year"),
        conference_id=record.get("conference_id"),
    )


def _candidate_identity(candidate: Any) -> PaperImportIdentity:
    return build_paper_identity(
        doi=_value(candidate, "doi"),
        dblp_key=_value(candidate, "dblp_key") or _value(candidate, "dblp"),
        title=_value(candidate, "title"),
        year=_value(candidate, "year"),
        conference_id=_value(candidate, "conference_id") or _value(candidate, "conference"),
    )


def _find_existing(candidate: Any, meta_path: Optional[Path]) -> Optional[dict[str, Any]]:
    wanted = _candidate_identity(candidate)
    if not wanted.keys:
        return None
    for record in load_papers(meta_path):
        if not isinstance(record, dict):
            continue
        if _identities_match(wanted, _record_identity(record)):
            return record
    return None


def _call_with_supported_kwargs(function: Callable[..., Any], positional: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Call injected seams while keeping tiny test doubles convenient."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return function(*positional, **kwargs)
    parameters = signature.parameters.values()
    accepts_kwargs = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters)
    accepted = kwargs if accepts_kwargs else {key: value for key, value in kwargs.items() if key in signature.parameters}
    positional_parameters = [
        item for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    args = positional[: len(positional_parameters)]
    return function(*args, **accepted)


def _download(
    downloader: Callable[..., DownloadResult],
    candidate: Any,
    settings: ArticleSettings,
    allowed_hosts: Iterable[str],
    *,
    transport: Any = None,
    client: Any = None,
    dns_resolver: Any = None,
    peer_ip_resolver: Any = None,
    temp_dir: Optional[Path] = None,
    context: Any = None,
) -> DownloadResult:
    return _call_with_supported_kwargs(
        downloader,
        (candidate, settings, allowed_hosts),
        {
            "transport": transport,
            "client": client,
            "dns_resolver": dns_resolver,
            "peer_ip_resolver": peer_ip_resolver,
            "temp_dir": temp_dir,
            "context": context,
        },
    )


def _cleanup_download(download: Any) -> None:
    path_value = getattr(download, "file_path", None)
    if path_value is None and isinstance(download, Mapping):
        path_value = download.get("file_path") or download.get("path")
    if not path_value:
        return
    path = Path(str(path_value))
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    # Never recursively remove an injected caller directory.  The secure
    # downloader uses a private directory, and an empty rmdir is sufficient.
    try:
        path.parent.rmdir()
    except OSError:
        pass


def _cleanup_import_artifacts(
    download: Any,
    target: Optional[Path],
    paper_id: Optional[str],
    meta_path: Optional[Path],
    papers_dir: Path,
) -> None:
    """Compensate only artifacts created by this import invocation."""
    if paper_id:
        try:
            remove_paper(paper_id, meta_path, papers_dir)
        except Exception:
            # The physical target is still removed below; a failed metadata
            # cleanup must not leave a readable orphan PDF behind.
            pass
    if target is not None:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    _cleanup_download(download)


def _download_path(download: Any) -> Path:
    value = getattr(download, "file_path", None)
    if value is None and isinstance(download, Mapping):
        value = download.get("file_path") or download.get("path")
    if not value:
        raise PaperImportError(KB_IMPORT_FAILED, "下载器未返回临时文件")
    path = Path(str(value))
    if not path.is_file():
        raise PaperImportError(KB_IMPORT_FAILED, "下载临时文件不存在")
    return path


def _existing_names(papers_dir: Path, meta_path: Optional[Path]) -> set[str]:
    names = {
        str(item.get("stored_name"))
        for item in load_papers(meta_path)
        if isinstance(item, dict) and item.get("stored_name")
    }
    try:
        names.update(item.name for item in papers_dir.iterdir() if item.is_file())
    except OSError:
        pass
    return names


def _index_succeeded(result: Any) -> bool:
    if result is True:
        return True
    status: Any = getattr(result, "status", None)
    if status is None and isinstance(result, Mapping):
        status = result.get("status")
        if status is None and isinstance(result.get("paper"), Mapping):
            status = result["paper"].get("status")
        if result.get("error") and status is None:
            return False
    return status == STATUS_INDEXED


def _default_indexer(record: PaperRecord, path: Path, *, meta_path: Optional[Path], client: Any = None) -> Any:
    return run_index_task_sync(
        record.paper_id,
        CHUNKER_V1,
        lambda progress: index_paper_chunker(
            record, path, CHUNKER_V1, progress=progress, client=client, meta_path=meta_path
        ),
    )


def _default_deleter(paper_id: str, *, client: Any = None) -> None:
    """Idempotently remove the v1 points written by this import."""
    delete_paper_chunker(paper_id, CHUNKER_V1, client=client)


def import_candidate(
    candidate: Any,
    settings: Optional[ArticleSettings] = None,
    allowed_hosts: Iterable[str] = (),
    *,
    conference_short_name: Optional[str] = None,
    downloader: Callable[..., DownloadResult] = download_candidate,
    indexer: Optional[Callable[..., Any]] = None,
    deleter: Optional[Callable[..., Any]] = None,
    papers_dir: Optional[Path] = None,
    meta_path: Optional[Path] = None,
    temp_dir: Optional[Path] = None,
    transport: Any = None,
    client: Any = None,
    dns_resolver: Any = None,
    peer_ip_resolver: Any = None,
    context: Any = None,
    max_filename_length: int = 180,
) -> PaperImportResult:
    """Download, persist metadata/file, and synchronously build the v1 index.

    Duplicate checks happen once before download and again in the short local
    commit section.  Any failure after the file move removes only the record
    and file created by this invocation; pre-existing records are untouched.
    """
    settings = settings or ArticleSettings()
    root = Path(papers_dir or KB_PAPERS_DIR).resolve()
    metadata = Path(meta_path).resolve() if meta_path else None
    root.mkdir(parents=True, exist_ok=True)

    with _IMPORT_LOCK:
        existing = _find_existing(candidate, metadata)
    if existing:
        return PaperImportResult(
            existing.get("paper_id"), existing.get("stored_name") or existing.get("file_name"),
            str(existing.get("status") or "indexed"), PAPER_ALREADY_EXISTS, "论文已在知识库中", True,
        )

    try:
        download = _download(
            downloader, candidate, settings, allowed_hosts,
            transport=transport, client=client, dns_resolver=dns_resolver,
            peer_ip_resolver=peer_ip_resolver, temp_dir=Path(temp_dir).resolve() if temp_dir else None,
            context=context,
        )
    except PaperDownloadError:
        raise
    except Exception as error:
        raise PaperImportError(KB_IMPORT_FAILED, "下载器执行失败", retryable=True) from error

    target: Optional[Path] = None
    record: Optional[PaperRecord] = None
    try:
        source = _download_path(download)
        # The server-side conference short name is the only naming input.
        # Falling back to the sanitized conference id keeps direct service use
        # possible while never trusting display conference_name.
        conference = conference_short_name or _value(candidate, "conference_id") or "Conference"
        with _IMPORT_LOCK:
            existing = _find_existing(candidate, metadata)
            if existing:
                _cleanup_download(download)
                return PaperImportResult(
                    existing.get("paper_id"), existing.get("stored_name") or existing.get("file_name"),
                    str(existing.get("status") or "indexed"), PAPER_ALREADY_EXISTS, "论文已在知识库中", True,
                )
            stored_name = filename_for_candidate(
                candidate, conference,
                existing_names=_existing_names(root, metadata), max_length=max_filename_length,
            )
            target = root / stored_name
            # filename_for_candidate returns a basename, but retain this
            # assertion as a defense-in-depth boundary for injected helpers.
            if target.parent != root or target.name != stored_name:
                raise PaperImportError(KB_IMPORT_FAILED, "生成的文件名不安全")
            os.rename(source, target)
            record = new_record(
                stored_name,
                title=_value(candidate, "title"),
                authors=list(_value(candidate, "authors", []) or []),
                year=_value(candidate, "year"),
                conference_id=_value(candidate, "conference_id"),
                # The candidate is a server-side snapshot.  The explicit
                # conference argument above remains the sole naming input;
                # this display value is retained as optional metadata.
                conference_name=_value(candidate, "conference_name"),
                doi=_candidate_identity(candidate).doi or None,
                dblp_key=_candidate_identity(candidate).dblp_key or None,
                source_url=_value(candidate, "article_url"),
                import_source="paper-discovery",
                stored_name=stored_name,
            )
            record.status = STATUS_INDEXING
            upsert_paper(record, metadata)
    except PaperImportError:
        _cleanup_import_artifacts(download, target, record.paper_id if record else None, metadata, root)
        raise
    except OSError as error:
        _cleanup_import_artifacts(download, target, record.paper_id if record else None, metadata, root)
        raise PaperImportError(KB_IMPORT_FAILED, "知识库文件保存失败", retryable=True) from error
    except Exception as error:
        _cleanup_import_artifacts(download, target, record.paper_id if record else None, metadata, root)
        raise PaperImportError(KB_IMPORT_FAILED, "知识库元数据写入失败", retryable=True) from error

    try:
        index_result = _call_with_supported_kwargs(
            indexer or _default_indexer,
            (record, target),
            {"meta_path": metadata, "client": client},
        )
        if not _index_succeeded(index_result):
            raise PaperImportError(KB_IMPORT_FAILED, "知识库 v1 索引失败", retryable=True)
        # The existing v1 entry point persists per-chunker progress itself and
        # returns the refreshed JSON record.  Carry that state forward instead
        # of overwriting it with PaperRecord's initial ``indexing`` defaults.
        if isinstance(index_result, Mapping):
            if isinstance(index_result.get("chunkers"), dict):
                record.chunkers = index_result["chunkers"]
            for field in ("page_count", "chunk_count", "error"):
                if field in index_result:
                    setattr(record, field, index_result[field])
        record.status = STATUS_INDEXED
        record.error = None
        upsert_paper(record, metadata)
        return PaperImportResult(record.paper_id, stored_name, STATUS_INDEXED)
    except PaperImportError:
        try:
            _call_with_supported_kwargs(
                deleter or _default_deleter,
                (record.paper_id, CHUNKER_V1),
                {"client": client},
            )
        except Exception:
            pass
        _cleanup_import_artifacts(download, target, record.paper_id, metadata, root)
        raise
    except Exception as error:
        try:
            _call_with_supported_kwargs(
                deleter or _default_deleter,
                (record.paper_id, CHUNKER_V1),
                {"client": client},
            )
        except Exception:
            pass
        _cleanup_import_artifacts(download, target, record.paper_id, metadata, root)
        raise PaperImportError(KB_IMPORT_FAILED, "知识库 v1 索引失败", retryable=True) from error


__all__ = [
    "DOWNLOAD_BLOCKED", "DOWNLOAD_TIMEOUT", "INVALID_PDF", "LOGIN_REQUIRED", "PDF_NOT_FOUND",
    "PDF_TOO_LARGE", "KB_IMPORT_FAILED", "PAPER_ALREADY_EXISTS", "PaperImportError",
    "safe_import_error_message",
    "safe_import_error_code",
    "PaperImportResult", "import_candidate",
]
