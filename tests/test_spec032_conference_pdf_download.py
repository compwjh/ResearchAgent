"""Spec-032 Task 04（候选 3）：无人值守 PDF 下载分层测试。

覆盖三件事：

1. **分层判定**（纯函数）：``site_for_url`` / ``classify_pdf_access`` / ``build_publisher_pdf_url``。
   层级取值固定为 ``open_access`` / ``browser_required`` / ``unavailable`` / ``unknown``。
2. **三个适配器只记录 PDF 候选直链、绝不请求**（spec-032 禁止发现阶段下载/探测）。
3. **``ConferencePdfDownloader``**：先走既有安全 HTTP 下载链（OA），OA 失败才复用
   ``PaperBrowserManager`` 的持久化浏览器上下文；逐条降级、错误码稳定、会话必被释放。
4. **DOI 解析器地址（回归）**：``pdf_url`` 是 ``doi.org`` 时，先解析出最终地址、用**最终 host**
   过 ``allowed_hosts``；``doi.org`` 绝不因此进入下载白名单（逐跳校验、重定向有上限、
   内网地址一律拒绝）。

本文件不访问网络、也不需要真实 chromium：浏览器层注入 fake manager/session
（与 ``tests/test_paper_browser_manager.py`` 相同的注入方式），HTTP 层注入 fake downloader。
fake session 记录实际调用的 transport：浏览器层必须走 ``page.goto``（``cf_clearance`` 绑定
浏览器实例的 UA/TLS/指纹，APIRequest 自带 UA 会被 Cloudflare 判为不一致 → 恒 403，2026-09-14
实测），逐跳白名单/大小/PDF 校验由 ``BrowserSession`` 既有实现保证（见
``tests/test_paper_browser_manager.py``）。
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.app.core.url_security import DEFAULT_MAX_REDIRECTS
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import CCS_SOURCE_ID
from backend.app.paper_discovery.infrastructure.ccs_publication_source import CcsPublicationSource
from backend.app.paper_discovery.infrastructure.conference_pdf_downloader import (
    PDF_ACCESS_BROWSER_REQUIRED,
    PDF_ACCESS_LAYER_BROWSER,
    PDF_ACCESS_LAYER_OPEN_ACCESS,
    PDF_ACCESS_OPEN_ACCESS,
    PDF_ACCESS_UNAVAILABLE,
    PDF_ACCESS_UNKNOWN,
    PDF_BROWSER_UNAVAILABLE,
    PDF_OPEN_ACCESS_FAILED,
    PDF_OPEN_ACCESS_SKIPPED,
    PDF_UNAVAILABLE,
    ConferencePdfDownloader,
    build_publisher_pdf_url,
    classify_pdf_access,
    site_for_url,
)
from backend.app.paper_discovery.infrastructure.ieee_sp_paper_parser import IEEE_SP_SOURCE_ID
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import IeeeSpPublicationSource
from backend.app.paper_discovery.infrastructure.ndss_publication_source import NdssPublicationSource
from backend.app.paper_discovery.infrastructure.paper_browser_manager import (
    BROWSER_UNAVAILABLE,
    BrowserManagerError,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    DownloadResult,
    PaperDownloadError,
    download_candidate,
)

FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC_IP = "93.184.216.34"

CCS_2024_NO_OA = "10.1145/3658644.3670328"
CCS_2024_WITH_OA = "10.1145/3658644.3670374"
SP_2025_WITH_OA = "10.1109/sp61157.2025.00241"
SP_2025_OPENALEX_MISSING = "10.1109/sp61157.2025.00083"
SP_2024_NO_OA = "10.1109/sp54263.2024.00212"


# --- 夹具与替身 ---------------------------------------------------------------


def _load(conference: str, name: str) -> Any:
    return json.loads((FIXTURES / conference / name).read_text(encoding="utf-8"))


def _crossref(conference: str, year: int) -> Any:
    prefix = {"ccs": "ccs", "ieee_sp": "sp", "ndss": "ndss"}[conference]
    return _load(conference, f"crossref-{prefix}-{year}.json")


def _ccs_source(handler: Any) -> CcsPublicationSource:
    return CcsPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda _host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
    )


def _ieee_source(handler: Any) -> IeeeSpPublicationSource:
    return IeeeSpPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda _host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
    )


def _ndss_source(handler: Any) -> NdssPublicationSource:
    return NdssPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda _host: [PUBLIC_IP],
        sleep=lambda _seconds: None,
        rate_limit_seconds=0.0,
    )


@dataclass(frozen=True)
class Record:
    """下载器输入的最小记录视图（也可用 Mapping，见下）。"""

    doi: str
    title: str
    year: int = 2024
    pdf_url: str | None = None
    pdf_access: str = "unknown"
    pdf_site: str | None = None


class FakeSession:
    """``BrowserSession`` 的最小替身：只暴露下载器允许使用的那两个方法。

    ``transports`` 记录实际调用的 transport 名：浏览器层**必须**走页面导航
    （``page.goto``），因为 ``cf_clearance`` 绑定签发它的浏览器实例，APIRequest
    自带 UA 会被 Cloudflare 判为不一致 → 恒 403（2026-09-14 实测）。
    """

    def __init__(self, result: DownloadResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.urls: list[str] = []
        self.transports: list[str] = []
        self.closed = False

    def _record(self, transport: str, url: Any) -> DownloadResult:
        self.transports.append(transport)
        self.urls.append(url if isinstance(url, str) else str(url))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result

    def authenticated_pdf_request_via_page(self, url: Any, **_kwargs: Any) -> DownloadResult:
        return self._record("page", url)

    def authenticated_pdf_request(self, url: Any, **_kwargs: Any) -> DownloadResult:
        # 保留同名方法以便断言下载器没有退回被 Cloudflare 拒绝的 transport。
        return self._record("api_request", url)

    def close(self) -> None:
        self.closed = True


class FakeBrowserManager:
    """记录 ``open_session`` 调用，证明下载器复用了持久化上下文入口。"""

    def __init__(self, session: FakeSession):
        self.session = session
        self.opened: list[tuple[str, Any]] = []

    def open_session(self, site: str, url: Any = None) -> FakeSession:
        self.opened.append((site, url))
        return self.session


class FakeDownloader:
    def __init__(self, result: DownloadResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, candidate: Any, settings: Any, allowed_hosts: Any, **kwargs: Any) -> DownloadResult:
        self.calls.append(
            {
                "candidate": candidate,
                "settings": settings,
                "allowed_hosts": tuple(allowed_hosts),
                "kwargs": kwargs,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _download_result(url: str) -> DownloadResult:
    return DownloadResult("/tmp/paper.pdf", 4096, "a" * 64, url, 12)


def _downloader(**kwargs: Any) -> ConferencePdfDownloader:
    kwargs.setdefault("allowed_hosts", ("dl.acm.org", "ieeexplore.ieee.org"))
    return ConferencePdfDownloader(**kwargs)


# --- 1. 分层判定（纯函数） -----------------------------------------------------


def test_site_for_url_reuses_the_browser_origin_whitelist():
    """站点反查必须复用 ``SITE_ORIGINS``，不能另起一套白名单。"""
    assert site_for_url("https://dl.acm.org/doi/pdf/10.1145/3658644.3670328") == "acm"
    assert site_for_url("https://ieeexplore.ieee.org/document/10646786/") == "ieee"
    assert site_for_url("https://arxiv.org/pdf/2504.06552") is None
    assert site_for_url("https://www.ndss-symposium.org/wp-content/uploads/x.pdf") is None
    assert site_for_url(None) is None
    assert site_for_url("") is None


@pytest.mark.parametrize(
    "record,expected",
    [
        # OpenAlex 公开 OA 地址 → 公开直下
        (Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public"), PDF_ACCESS_OPEN_ACCESS),
        # 冻结词表里的 public 与任务词表里的 open_access 都按「公开可直下」处理
        (Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access=PDF_ACCESS_OPEN_ACCESS), PDF_ACCESS_OPEN_ACCESS),
        # 出版方直链 + 未知可访问性 → 只能走持久化浏览器
        (Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a"), PDF_ACCESS_BROWSER_REQUIRED),
        (Record("10.1/a", "A", pdf_url="https://ieeexplore.ieee.org/document/1/"), PDF_ACCESS_BROWSER_REQUIRED),
        # 显式声明的站点（供未来 Task05 的合并记录使用）：优先于 URL 主机判定
        (Record("10.1/a", "A", pdf_url="https://example.test/x.pdf", pdf_site="acm"), PDF_ACCESS_BROWSER_REQUIRED),
        # 有地址但不在白名单 → 按公开路径尝试；下载器按 allowed_hosts 拦截未授权主机
        (Record("10.1/a", "A", pdf_url="https://example.test/x.pdf"), PDF_ACCESS_OPEN_ACCESS),
        # 有 DOI 但没有任何地址 → 无法获取
        (Record("10.1/a", "A"), PDF_ACCESS_UNAVAILABLE),
        # 连判定依据都没有 → 未知
        (Record("", ""), PDF_ACCESS_UNKNOWN),
    ],
)
def test_classify_pdf_access_covers_all_four_levels(record: Record, expected: str):
    assert classify_pdf_access(record) == expected


def test_classify_pdf_access_accepts_mappings():
    payload = {"doi": "10.1/a", "title": "A", "pdf_url": "https://dl.acm.org/doi/pdf/10.1/a"}
    assert classify_pdf_access(payload) == PDF_ACCESS_BROWSER_REQUIRED


def test_classify_pdf_access_non_publisher_url_defaults_to_open_access():
    # OpenAlex ``best_oa_location`` 经常给出 arXiv / 机构仓库直链，
    # 且 ``ccs_fetch.py`` 输出不带 ``pdf_access`` 字段。
    # 之前会误判为 UNAVAILABLE，把免费 PDF 漏掉；现在归入 OPEN_ACCESS，
    # 下载端按 ``allowed_hosts`` 拦截未授权主机（fail-closed）。
    record = {"doi": "10.1145/3658644.3690254", "title": "x", "pdf_url": "https://arxiv.org/pdf/2401.12345"}
    assert classify_pdf_access(record) == PDF_ACCESS_OPEN_ACCESS
    payload = {"doi": "10.1/a", "title": "A", "pdf_url": "https://example.test/x.pdf"}
    assert classify_pdf_access(payload) == PDF_ACCESS_OPEN_ACCESS


@pytest.mark.parametrize(
    "site,doi,article_url,expected",
    [
        (
            "acm",
            "10.1145/3658644.3670328",
            "",
            "https://dl.acm.org/doi/pdf/10.1145/3658644.3670328",
        ),
        (
            "ieee",
            "10.1109/sp54263.2024.00212",
            "https://ieeexplore.ieee.org/document/10646786/",
            "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10646786",
        ),
        # DOI 大小写与空白先规范化，避免生成两个不同直链
        ("acm", " 10.1145/3658644.3670328 ", "", "https://dl.acm.org/doi/pdf/10.1145/3658644.3670328"),
        # 没有 DOI → 构造不出来
        ("acm", "", "", None),
        # IEEE 只有 DOI 是不够的：Xplore 直链需要 document number
        ("ieee", "10.1109/sp54263.2024.00212", "https://doi.org/10.1109/sp54263.2024.00212", None),
        # NDSS（Internet Society）不在浏览器白名单内，禁止伪造 acm/ieee 站点
        ("ndss", "10.14722/ndss.2024.23295", "", None),
        ("", "10.1/a", "", None),
    ],
)
def test_build_publisher_pdf_url_records_candidate_links_only(
    site: str, doi: str, article_url: str, expected: str | None
):
    assert build_publisher_pdf_url(site, doi=doi, article_url=article_url) == expected


# --- 2. 适配器：只记录直链，不请求 PDF -----------------------------------------


def test_ccs_adapter_records_acm_pdf_link_without_requesting_the_pdf():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref("ccs", 2024))
        return httpx.Response(200, json=_load("ccs", "openalex-work-10.1145-3658644.3670328-no-oa-pdf.json"))

    result = _ccs_source(handler).sync_year(2024)

    record = next(item for item in result.records if item.doi == CCS_2024_NO_OA)
    assert record.pdf_url == f"https://dl.acm.org/doi/pdf/{CCS_2024_NO_OA}"
    # 冻结词表：可访问性未知（该直链在普通 HTTP 下会被 Cloudflare 403，只有浏览器能取）
    assert record.pdf_access == "unknown"
    assert record.provenance["pdf_url"] == CCS_SOURCE_ID
    assert classify_pdf_access(record) == PDF_ACCESS_BROWSER_REQUIRED
    # 关键：发现阶段不得对 dl.acm.org 发起任何请求（spec-032 禁止探测 PDF）
    assert requested and all("dl.acm.org" not in url for url in requested)


def test_ccs_adapter_keeps_the_openalex_oa_link_when_present():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref("ccs", 2024))
        work = _load("ccs", "openalex-work-10.1145-3658644.3670374-with-oa-pdf.json")
        # 富化已改为批量：批量接口需要 ``{"results": [...]}`` 形态
        if "filter=doi" in str(request.url):
            return httpx.Response(200, json={"results": [work]})
        return httpx.Response(200, json=work)

    result = _ccs_source(handler).sync_year(2024)

    record = next(item for item in result.records if item.doi == CCS_2024_WITH_OA)
    assert record.pdf_url == f"https://dl.acm.org/doi/pdf/{CCS_2024_WITH_OA}"
    assert record.pdf_access == "public"
    assert record.provenance["pdf_url"] == "openalex"
    # OpenAlex 对 CCS 给出的「OA」地址本身就在 dl.acm.org：公开层失败后仍需浏览器兜底
    assert classify_pdf_access(record) == PDF_ACCESS_OPEN_ACCESS
    assert site_for_url(record.pdf_url) == "acm"


def test_ieee_adapter_records_xplore_pdf_link_from_the_document_number():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref("ieee_sp", 2024))
        return httpx.Response(404, text="not found")

    result = _ieee_source(handler).sync_year(2024)

    record = next(item for item in result.records if item.doi == SP_2024_NO_OA)
    arnumber = record.article_url.rstrip("/").rsplit("/", 1)[-1]
    assert arnumber.isdigit()
    assert record.pdf_url == (
        f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
    )
    assert record.pdf_access == "unknown"
    assert record.provenance["pdf_url"] == IEEE_SP_SOURCE_ID
    assert classify_pdf_access(record) == PDF_ACCESS_BROWSER_REQUIRED


def test_ieee_adapter_keeps_the_arxiv_oa_link_when_present():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref("ieee_sp", 2025))
        if SP_2025_OPENALEX_MISSING in str(request.url):
            return httpx.Response(404, text="not found")
        work = _load("ieee_sp", "openalex-work-10.1109-sp61157.2025.00241-with-oa-pdf.json")
        # 富化已改为批量：批量接口需要 ``{"results": [...]}`` 形态
        if "filter=doi" in str(request.url):
            return httpx.Response(200, json={"results": [work]})
        return httpx.Response(200, json=work)

    result = _ieee_source(handler).sync_year(2025)
    by_doi = {item.doi: item for item in result.records}

    assert by_doi[SP_2025_WITH_OA].pdf_url == "https://arxiv.org/pdf/2504.06552"
    assert classify_pdf_access(by_doi[SP_2025_WITH_OA]) == PDF_ACCESS_OPEN_ACCESS
    assert site_for_url(by_doi[SP_2025_WITH_OA].pdf_url) is None
    # 无 OA 的条目退化为 Xplore 浏览器直链
    assert classify_pdf_access(by_doi[SP_2025_OPENALEX_MISSING]) == PDF_ACCESS_BROWSER_REQUIRED


def test_ndss_records_are_open_access_and_never_browser_required():
    """NDSS（Internet Society）不在浏览器白名单内：只能走公开层，绝不伪造 acm/ieee 站点。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=_crossref("ndss", 2024))
        return httpx.Response(404, text="not found")

    result = _ndss_source(handler).sync_year(2024)

    assert result.records
    for record in result.records:
        assert record.pdf_url and record.pdf_url.startswith("https://www.ndss-symposium.org/")
        assert site_for_url(record.pdf_url) is None
        assert classify_pdf_access(record) == PDF_ACCESS_OPEN_ACCESS


