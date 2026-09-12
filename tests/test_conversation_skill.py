"""spec-032.1 task-09 — 会话链路（`/api/conversations/messages`）接入 Skill 识别 + Tool 执行。

验收（每条一个/组用例）：
1. 未点名 Skill 的普通会话消息：行为与改动前完全一致（仍走 run_chat，无 intent 事件）。
2. 点名 usenix-catalog-orchestration：产生 intent 事件且 `skill` 字段正确。
3. 点名不存在 / 已禁用的 Skill：返回提示且**不调用模型**。
4. 命中且无可用 Tool：技能正文被注入 messages，走 run_chat。
5. 命中且有 enabled Tool：走 ToolLoop 并回流 token。
6. Skill 识别抛异常：降级走 run_chat，不中断、不报错给用户。

全程复用 spec-023 既有能力（intent / tool_executor / tool_dispatch / 两个注册表），
不新增第二套实现；本文件只做接线验证。
"""

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.chat.application.conversation_service import stop_all_workers
from backend.app.main import app
from backend.app.skills.intent import SkillDecision
from backend.app.skills.models import SkillSummary, ToolEntry
from backend.app.skills.tool_executor import DispatchResult, ModelResponse


def _events(response):
    text = getattr(response, "text", response)
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


class FakeRun:
    route = "langchain"
    result = None

    @property
    def events(self):
        yield {"type": "token", "content": "答复"}


class _SkillRegistry:
    """仅实现路由所需的 list_skills / get_skill（免磁盘 fixture）。"""

    def __init__(self, summaries, bodies):
        self._summaries = summaries
        self._bodies = bodies

    def list_skills(self):
        return list(self._summaries)

    def get_skill(self, name):
        body = self._bodies.get(name)
        if body is None:
            return None
        return SkillSummaryDetail(name=name, body=body)


class SkillSummaryDetail:
    def __init__(self, name, body):
        self.name = name
        self.body = body


class _ToolRegistry:
    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return list(self._tools)


def _tool(name, enabled=True):
    return ToolEntry(name=name, description="d", enabled=enabled, parameters={"type": "object", "properties": {}})


class _RecordingDispatch:
    def __init__(self):
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, args))
        return DispatchResult(ok=True, name=name, output=f"result-for-{name}")


