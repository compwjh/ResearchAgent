import unittest
from unittest.mock import patch

from backend.app.agents.article_agent import classify_intent


class _FakeModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, _prompt):
        return type("Response", (), {"content": self._content})()


class IntentClassificationTests(unittest.TestCase):
    def test_strong_download_shortcut_skips_llm(self):
        intent, confidence = classify_intent("下载论文 Attention is all you need")
        self.assertEqual(intent, "download_paper")
        self.assertEqual(confidence, 0.96)

    @patch("backend.app.services.ollama.create_chat_model")
    def test_llm_returns_chat(self, mock_create):
        mock_create.return_value = _FakeModel('{"intent": "chat", "confidence": 0.9}')
        intent, confidence = classify_intent("帮我写一首关于春天的诗")
        self.assertEqual(intent, "chat")
        self.assertAlmostEqual(confidence, 0.9)

    @patch("backend.app.services.ollama.create_chat_model")
    def test_llm_returns_download(self, mock_create):
        mock_create.return_value = _FakeModel('{"intent": "download_paper", "confidence": 0.95}')
        intent, confidence = classify_intent("帮我拿到这篇文献的 PDF")
        self.assertEqual(intent, "download_paper")
        self.assertAlmostEqual(confidence, 0.95)

    @patch("backend.app.services.ollama.create_chat_model", side_effect=Exception("ollama down"))
    def test_llm_exception_falls_back_to_chat(self, mock_create):
        intent, confidence = classify_intent("随便一句话")
        self.assertEqual(intent, "chat")
        self.assertEqual(confidence, 0.5)

    @patch("backend.app.services.ollama.create_chat_model")
    def test_llm_unexpected_output_falls_back_to_chat(self, mock_create):
        mock_create.return_value = _FakeModel("我不是 JSON")
        intent, confidence = classify_intent("你好")
        self.assertEqual(intent, "chat")
        self.assertEqual(confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
