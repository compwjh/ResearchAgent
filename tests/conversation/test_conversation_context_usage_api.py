"""Spec025 Task04：上下文用量端点、手动压缩端点、80% 自动触发。

覆盖：404 越权、409 已有非终态 job、手动入队成功、dry-run 不触发 RAG、
ratio 计算与 budget=0 不崩溃、0.79 不触发 / 0.80 触发自动压缩、
自动入队失败不影响回答。
"""
import json
import math
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.memory.repository import OWNER_ID, MemoryRepository


def _events(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


@contextmanager
def client_for(tmp_path):
    # patch 必须在整个请求期间生效（TestClient 惰性解析 provider）。
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        yield TestClient(app)


def _make_project(client):
    return client.post("/api/projects", json={"name": "P"}).json()["project_id"]


class _FakeRun:
    route = "langchain"
    result = None

    @property
    def events(self):
        yield {"type": "token", "content": "答复"}


def _explicit(statement):
    from backend.app.chat.application.conversation_service import MemoryIntent

    return MemoryIntent("explicit", statement, "project", 0.95)


def test_context_usage_404_unknown_conversation(tmp_path):
    with client_for(tmp_path) as client:
        response = client.get("/api/conversations/nonexistent/context-usage")
    assert response.status_code == 404


def test_context_usage_404_other_owner(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with patch("backend.app.memory.repository.default_database_path", return_value=db_path):
        other = MemoryRepository(db_path)
        conv = other.create_conversation("someone-else")
        client = TestClient(app)
        response = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
    assert response.status_code == 404


def test_context_usage_returns_usage(tmp_path):
    with client_for(tmp_path) as client:
        project_id = _make_project(client)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("回答要简洁")):
            resp = client.post("/api/conversations/messages", json={"content": "普通问题", "project_id": project_id, "model": "model"})
        cid = _events(resp.text)[0]["conversation_id"]
        usage = client.get(f"/api/conversations/{cid}/context-usage")
        assert usage.status_code == 200
        body = usage.json()
        assert set(body.keys()) == {"used_tokens", "budget_tokens", "ratio", "segment_count", "compaction_status", "breakdown"}
        assert isinstance(body["breakdown"], list)
        for item in body["breakdown"]:
            assert set(item.keys()) == {"kind", "label", "tokens", "bytes"}
            assert isinstance(item["tokens"], int) and item["tokens"] >= 0
            assert isinstance(item["bytes"], int) and item["bytes"] >= 0
        assert body["budget_tokens"] == 20000  # spec-038 P3：预算默认值 8000 → 20000
        assert body["compaction_status"] == "idle"
        assert body["segment_count"] == 0
        assert body["used_tokens"] >= 0
        assert 0.0 <= body["ratio"] <= 1.0


def test_context_usage_dry_run_does_not_trigger_rag(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        project_id = _make_project(client)
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID, project_id)
        repo.create_message(conv.conversation_id, OWNER_ID, "user", "你好", status="completed")
        # 即便存在可见文档(hybrid_search 的调用前置)且 hybrid_search 抛异常，dry-run 也绝不应调用它
        mock_hybrid = MagicMock(side_effect=RuntimeError("hybrid_search must not run"))
        with patch("backend.app.api.routes_conversations.hybrid_search", mock_hybrid), \
             patch("backend.app.api.routes_conversations.list_documents_for_project", return_value=[{"document_id": "d1"}]):
            response = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
        assert response.status_code == 200
        assert not mock_hybrid.called


def test_compaction_manual_success(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        repo.create_message(conv.conversation_id, OWNER_ID, "user", "hi", status="completed")
        response = client.post(f"/api/conversations/{conv.conversation_id}/compactions")
    assert response.status_code == 200
    body = response.json()
    assert body["trigger"] == "manual"
    assert body["job_id"]
    assert body["status"] == "queued"
    repo = MemoryRepository(db_path)
    job = repo.get_latest_compaction_job(conv.conversation_id, OWNER_ID)
    assert job is not None and job.trigger == "manual"


def test_compaction_409_when_active_job_exists(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        repo.create_message(conv.conversation_id, OWNER_ID, "user", "hi", status="completed")
        # 直接插入一个非终态(queued) job，不启动 worker
        repo.create_compaction_job(conv.conversation_id, OWNER_ID, trigger="manual")
        response = client.post(f"/api/conversations/{conv.conversation_id}/compactions")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "COMPACTION_IN_PROGRESS"


def test_context_usage_ratio_and_budget_zero(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        repo.create_message(conv.conversation_id, OWNER_ID, "user", "这是一段历史内容用于估算 token", status="completed")
        usage = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
        assert usage.status_code == 200
        assert usage.json()["budget_tokens"] == 20000  # spec-038 P3：预算默认值 8000 → 20000
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", 0):
            usage0 = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
        assert usage0.status_code == 200
        assert usage0.json()["budget_tokens"] == 0
        assert usage0.json()["ratio"] == 1.0


def _recording_worker():
    recorded = []
    fake = MagicMock()

    def _enqueue(*a, **k):
        recorded.append((a, k))
        return MagicMock(job_id="j", status="queued")

    fake.enqueue = _enqueue
    return fake, recorded


def test_auto_compaction_below_threshold_does_not_enqueue(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        repo.create_message(conv.conversation_id, OWNER_ID, "user", "短历史", status="completed")
        fake, recorded = _recording_worker()
        with patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": "新问题", "model": "model"})
        assert resp.status_code == 200 and _events(resp.text)[-1]["type"] == "done"
        assert not any(a[3] == "auto" for a, k in recorded), recorded


def test_auto_compaction_threshold_boundary(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        long_text = "内容" * 1000  # 2000 字符
        for _ in range(20):
            repo.create_message(conv.conversation_id, OWNER_ID, "user", long_text, status="completed")
        usage = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
        used = usage.json()["used_tokens"]
        new_content = long_text  # 等长，避免窗口替换导致 token 骤降

        # 0.79 不触发：budget = ceil(used/0.79) -> ratio_auto < 0.8
        budget_low = math.ceil(used / 0.79)
        fake_low, recorded_low = _recording_worker()
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", budget_low), \
             patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake_low), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp_low = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": new_content, "model": "model"})
        assert resp_low.status_code == 200
        assert not any(a[3] == "auto" for a, k in recorded_low), recorded_low

        # 0.80 触发：budget = floor(used/0.80) -> ratio_auto >= 0.8
        budget_high = max(1, math.floor(used / 0.80))
        fake_high, recorded_high = _recording_worker()
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", budget_high), \
             patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake_high), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp_high = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": new_content, "model": "model"})
        assert resp_high.status_code == 200
        assert any(a[3] == "auto" for a, k in recorded_high), recorded_high


def test_auto_compaction_enqueue_failure_does_not_block(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    with client_for(tmp_path) as client:
        repo = MemoryRepository(db_path)
        conv = repo.create_conversation(OWNER_ID)
        long_text = "内容" * 1000
        for _ in range(20):
            repo.create_message(conv.conversation_id, OWNER_ID, "user", long_text, status="completed")
        usage = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
        used = usage.json()["used_tokens"]
        budget = max(1, math.floor(used / 0.80))  # ratio >= 0.8 -> 触发
        fake = MagicMock()
        fake.enqueue = MagicMock(side_effect=RuntimeError("injected compaction failure"))
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", budget), \
             patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": long_text, "model": "model"})
    # 自动入队失败不得影响本次回答
    assert resp.status_code == 200
    assert _events(resp.text)[-1]["type"] == "done"
