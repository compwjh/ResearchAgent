"""Single-paper import saga for security-paper discovery.

The orchestration boundary accepts a server-side candidate snapshot and hands
only a trusted local PDF path to the injected knowledge-base port. Download
security and stable paper-discovery errors remain in this context; metadata,
file moves, indexing, and compensation belong to the KB adapter.
"""

from __future__ import annotations

import hashlib
import inspect
import shutil
import stat
import tempfile
from contextlib import nullcontext
from dataclasses import asdict, dataclass, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
    BrowserManagerError,
)
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
    ImportResourceCapability,
    PaperImportPort,
    PaperImportRequest,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

PAPER_ALREADY_EXISTS = "PAPER_ALREADY_EXISTS"
KB_IMPORT_FAILED = "KB_IMPORT_FAILED"
# 源文件已安全落盘、元数据已写入，但向量索引阶段失败。与 KB_IMPORT_FAILED 区分：
# 前者可原地重建索引，后者意味着根本没入库。此前两者共用 KB_IMPORT_FAILED，
# 导致"下载到垃圾""embedding 超时""generation 漂移"在 API 与批次记录里无法区分。
KB_INDEX_FAILED = "KB_INDEX_FAILED"
KB_STORAGE_LOCKED = "KB_STORAGE_LOCKED"
DUPLICATE_IMPORT = "DUPLICATE_IMPORT"

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
    BROWSER_SESSION_EXPIRED: "受控登录会话已过期，请重新登录",
    BROWSER_SESSION_REQUIRED: "请先完成受控登录后再续传",
    KB_IMPORT_FAILED: "论文导入失败",
    KB_INDEX_FAILED: "论文已保存，但向量索引失败，请稍后重建索引",
    # 存储被另一个实例独占：可重试、可行动（spec-021 Task03）。
    KB_STORAGE_LOCKED: "知识库存储被另一个实例占用，请关闭其他服务实例后重试",
    # 同论文再次新建导入批次撞 import_item_title 唯一索引：指引回原批次重试。
    DUPLICATE_IMPORT: "该论文已在导入批次中，请在原批次重试",
}


def safe_import_error_message(code: object, fallback: object = None) -> str:
    """Return the fixed human-readable message for an import error code."""
    return _SAFE_IMPORT_ERROR_MESSAGES.get(str(code or ""), "论文导入失败")


def safe_import_error_code(code: object, fallback: str = KB_IMPORT_FAILED) -> str:
    """Keep persisted/API error codes within the documented stable set."""
    value = str(code or "")
    return value if value in _SAFE_IMPORT_ERROR_MESSAGES else fallback


def _is_storage_locked_error(error: BaseException) -> bool:
    """Narrow-match a Qdrant storage-in-use RuntimeError (spec-021 Task03).

    The fixed error code is the only durable detail; we never forward the raw
    exception text (it may contain a filesystem path) into state or a response.
    """
    return isinstance(error, RuntimeError) and "already accessed by another instance" in str(error)


class PaperImportError(RuntimeError):
    """Stable error at the import orchestration boundary."""

    def __init__(self, code: str, message: str = "论文导入失败", *, retryable: bool = False,
                 cleanup_status: str | None = None,
                 resource_capability: ImportResourceCapability | None = None) -> None:
        self.code = code
        self.error_code = code
        self.message = safe_import_error_message(code, message)
        self.retryable = retryable
        self.cleanup_status = cleanup_status
        self.resource_capability = resource_capability
        super().__init__(self.message)


@dataclass(frozen=True)
class PaperImportResult:
    paper_id: Optional[str]
    stored_name: Optional[str]
    status: str
    error_code: Optional[str] = None
    message: Optional[str] = None
    existing: bool = False
    source_sha256: Optional[str] = None
    cleanup_status: Optional[str] = None
    resource_capability: Optional[ImportResourceCapability] = None

    @property
    def created_resource(self) -> Optional[ImportResourceCapability]:
        return self.resource_capability

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "stored_name": self.stored_name,
            "status": self.status,
            "error_code": self.error_code,
            "message": self.message,
            "existing": self.existing,
            "cleanup_status": self.cleanup_status,
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


