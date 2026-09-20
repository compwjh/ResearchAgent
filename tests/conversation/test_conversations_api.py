import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes_conversations import _message_stream
from backend.app.chat.application.conversation_service import MemoryEvolutionService, MemoryIntent
from backend.app.main import app
from backend.app.memory.repository import MemoryRepository
from backend.app.platform.ollama import ReasoningCapabilities


@pytest.fixture(autouse=True)
def _task03_reasoning_probe(tmp_path, monkeypatch):
    # spec-038：文件记忆层默认读仓库 data/memory（真实 USER.md 可能非空）。
    # 本文件断言装配后的消息结构，必须把 MEMORY_DIR 隔离到 tmp，否则真实画像
    # 会额外注入一条 system 消息（曾导致 test_chat_prompt_* 误报），且测试写入会
    # 污染开发者本机的 data/memory。
    monkeypatch.setattr("backend.app.memory.markdown_store.MEMORY_DIR", tmp_path / "memory")
    capabilities = ReasoningCapabilities("model", ("off", "low", "medium", "high", "xhigh"), "xhigh", "ollama_probe", "now", {effort: f"e-{effort}" for effort in ("off", "low", "medium", "high", "xhigh")})
    with patch("backend.app.platform.ollama.probe_reasoning_capabilities", return_value=capabilities):
        yield


def _events(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def _wait_analysis(client, user_message_id, timeout=2):
    deadline = time.monotonic() + timeout
    result = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/messages/{user_message_id}/memory-analysis")
        if response.status_code == 200:
            result = response.json()
            if result["job"]["status"] in {"completed", "partial", "failed"}:
                return result
        time.sleep(.01)
    return result


class FakeRun:
    route = "langchain"
    result = None

    @property
    def events(self):
        yield {"type": "token", "content": "答复"}


def test_project_and_lazy_conversation_flow(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project = client.post("/api/projects", json={"name": "记忆测试"})
        assert project.status_code == 201
        project_id = project.json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "以后先给结论", "project", .95)):
            response = client.post("/api/conversations/messages", json={"content": "以后回答先给结论", "project_id": project_id, "model": "model"})
        assert response.status_code == 200
        events = _events(response.text)
        assert events[0]["type"] == "meta"
        assert events[-1]["type"] == "done"
        progress = [event for event in events if event["type"] == "progress"]
        assert {event["label"] for event in progress} == {"记忆召回", "回答生成"}
        assert all(event["step_id"] and event["status"] in {"running", "completed", "failed", "skipped"} for event in progress)
        conversation_id = events[0]["conversation_id"]
        analysis = _wait_analysis(client, events[0]["user_message_id"])
        # spec-038 P3：高置信度 explicit（≥0.9）改为直写 MD，审计项记 auto_saved。
        assert analysis and analysis["items"][0]["decision_status"] == "auto_saved"
        messages = client.get(f"/api/conversations/{conversation_id}/messages?target_chars=100")
        assert messages.status_code == 200
        assert len(messages.json()["messages"]) == 2
        evolution_repo = MemoryRepository(tmp_path / "memory.sqlite3")
        raw_kinds = [event.event_kind for event in evolution_repo.list_raw_events(conversation_id, "local-user")]
        assert "user_message" in raw_kinds and "explicit_memory" in raw_kinds


def test_unbound_conversation_does_not_recall_project_memory(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "以后先给结论", "project", .95)):
            client.post("/api/conversations/messages", json={"content": "以后回答先给结论", "project_id": project_id, "model": "model"})
            response = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
        assert response.status_code == 200
        assert not any(event.get("type") == "memory" and event.get("status") == "used" for event in _events(response.text))


def test_ambiguous_memory_is_not_saved(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("ambiguous", "我通常喜欢先说结论", "project", .62)):
            response = client.post("/api/conversations/messages", json={"content": "我通常喜欢先说结论", "project_id": project_id, "model": "model"})
            event = _events(response.text)[0]
            analysis = _wait_analysis(client, event["user_message_id"])
            assert analysis and analysis["items"][0]["decision_status"] == "pending_confirmation"


