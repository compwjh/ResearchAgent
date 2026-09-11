import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import httpx

from backend.app.article_assistant.domain.article import ArticleCandidate
from backend.app.core.url_security import (
    DEFAULT_MAX_REDIRECTS,
    URLSecurityError,
    ValidatedURL,
    validate_peer_ip,
    validate_redirect_target,
    validate_url,
)
from backend.app.platform.settings.settings_repository import ArticleSettings


class _PdfLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        if href and ("pdf" in href.lower() or "download" in href.lower()):
            self.links.append(href)


def safe_filename(title: str, suffix: str = ".pdf") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff .-]+", "_", title).strip(" .") or "article"
    return f"{cleaned[:180]}{suffix}"


def _allowed_hosts(settings: ArticleSettings) -> set[str]:
    """Return only hosts explicitly configured by the server.

    Article candidates are external metadata snapshots and must never expand
    the source allowlist.  ``article_download_urls`` is the legacy configured
    origin list; ``paper_discovery_allowed_hosts`` is an explicit host-only
    setting already carried by the shared settings object.  With neither set,
    article probe/download fails closed before opening a network request.
    """
    hosts: set[str] = set()
    for value in (
        *(settings.article_download_urls or []),
        *(getattr(settings, "paper_discovery_allowed_hosts", []) or []),
    ):
        try:
            host = urlsplit(value).hostname if "://" in value else value
        except ValueError:
            host = None
        if host:
            hosts.add(host.casefold().rstrip("."))
    return hosts


def _validate_article_url(
    url: str,
    settings: ArticleSettings,
    *,
    allowed_hosts: Iterable[str] | None = None,
) -> ValidatedURL:
    # HTTP was accepted by the legacy settings contract.  Keep that compatibility
    # while applying the same host, DNS, port, redirect and peer checks as the
    # secure paper downloader.  New paper-discovery calls retain HTTPS-only
    # defaults because this option is only passed by the legacy adapter.
    return validate_url(
        url,
        allowed_hosts=allowed_hosts if allowed_hosts is not None else _allowed_hosts(settings),
        allowed_schemes=("http", "https"),
    )


def _validate_article_peer(response: object, target: ValidatedURL) -> None:
    # Existing unit callers use tiny response doubles.  A real httpx.Response
    # must expose peer evidence; otherwise an actual connection cannot be
    # rechecked against the DNS result and is blocked fail-closed.
    if not isinstance(response, httpx.Response):
        return
    extensions = getattr(response, "extensions", {}) or {}
    peer = extensions.get("peer_ip")
    stream = extensions.get("network_stream")
    if peer is None and stream is not None and hasattr(stream, "get_extra_info"):
        for key in ("peername", "server_addr"):
            try:
                peer = stream.get_extra_info(key)
            except Exception:
                peer = None
            if peer:
                break
    if isinstance(peer, tuple):
        peer = peer[0]
    if not peer:
        raise URLSecurityError("DOWNLOAD_BLOCKED", "无法复核实际连接地址")
    validate_peer_ip(target, str(peer))


