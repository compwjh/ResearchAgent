"""Safe, side-effect-limited PDF download adapter for paper candidates."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urljoin

import httpx

from backend.app.paper_discovery.domain.paper_download_security import (
    DEFAULT_MAX_REDIRECTS,
    DNSResolver,
    URLSecurityError,
    ValidatedURL,
    validate_peer_ip,
    validate_redirect_target,
    validate_url,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

DOWNLOAD_BLOCKED = "DOWNLOAD_BLOCKED"
DOWNLOAD_TIMEOUT = "DOWNLOAD_TIMEOUT"
PDF_TOO_LARGE = "PDF_TOO_LARGE"
INVALID_PDF = "INVALID_PDF"
PDF_NOT_FOUND = "PDF_NOT_FOUND"
LOGIN_REQUIRED = "LOGIN_REQUIRED"
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_HEADERS = 64 * 1024


class PaperDownloadError(RuntimeError):
    """Stable, safe-to-display error from the download boundary."""

    def __init__(self, code: str, message: str = "论文 PDF 下载失败") -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class DownloadResult:
    file_path: str
    file_size: int
    checksum: str
    url: str
    page_count: int | None = None

    @property
    def path(self) -> str:
        return self.file_path


def _candidate_value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _setting(settings: ArticleSettings, name: str, default: Any) -> Any:
    value = getattr(settings, name, default)
    return default if value is None else value


def _header_size(response: httpx.Response) -> int:
    raw = getattr(response.headers, "raw", ())
    if raw:
        return sum(len(bytes(key)) + len(bytes(value)) + 4 for key, value in raw)
    return sum(len(str(key).encode()) + len(str(value).encode()) + 4 for key, value in response.headers.items())


def _peer_from_response(response: httpx.Response) -> str | None:
    extensions = getattr(response, "extensions", {}) or {}
    direct = extensions.get("peer_ip")
    if direct:
        return str(direct)
    stream = extensions.get("network_stream")
    if stream is not None and hasattr(stream, "get_extra_info"):
        # httpcore exposes the connected remote address as ``server_addr``.
        # ``peername`` is only populated by transports that mimic an
        # anyio/SSL socket, so a real httpcore stream answers ``peername``
        # with None and the peer check would reject every real download.
        for key in ("peername", "server_addr"):
            try:
                peer = stream.get_extra_info(key)
            except Exception:
                peer = None
            if isinstance(peer, tuple):
                return str(peer[0])
            if peer:
                return str(peer)
    peer = extensions.get("peername") or extensions.get("server_addr")
    return str(peer[0] if isinstance(peer, tuple) else peer) if peer else None


def _check_peer(
    response: httpx.Response,
    target: ValidatedURL,
    resolver: Callable[..., str | None] | None,
    transport: httpx.BaseTransport | None,
    supplied_client: bool,
) -> None:
    try:
        peer = resolver(response, target) if resolver else _peer_from_response(response)
    except TypeError:
        peer = resolver(target, response) if resolver else None
    # Mock transports do not expose a socket peer.  They are explicitly
    # injectable test seams; real clients must provide peer evidence.
    if peer is None:
        if transport is None and not supplied_client:
            raise PaperDownloadError(DOWNLOAD_BLOCKED, "无法复核实际连接地址")
        return
    try:
        validate_peer_ip(target, peer)
    except URLSecurityError as error:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "实际连接地址被拒绝") from error


def _validate_pages(path: Path) -> int:
    try:
        import fitz

        document = fitz.open(path)
        try:
            if document.is_encrypted:
                raise PaperDownloadError(INVALID_PDF, "PDF 无法读取")
            pages = document.page_count
        finally:
            document.close()
    except PaperDownloadError:
        raise
    except Exception as error:
        raise PaperDownloadError(INVALID_PDF, "PDF 无法读取") from error
    if pages < 1:
        raise PaperDownloadError(INVALID_PDF, "PDF 没有可读取页面")
    return pages


def _timeouts(settings: ArticleSettings) -> tuple[httpx.Timeout, float]:
    connect = float(_setting(settings, "paper_download_connect_timeout_seconds", 10.0))
    read = float(_setting(settings, "paper_download_read_timeout_seconds", 30.0))
    total = float(_setting(settings, "paper_download_total_timeout_seconds", 120.0))
    if min(connect, read, total) <= 0:
        raise PaperDownloadError(DOWNLOAD_TIMEOUT, "下载超时配置无效")
    return httpx.Timeout(total, connect=connect, read=read, write=read, pool=connect), total


class _CitationPdfParser(HTMLParser):
    """Extract a paper PDF URL from a landing page.

    Prefers ``<meta name="citation_pdf_url">``; falls back to the first
    ``<a href="...">`` whose href looks like a PDF link.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pdf_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.pdf_url is not None:
            return
        data = {key.casefold(): value for key, value in attrs if value is not None}
        if tag.casefold() == "meta":
            if data.get("name", "").casefold() == "citation_pdf_url":
                content = data.get("content")
                if content:
                    self.pdf_url = content
        elif tag.casefold() == "a":
            href = data.get("href", "")
            if ".pdf" in href.lower():
                self.pdf_url = href


