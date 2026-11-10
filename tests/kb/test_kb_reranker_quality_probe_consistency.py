"""L-3：固定三文档质量集的跨语言一致性门禁。

Python（``retrieve._RERANKER_HEALTH_PROBE``）与 shell（``deploy/reranker/probe.sh``）
必须都从同一份 ``deploy/reranker/quality-probe.json`` 读取 query/documents。
本测试解析**两侧实际发出**的 POST 请求体，而不是只比源码文本，防止任一侧重新
硬编码出第二份质量集；同时锁定 ``scores[1] 严格居首`` 判定语义逐字不变。
"""

import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from backend.app.knowledge_base.infrastructure import retrieve

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "deploy" / "reranker" / "quality-probe.json"
PROBE_SCRIPT = ROOT / "deploy" / "reranker" / "probe.sh"
RETRIEVE_SOURCE = ROOT / "backend" / "app" / "knowledge_base" / "infrastructure" / "retrieve.py"
STRICT_RANK_EXPRESSION = "scores[1] <= max(scores[0], scores[2])"
_VALID_RESULTS = [
    {"index": 0, "relevance_score": 0.1},
    {"index": 1, "relevance_score": 0.9},
    {"index": 2, "relevance_score": 0.2},
]


class _StubHandler(BaseHTTPRequestHandler):
    """最小 llama-server 替身：记录 POST 体，返回 index 1 严格居首的合法响应。"""

    def _send(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(b'{"status":"ok"}')
        else:
            self._send(b'{"error":"not found"}', status=404)

    def do_POST(self):
        if self.path != "/v1/rerank":
            self._send(b'{"error":"not found"}', status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.server.received.append(json.loads(self.rfile.read(length)))
        self._send(json.dumps({"results": _VALID_RESULTS}).encode("utf-8"))

    def log_message(self, *_args):
        pass


class QualityProbeConsistencyTests(unittest.TestCase):
    def setUp(self):
        with retrieve._health_condition:
            retrieve._health_cache.clear()
            retrieve._health_inflight.clear()

    def tearDown(self):
        with retrieve._health_condition:
            retrieve._health_cache.clear()
            retrieve._health_inflight.clear()

    def _shared(self):
        self.assertTrue(SHARED.is_file(), f"共享质量集缺失：{SHARED}")
        shared = json.loads(SHARED.read_text(encoding="utf-8"))
        self.assertEqual(set(shared), {"query", "documents"})
        self.assertIsInstance(shared["query"], str)
        self.assertTrue(shared["query"].strip())
        documents = shared["documents"]
        self.assertIsInstance(documents, list)
        self.assertEqual(len(documents), 3, "质量集必须恰好三文档")
        self.assertEqual(len(set(documents)), 3)
        for document in documents:
            self.assertIsInstance(document, str)
            self.assertTrue(document)
        return shared

    def test_shared_quality_probe_set_is_the_single_source_of_truth(self):
        """共享文件存在、Python 常量同源，且两侧源码不得再硬编码任何一条文本。"""
        shared = self._shared()
        self.assertEqual(
            retrieve._RERANKER_HEALTH_PROBE,
            (shared["query"], tuple(shared["documents"])),
            "Python 侧常量必须与共享文件逐字一致",
        )
        for path, side in ((RETRIEVE_SOURCE, "Python"), (PROBE_SCRIPT, "shell")):
            with self.subTest(side=side):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(shared["query"], text, f"{side} 不得再硬编码 query")
                for document in shared["documents"]:
                    self.assertNotIn(document, text, f"{side} 不得再硬编码 document")
                self.assertIn(STRICT_RANK_EXPRESSION, text,
                              "scores[1] 严格居首的判定语义必须逐字保留")
        self.assertIn("quality-probe.json", PROBE_SCRIPT.read_text(encoding="utf-8"),
                      "shell 必须显式从共享文件读取质量集")

    def test_python_health_probe_posts_shared_quality_set(self):
        """运行期 health 探针实际 POST 的 body 必须等于共享质量集。"""
        shared = self._shared()
        captured = []

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"results": _VALID_RESULTS})

        detail = retrieve.reranker_health(
            enabled=True, api_model="", transport=httpx.MockTransport(handler),
        )
        self.assertTrue(detail["available"], detail)
        self.assertEqual(len(captured), 1, "health 必须真的执行质量 POST")
        self.assertEqual(captured[0], dict(shared))

    def test_shell_probe_posts_shared_quality_set(self):
        """启动期 probe.sh 实际 POST 的 body 必须等于共享质量集，且仍输出 passed。"""
        shared = self._shared()
        received = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        server.received = received
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {**os.environ, "RERANKER_API_MODEL": ""}
            completed = subprocess.run(
                ["bash", str(PROBE_SCRIPT), f"http://127.0.0.1:{server.server_address[1]}"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("reranker probe passed", completed.stdout)
            self.assertEqual(len(received), 1, "probe.sh 必须真的执行质量 POST")
            self.assertEqual(received[0], dict(shared))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
