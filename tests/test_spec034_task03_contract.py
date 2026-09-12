"""Spec034 Task03 — conversational intake contracts."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.api.routes_conversations import (
    _intake_stream,
    _start_message,
    get_messages,
    remove_project,
)
from backend.app.api.schemas import ConversationMessageRequest
from backend.app.memory.repository import MemoryRepository
from backend.app.platform.bootstrap import override_provider
from backend.app.research.application.intake import (
    BEGIN_RESEARCH_INTAKE_SCHEMA,
    ResearchIntakeCoordinator,
)
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.service import SkillRegistryService


def _setup(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation("owner-a", None, "intake")
    store = ResearchStore(tmp_path / "research.sqlite3")
    registry = SkillRegistryService(
        tmp_path / "skills", tmp_path / "skill-state.json"
    )
    return memory, store, conversation, registry


def test_registered_intake_schema_has_blocking_fields(tmp_path):
    assert BEGIN_RESEARCH_INTAKE_SCHEMA["type"] == "object"
    assert set(BEGIN_RESEARCH_INTAKE_SCHEMA["required"]) >= {
        "conversation_id", "message_id", "fields"
    }


def test_ordinary_and_ambiguous_messages_do_not_create_session(tmp_path):
    _memory, store, conversation, registry = _setup(tmp_path)
    coordinator = ResearchIntakeCoordinator(store, _memory, registry)
    ordinary = coordinator.handle_message(
        conversation.conversation_id, "owner-a", "m1", "你好，今天怎么样？"
    )
    ambiguous = coordinator.handle_message(
        conversation.conversation_id, "owner-a", "m2", "帮我查一下软件供应链攻击"
    )
    assert ordinary.status == "ordinary"
    assert ambiguous.status == "clarification"
    assert store.list_sessions("owner-a") == []


def test_explicit_request_activates_skill_and_collects_defaults(tmp_path):
    memory, store, conversation, registry = _setup(tmp_path)
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\n\nbody",
        encoding="utf-8",
    )
    coordinator = ResearchIntakeCoordinator(store, memory, registry)
    _conversation, user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "research"
    )
    result = coordinator.handle_message(
        conversation.conversation_id,
        "owner-a",
        user.message_id,
        "帮我做一个深度研究，主题是软件供应链攻击，目标是总结攻击面，时间范围是2020-2024。",
    )
    assert result.status == "intake"
    assert result.activation["skill"]["name"] == "deep-research-orchestration"
    assert result.missing == []
    assert result.session is not None
    fields = {item.field_name: item for item in store.list_intake_fields(result.session.intake_draft_id, "owner-a")}
    assert json.loads(fields["topic"].value_json) == "软件供应链攻击"
    assert fields["topic"].source == "user_explicit"
    assert fields["objective"].confirmation_status == "confirmed"
    assert json.loads(fields["time_range"].value_json) == {"from": 2020, "to": 2024}
    assert fields["language"].source == "system_default"


def test_repeated_message_is_idempotent_and_active_conflict_is_stable(tmp_path):
    memory, store, conversation, registry = _setup(tmp_path)
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody",
        encoding="utf-8",
    )
    coordinator = ResearchIntakeCoordinator(store, memory, registry)
    _conversation, user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "帮我做深度研究，研究量子安全"
    )
    first = coordinator.handle_message(
        conversation.conversation_id, "owner-a", user.message_id, "帮我做深度研究，研究量子安全"
    )
    replay = coordinator.handle_message(
        conversation.conversation_id, "owner-a", user.message_id, "帮我做深度研究，研究量子安全"
    )
    assert replay.session.research_session_id == first.session.research_session_id
    assert len(store.list_sessions("owner-a")) == 1
    _conversation, second_user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "帮我做深度研究，研究云安全"
    )
    conflict = coordinator.handle_message(
        conversation.conversation_id, "owner-a", second_user.message_id, "帮我做深度研究，研究云安全"
    )
    assert conflict.status == "active_conflict"
    assert {choice["id"] for choice in conflict.choices} == {
        "modify_current", "cancel_then_new", "new_conversation"
    }


def test_follow_up_messages_restore_and_complete_blocking_fields(tmp_path):
    memory, store, conversation, registry = _setup(tmp_path)
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody",
        encoding="utf-8",
    )
    coordinator = ResearchIntakeCoordinator(store, memory, registry)
    _conversation, first_user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "帮我做深度研究，研究量子安全"
    )
    first = coordinator.handle_message(
        conversation.conversation_id, "owner-a", first_user.message_id, first_user.content
    )
    assert first.missing == ["objective", "time_range"]
    _conversation, second_user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "目标是总结防御方法"
    )
    second = coordinator.handle_message(
        conversation.conversation_id, "owner-a", second_user.message_id, second_user.content
    )
    assert second.missing == ["time_range"]
    _conversation, third_user, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "2020-2024"
    )
    third = coordinator.handle_message(
        conversation.conversation_id, "owner-a", third_user.message_id, third_user.content
    )
    assert third.missing == []
    assert store.get_intake_draft(third.session.research_session_id, "owner-a").status == "complete"


def test_skill_activation_locks_target_and_checks_declared_tools(tmp_path):
    memory, store, conversation, _registry = _setup(tmp_path)
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: [unknown-tool]\n---\nbody",
        encoding="utf-8",
    )
    registry = SkillRegistryService(tmp_path / "skills", tmp_path / "skill-state.json")

    class EmptyToolRegistry:
        def get_tool(self, _name):
            return None

    coordinator = ResearchIntakeCoordinator(store, memory, registry, EmptyToolRegistry())
    assert coordinator.activate_skill("usenix-catalog-orchestration")["error"]["code"] == "CAPABILITY_NOT_AUTHORIZED"
    rejected = coordinator.activate_skill()
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "CAPABILITY_NOT_AUTHORIZED"


def test_active_conflict_sse_is_interactive_and_does_not_fail_assistant(tmp_path):
    memory, store, conversation, registry = _setup(tmp_path)
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody",
        encoding="utf-8",
    )
    coordinator = ResearchIntakeCoordinator(store, memory, registry)
    _conversation, first, _assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "帮我做深度研究，研究量子安全"
    )
    coordinator.handle_message(conversation.conversation_id, "owner-a", first.message_id, first.content)
    _conversation, second, second_assistant = memory.create_message_pair(
        conversation.conversation_id, "owner-a", "帮我做深度研究，研究云安全"
    )
    result = coordinator.handle_message(conversation.conversation_id, "owner-a", second.message_id, second.content)
    frames = "".join(_intake_stream(memory, conversation, second, second_assistant, result, "model", "normal", "off"))
    assert '"type": "intake"' in frames
    assert all(choice in frames for choice in ("modify_current", "cancel_then_new", "new_conversation"))
    assert memory.get_message(second_assistant.message_id, "owner-a").status == "completed"


def test_model_preflight_after_message_persistence_keeps_user_message(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    payload = ConversationMessageRequest(content="帮我做深度研究", model="missing")
    unavailable = HTTPException(
        status_code=503,
        detail={"code": "MODEL_UNAVAILABLE", "message": "模型不可用", "retryable": True},
    )
    with override_provider("memory_repository", repo), patch(
        "backend.app.api.routes_conversations._validate_model", side_effect=unavailable
    ):
        response = _start_message(payload)
        async def drain():
            return "".join([chunk async for chunk in response.body_iterator])
        body = asyncio.run(drain())
    assert '"MODEL_UNAVAILABLE"' in body
    conversations, _cursor = repo.list_conversations("local-user")
    assert len(conversations) == 1
    messages, _cursor = repo.list_messages(conversations[0].conversation_id, "local-user")
    assert any(item.role == "user" and item.content == "帮我做深度研究" for item in messages)


def test_intake_dependency_failure_does_not_block_ordinary_chat(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = repo.create_conversation("local-user", title="ordinary")

    class BrokenCoordinator:
        def handle_message(self, *_args):
            raise RuntimeError("research store unavailable")

    resolution = SimpleNamespace(effort="off", capabilities=SimpleNamespace(source="test"))
    with override_provider("memory_repository", repo), override_provider(
        "research_intake_coordinator", BrokenCoordinator()
    ), patch("backend.app.api.routes_conversations._validate_model"), patch(
        "backend.app.api.routes_conversations._resolve_request_effort", return_value=resolution
    ), patch(
        "backend.app.api.routes_conversations._message_stream", return_value=iter(["data: original-chat\n\n"])
    ):
        response = _start_message(
            ConversationMessageRequest(content="普通问题", model="model"),
            conversation.conversation_id,
        )
        async def drain():
            return "".join([chunk async for chunk in response.body_iterator])
        body = asyncio.run(drain())
    assert "original-chat" in body
    messages, _cursor = repo.list_messages(conversation.conversation_id, "local-user")
    assert any(item.role == "user" and item.content == "普通问题" for item in messages)
    assistant = next(item for item in messages if item.role == "assistant")
    assert any(step.kind == "research_intake" and step.status == "failed" for step in repo.list_processing_steps(assistant.message_id, "local-user"))


def test_project_document_detach_failure_returns_stable_error(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("local-user", "P")
    with override_provider("memory_repository", repo), patch(
        "backend.app.api.routes_conversations.clear_project_document_associations",
        side_effect=RuntimeError("detach failed"),
    ):
        try:
            remove_project(project.project_id)
        except HTTPException as error:
            assert error.status_code == 503
            assert error.detail["code"] == "DOCUMENT_ASSOCIATION_FAILED"
        else:
            raise AssertionError("expected stable document association error")


def test_message_history_restores_persisted_intake_projection_after_refresh(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation("local-user", None, "intake")
    store = ResearchStore(tmp_path / "research.sqlite3")
    skills_dir = tmp_path / "skills" / "deep-research-orchestration"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: deep-research-orchestration\ndescription: research\ntools: []\n---\nbody",
        encoding="utf-8",
    )
    registry = SkillRegistryService(tmp_path / "skills", tmp_path / "skill-state.json")
    _conversation, user, assistant = memory.create_message_pair(
        conversation.conversation_id,
        "local-user",
        "帮我做一个深度研究，主题是软件供应链攻击，目标是总结攻击面，时间范围是2020-2024。",
    )
    result = ResearchIntakeCoordinator(store, memory, registry).handle_message(
        conversation.conversation_id, "local-user", user.message_id, user.content
    )
    "".join(_intake_stream(memory, conversation, user, assistant, result, "model", "normal", "off"))

    refreshed = MemoryRepository(tmp_path / "memory.sqlite3")
    with override_provider("memory_repository", refreshed):
        history = get_messages(conversation.conversation_id, target_chars=4000)
    assistant_item = next(item for item in history["messages"] if item["role"] == "assistant")
    intake = assistant_item["research_intake"]
    assert assistant_item["intake"] == intake
    assert intake["status"] == "intake"
    assert {field["field_name"] for field in intake["fields"]} >= {"topic", "objective", "time_range"}
    assert intake["fields"][0]["source"]
    assert "confidence" in intake["fields"][0]
    assert "confirmation_status" in intake["fields"][0]
    assert intake["missing"] == []
    assert intake["question"] is None
    assert intake["skill"]["skill_id"] == "deep-research-orchestration"
    assert "body" not in intake["skill"]


def test_message_history_keeps_ordinary_messages_free_of_intake_fields(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "local-user", "普通聊天", None, "model", "normal", None
    )
    with override_provider("memory_repository", MemoryRepository(tmp_path / "memory.sqlite3")):
        history = get_messages(conversation.conversation_id, target_chars=4000)
    assert all("intake" not in item and "research_intake" not in item for item in history["messages"])
    assert {item["message_id"] for item in history["messages"]} == {user.message_id, assistant.message_id}