def test_management_and_lifecycle_api(tmp_path):
    """原 `test_management_and_global_memory_api` 的后继。

    ``/api/memories*`` 端点已随表停用移除；全局画像的管理改由 ``/api/system-rule``
    承载（底层 USER.md），项目的会话生命周期部分原样保留。
    """
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        first = client.post("/api/projects", json={"name": "P1"})
        second = client.post("/api/projects", json={"name": "P2"})
        p1, p2 = first.json()["project_id"], second.json()["project_id"]

        # 长期记忆 CRUD 端点已移除。
        assert client.get("/api/memories").status_code == 404

        # 全局画像：写入 → 读回（内容非空即 enabled）→ 清空。
        assert client.put("/api/system-rule", json={"content": "Concise answers", "enabled": True}).status_code == 200
        assert client.get("/api/system-rule").json()["content"] == "Concise answers"
        assert client.delete("/api/system-rule").status_code == 204
        assert client.get("/api/system-rule").json()["content"] == ""

        conversation = client.post("/api/conversations/messages", json={"content": "hello", "project_id": p1, "model": "missing"})
        # Model validation happens after message persistence; the failed SSE
        # remains recoverable through the conversation history.
        assert conversation.status_code == 200
        repo = __import__("backend.app.memory.repository", fromlist=["MemoryRepository"]).MemoryRepository(tmp_path / "memory.sqlite3")
        conversation_record = repo.create_conversation("local-user", p1, title="Draft")
        repo.create_message(conversation_record.conversation_id, "local-user", "user", "old context", status="completed")
        blocked_move = client.patch(f"/api/conversations/{conversation_record.conversation_id}", json={"project_id": p2})
        assert blocked_move.status_code == 409
        moved = client.patch(f"/api/conversations/{conversation_record.conversation_id}", json={"project_id": p2, "memory_history_policy": "include_prior_history", "confirm_move": True})
        assert moved.status_code == 200
        assert moved.json()["project_id"] == p2
        assert moved.json()["memory_history_policy"] == "include_prior_history"
        assert client.patch(f"/api/projects/{p2}", json={"status": "archived"}).status_code == 200
        assert client.patch(f"/api/projects/{p2}", json={"status": "active"}).status_code == 200
        assert client.get(f"/api/conversations/{conversation_record.conversation_id}").status_code == 200
        assert client.patch(f"/api/conversations/{conversation_record.conversation_id}", json={"status": "archived"}).status_code == 200
        assert client.post(f"/api/conversations/{conversation_record.conversation_id}/restore").json()["status"] == "active"


def test_explicit_global_memory_becomes_auto_saved_analysis_item(tmp_path):
    """原 `test_explicit_global_memory_is_saved_and_recalled_for_unbound_chat` 的后继。

    ``memories`` 停用后，明确表达落审计分析项、也不再有 ``memory: used`` 事件
    （DB 长期记忆段不再注入）。spec-038 P3 起：高置信度 explicit 直写 L1 MD，
    审计项记 ``auto_saved``；scope 仍按显式全局意图记为 global。
    """
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "回答要简洁", "global", .95)):
            saved = client.post("/api/conversations/messages", json={"content": "请记住我：回答要简洁，全局", "model": "model"})
            assert saved.status_code == 200
            saved_event = _events(saved.text)[0]
            analysis = _wait_analysis(client, saved_event["user_message_id"])
            # P3：高置信度 explicit → 直写 MD（auto_saved），scope 仍记为 global。
            assert analysis and analysis["items"][0]["decision_status"] == "auto_saved"
            assert analysis["items"][0]["suggested_scope"] == "global"
            recalled = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
            # 不再有 DB 记忆注入事件（MD 快照由 compose 内部读盘，不发 memory 事件）。
            assert not any(event.get("type") == "memory" for event in _events(recalled.text))


def test_memory_recall_is_advisory_and_chat_completes(tmp_path):
    """原 `test_memory_usage_write_failure_is_advisory_and_chat_completes` 的后继。

    原用例注入 ``mark_memory_used`` 失败来验证「记忆写失败不影响回答」。该写路径已
    随 ``memories`` 停用移除，改为验证仍然存在的等价契约：**摘要召回失败时降级为
    空、记录 failed 步骤，但整轮对话照常完成**。
    """
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch.object(MemoryRepository, "list_recall_summaries", side_effect=RuntimeError("injected lock")):
            response = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
            events = _events(response.text)
        assert any(event.get("type") == "progress" and event.get("kind") == "memory_recall" and event.get("status") == "failed" for event in events)
        assert events[-1]["type"] == "done" and events[-1]["status"] == "completed"


def test_stream_close_persists_interrupted_assistant(tmp_path):
    repo = MemoryRepository(tmp_path / "interrupted.sqlite3")
    conversation = repo.create_conversation("local-user")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="pending", parent_message_id=user.message_id)
    with patch("backend.app.api.routes_conversations.run_chat", return_value=FakeRun()):
        stream = _message_stream(repo, conversation, user, assistant, "model", "normal")
        for frame in stream:
            if '"type": "token"' in frame:
                stream.close()
                break
    assert repo.get_message(assistant.message_id, "local-user").status == "interrupted"
    assert any(step.status == "interrupted" and step.label == "回答生成" for step in repo.list_processing_steps(assistant.message_id, "local-user"))


