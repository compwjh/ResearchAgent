"""spec-032 Task 04：DOI 解析器地址（doi.org）在**入库路径**的复用测试。

背景（实测故障）：NDSS 记录经 OpenAlex 富化后 ``pdf_url`` 形如
``https://doi.org/10.14722/ndss.2024.24017``，它 302 到
``https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf``。
上一轮只在 ``ConferencePdfDownloader``（批量下载器）里修好了「doi.org 是跳转入口、
不是下载目标」；``import_candidate``（入库路径）仍然把 ``doi.org`` 原样交给
``download_candidate``，于是在 ``allowed_hosts=("www.ndss-symposium.org",)`` 下
100% ``DOWNLOAD_BLOCKED``。

本文件锁定四件事：

1. **只有一份实现**：解析逻辑在 ``infrastructure/doi_resolver.py``，批量下载器与入库路径
   引用**同一个函数对象**（不是复制粘贴），且两处交给下载链的最终地址一致。
2. **入库成功**：``doi.org`` → NDSS 官方主机、allowlist 只含最终主机时能入库。
3. **安全不削弱**：未授权主机（含中间跳）/ 内网地址 / 非 https / 带认证参数一律拒绝；
   重定向有上限；``doi.org`` 绝不进入下载 allowlist；没有「跳过校验」的开关。
4. **回归保护**：直连 URL（非 DOI 解析器地址）行为完全不变（零解析探针）。

全部用例用 fake transport（``httpx.MockTransport``）+ in-memory port 桩，不依赖真实网络。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import httpx
import pytest

from backend.app.core.url_security import DEFAULT_MAX_REDIRECTS
from backend.app.paper_discovery.application import paper_import as import_module
from backend.app.paper_discovery.application.paper_import import (
    PAPER_ALREADY_EXISTS,
    import_candidate,
)
from backend.app.paper_discovery.infrastructure import (
    conference_pdf_downloader as downloader_module,
)
from backend.app.paper_discovery.infrastructure import doi_resolver as resolver_module
from backend.app.paper_discovery.infrastructure.conference_pdf_downloader import (
    PDF_ACCESS_LAYER_OPEN_ACCESS,
    ConferencePdfDownloader,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    PDF_NOT_FOUND,
    DownloadResult,
    PaperDownloadError,
    download_candidate,
)
from backend.app.platform.ports import (
    ImportIndexStatus,
    PaperImportRequest,
)
from backend.app.platform.ports import (
    PaperImportResult as PortImportResult,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

PUBLIC_IP = "93.184.216.34"
DOI_URL = "https://doi.org/10.14722/ndss.2024.24017"
NDSS_PDF_URL = "https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf"
NDSS_LANDING_URL = "https://www.ndss-symposium.org/landing/2024-17"
NDSS_HOST = "www.ndss-symposium.org"
NDSS_DOI = "10.14722/ndss.2024.24017"
ARXIV_URL = "https://arxiv.org/pdf/2401.12345"
LOOP_URL = "https://www.ndss-symposium.org/loop.pdf"


# --- 夹具与替身 ---------------------------------------------------------------


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    """一页的真实 PDF：入库路径用**真实** ``download_candidate``，页码校验必须能过。"""
    import pymupdf

    document = pymupdf.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


def _pdf_response(pdf: bytes) -> httpx.Response:
    return httpx.Response(200, content=pdf, headers={"Content-Type": "application/pdf"})


def _redirect(to: str) -> httpx.Response:
    return httpx.Response(302, headers={"Location": to})


def _handler(routes: Mapping[str, Callable[[], httpx.Response]], seen: Optional[list[str]] = None) -> Callable:
    """按 URL 分发的 fake transport；未登记的地址一律 404。"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        build = routes.get(url)
        return build() if build is not None else httpx.Response(404, text="not found")

    return handler


