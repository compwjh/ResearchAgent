import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


def _events(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


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
        ):
            response = client.post("/api/conversations/messages", json={"content": "以后回答先给结论", "project_id": project_id, "model": "model"})
        assert response.status_code == 200
        events = _events(response.text)
        assert events[0]["type"] == "meta"
        assert events[-1]["type"] == "done"
        progress = [event for event in events if event["type"] == "progress"]
        assert {event["label"] for event in progress} == {"记忆分析", "记忆召回", "回答生成"}
        assert all(event["step_id"] and event["status"] in {"running", "completed", "failed", "skipped"} for event in progress)
        assert any(event["type"] == "memory" and event["status"] == "saved" for event in events)
        conversation_id = events[0]["conversation_id"]
        messages = client.get(f"/api/conversations/{conversation_id}/messages?target_chars=100")
        assert messages.status_code == 200
        assert len(messages.json()["messages"]) == 2


def test_unbound_conversation_does_not_recall_project_memory(tmp_path):
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
        with patch("backend.app.api.routes_conversations.get_available_models", return_value=["model"]), patch(
            "backend.app.api.routes_conversations.run_chat", return_value=FakeRun()
        ):
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
        ):
            response = client.post("/api/conversations/messages", json={"content": "我通常喜欢先说结论", "project_id": project_id, "model": "model"})
        assert any(event.get("status") == "needs_confirmation" for event in _events(response.text))
