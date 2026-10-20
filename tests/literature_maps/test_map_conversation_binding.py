import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from backend.app.literature_maps.application.analysis import MapAnalysisService
from backend.app.literature_maps.domain.analysis import MapConversationBinding
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.memory.repository import MemoryRepository
from backend.app.api.routes_conversations import _message_stream


def test_conversation_binding_is_idempotent_and_preserves_project_snapshot(tmp_path):
    map_store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    project = memory.create_project("owner-a", "Fuzzing")
    item = map_store.create_map("owner-a", topic="fuzzing", project_id=project.project_id)
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="A paper", abstract="A real abstract")
    map_store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=map_store, executor=None, memory_repository=memory)

    first = service.create_conversation(
        item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="same"
    )
    second = service.create_conversation(
        item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="same"
    )

    assert first["created"] is True
    assert second["created"] is False
    assert first["conversation_id"] == second["conversation_id"]
    assert second["project_id"] == project.project_id
    assert memory.get_conversation(first["conversation_id"], "owner-a").project_id == project.project_id


def test_abstract_binding_keeps_frozen_context_after_map_delete(tmp_path):
    map_store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    project = memory.create_project("owner-a", "Fuzzing")
    item = map_store.create_map("owner-a", topic="fuzzing", project_id=project.project_id)
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-snapshot",
        title="Snapshot paper",
        abstract="Frozen abstract",
    )
    map_store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=map_store, executor=None, memory_repository=memory)
    created = service.create_conversation(
        item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="snapshot"
    )
    binding = map_store.get_conversation_binding(created["conversation_id"], "owner-a")
    assert binding is not None
    map_store.delete_map(item.map_id, "owner-a")
    context = service.conversation_context(binding, "owner-a", project.project_id)
    assert context["visible_document_ids"] == []
    assert context["context"]["abstract"] == "Frozen abstract"


def test_archived_or_deleted_conversation_does_not_reuse_binding_id(tmp_path):
    map_store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    project = memory.create_project("owner-a", "Fuzzing")
    item = map_store.create_map("owner-a", topic="fuzzing", project_id=project.project_id)
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-archive", title="Archive", abstract="Abstract")
    map_store.add_nodes(item.map_id, "owner-a", [node])
    service = MapAnalysisService(store=map_store, executor=None, memory_repository=memory)
    first = service.create_conversation(item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="reuse")
    memory.update_conversation(first["conversation_id"], "owner-a", status="archived")
    second = service.create_conversation(item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="reuse")
    assert second["conversation_id"] != first["conversation_id"]
    assert memory.get_conversation(first["conversation_id"], "owner-a").status == "archived"
    memory.delete_conversation(second["conversation_id"], "owner-a")
    third = service.create_conversation(item.map_id, node.node_id, "owner-a", evidence_level="abstract", idempotency_key="reuse")
    assert third["conversation_id"] != second["conversation_id"]


