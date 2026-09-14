"""spec-032 候选 3：安全会议论文的**无人值守** PDF 分层下载。

分层策略（详见 ``docs/sdd/plans/032/artifacts/task-04/pdf-download-candidate3.md``）：

1. **公开层（open access）**：走既有公开直下链 ``paper_download.download_candidate``
   （URL/SSRF/DNS/逐跳重定向/peer IP 全套校验），不需要浏览器。
2. **持久化浏览器层（browser）**：公开层拿不到时，复用 ``PaperBrowserManager`` 的
   ``launch_persistent_context`` 登录态，经
   ``BrowserSession.authenticated_pdf_request_via_page`` 拉 PDF（origin 白名单 + 逐跳
   重定向校验 + 临时目录 0700 由既有实现保证）。

为什么需要浏览器层：实测 ``https://dl.acm.org/doi/pdf/{doi}`` 在浏览器里可下，纯 HTTP
恒 403（Cloudflare 机器人挑战，与 IP / 机构订阅 / 权限无关，机构网络实测同样 403），
header/UA 组合已证伪；合法脚本方式（OpenAlex OA）覆盖仅约 34%。

**为什么用页面导航而不是 ``BrowserContext.request``**：人工解挑战后 Cloudflare 签发的
``cf_clearance`` 绑定解挑战的那个浏览器实例（UA+TLS+指纹）。APIRequest 自带 UA 与浏览器
不一致，Cloudflare 判定失效 → 即使持久化上下文持有有效 cookie 也返回 403（2026-09-14
实测：裸请求 / 带真实 UA+Sec-Fetch-* / ``?download=true`` / 未过挑战时的 ``page.goto``
四种全部 403）。走 ``page.goto`` + ``resp.body()`` 用的是浏览器自己的网络栈，UA/TLS/指纹
一致，挑战放行。

**不做**的事：不伪造 UA/header、不解析或绕过机器人挑战、不碰付费墙、不在发现阶段
探测 PDF、不在代码里做登录。一次性人工登录由用户在持久化 profile 里完成；上下文未认证时
本模块返回 ``LOGIN_REQUIRED``（``login_required=True``）让上层提示用户。

**禁止重复实现**：HTTP 下载、URL 安全校验、浏览器会话与站点白名单、DOI/标题规范化
全部复用既有实现（``download_candidate`` / ``_check_peer`` / ``_timeouts`` / ``SITE_ORIGINS`` /
``_origin`` / ``normalize_doi`` / ``normalize_title`` / ``_candidate_value``）。

**DOI 解析器地址（``doi.org`` / ``www.doi.org`` / ``dx.doi.org`` / ``www.dx.doi.org``）**：
这类地址只是「指路牌」，本身永远不是下载目标。实测 NDSS 记录经 OpenAlex 会带出
``pdf_url=https://doi.org/10.14722/ndss.2024.24017``，它 302 到
``https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf``；而
``download_candidate`` 是在**跟随重定向之前**用 ``allowed_hosts`` 校验初始 URL 的，
于是被校验的是 ``doi.org`` 而不是最终落地主机 → 只声明最终真实主机的配置 100% ``DOWNLOAD_BLOCKED``。
把 ``doi.org`` 加进 ``allowed_hosts`` 虽然能跑通，但等于允许它重定向到任意域名（白名单被架空），
因此**不可接受**。正确做法：公开层下载前先用同一套 ``url_security`` 设施**逐跳**解析重定向
（``doi_resolver.resolve_doi_url``，**唯一实现**，入库路径 ``import_candidate`` 共用同一函数），
用**最终 host** 过 ``allowed_hosts``，再把最终 URL 交给既有 ``download_candidate`` 复核。
``doi.org`` 绝不因此进入下载白名单。

层级取值（``pdf_access``，spec-032 冻结）：

===================  ==============================================================
``open_access``      公开 PDF 地址，普通 HTTPS 可直下
``browser_required`` 出版方直链，普通 HTTPS 被机器人挑战拦下，只有持久化浏览器能取
``unavailable``      有 DOI 但没有任何可用路径（构造不出直链、也不在白名单内）
``unknown``          连判定依据（DOI 与 ``pdf_url``）都缺
===================  ==============================================================

注意双轴：领域对象/store 里的 ``pdf_access`` 另有**冻结词表**
``{unknown, public, login_required, unavailable}``（``paper_discovery_store.py`` 会把越界值
静默降级为 ``unknown``）。本模块的层级是**派生的下载路由**，不改写该字段，二者是不同轴。
"""

from __future__ import annotations