def _ndss_routes(pdf: bytes, *, final_url: str = NDSS_PDF_URL) -> dict[str, Callable[[], httpx.Response]]:
    return {DOI_URL: lambda: _redirect(final_url), final_url: lambda: _pdf_response(pdf)}


@dataclass(frozen=True)
class DataclassCandidate:
    """属性式候选（真实调用链里 store 返回的候选就是这种形态）。"""

    doi: str = NDSS_DOI
    title: str = "Efficient and Timely Revocation of V2X Credentials"
    year: int = 2024
    conference_id: str = "ndss"
    article_url: str = NDSS_LANDING_URL
    pdf_url: str = DOI_URL


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "doi": NDSS_DOI,
        "title": "Efficient and Timely Revocation of V2X Credentials",
        "year": 2024,
        "conference_id": "ndss",
        "conference_name": "NDSS",
        "article_url": NDSS_LANDING_URL,
        "pdf_url": DOI_URL,
    }
    record.update(overrides)
    return record


class StubKbPort:
    """in-memory 知识库桩：记录每次入库请求，验证受信任路径与快照内容。

    与验收脚本一致：**在 ``import_paper`` 内**读取受信任文件（真实适配器会把它搬进知识库，
    ``import_candidate`` 随后会删掉本次 attempt 自建的临时根，事后按路径读文件必然 404）。
    """

    def __init__(self, *, existing: Optional[PortImportResult] = None) -> None:
        self.requests: list[PaperImportRequest] = []
        self.imports: list[dict[str, Any]] = []
        self._existing = existing
        self._names: set[str] = set()

    def find_existing(self, candidate_snapshot: Mapping[str, Any]) -> Optional[PortImportResult]:
        return self._existing

    def existing_names(self) -> set[str]:
        return set(self._names)

    def import_paper(self, request: PaperImportRequest) -> PortImportResult:
        path = Path(request.trusted_pdf_path)
        data = path.read_bytes() if path.is_file() else b""
        self._names.add(path.name)
        self.requests.append(request)
        self.imports.append(
            {
                "path": str(path),
                "size": len(data),
                "magic": data[:5],
                "sha256": hashlib.sha256(data).hexdigest() if data else None,
                "source_sha256": request.source_sha256,
                "snapshot": dict(request.candidate_snapshot),
            }
        )
        return PortImportResult(
            paper_id=f"stub-{len(self.requests)}",
            index_status=ImportIndexStatus.INDEXED,
            error_code=None,
            stored_name=path.name,
            source_sha256=hashlib.sha256(data).hexdigest() if data else None,
        )

    def compensate_import(self, capability: Any) -> str:
        return "cleanup_done"


def _import(
    record: Mapping[str, Any],
    hosts: Iterable[str],
    *,
    handler: Callable,
    port: StubKbPort,
    tmp_path: Path,
    dns_resolver: Optional[Callable[[str], list[str]]] = None,
    downloader: Callable[..., DownloadResult] = download_candidate,
) -> Any:
    return import_candidate(
        record,
        ArticleSettings(article_download_dir=str(tmp_path / "downloads")),
        hosts,
        transport=httpx.MockTransport(handler),
        dns_resolver=dns_resolver or (lambda _host: [PUBLIC_IP]),
        paper_import_port=port,
        downloader=downloader,
    )


# --- 1. 只有一份实现（两处调用共用） --------------------------------------------


def test_the_downloader_and_the_import_path_share_one_resolver_implementation():
    """禁止第二套实现：两处引用的必须是 ``doi_resolver`` 里的同一个对象。"""
    assert downloader_module.resolve_doi_url is resolver_module.resolve_doi_url
    assert import_module.resolve_doi_url is resolver_module.resolve_doi_url
    assert downloader_module.DOI_RESOLVER_HOSTS is resolver_module.DOI_RESOLVER_HOSTS


