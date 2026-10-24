"""离线出口守卫与受控 HTTP transport。

评测工具只允许向本机的 HTTP loopback 地址发请求。除检查每次请求的 URL
外，transport 还显式禁用环境 proxy，并拒绝所有 HTTP redirect；这样
``HTTP_PROXY`` 或一个本机 3xx 响应都不能把请求带到外网。该模块不修改
``urllib`` 全局 opener，调用方必须显式使用这里的入口。
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from .config import ALLOWED_HOSTS


class OfflineGuardError(Exception):
    """试图访问非 loopback 主机，违反离线硬约束。"""


def _safe_endpoint(url: str) -> str:
    """Return a credential-free endpoint summary for guard errors.

    Guard failures are often surfaced directly by a CLI, so error messages
    must not echo URL userinfo, query parameters, paths, or redirect targets.
    """
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower() or "<missing>"
        host = parsed.hostname or "<missing>"
    except Exception:
        return "<unparseable>"
    return f"{scheme}://{host.lower()}"


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """首期拒绝 redirect，而不是让 urllib 自动跟随。"""

    def _reject(self, req, headers, code):
        location = headers.get("Location", "") if headers is not None else ""
        raise OfflineGuardError(
            "offline guard blocked redirect "
            f"status={code} request={_safe_endpoint(req.full_url)} "
            f"location={_safe_endpoint(location) if location else '<missing>'}"
        )

    def http_error_300(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)

    def http_error_301(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)

    def http_error_302(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)

    def http_error_303(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)

    def http_error_307(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)

    def http_error_308(self, req, fp, code, msg, headers):  # noqa: N802
        return self._reject(req, headers, code)


def _url_for_request(request: urllib.request.Request | str) -> str:
    if isinstance(request, str):
        return request
    return request.full_url


def assert_loopback(url: str) -> str:
    """校验 URL 为无 userinfo 的 HTTP loopback 地址。

    只允许 ``http://127.0.0.1``、``http://localhost`` 和
    ``http://[::1]``（端口与路径可不同）。HTTPS、file/ftp、userinfo、空
    host 和其它 host 均在真正建立连接前拒绝。
    """
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        username = parsed.username
        password = parsed.password
    except Exception as exc:  # pragma: no cover - 解析失败时按违规处理
        raise OfflineGuardError("offline guard blocked invalid URL") from exc
    if scheme != "http":
        raise OfflineGuardError(
            "offline guard blocked non-http scheme "
            f"scheme={scheme!r} host={host.lower() or '<missing>'}"
        )
    if username is not None or password is not None:
        raise OfflineGuardError(
            "offline guard blocked URL userinfo "
            f"scheme={scheme!r} host={host.lower() or '<missing>'}"
        )
    if host.lower() not in ALLOWED_HOSTS:
        raise OfflineGuardError(
            "offline guard blocked non-loopback host "
            f"host={host!r} scheme={scheme!r}"
        )
    return host.lower()


def is_loopback(url: str) -> bool:
    try:
        assert_loopback(url)
    except OfflineGuardError:
        return False
    return True


def build_offline_opener() -> urllib.request.OpenerDirector:
    """创建不读取环境 proxy 且拒绝 redirect 的独立 opener。"""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirectHandler(),
    )


def offline_urlopen(
    request: urllib.request.Request | str,
    *,
    timeout: float = 30,
):
    """在每次尝试前守卫 URL，再用隔离 opener 打开请求。

    返回值与 ``urllib`` response 兼容，由调用方负责关闭；不修改全局
    ``urllib.request`` 状态。redirect 由 opener 直接转换为
    :class:`OfflineGuardError`。
    """
    url = _url_for_request(request)
    assert_loopback(url)
    req = urllib.request.Request(request) if isinstance(request, str) else request
    return build_offline_opener().open(req, timeout=timeout)


_MAX_GET_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (0.05, 0.1)


def _is_retryable_get_error(exc: BaseException) -> bool:
    """只允许 GET 的 HTTP 429/5xx 和连接瞬态错误重试。"""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code <= 599
    transient_types = (
        TimeoutError,
        socket.timeout,
        ConnectionAbortedError,
        ConnectionError,
        BrokenPipeError,
    )
    if isinstance(exc, transient_types):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return isinstance(reason, transient_types)
    return False


def _decode_json_response(response) -> Any:
    with response:
        raw = response.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)


def http_get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30,
    max_attempts: int = _MAX_GET_ATTEMPTS,
) -> Any:
    """执行受控 GET JSON 请求，瞬态错误最多尝试三次。

    ``OfflineGuardError``、认证/参数错误、JSON 解析错误等不可重试错误会
    立即抛出。每次 retry 都重新构造 request，并重新经过
    :func:`offline_urlopen` 的 URL 守卫。
    """
    attempts = max(1, min(int(max_attempts), _MAX_GET_ATTEMPTS))
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        try:
            return _decode_json_response(offline_urlopen(req, timeout=timeout))
        except Exception as exc:
            if attempt + 1 >= attempts or not _is_retryable_get_error(exc):
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)])
    raise AssertionError("unreachable")  # pragma: no cover


def http_post_json(
    url: str,
    body: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    """执行一次受控 POST JSON 请求，不自动重试。

    score 写入在网络异常后可能已经到达服务端；因此未知写入结果必须交给
    上层报告为失败，不能自动重放造成重复 score。
    """
    merged_headers = {"Content-Type": "application/json", **dict(headers or {})}
    req = urllib.request.Request(
        url,
        data=json.dumps(dict(body), ensure_ascii=False).encode("utf-8"),
        headers=merged_headers,
        method="POST",
    )
    return _decode_json_response(offline_urlopen(req, timeout=timeout))
