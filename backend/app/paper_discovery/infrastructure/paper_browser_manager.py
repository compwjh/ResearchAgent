"""Small, credential-safe Playwright bridge for paper imports.

The bridge is deliberately independent from the ACM and IEEE DOM adapters.  It
only owns the headed persistent context, its profile lock, and the narrow URL
boundary used by those adapters.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional
from urllib.parse import urlsplit

from backend.app.paper_discovery.domain.paper_download_security import (
    DEFAULT_MAX_REDIRECTS,
    URLSecurityError,
    ValidatedURL,
    validate_redirect_target,
    validate_url,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    INVALID_PDF,
    LOGIN_REQUIRED,
    MAX_PDF_BYTES,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    DownloadResult,
    PaperDownloadError,
    _validate_pages,
)
from backend.app.platform.config import BASE_DIR

try:  # Playwright is optional so public-PDF imports keep working without it.
    from playwright.async_api import TimeoutError as _PlaywrightAsyncTimeoutError
    from playwright.sync_api import TimeoutError as _PlaywrightSyncTimeoutError
    from playwright.sync_api import sync_playwright as _sync_playwright
except ImportError:  # pragma: no cover - exercised through the health tests
    _sync_playwright = None
    _PlaywrightSyncTimeoutError = None
    _PlaywrightAsyncTimeoutError = None


_PLAYWRIGHT_TIMEOUT_ERRORS = tuple(
    error_type
    for error_type in (_PlaywrightSyncTimeoutError, _PlaywrightAsyncTimeoutError)
    if isinstance(error_type, type)
)


def _is_timeout_error(error: BaseException) -> bool:
    """Recognize built-in and Playwright sync/async timeout exceptions."""
    return isinstance(error, TimeoutError) or any(
        isinstance(error, error_type) for error_type in _PLAYWRIGHT_TIMEOUT_ERRORS
    )


PINNED_PLAYWRIGHT_VERSION = "1.52.0"
DEFAULT_PROFILE_DIR = BASE_DIR / "data" / "browser-profile" / "security-papers"
SUPPORTED_SITES = ("acm", "ieee")
SITE_ORIGINS = {
    "acm": frozenset({"https://dl.acm.org"}),
    "ieee": frozenset({"https://ieeexplore.ieee.org"}),
}

BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
BROWSER_PROFILE_LOCKED = "BROWSER_PROFILE_LOCKED"
BROWSER_PROFILE_UNSAFE = "BROWSER_PROFILE_UNSAFE"
BROWSER_ORIGIN_NOT_ALLOWED = "BROWSER_ORIGIN_NOT_ALLOWED"
BROWSER_TIMEOUT = "BROWSER_TIMEOUT"
BROWSER_CRASHED = "BROWSER_CRASHED"
BROWSER_CANCELLED = "BROWSER_CANCELLED"


class BrowserManagerError(RuntimeError):
    """Stable, non-sensitive error returned by the browser bridge."""

    def __init__(self, code: str, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _runtime_version() -> Optional[str]:
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        return ""
    # urlsplit().port can raise for malformed/non-numeric ports.  A URL with a
    # port is not an ACM/IEEE origin, even when it happens to use port 443.
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port is not None:
        return ""
    return f"https://{parsed.hostname.lower()}"


class _ProfileLock:
    """Process lock for the one persistent profile (POSIX implementation)."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.touch(mode=0o600, exist_ok=True)
            os.chmod(self.path, 0o600)
            handle = self.path.open("r+")
        except OSError as exc:
            raise BrowserManagerError(BROWSER_PROFILE_UNSAFE, "浏览器 profile 不可安全使用") from exc
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as exc:
            handle.close()
            raise BrowserManagerError(BROWSER_PROFILE_LOCKED, "浏览器 profile 正被另一个任务使用") from exc
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