# --- 3. 分层下载器 -------------------------------------------------------------


def test_downloader_defaults_to_the_existing_safe_download_chain():
    """不得新写第二套 HTTP 下载实现：默认下载器必须是既有 ``download_candidate``。"""
    parameters = inspect.signature(ConferencePdfDownloader.__init__).parameters
    assert parameters["downloader"].default is download_candidate


def test_downloader_uses_the_open_access_layer_without_touching_the_browser():
    http = FakeDownloader(result=_download_result("https://arxiv.org/pdf/1.pdf"))
    manager = FakeBrowserManager(FakeSession(result=_download_result("https://arxiv.org/pdf/1.pdf")))
    record = Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public")

    outcome = _downloader(downloader=http, browser_manager=manager).download(record)

    assert outcome.ok is True
    assert outcome.layer == PDF_ACCESS_LAYER_OPEN_ACCESS
    assert outcome.pdf_access == PDF_ACCESS_OPEN_ACCESS
    assert outcome.attempts == ((PDF_ACCESS_LAYER_OPEN_ACCESS, ""),)
    assert len(http.calls) == 1
    assert manager.opened == []


def test_downloader_falls_back_to_the_persistent_browser_when_plain_http_is_blocked():
    http = FakeDownloader(error=PaperDownloadError(LOGIN_REQUIRED, "下载来源需要登录"))
    session = FakeSession(result=_download_result("https://dl.acm.org/doi/pdf/10.1145/3658644.3670374"))
    manager = FakeBrowserManager(session)
    record = Record(
        "10.1145/3658644.3670374",
        "Asynchronous Authentication",
        pdf_url="https://dl.acm.org/doi/pdf/10.1145/3658644.3670374",
        pdf_access="public",
    )

    outcome = _downloader(downloader=http, browser_manager=manager).download(record)

    assert outcome.ok is True
    assert outcome.layer == PDF_ACCESS_LAYER_BROWSER
    assert outcome.attempts == (
        (PDF_ACCESS_LAYER_OPEN_ACCESS, LOGIN_REQUIRED),
        (PDF_ACCESS_LAYER_BROWSER, ""),
    )
    assert len(http.calls) == 1
    # 无人值守：打开会话时不得导航到登录页（一次性人工登录在会话之前完成）
    assert manager.opened == [("acm", None)]
    assert session.urls == ["https://dl.acm.org/doi/pdf/10.1145/3658644.3670374"]
    # 回归护栏：浏览器层必须走页面导航，不能退回恒 403 的 APIRequest transport
    assert session.transports == ["page"]
    assert session.closed is True