def test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer(tmp_path):
    repo = MemoryRepository(tmp_path / "provider-interrupted.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="xhigh")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="pending", parent_message_id=user.message_id)

    class BrokenRun:
        route = "direct"
        result = None

        @property
        def events(self):
            yield {"type": "thinking", "content": "先想"}
            yield {"type": "token", "content": "部分答案"}
            raise RuntimeError("provider connection reset")

    with patch("backend.app.api.routes_conversations.run_chat", return_value=BrokenRun()):
        events = _events("\n\n".join(frame for frame in _message_stream(repo, conversation, user, assistant, "model", "normal")))

    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "interrupted"
    assert any(event.get("type") == "error" and event.get("code") == "STREAM_INTERRUPTED" for event in events)
    saved = repo.get_message(assistant.message_id, "local-user")
    assert saved.status == "interrupted"
    assert saved.content == "部分答案"
    # The answer token closes the reasoning subphase before the provider
    # iterator fails; the assistant turn itself still must be interrupted.
    assert saved.reasoning_status == "completed"


def test_provider_initial_iterator_failure_keeps_chat_failed_semantics(tmp_path):
    repo = MemoryRepository(tmp_path / "provider-initial-failure.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="xhigh")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="pending", parent_message_id=user.message_id)

    class FailedRun:
        route = "direct"
        result = None

        @property
        def events(self):
            raise RuntimeError("provider unavailable")
            yield  # pragma: no cover

    with patch("backend.app.api.routes_conversations.run_chat", return_value=FailedRun()):
        events = _events("\n\n".join(frame for frame in _message_stream(repo, conversation, user, assistant, "model", "normal")))

    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "failed"
    assert any(event.get("type") == "error" and event.get("code") == "CHAT_FAILED" for event in events)
    assert repo.get_message(assistant.message_id, "local-user").status == "failed"


def test_provider_failure_after_reasoning_completed_keeps_reasoning_completed(tmp_path):
    """A completed reasoning phase must not regress when no answer token arrived."""
    repo = MemoryRepository(tmp_path / "reasoning-completed-before-failure.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="xhigh")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(
        conversation.conversation_id,
        "local-user",
        "assistant",
        "",
        status="pending",
        parent_message_id=user.message_id,
    )

    class FailedAfterReasoningRun:
        route = "direct"
        result = None

        @property
        def events(self):
            yield {"type": "thinking", "content": "先想"}
            yield {"type": "reasoning_completed", "status": "completed"}
            raise RuntimeError("provider unavailable before first answer token")

    with patch("backend.app.api.routes_conversations.run_chat", return_value=FailedAfterReasoningRun()):
        events = _events("\n\n".join(frame for frame in _message_stream(repo, conversation, user, assistant, "model", "normal")))

    completed = [event for event in events if event.get("type") == "reasoning_completed"]
    assert [event["status"] for event in completed] == ["completed"]
    assert any(event.get("type") == "error" and event.get("code") == "CHAT_FAILED" for event in events)
    assert events[-1]["type"] == "done" and events[-1]["status"] == "failed"
    saved = repo.get_message(assistant.message_id, "local-user")
    assert saved.status == "failed"
    assert saved.reasoning_status == "completed"
    assert saved.content == ""
    steps = repo.list_processing_steps(assistant.message_id, "local-user")
    assert any(step.kind == "generation" and step.status == "failed" for step in steps)


def test_provider_eof_without_done_is_interrupted_at_consumer(tmp_path):
    from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

    repo = MemoryRepository(tmp_path / "provider-eof-without-done.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="off")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="pending", parent_message_id=user.message_id)

    class EofRun:
        route = "direct"
        result = OllamaChatResult("partial", "", OllamaTimings(), False, 1, 2, completed_normally=False)

        @property
        def events(self):
            yield {"type": "token", "content": "partial"}

    with patch("backend.app.api.routes_conversations.run_chat", return_value=EofRun()):
        events = _events("\n\n".join(frame for frame in _message_stream(repo, conversation, user, assistant, "model", "normal", "off")))

    assert events[-1]["type"] == "done" and events[-1]["status"] == "interrupted"
    assert repo.get_message(assistant.message_id, "local-user").status == "interrupted"


def test_reasoning_sse_budget_includes_stream_filter_tail(tmp_path):
    repo = MemoryRepository(tmp_path / "reasoning-sse-budget.sqlite3")
    conversation = repo.create_conversation("local-user", reasoning_effort="xhigh")
    user = repo.create_message(conversation.conversation_id, "local-user", "user", "hello", status="completed")
    assistant = repo.create_message(conversation.conversation_id, "local-user", "assistant", "", status="pending", parent_message_id=user.message_id)

    class CarryRun:
        route = "langchain"
        result = None

        @property
        def events(self):
            # The trailing marker prefix is held by ReasoningStreamFilter and
            # flushed after the token.  It must not add a 20,001st SSE code
            # point after the first delta already consumed the budget.
            yield {"type": "thinking", "content": "a" * 20_000 + "<thi"}
            yield {"type": "token", "content": "answer"}

    with patch("backend.app.api.routes_conversations.run_chat", return_value=CarryRun()):
        events = _events("\n\n".join(frame for frame in _message_stream(repo, conversation, user, assistant, "model", "normal", "xhigh")))

    deltas = [event["content"] for event in events if event["type"] == "reasoning_delta"]
    assert sum(len(delta) for delta in deltas) <= 20_000
    assert repo.get_message(assistant.message_id, "local-user").status == "completed"


def test_retired_memory_endpoints_return_404(tmp_path):
    """原 `test_memory_scope_project_parameter_conflicts_are_stable_errors` 的后继。

    ``/api/memories*`` 已随 ``memories`` 表停用移除，所有旧路径必须稳定 404
    （而不是 500 或静默落到别的语义）。
    """
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        assert client.get(f"/api/memories?scope=global&project_id={project_id}").status_code == 404
        assert client.get("/api/memories").status_code == 404
        assert client.post("/api/memories", json={"scope": "global", "statement": "x", "source_kind": "manual"}).status_code == 404


def test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch(
            "backend.app.chat.application.conversation_service.classify_memory_intent",
            return_value=MemoryIntent("explicit", "回答简洁", "project", .95),
        ):
            response = client.post("/api/conversations/messages", json={"content": "纠正：回答简洁", "project_id": project_id, "model": "model"})
        assert response.status_code == 200 and _events(response.text)[-1]["type"] == "done"
        events = _events(response.text)
        conversation_id = events[0]["conversation_id"]
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        deadline = time.monotonic() + 2
        checkpoint = None
        while time.monotonic() < deadline:
            checkpoint = repo.get_evolution_checkpoint(conversation_id, "local-user")
            if checkpoint and checkpoint.status == "completed":
                break
            time.sleep(0.01)
        assert checkpoint and checkpoint.status == "completed"
        assert repo.list_conversation_summaries(conversation_id, "local-user")
        analysis = repo.get_memory_analysis_job(events[0]["user_message_id"], "local-user")
        # 记忆分析依赖本地 Ollama：可用时 job 可能仍是 running，不可用时会快速 failed。
        # 本用例只验证「消息落库即创建了分析 job」（接线成功），不断言终态，避免与模型耗时耦合。
        assert analysis is not None
        assert analysis.user_message_id == events[0]["user_message_id"]

        with patch("backend.app.api.routes_conversations.run_chat", return_value=FakeRun()), patch.object(
            MemoryEvolutionService, "process_session", side_effect=RuntimeError("worker failure")
        ), patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]):
            failed_worker_response = client.post("/api/conversations/messages", json={"content": "普通问题", "project_id": project_id, "model": "model"})
        assert failed_worker_response.status_code == 200 and _events(failed_worker_response.text)[-1]["type"] == "done"


def test_worker_initialization_failure_does_not_block_sse(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch(
            "backend.app.api.routes_conversations.get_memory_evolution_worker", side_effect=RuntimeError("worker init failure")
        ):
            response = client.post("/api/conversations/messages", json={"content": "worker init must not block", "model": "model"})
        assert response.status_code == 200
        events = _events(response.text)
        assert events[-1]["type"] == "done" and events[-1]["status"] == "completed"
        repo = MemoryRepository(tmp_path / "memory.sqlite3")
        assert repo.list_raw_events(events[0]["conversation_id"], "local-user")


def test_chat_prompt_does_not_duplicate_current_user_message(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        captured = {}
        class CaptureRun(FakeRun):
            pass
        def capture_run(_question, _model, *, messages, reasoning_effort):
            captured["messages"] = messages
            return CaptureRun()
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", side_effect=capture_run
        ):
            response = client.post("/api/conversations/messages", json={"content": "CURRENT_UNIQUE_9f2", "model": "model"})
        assert response.status_code == 200
        messages = captured["messages"]
        assert [message["role"] for message in messages] == ["system", "user"]
        assert [message for message in messages if message["role"] == "user"] == [
            {"role": "user", "content": "CURRENT_UNIQUE_9f2"}
        ]