import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from backend.app.core.url_security import DEFAULT_MAX_REDIRECTS
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.paper_discovery.infrastructure.doi_resolver import (
    DOI_RESOLVER_HOSTS,
    resolve_doi_url,
)
from backend.app.paper_discovery.infrastructure.paper_browser_manager import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
    SITE_ORIGINS,
    SUPPORTED_SITES,
    BrowserManagerError,
    _origin,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    LOGIN_REQUIRED,
    DownloadResult,
    PaperDownloadError,
    _candidate_value,
    download_candidate,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

logger = logging.getLogger(__name__)

PDF_ACCESS_OPEN_ACCESS = "open_access"
PDF_ACCESS_BROWSER_REQUIRED = "browser_required"
PDF_ACCESS_UNAVAILABLE = "unavailable"
PDF_ACCESS_UNKNOWN = "unknown"
PDF_ACCESS_LEVELS = (
    PDF_ACCESS_OPEN_ACCESS,
    PDF_ACCESS_BROWSER_REQUIRED,
    PDF_ACCESS_UNAVAILABLE,
    PDF_ACCESS_UNKNOWN,
)

#: 下载路由层 id（结果里的 ``layer``）。
PDF_ACCESS_LAYER_OPEN_ACCESS = "open_access"
PDF_ACCESS_LAYER_BROWSER = "browser"

#: 既有冻结词表里代表「公开可直下」的取值（见模块 docstring 的双轴说明）。
_OPEN_ACCESS_VALUES = frozenset({"public", PDF_ACCESS_OPEN_ACCESS})
#: 需要上层提示用户先登录的稳定错误码。
_LOGIN_REQUIRED_CODES = frozenset({LOGIN_REQUIRED, BROWSER_SESSION_REQUIRED, BROWSER_SESSION_EXPIRED})

PDF_UNAVAILABLE = "PDF_UNAVAILABLE"
PDF_OPEN_ACCESS_SKIPPED = "PDF_OPEN_ACCESS_SKIPPED"
PDF_OPEN_ACCESS_FAILED = "PDF_OPEN_ACCESS_FAILED"
PDF_BROWSER_UNAVAILABLE = "PDF_BROWSER_UNAVAILABLE"
PDF_BROWSER_FAILED = "PDF_BROWSER_FAILED"
PDF_DOWNLOAD_FAILED = "PDF_DOWNLOAD_FAILED"

_LOGIN_PROMPT = "持久化浏览器上下文未认证：请先手动登录一次（保持 profile）后重试"

_IEEE_DOCUMENT_RE = re.compile(r"/document/(\d+)")

#: 兼容既有命名（上一轮修复与本模块 docstring 引用的名字）。实现已提取到
#: ``doi_resolver.DOI_RESOLVER_HOSTS``，入库路径与批量下载器共用同一份，不再复制。
_DOI_RESOLVER_HOSTS = DOI_RESOLVER_HOSTS


def site_for_url(url: Any) -> Optional[str]:
    """把 PDF 地址反查成受控站点 id；复用 ``SITE_ORIGINS`` 白名单，不新建第二套。

    显式端口 / 凭据 / fragment 的地址不算受控 origin（与 ``validate_origin`` 一致）。
    """
    if not isinstance(url, str) or not url:
        return None
    origin = _origin(url)
    if not origin:
        return None
    for site, origins in SITE_ORIGINS.items():
        if origin in origins:
            return site
    return None


def _declared_site(record: Any) -> Optional[str]:
    """读取调用方显式声明的站点（``pdf_site``），非法值一律忽略。"""
    site = str(_candidate_value(record, "pdf_site", "") or "").strip().casefold()
    return site if site in SUPPORTED_SITES else None


def build_publisher_pdf_url(site: Any, *, doi: Any = "", article_url: Any = "") -> Optional[str]:
    """构造出版方 PDF 候选直链；**只记录，绝不请求**。

    白名单外的站点（例如 NDSS 的 ``www.ndss-symposium.org``）一律返回 ``None``——
    绝不把非受控站点伪造成 acm/ieee 站点。
    """
    site = str(site or "").strip().casefold()
    if site not in SUPPORTED_SITES:
        return None
    origin = next(iter(SITE_ORIGINS[site]))
    if site == "acm":
        normalized = normalize_doi(doi)
        if not normalized:
            return None
        return f"{origin}/doi/pdf/{normalized}"
    # IEEE Xplore 的 PDF 直链需要 document number（arnumber），只有 DOI 构造不出来。
    match = _IEEE_DOCUMENT_RE.search(str(article_url or ""))
    if not match:
        return None
    return f"{origin}/stampPDF/getPDF.jsp?tp=&arnumber={match.group(1)}"