def _resolve_pdf_url_from_page(
    page_url: str,
    *,
    allowed_hosts: Iterable[str],
    dns_resolver: DNSResolver | None = None,
    transport: httpx.BaseTransport | None = None,
    max_bytes: int = 256 * 1024,
) -> str:
    """Fetch a paper landing page and return its PDF URL via SSRF-safe checks.

    Only used when a candidate has no direct ``pdf_url`` but a ``source_page_url``
    (USENIX presentation page). The landing page host must already be in
    ``allowed_hosts`` (validated here), and the resolved PDF URL is re-validated
    against the same allowlist so no untrusted host is ever downloaded.
    """
    try:
        validate_url(page_url, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver)
    except URLSecurityError as error:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "下载来源被安全策略拒绝") from error
    client = httpx.Client(
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        trust_env=False,
        transport=transport,
    )
    try:
        with client.stream("GET", page_url) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise PaperDownloadError(PDF_NOT_FOUND, "无法从论文页解析 PDF 地址")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                if not isinstance(chunk, bytes):
                    chunk = bytes(chunk)
                total += len(chunk)
                if total > max_bytes:
                    break
                chunks.append(chunk)
            html = b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        client.close()
    parser = _CitationPdfParser()
    parser.feed(html)
    found = parser.pdf_url
    if not isinstance(found, str) or not found:
        raise PaperDownloadError(PDF_NOT_FOUND, "无法从论文页解析 PDF 地址")
    pdf_url = urljoin(page_url, found)
    try:
        validate_url(pdf_url, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver)
    except URLSecurityError as error:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "下载来源被安全策略拒绝") from error
    return pdf_url


