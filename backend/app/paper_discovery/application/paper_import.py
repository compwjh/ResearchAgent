"""Single-paper import saga for security-paper discovery.

The orchestration boundary accepts a server-side candidate snapshot and hands
only a trusted local PDF path to the injected knowledge-base port. Download
security and stable paper-discovery errors remain in this context; metadata,
file moves, indexing, and compensation belong to the KB adapter.
"""

from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from backend.app.paper_discovery.domain.paper_import_identity import (
    PaperImportIdentity,
    build_paper_identity,
    filename_for_candidate,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
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
from backend.app.platform.bootstrap import get_provider
from backend.app.platform.ports import (
    ImportIndexStatus,
    PaperImportPort,
    PaperImportRequest,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

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


def _candidate_identity(candidate: Any) -> PaperImportIdentity:
    return build_paper_identity(
        doi=_value(candidate, "doi"),
        dblp_key=_value(candidate, "dblp_key") or _value(candidate, "dblp"),
        title=_value(candidate, "title"),
        year=_value(candidate, "year"),
        conference_id=_value(candidate, "conference_id") or _value(candidate, "conference"),
    )


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
        item
        for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return function(*positional[: len(positional_parameters)], **accepted)


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
    # Never recursively remove an injected caller directory. The secure
    # downloader uses a private directory, and an empty rmdir is sufficient.
    try:
        path.parent.rmdir()
    except OSError:
        pass


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


def _candidate_snapshot(candidate: Any) -> dict[str, Any]:
    """Make the server-owned candidate snapshot passed across the port."""
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if hasattr(candidate, "model_dump"):
        return dict(candidate.model_dump())
    if is_dataclass(candidate):
        return asdict(candidate)
    values = getattr(candidate, "__dict__", None)
    if isinstance(values, dict):
        return dict(values)
    names = (
        "candidate_id", "search_id", "title", "authors", "year", "conference_id",
        "conference_name", "doi", "dblp_key", "article_url", "pdf_url",
    )
    return {name: _value(candidate, name) for name in names if _value(candidate, name) is not None}


def _port_value(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, Mapping):
        return result.get(name, default)
    return getattr(result, name, default)


def _port_status(result: Any) -> str:
    value = _port_value(result, "index_status", None)
    if value is None:
        value = _port_value(result, "status", "failed")
    if isinstance(value, ImportIndexStatus):
        return value.value
    return str(getattr(value, "value", value) or "failed")


def _application_result(result: Any, *, existing: bool = False) -> PaperImportResult:
    """Translate the stable port DTO into the paper-discovery result DTO."""
    result_existing = bool(_port_value(result, "existing", existing))
    error_code = _port_value(result, "error_code")
    if result_existing:
        error_code = PAPER_ALREADY_EXISTS
    error_code = safe_import_error_code(error_code, KB_IMPORT_FAILED) if error_code else None
    return PaperImportResult(
        paper_id=_port_value(result, "paper_id"),
        stored_name=_port_value(result, "stored_name"),
        status=_port_status(result),
        error_code=error_code,
        message=safe_import_error_message(error_code) if error_code else None,
        existing=result_existing,
    )


def _resolve_port(
    paper_import_port: Optional[PaperImportPort],
    *,
    papers_dir: Optional[Path],
    meta_path: Optional[Path],
    indexer: Optional[Callable[..., Any]],
    deleter: Optional[Callable[..., Any]],
    client: Any,
) -> PaperImportPort:
    """Resolve the injected port without importing the KB context."""
    if paper_import_port is not None:
        return paper_import_port
    custom = any(value is not None for value in (papers_dir, meta_path, indexer, deleter, client))
    try:
        if custom:
            factory = get_provider("paper_import_port_factory")
            return _call_with_supported_kwargs(
                factory,
                (),
                {
                    "papers_dir": papers_dir,
                    "meta_path": meta_path,
                    "indexer": indexer,
                    "deleter": deleter,
                    "client": client,
                },
            )
        return get_provider("paper_import_port")
    except KeyError as error:
        raise PaperImportError(KB_IMPORT_FAILED, "论文导入适配器未配置", retryable=True) from error


def _find_existing(port: PaperImportPort, snapshot: Mapping[str, Any]) -> Any:
    """Keep adapter/storage failures behind the stable import error boundary."""
    try:
        return port.find_existing(snapshot)
    except PaperImportError:
        raise
    except Exception as error:
        raise PaperImportError(KB_IMPORT_FAILED, "知识库导入状态不可用", retryable=True) from error


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
    paper_import_port: Optional[PaperImportPort] = None,
) -> PaperImportResult:
    """Download a candidate and hand the trusted local file to the KB port.

    Duplicate checks happen once before download and again after download. All
    metadata, file moves, indexing, and compensation remain inside the
    injected port; paper discovery owns only secure download orchestration.
    """
    settings = settings or ArticleSettings()
    port = _resolve_port(
        paper_import_port,
        papers_dir=papers_dir,
        meta_path=meta_path,
        indexer=indexer,
        deleter=deleter,
        client=client,
    )
    snapshot = _candidate_snapshot(candidate)
    existing = _find_existing(port, snapshot)
    if existing:
        return _application_result(existing, existing=True)

    try:
        download = _download(
            downloader,
            candidate,
            settings,
            allowed_hosts,
            transport=transport,
            client=client,
            dns_resolver=dns_resolver,
            peer_ip_resolver=peer_ip_resolver,
            temp_dir=Path(temp_dir).resolve() if temp_dir else None,
            context=context,
        )
    except PaperDownloadError:
        raise
    except Exception as error:
        raise PaperImportError(KB_IMPORT_FAILED, "下载器执行失败", retryable=True) from error

    try:
        source = _download_path(download)
        # The server-side conference short name is the only naming input.
        # Falling back to the sanitized conference id keeps direct service use
        # possible while never trusting display conference_name.
        conference = conference_short_name or _value(candidate, "conference_id") or "Conference"
        existing = _find_existing(port, snapshot)
        if existing:
            return _application_result(existing, existing=True)
        stored_name = filename_for_candidate(
            candidate,
            conference,
            existing_names=port.existing_names(),
            max_length=max_filename_length,
        )
        snapshot["_stored_name"] = stored_name
        result = port.import_paper(PaperImportRequest(snapshot, source))
        translated = _application_result(result)
        if translated.error_code and translated.error_code != PAPER_ALREADY_EXISTS:
            raise PaperImportError(translated.error_code, translated.message or "论文导入失败", retryable=True)
        return translated
    except PaperImportError:
        raise
    except Exception as error:
        raise PaperImportError(KB_IMPORT_FAILED, "知识库 v1 索引失败", retryable=True) from error
    finally:
        # The adapter moves the file into the KB on success and removes its own
        # artifacts on failure; this only removes the downloader's private
        # temporary file/directory when it still exists.
        _cleanup_download(download)


__all__ = [
    "DOWNLOAD_BLOCKED", "DOWNLOAD_TIMEOUT", "INVALID_PDF", "LOGIN_REQUIRED", "PDF_NOT_FOUND",
    "PDF_TOO_LARGE", "KB_IMPORT_FAILED", "PAPER_ALREADY_EXISTS", "PaperImportError",
    "safe_import_error_message", "safe_import_error_code", "PaperImportResult", "import_candidate",
]
