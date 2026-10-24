from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import reset_literature_map_runtime
from backend.app.main import app


def test_map_api_create_list_graph_view_and_owner_boundary(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        response = client.post("/api/literature-maps", json={"topic": "fuzzing", "limit": 20})
        assert response.status_code == 202
        body = response.json()
        assert body["schema_version"] == "literature-map-v1"
        map_id = body["map_id"]
        assert client.get(f"/api/literature-maps/{map_id}").status_code == 200
        assert client.get(f"/api/literature-maps/{map_id}/graph").status_code == 200
        view = client.patch(
            f"/api/literature-maps/{map_id}/view",
            json={"expected_revision": 0, "viewport": {"x": 0, "y": 0, "scale": 1.25}},
        )
        assert view.status_code == 200
        assert view.json()["map"]["revision"] == 1
        assert client.get(f"/api/literature-maps/{map_id}/jobs/{body['job_id']}").status_code == 200
    reset_literature_map_runtime()