def download_candidate(
    candidate: Any,
    settings: ArticleSettings,
    allowed_hosts: Iterable[str],
    *,
    transport: httpx.BaseTransport | None = None,
    client: httpx.Client | None = None,
    dns_resolver: Callable[[str], Iterable[object]] | None = None,
    peer_ip_resolver: Callable[..., str | None] | None = None,
    temp_dir: str | os.PathLike[str] | None = None,
    pdf_page_validator: Callable[[Path], int] | None = None,
    validate_pdf_pages: bool = True,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = MAX_PDF_BYTES,
    max_header_bytes: int = MAX_RESPONSE_HEADERS,
    clock: Callable[[], float] = time.monotonic,
) -> DownloadResult:
    """Download one server-side candidate, manually validating every hop."""
    url = _candidate_value(candidate, "pdf_url")
    if not isinstance(url, str) or not url:
        page_url = _candidate_value(candidate, "source_page_url") or _candidate_value(candidate, "official_page_url")
        if isinstance(page_url, str) and page_url:
            try:
                url = _resolve_pdf_url_from_page(
                    page_url, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver, transport=transport,
                )
            except PaperDownloadError as error:
                if error.code == DOWNLOAD_BLOCKED:
                    raise
                url = None
        if not isinstance(url, str) or not url:
            raise PaperDownloadError(PDF_NOT_FOUND, "候选没有公开 PDF 地址")
    if isinstance(max_redirects, bool) or max_redirects < 0 or max_bytes < 1 or max_header_bytes < 1:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "下载限制配置无效")
    started = clock()
    partial: Path | None = None
    private_dir: Path | None = None
    final_path: Path | None = None
    succeeded = False
    own_client = client is None
    try:
        target = validate_url(url, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver)
        root = Path(temp_dir or _setting(settings, "article_download_dir", tempfile.gettempdir())).resolve()
        root.mkdir(parents=True, exist_ok=True)
        private_dir = Path(tempfile.mkdtemp(prefix="paper-download-", dir=root))
        os.chmod(private_dir, stat.S_IRWXU)
        descriptor, partial_name = tempfile.mkstemp(prefix=".partial-", suffix=".part", dir=private_dir)
        partial = Path(partial_name)
        timeout, total_timeout = _timeouts(settings)
        if own_client:
            client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport)
        current_url = target
        redirects = 0
        total = 0
        digest = hashlib.sha256()
        first_bytes = bytearray()
        with os.fdopen(descriptor, "wb") as output:
            while True:
                if clock() - started > total_timeout:
                    raise PaperDownloadError(DOWNLOAD_TIMEOUT, "下载超过总超时")
                try:
                    stream = client.stream("GET", current_url.url, timeout=timeout)
                    with stream as response:
                        if _header_size(response) > max_header_bytes:
                            raise PaperDownloadError(DOWNLOAD_BLOCKED, "响应头超过限制")
                        _check_peer(response, current_url, peer_ip_resolver, transport, not own_client)
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location or redirects >= max_redirects:
                                raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向次数超过限制")
                            redirects += 1
                            try:
                                current_url = validate_redirect_target(current_url, location, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver)
                            except URLSecurityError as error:
                                raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向目标被拒绝") from error
                            continue
                        if response.status_code in (401, 403):
                            raise PaperDownloadError(LOGIN_REQUIRED, "下载来源需要登录")
                        if response.status_code == 404:
                            raise PaperDownloadError(PDF_NOT_FOUND, "PDF 不存在")
                        if response.status_code in (408, 504):
                            raise PaperDownloadError(DOWNLOAD_TIMEOUT, "下载来源超时")
                        if response.status_code < 200 or response.status_code >= 300:
                            raise PaperDownloadError(PDF_NOT_FOUND, "PDF 下载不可用")
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                if int(content_length) > max_bytes:
                                    raise PaperDownloadError(PDF_TOO_LARGE, "PDF 超过大小限制")
                            except ValueError as error:
                                raise PaperDownloadError(INVALID_PDF, "响应大小无效") from error
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        for chunk in response.iter_bytes():
                            if clock() - started > total_timeout:
                                raise PaperDownloadError(DOWNLOAD_TIMEOUT, "下载超过总超时")
                            if not isinstance(chunk, bytes):
                                chunk = bytes(chunk)
                            total += len(chunk)
                            if total > max_bytes:
                                raise PaperDownloadError(PDF_TOO_LARGE, "PDF 超过大小限制")
                            if len(first_bytes) < 5:
                                first_bytes.extend(chunk[: 5 - len(first_bytes)])
                            digest.update(chunk)
                            output.write(chunk)
                        # A PDF magic prefix is necessary but not sufficient:
                        # HTML/login responses must be rejected even when a
                        # test or proxy prepends a forged ``%PDF-`` prefix.
                        # Missing Content-Type remains supported for injected
                        # transports; any declared non-PDF type is invalid.
                        if content_type == "text/html" or (
                            content_type and content_type != "application/pdf"
                        ) or bytes(first_bytes) != b"%PDF-":
                            raise PaperDownloadError(INVALID_PDF, "下载内容不是 PDF")
                        break
                except httpx.TimeoutException as error:
                    raise PaperDownloadError(DOWNLOAD_TIMEOUT, "下载超时") from error
                except httpx.HTTPError as error:
                    raise PaperDownloadError(PDF_NOT_FOUND, "PDF 下载失败") from error
        final_path = private_dir / f"{secrets.token_hex(16)}.pdf"
        os.replace(partial, final_path)
        partial = None
        if pdf_page_validator:
            try:
                pages = pdf_page_validator(final_path)
            except PaperDownloadError:
                raise
            except Exception as error:
                raise PaperDownloadError(INVALID_PDF, "PDF 无法读取") from error
        else:
            pages = _validate_pages(final_path) if validate_pdf_pages else None
        if pages is not None and pages < 1:
            raise PaperDownloadError(INVALID_PDF, "PDF 没有可读取页面")
        succeeded = True
        return DownloadResult(str(final_path), total, digest.hexdigest(), current_url.url, pages)
    except URLSecurityError as error:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "下载地址被安全策略拒绝") from error
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
        if not succeeded and final_path is not None:
            final_path.unlink(missing_ok=True)
        if private_dir is not None and not succeeded:
            shutil.rmtree(private_dir, ignore_errors=True)
        if own_client and client is not None:
            client.close()