def test_downloader_uses_the_page_navigation_transport_for_the_browser_layer():
    """浏览器层必须经 ``page.goto``：APIRequest 的 UA 与浏览器不一致，实测恒 403。"""
    session = FakeSession(result=_download_result("https://dl.acm.org/doi/pdf/10.1/a"))
    record = Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a")

    outcome = _downloader(allowed_hosts=(), browser_manager=FakeBrowserManager(session)).download(record)

    assert outcome.ok is True
    assert outcome.layer == PDF_ACCESS_LAYER_BROWSER
    assert session.transports == ["page"]
    assert session.closed is True


def test_downloader_reports_login_required_so_the_caller_can_prompt_the_user():
    session = FakeSession(error=PaperDownloadError(LOGIN_REQUIRED, "下载来源需要登录"))
    record = Record("10.1145/3658644.3670328", "A", pdf_url=f"https://dl.acm.org/doi/pdf/{CCS_2024_NO_OA}")

    outcome = _downloader(browser_manager=FakeBrowserManager(session)).download(record)

    assert outcome.ok is False
    assert outcome.login_required is True
    assert outcome.error_code == LOGIN_REQUIRED
    assert "登录" in outcome.reason
    assert session.closed is True


def test_downloader_reports_expired_browser_session_as_login_required():
    session = FakeSession(
        error=BrowserManagerError("BROWSER_SESSION_EXPIRED", "浏览器登录会话已过期，请重新登录")
    )
    record = Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a")

    outcome = _downloader(browser_manager=FakeBrowserManager(session)).download(record)

    assert outcome.ok is False
    assert outcome.login_required is True
    assert outcome.error_code == "BROWSER_SESSION_EXPIRED"