def classify_pdf_access(record: Any) -> str:
    """判定一条记录的 PDF 获取层级（取值见模块 docstring）。"""
    url = _candidate_value(record, "pdf_url")
    declared = str(_candidate_value(record, "pdf_access", "") or "").strip().casefold()
    if not isinstance(url, str) or not url:
        # 没有地址：有 DOI 说明能判定归属（只是缺路径），否则无从判定。
        return PDF_ACCESS_UNAVAILABLE if normalize_doi(_candidate_value(record, "doi")) else PDF_ACCESS_UNKNOWN
    if declared in _OPEN_ACCESS_VALUES:
        return PDF_ACCESS_OPEN_ACCESS
    if _declared_site(record) is not None or site_for_url(url) is not None:
        return PDF_ACCESS_BROWSER_REQUIRED
    # 非白名单 URL（典型来源：OpenAlex ``best_oa_location`` 指向 arXiv / 机构仓库
    # 等），默认走公开路径；下载端 ``allowed_hosts`` 会按白名单拒绝任何未授权
    # 主机（fail-closed），不会"以为免费就乱下"。这样 ``ccs_fetch.py`` 输出的
    # 纯 JSONL 记录（无 ``pdf_access`` 字段）也能正确分类，不会被错认为无法获取。
    return PDF_ACCESS_OPEN_ACCESS


def _identity(record: Any) -> str:
    """身份键：复用既有 DOI / 标题规范化（与各 Source Adapter 的 ``normalize_identity`` 同规则）。"""
    doi = normalize_doi(_candidate_value(record, "doi"))
    if doi:
        return f"doi:{doi}"
    year = _candidate_value(record, "year", 0)
    year = year if isinstance(year, int) and not isinstance(year, bool) else 0
    return f"title:{normalize_title(_candidate_value(record, 'title'))}|{year}"


