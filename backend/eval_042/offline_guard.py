"""离线出口守卫：本评测只允许访问 loopback 主机，任何外网目标立即拒绝。

用于步骤 4（离线校验）的结构化保证：所有 HTTP 调用前先校验 host，
非白名单主机直接抛 OfflineGuardError，绝不发生外网请求。
"""
from __future__ import annotations

from urllib.parse import urlparse

from .config import ALLOWED_HOSTS


class OfflineGuardError(Exception):
    """试图访问非 loopback 主机，违反离线硬约束。"""


def assert_loopback(url: str) -> str:
    """校验 url 的主机在 ALLOWED_HOSTS 内，返回归一化主机名；否则抛错。"""
    try:
        host = urlparse(url).hostname or ""
    except Exception as exc:  # pragma: no cover - 解析失败时按违规处理
        raise OfflineGuardError(f"cannot parse url: {url!r} ({exc})") from exc
    if host.lower() not in ALLOWED_HOSTS:
        raise OfflineGuardError(
            f"offline guard blocked non-loopback host {host!r} (url={url!r}); "
            f"allowed={sorted(ALLOWED_HOSTS)}"
        )
    return host.lower()


def is_loopback(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return host.lower() in ALLOWED_HOSTS