def test_downloader_reports_browser_unavailable_when_no_manager_is_wired():
    record = Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a")

    outcome = _downloader(allowed_hosts=(), downloader=FakeDownloader(error=PaperDownloadError(DOWNLOAD_BLOCKED, "x"))).download(record)

    assert outcome.ok is False
    assert outcome.error_code == PDF_BROWSER_UNAVAILABLE
    assert outcome.pdf_access == PDF_ACCESS_BROWSER_REQUIRED


def test_downloader_skips_the_open_access_layer_without_an_allowlist():
    http = FakeDownloader(result=_download_result("https://arxiv.org/pdf/1.pdf"))
    record = Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public")

    outcome = ConferencePdfDownloader(downloader=http).download(record)

    assert outcome.ok is False
    assert http.calls == []  # 未配置 allowlist：不做无谓请求
    assert outcome.attempts == ((PDF_ACCESS_LAYER_OPEN_ACCESS, PDF_OPEN_ACCESS_SKIPPED),)
    assert outcome.error_code == PDF_OPEN_ACCESS_SKIPPED


def test_downloader_marks_records_without_any_route():
    # 非白名单 URL 在新契约下走 OPEN_ACCESS 层；allowed_hosts=() 时下载端
    # 返回 DOWNLOAD_BLOCKED，证明 1) 被正确路由 2) 安全闸门真的拦了。
    http = FakeDownloader(error=PaperDownloadError(DOWNLOAD_BLOCKED, "下载站点不在 allowlist"))
    manager = FakeBrowserManager(FakeSession(result=_download_result("https://example.test/x.pdf")))

    outcome = _downloader(downloader=http, browser_manager=manager).download(
        Record("10.1/a", "A", pdf_url="https://example.test/x.pdf")
    )

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    assert outcome.pdf_access == PDF_ACCESS_OPEN_ACCESS
    assert manager.opened == []


