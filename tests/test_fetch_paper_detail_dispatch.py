"""spec-032.1 Task04 收尾 — 把 ``fetch_paper_detail`` 接入 ``build_default_dispatch``（TDD，全离线）。

背景：Task04 已在 registry 注册该 Tool、并在 ``UsenixAcceptedSource`` 上有公开入口
``fetch_paper_detail(url)``，但 ``tool_dispatch._ADAPTERS`` 未接线，模型真调用时只会拿到
「未找到工具「fetch_paper_detail」的执行器。」。本测试锁定适配器行为：

1. 合法 URL：复用既有公开入口，``ok=True`` 且 ``output`` 含摘要（fake client 注入，不触网）。
2. 非法 URL（其它域名 / 带 query / 非 presentation 路径）：``ok=False`` 且**不发起网络请求**。
3. 缺少 url 参数：``ok=False`` 且返回可读错误，不抛异常。
4. 未知工具名仍返回既有降级错误（回归保护）。
5. 摘要缺失时如实说明，不编造。
"""

import httpx
import pytest

from backend.app.skills.tool_dispatch import build_default_dispatch

TOOL = "fetch_paper_detail"
PUBLIC = "93.184.216.34"
DETAIL = "https://www.usenix.org/conference/usenixsecurity25/presentation/demo"
DETAIL_HTML = (
    '<meta name="citation_title" content="Secure Search">'
    '<meta name="citation_author" content="Ada Lovelace">'
    '<meta name="citation_author" content="Grace Hopper">'
    '<meta name="citation_publication_date" content="2025-01-01">'
    '<a href="/conference/usenixsecurity25/presentation/demo/official.pdf">PDF</a>'
    '<div class="field-name-field-paper-description"><p>'
    "We study collaborative perception under partial observability."
    "</p></div>"
)
ABSTRACT = "We study collaborative perception under partial observability."

# 非空但非法的 URL：统一由既有白名单拒绝，错误码为 USENIX_DETAIL_URL_REJECTED。
BAD_URLS = [
    "https://evil.example.com/conference/usenixsecurity25/presentation/demo",
    "http://www.usenix.org/conference/usenixsecurity25/presentation/demo",
    "https://www.usenix.org/conference/usenixsecurity25/presentation/demo?x=1",
    "https://www.usenix.org/conference/usenixsecurity25/presentation/demo#frag",
    "https://www.usenix.org/conference/usenixsecurity25/accepted-papers",
    "not-a-url",
]


def _fake_source_factory(html=DETAIL_HTML):
    """返回 ``(patch 回调, 触网 URL 列表)``。

    适配器内部用 ``UsenixAcceptedSource().fetch_paper_detail(url)``，因此把**类方法**换成
    一个用注入 MockTransport 的实例来执行的原函数最稳妥：既不递归（类本身不被替换），
    又让全部白名单 / 限速 / 解析逻辑仍然走真实实现。任何真实请求都不会发生。
    """
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=html)

    def patch(monkeypatch):
        from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
            UsenixAcceptedSource,
        )

        # 先抓住**未打补丁**的原函数，再以「假实例」为 self 调用它，
        # 避免在替身内部再次解析到被补丁后的类属性（会无限递归）。
        original = UsenixAcceptedSource.fetch_paper_detail

        def _fake(self, url):  # noqa: ANN001 - 测试替身
            fake = UsenixAcceptedSource(
                client=httpx.Client(transport=httpx.MockTransport(handler)),
                dns_resolver=lambda _host: [PUBLIC],
                sleep=lambda _seconds: None,
            )
            return original(fake, url)

        monkeypatch.setattr(UsenixAcceptedSource, "fetch_paper_detail", _fake)

    return patch, calls


# --- 1. 合法 URL 走通：ok=True 且 output 含摘要 -------------------------------

def test_valid_url_returns_ok_and_abstract(monkeypatch):
    patch, calls = _fake_source_factory()
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": DETAIL})

    assert result.ok is True, result.error
    assert result.name == TOOL
    assert ABSTRACT in result.output
    assert "Secure Search" in result.output
    assert calls == [DETAIL], "只应请求一次详情页"


def test_output_reports_title_authors_year(monkeypatch):
    patch, _calls = _fake_source_factory()
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": DETAIL})

    assert result.ok is True, result.error
    assert "Secure Search" in result.output
    assert "Ada Lovelace" in result.output
    assert "Grace Hopper" in result.output
    assert "2025" in result.output


def test_missing_abstract_is_stated_not_fabricated(monkeypatch):
    # 详情页没有摘要 -> 如实说明，绝不留空也无中生有
    html = (
        '<meta name="citation_title" content="No Abstract Paper">'
        '<meta name="citation_author" content="Ada Lovelace">'
        '<meta name="citation_publication_date" content="2025-01-01">'
    )
    patch, _calls = _fake_source_factory(html=html)
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": DETAIL})

    assert result.ok is True, result.error
    assert "No Abstract Paper" in result.output
    assert "未" in result.output or "无" in result.output


def test_parser_failure_is_readable_error(monkeypatch):
    # 无 citation_title 时 parse_usenix_detail 抛错 -> 适配器返回可读错误，不冒泡
    patch, _calls = _fake_source_factory(html="<html>junk</html>")
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": DETAIL})

    if result.ok:  # 解析器若容忍该 HTML，则退化为「摘要缺失」的可读文本
        assert "junk" not in result.output
    else:
        assert "USENIX_PARSE_FAILED" in result.error
    assert isinstance(result.output, str)
    assert isinstance(result.error, str)


# --- 2. 非法 URL：ok=False 且不触网 ------------------------------------------

