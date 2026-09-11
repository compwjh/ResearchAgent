import json
import time
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.routes_conversations import _message_stream
from backend.app.chat.application.conversation_service import MemoryEvolutionService, MemoryIntent
from backend.app.memory.repository import MemoryRepository
from backend.app.platform.ollama import ReasoningCapabilities


@pytest.fixture(autouse=True)
def _task03_reasoning_probe():
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


def test_management_and_global_memory_api(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        first = client.post("/api/projects", json={"name": "P1"})
        second = client.post("/api/projects", json={"name": "P2"})
        p1, p2 = first.json()["project_id"], second.json()["project_id"]
        created = client.post("/api/memories", json={"scope": "global", "statement": "Concise", "source_kind": "manual"})
        assert created.status_code == 201
        global_id = created.json()["memory_id"]
        candidate = client.post("/api/memories", json={"scope": "project", "project_id": p1, "statement": "Candidate", "status": "candidate"})
        assert candidate.status_code == 201
        candidate_id = candidate.json()["memory_id"]
        assert client.post(f"/api/memories/{candidate_id}/confirm").json()["status"] == "active"
        edited = client.patch(f"/api/memories/{global_id}", json={"statement": "Concise answers"})
        assert edited.status_code == 200 and edited.json()["memory_id"] != global_id
        assert client.get("/api/memories?scope=global").json()["memories"][0]["statement"] == "Concise answers"
        assert client.get(f"/api/memories/{edited.json()['memory_id']}/evidence").status_code == 200
        assert client.delete(f"/api/memories/{edited.json()['memory_id']}").status_code == 204
        assert client.post(f"/api/memories/{edited.json()['memory_id']}/undo").json()["status"] == "active"

        conversation = client.post("/api/conversations/messages", json={"content": "hello", "project_id": p1, "model": "missing"})
        # Model validation runs before creating a conversation; use repository
        # through the management endpoint for the lifecycle assertions below.
        assert conversation.status_code in {400, 503}
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


def test_explicit_global_memory_is_saved_and_recalled_for_unbound_chat(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "回答要简洁", "global", .95)):
            saved = client.post("/api/conversations/messages", json={"content": "请记住我：回答要简洁，全局", "model": "model"})
            assert saved.status_code == 200
            saved_event = _events(saved.text)[0]
            analysis = _wait_analysis(client, saved_event["user_message_id"])
            assert analysis and analysis["items"][0]["decision_status"] == "auto_saved"
            recalled = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
            assert any(event.get("status") == "used" and event.get("scope") == "global" for event in _events(recalled.text))


def test_memory_usage_write_failure_is_advisory_and_chat_completes(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ), patch("backend.app.chat.application.conversation_service.classify_memory_intent", return_value=MemoryIntent("explicit", "回答要简洁", "global", .95)):
            saved = client.post("/api/conversations/messages", json={"content": "请记住我：简洁回答，全局", "model": "model"})
            assert saved.status_code == 200
            with patch.object(MemoryRepository, "mark_memory_used", side_effect=RuntimeError("injected lock")):
                response = client.post("/api/conversations/messages", json={"content": "普通问题", "model": "model"})
            events = _events(response.text)
            assert any(event.get("type") == "memory" and event.get("status") == "skipped" for event in events)
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


def test_memory_scope_project_parameter_conflicts_are_stable_errors(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        assert client.get(f"/api/memories?scope=global&project_id={project_id}").status_code == 400
        assert client.get("/api/memories?scope=project").status_code == 400
        assert client.get("/api/memories?scope=project&project_id=missing").status_code == 404


def test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
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
        assert analysis and analysis.status in {"completed", "partial", "failed"}

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
