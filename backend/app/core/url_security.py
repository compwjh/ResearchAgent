"""Shared URL and connection-target checks for server-side downloads.

The module deliberately performs no HTTP requests. Callers inject DNS resolution and must validate the peer address after connecting.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urljoin, urlsplit

DOWNLOAD_BLOCKED = "DOWNLOAD_BLOCKED"
INVALID_URL = "INVALID_URL"
DEFAULT_MAX_REDIRECTS = 5
_AUTH_QUERY_NAMES = frozenset(
    {"auth", "authorization", "api_key", "apikey", "access_key", "key", "password",
     "passwd", "secret", "session", "sig", "signature", "token", "access_token",
     "refresh_token", "id_token", "jwt", "cookie"}
)
DNSResolver = Callable[[str], Iterable[object]]


class URLSecurityError(ValueError):
    def __init__(self, code: str, message: str = "URL 被安全策略拒绝") -> None:
        if code not in {DOWNLOAD_BLOCKED, INVALID_URL}:
            raise ValueError("未知 URL 安全错误码")
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _fail(code: str, message: str) -> None:
    raise URLSecurityError(code, message)


def _normalise_host(host: str) -> str:
    if not host or any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in host):
        _fail(INVALID_URL, "URL 主机名无效")
    if "%" in host:
        _fail(DOWNLOAD_BLOCKED, "URL 主机名包含非标准地址表示")
    try:
        normalized = host.rstrip(".").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        _fail(INVALID_URL, "URL 主机名无效")
    if not normalized or any(not label for label in normalized.split(".")):
        _fail(INVALID_URL, "URL 主机名无效")
    return normalized


def _looks_obfuscated(host: str) -> bool:
    if host.isdigit() or ":" in host and not _parse_ip(host):
        return True
    labels = host.split(".")
    if any(label.lower().startswith("0x") for label in labels):
        return True
    return all(label.isdigit() for label in labels) and (len(labels) != 4 or _parse_ip(host) is None)


def _parse_ip(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(str(value))
    except ValueError:
        return None


def _unsafe_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        (address.version == 6 and address.ipv4_mapped is not None)
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def _allowlist(allowed_hosts: Iterable[str]) -> frozenset[str]:
    values: set[str] = set()
    try:
        entries = list(allowed_hosts)
    except TypeError:
        _fail(INVALID_URL, "下载站点 allowlist 无效")
    if not entries:
        _fail(DOWNLOAD_BLOCKED, "下载站点不在 allowlist")
    for entry in entries:
        if not isinstance(entry, str) or "/" in entry or "@" in entry or "?" in entry:
            _fail(INVALID_URL, "下载站点 allowlist 无效")
        wildcard = entry.startswith("*.")
        host = entry[2:] if wildcard else entry
        host = _normalise_host(host.strip())
        if wildcard and not host:
            _fail(INVALID_URL, "下载站点 allowlist 无效")
        values.add(("*." if wildcard else "") + host)
    return frozenset(values)


def _allowed(host: str, patterns: frozenset[str]) -> bool:
    return host in patterns or any(
        pattern.startswith("*.") and host.endswith("." + pattern[2:]) and host != pattern[2:]
        for pattern in patterns
    )


def _default_resolver(host: str) -> Iterable[object]:
    return [item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def _public_addresses(host: str, resolver: DNSResolver | None) -> tuple[str, ...]:
    try:
        values = [host] if _parse_ip(host) is not None else list((resolver or _default_resolver)(host))
    except (OSError, socket.gaierror, TypeError, ValueError):
        _fail(DOWNLOAD_BLOCKED, "DNS 解析失败")
    public: list[str] = []
    for value in values:
        if isinstance(value, tuple):
            value = value[4][0] if len(value) > 4 and isinstance(value[4], tuple) else (value[0] if value else "")
        address = _parse_ip(value)
        if address is None or _unsafe_ip(address):
            continue
        text = str(address)
        if text not in public:
            public.append(text)
    if not public:
        _fail(DOWNLOAD_BLOCKED, "DNS 解析结果不是公共地址")
    return tuple(public)


def validate_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    dns_resolver: DNSResolver | None = None,
    authentication_query_names: Iterable[str] = _AUTH_QUERY_NAMES,
    allowed_schemes: Iterable[str] = ("https",),
) -> ValidatedURL:
    """Validate one download URL and return addresses safe to connect to."""
    if not isinstance(url, str) or not url or any(ord(char) < 32 for char in url):
        _fail(INVALID_URL, "URL 无效")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        _fail(INVALID_URL, "URL 无效")
    scheme = parsed.scheme.lower()
    schemes = {str(value).lower() for value in allowed_schemes}
    if scheme not in schemes:
        _fail(DOWNLOAD_BLOCKED if scheme == "http" else INVALID_URL, "URL 不符合下载协议")
    if not host:
        _fail(INVALID_URL, "URL 主机名无效")
    if parsed.username is not None or parsed.password is not None:
        _fail(DOWNLOAD_BLOCKED, "URL 不得包含用户信息")
    if parsed.fragment:
        _fail(DOWNLOAD_BLOCKED, "URL 不得包含 fragment")
    query_names = {str(name).casefold() for name in authentication_query_names}
    query_names |= _AUTH_QUERY_NAMES
    if any(key.casefold() in query_names or re.search(r"(?:^|[_-])(token|secret|password|credential|signature)(?:$|[_-])", key.casefold()) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        _fail(DOWNLOAD_BLOCKED, "URL 包含认证参数")
    host = _normalise_host(host)
    if _looks_obfuscated(host):
        _fail(DOWNLOAD_BLOCKED, "URL 主机名包含混淆地址")
    patterns = _allowlist(allowed_hosts)
    if not _allowed(host, patterns):
        _fail(DOWNLOAD_BLOCKED, "下载站点不在 allowlist")
    default_port = 443 if scheme == "https" else 80
    if port not in (None, default_port):
        _fail(DOWNLOAD_BLOCKED, "下载端口不被允许")
    addresses = _public_addresses(host, dns_resolver)
    return ValidatedURL(url=url, hostname=host, port=default_port, addresses=addresses)


def validate_redirect_target(
    current_url: str | ValidatedURL,
    location: str,
    *,
    allowed_hosts: Iterable[str],
    dns_resolver: DNSResolver | None = None,
    allowed_schemes: Iterable[str] = ("https",),
) -> ValidatedURL:
    """Resolve and validate one Location target; callers must invoke per hop."""
    base = current_url.url if isinstance(current_url, ValidatedURL) else current_url
    if not isinstance(location, str) or not location:
        _fail(INVALID_URL, "重定向目标无效")
    return validate_url(
        urljoin(base, location),
        allowed_hosts=allowed_hosts,
        dns_resolver=dns_resolver,
        allowed_schemes=allowed_schemes,
    )


def validate_redirect_chain(
    initial_url: str,
    locations: Iterable[str],
    *,
    allowed_hosts: Iterable[str],
    dns_resolver: DNSResolver | None = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    allowed_schemes: Iterable[str] = ("https",),
) -> ValidatedURL:
    """Validate an initial URL and manually supplied redirect Locations."""
    if isinstance(max_redirects, bool) or max_redirects < 0:
        _fail(INVALID_URL, "重定向上限无效")
    current = validate_url(
        initial_url,
        allowed_hosts=allowed_hosts,
        dns_resolver=dns_resolver,
        allowed_schemes=allowed_schemes,
    )
    for count, location in enumerate(locations, start=1):
        if count > max_redirects:
            _fail(DOWNLOAD_BLOCKED, "重定向次数超过限制")
        current = validate_redirect_target(
            current,
            location,
            allowed_hosts=allowed_hosts,
            dns_resolver=dns_resolver,
            allowed_schemes=allowed_schemes,
        )
    return current


def validate_peer_ip(target: ValidatedURL, peer_ip: str) -> str:
    """Require the connected peer to be one of the DNS-validated public IPs."""
    address = _parse_ip(peer_ip)
    if address is None or _unsafe_ip(address) or str(address) not in target.addresses:
        _fail(DOWNLOAD_BLOCKED, "实际连接地址与校验结果不一致")
    return str(address)