def test_downloader_never_opens_a_browser_for_a_public_third_party_host():
    http = FakeDownloader(error=PaperDownloadError(DOWNLOAD_BLOCKED, "下载站点不在 allowlist"))
    manager = FakeBrowserManager(FakeSession(result=_download_result("https://arxiv.org/pdf/1.pdf")))
    record = Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public")

    outcome = _downloader(downloader=http, browser_manager=manager).download(record)

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    assert manager.opened == []


def test_downloader_closes_the_session_even_when_the_browser_layer_succeeds_late():
    session = FakeSession(result=_download_result("https://dl.acm.org/doi/pdf/10.1/a"))
    manager = FakeBrowserManager(session)

    outcome = _downloader(allowed_hosts=(), browser_manager=manager).download(
        Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a")
    )

    assert outcome.ok is True
    assert session.closed is True


def test_downloader_derives_identity_from_existing_normalizers():
    record = Record(" 10.1/A ", "A Title")
    outcome = _downloader().download(record)
    assert outcome.identity == "doi:10.1/a"

    # 复用既有 normalize_title（去空白/标点），不另写一套身份规则
    mapping = {"title": "A  Title", "year": 2024}
    assert _downloader().download(mapping).identity == "title:atitle|2024"


def test_download_batch_aggregates_layers_and_degrades_per_record():
    http = FakeDownloader(result=_download_result("https://arxiv.org/pdf/1.pdf"))
    session = FakeSession(result=_download_result("https://dl.acm.org/doi/pdf/10.1/b"))
    manager = FakeBrowserManager(session)
    records = (
        Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public"),
        Record("10.1/b", "B", pdf_url="https://dl.acm.org/doi/pdf/10.1/b"),
        Record("10.1/c", "C", pdf_url="https://example.test/x.pdf"),
        Record("", ""),
    )
    progress: list[tuple[int, int, bool]] = []

    result = _downloader(downloader=http, browser_manager=manager).download_batch(
        records, progress=lambda index, total, outcome: progress.append((index, total, outcome.ok))
    )

    assert result.total == 4
    assert result.ok_count == 3
    assert [item.identity for item in result.failed] == ["title:|2024"]
    assert result.layer_counts == {PDF_ACCESS_LAYER_OPEN_ACCESS: 2, PDF_ACCESS_LAYER_BROWSER: 1}
    assert result.access_counts == {
        PDF_ACCESS_OPEN_ACCESS: 2,
        PDF_ACCESS_BROWSER_REQUIRED: 1,
        PDF_ACCESS_UNKNOWN: 1,
    }
    assert result.error_counts == {PDF_UNAVAILABLE: 1}
    assert progress == [(1, 4, True), (2, 4, True), (3, 4, True), (4, 4, False)]


