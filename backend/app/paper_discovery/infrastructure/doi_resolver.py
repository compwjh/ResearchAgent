"""DOI 解析器地址（``doi.org`` 一族）的**逐跳**解析。

为什么需要它
------------
OpenAlex 富化后的记录常把 ``pdf_url`` 写成 DOI 解析器地址，例如 NDSS 的
``https://doi.org/10.14722/ndss.2024.24017``；该地址 302 到
``https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf``（真实 PDF）。

``download_candidate`` 是在**跟随重定向之前**用 ``allowed_hosts`` 校验初始 URL 的，
于是被校验的是 ``doi.org``（跳转入口）而不是最终落地主机——只声明最终真实主机的配置
100% ``DOWNLOAD_BLOCKED``。

把 ``doi.org`` 加进 ``allowed_hosts`` 虽然能跑通，但 ``doi.org`` 可以 302 到**任意域名**，
等于把主机白名单架空（``evil.example.test`` 也会被放行），**因此不可接受**。

正确做法：下载前先用同一套 ``url_security`` 设施**逐跳**解析重定向，用**最终 host**
过调用方的 ``allowed_hosts``，再把最终 URL 交给既有 ``download_candidate`` 复核。
``doi.org`` 绝不因此进入任何下载白名单。

唯一实现
--------
本模块是这条能力的**唯一实现**，两个调用方共用：

- ``conference_pdf_downloader.ConferencePdfDownloader._download_open_access``（批量下载器）
- ``paper_import.import_candidate``（入库路径）

两处必须引用本模块的**同一个函数对象**，不得各自复制一份（回归护栏见
``tests/test_spec032_doi_resolver_import.py``）。

安全约束（与批量下载器完全一致）
--------------------------------
- ``DOI_RESOLVER_HOSTS`` 是**封闭集合**（不接受调用方输入），**只**用于校验解析入口那一跳。
- 每一跳（含中间跳）都过调用方传入的 ``allowed_hosts``。
- 内网 / 回环 / 链路本地 / 保留地址在每一跳由 ``url_security`` 拒绝。
- 重定向次数受 ``max_redirects``（默认 ``DEFAULT_MAX_REDIRECTS``）限制。
- 保留 ``_check_peer`` 对端 IP 复核，与下载链同一套判断。
- 失败一律转成稳定错误码（``PaperDownloadError``），绝不抛裸异常。
- **没有**「跳过校验」的开关，也不放宽 ``allowed_hosts`` 语义。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

import httpx

from backend.app.core.url_security import (
    DEFAULT_MAX_REDIRECTS,
    URLSecurityError,
    ValidatedURL,
    validate_redirect_target,
    validate_url,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    PDF_NOT_FOUND,
    PaperDownloadError,
    _check_peer,
    _timeouts,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

logger = logging.getLogger(__name__)

#: DOI 解析器主机：**封闭集合**（不接受调用方输入）。这些地址只是「指路牌」，本身不是下载目标，
#: 因此**只**用于校验解析入口那一跳，绝不进入下载用的 ``allowed_hosts``。
DOI_RESOLVER_HOSTS = frozenset({"doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"})

#: 与 ``download_candidate`` 一致的重定向状态码集合。
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def doi_resolver_host(url: Any) -> Optional[str]:
    """返回 URL 的 DOI 解析器主机名；不是解析器地址（或无法解析）时返回 ``None``。"""
    if not isinstance(url, str) or not url:
        return None
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.casefold() if host and host.casefold() in DOI_RESOLVER_HOSTS else None


def resolve_doi_url(
    url: Any,
    *,
    allowed_hosts: Iterable[str],
    settings: Any = None,
    dns_resolver: Optional[Callable[[str], Iterable[object]]] = None,
    transport: Any = None,
    client: Any = None,
    peer_ip_resolver: Optional[Callable[..., Optional[str]]] = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> str:
    """把 DOI 解析器地址换成它**最终落地**的地址；非解析器地址原样返回。

    调用方必须在**下载之前**调用本函数，并把返回值当作下载目标（仍由
    ``download_candidate`` 用**原样的** ``allowed_hosts`` 复核最终 host，并复核实际连接的
    对端 IP）。

    失败一律抛 ``PaperDownloadError``（稳定错误码），调用方无需再包一层异常处理。
    """
    if doi_resolver_host(url) is None:
        return url
    try:
        # 入口那一跳用封闭的解析器主机集合校验（仍然做 DNS 公共地址/协议/端口/认证参数检查）。
        target = validate_url(url, allowed_hosts=DOI_RESOLVER_HOSTS, dns_resolver=dns_resolver)
    except URLSecurityError as error:
        raise PaperDownloadError(DOWNLOAD_BLOCKED, "DOI 解析地址被安全策略拒绝") from error
    timeout, _ = _timeouts(settings or ArticleSettings())
    probe_client, own_client = _probe_client(client, transport, timeout)
    redirects = 0
    try:
        while True:
            status, location = _probe(
                probe_client, target, timeout, transport=transport, client=client, peer_ip_resolver=peer_ip_resolver
            )
            if status not in REDIRECT_STATUSES:
                if redirects == 0:
                    # 解析器没有重定向：既没解析出可下载地址，doi.org 也不是下载目标（fail-closed）。
                    raise PaperDownloadError(PDF_NOT_FOUND, "DOI 未解析到可下载的地址")
                return target.url
            if not location or redirects >= max_redirects:
                raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向次数超过限制")
            redirects += 1
            try:
                # 每一跳都过调用方的 allowlist：中间跳未授权同样拒绝。
                target = validate_redirect_target(
                    target, location, allowed_hosts=allowed_hosts, dns_resolver=dns_resolver
                )
            except URLSecurityError as error:
                raise PaperDownloadError(DOWNLOAD_BLOCKED, "DOI 解析到未授权的下载地址") from error
    except httpx.TimeoutException as error:
        raise PaperDownloadError(DOWNLOAD_TIMEOUT, "DOI 解析超时") from error
    except httpx.HTTPError as error:
        raise PaperDownloadError(PDF_NOT_FOUND, "无法解析 DOI 目标地址") from error
    finally:
        if own_client:
            with suppress(Exception):
                probe_client.close()


def _probe_client(
    client: Any, transport: Any, timeout: httpx.Timeout
) -> tuple[httpx.Client, bool]:
    """解析探针的网络出口：复用调用方注入的 client / transport，不自建第二套。"""
    if client is not None:
        return client, False
    return (
        httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport),
        True,
    )


def _probe(
    probe_client: httpx.Client,
    target: ValidatedURL,
    timeout: httpx.Timeout,
    *,
    transport: Any = None,
    client: Any = None,
    peer_ip_resolver: Optional[Callable[..., Optional[str]]] = None,
) -> tuple[int, Optional[str]]:
    """只读状态码与 ``Location``：不读响应体，避免把整份 PDF 拉两遍。"""
    with probe_client.stream("GET", target.url, timeout=timeout, follow_redirects=False) as response:
        # 与 download_candidate 同一套对端复核：真实 transport 必须给出可校验的 peer IP。
        _check_peer(response, target, peer_ip_resolver, transport, client is not None)
        return response.status_code, response.headers.get("location")


__all__ = [
    "DOI_RESOLVER_HOSTS",
    "REDIRECT_STATUSES",
    "doi_resolver_host",
    "resolve_doi_url",
]