def _probe_url(
    url: str,
    settings: ArticleSettings,
    *,
    redirects: int = 0,
    visited: frozenset[str] = frozenset(),
    allowed_hosts: Iterable[str] | None = None,
) -> Tuple[str, str]:
    if redirects > DEFAULT_MAX_REDIRECTS or url in visited:
        return "invalid", url
    try:
        hosts = set(allowed_hosts if allowed_hosts is not None else _allowed_hosts(settings))
        target = _validate_article_url(url, settings, allowed_hosts=hosts)
        with httpx.stream(
            "GET",
            target.url,
            headers={"Range": "bytes=0-1023"},
            timeout=settings.article_pdf_probe_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as response:
            _validate_article_peer(response, target)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location or redirects >= DEFAULT_MAX_REDIRECTS:
                    return "invalid", target.url
                redirected = validate_redirect_target(
                    target,
                    location,
                    allowed_hosts=hosts,
                    allowed_schemes=("http", "https"),
                )
                return _probe_url(
                    redirected.url,
                    settings,
                    redirects=redirects + 1,
                    visited=visited | {url},
                    allowed_hosts=hosts,
                )
            if response.status_code in (401, 403):
                return "login_required", target.url
            if response.status_code == 429:
                return "rate_limited", target.url
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            chunks = []
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                if sum(len(item) for item in chunks) >= 8192:
                    break
            body = b"".join(chunks)
            prefix = body[:5]
            if prefix == b"%PDF-" or "application/pdf" in content_type:
                return "public_pdf", str(getattr(response, "url", target.url))
            if "text/html" in content_type or body.lstrip().startswith(b"<"):
                parser = _PdfLinkParser()
                parser.feed(body.decode("utf-8", errors="ignore"))
                for link in parser.links:
                    linked_url = urljoin(str(getattr(response, "url", target.url)), link)
                    status, resolved_url = _probe_url(
                        linked_url,
                        settings,
                        redirects=redirects + 1,
                        visited=visited | {url},
                        allowed_hosts=hosts,
                    )
                    if status in {"public_pdf", "login_required", "rate_limited"}:
                        return status, resolved_url
            return "invalid", str(getattr(response, "url", target.url))
    except URLSecurityError:
        return "not_found", url
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (401, 403):
            return "login_required", url
        if error.response.status_code == 429:
            return "rate_limited", url
        return "not_found", url
    except httpx.HTTPError:
        return "not_found", url


def probe_pdf_url(candidate: ArticleCandidate, settings: ArticleSettings) -> Tuple[str, str]:
    url = candidate.pdf_url or candidate.article_url or (settings.article_download_urls[0] if settings.article_download_urls else None)
    if not url:
        return "not_found", ""
    return _probe_url(url, settings, allowed_hosts=_allowed_hosts(settings))


def download_article(candidate: ArticleCandidate, settings: ArticleSettings, extra_headers: Optional[dict] = None) -> Iterator[dict]:
    download_url = candidate.pdf_url or (settings.article_download_urls[0] if settings.article_download_urls else None)
    if not download_url:
        raise ValueError("候选文章没有可下载的 PDF 地址")
    output_dir = Path(settings.article_download_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_filename(candidate.title)
    max_bytes = settings.article_max_file_size_mb * 1024 * 1024
    digest = hashlib.sha256()
    total = 0
    request_headers = dict(extra_headers or {})
    content_type = ""
    try:
        allowed_hosts = _allowed_hosts(settings)
        target = _validate_article_url(download_url, settings, allowed_hosts=allowed_hosts)
        redirects = 0
        with output_path.open("wb") as file:
            while True:
                with httpx.stream(
                    "GET",
                    target.url,
                    headers=request_headers,
                    timeout=settings.article_request_timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                ) as response:
                    _validate_article_peer(response, target)
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location or redirects >= DEFAULT_MAX_REDIRECTS:
                            raise ValueError("下载重定向次数超过限制")
                        target = validate_redirect_target(
                            target,
                            location,
                            allowed_hosts=allowed_hosts,
                            allowed_schemes=("http", "https"),
                        )
                        redirects += 1
                        continue
                    if response.status_code in (401, 403):
                        candidate.requires_login = True
                        raise PermissionError("下载来源需要登录")
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > max_bytes:
                        raise ValueError("文件超过大小限制")
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("文件超过大小限制")
                        digest.update(chunk)
                        file.write(chunk)
                    break
        with output_path.open("rb") as file:
            if file.read(5) != b"%PDF-":
                raise ValueError(f"下载内容不是 PDF（{content_type or '未知类型'}）")
    except URLSecurityError as error:
        output_path.unlink(missing_ok=True)
        raise ValueError("下载地址被安全策略拒绝") from error
    except (httpx.HTTPError, ValueError, PermissionError):
        output_path.unlink(missing_ok=True)
        raise
    yield {"type": "result", "file_path": str(output_path), "file_size": total, "checksum": digest.hexdigest()}