def test_download_batch_survives_an_unexpected_layer_error():
    class Exploding:
        def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("boom")

    result = _downloader(downloader=Exploding()).download_batch(
        (Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public"),)
    )

    outcome = result.outcomes[0]
    assert outcome.ok is False
    assert outcome.error_code == PDF_OPEN_ACCESS_FAILED
    assert outcome.reason


def test_downloader_reports_browser_layer_failure_without_leaking_credentials():
    session = FakeSession(error=BrowserManagerError(BROWSER_UNAVAILABLE, "Playwright 当前不可用"))
    record = Record("10.1/a", "A", pdf_url="https://dl.acm.org/doi/pdf/10.1/a")

    outcome = _downloader(allowed_hosts=(), browser_manager=FakeBrowserManager(session)).download(record)

    assert outcome.ok is False
    assert outcome.error_code == BROWSER_UNAVAILABLE
    assert "cookie" not in outcome.reason.casefold()


# --- 4. DOI 解析器地址（回归：doi.org 是「指路牌」，不是下载目标） ---------------
#
# 实测故障：NDSS 记录的 ``pdf_url`` 形如 ``https://doi.org/10.14722/ndss.2024.24017``，
# 该地址 302 到 ``https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf``。
# 修复前 ``download_candidate`` 在**跟随重定向之前**就用 ``allowed_hosts`` 校验初始 URL，
# 于是校验的是 ``doi.org`` 而不是最终落地主机 → ``allowed_hosts=("www.ndss-symposium.org",)``
# 时 100% ``DOWNLOAD_BLOCKED``。
#
# 修复后：公开层下载前先解析 DOI 解析器地址（逐跳复用 ``url_security`` 校验），
# 用**最终 host** 过 ``allowed_hosts``；``doi.org`` 绝不因此进入下载白名单
# （否则等于允许它重定向到任意域名，白名单被架空）。

DOI_RESOLVER_URL = "https://doi.org/10.14722/ndss.2024.24017"
NDSS_PDF_URL = "https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf"
NDSS_HOST = "www.ndss-symposium.org"
NDSS_DOI = "10.14722/ndss.2024.24017"
PDF_BODY = b"%PDF-1.7\n" + b"0" * 512


def _pdf_response(body: bytes = PDF_BODY) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"Content-Type": "application/pdf"})


def _redirect(to: str) -> httpx.Response:
    return httpx.Response(302, headers={"Location": to})


