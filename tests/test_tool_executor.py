"""spec-023 Task07 — Tool 执行编排器（原生 function calling 优先 + 计划 JSON 降级）单元测试。

TDD：先写测试覆盖所有硬边界（来自 task 约束与 RESULT.md R1/R4），再实现 tool_executor。

覆盖边界：
- schema 生成：name/description/parameters(含 required) 正确
- 原生路径 A：模型返回 tool_calls -> 校验 -> 执行 -> 回灌 -> 合成最终回答
- 未注册 / 已禁用 / 参数非法 / 缺必填 / 未知参数 -> 拒绝执行，返回可读错误，不猜着执行
- 降级路径 B：原生不可用（无 tool_calls）-> 解析受控计划 JSON -> 校验 -> 执行
- 两条路径都失败 / 超时 -> 降级为不执行，对话照常继续
- 达到最大轮次 -> 停止并产出当前结果（不无限编排）
- 普通提问（无工具 / 模型直接回答）-> 不进入 Tool 执行
- dispatch 抛异常 -> 降级为错误结果回灌，不中断
"""

import unittest
from typing import List
from unittest.mock import patch

from backend.app.skills.models import ToolEntry
from backend.app.skills.tool_dispatch import build_default_dispatch
from backend.app.skills.tool_executor import (
    DispatchResult,
    ModelResponse,
    ToolLoop,
    build_tool_schema,
    build_tool_schemas,
)


def _tool(name, enabled=True, parameters=None, entry="mod.fn"):
    return ToolEntry(
        name=name,
        description=f"desc of {name}",
        enabled=enabled,
        entry=entry,
        parameters=parameters
        or {"type": "object", "properties": {}, "required": []},
    )


def _search_tool():
    return _tool(
        "search_paper_catalog",
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["usenix", "dblp", "all"]},
                "query": {"type": "string"},
                "years": {"type": "array", "items": {"type": "integer"}},
                "limit": {"type": "integer"},
            },
            "required": ["source", "query"],
        },
    )


def _kb_tool():
    return _tool(
        "kb_search",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["question"],
        },
    )


class _Recorder:
    """可注入的假模型调用 / 假 dispatch，记录调用并回放预设响应。"""

    def __init__(self, responses: List[ModelResponse], *, raise_on_call=None):
        self._responses = list(responses)
        self._idx = 0
        self._raise = raise_on_call
        self.model_calls = []  # [(messages, tools)]
        self.dispatch_calls = []  # [(name, args)]

    def model_call(self, messages, tools):
        self.model_calls.append((messages, tools))
        if self._raise is not None:
            raise self._raise
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        # 默认：空响应（相当于“无工具调用、无内容”）
        return ModelResponse(content="", tool_calls=[])

    def dispatch(self, name, args):
        self.dispatch_calls.append((name, args))
        # 默认成功：回显
        return DispatchResult(ok=True, name=name, output=f"result-for-{name}")


def _run(loop: ToolLoop) -> List[dict]:
    return list(loop.run(system_prompt="SYS", user_question="Q"))


class ToolSchemaTests(unittest.TestCase):
    def test_schema_shape(self):
        schema = build_tool_schema(_search_tool())
        self.assertEqual(schema["type"], "function")
        fn = schema["function"]
        self.assertEqual(fn["name"], "search_paper_catalog")
        self.assertIn("desc of search_paper_catalog", fn["description"])
        self.assertEqual(fn["parameters"]["required"], ["source", "query"])

    def test_schemas_filter_enabled(self):
        tools = [_search_tool(), _kb_tool()]
        schemas = build_tool_schemas(tools)
        names = {s["function"]["name"] for s in schemas}
        self.assertEqual(names, {"search_paper_catalog", "kb_search"})


class NativePathTests(unittest.TestCase):
    def test_native_executes_then_synthesizes(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}],
                ),
                ModelResponse(content="最终回答", tool_calls=[]),
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        # 最终回答以 token 流出
        self.assertIn({"type": "token", "content": "最终回答"}, events)
        # dispatch 被调用一次，参数原样传入
        self.assertEqual(rec.dispatch_calls, [("kb_search", {"question": "x"})])
        # 每轮都带 schema（让模型可继续调用工具），最终回答轮也不例外
        self.assertIsNotNone(rec.model_calls[0][1])
        self.assertIsNotNone(rec.model_calls[1][1])
        self.assertEqual(len(rec.model_calls), 2)

    def test_native_takes_precedence_over_plan_json(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content='ignored plan {"tool":"kb_search","args":{}}',
                    tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}],
                ),
                ModelResponse(content="ok", tool_calls=[]),
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        _run(loop)
        # 只按原生路径执行一次，不重复解析计划 JSON
        self.assertEqual(rec.dispatch_calls, [("kb_search", {"question": "x"})])


