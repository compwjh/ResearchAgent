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
from backend.app.memory.markdown_store import MarkdownMemoryStore
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


class _StableBackgroundWorker:
    """受控后台 worker：记录入队但不异步写入测试记忆目录。"""

    def __init__(self):
        self.enqueued = []

    def enqueue(self, *args, **kwargs):
        self.enqueued.append((args, kwargs))
        return None

    def enqueue_session(self, *args, **kwargs):
        self.enqueued.append((args, kwargs))
        return None


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
        stable_analysis_worker = _StableBackgroundWorker()
        stable_evolution_worker = _StableBackgroundWorker()
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", budget_low), \
             patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake_low), \
             patch("backend.app.api.routes_conversations.get_memory_analysis_worker", return_value=stable_analysis_worker), \
             patch("backend.app.api.routes_conversations.get_memory_evolution_worker", return_value=stable_evolution_worker), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp_low = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": new_content, "model": "model"})
        assert resp_low.status_code == 200
        assert not any(a[3] == "auto" for a, k in recorded_low), recorded_low
        assert not (tmp_path / "memory" / "MEMORY.md").exists()

        # 0.80 触发：budget = floor(used/0.80) -> ratio_auto >= 0.8
        budget_high = max(1, math.floor(used / 0.80))
        fake_high, recorded_high = _recording_worker()
        with patch("backend.app.api.routes_conversations.CHAT_TOTAL_TOKEN_BUDGET", budget_high), \
             patch("backend.app.api.routes_conversations.get_compaction_worker", return_value=fake_high), \
             patch("backend.app.api.routes_conversations.get_memory_analysis_worker", return_value=stable_analysis_worker), \
             patch("backend.app.api.routes_conversations.get_memory_evolution_worker", return_value=stable_evolution_worker), \
             patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), \
             patch("backend.app.api.routes_conversations.run_chat", return_value=_FakeRun()), \
             patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=_explicit("简洁")):
            resp_high = client.post(f"/api/conversations/{conv.conversation_id}/messages", json={"content": new_content, "model": "model"})
        assert resp_high.status_code == 200
        auto_high = [(a, k) for a, k in recorded_high if a[3] == "auto"]
        assert len(auto_high) == 1, recorded_high
        # The real route-side compute_context_usage must observe the same
        # stable history baseline used to derive the threshold.
        assert auto_high[0][1]["est_tokens_before"] == used
        assert len(stable_analysis_worker.enqueued) == 2
        assert not (tmp_path / "memory" / "MEMORY.md").exists()


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


def _memory_store_dir(monkeypatch, tmp_path):
    """把文件记忆根目录重定向到临时目录（与真实读盘同源），返回该目录。"""
    memory_dir = tmp_path / "memory"
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", memory_dir)
    return memory_dir


def test_context_usage_counts_system_rule_and_file_memory(tmp_path, monkeypatch):
    """spec-036 Bug1：系统规则(USER.md) + 文件记忆(USER.md/MEMORY.md/项目 MD) 必须计入。

    dry-run 须与真实装配同源：系统规则段经 read_user_memory_or_empty 注入、
    文件记忆段经 compose_chat_prompt(project_id=...) 读盘叠加。
    """
    memory_dir = _memory_store_dir(monkeypatch, tmp_path)
    store = MarkdownMemoryStore(memory_dir)
    store.write_user("用户画像：回答要简洁")                 # USER.md
    store.append_memory(scope="global", project_id=None, content="长期记忆：关注项目A")  # MEMORY.md
    with client_for(tmp_path) as client:
        project_id = _make_project(client)
        store.append_memory(scope="project", project_id=project_id, content="项目记忆：里程碑M1")  # projects/<id>.md
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        conv = repo.create_conversation(OWNER_ID, project_id)
        response = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
    assert response.status_code == 200
    body = response.json()
    kinds = {item["kind"]: item for item in body["breakdown"]}
    # 系统规则段（USER.md 内容）必须出现且带中文 label、token>0。
    assert "system_rule" in kinds
    assert kinds["system_rule"]["label"] == "系统规则"
    assert kinds["system_rule"]["tokens"] > 0
    # 文件记忆段（USER.md / MEMORY.md / 项目 MD）必须出现且 token>0（验证 project_id 已传入）。
    assert "file_memory" in kinds
    assert kinds["file_memory"]["label"] == "文件记忆 (USER.md / MEMORY.md)"
    assert kinds["file_memory"]["tokens"] > 0
    # used_tokens 至少涵盖恒定上下文（系统规则 + 文件记忆），明显大于 0。
    assert body["used_tokens"] >= kinds["system_rule"]["tokens"] + kinds["file_memory"]["tokens"]
    assert body["used_tokens"] > 0


def test_context_usage_empty_memory_fail_open(tmp_path, monkeypatch):
    """空记忆（USER.md / MEMORY.md / 项目 MD 均缺失）时 fail-open：200、不抛异常、不 500。"""
    _memory_store_dir(monkeypatch, tmp_path)  # 空目录，无任何记忆文件
    with client_for(tmp_path) as client:
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        conv = repo.create_conversation(OWNER_ID)  # 无项目、无历史、无记忆
        response = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
    assert response.status_code == 200
    body = response.json()
    kinds = {item["kind"] for item in body["breakdown"]}
    # 空记忆时不得出现恒定段（read_user_memory_or_empty 返回空串，不注入系统规则段）。
    assert "system_rule" not in kinds
    assert "file_memory" not in kinds
    # 空会话 + 空记忆：used_tokens 趋近 0、不为负、不 500。
    assert body["used_tokens"] >= 0


def test_context_usage_project_md_counted_via_project_id(tmp_path, monkeypatch):
    """仅项目 MD 存在（无 USER.md / MEMORY.md）时，file_memory 段必须出现。

    这是 project_id 漏传回归点：旧实现不传 project_id，项目 MD 不会被读盘计入，
    此断言会失败；修复后 compose_chat_prompt 收到 project_id，项目 MD 计入 file_memory。
    """
    memory_dir = _memory_store_dir(monkeypatch, tmp_path)
    store = MarkdownMemoryStore(memory_dir)
    with client_for(tmp_path) as client:
        project_id = _make_project(client)
        store.append_memory(scope="project", project_id=project_id, content="项目记忆：仅此一项")
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        conv = repo.create_conversation(OWNER_ID, project_id)
        response = client.get(f"/api/conversations/{conv.conversation_id}/context-usage")
    assert response.status_code == 200
    body = response.json()
    kinds = {item["kind"]: item for item in body["breakdown"]}
    # 无 USER.md → 无 system_rule 段；但项目 MD 必须在 file_memory 段出现。
    assert "system_rule" not in kinds
    assert "file_memory" in kinds
    assert kinds["file_memory"]["tokens"] > 0
