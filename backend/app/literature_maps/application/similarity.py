"""Deterministic dense cosine graph construction."""

from __future__ import annotations

import hashlib
import math
from typing import Iterable, Mapping, Sequence

from backend.app.literature_maps.domain.models import MapEdge, MapPaper


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not is_valid_vector(left) or not is_valid_vector(right) or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if not left_norm or not right_norm:
        return 0.0
    score = dot / (left_norm * right_norm)
    return score if math.isfinite(score) else 0.0


def is_valid_vector(vector: Sequence[float], *, dimension: int | None = None, require_nonzero: bool = True) -> bool:
    """Return whether a vector is safe to persist and compare."""
    if not isinstance(vector, (list, tuple)) or not vector:
        return False
    if dimension is not None and len(vector) != int(dimension):
        return False
    try:
        values = [float(item) for item in vector]
    except (TypeError, ValueError, OverflowError):
        return False
    if not all(math.isfinite(item) for item in values):
        return False
    return not (require_nonzero and not math.sqrt(sum(item * item for item in values)))


def build_similarity_edges(
    nodes: Iterable[MapPaper],
    vectors: Mapping[str, Sequence[float]],
    *,
    threshold: float = 0.75,
    top_k: int = 3,
    model_version: str = "unknown",
    basis: str = "title_abstract",
) -> list[MapEdge]:
    ordered = sorted(nodes, key=lambda node: node.node_id)
    candidate_edges: dict[str, tuple[float, str]] = {}
    for node in ordered:
        neighbors: list[tuple[float, str]] = []
        for other in ordered:
            if node.node_id == other.node_id:
                continue
            score = cosine_similarity(vectors.get(node.node_id, ()), vectors.get(other.node_id, ()))
            if score >= threshold:
                neighbors.append((score, other.node_id))
        neighbors.sort(key=lambda item: (-item[0], item[1]))
        for score, other_id in neighbors[: max(0, int(top_k))]:
            source_id, target_id = sorted((node.node_id, other_id))
            key = f"{source_id}:{target_id}"
            previous = candidate_edges.get(key)
            if previous is None or score > previous[0]:
                candidate_edges[key] = (score, other_id)
    result: list[MapEdge] = []
    for key, (score, _) in sorted(candidate_edges.items()):
        source_id, target_id = key.split(":", 1)
        map_id = next((node.map_id for node in ordered if node.node_id == source_id), "")
        result.append(
            MapEdge.new(
                map_id,
                "similarity",
                source_id,
                target_id,
                score=round(float(score), 8),
                basis=basis,
                model_version=model_version,
                content_hash=_pair_hash(vectors.get(source_id, ()), vectors.get(target_id, ())),
                provenance={"algorithm": "dense_cosine", "threshold": threshold, "top_k": top_k},
            )
        )
    return result


def _pair_hash(left: Sequence[float], right: Sequence[float]) -> str:
    payload = ",".join(f"{float(value):.8g}" for value in (*left, *right))
    return hashlib.sha256(payload.encode()).hexdigest()