def _import_lifecycle_boundary(downloader: Callable[..., Any], context: Any = None):
    """Return the optional browser-session guard for the KB write boundary.

    Authenticated downloads use ``BrowserSession.download_pdf`` as a bound
    method.  Keeping this discovery-side protocol narrow lets public
    downloaders remain unchanged while allowing the browser session to make
    its final TTL check atomic with entry into ``PaperImportPort``.
    """
    owner = getattr(downloader, "__self__", None)
    guard = getattr(owner, "import_boundary", None)
    if not callable(guard):
        guard = getattr(context, "import_boundary", None)
    return guard() if callable(guard) else nullcontext()


def _cleanup_download(
    download: Any,
    *,
    attempt_root: Optional[Path] = None,
    preexisting_paths: Iterable[Path] = (),
    file_token: tuple[int, int] | None = None,
) -> str:
    """Record a downloaded path as pending; never unlink a single pathname.

    A downloader path is untrusted even after the downloader returns.  No
    pathname can provide compare-and-unlink ownership semantics: a directory
    entry may be replaced after any fd/stat probe and before ``unlink``.  The
    caller-owned ``temp_dir`` contract therefore retains every file.  For an
    import-created private root, the owning orchestration layer removes the
    whole root with ``_cleanup_attempt_root`` instead.
    """
    path_value = getattr(download, "file_path", None)
    if path_value is None and isinstance(download, Mapping):
        path_value = download.get("file_path") or download.get("path")
    if not path_value:
        return "completed"
    # Keep the parameters for compatibility with existing callers and to make
    # the ownership evidence available to a future maintenance workflow.  It
    # is deliberately not used to authorize a single-file pathname deletion.
    del attempt_root, preexisting_paths, file_token
    return "cleanup_pending"