def test_binding_lookup_failure_blocks_project_wide_rag_fallback(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    project = memory.create_project("local-user", "Fuzzing")
    conversation = memory.create_conversation("local-user", project_id=project.project_id)
    user = memory.create_message(conversation.conversation_id, "local-user", "user", "find evidence", status="completed")
    assistant = memory.create_message(
        conversation.conversation_id,
        "local-user",
        "assistant",
        "",
        status="pending",
        parent_message_id=user.message_id,
    )
    with patch("backend.app.api.routes_conversations._read_map_conversation_binding", side_effect=RuntimeError("locked")):
        events = [json.loads(frame[6:]) for frame in _message_stream(memory, conversation, user, assistant, "model", "normal") if frame.startswith("data: ")]
    assert any(event.get("code") == "MAP_CONVERSATION_CONTEXT_UNAVAILABLE" for event in events)
    assert events[-1]["status"] == "failed"
    assert memory.get_message(assistant.message_id, "local-user").status == "failed"


def test_map_runtime_failure_does_not_break_explicitly_unbound_chat(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    project = memory.create_project("local-user", "Ordinary")
    conversation = memory.create_conversation("local-user", project_id=project.project_id)
    user = memory.create_message(conversation.conversation_id, "local-user", "user", "ordinary", status="completed")
    assistant = memory.create_message(
        conversation.conversation_id,
        "local-user",
        "assistant",
        "",
        status="pending",
        parent_message_id=user.message_id,
    )

    class Run:
        route = "direct"
        result = None

        @property
        def events(self):
            yield {"type": "token", "content": "ordinary answer"}

    with patch(
        "backend.app.api.routes_conversations._read_map_conversation_binding",
        return_value=(None, None),
    ), patch(
        "backend.app.api.routes_conversations.get_literature_map_service",
        side_effect=RuntimeError("map runtime unavailable"),
    ), patch(
        "backend.app.api.routes_conversations.list_documents_for_project",
        return_value=[],
    ), patch("backend.app.api.routes_conversations.run_chat", return_value=Run()):
        events = [
            json.loads(frame[6:])
            for frame in _message_stream(memory, conversation, user, assistant, "model", "normal", "off")
            if frame.startswith("data: ")
        ]
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "completed"
    assert memory.get_message(assistant.message_id, "local-user").status == "completed"


def test_full_binding_passes_verified_chunker_to_conversation_rag(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = memory.create_conversation("local-user")
    user = memory.create_message(conversation.conversation_id, "local-user", "user", "full evidence", status="completed")
    assistant = memory.create_message(
        conversation.conversation_id,
        "local-user",
        "assistant",
        "",
        status="pending",
        parent_message_id=user.message_id,
    )
    binding = MapConversationBinding(
        "binding-1",
        "local-user",
        "map-1",
        "node-1",
        conversation.conversation_id,
        None,
        "full",
        "source-v1",
        {"title": "Full paper", "abstract": "Abstract", "document_id": "doc-1"},
        "confirmed",
        "request-1",
    )

    class Gate:
        def conversation_context(self, *_args):
            return {"context": binding.context, "visible_document_ids": ["doc-1"], "chunker": "v2"}

    class Run:
        route = "direct"

        @property
        def events(self):
            yield {"type": "token", "content": "answer"}

    calls = []
    with patch(
        "backend.app.api.routes_conversations._read_map_conversation_binding",
        return_value=(binding, Gate()),
    ), patch(
        "backend.app.api.routes_conversations.hybrid_search",
        side_effect=lambda *args, **kwargs: calls.append(kwargs) or [],
    ), patch("backend.app.api.routes_conversations.run_chat", return_value=Run()):
        list(_message_stream(memory, conversation, user, assistant, "model", "normal", "off"))
    assert calls and calls[0]["document_ids"] == ["doc-1"]
    assert calls[0]["chunker"] == "v2"


def test_concurrent_reservation_reports_actual_memory_creator_once_per_round(tmp_path):
    map_path = tmp_path / "maps.sqlite3"
    memory_path = tmp_path / "memory.sqlite3"
    map_store = LiteratureMapStore(map_path)
    memory = MemoryRepository(memory_path)
    project = memory.create_project("owner-a", "Fuzzing")
    item = map_store.create_map("owner-a", topic="fuzzing", project_id=project.project_id)
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-rounds", title="Rounds", abstract="Abstract")
    map_store.add_nodes(item.map_id, "owner-a", [node])

    for round_no in range(8):
        first_store = LiteratureMapStore(map_path)
        second_store = LiteratureMapStore(map_path)
        first_memory = MemoryRepository(memory_path)
        second_memory = MemoryRepository(memory_path)
        services = (
            MapAnalysisService(store=first_store, executor=None, memory_repository=first_memory),
            MapAnalysisService(store=second_store, executor=None, memory_repository=second_memory),
        )
        barrier = Barrier(2)

        def create(service):
            barrier.wait(timeout=5)
            return service.create_conversation(
                item.map_id,
                node.node_id,
                "owner-a",
                evidence_level="abstract",
                idempotency_key=f"round-{round_no}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, services))
        assert len({result["conversation_id"] for result in results}) == 1
        assert sorted(result["created"] for result in results) == [False, True]