@dataclass(frozen=True)
class ConferencePdfOutcome:
    """单条记录的下载结果；``attempts`` 逐层记录 ``(层, 错误码)``，成功层错误码为空串。"""

    identity: str
    title: str
    doi: str
    pdf_access: str
    ok: bool
    layer: Optional[str] = None
    url: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    page_count: Optional[int] = None
    error_code: Optional[str] = None
    reason: str = ""
    login_required: bool = False
    attempts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ConferencePdfBatchResult:
    """批量结果与各层命中率统计（供上层进度/报告使用）。"""

    outcomes: tuple[ConferencePdfOutcome, ...] = ()

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def ok_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.ok)

    @property
    def succeeded(self) -> tuple[ConferencePdfOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.ok)

    @property
    def failed(self) -> tuple[ConferencePdfOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if not outcome.ok)

    @property
    def login_required_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.login_required)

    def _counts(self, values: Iterable[Optional[str]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
        return counts

    @property
    def layer_counts(self) -> dict[str, int]:
        """命中层计数（只统计成功记录）。"""
        return self._counts(outcome.layer for outcome in self.outcomes if outcome.ok)

    @property
    def access_counts(self) -> dict[str, int]:
        """各获取层级的记录数（全量）。"""
        return self._counts(outcome.pdf_access for outcome in self.outcomes)

    @property
    def error_counts(self) -> dict[str, int]:
        """失败错误码计数。"""
        return self._counts(outcome.error_code for outcome in self.outcomes if not outcome.ok)


class ConferencePdfDownloader:
    """批量无人值守下载器：公开层优先，失败才用持久化浏览器上下文。

    ``downloader`` / ``browser_manager`` 均可注入（测试用 fake，不依赖真实 chromium）。
    ``allowed_hosts`` 由调用方提供（与 ``import_candidate`` 同合同：不从候选 URL 推导主机名）；
    为空时公开层 fail-closed 并给出可行动原因，绝不放宽校验。
    """

    def __init__(
        self,
        *,
        settings: Any = None,
        allowed_hosts: Iterable[str] = (),
        browser_manager: Any = None,
        downloader: Callable[..., DownloadResult] = download_candidate,
        transport: Any = None,
        client: Any = None,
        dns_resolver: Any = None,
        peer_ip_resolver: Any = None,
        temp_dir: Any = None,
        pdf_page_validator: Any = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self.settings = settings or ArticleSettings()
        self.allowed_hosts = tuple(str(host) for host in (allowed_hosts or ()))
        self.browser_manager = browser_manager
        self._download = downloader
        self.transport = transport
        self.client = client
        self.dns_resolver = dns_resolver
        self.peer_ip_resolver = peer_ip_resolver
        self.temp_dir = temp_dir
        self.pdf_page_validator = pdf_page_validator
        self.max_redirects = max_redirects

    # --- 单条 ---------------------------------------------------------------

    def download(self, record: Any) -> ConferencePdfOutcome:
        """按层尝试下载一条记录；任何失败都转成稳定错误码，绝不抛给批量循环。"""
        access = classify_pdf_access(record)
        plan = self._plan(record, access)
        attempts: list[tuple[str, str]] = []
        last_code = PDF_UNAVAILABLE
        last_reason = "没有可用的 PDF 获取路径"
        for layer, site, url in plan:
            if layer == PDF_ACCESS_LAYER_OPEN_ACCESS:
                result, code, reason = self._download_open_access(url)
            else:
                result, code, reason = self._download_via_browser(site, url)
            attempts.append((layer, code))
            if result is not None:
                return self._outcome(
                    record, access, ok=True, layer=layer, url=result.url, result=result, attempts=attempts
                )
            last_code, last_reason = code, reason
            logger.warning(
                "conference_pdf_downloader: layer=%s identity=%s failed code=%s",
                layer,
                _identity(record),
                code,
            )
        return self._outcome(
            record,
            access,
            ok=False,
            error_code=last_code,
            reason=last_reason,
            login_required=last_code in _LOGIN_REQUIRED_CODES,
            attempts=tuple(attempts),
        )

    def download_batch(
        self,
        records: Iterable[Any],
        *,
        progress: Optional[Callable[[int, int, ConferencePdfOutcome], None]] = None,
    ) -> ConferencePdfBatchResult:
        """逐条下载：单条失败不影响其他记录（与批任务「失败降级」一致）。"""
        items = tuple(records)
        outcomes: list[ConferencePdfOutcome] = []
        for index, record in enumerate(items, start=1):
            try:
                outcome = self.download(record)
            except Exception:  # 兜底：任何非预期异常都不得中断整批
                logger.warning("conference_pdf_downloader: record failed unexpectedly", exc_info=True)
                outcome = self._outcome(
                    record,
                    PDF_ACCESS_UNKNOWN,
                    ok=False,
                    error_code=PDF_DOWNLOAD_FAILED,
                    reason="PDF 下载失败",
                )
            outcomes.append(outcome)
            if progress is not None:
                progress(index, len(items), outcome)
        return ConferencePdfBatchResult(tuple(outcomes))

    # --- 层实现 -------------------------------------------------------------

    def _plan(self, record: Any, access: str) -> tuple[tuple[str, Optional[str], str], ...]:
        """按优先级列出可用层；URL 是站点的唯一判定依据（适配器负责记录直链）。"""
        url = _candidate_value(record, "pdf_url")
        url = url if isinstance(url, str) and url else None
        plan: list[tuple[str, Optional[str], str]] = []
        if access == PDF_ACCESS_OPEN_ACCESS and url:
            plan.append((PDF_ACCESS_LAYER_OPEN_ACCESS, None, url))
        site = _declared_site(record) or site_for_url(url)
        if site is not None:
            browser_url = url if site_for_url(url) == site else build_publisher_pdf_url(
                site,
                doi=_candidate_value(record, "doi"),
                article_url=_candidate_value(record, "article_url", ""),
            )
            if browser_url:
                plan.append((PDF_ACCESS_LAYER_BROWSER, site, browser_url))
        return tuple(plan)

    def _download_open_access(self, url: str) -> tuple[Optional[DownloadResult], str, str]:
        if not self.allowed_hosts:
            # 既有校验对空 allowlist 是 fail-closed；这里直接给出可行动原因，避免无谓请求。
            return None, PDF_OPEN_ACCESS_SKIPPED, "未配置公开下载 allowlist（allowed_hosts 为空），跳过公开直下"
        try:
            # DOI 解析器地址只是「指路牌」：先逐跳解析出**最终落地**地址（实现唯一，见
            # ``doi_resolver.resolve_doi_url``，入库路径 ``import_candidate`` 共用同一函数），
            # 再用最终 host 过调用方的 ``allowed_hosts``；非解析器地址原样返回（行为不变）。
            resolved = resolve_doi_url(
                url,
                allowed_hosts=self.allowed_hosts,
                settings=self.settings,
                transport=self.transport,
                client=self.client,
                dns_resolver=self.dns_resolver,
                peer_ip_resolver=self.peer_ip_resolver,
                max_redirects=self.max_redirects,
            )
            result = self._download({"pdf_url": resolved}, self.settings, self.allowed_hosts, **self._download_kwargs())
        except PaperDownloadError as error:
            return None, error.code, error.message
        except Exception:
            logger.warning("conference_pdf_downloader: open-access layer failed unexpectedly", exc_info=True)
            return None, PDF_OPEN_ACCESS_FAILED, "公开直下失败"
        return result, "", ""

    def _download_via_browser(self, site: Optional[str], url: str) -> tuple[Optional[DownloadResult], str, str]:
        if self.browser_manager is None:
            return None, PDF_BROWSER_UNAVAILABLE, "未装配 PaperBrowserManager，无法使用持久化浏览器"
        try:
            # 不传 url：无人值守不导航到登录页；登录态来自持久化 profile。
            session = self.browser_manager.open_session(site)
        except BrowserManagerError as error:
            return None, error.code, error.message
        except Exception:
            logger.warning("conference_pdf_downloader: browser session unavailable", exc_info=True)
            return None, PDF_BROWSER_FAILED, "浏览器会话不可用"
        try:
            # 必须走页面导航（page.goto）而不是 BrowserContext.request：cf_clearance
            # 绑定签发它的浏览器实例（UA+TLS+指纹），APIRequest 自带 UA 会被 Cloudflare
            # 判为不一致而失效 → 恒 403（2026-09-14 实测）。逐跳白名单/大小/PDF 校验
            # 仍由 BrowserSession 既有实现保证，调用方错误映射不变。
            result = session.authenticated_pdf_request_via_page(url, **self._browser_kwargs())
        except PaperDownloadError as error:
            reason = _LOGIN_PROMPT if error.code in _LOGIN_REQUIRED_CODES else error.message
            return None, error.code, reason
        except BrowserManagerError as error:
            reason = _LOGIN_PROMPT if error.code in _LOGIN_REQUIRED_CODES else error.message
            return None, error.code, reason
        except Exception:
            logger.warning("conference_pdf_downloader: browser layer failed unexpectedly", exc_info=True)
            return None, PDF_BROWSER_FAILED, "浏览器认证下载失败"
        finally:
            with suppress(Exception):
                session.close()
        return result, "", ""

    def _download_kwargs(self) -> dict[str, Any]:
        return self._passthrough(
            "transport",
            "client",
            "dns_resolver",
            "peer_ip_resolver",
            "temp_dir",
            "pdf_page_validator",
            "max_redirects",
        )

    def _browser_kwargs(self) -> dict[str, Any]:
        return self._passthrough("temp_dir", "pdf_page_validator", "max_redirects")

    def _passthrough(self, *names: str) -> dict[str, Any]:
        return {name: getattr(self, name) for name in names if getattr(self, name) is not None}

    def _outcome(
        self,
        record: Any,
        access: str,
        *,
        ok: bool,
        layer: Optional[str] = None,
        url: Optional[str] = None,
        result: Optional[DownloadResult] = None,
        error_code: Optional[str] = None,
        reason: str = "",
        login_required: bool = False,
        attempts: tuple[tuple[str, str], ...] = (),
    ) -> ConferencePdfOutcome:
        return ConferencePdfOutcome(
            identity=_identity(record),
            title=" ".join(str(_candidate_value(record, "title") or "").split()),
            doi=normalize_doi(_candidate_value(record, "doi")),
            pdf_access=access,
            ok=ok,
            layer=layer,
            url=url,
            file_path=result.file_path if result is not None else None,
            file_size=result.file_size if result is not None else None,
            checksum=result.checksum if result is not None else None,
            page_count=result.page_count if result is not None else None,
            error_code=error_code,
            reason=reason,
            login_required=login_required,
            attempts=tuple(attempts),
        )


__all__ = [
    "PDF_ACCESS_BROWSER_REQUIRED",
    "PDF_ACCESS_LAYER_BROWSER",
    "PDF_ACCESS_LAYER_OPEN_ACCESS",
    "PDF_ACCESS_LEVELS",
    "PDF_ACCESS_OPEN_ACCESS",
    "PDF_ACCESS_UNAVAILABLE",
    "PDF_ACCESS_UNKNOWN",
    "PDF_BROWSER_FAILED",
    "PDF_BROWSER_UNAVAILABLE",
    "PDF_DOWNLOAD_FAILED",
    "PDF_OPEN_ACCESS_FAILED",
    "PDF_OPEN_ACCESS_SKIPPED",
    "PDF_UNAVAILABLE",
    "ConferencePdfBatchResult",
    "ConferencePdfDownloader",
    "ConferencePdfOutcome",
    "build_publisher_pdf_url",
    "classify_pdf_access",
    "site_for_url",
]
