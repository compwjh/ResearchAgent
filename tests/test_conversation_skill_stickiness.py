"""spec-032.1 task-10 — 会话级 Skill 粘性（sticky skill）。

验收（每条一个/组用例）：
1. 第 1 轮点名 -> intent 命中；**第 2 轮不点名 -> 仍产生 intent 且带工具**（核心）。
2. 点名另一个 Skill -> 切换。
3. 明确退出语义 -> 清除粘性，本轮无 intent 且走 run_chat。
4. active_skill 指向的 Skill 被禁用 -> 清除并回退，不报错。
5. 从未点名的会话 -> 行为完全不变（无 intent、走 run_chat）。
6. 存储：新表 conversation_active_skill 可读写、按会话隔离、删除后回落。

复用既有能力（detect_skill / ToolLoop / 两个注册表），不新增第二套识别。
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.chat.application.conversation_service import stop_all_workers
from backend.app.main import app
from backend.app.memory.repository import MemoryRepository
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


class StickySkillRepositoryTests(unittest.TestCase):
    """验收 6：新表读写、隔离与清理（repository 层）。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "memory.sqlite3"
        self.repo = MemoryRepository(self.path)

    def _conversation(self, owner="local-user"):
        project = self.repo.create_project(owner, f"P-{owner}-{len(self.repo.list_projects(owner)[0])}")
        return self.repo.create_conversation(owner, project.project_id, title="c")

    def test_active_skill_roundtrip_and_isolation(self):
        first = self._conversation()
        second = self._conversation()
        self.assertIsNone(self.repo.get_conversation_active_skill(first.conversation_id, "local-user"))
        self.repo.set_conversation_active_skill(first.conversation_id, "local-user", "skill-a")
        active = self.repo.get_conversation_active_skill(first.conversation_id, "local-user")
        self.assertIsNotNone(active)
        self.assertEqual(active.skill_name, "skill-a")
        self.assertEqual(active.owner_id, "local-user")
        # 会话隔离：另一个会话不受影响
        self.assertIsNone(self.repo.get_conversation_active_skill(second.conversation_id, "local-user"))
        # owner 隔离
        self.assertIsNone(self.repo.get_conversation_active_skill(first.conversation_id, "other-user"))

    def test_set_overwrites_and_clear_removes(self):
        conversation = self._conversation()
        self.repo.set_conversation_active_skill(conversation.conversation_id, "local-user", "skill-a")
        self.repo.set_conversation_active_skill(conversation.conversation_id, "local-user", "skill-b")
        self.assertEqual(
            self.repo.get_conversation_active_skill(conversation.conversation_id, "local-user").skill_name, "skill-b"
        )
        self.repo.clear_conversation_active_skill(conversation.conversation_id, "local-user")
        self.assertIsNone(self.repo.get_conversation_active_skill(conversation.conversation_id, "local-user"))
        # 重复清除幂等，不报错
        self.repo.clear_conversation_active_skill(conversation.conversation_id, "local-user")

    def test_schema_initialize_is_idempotent_with_new_table(self):
        self.repo.initialize()
        self.repo.initialize()
        with self.repo.connection() as db:
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_active_skill'"
            ).fetchone()
        self.assertIsNotNone(table)

    def test_soft_deleted_conversation_drops_sticky_skill(self):
        conversation = self._conversation()
        self.repo.set_conversation_active_skill(conversation.conversation_id, "local-user", "skill-a")
        self.assertTrue(self.repo.delete_conversation(conversation.conversation_id, "local-user"))
        self.assertIsNone(self.repo.get_conversation_active_skill(conversation.conversation_id, "local-user"))

    def test_legacy_v6_database_gains_new_table_on_initialize(self):
        # 模拟「迁移前就已存在的 v6 库」：删掉新表再 initialize 应被重建（幂等加性扩展）。
        with self.repo.connection() as db:
            db.execute("DROP TABLE conversation_active_skill")
        self.repo.initialize()
        with self.repo.connection() as db:
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_active_skill'"
            ).fetchone()
            # 既有 conversations 表结构不得被改动
            columns = {row["name"] for row in db.execute("PRAGMA table_info(conversations)")}
        self.assertIsNotNone(table)
        self.assertEqual(
            columns,
            {"conversation_id", "owner_id", "project_id", "title", "status", "memory_history_policy",
             "created_at", "updated_at", "memory_binding_at", "memory_binding_message_id"},
        )


