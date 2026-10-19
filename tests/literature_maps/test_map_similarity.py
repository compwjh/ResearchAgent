from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.application.similarity import build_similarity_edges, cosine_similarity
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore


def test_similarity_is_thresholded_top_three_and_undirected_deduplicated():
    nodes = [
        MapPaper.new("map", semantic_scholar_id=f"s{i}", title=f"Paper {i}")
        for i in range(4)
    ]
    vectors = {node.node_id: [1.0, 0.0] if i < 3 else [0.0, 1.0] for i, node in enumerate(nodes)}
    edges = build_similarity_edges(nodes, vectors, threshold=0.75, model_version="fake", basis="title_abstract")
    assert edges
    assert all(edge.source_id < edge.target_id for edge in edges)
    assert len({(edge.source_id, edge.target_id) for edge in edges}) == len(edges)
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0], [0.0, 1.0]) == 0.0


def test_nonfinite_and_zero_norm_vectors_fail_closed():
    assert cosine_similarity([float("nan"), 1.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([float("inf"), 1.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_invalid_embedding_is_unavailable_and_not_cached(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item = store.create_map("owner-a", topic="fuzzing", requested_count=20)
    node = MapPaper.new(item.map_id, semantic_scholar_id="s2-a", title="Fuzzing")
    store.add_nodes(item.map_id, "owner-a", [node])
    service = LiteratureMapService(
        store=store,
        embedder=lambda texts: [[float("nan"), 1.0] for _ in texts],
        executor=None,
    )

    edges, error = service._collect_similarity([node])

    assert edges == []
    assert error == "EMBEDDING_INVALID_RESPONSE"
    assert store.get_embedding(
        model_version="bge-m3",
        basis="title_abstract",
        content_hash="missing",
    ) is None