def _doi_resolver_handler(seen: list[str] | None = None) -> Any:
    """DOI 解析器 → NDSS 官方 PDF 的最小 fake transport（不碰真实网络）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if url == DOI_RESOLVER_URL:
            return _redirect(NDSS_PDF_URL)
        if url == NDSS_PDF_URL:
            return _pdf_response()
        return httpx.Response(404, text="not found")

    return handler


def _doi_downloader(handler: Any, **kwargs: Any) -> ConferencePdfDownloader:
    """只声明**最终真实主机**的 allowlist —— 修复的验收配置。"""
    kwargs.setdefault("allowed_hosts", (NDSS_HOST,))
    kwargs.setdefault("transport", httpx.MockTransport(handler))
    kwargs.setdefault("dns_resolver", lambda _host: [PUBLIC_IP])
    return ConferencePdfDownloader(**kwargs)


def test_doi_resolver_url_downloads_through_the_final_allowlisted_host(tmp_path: Path):
    """端到端（真实 ``download_candidate``）：allowlist 只含最终主机也必须能下。"""
    seen: list[str] = []
    downloader = _doi_downloader(
        _doi_resolver_handler(seen),
        temp_dir=tmp_path,
        pdf_page_validator=lambda _path: 12,
    )

    outcome = downloader.download(Record(NDSS_DOI, "NDSS Paper", pdf_url=DOI_RESOLVER_URL, pdf_access="public"))

    assert outcome.ok is True
    assert outcome.layer == PDF_ACCESS_LAYER_OPEN_ACCESS
    assert outcome.error_code is None
    assert outcome.url == NDSS_PDF_URL
    assert outcome.page_count == 12
    assert outcome.file_path and outcome.file_path.endswith(".pdf")
    # 解析探针碰 doi.org 与最终主机；最终主机被请求两次（探针一次 + 真正下载一次）
    assert seen == [DOI_RESOLVER_URL, NDSS_PDF_URL, NDSS_PDF_URL]


def test_doi_resolver_url_is_resolved_before_the_allowlist_is_applied():
    """下载链收到的是**解析后**的最终地址，且 allowlist 里没有 doi.org。"""
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))
    downloader = _doi_downloader(_doi_resolver_handler(), downloader=http)

    outcome = downloader.download(Record(NDSS_DOI, "NDSS Paper", pdf_url=DOI_RESOLVER_URL, pdf_access="public"))

    assert outcome.ok is True
    assert len(http.calls) == 1
    assert http.calls[0]["candidate"] == {"pdf_url": NDSS_PDF_URL}
    # 白名单语义不变：doi.org 没有因为这次解析被加进来
    assert http.calls[0]["allowed_hosts"] == (NDSS_HOST,)
    assert DOI_RESOLVER_URL not in http.calls[0]["allowed_hosts"]


@pytest.mark.parametrize("host", ["doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"])
def test_every_doi_resolver_host_is_recognized(host: str):
    url = f"https://{host}/{NDSS_DOI}"
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))

    def handler(request: httpx.Request) -> httpx.Response:
        return _redirect(NDSS_PDF_URL) if str(request.url) == url else httpx.Response(404, text="not found")

    outcome = _doi_downloader(handler, downloader=http).download(Record(NDSS_DOI, "T", pdf_url=url))

    assert outcome.ok is True
    assert http.calls[0]["candidate"] == {"pdf_url": NDSS_PDF_URL}


def test_doi_redirect_to_an_unauthorized_host_is_blocked():
    http = FakeDownloader(result=_download_result("https://evil.example.test/2024-17-paper.pdf"))

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DOI_RESOLVER_URL:
            return _redirect("https://evil.example.test/2024-17-paper.pdf")
        return _pdf_response()

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    # 未授权的最终主机绝不进入下载链
    assert http.calls == []


def test_doi_redirect_to_a_private_address_is_blocked():
    """最终主机虽在 allowlist 内，但解析到内网地址时必须拒绝。"""
    http = FakeDownloader(result=_download_result("https://internal.example.test/paper.pdf"))
    resolved: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DOI_RESOLVER_URL:
            return _redirect("https://internal.example.test/paper.pdf")
        return _pdf_response()

    def resolver(host: str) -> list[str]:
        resolved.append(host)
        return ["127.0.0.1"] if host == "internal.example.test" else [PUBLIC_IP]

    downloader = ConferencePdfDownloader(
        allowed_hosts=("internal.example.test",),
        transport=httpx.MockTransport(handler),
        dns_resolver=resolver,
        downloader=http,
    )

    outcome = downloader.download(Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public"))

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    assert http.calls == []
    # 走到 DNS 校验才被拒（不是被 allowlist 挡的）：逐跳都做了公共地址检查
    assert resolved == ["doi.org", "internal.example.test"]


def test_every_hop_of_a_doi_redirect_chain_must_be_authorized():
    """中间跳也必须过 allowlist，不能只看最后一跳。"""
    http = FakeDownloader(result=_download_result("https://evil.example.test/x.pdf"))

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DOI_RESOLVER_URL:
            return _redirect("https://www.ndss-symposium.org/landing/2024-17")
        if str(request.url) == "https://www.ndss-symposium.org/landing/2024-17":
            return _redirect("https://evil.example.test/x.pdf")
        return _pdf_response()

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    assert http.calls == []


def test_doi_redirect_chain_is_bounded_by_max_redirects():
    seen: list[str] = []
    http = FakeDownloader(result=_download_result("https://www.ndss-symposium.org/loop.pdf"))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _redirect("https://www.ndss-symposium.org/loop.pdf")

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_BLOCKED
    assert len(seen) <= DEFAULT_MAX_REDIRECTS + 1
    assert http.calls == []


def test_doi_resolver_without_a_redirect_is_never_downloaded():
    """解析器直接返回 200（落地页）时，doi.org 本身不得被当作下载目标。"""
    http = FakeDownloader(result=_download_result(DOI_RESOLVER_URL))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>landing page</html>")

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == PDF_NOT_FOUND
    assert http.calls == []


def test_doi_resolution_network_failure_returns_a_stable_code():
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == PDF_NOT_FOUND
    assert http.calls == []


def test_doi_resolution_timeout_reuses_the_existing_timeout_code():
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    outcome = _doi_downloader(handler, downloader=http).download(
        Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public")
    )

    assert outcome.ok is False
    assert outcome.error_code == DOWNLOAD_TIMEOUT
    assert http.calls == []


def test_non_doi_urls_never_trigger_a_resolution_probe():
    http = FakeDownloader(result=_download_result("https://arxiv.org/pdf/1.pdf"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"非 DOI 地址不应触发解析探针：{request.url}")

    downloader = ConferencePdfDownloader(
        allowed_hosts=("arxiv.org",),
        transport=httpx.MockTransport(handler),
        downloader=http,
    )

    outcome = downloader.download(Record("10.1/a", "A", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public"))

    assert outcome.ok is True
    assert http.calls[0]["candidate"] == {"pdf_url": "https://arxiv.org/pdf/1.pdf"}


def test_doi_resolver_urls_still_skip_the_open_access_layer_without_an_allowlist():
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"空 allowlist 时不得发起解析探针：{request.url}")

    downloader = ConferencePdfDownloader(transport=httpx.MockTransport(handler), downloader=http)

    outcome = downloader.download(Record(NDSS_DOI, "T", pdf_url=DOI_RESOLVER_URL, pdf_access="public"))

    assert outcome.ok is False
    assert outcome.error_code == PDF_OPEN_ACCESS_SKIPPED
    assert http.calls == []


def test_download_batch_degrades_when_doi_resolution_is_rejected():
    """解析被拒只影响该条记录，不得中断整批（批任务「失败降级」语义）。"""
    http = FakeDownloader(result=_download_result(NDSS_PDF_URL))
    blocked_url = "https://doi.org/10.14722/ndss.2024.99999"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == DOI_RESOLVER_URL:
            return _redirect(NDSS_PDF_URL)
        if url == blocked_url:
            return _redirect("https://evil.example.test/x.pdf")
        return _pdf_response()

    result = _doi_downloader(handler, downloader=http).download_batch(
        (
            Record(NDSS_DOI, "Good", pdf_url=DOI_RESOLVER_URL, pdf_access="public"),
            Record("10.14722/ndss.2024.99999", "Bad", pdf_url=blocked_url, pdf_access="public"),
            Record("10.1/a", "Plain", pdf_url="https://arxiv.org/pdf/1.pdf", pdf_access="public"),
        )
    )

    assert result.total == 3
    assert result.ok_count == 2
    assert result.error_counts == {DOWNLOAD_BLOCKED: 1}
    assert [item.identity for item in result.failed] == ["doi:10.14722/ndss.2024.99999"]


def test_classify_pdf_access_still_routes_doi_resolver_urls_to_the_open_access_layer():
    """判定不变（既有测试已锁定）：doi.org 地址仍是 ``open_access``。"""
    record = {"doi": NDSS_DOI, "title": "T", "pdf_url": DOI_RESOLVER_URL}
    assert classify_pdf_access(record) == PDF_ACCESS_OPEN_ACCESS
    assert site_for_url(DOI_RESOLVER_URL) is None