class RejectionTests(unittest.TestCase):
    def test_unregistered_tool_rejected(self):
        rec = _Recorder(
            [ModelResponse(content="", tool_calls=[{"name": "ghost_tool", "arguments": {}}])]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        # dispatch 绝不被调用
        self.assertEqual(rec.dispatch_calls, [])
        # 输出可读错误
        err = [e for e in events if e["type"] == "token"]
        self.assertTrue(err)
        self.assertIn("ghost_tool", err[-1]["content"])
        self.assertIn("不存在", err[-1]["content"])

    def test_disabled_tool_rejected(self):
        rec = _Recorder(
            [ModelResponse(content="", tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}])]
        )
        loop = ToolLoop(
            tools=[_tool("kb_search", enabled=False)],
            model_call=rec.model_call,
            dispatch=rec.dispatch,
        )
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        self.assertIn("已禁用", events[-1]["content"])

    def test_missing_required_arg_rejected(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[{"name": "search_paper_catalog", "arguments": {"limit": 5}}],
                )
            ]
        )
        loop = ToolLoop(tools=[_search_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        self.assertIn("参数", events[-1]["content"])

    def test_unknown_arg_rejected(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[
                        {"name": "kb_search", "arguments": {"question": "x", "evil": "rm -rf"}}
                    ],
                )
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        self.assertIn("参数", events[-1]["content"])


class FallbackPlanJsonTests(unittest.TestCase):
    def test_fallback_plan_json_executes(self):
        rec = _Recorder(
            [
                ModelResponse(content='{"tool":"kb_search","args":{"question":"x"}}', tool_calls=[]),
                ModelResponse(content="合成回答", tool_calls=[]),
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [("kb_search", {"question": "x"})])
        self.assertIn({"type": "token", "content": "合成回答"}, events)

    def test_fallback_unknown_tool_rejected(self):
        rec = _Recorder(
            [ModelResponse(content='{"tool":"ghost_tool","args":{}}', tool_calls=[])]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        self.assertIn("ghost_tool", events[-1]["content"])

    def test_both_paths_fail_degrade_to_normal_answer(self):
        # 模型只给了普通文本，无 tool_calls、无计划 JSON -> 直接作为最终回答，不执行
        rec = _Recorder([ModelResponse(content="我帮不了这个", tool_calls=[])])
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        self.assertEqual(events, [{"type": "token", "content": "我帮不了这个"}])


class RoundLimitTests(unittest.TestCase):
    def test_max_rounds_stops(self):
        # 模型每轮都返回 tool_calls（无限编排），应在 max_rounds 后停止并合成
        endless = ModelResponse(
            content="", tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}]
        )
        rec = _Recorder([endless, endless, endless, ModelResponse(content="收尾", tool_calls=[])])
        loop = ToolLoop(
            tools=[_kb_tool()],
            model_call=rec.model_call,
            dispatch=rec.dispatch,
            max_rounds=3,
        )
        events = _run(loop)
        # 最多执行 max_rounds 次工具
        self.assertEqual(len(rec.dispatch_calls), 3)
        # 触发了一次无 schema 的收尾合成
        self.assertIn({"type": "token", "content": "收尾"}, events)


class PlainAndDegradeTests(unittest.TestCase):
    def test_no_tools_no_execution(self):
        rec = _Recorder([ModelResponse(content="直接回答", tool_calls=[])])
        loop = ToolLoop(tools=[], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [])
        # 没有工具时，请求不带 schema
        self.assertIsNone(rec.model_calls[0][1])
        self.assertEqual(events, [{"type": "token", "content": "直接回答"}])

    def test_dispatch_exception_degrades(self):
        def boom(name, args):
            raise RuntimeError("boom")

        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}],
                ),
                ModelResponse(content="还是给了回答", tool_calls=[]),
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=boom)
        events = _run(loop)
        # 不抛异常，最终仍产出回答
        self.assertIn({"type": "token", "content": "还是给了回答"}, events)

    def test_model_call_failure_degrades(self):
        import httpx

        rec = _Recorder([], raise_on_call=httpx.ReadTimeout("timeout"))
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        _run(loop)
        # 超时降级为不执行，对话照常结束（空内容也算正常结束）
        self.assertEqual(rec.dispatch_calls, [])


