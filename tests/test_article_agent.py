import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app.article_assistant.application.article_agent import build_intent_graph, normalize_query
from backend.app.article_assistant.domain.article import ArticleTask
from backend.app.article_assistant.infrastructure.task_store import TaskStore


class _FakeChatModel:
    """Deterministic stand-in for the intent-classification LLM."""

    def __init__(self, intent: str, confidence: float = 0.9):
        self._payload = json.dumps({"intent": intent, "confidence": confidence})

    def invoke(self, _prompt):
        class _Response:
            content = self._payload

        return _Response()


class ArticleAgentTests(unittest.TestCase):
    @mock.patch(
        "backend.app.platform.ollama.create_chat_model",
        lambda _model: _FakeChatModel("download_paper"),
    )
    def test_required_paper_titles_route_to_download(self):
        # 论文标题经大模型判断应归为下载意图（生产环境由 LLM 判定，测试用假模型固定）。
        for title in (
            "Planning as Graphs: Adaptive Agentic Planning for LLM Agents",
            "SoK: Agentic Skills -- Beyond Tool Use in LLM Agents",
        ):
            result = build_intent_graph().invoke({"query": title})
            self.assertEqual(result["intent"], "download_paper")

    def test_normalize_query(self):
        self.assertEqual(normalize_query("  请  下载论文，  "), "请 下载论文,")

    def test_intent_graph_routes_download(self):
        # 强下载触发词应直接命中 download_paper，且置信度高于阈值。
        result = build_intent_graph().invoke({"query": "请下载这篇论文"})
        self.assertEqual(result["intent"], "download_paper")
        self.assertGreaterEqual(result["confidence"], 0.9)

    @mock.patch(
        "backend.app.platform.ollama.create_chat_model",
        lambda _model: _FakeChatModel("download_paper"),
    )
    def test_title_only_input_routes_download(self):
        # 仅有标题、无显式动词时由大模型判断；此处假模型判定为下载意图。
        result = build_intent_graph().invoke({"query": "Attention Is All You Need"})
        self.assertEqual(result["intent"], "download_paper")

    def test_intent_graph_does_not_route_unknown_to_download(self):
        result = build_intent_graph().invoke({"query": "帮我处理实验数据"})
        self.assertNotEqual(result["intent"], "download_paper")

    def test_task_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.sqlite3")
            task = ArticleTask(
                task_id="task-1",
                query="请下载论文",
                normalized_query="请下载论文",
                intent="download_paper",
                intent_confidence=0.96,
            )
            store.save(task)
            restored = store.get("task-1")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.intent, "download_paper")


if __name__ == "__main__":
    unittest.main()
