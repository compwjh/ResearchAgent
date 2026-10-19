"""Task02 backend feasibility evidence and reuse contracts.

These tests intentionally replay the fixed, redacted evidence.  They do not
call Semantic Scholar, Ollama, a database, or a PDF/HTML endpoint.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SemanticScholarGraphClient,
    SemanticScholarMetadata,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = ROOT / "docs/sdd/plans/043/artifacts/task-02/api-evidence.json"


def _evidence() -> dict:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_bulk_search_budget_records_provider_count_separately() -> None:
    evidence = _evidence()
    requests = evidence["search"]["requests"]
    by_limit = {entry["limit"]: entry for entry in requests}

    assert set(by_limit) == {30, 50}
    for requested_limit, entry in by_limit.items():
        assert 1 <= requested_limit <= 100
        assert isinstance(entry["actual_parsed_count"], int)
        assert entry["actual_parsed_count"] >= requested_limit
        assert entry["accepted_count"] == requested_limit
        assert entry["selection"] == "map-layer-truncate-after-provider-response"
    assert by_limit[30]["actual_parsed_count"] == by_limit[50]["actual_parsed_count"]
    assert by_limit[30]["actual_parsed_count"] > 50


def test_graph_edges_preserve_direction_and_invalid_is_not_empty() -> None:
    graph = _evidence()["graph"]

    assert graph["references"]["direction"] == "source->citedPaper"
    assert graph["citations"]["direction"] == "citingPaper->source"
    assert graph["references"]["response_code"] == "SEMANTIC_SCHOLAR_INVALID_RESPONSE"
    assert graph["references"]["actual_parsed_count"] is None
    assert graph["citations"]["response_code"] is None
    assert graph["citations"]["actual_parsed_count"] == 0
    assert "not treated as no references" in graph["references"]["observation"]
    follow_up = graph["follow_up"]["sizzler_references"]
    assert follow_up["actual_parsed_count"] == 5
    assert follow_up["direction"] == "source->citedPaper"
    assert follow_up["next_offset"] == 5
    assert follow_up["safe_envelope"]["data_type"] == "list"
    assert follow_up["safe_envelope"]["row_keys"] == ["citedPaper"]
    assert graph["follow_up"]["slime_citations"]["http_status"] == 429
    assert graph["follow_up"]["slime_citations"]["response_code"] == "SEMANTIC_SCHOLAR_RATE_LIMITED"


def test_external_identity_requires_deterministic_external_id() -> None:
    evidence = _evidence()
    identity = evidence["identity"]
    paper = next(item for item in evidence["search"]["sample_papers"] if item["paper_id"] == identity["search_paper_id"])

    assert identity["external_id_kind"] == "doi"
    assert normalize_doi(identity["external_id"]) == "10.1145/3533767.3534385"
    assert paper["doi"] == identity["external_id"]
    assert identity["normalized_external_id_matches"] is True
    assert identity["batch_confirmation"] == "not_available_after_provider_rate_limit"
    assert identity["catalog_paper_id"] is None

    candidate = {
        "title": paper["title"],
        "year": paper["year"],
        "authors": (),
    }
    metadata = SemanticScholarMetadata(
        paper_id=paper["paper_id"],
        title=paper["title"],
        year=paper["year"],
        doi=paper["doi"],
    )
    assert SemanticScholarGraphClient._matches(candidate, metadata)


def test_embedding_evidence_keeps_similarity_threshold_honest() -> None:
    embedding = _evidence()["embedding"]

    assert embedding["status"] == "ok"
    assert embedding["model"] == "bge-m3"
    assert embedding["dimensions"] == [1024]
    assert embedding["basis"] == "title_abstract"
    assert embedding["threshold"] == 0.75
    assert 0.0 <= embedding["cosine"] < embedding["threshold"]
    assert embedding["accepted_pairs"] == []
    assert embedding["text_count"] == 6
    assert embedding["compared_pairs"] == 15
    assert len(embedding["fixture_inputs"]) == embedding["text_count"]
    assert all(item["abstract_chars"] > 0 for item in embedding["fixture_inputs"])
    assert all(len(item["abstract_sha256"]) == 64 for item in embedding["fixture_inputs"])
    assert all(len(item["text_sha256"]) == 64 for item in embedding["fixture_inputs"])


def test_probe_is_bounded_and_redacted() -> None:
    evidence = _evidence()
    probe = evidence["probe"]
    serialized = json.dumps(evidence, ensure_ascii=False).casefold()

    assert probe["logical_requests"] <= 12
    assert probe["maximum_provider_attempts"] <= 12
    assert probe["within_request_budget"] is True
    assert probe["key_value_recorded"] is False
    assert evidence["safety"] == {
        "html_fetched": False,
        "pdf_fetched": False,
        "database_written": False,
        "old_task_modified": False,
        "secrets_emitted": False,
    }
    assert "x-api-key" not in serialized
    assert "api_key" not in serialized
    assert ".env" not in serialized
    assert not re.search(r"\b(sk|dw)-[a-z0-9_-]{8,}\b", serialized)
