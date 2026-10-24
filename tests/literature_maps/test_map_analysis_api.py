from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import reset_literature_map_runtime
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app


def test_analysis_api_returns_source_status_and_idempotent_job_handle(tmp_path):
    reset_literature_map_runtime()


def test_deleted_map_conversation_messages_are_404_and_retry_reserves_new_id(tmp_path):
    reset_literature_map_runtime()
    database = tmp_path / "maps.sqlite3"
    memory_database = tmp_path / "memory.sqlite3"
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(database), "MEMORY_DB_PATH": str(memory_database)}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        created = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20})
        assert created.status_code == 202
        map_id = created.json()["map_id"]
        store = LiteratureMapStore(database)
        node = MapPaper.new(map_id, semantic_scholar_id="s2-delete-api", title="Delete API", abstract="Abstract")
        store.add_nodes(map_id, "local-user", [node])
        first = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/conversation",
            json={"evidence_level": "abstract", "idempotency_key": "delete-retry"},
        )
        assert first.status_code == 200
        first_id = first.json()["conversation_id"]
        assert client.delete(f"/api/conversations/{first_id}").status_code == 204
        assert client.get(f"/api/conversations/{first_id}/messages").status_code == 404
        second = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/conversation",
            json={"evidence_level": "abstract", "idempotency_key": "delete-retry"},
        )
        assert second.status_code == 200
        assert second.json()["conversation_id"] != first_id
        with store.connection() as db:
            binding_rows = db.execute(
                "SELECT status FROM literature_map_conversation_bindings WHERE conversation_id IN (?, ?)",
                (first_id, second.json()["conversation_id"]),
            ).fetchall()
        assert {row["status"] for row in binding_rows} == {"superseded", "confirmed"}
    reset_literature_map_runtime()
    database = tmp_path / "maps.sqlite3"
    memory_database = tmp_path / "memory.sqlite3"
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(database), "MEMORY_DB_PATH": str(memory_database)}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ), patch("backend.app.literature_maps.application.analysis.MapAnalysisService.run_analysis_job", autospec=True):
        client = TestClient(app)
        created = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20})
        assert created.status_code == 202
        map_id = created.json()["map_id"]
        store = LiteratureMapStore(database)
        node = MapPaper.new(map_id, semantic_scholar_id="s2-a", title="A paper", abstract="A real abstract")
        store.add_nodes(map_id, "local-user", [node])

        listed = client.get(f"/api/literature-maps/{map_id}/nodes/{node.node_id}/analyses")
        assert listed.status_code == 200
        assert listed.json()["source_status"]["available_evidence_levels"] == ["abstract"]
        started = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/analyses",
            json={"evidence_level": "abstract", "idempotency_key": "a1"},
        )
        assert started.status_code == 202
        body = started.json()
        assert body["analysis"]["status"] == "pending"
        assert body["analysis_id"] == body["analysis"]["analysis_id"]
        repeated = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/analyses",
            json={"evidence_level": "abstract", "idempotency_key": "a1"},
        )
        assert repeated.status_code == 202
        assert repeated.json()["analysis_id"] == body["analysis_id"]
        conversation = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/conversation",
            json={"evidence_level": "abstract", "idempotency_key": "conversation-1"},
        )
        assert conversation.status_code == 200
        conversation_body = conversation.json()
        assert conversation_body["project_id"] is None
        same_conversation = client.post(
            f"/api/literature-maps/{map_id}/nodes/{node.node_id}/conversation",
            json={"evidence_level": "abstract", "idempotency_key": "conversation-1"},
        )
        assert same_conversation.status_code == 200
        assert same_conversation.json()["conversation_id"] == conversation_body["conversation_id"]
    reset_literature_map_runtime()
