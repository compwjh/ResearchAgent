"""`GET /api/literature-maps` must report each map's live node count."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.literature_maps.application.runtime import (
    get_literature_map_service,
    reset_literature_map_runtime,
)
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.main import app

OWNER_ID = "local-user"
COUNT_SQL_MARKER = "FROM literature_map_nodes n JOIN literature_maps m ON m.map_id=n.map_id"


class _TraceConnection:
    """Proxy a store connection and record every SQL statement it executes."""

    def __init__(self, connection, statements):
        self._connection = connection
        self._statements = statements

    def __enter__(self):
        db = self._connection.__enter__()
        db.set_trace_callback(self._statements.append)
        return db

    def __exit__(self, *exc_info):
        return self._connection.__exit__(*exc_info)


def _paper(map_id, suffix):
    return MapPaper.new(
        map_id,
        semantic_scholar_id=f"s2-{suffix}",
        title=f"Paper {suffix}",
        authors=("A",),
        year=2024,
        position={"x": 1, "y": 1},
    )


def _seed(client, topic, limit=20):
    created = client.post("/api/literature-maps", json={"topic": topic, "limit": limit})
    assert created.status_code == 202
    return created.json()["map_id"]


def _listed(client, map_id):
    response = client.get("/api/literature-maps")
    assert response.status_code == 200
    assert set(response.json()) == {"schema_version", "maps"}
    matches = [item for item in response.json()["maps"] if item["map_id"] == map_id]
    assert len(matches) == 1
    return matches[0]


def _graph_active_node_ids(client, map_id):
    """Active nodes exactly as the graph view renders them (tombstones flagged)."""
    graph = client.get(f"/api/literature-maps/{map_id}/graph")
    assert graph.status_code == 200
    return {
        node["node_id"]
        for node in graph.json()["nodes"]
        if not node["removed"] and not node.get("tombstone")
    }


def test_list_node_count_matches_active_graph_nodes_and_keeps_legacy_fields(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        map_id = _seed(client, "node count", limit=20)
        service = get_literature_map_service()
        service.store.add_nodes(map_id, OWNER_ID, [_paper(map_id, f"n{i}") for i in range(32)])

        item = _listed(client, map_id)
        active_node_ids = _graph_active_node_ids(client, map_id)
        assert len(active_node_ids) == 32
        assert item["node_count"] == 32
        assert item["node_count"] == len(active_node_ids)
        # requested_count keeps its original meaning (build target) and is untouched.
        assert item["requested_count"] == 20
        # Every pre-existing to_dict() field survives; node_count and the
        # derived ``tags`` are additive (Spec043 BE-2).
        assert set(item) == {
            "map_id",
            "name",
            "topic",
            "owner_id",
            "project_id",
            "filters",
            "requested_count",
            "revision",
            "status",
            "view_settings",
            "created_at",
            "updated_at",
            "node_count",
            "tags",
        }
        assert item["tags"] == []
        assert item["topic"] == "node count"
        assert item["owner_id"] == OWNER_ID
        assert isinstance(item["node_count"], int)
    reset_literature_map_runtime()


def test_list_node_count_excludes_removed_tombstones(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        map_id = _seed(client, "tombstone")
        service = get_literature_map_service()
        papers = [_paper(map_id, f"t{i}") for i in range(5)]
        service.store.add_nodes(map_id, OWNER_ID, papers)
        assert _listed(client, map_id)["node_count"] == 5

        removed = service.remove_node(map_id, papers[0].node_id, OWNER_ID, expected_revision=0)
        assert removed["map"]["revision"] == 1
        service.remove_node(map_id, papers[1].node_id, OWNER_ID, expected_revision=1)

        item = _listed(client, map_id)
        assert item["node_count"] == 3
        assert item["node_count"] == len(_graph_active_node_ids(client, map_id))
    reset_literature_map_runtime()


def test_list_node_counts_are_per_map_and_need_one_batch_query(tmp_path):
    reset_literature_map_runtime()
    statements = []
    original_connection = LiteratureMapStore.connection

    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        map_a = _seed(client, "map a")
        map_b = _seed(client, "map b")
        service = get_literature_map_service()
        service.store.add_nodes(map_a, OWNER_ID, [_paper(map_a, f"a{i}") for i in range(7)])
        service.store.add_nodes(map_b, OWNER_ID, [_paper(map_b, f"b{i}") for i in range(2)])

        with patch.object(
            LiteratureMapStore, "connection", lambda self: _TraceConnection(original_connection(self), statements)
        ):
            response = client.get("/api/literature-maps")

        assert response.status_code == 200
        maps = {item["map_id"]: item for item in response.json()["maps"]}
        assert maps[map_a]["node_count"] == 7
        assert maps[map_b]["node_count"] == 2
        count_statements = [sql for sql in statements if COUNT_SQL_MARKER in sql]
        # One batched statement for all listed maps: no per-map N+1 COUNT(*).
        assert len(count_statements) == 1, count_statements
        count_sql = count_statements[0]
        assert "COUNT(*)" in count_sql
        assert "removed_at IS NULL" in count_sql
        assert "map_id IN (" in count_sql
        # The batched statement covers exactly the listed maps: as many bind
        # values in the IN (...) list as maps, and no per-map statement.
        in_list = count_sql[count_sql.index("IN (") + 4 : count_sql.index(")", count_sql.index("IN ("))]
        bound_ids = [value.strip().strip("'") for value in in_list.split(",")]
        assert sorted(bound_ids) == sorted(maps) == sorted([map_a, map_b])
    reset_literature_map_runtime()


def test_list_node_count_is_owner_scoped(tmp_path):
    reset_literature_map_runtime()
    with patch.dict("os.environ", {"LITERATURE_MAP_DB_PATH": str(tmp_path / "maps.sqlite3")}, clear=False), patch(
        "backend.app.literature_maps.application.service.LiteratureMapService.run_job", autospec=True
    ):
        client = TestClient(app)
        map_id = _seed(client, "owner scope")
        service = get_literature_map_service()
        service.store.add_nodes(map_id, OWNER_ID, [_paper(map_id, f"o{i}") for i in range(4)])
        assert _listed(client, map_id)["node_count"] == 4

        # Counts never leak across owners, and an empty id list costs no query.
        assert service.store.active_node_counts("another-owner", [map_id]) == {}
        assert service.store.active_node_counts(OWNER_ID, [map_id]) == {map_id: 4}
        assert service.store.active_node_counts(OWNER_ID, []) == {}
    reset_literature_map_runtime()
