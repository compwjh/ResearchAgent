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

from backend.app.skills.models import ToolEntry
from backend.app.skills.tool_executor import (
    DEFAULT_MAX_TOOL_ROUNDS,
    DispatchResult,
    ModelResponse,
    ToolLoop,
    build_tool_schema,
    build_tool_schemas,
)
from backend.app.skills.tool_dispatch import build_default_dispatch


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
        events = _run(loop)
        # 超时降级为不执行，对话照常结束（空内容也算正常结束）
        self.assertEqual(rec.dispatch_calls, [])


class DispatchRegistryTests(unittest.TestCase):
    def test_build_default_dispatch_unknown_returns_error(self):
        dispatch = build_default_dispatch()
        result = dispatch("no_such_tool", {})
        self.assertIsInstance(result, DispatchResult)
        self.assertFalse(result.ok)
        self.assertIn("no_such_tool", result.error)


if __name__ == "__main__":
    unittest.main()