class MultiToolCallMessageTests(unittest.TestCase):
    """B2（spec-023.1）：一次响应的多个 tool_calls 必须聚合成单条 assistant 消息。

    现状缺陷：循环内每个 tc 都调 _append_tool_turn，每次追加单条 assistant 消息，
    导致 2 个 tool_calls -> 2 条 assistant 消息且 content 重复写入，污染后续上下文。
    """

    def test_two_tool_calls_append_single_assistant_message(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content="我先并行查两个动作",
                    tool_calls=[
                        {"id": "c1", "name": "kb_search", "arguments": {"question": "a"}},
                        {"id": "c2", "name": "kb_ask", "arguments": {"question": "b"}},
                    ],
                ),
                ModelResponse(content="最终回答", tool_calls=[]),
            ]
        )
        loop = ToolLoop(
            tools=[_kb_tool(), _tool("kb_ask", parameters={"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]})],
            model_call=rec.model_call,
            dispatch=rec.dispatch,
        )
        _run(loop)

        # 第二轮模型调用看到的 messages = [system, user, assistant, tool, tool]
        messages = rec.model_calls[1][0]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_messages), 1, "多个 tool_calls 只能产生 1 条 assistant 消息")
        assistant = assistant_messages[0]
        self.assertEqual(len(assistant["tool_calls"]), 2)
        # content 只写一次（不再按 tc 数重复）
        self.assertEqual(assistant["content"], "我先并行查两个动作")
        # 每个 tool_call 有配对的 role="tool" 消息，顺序与 id 严格一致
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 2)
        self.assertEqual(
            [m["tool_call_id"] for m in tool_messages],
            [tc["id"] for tc in assistant["tool_calls"]],
        )
        # 模型给出的 id 唯一且被保留（不重复、不丢失）
        self.assertEqual(len({tc["id"] for tc in assistant["tool_calls"]}), 2)

    def test_two_tool_calls_both_dispatched_in_order(self):
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[
                        {"id": "c1", "name": "kb_search", "arguments": {"question": "a"}},
                        {"id": "c2", "name": "kb_ask", "arguments": {"question": "b"}},
                    ],
                ),
                ModelResponse(content="最终回答", tool_calls=[]),
            ]
        )
        loop = ToolLoop(
            tools=[
                _kb_tool(),
                _tool("kb_ask", parameters={"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}),
            ],
            model_call=rec.model_call,
            dispatch=rec.dispatch,
        )
        _run(loop)
        self.assertEqual(rec.dispatch_calls, [("kb_search", {"question": "a"}), ("kb_ask", {"question": "b"})])

    def test_invalid_tool_call_rejects_whole_batch_no_partial_execution(self):
        # 边界：批内任一 tool_call 非法 -> 整轮拒绝，一个都不执行（不产生「部分执行 + 半截消息」）
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[
                        {"id": "c1", "name": "kb_search", "arguments": {"question": "a"}},
                        {"id": "c2", "name": "ghost_tool", "arguments": {}},
                    ],
                ),
            ]
        )
        loop = ToolLoop(tools=[_kb_tool()], model_call=rec.model_call, dispatch=rec.dispatch)
        events = _run(loop)
        self.assertEqual(rec.dispatch_calls, [], "批内非法时不得执行任何工具")
        self.assertIn("ghost_tool", [e.get("content", "") for e in events if e["type"] == "token"][-1])

    def test_missing_tool_call_id_is_generated_and_paired(self):
        # 模型未给 id 时必须生成，且 assistant/tool 两侧 id 严格配对
        rec = _Recorder(
            [
                ModelResponse(
                    content="",
                    tool_calls=[
                        {"name": "kb_search", "arguments": {"question": "a"}},
                        {"name": "kb_ask", "arguments": {"question": "b"}},
                    ],
                ),
                ModelResponse(content="ok", tool_calls=[]),
            ]
        )
        loop = ToolLoop(
            tools=[
                _kb_tool(),
                _tool("kb_ask", parameters={"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}),
            ],
            model_call=rec.model_call,
            dispatch=rec.dispatch,
        )
        _run(loop)
        messages = rec.model_calls[1][0]
        assistant = [m for m in messages if m.get("role") == "assistant"][0]
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        ids = [tc["id"] for tc in assistant["tool_calls"]]
        self.assertTrue(all(isinstance(i, str) and i for i in ids))
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual([m["tool_call_id"] for m in tool_messages], ids)


class DispatchRegistryTests(unittest.TestCase):
    def test_build_default_dispatch_unknown_returns_error(self):
        dispatch = build_default_dispatch()
        result = dispatch("no_such_tool", {})
        self.assertIsInstance(result, DispatchResult)
        self.assertFalse(result.ok)
        self.assertIn("no_such_tool", result.error)


class _CapturingSearchService:
    """假检索服务：记录被选中的会议来源，不触发任何网络。"""

    def __init__(self):
        self.sources = []

    def search(self, source, query, years, limit, publication_scope):
        self.sources.append(source)
        from backend.app.paper_discovery.application.paper_discovery_search import SearchResult
        from backend.app.paper_discovery.domain.paper_discovery import SearchSession

        session = SearchSession(search_id="s1", query=query, expires_at="", created_at="")
        return SearchResult(session, [], [], None)


class _FakeConference:
    def __init__(self, conference_id, short_name, *, enabled=True, aliases=None):
        self.conference_id = conference_id
        self.name = f"{short_name} full name"
        self.short_name = short_name
        self.dblp_stream = f"conf/{conference_id}"
        self.venue_aliases = list(aliases or [])
        self.enabled = enabled


class _FakeStore:
    def __init__(self, conferences):
        self._conferences = list(conferences)

    def list_conferences(self):
        # 与真实 store 同序：built_in DESC, short_name ASC —— 故意让 USENIX 排在最后，
        # 以免「USENIX 优先」碰巧靠 conferences[0] 通过。
        return sorted(self._conferences, key=lambda c: c.short_name)


# 本机真实会议配置（2026-09-11 实测）：CCS / IEEE S&P / NDSS / USENIX Security，无任何 dblp 会议。
_LOCAL_CONFERENCES = [
    _FakeConference("ccs", "CCS"),
    _FakeConference("ieee-sp", "IEEE S&P"),
    _FakeConference("ndss", "NDSS"),
    _FakeConference("usenix-security", "USENIX Security", aliases=["USENIX Security Symposium"]),
]


class SourceSelectionTests(unittest.TestCase):
    """B1（spec-023.1）：search_paper_catalog 选源必须明确，禁止静默退化到 conferences[0]。"""

    def setUp(self):
        from backend.app.paper_discovery.application import paper_discovery_search as search_module

        self.search_module = search_module
        self.service = _CapturingSearchService()
        self.store = _FakeStore(_LOCAL_CONFERENCES)
        self._patches = [
            patch(
                "backend.app.api.common._build_paper_search_service",
                return_value=self.service,
            ),
            patch("backend.app.api.common._paper_store", return_value=self.store),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _dispatch(self, **args):
        return build_default_dispatch()("search_paper_catalog", dict(args))

    def test_source_all_prefers_usenix_not_first_conference(self):
        # 边界：source="all" 结果必须来自 USENIX，不得退化为 conferences[0]（CCS）
        result = self._dispatch(source="all", query="fuzzing")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([s.conference_id for s in self.service.sources], ["usenix-security"])
        self.assertIn("USENIX", result.output)

    def test_source_usenix_selects_usenix(self):
        result = self._dispatch(source="usenix", query="fuzzing")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([s.conference_id for s in self.service.sources], ["usenix-security"])

    def test_source_dblp_without_dblp_conference_is_readable_error(self):
        # 边界：无 dblp 会议 -> 可读错误，绝不返回其它会议结果
        result = self._dispatch(source="dblp", query="fuzzing")
        self.assertFalse(result.ok)
        self.assertEqual(self.service.sources, [], "无匹配来源时不得检索任何会议")
        self.assertIn("dblp", result.error.lower())
        # 不得把 conferences[0]（CCS）的**检索结果**冒充 dblp 结果（无 output、无候选）
        self.assertEqual(result.output, "")
        self.assertIn("不会退化", result.error)

    def test_source_all_without_usenix_still_uses_a_real_conference(self):
        # 无 USENIX 时：退到首个可用会议是允许的（结果可用但需报告实际来源）
        self.store._conferences = [
            _FakeConference("ndss", "NDSS"),
            _FakeConference("ccs", "CCS"),
        ]
        result = self._dispatch(source="all", query="fuzzing")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([s.conference_id for s in self.service.sources], ["ccs"])
        self.assertIn("CCS", result.output)

    def test_no_conference_at_all_reports_readable_error(self):
        self.store._conferences = []
        result = self._dispatch(source="all", query="fuzzing")
        self.assertFalse(result.ok)
        self.assertEqual(self.service.sources, [])
        self.assertIn("论文来源", result.error)

    def test_dblp_source_is_discovered_from_venue_aliases(self):
        # 若服务端确实配置了 dblp 来源（别名含 dblp），必须被选中而不是报错
        self.store._conferences = [
            _FakeConference("ccs", "CCS"),
            _FakeConference("dblp-cs", "DBLP", aliases=["dblp computer science bibliography"]),
        ]
        result = self._dispatch(source="dblp", query="fuzzing")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([s.conference_id for s in self.service.sources], ["dblp-cs"])
        self.assertIn("DBLP", result.output)

    def test_search_error_keeps_diagnosable_message(self):
        # 边界：来源不匹配的可诊断报错不得被压成通用「执行失败」（保留错误码）
        def _raise(**kwargs):
            raise self.search_module.PaperDiscoverySearchError(
                "CONFERENCE_NOT_CONFIGURED", "conference must be configured by the server"
            )

        self.service.search = _raise
        result = self._dispatch(source="all", query="fuzzing")
        self.assertFalse(result.ok)
        self.assertIn("CONFERENCE_NOT_CONFIGURED", result.error)


if __name__ == "__main__":
    unittest.main()
