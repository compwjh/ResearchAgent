"""本地 Ollama 服务封装测试（spec-011 附带修复：本机请求不得走系统代理）。"""

import unittest
from unittest.mock import patch

import httpx

from backend.app.platform.config import OLLAMA_BASE_URL
from backend.app.platform.ollama import create_chat_model, get_available_models


class OllamaServiceTests(unittest.TestCase):
    def test_chat_model_bypasses_system_proxy(self):
        model = create_chat_model("qwen3.5:9b")
        self.assertFalse(model.client_kwargs["trust_env"])
        self.assertFalse(model.async_client_kwargs["trust_env"])
        self.assertFalse(model.sync_client_kwargs["trust_env"])
        # 跟随配置（允许 .env 覆盖为局域网地址），不硬编码 localhost。
        self.assertEqual(model.base_url, OLLAMA_BASE_URL)

    def test_available_models_bypasses_system_proxy(self):
        request = httpx.Request("GET", "http://localhost:11434/api/tags")
        response = httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]}, request=request)
        with patch.object(httpx, "get", return_value=response) as mock_get:
            models = get_available_models()
        self.assertEqual(models, ["qwen3.5:9b"])
        self.assertFalse(mock_get.call_args.kwargs["trust_env"])


if __name__ == "__main__":
    unittest.main()
