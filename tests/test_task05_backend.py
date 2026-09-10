"""Spec022 Task05 backend acceptance probes."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api import routes_conversations
from backend.app.chat.application.conversation_service import compose_chat_prompt
from backend.app.knowledge_base.application import (
    clear_project_document_associations,
    create_uploaded_document,
    filter_hits_for_project,
    set_document_project,
)
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.knowledge_base.infrastructure.index import point_id
from backend.app.knowledge_base.infrastructure.migration import patch_knowledge_document
from backend.app.knowledge_base.infrastructure.prompts import citation_payloads
from backend.app.knowledge_base.infrastructure import retrieve as retrieve_module
from backend.app.main import app
from backend.app.memory.repository import MemoryRepository


def _events(text):
    return [json.loads(item[6:]) for item in text.split("\n\n") if item.startswith("data: ")]


def test_document_project_association_preserves_source_identity_and_detach(tmp_path: Path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    document = create_uploaded_document("note.md", "text/markdown", b"# source\n", meta_path=meta, papers_dir=papers)["document"]
    original = json.loads(meta.read_text(encoding="utf-8"))[0]
    associated = set_document_project(document["document_id"], "project-a", meta_path=meta, papers_dir=papers)
    assert associated["project_id"] == "project-a"
    assert associated["document_id"] == original["document_id"]
    assert associated["source_sha256"] == original["source_sha256"]
    assert (papers / original["stored_name"]).read_bytes() == b"# source\n"
    detached = clear_project_document_associations("project-a", meta_path=meta, papers_dir=papers)
    assert detached == 1
    after = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert "project_id" not in after
    assert after["document_id"] == original["document_id"]
    assert after["chunkers"] == original["chunkers"]
    assert (papers / original["stored_name"]).exists()
    associations = json.loads(meta.with_name("project-associations.json").read_text(encoding="utf-8"))
    assert associations["associations"] == {}


def test_project_association_keeps_canonical_schema_and_status_patch(tmp_path: Path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    document = create_uploaded_document("note.md", "text/markdown", b"# source\n", meta_path=meta, papers_dir=papers)["document"]
    set_document_project(document["document_id"], "project-a", meta_path=meta, papers_dir=papers)
    canonical = json.loads(meta.read_text(encoding="utf-8"))[0]
    assert "project_id" not in canonical
    patched = patch_knowledge_document(meta, document["document_id"], status="indexed")
    assert patched["status"] == "indexed"
    assert "project_id" not in json.loads(meta.read_text(encoding="utf-8"))[0]


def test_project_visibility_excludes_other_project_documents(tmp_path: Path):
    meta = tmp_path / "papers.json"
    papers = tmp_path / "papers"
    first = create_uploaded_document("a.md", "text/markdown", b"a", meta_path=meta, papers_dir=papers)["document"]
    second = create_uploaded_document("b.md", "text/markdown", b"b", meta_path=meta, papers_dir=papers)["document"]
    set_document_project(first["document_id"], "project-a", meta_path=meta, papers_dir=papers)
    set_document_project(second["document_id"], "project-b", meta_path=meta, papers_dir=papers)
    hits = [Hit(first["document_id"], "a.md", None, 0, "a", .9), Hit(second["document_id"], "b.md", None, 0, "b", .8)]
    assert [hit.paper_id for hit in filter_hits_for_project(hits, "project-a", meta_path=meta)] == [first["document_id"]]
    assert [hit.paper_id for hit in filter_hits_for_project(hits, None, meta_path=meta)] == []


def test_compose_chat_prompt_keeps_current_question_and_rag_budget():
    hit = Hit("doc-1", "source.md", 2, 0, "EVIDENCE_UNIQUE " * 200, .9)
    prompt = compose_chat_prompt(
        "CURRENT_UNIQUE_TASK",
        [],
        [],
        "INSTRUCTION_UNIQUE",
        [],
        rag_hits=[hit],
        rag_budget_chars=100,
        history_budget_chars=20,
    )
    assert "INSTRUCTION_UNIQUE" in prompt
    assert "CURRENT_UNIQUE_TASK" in prompt
    assert len(prompt) < 700


def test_conversation_sources_follow_final_token_and_are_bounded(tmp_path: Path):
    class FakeRun:
        route = "langchain"
        result = None

        @property
        def events(self):
            yield {"type": "token", "content": "ANSWER"}

    project_id = None
    with patch("backend.app.memory.repository.default_database_path", return_value=tmp_path / "memory.sqlite3"):
        client = TestClient(app)
        project_id = client.post("/api/projects", json={"name": "RAG project"}).json()["project_id"]
        hits = [Hit(f"doc-{index}", f"doc-{index}.md", None, index, f"chunk-{index}", 1.0) for index in range(8)]
        with patch.object(routes_conversations, "get_available_models", return_value=["model"]), patch.object(routes_conversations, "run_chat", return_value=FakeRun()), patch.object(routes_conversations, "list_documents_for_project", return_value=[{"document_id": "doc-0"}]), patch.object(routes_conversations, "hybrid_search", return_value=hits) as search:
            response = client.post("/api/conversations/messages", json={"content": "find evidence", "project_id": project_id, "model": "model"})
    assert response.status_code == 200
    events = _events(response.text)
    source = next(item for item in events if item["type"] == "sources")
    assert len(source["sources"]) == 5
    assert events.index(source) > max(index for index, item in enumerate(events) if item["type"] == "token")
    assert events[-1]["type"] == "done"
    assert all(item["document_id"] == item["paper_id"] and item["source_url"].startswith("/api/kb/documents/") for item in source["sources"])
    assert search.call_args.kwargs["document_ids"] == ["doc-0"]


def test_citation_source_document_chunk_raw_identity():
    hit = Hit("doc-1", "source.md", 2, 3, "evidence", 0.9, chunker="v2")
    source = citation_payloads([hit])[0]
    assert source["document_id"] == "doc-1"
    assert source["chunk_id"] == point_id("doc-1", 3, "v2")
    assert source["source_url"] == "/api/kb/documents/doc-1/source"


def test_project_document_allowlist_reaches_dense_and_sparse_before_top_k():
    class Client:
        def __init__(self):
            self.filters = []

        def collection_exists(self, _name):
            return True

        def query_points(self, **kwargs):
            self.filters.append(kwargs["query_filter"])
            conditions = kwargs["query_filter"].must
            allowlist = next(condition.match.any for condition in conditions if condition.key == "document_id")
            assert allowlist == ["project-doc"]
            global_points = [SimpleNamespace(
                score=100.0 - index,
                payload={"paper_id": f"global-{index}", "document_id": f"global-{index}", "file_name": "global.md", "chunk_index": 0, "text": "global evidence"},
            ) for index in range(12)]
            project_points = [SimpleNamespace(
                score=0.1,
                payload={"paper_id": "project-doc", "document_id": "project-doc", "file_name": "p.md", "chunk_index": 0, "text": "project evidence"},
            )]
            return SimpleNamespace(points=project_points if "project-doc" in allowlist else global_points)

    client = Client()
    def rerank(_question, candidates, **_kwargs):
        return SimpleNamespace(used=False, scores_by_original_index=None, hits=list(candidates))

    with patch.object(retrieve_module, "embed_texts", return_value=[[0.1]]), patch.object(retrieve_module, "encode_sparse", return_value={"indices": [], "values": []}), patch.object(retrieve_module, "rerank_hits", side_effect=rerank):
        result = retrieve_module.hybrid_search("question", top_k=10, document_ids=["project-doc"], client=client)
    assert client.filters[0] is client.filters[1]
    assert [hit.paper_id for hit in result] == ["project-doc"]
