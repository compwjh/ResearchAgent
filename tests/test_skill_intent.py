"""spec-023 Task06 — Skill 识别器（规则 + LLM 双触发）单元测试与路由集成测试。

覆盖边界（来自 task 约束与 RESULT.md R2/R3/R4）：
- 未点名任何 Skill 的普通消息 -> 不触发、不额外调用 LLM、行为与改动前一致
- 规则假阳性（听说过 / 是什么 / 拼写错误 papper）-> 不触发
- 规则命中（指令性动词 + 词边界）-> 直接返回，省一次推理
- 命中可用 / 已禁用 / 不存在 -> 对应决策
- LLM 超时/报错 -> 降级为 none，不抛异常
- 可用列表为空 -> 直接 none，不调用 LLM
- 路由：matched 注入正文并流出 token；disabled/not_found/ambiguous 不调用模型并给出提示
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.skills import intent as intent_module
from backend.app.skills.intent import (
    SkillDecision,
    build_skill_prompt,
    detect_skill,
    format_skill_hint,
    to_intent_event,
)
from backend.app.skills.models import SkillSummary
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_executor import DispatchResult, ModelResponse


def _skill(name: str, enabled: bool = True) -> SkillSummary:
    return SkillSummary(name=name, description="", tools=[], enabled=enabled)


class SimpleNamespace:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, question):
        for text in self._chunks:
            yield SimpleNamespace(content=text)


def _mock_model(chunks):
    return lambda _name: _FakeModel(chunks)


def _fake_dispatch(name, args):
    return DispatchResult(ok=True, name=name, output=f"result-for-{name}")


class _RecordingDispatch:
    """记录 (name, args) 调用，供路由集成测试断言 Tool 执行确实发生。"""

    def __init__(self):
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, args))
        return DispatchResult(ok=True, name=name, output=f"result-for-{name}")


class DetectSkillUnitTests(unittest.TestCase):
    def setUp(self):
        self.skills = [
            _skill("usenix-paper-catalog-search", enabled=True),
            _skill("usenix-accepted-papers", enabled=False),
        ]

    # ---------- 可用列表为空 ----------
    def test_empty_available_returns_none_no_llm(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=AssertionError("不应调用 LLM")):
            decision = detect_skill("随便说点什么", [])
        self.assertEqual(decision.status, "none")

    # ---------- 普通消息：不触发、不调 LLM ----------
    def test_plain_message_no_skill_no_llm(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=AssertionError("不应调用 LLM")):
            decision = detect_skill("今天天气怎么样", self.skills)
        self.assertEqual(decision.status, "none")

    def test_plain_message_with_verb_but_no_skill_token_no_llm(self):
        # 含「用」但没有类技能名 token -> 不调用 LLM
        with patch.object(intent_module, "_call_intent_model", side_effect=AssertionError("不应调用 LLM")):
            decision = detect_skill("帮我用 Python 写个函数", self.skills)
        self.assertEqual(decision.status, "none")

    # ---------- 规则命中：指令性动词 + 词边界 ----------
    def test_rule_match_with_verb(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=AssertionError("不应调用 LLM")):
            decision = detect_skill("帮我用 usenix-paper-catalog-search 搜论文", self.skills)
        self.assertEqual(decision.status, "matched")
        self.assertEqual(decision.skill, "usenix-paper-catalog-search")
        self.assertEqual(decision.source, "rule")

    def test_rule_match_disabled(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=AssertionError("不应调用 LLM")):
            decision = detect_skill("请用 usenix-accepted-papers", self.skills)
        self.assertEqual(decision.status, "disabled")
        self.assertEqual(decision.skill, "usenix-accepted-papers")
        self.assertEqual(decision.source, "rule")

    def test_rule_match_requires_word_boundary(self):
        # papper 拼写错误：词边界不匹配真实技能名 -> 走 LLM
        with patch.object(intent_module, "_call_intent_model", return_value="none") as m:
            decision = detect_skill("帮我用 usenix-papper-catalog-search 搜论文", self.skills)
        m.assert_called_once()
        self.assertEqual(decision.status, "none")

    # ---------- 规则假阳性：听说过 / 是什么 ----------
    def test_mention_without_verb_goes_to_llm_and_none(self):
        with patch.object(intent_module, "_call_intent_model", return_value="none") as m:
            decision = detect_skill("我听说过 usenix-paper-catalog-search 这个东西", self.skills)
        m.assert_called_once()
        self.assertEqual(decision.status, "none")

    def test_what_is_goes_to_llm_and_none(self):
        with patch.object(intent_module, "_call_intent_model", return_value="none") as m:
            decision = detect_skill("usenix-paper-catalog-search 是什么", self.skills)
        m.assert_called_once()
        self.assertEqual(decision.status, "none")

    # ---------- LLM 命中（动词在名后 / 仅提及） ----------
    def test_llm_match_when_name_mentioned_without_verb(self):
        with patch.object(intent_module, "_call_intent_model", return_value="usenix-paper-catalog-search"):
            decision = detect_skill("usenix-paper-catalog-search 帮我搜一下", self.skills)
        self.assertEqual(decision.status, "matched")
        self.assertEqual(decision.source, "llm")

    # ---------- 点名不存在的技能 -> not_found ----------
    def test_unknown_skill_name_returns_not_found(self):
        with patch.object(intent_module, "_call_intent_model", return_value="foobar-skill") as m:
            decision = detect_skill("用 foobar-skill 搜论文", self.skills)
        m.assert_called_once()
        self.assertEqual(decision.status, "not_found")
        self.assertEqual(decision.requested, "foobar-skill")

    # ---------- LLM 返回闲聊文本 -> 降级 none（不误判 not_found） ----------
    def test_llm_garbage_degrades_to_none(self):
        with patch.object(intent_module, "_call_intent_model", return_value="我不知道你说什么"):
            decision = detect_skill("我听说过 usenix-paper-catalog-search", self.skills)
        self.assertEqual(decision.status, "none")

    # ---------- LLM 超时/报错 -> 降级 none，不抛异常 ----------
    def test_llm_timeout_degrades_to_none(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=httpx.ReadTimeout("boom")):
            decision = detect_skill("我听说过 usenix-paper-catalog-search 这个东西", self.skills)
        self.assertEqual(decision.status, "none")

    def test_llm_runtime_error_degrades_to_none(self):
        with patch.object(intent_module, "_call_intent_model", side_effect=RuntimeError("down")):
            decision = detect_skill("我听说过 usenix-paper-catalog-search 这个东西", self.skills)
        self.assertEqual(decision.status, "none")


class IntentHelperTests(unittest.TestCase):
    def test_build_skill_prompt_injects_body(self):
        prompt = build_skill_prompt("用户问题X", "技能正文Y")
        self.assertIn("技能正文Y", prompt)
        self.assertIn("用户问题X", prompt)
        self.assertIn("技能正文开始", prompt)

    def test_to_intent_event_matched(self):
        ev = to_intent_event(SkillDecision(status="matched", skill="demo", source="rule"))
        self.assertEqual(ev["type"], "intent")
        self.assertEqual(ev["skill"], "demo")
        self.assertEqual(ev["intent"], "demo")
        self.assertEqual(ev["confidence"], 1.0)

    def test_to_intent_event_none_is_none(self):
        self.assertIsNone(to_intent_event(SkillDecision(status="none")))

    def test_to_intent_event_disabled(self):
        ev = to_intent_event(SkillDecision(status="disabled", skill="demo"))
        self.assertEqual(ev["intent"], "disabled")
        self.assertIsNone(ev["skill"])
        self.assertIn("已禁用", ev["message"])

    def test_to_intent_event_not_found_lists_available(self):
        ev = to_intent_event(
            SkillDecision(status="not_found", requested="ghost"), available_names=["a", "b"]
        )
        self.assertEqual(ev["intent"], "not_found")
        self.assertIn("ghost", ev["message"])
        self.assertIn("a", ev["message"])

    def test_format_skill_hint_matched_none(self):
        self.assertIsNone(format_skill_hint(SkillDecision(status="matched", skill="demo")))
        self.assertIsNone(format_skill_hint(SkillDecision(status="none")))

    def test_format_skill_hint_disabled(self):
        self.assertIn("已禁用", format_skill_hint(SkillDecision(status="disabled", skill="demo")))

    def test_format_skill_hint_not_found(self):
        self.assertIn("未找到", format_skill_hint(SkillDecision(status="not_found", requested="ghost"), ["a"]))


class ChatSkillRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.skills_dir = Path(self.tmp.name) / "skills"
        self.state = Path(self.tmp.name) / "skill-state.json"
        self._write_skill("demo-skill", "这是一个用于演示的技能正文。", enabled=True)
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_skill(self, name, body, *, enabled=True):
        directory = self.skills_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        content = f"---\nname: {name}\ndescription: x\ntools: []\n---\n\n{body}\n"
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
        if not enabled:
            self.state.write_text(
                json.dumps(
                    {"schema_version": "skill-state-v1", "skills": {name: {"enabled": False}}, "tools": {}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    def _registry(self) -> SkillRegistryService:
        return SkillRegistryService(skills_dir=self.skills_dir, state_path=self.state)

    def _post(self, decision: SkillDecision, question: str = "hello", *, tool_responses=None, dispatch=None):
        if tool_responses is None:
            tool_responses = [ModelResponse(content="Hi there", tool_calls=[])]
        tool_responses = list(tool_responses)
        if dispatch is None:
            dispatch = _fake_dispatch

        def _tool_model_factory(model_name=None, *, timeout=0.0, retry=0, **kwargs):
            # 与真实 make_model_call 签名一致：工厂接收 model_name/timeout/retry，返回 (messages, tools) -> ModelResponse
            def _call(messages, tools):
                return tool_responses.pop(0) if tool_responses else ModelResponse(content="", tool_calls=[])

            return _call

        with patch("backend.app.api.routes_skills.get_skill_registry", return_value=self._registry()):  # noqa: SIM117
            with patch("backend.app.api.routes_chat.get_available_models", return_value=["qwen3.5:9b"]):
                with patch("backend.app.skills.intent.detect_skill", return_value=decision):
                    with patch(
                        "backend.app.platform.ollama.create_chat_model",
                        side_effect=_mock_model(["Hi", " there"]),
                    ) as mock_model:
                        with patch(
                            "backend.app.skills.tool_executor.make_model_call",
                            _tool_model_factory,
                        ):
                            with patch(
                                "backend.app.skills.tool_dispatch.build_default_dispatch",
                                return_value=dispatch,
                            ):
                                response = self.client.post(
                                    "/api/chat", json={"question": question, "model": "qwen3.5:9b"}
                                )
                                return response, mock_model

    def test_none_no_extra_events_and_streams(self):
        response, mock_model = self._post(SkillDecision(status="none"))
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "meta"', response.text)
        self.assertIn('"type": "token"', response.text)
        self.assertIn('"type": "done"', response.text)
        self.assertNotIn('"type": "intent"', response.text)
        self.assertNotIn("未找到", response.text)
        self.assertNotIn("已禁用", response.text)
        mock_model.assert_called()

    def test_matched_emits_intent_and_streams(self):
        response, mock_model = self._post(
            SkillDecision(status="matched", skill="demo-skill", source="rule")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "intent"', response.text)
        self.assertIn('"skill": "demo-skill"', response.text)
        self.assertIn('"type": "token"', response.text)
        # Task07 契约变更：matched 路径走 Tool 循环（model_call=make_model_call），
        # 不再使用 create_chat_model（mock_model）。改用最终 token 内容断言模型已被调用。
        self.assertIn("Hi there", response.text)

    def test_not_found_does_not_call_model_and_hints(self):
        response, mock_model = self._post(
            SkillDecision(status="not_found", requested="ghost-skill")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("未找到名为「ghost-skill」", response.text)
        self.assertIn("demo-skill", response.text)  # 列出可用技能
        self.assertIn('"type": "intent"', response.text)
        self.assertNotIn('"type": "token"', response.text)
        mock_model.assert_not_called()

    def test_disabled_does_not_call_model_and_hints(self):
        response, mock_model = self._post(
            SkillDecision(status="disabled", skill="demo-skill")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("已禁用", response.text)
        self.assertNotIn('"type": "token"', response.text)
        mock_model.assert_not_called()

    def test_ambiguous_does_not_call_model_and_hints(self):
        response, mock_model = self._post(SkillDecision(status="ambiguous"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("同时命中多个技能", response.text)
        self.assertNotIn('"type": "token"', response.text)
        mock_model.assert_not_called()

    def test_matched_native_tool_call_executes_and_streams(self):
        # 路径 A：模型返回 tool_calls -> 校验 -> 执行 -> 回灌 -> 合成最终回答
        recorder = _RecordingDispatch()
        response, _ = self._post(
            SkillDecision(status="matched", skill="demo-skill", source="rule"),
            tool_responses=[
                ModelResponse(
                    content="",
                    tool_calls=[{"name": "kb_search", "arguments": {"question": "x"}}],
                ),
                ModelResponse(content="合成回答", tool_calls=[]),
            ],
            dispatch=recorder,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("合成回答", response.text)
        self.assertEqual(recorder.calls, [("kb_search", {"question": "x"})])

    def test_matched_fallback_plan_json_executes(self):
        # 路径 B：原生不可用（无 tool_calls）-> 解析受控计划 JSON -> 校验 -> 执行
        recorder = _RecordingDispatch()
        response, _ = self._post(
            SkillDecision(status="matched", skill="demo-skill", source="rule"),
            tool_responses=[
                ModelResponse(content='{"tool":"kb_search","args":{"question":"x"}}', tool_calls=[]),
                ModelResponse(content="合成回答", tool_calls=[]),
            ],
            dispatch=recorder,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("合成回答", response.text)
        self.assertEqual(recorder.calls, [("kb_search", {"question": "x"})])

    def test_matched_unregistered_tool_rejected_no_execute(self):
        # 边界：未注册 Tool -> 拒绝执行，返回可读错误，不猜测执行
        recorder = _RecordingDispatch()
        response, _ = self._post(
            SkillDecision(status="matched", skill="demo-skill", source="rule"),
            tool_responses=[
                ModelResponse(
                    content="",
                    tool_calls=[{"name": "ghost_tool", "arguments": {}}],
                ),
            ],
            dispatch=recorder,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorder.calls, [])
        self.assertIn("ghost_tool", response.text)
        self.assertIn("不存在", response.text)


if __name__ == "__main__":
    unittest.main()