class ConversationSkillRouteTests(unittest.TestCase):
    def setUp(self):
        # 消息链路按库路径永久缓存 worker 线程；用例结束必须停掉它们，否则线程会
        # 在用例（及其临时库）消失后继续轮询。本类虽未自建临时目录，但其 worker
        # 会驻留在全进程缓存里、跟随其它用例的默认库，因此按同一纪律清理。
        self.addCleanup(stop_all_workers)
        self.client = TestClient(app)
        self.skill_name = "usenix-catalog-orchestration"
        self.skill = SkillSummary(name=self.skill_name, description="", tools=[], enabled=True)
        self.registry = _SkillRegistry([self.skill], {self.skill_name: "技能正文BODY_9f2"})

    def _patch_env(self, decision, tools=None, run_chat_side_effect=None, capture=None):
        """统一装配 patch 栈，返回 ExitStack 形式嵌套的上下文管理器列表。"""
        tool_registry = _ToolRegistry(tools if tools is not None else [])
        run = FakeRun()
        if run_chat_side_effect is None:
            def _run(question, model, *, messages):
                if capture is not None:
                    capture["messages"] = messages
                    capture["question"] = question
                return run
            run_chat_side_effect = _run
        return [
            patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]),
            patch("backend.app.api.routes_conversations.run_chat", side_effect=run_chat_side_effect),
            patch("backend.app.api.routes_conversations.get_skill_registry", return_value=self.registry),
            patch("backend.app.api.routes_conversations.get_tool_registry", return_value=tool_registry),
            patch("backend.app.api.routes_conversations.detect_skill", return_value=decision),
        ]

    def _post(self, content, decision, tools=None, capture=None, run_chat_side_effect=None):
        from contextlib import ExitStack

        with ExitStack() as stack:
            for ctx in self._patch_env(decision, tools=tools, capture=capture, run_chat_side_effect=run_chat_side_effect):
                stack.enter_context(ctx)
            return self.client.post(
                "/api/conversations/messages", json={"content": content, "model": "model"}
            )

    # ---------- 验收 1：未点名 Skill，行为完全不变 ----------
    def test_plain_message_unchanged(self):
        capture = {}
        response = self._post("普通问题", SkillDecision(status="none"), capture=capture)
        self.assertEqual(response.status_code, 200)
        events = _events(response)
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse([e for e in events if e["type"] == "intent"])
        self.assertNotIn("技能", response.text)
        # 仍走原链路，且 messages 未被注入任何技能正文
        self.assertIn("messages", capture)
        self.assertFalse([m for m in capture["messages"] if "技能正文" in (m.get("content") or "")])
        self.assertIn('"type": "token"', response.text)

    # ---------- 验收 2：点名 Skill -> intent 事件 ----------
    def test_matched_emits_intent_with_skill_field(self):
        response = self._post("帮我使用 usenix-catalog-orchestration 下载一篇论文", SkillDecision(status="matched", skill=self.skill_name, source="rule"))
        self.assertEqual(response.status_code, 200)
        intents = [e for e in _events(response) if e["type"] == "intent"]
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["skill"], self.skill_name)
        self.assertEqual(intents[0]["intent"], self.skill_name)
        # 会话上下文字段不得丢失（与同文件既有 stream_event 写法一致）
        events = _events(response)
        self.assertTrue(events[0].get("conversation_id"))
        self.assertTrue(events[0].get("user_message_id"))
        self.assertTrue(events[0].get("assistant_message_id"))

    # ---------- 验收 3：不存在 / 已禁用 -> 提示且不调用模型 ----------
    def test_not_found_hints_without_calling_model(self):
        capture = {}
        response = self._post("用 ghost-skill 干活", SkillDecision(status="not_found", requested="ghost-skill"), capture=capture)
        self.assertEqual(response.status_code, 200)
        self.assertIn("未找到名为「ghost-skill」", response.text)
        self.assertIn('"type": "intent"', response.text)
        hints = [e for e in _events(response) if e["type"] in {"result", "token"}]
        self.assertEqual(len(hints), 1)  # 提示以 result 或 token 之一返回
        self.assertEqual(_events(response)[-1]["type"], "done")
        self.assertNotIn("messages", capture)  # run_chat 未被调用 -> 未调用模型

    def test_disabled_hints_without_calling_model(self):
        capture = {}
        response = self._post("用 usenix-catalog-orchestration", SkillDecision(status="disabled", skill=self.skill_name), capture=capture)
        self.assertEqual(response.status_code, 200)
        self.assertIn("已禁用", response.text)
        hints = [e for e in _events(response) if e["type"] in {"result", "token"}]
        self.assertEqual(len(hints), 1)  # 提示以 result 或 token 之一返回
        self.assertNotIn("messages", capture)
        self.assertEqual(_events(response)[-1]["type"], "done")

    # ---------- 验收 4：命中且无可用 Tool -> 注入正文走 run_chat ----------
    def test_matched_without_tools_injects_body_and_runs_chat(self):
        capture = {}
        response = self._post("帮我使用 usenix-catalog-orchestration 下载论文", SkillDecision(status="matched", skill=self.skill_name, source="rule"), tools=[], capture=capture)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "token"', response.text)
        injected = [m for m in capture["messages"] if "技能正文BODY_9f2" in (m.get("content") or "")]
        self.assertEqual(len(injected), 1)
        self.assertEqual(injected[0]["role"], "system")

    # ---------- 验收 5：命中且有 enabled Tool -> ToolLoop 回流 token ----------
    def test_matched_with_enabled_tool_runs_tool_loop(self):
        recorder = _RecordingDispatch()
        responses = [
            ModelResponse(content="", tool_calls=[{"name": "kb_search", "arguments": {}}]),
            ModelResponse(content="工具合成回答", tool_calls=[]),
        ]

        def _model_factory(model_name=None, *, timeout=0.0, retry=0, **kwargs):
            def _call(messages, tools):
                return responses.pop(0) if responses else ModelResponse(content="", tool_calls=[])
            return _call

        capture = {}
        from contextlib import ExitStack

        with ExitStack() as stack:
            for ctx in self._patch_env(SkillDecision(status="matched", skill=self.skill_name, source="rule"), tools=[_tool("kb_search")], capture=capture):
                stack.enter_context(ctx)
            stack.enter_context(patch("backend.app.skills.tool_executor.make_model_call", _model_factory))
            stack.enter_context(patch("backend.app.skills.tool_dispatch.build_default_dispatch", return_value=recorder))
            response = self.client.post("/api/conversations/messages", json={"content": "帮我使用 usenix-catalog-orchestration", "model": "model"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("工具合成回答", response.text)
        self.assertEqual(recorder.calls, [("kb_search", {})])
        self.assertNotIn("messages", capture)  # 未退回 run_chat
        events = _events(response)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["status"], "completed")

    # ---------- 验收 6：识别异常 -> 降级 run_chat ----------
    def test_detect_skill_exception_falls_back_to_run_chat(self):
        capture = {}
        from contextlib import ExitStack

        with ExitStack() as stack:
            for ctx in self._patch_env(SkillDecision(status="none"), capture=capture):
                stack.enter_context(ctx)
            stack.enter_context(patch("backend.app.api.routes_conversations.detect_skill", side_effect=RuntimeError("boom")))
            response = self.client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
        self.assertEqual(response.status_code, 200)
        events = _events(response)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["status"], "completed")
        self.assertFalse([e for e in events if e["type"] == "error"])
        self.assertIn("messages", capture)


if __name__ == "__main__":
    unittest.main()