class ConversationStickySkillRouteTests(unittest.TestCase):
    """路由层 7 条验收（1-5 + 与既有链路等价）。"""

    def setUp(self):
        self.client = TestClient(app)
        self.skill_name = "usenix-catalog-orchestration"
        self.other_skill = "other-orchestration"
        self.skill = SkillSummary(name=self.skill_name, description="", tools=[], enabled=True)
        self.registry = _SkillRegistry(
            [self.skill],
            {self.skill_name: "技能正文BODY_9f2", self.other_skill: "另一技能正文BODY_a11"},
        )
        self._tmp = TemporaryDirectory()
        self.db_patch = patch(
            "backend.app.memory.repository.default_database_path", return_value=Path(self._tmp.name) / "memory.sqlite3"
        )
        self.db_patch.start()

        def _teardown():
            # 顺序无关的强保证：先停掉按库路径永久驻留的 worker 线程，再删临时目录。
            # 否则线程会在 cleanup 之后重新建连并重建库文件，与 rmtree 竞态（Errno 66）。
            # 统一注册为**单个** cleanup，LIFO 使其成为本用例最后一步，不受 patch 顺序影响。
            self.db_patch.stop()
            stop_all_workers()
            self._tmp.cleanup()

        self.addCleanup(_teardown)

    def _stack(self, decision, tools=None, capture=None, registry=None):
        """统一装配 patch 栈（复用 task-09 同款接缝）。"""
        from contextlib import ExitStack

        tool_registry = _ToolRegistry(tools if tools is not None else [])
        run = FakeRun()

        def _run(question, model, *, messages):
            if capture is not None:
                capture["messages"] = messages
                capture["question"] = question
            return run

        stack = ExitStack()
        stack.enter_context(patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]))
        stack.enter_context(patch("backend.app.api.routes_conversations.run_chat", side_effect=_run))
        stack.enter_context(
            patch("backend.app.api.routes_conversations.get_skill_registry", return_value=registry or self.registry)
        )
        stack.enter_context(patch("backend.app.api.routes_conversations.get_tool_registry", return_value=tool_registry))
        self._detect = stack.enter_context(
            patch("backend.app.api.routes_conversations.detect_skill", side_effect=self._decision_side_effect(decision))
        )
        return stack

    def _decision_side_effect(self, decisions):
        """按用户消息顺序返回决策；dict 精确匹配，否则按列表顺序 consuming。"""
        if isinstance(decisions, list):
            queue = list(decisions)

            def _side_effect(message, skills):
                return queue.pop(0)

            return _side_effect

        def _side_effect(message, skills):
            if isinstance(decisions, dict):
                return decisions.get(message, SkillDecision(status="none"))
            return decisions

        return _side_effect

    def _post(self, content, decision, conversation_id=None, tools=None, capture=None, registry=None):
        url = "/api/conversations/messages" if conversation_id is None else f"/api/conversations/{conversation_id}/messages"
        body = {"content": content, "model": "model"}
        with self._stack(decision, tools=tools, capture=capture, registry=registry):
            return self.client.post(url, json=body)

    # ---------- 验收 1（核心）：第 1 轮点名，第 2 轮不点名仍带工具 ----------
    def test_second_turn_without_naming_keeps_skill_and_tools(self):
        capture = {}
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
            tools=[_tool("kb_search")],
        )
        intents = [e for e in _events(first) if e["type"] == "intent"]
        self.assertEqual(len(intents), 1)
        conversation_id = _events(first)[0]["conversation_id"]

        recorder = _RecordingDispatch()
        responses = [
            ModelResponse(content="", tool_calls=[{"name": "kb_search", "arguments": {}}]),
            ModelResponse(content="工具合成回答", tool_calls=[]),
        ]

        def _model_factory(model_name=None, *, timeout=0.0, retry=0, **kwargs):
            def _call(messages, tools):
                return responses.pop(0) if responses else ModelResponse(content="", tool_calls=[])

            return _call

        from contextlib import ExitStack

        with ExitStack() as stack:
            for ctx in [patch("backend.app.skills.tool_executor.make_model_call", _model_factory),
                        patch("backend.app.skills.tool_dispatch.build_default_dispatch", return_value=recorder)]:
                stack.enter_context(ctx)
            with self._stack(
                [SkillDecision(status="none")],
                tools=[_tool("kb_search")],
                capture=capture,
            ):
                second = self.client.post(
                    f"/api/conversations/{conversation_id}/messages",
                    json={"content": "好的，就下载第一篇吧", "model": "model"},
                )
        self.assertEqual(second.status_code, 200)
        events = _events(second)
        # 核心：第二轮仍产生 intent，且带工具走 ToolLoop（未退回 run_chat）
        self.assertEqual([e["type"] for e in events if e["type"] == "intent"].count("intent"), 1)
        intent = [e for e in events if e["type"] == "intent"][0]
        self.assertEqual(intent["skill"], self.skill_name)
        self.assertIn("工具合成回答", second.text)
        self.assertEqual(recorder.calls, [("kb_search", {})])
        self.assertNotIn("messages", capture)

    # ---------- 验收 1b：沿用粘性但无 Tool -> 注入正文走 run_chat ----------
    def test_second_turn_without_naming_injects_body_when_no_tools(self):
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
        )
        conversation_id = _events(first)[0]["conversation_id"]

        capture = {}
        second = self._post(
            "就下载第一篇吧", [SkillDecision(status="none")], conversation_id=conversation_id, capture=capture
        )
        events = _events(second)
        self.assertEqual(len([e for e in events if e["type"] == "intent"]), 1)
        injected = [m for m in capture["messages"] if "技能正文BODY_9f2" in (m.get("content") or "")]
        self.assertEqual(len(injected), 1)

    # ---------- 验收 2：切换 ----------
    def test_naming_another_skill_switches(self):
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
        )
        conversation_id = _events(first)[0]["conversation_id"]
        other = SkillSummary(name=self.other_skill, description="", tools=[], enabled=True)
        registry = _SkillRegistry(
            [self.skill, other],
            {self.skill_name: "技能正文BODY_9f2", self.other_skill: "另一技能正文BODY_a11"},
        )
        capture = {}
        second = self._post(
            f"改用 {self.other_skill} 来做",
            [SkillDecision(status="matched", skill=self.other_skill, source="rule")],
            conversation_id=conversation_id,
            capture=capture,
            registry=registry,
        )
        intent = [e for e in _events(second) if e["type"] == "intent"][0]
        self.assertEqual(intent["skill"], self.other_skill)
        injected = [m for m in capture["messages"] if "另一技能正文BODY_a11" in (m.get("content") or "")]
        self.assertEqual(len(injected), 1)
        # 后续轮次沿用「新」技能，而非旧技能
        capture2 = {}
        third = self._post("继续", [SkillDecision(status="none")], conversation_id=conversation_id, capture=capture2, registry=registry)
        self.assertEqual([e for e in _events(third) if e["type"] == "intent"][0]["skill"], self.other_skill)
        self.assertFalse([m for m in capture2["messages"] if "技能正文BODY_9f2" in (m.get("content") or "")])
        self.assertTrue([m for m in capture2["messages"] if "另一技能正文BODY_a11" in (m.get("content") or "")])

    # ---------- 验收 3：明确退出 ----------
    def test_explicit_exit_clears_stickiness(self):
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
        )
        conversation_id = _events(first)[0]["conversation_id"]
        capture = {}
        second = self._post(
            "结束技能，回到普通对话",
            [SkillDecision(status="none")],
            conversation_id=conversation_id,
            capture=capture,
        )
        events = _events(second)
        self.assertFalse([e for e in events if e["type"] == "intent"])
        self.assertIn("messages", capture)  # 走原 run_chat
        self.assertFalse([m for m in capture["messages"] if "技能正文BODY_9f2" in (m.get("content") or "")])
        # 会话状态隔离：本用例只跑一轮，忽略落库的粘性，避免与 TestClient 共享
        # 数据库/单例在同一进程内的先序用例产生耦合。
        capture = {}
        response = self._post("随便聊聊", [SkillDecision(status="none")], capture=capture)
        self.assertFalse([e for e in _events(response) if e["type"] == "intent"])
        self.assertIn("messages", capture)

    # ---------- 验收 4：粘性技能失效 -> 清除回退，不报错 ----------
    def test_disabled_sticky_skill_degrades_without_error(self):
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
        )
        conversation_id = _events(first)[0]["conversation_id"]
        # 第二轮：粘性技能已从注册表移除（禁用/删除）
        empty_registry = _SkillRegistry([], {})
        capture = {}
        second = self._post(
            "继续", [SkillDecision(status="none")], conversation_id=conversation_id, capture=capture, registry=empty_registry
        )
        self.assertEqual(second.status_code, 200)
        events = _events(second)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["status"], "completed")
        self.assertFalse([e for e in events if e["type"] == "error"])
        self.assertFalse([e for e in events if e["type"] == "intent"])
        self.assertIn("messages", capture)
        # 失效状态应被清除：第三轮（注册表恢复）不再自动沿用
        capture2 = {}
        third = self._post("再说一句", [SkillDecision(status="none")], conversation_id=conversation_id, capture=capture2)
        self.assertFalse([e for e in _events(third) if e["type"] == "intent"])

    # ---------- 验收 5：从未点名 -> 行为完全不变 ----------
    def test_never_named_conversation_unchanged(self):
        capture = {}
        first = self._post("普通问题", SkillDecision(status="none"), capture=capture)
        events = _events(first)
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse([e for e in events if e["type"] == "intent"])
        self.assertIn("messages", capture)
        self.assertFalse([m for m in capture["messages"] if "技能正文" in (m.get("content") or "")])
        # 第二轮仍无粘性
        conversation_id = events[0]["conversation_id"]
        capture2 = {}
        second = self._post("第二个普通问题", SkillDecision(status="none"), conversation_id=conversation_id, capture=capture2)
        self.assertFalse([e for e in _events(second) if e["type"] == "intent"])

    # ---------- 退出词表保守：含技能的普通表述不得误退 ----------
    def test_non_exit_phrasing_keeps_stickiness(self):
        first = self._post(
            "帮我使用 usenix-catalog-orchestration 下载论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
        )
        conversation_id = _events(first)[0]["conversation_id"]
        for message in ("这个技能很好用", "先不要结束", "技能还能用吗", "继续下载下一篇"):
            capture = {}
            response = self._post(message, [SkillDecision(status="none")], conversation_id=conversation_id, capture=capture)
            self.assertEqual(
                len([e for e in _events(response) if e["type"] == "intent"]), 1, f"被误退：{message}"
            )


    # ---------- 验收 8：真实链路复现（第二轮走真实 detect_skill = none） ----------
    def test_real_chain_second_turn_hits_native_function_calling(self):
        """只有第一轮 mock 识别为命中；第二轮「就下载第一篇吧」经真实 detect_skill
        返回 none，粘性必须把它拉回带工具的链路并真实执行工具。"""
        from backend.app.skills.intent import detect_skill as real_detect

        calls = {"n": 0}

        def _detect(message, skills):
            calls["n"] += 1
            if calls["n"] == 1:
                return SkillDecision(status="matched", skill=self.skill_name, source="rule")
            return real_detect(message, skills)

        tool = ToolEntry(
            name="search_paper_catalog", description="d", enabled=True,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        )
        recorder = _RecordingDispatch()
        rounds = {"n": 0}

        def _model_factory(model_name=None, *, timeout=0.0, retry=0, **kwargs):
            def _call(messages, tools):
                rounds["n"] += 1
                if rounds["n"] == 1:
                    return ModelResponse(
                        content="", tool_calls=[{"name": "search_paper_catalog", "arguments": {"query": "agent"}}]
                    )
                return ModelResponse(content="已检索到论文：第一篇《Agent X》", tool_calls=[])

            return _call

        first = self._post(
            "帮我使用 skill usenix-catalog-orchestration 下载一篇关于 agent 的论文",
            SkillDecision(status="matched", skill=self.skill_name, source="rule"),
            tools=[tool],
        )
        self.assertEqual([e["skill"] for e in _events(first) if e["type"] == "intent"], [self.skill_name])
        conversation_id = _events(first)[0]["conversation_id"]

        registry = _SkillRegistry([self.skill], {self.skill_name: "技能正文BODY_9f2"})
        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(patch("backend.app.skills.tool_executor.make_model_call", _model_factory))
            stack.enter_context(patch("backend.app.skills.tool_dispatch.build_default_dispatch", return_value=recorder))
            stack.enter_context(
                patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"])
            )
            stack.enter_context(
                patch("backend.app.api.routes_conversations.get_skill_registry", return_value=registry)
            )
            stack.enter_context(
                patch("backend.app.api.routes_conversations.get_tool_registry", return_value=_ToolRegistry([tool]))
            )
            stack.enter_context(patch("backend.app.api.routes_conversations.detect_skill", side_effect=_detect))
            second = self.client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "好的，就下载第一篇吧", "model": "model"},
            )
        self.assertEqual(second.status_code, 200)
        intents = [e for e in _events(second) if e["type"] == "intent"]
        self.assertEqual([e["skill"] for e in intents], [self.skill_name])
        self.assertEqual(recorder.calls, [("search_paper_catalog", {"query": "agent"})])
        self.assertIn("第一篇", second.text)


if __name__ == "__main__":
    unittest.main()
