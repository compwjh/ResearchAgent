"""双链路 A/B 基准入口单测（spec-013 task-05）。

**禁止真实调用 Ollama**：patch `backend.app.chat.application.chat_runner.run_chat`，
让 langchain / direct 分别返回可控的假 `ChatRun`（.result 用
`OllamaChatResult` 构造），从而几秒内完成且不触达模型。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

# 基准脚本位于项目根的 scripts/ 目录，非包，故手动加入 sys.path。
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import bench_ollama_routes as bench  # noqa: E402

from backend.app.platform.ollama import ChatRun  # noqa: E402
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings  # noqa: E402


def _fake_run(route, *, result=None, explode=False):
    """构造一个可迭代的假 ChatRun；迭代完后 .result 被设好。

    explode=True 时迭代中途抛异常，模拟单次链路失败。
    """
    run = ChatRun(route=route)
    if result is not None:
        run.result = result

    def _gen():
        if explode:
            raise RuntimeError(f"{route} 中途失败")
        yield {"type": "token", "content": "hi"}
        # 迭代结束时绑定 result（模拟 .result 在迭代后填好）
        run.result = result

    run.events = iter(_gen())
    return run


def _result(route, **overrides):
    payload = dict(
        content="答案",
        thinking="",
        timings=OllamaTimings(
            load_ms=7000.0,
            prompt_eval_ms=300.0,
            eval_ms=1100.0,
            total_ms=8400.0,
            prompt_tokens=15,
            completion_tokens=27,
        ),
        timings_available=True,
        first_token_ms=7300.0,
        client_wall_ms=8500.0,
        chunk_intervals_ms=(40.0, 41.0),
    )
    payload.update(overrides)
    return OllamaChatResult(**payload)


# langchain 无原生 timings（timings_available=False，total_ms=0，overhead 记 0）
LC_RESULT = _result(
    "langchain",
    timings=OllamaTimings(total_ms=0.0),
    timings_available=False,
    first_token_ms=1200.0,
    client_wall_ms=9000.0,
)
# direct 有原生 timings（total_ms=8400，overhead = 8500-8400 = 100）
DC_RESULT = _result("direct")


class _RunChatMock:
    """按 route 返回不同 fake run 的 run_chat 替身，支持指定 route 爆炸。"""

    def __init__(self, explode_routes=()):
        self.explode_routes = set(explode_routes)

    def __call__(self, question, model, *, route=None, prompt=None):
        if route in self.explode_routes:
            return _fake_run("langchain", explode=True)
        if route == "direct":
            return _fake_run("direct", result=DC_RESULT)
        return _fake_run("langchain", result=LC_RESULT)


class RunBenchmarkStructureTests(unittest.TestCase):
    def test_structure_and_default_routes(self):
        # 不传 routes 时应默认跑 langchain,direct（默认替身即跑这两条）。
        with mock.patch.object(bench.chat_runner, "run_chat", _RunChatMock()):
            report = bench.run_benchmark("问题", "model-x")
        self.assertEqual(report["question"], "问题")
        self.assertEqual(report["model"], "model-x")
        self.assertEqual(report["runs"], 1)
        self.assertEqual(set(report["routes"].keys()), {"langchain", "direct"})
        for data in report["routes"].values():
            self.assertIn("samples", data)
            self.assertIn("avg", data)
            self.assertIn("errors", data)
        self.assertIn("diff", report)

    def test_samples_and_avg_present(self):
        with mock.patch.object(bench.chat_runner, "run_chat", _RunChatMock()):
            report = bench.run_benchmark("q", "m", runs=2)
        for data in report["routes"].values():
            # 2 轮无异常应各积累 2 个样本
            self.assertEqual(len(data["samples"]), 2)
            self.assertEqual(len(data["errors"]), 0)
            # avg 含 derive_metrics 的关键字段
            for key in ("ttft_ms", "client_wall_ms", "overhead_ms", "total_ms"):
                self.assertIn(key, data["avg"])


class DiffSemanticsTests(unittest.TestCase):
    """diff 固定语义 = langchain - direct。"""

    def _report(self):
        with mock.patch.object(bench.chat_runner, "run_chat", _RunChatMock()):
            return bench.run_benchmark("q", "m", runs=1)

    def test_diff_equals_langchain_minus_direct(self):
        report = self._report()
        lc = report["routes"]["langchain"]["avg"]
        dc = report["routes"]["direct"]["avg"]
        for key in ("ttft_ms", "client_wall_ms", "overhead_ms", "total_ms"):
            expected = round(lc.get(key, 0.0) - dc.get(key, 0.0), bench._ROUND)
            self.assertAlmostEqual(report["diff"][key], expected, places=3)

    def test_langchain_overhead_zero_due_to_no_timings(self):
        # langchain 无原生 timings，overhead 记 0；direct overhead=100 → diff 为负。
        report = self._report()
        self.assertEqual(report["routes"]["langchain"]["avg"]["overhead_ms"], 0.0)
        self.assertEqual(report["routes"]["direct"]["avg"]["overhead_ms"], 100.0)
        self.assertAlmostEqual(report["diff"]["overhead_ms"], -100.0, places=3)

    def test_total_diff_when_direct_missing_total(self):
        # direct 缺 total_ms（timings_available=False）时 total=0，diff 如实相减不伪造。
        direct_no_total = _result("direct", timings=OllamaTimings(total_ms=0.0), timings_available=False)
        with mock.patch.object(bench.chat_runner, "run_chat") as mock_run:
            def _side(question, model, *, route=None, prompt=None):
                if route == "direct":
                    return _fake_run("direct", result=direct_no_total)
                return _fake_run("langchain", result=LC_RESULT)
            mock_run.side_effect = _side
            report = bench.run_benchmark("q", "m", runs=1)
        # langchain total=0, direct total=0 → diff total 为 0
        self.assertEqual(report["diff"]["total_ms"], 0.0)


class ErrorResilienceTests(unittest.TestCase):
    """某 route 抛异常时记入 errors 且不中断，另一 route 仍有结果。"""

    def test_route_error_recorded_others_survive(self):
        with mock.patch.object(bench.chat_runner, "run_chat", _RunChatMock(explode_routes={"langchain"})):
            report = bench.run_benchmark("q", "m", runs=1)
        # langchain 全失败：0 样本、1 条错误
        self.assertEqual(report["routes"]["langchain"]["samples"], [])
        self.assertEqual(len(report["routes"]["langchain"]["errors"]), 1)
        self.assertIn("RuntimeError", report["routes"]["langchain"]["errors"][0])
        # direct 仍正常产出结果
        self.assertEqual(len(report["routes"]["direct"]["samples"]), 1)
        self.assertEqual(report["routes"]["direct"]["errors"], [])
        self.assertIn("avg", report["routes"]["direct"])

    def test_partial_runs_error_then_success(self):
        # 第一轮爆炸、第二轮成功：errors 记 1，samples 记 1
        calls = {"n": 0}

        def _side(question, model, *, route=None, prompt=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_run("langchain", explode=True)
            return _fake_run("langchain", result=LC_RESULT)

        with mock.patch.object(bench.chat_runner, "run_chat", side_effect=_side):
            report = bench.run_benchmark("q", "m", routes=["langchain"], runs=2)
        self.assertEqual(len(report["routes"]["langchain"]["samples"]), 1)
        self.assertEqual(len(report["routes"]["langchain"]["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