def test_bad_urls_rejected_without_network(monkeypatch):
    patch, calls = _fake_source_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    for url in BAD_URLS:
        result = dispatch(TOOL, {"url": url})
        assert result.ok is False, url
        assert result.name == TOOL
        assert result.error, url
        assert "USENIX_DETAIL_URL_REJECTED" in result.error, url

    assert calls == [], "非法 URL 不得发起任何网络请求"


def test_blank_url_rejected_without_network(monkeypatch):
    # 空串按「缺参数」处理（也更易读），同样 ok=False 且不触网。
    patch, calls = _fake_source_factory()
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": ""})

    assert result.ok is False
    assert result.error
    assert calls == []


def test_non_string_url_rejected_without_network(monkeypatch):
    patch, calls = _fake_source_factory()
    patch(monkeypatch)

    result = build_default_dispatch()(TOOL, {"url": 123})

    assert result.ok is False
    assert result.error
    assert calls == []


# --- 3. 缺少 url 参数 --------------------------------------------------------

def test_missing_url_is_readable_error_not_exception(monkeypatch):
    patch, calls = _fake_source_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    for args in ({}, {"url": None}, {"url": "   "}):
        result = dispatch(TOOL, args)
        assert result.ok is False, args
        assert result.name == TOOL
        assert result.error, args
        assert "url" in result.error, args

    assert calls == [], "缺参数不得触网"


def test_empty_args_does_not_raise():
    # 不 patch 也要保证「不触网」：参数校验先于构造来源，缺参直接返回
    result = build_default_dispatch()(TOOL, {})
    assert result.ok is False
    assert result.error


# --- 4. 未知工具名仍走既有降级（回归保护） -----------------------------------

def test_unknown_tool_keeps_existing_fallback_error():
    result = build_default_dispatch()("no_such_tool", {})
    assert result.ok is False
    assert "no_such_tool" in result.error


def test_registered_tool_no_longer_reports_missing_executor():
    result = build_default_dispatch()(TOOL, {})
    assert "未找到工具" not in result.error


# --- spec-032.1 MEDIUM-2: the adapter must reuse ONE source instance ----------
#
# ``_fetch_paper_detail`` used to build a ``UsenixAcceptedSource()`` per call, so
# the rate-limit state (``_next_request_at``) and the text cache (``self._cache``)
# were thrown away each time: three calls meant three live requests and an empty
# sleep log.  These tests assert the observable consequences - a shared instance
# keeps the limiter and the cache alive across Tool calls.

@pytest.fixture(autouse=True)
def _reset_usenix_singleton():
    """Every test starts from a fresh process-wide source.

    The singleton is deliberately process-wide in production, so the tests must
    reset it explicitly; otherwise the first test's instance leaks into the rest
    and the counting ``__init__`` patch is never applied again.
    """
    import backend.app.skills.tool_dispatch as tool_dispatch

    tool_dispatch._usenix_source = None
    yield
    tool_dispatch._usenix_source = None


def _counting_factory():
    """Install a counting source factory; returns (patch, requests, sleeps, sources)."""
    requests, sleeps, sources = [], [], []

    def patch(monkeypatch):
        from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
            UsenixAcceptedSource,
        )

        original_init = UsenixAcceptedSource.__init__

        def _init(self, *args, **kwargs):  # noqa: ANN001 - 测试替身
            kwargs.setdefault("client", httpx.Client(
                transport=httpx.MockTransport(_handler(requests))))
            kwargs.setdefault("dns_resolver", lambda _host: [PUBLIC])

            def _sleep(seconds):
                sleeps.append(seconds)

            kwargs.setdefault("sleep", _sleep)
            original_init(self, *args, **kwargs)
            sources.append(self)

        monkeypatch.setattr(UsenixAcceptedSource, "__init__", _init)

    return patch, requests, sleeps, sources


def _handler(requests):
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text=DETAIL_HTML)

    return handler


def test_repeated_tool_calls_reuse_one_source_instance(monkeypatch):
    patch, _requests, _sleeps, sources = _counting_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    for _ in range(3):
        assert dispatch(TOOL, {"url": DETAIL}).ok is True

    assert len(sources) == 1, "多次 Tool 调用必须复用同一实例（限流/缓存才有状态）"


def test_rate_limit_survives_across_tool_calls(monkeypatch):
    patch, requests, sleeps, _sources = _counting_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    # Three DIFFERENT presentation pages so the cache cannot mask the limiter.
    urls = [DETAIL, DETAIL.replace("/demo", "/demo2"), DETAIL.replace("/demo", "/demo3")]
    for url in urls:
        assert dispatch(TOOL, {"url": url}).ok is True

    assert len(requests) == 3, requests
    # A fresh instance per call resets ``_next_request_at``, which makes every
    # wait zero and leaves the sleep log EMPTY - the review's exact symptom.
    assert sleeps and any(seconds > 0 for seconds in sleeps), (
        "跨 Tool 调用的限流必须真实生效（sleep 记录非空）")


def test_same_url_second_tool_call_is_served_from_cache(monkeypatch):
    patch, requests, _sleeps, _sources = _counting_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    assert dispatch(TOOL, {"url": DETAIL}).ok is True
    assert dispatch(TOOL, {"url": DETAIL}).ok is True

    assert requests == [DETAIL], (
        "同一 URL 第二次调用必须命中实例缓存，不再发起请求")


def test_cached_second_call_still_returns_the_parsed_metadata(monkeypatch):
    patch, _requests, _sleeps, _sources = _counting_factory()
    patch(monkeypatch)

    dispatch = build_default_dispatch()
    dispatch(TOOL, {"url": DETAIL})
    result = dispatch(TOOL, {"url": DETAIL})

    assert result.ok is True, result.error
    assert ABSTRACT in result.output
    assert "Secure Search" in result.output
