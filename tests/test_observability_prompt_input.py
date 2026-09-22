"""spec-041 T-B：埋点 input 全量可见（redact_prompt_messages 修复验收）。

边界 6 验收载体：修复必须落在 redact_prompt_messages 函数本体，一次性覆盖
routes_article / routes_chat / routes_kb / routes_conversations / spans 共 5 个入口。
本文件用单测把「函数本体修复 = 全部入口生效」这一结论锁死，防止有人只改旧脱敏
调用点而漏掉其余 4 个 route 入口。

关键断言要求（regression-guard 边界 12）：
- 不得写成恒真断言（如把响应字段与自己比）；
- 不得写成「缺文件就静默 return 通过」的守卫——本文件直接 import 并调用被测函数，
  若模块被整目录删除，import 即失败（显式报错，而非静默通过）。
"""

import unittest
from unittest import mock

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability.spans import (
    record_ollama_generation,
    redact_prompt_messages,
)
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


def _result(**overrides) -> OllamaChatResult:
    payload = {
        "content": "答案",
        "thinking": "思考",
        "timings": OllamaTimings(
            load_ms=7000.0,
            prompt_eval_ms=300.0,
            eval_ms=1100.0,
            total_ms=8400.0,
            prompt_tokens=15,
            completion_tokens=27,
        ),
        "timings_available": True,
        "first_token_ms": 7300.0,
        "client_wall_ms": 8500.0,
        "chunk_intervals_ms": (40.0, 41.0),
    }
    payload.update(overrides)
    return OllamaChatResult(**payload)


SAMPLE_PROMPT = [
    {"role": "system", "content": "你是学术研究助手"},
    {"role": "user", "content": "请总结这篇论文的核心贡献与实验设置"},
    {"role": "assistant", "content": "好的，我来梳理一下。"},
]


class RedactPromptMessagesInputVisibilityTests(unittest.TestCase):
    """函数本体修复的核心锁定：content 必须原样保留。"""

    def test_preserves_role_and_original_content_per_message(self):
        out = redact_prompt_messages(SAMPLE_PROMPT)
        self.assertEqual(len(out), len(SAMPLE_PROMPT))
        for original, observed in zip(SAMPLE_PROMPT, out, strict=True):
            self.assertEqual(observed["role"], original["role"])
            # 非恒真：逐字期望原文 content
            self.assertEqual(observed["content"], original["content"])

    def test_content_is_not_cleared(self):
        """回归锁：脱敏 seam 不得再把 content 清零（旧实现缺陷）。"""
        out = redact_prompt_messages(SAMPLE_PROMPT)
        for observed in out:
            self.assertTrue(
                observed["content"],
                f"content 不应为空（被清零），实际 role={observed['role']!r}",
            )

    def test_empty_prompt_returns_empty_list(self):
        self.assertEqual(redact_prompt_messages([]), [])

    def test_missing_content_defaults_to_empty_string(self):
        """缺 content 字段时兜底为空串，role 仍保留（返回结构不变）。"""
        out = redact_prompt_messages([{"role": "user"}])
        self.assertEqual(out, [{"role": "user", "content": ""}])


class RouteLevelInputVisibilityTests(unittest.TestCase):
    """锁定「函数本体修复覆盖全部 route 入口」：route 级入口透传全量 content。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def _capture(self):
        captured = {}

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                captured.setdefault("update", []).append(kwargs)

            def score(self, **kwargs):
                captured.setdefault("scores", []).append(kwargs)

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                captured["start"] = kwargs
                return _FakeObservation()

        return captured, _FakeClient()

    def test_route_entry_reports_full_prompt_content(self):
        """直接走 record_ollama_generation（5 个 route 入口的同款调用），
        断言落到 observation 的 input 非空且包含原文 content。"""
        captured, client = self._capture()
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(obs_client, "get_client", return_value=client):
            record_ollama_generation(
                model="m",
                prompt_messages=redact_prompt_messages(SAMPLE_PROMPT),
                result=_result(),
                route="direct",
            )

        reported_input = captured["start"]["input"]
        self.assertTrue(reported_input, "上报 input 不应为空")
        # 原文 content 必须出现在上报 input 中（逐字期望，非恒真）
        self.assertIn("请总结这篇论文的核心贡献与实验设置", reported_input)
        self.assertIn("你是学术研究助手", reported_input)
        self.assertIn("好的，我来梳理一下。", reported_input)


class FormatFailOpenTests(unittest.TestCase):
    """回归锁：输入格式化已搬进 safe_call，格式化异常不得冒泡到业务。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_formatting_exception_is_swallowed(self):
        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                pass

            def score(self, **kwargs):
                pass

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                return _FakeObservation()

        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(obs_client, "get_client", return_value=_FakeClient()), \
             mock.patch(
                 "backend.app.platform.observability.spans.redact_prompt_messages",
                 side_effect=RuntimeError("格式化炸了"),
             ):
            # 不应抛出：格式化异常被 safe_call 吞掉
            record_ollama_generation(
                model="m",
                prompt_messages=SAMPLE_PROMPT,
                result=_result(),
                route="direct",
            )


if __name__ == "__main__":
    unittest.main()