class BrowserSession:
    """A single site-owned page; closing it always releases its site lock."""

    def __init__(self, manager: "PaperBrowserManager", site: str, page: Any, lock: threading.Lock, context: Any = None):
        self.manager = manager
        self.site = site
        self.page = page
        # Keep the persistent context available only through controlled
        # methods.  Callers never receive cookies, headers, or the profile.
        self.context = context
        self._lock = lock
        self._closed = False

    def goto(self, url: str, **kwargs: Any) -> Any:
        self.manager.validate_origin(self.site, url)
        if self._closed:
            raise BrowserManagerError(BROWSER_CANCELLED, "浏览器会话已关闭")
        try:
            return self.page.goto(url, **kwargs)
        except Exception as exc:  # Playwright's Error is optional at import time.
            if _is_timeout_error(exc):
                raise BrowserManagerError(BROWSER_TIMEOUT, "浏览器页面加载超时") from exc
            self.manager._recover_after_failure(exc)
            raise BrowserManagerError(BROWSER_CRASHED, "浏览器页面不可用，请重试") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.page.close()
        except Exception:
            self.manager._recover_after_failure(None)
        finally:
            self._lock.release()

    def authenticated_pdf_request(
        self,
        url: Any,
        *,
        temp_dir: os.PathLike[str] | str | None = None,
        max_bytes: int = MAX_PDF_BYTES,
        timeout_ms: int | None = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        pdf_page_validator: Callable[[Path], int] | None = None,
    ) -> DownloadResult:
        """Fetch one allowlisted PDF through this session's authenticated context.

        Playwright's ``BrowserContext.request`` shares the persistent browser
        storage state while keeping credentials inside the browser process.
        Only a validated temporary file and safe download metadata leave this
        boundary; response headers and exception text are never returned.
        """
        # ``import_candidate`` invokes downloader callbacks with the complete
        # server-side candidate, while small callers may provide a URL
        # directly.  Accept both forms without accepting a client URL from the
        # API (the route still resolves the candidate server-side).
        if not isinstance(url, str):
            url = url.get("pdf_url") if isinstance(url, Mapping) else getattr(url, "pdf_url", None)
        if not isinstance(url, str) or not url:
            raise PaperDownloadError(PDF_NOT_FOUND, "候选没有 PDF 地址")
        self.manager.validate_origin(self.site, url)
        if isinstance(max_redirects, bool) or max_redirects < 0:
            raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向次数超过限制")
        try:
            current = self._validate_download_url(url)
        except URLSecurityError as error:
            raise PaperDownloadError(DOWNLOAD_BLOCKED, "下载地址被安全策略拒绝") from error
        if self._closed:
            raise BrowserManagerError(BROWSER_CANCELLED, "浏览器会话已关闭")
        if isinstance(max_bytes, bool) or max_bytes < 1:
            raise PaperDownloadError(PDF_TOO_LARGE, "PDF 大小限制无效")
        context = self.context or self.manager._context
        request_context = getattr(context, "request", None)
        get = getattr(request_context, "get", None)
        if not callable(get):
            raise BrowserManagerError(BROWSER_UNAVAILABLE, "浏览器认证请求当前不可用")

        private_dir: Path | None = None
        final_path: Path | None = None
        succeeded = False
        try:
            root = Path(temp_dir or tempfile.gettempdir()).resolve()
            root.mkdir(parents=True, exist_ok=True)
            private_dir = Path(tempfile.mkdtemp(prefix="paper-browser-download-", dir=root))
            os.chmod(private_dir, 0o700)
            redirects = 0
            while True:
                # Playwright otherwise follows redirects inside the request
                # context.  Disable that behavior and validate each Location
                # before issuing the next authenticated request.
                response = get(
                    current.url,
                    fail_on_status_code=False,
                    timeout=timeout_ms or self.manager.page_timeout_ms,
                    max_redirects=0,
                )
                status = int(getattr(response, "status", 0) or 0)
                headers = getattr(response, "headers", {}) or {}
                if status in (301, 302, 303, 307, 308):
                    location = headers.get("location")
                    if not location or redirects >= max_redirects:
                        raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向次数超过限制")
                    try:
                        current = validate_redirect_target(
                            current,
                            location,
                            allowed_hosts=self.manager._download_hosts(self.site),
                            dns_resolver=self.manager.dns_resolver,
                        )
                        # validate_url permits explicit :443, while the
                        # browser seam intentionally requires the exact
                        # canonical ACM/IEEE origin.
                        self.manager.validate_origin(self.site, current.url)
                    except (URLSecurityError, BrowserManagerError) as error:
                        raise PaperDownloadError(DOWNLOAD_BLOCKED, "重定向目标被拒绝") from error
                    redirects += 1
                    continue
                break
            if status in (401, 403):
                raise PaperDownloadError(LOGIN_REQUIRED, "下载来源需要登录")
            if status == 404:
                raise PaperDownloadError(PDF_NOT_FOUND, "PDF 不存在")
            if status < 200 or status >= 300:
                raise PaperDownloadError(PDF_NOT_FOUND, "PDF 下载不可用")
            content_type = str(headers.get("content-type", "")).split(";", 1)[0].strip().lower()
            content_length = headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise PaperDownloadError(PDF_TOO_LARGE, "PDF 超过大小限制")
                except ValueError as error:
                    raise PaperDownloadError(INVALID_PDF, "响应大小无效") from error
            body_method = getattr(response, "body", None)
            body = body_method() if callable(body_method) else getattr(response, "body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            if len(body) > max_bytes:
                raise PaperDownloadError(PDF_TOO_LARGE, "PDF 超过大小限制")
            if (content_type and content_type != "application/pdf") or body[:5] != b"%PDF-":
                raise PaperDownloadError(INVALID_PDF, "下载内容不是 PDF")
            candidate_path = private_dir / (hashlib.sha256(body).hexdigest() + ".pdf")
            candidate_path.write_bytes(body)
            validator = pdf_page_validator if pdf_page_validator is not None else _validate_pages
            try:
                page_count = validator(candidate_path)
            except PaperDownloadError:
                raise
            except Exception as error:
                raise PaperDownloadError(INVALID_PDF, "PDF 无法读取") from error
            if page_count < 1:
                raise PaperDownloadError(INVALID_PDF, "PDF 没有可读取页面")
            final_path = candidate_path
            succeeded = True
            return DownloadResult(
                str(final_path),
                len(body),
                hashlib.sha256(body).hexdigest(),
                current.url,
                page_count,
            )
        except (PaperDownloadError, BrowserManagerError):
            raise
        except Exception as error:
            # Do not expose Playwright's exception text: it may contain URLs
            # or request headers.  The stable code is sufficient to retry.
            if _is_timeout_error(error):
                raise BrowserManagerError(BROWSER_TIMEOUT, "浏览器认证请求超时") from error
            self.manager._recover_after_failure(error)
            raise BrowserManagerError(BROWSER_CRASHED, "浏览器认证请求失败，请重试") from error
        finally:
            if not succeeded and private_dir is not None:
                shutil.rmtree(private_dir, ignore_errors=True)

    def _validate_download_url(self, url: str) -> ValidatedURL:
        """Apply the public downloader's URL checks to authenticated fetches."""
        target = validate_url(
            url,
            allowed_hosts=self.manager._download_hosts(self.site),
            dns_resolver=self.manager.dns_resolver,
        )
        # Preserve this seam's stricter exact-origin contract, including the
        # rejection of an explicit port spelling such as ``:443``.
        self.manager.validate_origin(self.site, target.url)
        return target

    # Importer-friendly callback name; both names intentionally share the same
    # safe implementation and return the standard DownloadResult contract.
    download_pdf = authenticated_pdf_request

    def cancel(self) -> None:
        self.close()

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


class PaperBrowserManager:
    """Own a headed, persistent Playwright context for ACM and IEEE only.

    ``playwright_factory`` is intentionally injectable.  Tests can provide a
    tiny fake with ``chromium.launch_persistent_context`` without installing a
    browser or writing credentials to the real profile.
    """

    def __init__(
        self,
        settings: Any = None,
        *,
        profile_dir: Optional[os.PathLike[str] | str] = None,
        playwright_factory: Optional[Callable[[], Any]] = None,
        page_timeout_seconds: Optional[float] = None,
        launch_kwargs: Optional[Mapping[str, Any]] = None,
        dns_resolver: Optional[Callable[[str], Any]] = None,
    ):
        configured = getattr(settings, "paper_discovery_browser_profile_dir", None)
        configured = configured or os.getenv("PAPER_DISCOVERY_BROWSER_PROFILE_DIR")
        self.profile_dir = Path(profile_dir or configured or DEFAULT_PROFILE_DIR).expanduser().resolve()
        self.page_timeout_ms = int(
            1000
            * (page_timeout_seconds if page_timeout_seconds is not None else getattr(settings, "article_login_timeout_seconds", 300))
        )
        self._playwright_factory = playwright_factory
        self._launch_kwargs = dict(launch_kwargs or {})
        self.dns_resolver = dns_resolver
        self._lock = _ProfileLock(self.profile_dir / ".profile.lock")
        self._site_locks = {site: threading.Lock() for site in SUPPORTED_SITES}
        self._state_lock = threading.RLock()
        self._playwright = None
        self._context = None
        self._profile_owned = False

    @property
    def available(self) -> bool:
        return self.health()["available"]

    def health(self) -> dict[str, Any]:
        """Return only the public browser capability contract."""
        if self._playwright_factory is not None:
            return {
                "available": True,
                "version": self._fake_version(),
                "supported_sites": list(SUPPORTED_SITES),
                "reason": None,
            }
        if _sync_playwright is None:
            return {
                "available": False,
                "version": None,
                "supported_sites": list(SUPPORTED_SITES),
                "reason": BROWSER_UNAVAILABLE,
            }
        version = _runtime_version()
        if version != PINNED_PLAYWRIGHT_VERSION:
            return {
                "available": False,
                "version": version,
                "supported_sites": list(SUPPORTED_SITES),
                "reason": BROWSER_UNAVAILABLE,
            }
        return {
            "available": True,
            "version": version,
            "supported_sites": list(SUPPORTED_SITES),
            "reason": None,
        }

    def _fake_version(self) -> str:
        factory = self._playwright_factory
        version = getattr(factory, "version", None)
        if version is None:
            version = getattr(getattr(factory, "__self__", None), "version", None)
        return str(version or PINNED_PLAYWRIGHT_VERSION)

    def validate_origin(self, site: str, url: str) -> None:
        site = site.lower().strip()
        if site not in SITE_ORIGINS or _origin(url) not in SITE_ORIGINS[site]:
            raise BrowserManagerError(BROWSER_ORIGIN_NOT_ALLOWED, "目标地址不在受控站点范围内", retryable=False)

    @staticmethod
    def _download_hosts(site: str) -> frozenset[str]:
        origin = next(iter(SITE_ORIGINS[site.lower().strip()]))
        return frozenset({urlsplit(origin).hostname or ""})

    def _ensure_profile(self) -> None:
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.profile_dir, 0o700)
            stat = self.profile_dir.stat()
            if hasattr(os, "getuid") and stat.st_uid != os.getuid():
                raise BrowserManagerError(BROWSER_PROFILE_UNSAFE, "浏览器 profile 所有权不安全")
        except BrowserManagerError:
            raise
        except OSError as exc:
            raise BrowserManagerError(BROWSER_PROFILE_UNSAFE, "浏览器 profile 不可安全使用") from exc

    def _start_playwright(self) -> Any:
        factory = self._playwright_factory or _sync_playwright
        if factory is None:
            raise BrowserManagerError(BROWSER_UNAVAILABLE, "Playwright 当前不可用")
        try:
            value = factory()
            if hasattr(value, "start"):
                value = value.start()
            elif hasattr(value, "__enter__"):
                value = value.__enter__()
            self._playwright = value
            return value
        except BrowserManagerError:
            raise
        except Exception as exc:
            raise BrowserManagerError(BROWSER_UNAVAILABLE, "Playwright 当前不可用") from exc

    def _ensure_context(self) -> Any:
        with self._state_lock:
            if self._context is not None:
                return self._context
            if self._playwright is None:
                self._start_playwright()
            try:
                chromium = self._playwright.chromium
                options = {
                    "headless": False,
                    "accept_downloads": False,
                    "viewport": {"width": 1440, "height": 1000},
                }
                options.update(self._launch_kwargs)
                options["headless"] = False
                options["accept_downloads"] = False
                # Do not let callers accidentally re-enable artifacts that can
                # contain cookies, authorization headers, or downloaded files.
                for forbidden in ("record_har_path", "record_har", "record_video_dir", "downloads_path"):
                    options.pop(forbidden, None)
                self._context = chromium.launch_persistent_context(str(self.profile_dir), **options)
                self._context.set_default_timeout(self.page_timeout_ms)
                self._context.set_default_navigation_timeout(self.page_timeout_ms)
                return self._context
            except Exception as exc:
                self._recover_after_failure(exc)
                raise BrowserManagerError(BROWSER_UNAVAILABLE, "Playwright 浏览器无法启动") from exc

    def open_session(self, site: str, url: Optional[str] = None) -> BrowserSession:
        site = site.lower().strip()
        if site not in SUPPORTED_SITES:
            raise BrowserManagerError(BROWSER_ORIGIN_NOT_ALLOWED, "目标站点不受支持", retryable=False)
        if url is not None:
            self.validate_origin(site, url)
        self._ensure_profile()
        site_lock = self._site_locks[site]
        if not site_lock.acquire(blocking=False):
            raise BrowserManagerError(BROWSER_PROFILE_LOCKED, "该站点浏览器会话正被另一个任务使用")
        try:
            if not self._profile_owned:
                self._lock.acquire()
                self._profile_owned = True
            context = self._ensure_context()
            page = context.new_page()
            page.set_default_timeout(self.page_timeout_ms)
            page.set_default_navigation_timeout(self.page_timeout_ms)
            session = BrowserSession(self, site, page, site_lock, context=context)
            if url is not None:
                session.goto(url)
            return session
        except Exception:
            site_lock.release()
            if self._profile_owned:
                self._lock.release()
                self._profile_owned = False
            raise

    @contextmanager
    def session(self, site: str, url: Optional[str] = None) -> Iterator[BrowserSession]:
        handle = self.open_session(site, url)
        try:
            yield handle
        finally:
            handle.close()

    def _recover_after_failure(self, _exc: Any) -> None:
        with self._state_lock:
            context, self._context = self._context, None
            playwright, self._playwright = self._playwright, None
            for resource in (context, playwright):
                if resource is not None:
                    with suppress(Exception):
                        resource.close()

    def close(self) -> None:
        self._recover_after_failure(None)
        if self._profile_owned:
            self._lock.release()
            self._profile_owned = False

    def __enter__(self) -> "PaperBrowserManager":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


__all__ = [
    "BROWSER_CANCELLED",
    "BROWSER_CRASHED",
    "BROWSER_ORIGIN_NOT_ALLOWED",
    "BROWSER_PROFILE_LOCKED",
    "BROWSER_PROFILE_UNSAFE",
    "BROWSER_TIMEOUT",
    "BROWSER_UNAVAILABLE",
    "BrowserManagerError",
    "BrowserSession",
    "DEFAULT_PROFILE_DIR",
    "PINNED_PLAYWRIGHT_VERSION",
    "PaperBrowserManager",
    "SITE_ORIGINS",
    "SUPPORTED_SITES",
]