def _cleanup_attempt_root(
    root: Optional[Path],
    *,
    expected_token: tuple[int, int] | None = None,
) -> None:
    """Remove an import-owned root without following symlinks.

    This function is called only when ``import_candidate`` created the root
    with ``tempfile.mkdtemp``.  ``shutil.rmtree`` uses descriptor-relative
    removal on platforms that advertise symlink-attack resistance; refusing
    to run otherwise keeps a replaced root fail-closed.
    """
    if root is None:
        return
    try:
        root_path = Path(root)
        if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
            return
        root_stat = root_path.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or root_path.is_symlink():
            return
        if expected_token is not None and (root_stat.st_dev, root_stat.st_ino) != expected_token:
            return
    except OSError:
        return
    try:
        shutil.rmtree(root_path)
    except OSError:
        return


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
        source_sha256=_port_value(result, "source_sha256"),
        cleanup_status=_port_value(result, "cleanup_status"),
        resource_capability=_port_value(result, "resource_capability"),
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
        if _is_storage_locked_error(error):
            # 存储被另一个实例独占：可重试、可行动（spec-021 Task03）。
            raise PaperImportError(
                KB_STORAGE_LOCKED, "知识库存储被另一个实例占用，请关闭其他服务实例后重试", retryable=True
            ) from error
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
    attempt_owner: Optional[str] = None,
    attempt_token: Optional[str] = None,
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

    cleanup_root: Optional[Path] = None
    attempt_root_owned = False
    attempt_root_token: tuple[int, int] | None = None
    preexisting_paths: tuple[Path, ...] = ()
    download: Any = None
    file_token: tuple[int, int] | None = None
    try:
        if temp_dir is None:
            # The downloader creates its own private child below this root.
            # Keeping a root per import attempt lets finally clean only
            # resources created by this call, while preserving the configured
            # article-download directory supplied by the caller/settings.
            download_base = Path(getattr(settings, "article_download_dir", tempfile.gettempdir())).resolve()
            download_base.mkdir(parents=True, exist_ok=True)
            cleanup_root = Path(tempfile.mkdtemp(prefix="paper-import-", dir=download_base)).resolve()
            try:
                root_stat = cleanup_root.lstat()
                if stat.S_ISDIR(root_stat.st_mode) and not cleanup_root.is_symlink():
                    attempt_root_token = (root_stat.st_dev, root_stat.st_ino)
                    attempt_root_owned = True
            except OSError:
                # If ownership cannot be recorded, retain the root rather
                # than risk removing a replacement at the same pathname.
                attempt_root_owned = False
        else:
            # An explicit temp_dir is caller-owned and is never removed.  Its
            # complete pre-attempt inventory protects nested pre-existing
            # files/directories, not just direct children.
            cleanup_root = Path(temp_dir).resolve()
            cleanup_root.mkdir(parents=True, exist_ok=True)
            preexisting_paths = tuple(cleanup_root.rglob("*"))

        download = _download(
            downloader,
            candidate,
            settings,
            allowed_hosts,
            transport=transport,
            client=client,
            dns_resolver=dns_resolver,
            peer_ip_resolver=peer_ip_resolver,
            temp_dir=cleanup_root,
            context=context,
        )
        # Capture ownership immediately after the downloader returns.  A
        # token collected in finally would describe a replacement installed
        # by an untrusted downloader path, and could authorize deleting that
        # replacement later.
        try:
            downloaded_path = _download_path(download)
            resolved_path = downloaded_path.resolve()
            if cleanup_root is not None and cleanup_root in resolved_path.parents:
                stat_result = downloaded_path.lstat()
                if not downloaded_path.is_symlink():
                    file_token = (stat_result.st_dev, stat_result.st_ino)
        except (OSError, PaperImportError):
            pass
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
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        request = PaperImportRequest(snapshot, source, source_sha256=source_digest)
        if attempt_owner is not None or attempt_token is not None:
            request = replace(
                request,
                attempt_owner=attempt_owner or request.attempt_owner,
                attempt_token=attempt_token or request.attempt_token,
            )
        with _import_lifecycle_boundary(downloader, context):
            result = port.import_paper(request)
        translated = _application_result(result)
        if translated.error_code and translated.error_code != PAPER_ALREADY_EXISTS:
            raise PaperImportError(
                translated.error_code,
                translated.message or "论文导入失败",
                retryable=True,
                cleanup_status=translated.cleanup_status,
                resource_capability=translated.resource_capability,
            )
        return translated
    except PaperDownloadError:
        raise
    except PaperImportError:
        raise
    except BrowserManagerError as error:
        if error.code in {BROWSER_SESSION_EXPIRED, BROWSER_SESSION_REQUIRED}:
            raise PaperImportError(error.code, retryable=error.retryable) from error
        raise PaperImportError(KB_IMPORT_FAILED, "知识库 v1 索引失败", retryable=True) from error
    except Exception as error:
        if _is_storage_locked_error(error):
            # 存储被另一个实例独占：可重试、可行动（spec-021 Task03）。
            raise PaperImportError(
                KB_STORAGE_LOCKED, "知识库存储被另一个实例占用，请关闭其他服务实例后重试", retryable=True
            ) from error
        raise PaperImportError(KB_IMPORT_FAILED, "知识库 v1 索引失败", retryable=True) from error
    finally:
        # The adapter moves the file into the KB on success and removes its own
        # artifacts on failure; this only removes the downloader's private
        # temporary file/directory when it still exists.
        _cleanup_download(
            download,
            attempt_root=cleanup_root,
            preexisting_paths=preexisting_paths,
            file_token=file_token,
        )
        if attempt_root_owned:
            _cleanup_attempt_root(cleanup_root, expected_token=attempt_root_token)


__all__ = [
    "DOWNLOAD_BLOCKED", "DOWNLOAD_TIMEOUT", "INVALID_PDF", "LOGIN_REQUIRED", "PDF_NOT_FOUND",
    "PDF_TOO_LARGE", "BROWSER_SESSION_EXPIRED", "BROWSER_SESSION_REQUIRED",
    "KB_IMPORT_FAILED", "KB_INDEX_FAILED", "PAPER_ALREADY_EXISTS", "KB_STORAGE_LOCKED",
    "DUPLICATE_IMPORT",
    "PaperImportError",
    "safe_import_error_message", "safe_import_error_code", "PaperImportResult", "import_candidate",
]
