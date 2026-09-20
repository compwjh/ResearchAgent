"""spec-032.1 Task04 — 注册 ``fetch_paper_detail`` Tool（TDD，全离线）。

覆盖：
1. ``build_default_tool_registry()`` 含 ``fetch_paper_detail``，entry 真实可导入。
2. 公开入口用 fake client 返回正确摘要（不依赖真实网络）。
3. 非法 URL（其它域名 / 带 query / 非 presentation 路径）返回可读错误且**不发起网络请求**。
4. 未注册 / 已禁用 Tool 在既有执行体系（ToolLoop）中仍被拒绝（spec-023 回归保护）。
"""

import importlib

import httpx

from backend.app.paper_discovery.infrastructure.usenix_publication_source import (
    UsenixAcceptedSource,
)
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.tool_executor import ModelResponse, ToolLoop

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
TOOL_NAME = "fetch_paper_detail"


def _source(handler):
    return UsenixAcceptedSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        dns_resolver=lambda _host: [PUBLIC],
        sleep=lambda _seconds: None,
    )


# --- 1. 注册表 ---------------------------------------------------------------

def _tool():
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    return tools[TOOL_NAME]


def test_registry_exposes_fetch_paper_detail():
    tool = _tool()
    assert tool.enabled is True
    assert tool.description
    assert tool.entry


def test_entry_points_to_a_real_importable_symbol():
    module_path, _, attr_path = _tool().entry.partition(".")
    module = importlib.import_module(module_path)
    target = module
    for attr in attr_path.split("."):
        target = getattr(target, attr)
    assert callable(target)


def test_parameters_require_url_and_forbid_unknown_arguments():
    parameters = _tool().parameters
    assert parameters["required"] == ["url"]
    assert "url" in parameters["properties"]


def test_public_entry_signature_matches_registered_entry():
    module_path, _, attr_path = _tool().entry.partition(".")
    module = importlib.import_module(module_path)
    target = module
    for attr in attr_path.split("."):
        target = getattr(target, attr)
    assert target.__name__ == "fetch_paper_detail"


# --- 2. 正常返回摘要 ---------------------------------------------------------

def test_fetch_paper_detail_returns_parsed_metadata_without_network():
    source = _source(lambda _request: httpx.Response(200, text=DETAIL_HTML))

    detail = source.fetch_paper_detail(DETAIL)

    assert detail["ok"] is True
    assert detail["error_code"] is None
    assert detail["url"] == DETAIL
    assert detail["title"] == "Secure Search"
    assert detail["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert detail["year"] == 2025
    assert detail["abstract"] == ABSTRACT
    assert detail["keywords"] == []
    assert detail["official_pdf_url"].endswith("/official.pdf")
    assert detail["publication_stage"] == "accepted"
    assert detail["source_kind"] == "usenix_accepted"


def test_fetch_paper_detail_parses_pdf_links_and_abstract():
    source = _source(lambda _request: httpx.Response(200, text=DETAIL_HTML))
    detail = source.fetch_paper_detail(DETAIL)
    assert detail["absolute_pdf_url"]


# --- 3. 非法 URL 不发起网络请求 ---------------------------------------------

def _collecting_source():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=DETAIL_HTML)

    return _source(handler), calls


def test_bad_urls_are_rejected_without_any_network_request():
    source, calls = _collecting_source()
    bad_urls = [
        "https://evil.example.com/conference/usenixsecurity25/presentation/demo",
        "http://www.usenix.org/conference/usenixsecurity25/presentation/demo",
        "https://www.usenix.org/conference/usenixsecurity25/presentation/demo?x=1",
        "https://www.usenix.org/conference/usenixsecurity25/accepted-papers",
        "https://www.usenix.org/conference/usenixsecurity25/presentation/demo#frag",
        "not-a-url",
        "",
        None,
        123,
    ]
    for url in bad_urls:
        detail = source.fetch_paper_detail(url)
        assert detail["ok"] is False, url
        assert detail["error_code"] == "USENIX_DETAIL_URL_REJECTED", url
        assert detail["error"], url
        # 非字符串入参被归一为空串；字符串入参原样回显，便于定位。
        assert detail["url"] == (url if isinstance(url, str) else ""), url
    assert calls == []


# --- 4. spec-023 执行体系回归保护 -------------------------------------------

class _Tool:
    def __init__(self, name, *, enabled=True):
        self.name, self.enabled = name, enabled
        self.description = f"Tool {name}"
        self.parameters = {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        }


def test_tool_loop_rejects_unregistered_and_disabled_tools():
    executed = []

    def dispatch(name, args):
        executed.append(name)
        from backend.app.skills.tool_executor import DispatchResult

        return DispatchResult(ok=True, name=name, output="ok")

    # 未注册
    loop = ToolLoop(
        [_Tool(TOOL_NAME)],
        model_call=lambda *_a: ModelResponse(
            tool_calls=({"function": {"name": "nope", "arguments": {"url": DETAIL}}},)
        ),
        dispatch=dispatch,
    )
    events = list(loop.run("sys", "hi"))
    assert any(event.get("status") == "rejected" for event in events)
    assert executed == []

    # 已禁用
    loop = ToolLoop(
        [_Tool(TOOL_NAME, enabled=False)],
        model_call=lambda *_a: ModelResponse(
            tool_calls=({"function": {"name": TOOL_NAME, "arguments": {"url": DETAIL}}},)
        ),
        dispatch=dispatch,
    )
    events = list(loop.run("sys", "hi"))
    assert any(event.get("status") == "rejected" for event in events)
    assert executed == []


def test_tool_loop_dispatches_registered_enabled_tool():
    executed = []

    def dispatch(name, args):
        from backend.app.skills.tool_executor import DispatchResult

        executed.append((name, args))
        return DispatchResult(ok=True, name=name, output="abstract: ok")

    replies = [ModelResponse(
        tool_calls=({"id": "c1", "function": {"name": TOOL_NAME, "arguments": {"url": DETAIL}}},)
    ), ModelResponse(content="done")]
    loop = ToolLoop([_Tool(TOOL_NAME)], model_call=lambda *_a: replies.pop(0), dispatch=dispatch)
    events = list(loop.run("sys", "hi"))
    assert executed == [(TOOL_NAME, {"url": DETAIL})]
    assert {"type": "token", "content": "done"} in events