def test_the_resolver_host_set_stays_closed():
    """封闭集合：不接受调用方输入，也不含任何非解析器主机。"""
    hosts = set(resolver_module.DOI_RESOLVER_HOSTS)
    assert hosts == {"doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"}
    assert resolver_module.doi_resolver_host("https://doi.org/10.1/a") == "doi.org"
    assert resolver_module.doi_resolver_host("https://DOI.ORG/10.1/a") == "doi.org"
    assert resolver_module.doi_resolver_host(NDSS_PDF_URL) is None
    assert resolver_module.doi_resolver_host(None) is None
    assert resolver_module.doi_resolver_host("") is None


def test_both_call_sites_hand_the_same_resolved_url_to_the_download_chain(tmp_path: Path, pdf_bytes: bytes):
    """同一份数据 + 同一份 allowlist：批量下载器与入库路径解析出同一个最终地址。"""
    routes = _ndss_routes(pdf_bytes)
    captured: list[tuple[Any, tuple[str, ...]]] = []

    def recording_downloader(candidate: Any, settings: Any, allowed_hosts: Iterable[str], **_kwargs: Any) -> DownloadResult:
        captured.append((candidate, tuple(allowed_hosts)))
        path = tmp_path / f"captured-{len(captured)}.pdf"
        path.write_bytes(pdf_bytes)
        return DownloadResult(str(path), len(pdf_bytes), "0" * 64, NDSS_PDF_URL, 1)

    record = _record()
    downloader = ConferencePdfDownloader(
        allowed_hosts=(NDSS_HOST,),
        transport=httpx.MockTransport(_handler(routes)),
        dns_resolver=lambda _host: [PUBLIC_IP],
        downloader=recording_downloader,
    )
    outcome = downloader.download(record)
    assert outcome.ok is True
    assert outcome.layer == PDF_ACCESS_LAYER_OPEN_ACCESS
    assert outcome.url == NDSS_PDF_URL

    port = StubKbPort()
    _import(record, (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path, downloader=recording_downloader)

    assert len(captured) == 2
    urls = set()
    for candidate, allowed_hosts in captured:
        assert candidate["pdf_url"] == NDSS_PDF_URL
        assert allowed_hosts == (NDSS_HOST,)
        # doi.org 绝不因这次解析进入下载白名单
        assert not set(allowed_hosts) & set(resolver_module.DOI_RESOLVER_HOSTS)
        urls.add(candidate["pdf_url"])
    assert urls == {NDSS_PDF_URL}
    assert port.imports[0]["snapshot"]["pdf_url"] == NDSS_PDF_URL


def test_both_call_sites_reject_the_same_unauthorized_doi(tmp_path: Path, pdf_bytes: bytes):
    """失败路径也一致：同一份数据在批量下载器与入库路径得到同一个稳定错误码。"""
    routes = {DOI_URL: lambda: _redirect("https://evil.example.test/x.pdf")}
    port = StubKbPort()

    downloader = ConferencePdfDownloader(
        allowed_hosts=(NDSS_HOST,),
        transport=httpx.MockTransport(_handler(routes)),
        dns_resolver=lambda _host: [PUBLIC_IP],
        temp_dir=tmp_path,
    )
    outcome = downloader.download(_record())
    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert outcome.ok is False
    assert outcome.error_code == excinfo.value.code == DOWNLOAD_BLOCKED
    assert port.requests == []


# --- 2. 入库路径：(a) doi.org → 最终主机，allowlist 只含最终主机时入库成功 ---------

def test_import_resolves_a_doi_resolver_url_through_the_final_allowlisted_host(tmp_path: Path, pdf_bytes: bytes):
    """端到端（真实 ``download_candidate``）：``allowed_hosts`` 只声明最终主机也能入库。"""
    seen: list[str] = []
    port = StubKbPort()
    record = _record()

    result = _import(
        record, (NDSS_HOST,), handler=_handler(_ndss_routes(pdf_bytes), seen), port=port, tmp_path=tmp_path
    )

    assert result.status == ImportIndexStatus.INDEXED.value
    assert result.paper_id == "stub-1"
    assert result.error_code is None
    assert len(port.imports) == 1
    entry = port.imports[0]
    assert entry["magic"] == b"%PDF-"
    assert entry["size"] == len(pdf_bytes)
    assert entry["source_sha256"] == entry["sha256"]
    # 解析探针碰 doi.org 与最终主机；最终主机被请求两次（探针一次 + 真正下载一次）
    assert seen == [DOI_URL, NDSS_PDF_URL, NDSS_PDF_URL]
    # 调用方传入的记录不被就地改写
    assert record["pdf_url"] == DOI_URL


def test_import_snapshot_records_the_address_that_was_actually_downloaded(tmp_path: Path, pdf_bytes: bytes):
    """快照不得自相矛盾：``pdf_url`` 是**实际下载**的最终地址，原始解析器地址单独留痕。"""
    port = StubKbPort()

    _import(_record(), (NDSS_HOST,), handler=_handler(_ndss_routes(pdf_bytes)), port=port, tmp_path=tmp_path)

    snapshot = port.imports[0]["snapshot"]
    assert snapshot["pdf_url"] == NDSS_PDF_URL
    assert snapshot["pdf_url_original"] == DOI_URL
    # 其余候选字段原样保留（快照仍可用于身份判重）
    assert snapshot["doi"] == NDSS_DOI
    assert snapshot["article_url"] == NDSS_LANDING_URL


@pytest.mark.parametrize("host", ["doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"])
def test_every_doi_resolver_host_is_resolved_in_the_import_path(host: str, tmp_path: Path, pdf_bytes: bytes):
    url = f"https://{host}/{NDSS_DOI}"
    routes = {url: lambda: _redirect(NDSS_PDF_URL), NDSS_PDF_URL: lambda: _pdf_response(pdf_bytes)}
    port = StubKbPort()

    result = _import(_record(pdf_url=url), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert result.paper_id == "stub-1"
    assert port.imports[0]["snapshot"]["pdf_url"] == NDSS_PDF_URL


def test_import_resolves_the_doi_address_before_the_download_chain_runs(tmp_path: Path, pdf_bytes: bytes):
    """下载链收到的候选已经是**解析后**的地址（而不是 doi.org）。"""
    captured: list[Any] = []

    def recording_downloader(candidate: Any, settings: Any, allowed_hosts: Iterable[str], **_kwargs: Any) -> DownloadResult:
        captured.append(candidate)
        path = tmp_path / "resolved.pdf"
        path.write_bytes(pdf_bytes)
        return DownloadResult(str(path), len(pdf_bytes), "0" * 64, NDSS_PDF_URL, 1)

    port = StubKbPort()
    _import(
        _record(),
        (NDSS_HOST,),
        handler=_handler(_ndss_routes(pdf_bytes)),
        port=port,
        tmp_path=tmp_path,
        downloader=recording_downloader,
    )

    assert len(captured) == 1
    assert captured[0]["pdf_url"] == NDSS_PDF_URL


def test_import_preserves_the_candidate_shape_for_injected_downloaders(tmp_path: Path, pdf_bytes: bytes):
    """只换 ``pdf_url``：注入的 downloader 仍拿到原类型（dataclass），其余字段原样。"""
    captured: list[Any] = []

    def recording_downloader(candidate: Any, settings: Any, allowed_hosts: Iterable[str], **_kwargs: Any) -> DownloadResult:
        captured.append(candidate)
        path = tmp_path / "dataclass.pdf"
        path.write_bytes(pdf_bytes)
        return DownloadResult(str(path), len(pdf_bytes), "0" * 64, NDSS_PDF_URL, 1)

    port = StubKbPort()
    _import(
        DataclassCandidate(),
        (NDSS_HOST,),
        handler=_handler(_ndss_routes(pdf_bytes)),
        port=port,
        tmp_path=tmp_path,
        downloader=recording_downloader,
    )

    assert len(captured) == 1
    assert isinstance(captured[0], DataclassCandidate)
    assert captured[0].pdf_url == NDSS_PDF_URL
    assert captured[0].title == DataclassCandidate.title
    assert captured[0].doi == NDSS_DOI
    assert port.imports[0]["snapshot"]["pdf_url"] == NDSS_PDF_URL


# --- 3. 安全负例：不削弱上一轮的约束 --------------------------------------------


def test_import_rejects_a_doi_that_resolves_to_an_unauthorized_host(tmp_path: Path, pdf_bytes: bytes):
    """最终主机未授权 → 拒绝，且绝不进入下载链 / 知识库。"""
    routes = {
        DOI_URL: lambda: _redirect("https://evil.example.test/2024-17-paper.pdf"),
        "https://evil.example.test/2024-17-paper.pdf": lambda: _pdf_response(pdf_bytes),
    }
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert port.requests == []


def test_import_rejects_an_unauthorized_intermediate_hop(tmp_path: Path, pdf_bytes: bytes):
    """中间跳也必须过 allowlist：不能只看最后一跳。"""
    routes = {
        DOI_URL: lambda: _redirect(NDSS_LANDING_URL),
        NDSS_LANDING_URL: lambda: _redirect("https://evil.example.test/x.pdf"),
        "https://evil.example.test/x.pdf": lambda: _pdf_response(pdf_bytes),
    }
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert port.requests == []


def test_import_rejects_a_doi_that_resolves_to_a_private_address(tmp_path: Path, pdf_bytes: bytes):
    """主机虽在 allowlist 内，但解析到内网地址时必须拒绝（每跳都做公共地址检查）。"""
    resolved: list[str] = []
    routes = {
        DOI_URL: lambda: _redirect("https://internal.example.test/paper.pdf"),
        "https://internal.example.test/paper.pdf": lambda: _pdf_response(pdf_bytes),
    }
    port = StubKbPort()

    def resolver(host: str) -> list[str]:
        resolved.append(host)
        return ["127.0.0.1"] if host == "internal.example.test" else [PUBLIC_IP]

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(
            _record(),
            ("internal.example.test",),
            handler=_handler(routes),
            port=port,
            tmp_path=tmp_path,
            dns_resolver=resolver,
        )

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert port.requests == []
    # 走到 DNS 校验才被拒（不是被 allowlist 挡的）
    assert resolved == ["doi.org", "internal.example.test"]


def test_import_bounds_doi_redirect_chains(tmp_path: Path, pdf_bytes: bytes):
    seen: list[str] = []
    routes = {DOI_URL: lambda: _redirect(LOOP_URL), LOOP_URL: lambda: _redirect(LOOP_URL)}
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=_handler(routes, seen), port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert len(seen) <= DEFAULT_MAX_REDIRECTS + 1
    assert port.requests == []


@pytest.mark.parametrize(
    "url",
    [
        # 非 https：doi.org 也不能例外
        "http://doi.org/10.14722/ndss.2024.24017",
        # 带认证参数：解析入口同样要过 validate_url 的认证参数检查
        "https://doi.org/10.14722/ndss.2024.24017?access_token=secret",
        # 带 fragment / 用户信息
        "https://doi.org/10.14722/ndss.2024.24017#frag",
        "https://user:pass@doi.org/10.14722/ndss.2024.24017",
    ],
)
def test_import_applies_url_security_to_the_resolver_entry_hop(url: str, tmp_path: Path, pdf_bytes: bytes):
    """解析入口那一跳仍走 ``validate_url``：协议/认证参数/fragment/用户信息一律拒绝。"""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 不应被调用
        raise AssertionError(f"非法入口地址不得发起请求：{request.url}")

    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(pdf_url=url), (NDSS_HOST,), handler=handler, port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert port.requests == []


def test_import_never_downloads_the_resolver_itself(tmp_path: Path, pdf_bytes: bytes):
    """解析器直接返回 200（落地页）时，``doi.org`` 不得被当作下载目标。"""
    routes = {DOI_URL: lambda: httpx.Response(200, text="<html>landing page</html>")}
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert excinfo.value.code == PDF_NOT_FOUND
    assert port.requests == []


def test_import_skips_doi_resolution_without_an_allowlist(tmp_path: Path, pdf_bytes: bytes):
    """空 allowlist：fail-closed，且不做无谓的解析探针（与批量下载器一致）。"""
    seen: list[str] = []
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (), handler=_handler(_ndss_routes(pdf_bytes), seen), port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_BLOCKED
    assert seen == []
    assert port.requests == []


def test_import_returns_a_stable_code_when_doi_resolution_fails(tmp_path: Path):
    """网络失败 → 稳定错误码，不抛裸异常。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=handler, port=port, tmp_path=tmp_path)

    assert excinfo.value.code == PDF_NOT_FOUND
    assert port.requests == []


def test_import_maps_a_doi_resolution_timeout_to_the_existing_code(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(_record(), (NDSS_HOST,), handler=handler, port=port, tmp_path=tmp_path)

    assert excinfo.value.code == DOWNLOAD_TIMEOUT
    assert port.requests == []


# --- 4. 回归保护：(d) 直连 URL 行为不变 + 幂等/清理语义保留 -----------------------


def test_import_keeps_direct_pdf_urls_unchanged(tmp_path: Path, pdf_bytes: bytes):
    """非 DOI 解析器地址：零解析探针，快照不带解析留痕。"""
    seen: list[str] = []
    routes = {ARXIV_URL: lambda: _pdf_response(pdf_bytes)}
    port = StubKbPort()

    result = _import(
        _record(pdf_url=ARXIV_URL),
        ("arxiv.org",),
        handler=_handler(routes, seen),
        port=port,
        tmp_path=tmp_path,
    )

    assert result.paper_id == "stub-1"
    assert seen == [ARXIV_URL]
    snapshot = port.imports[0]["snapshot"]
    assert snapshot["pdf_url"] == ARXIV_URL
    assert "pdf_url_original" not in snapshot


def test_import_skips_resolution_for_a_candidate_without_a_pdf_url(tmp_path: Path):
    seen: list[str] = []
    port = StubKbPort()

    with pytest.raises(PaperDownloadError) as excinfo:
        _import(
            _record(pdf_url=None),
            (NDSS_HOST,),
            handler=_handler({}, seen),
            port=port,
            tmp_path=tmp_path,
        )

    assert excinfo.value.code == PDF_NOT_FOUND
    assert seen == []
    assert port.requests == []


def test_import_still_short_circuits_on_an_existing_paper_before_any_network(tmp_path: Path, pdf_bytes: bytes):
    """幂等语义保留：已存在时既不做解析探针也不下载。"""
    seen: list[str] = []
    port = StubKbPort(
        existing=PortImportResult(
            paper_id="existing-1",
            index_status=ImportIndexStatus.INDEXED,
            error_code=None,
            stored_name="2024-NDSS-x.pdf",
            existing=True,
        )
    )

    result = _import(
        _record(), (NDSS_HOST,), handler=_handler(_ndss_routes(pdf_bytes), seen), port=port, tmp_path=tmp_path
    )

    assert result.existing is True
    assert result.error_code == PAPER_ALREADY_EXISTS
    assert seen == []
    assert port.requests == []


def test_import_removes_its_own_temp_root_after_a_rejected_doi(tmp_path: Path, pdf_bytes: bytes):
    """解析被拒时仍要清掉本次 attempt 自建的临时根（不破坏既有清理语义）。"""
    routes = {DOI_URL: lambda: _redirect("https://evil.example.test/x.pdf")}
    port = StubKbPort()
    download_base = tmp_path / "downloads"

    with pytest.raises(PaperDownloadError):
        _import(_record(), (NDSS_HOST,), handler=_handler(routes), port=port, tmp_path=tmp_path)

    assert not [item for item in download_base.iterdir() if item.name.startswith("paper-import-")]
