"""Spec030 Task02: evidence/report contract probes.

The application implementation lands in later tasks.  These tests intentionally
keep the frozen v1 sample and its invariants local so Task03/04 can implement
against an executable contract without writing business code in Task02.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re

import pytest


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_SAMPLE_REPORT = {
    "schema_version": "evidence-report-v1",
    "report_id": "report-030-1",
    "task_id": "task-030",
    "plan_version": 3,
    "report_version": 1,
    "status": "partial",
    "claims": [
        {
            "claim_id": "claim-1",
            "task_id": "task-030",
            "topic": "method",
            "statement": "Paper A reports an improvement under the evaluated setting.",
            "confidence": "medium",
            "status": "contested",
            "evidence_ids": ["evidence-1", "evidence-2", "evidence-3"],
        },
        {
            "claim_id": "claim-2",
            "task_id": "task-030",
            "topic": "limitation",
            "statement": "The selected papers do not establish the long-term effect.",
            "confidence": "low",
            "status": "unresolved",
            "evidence_ids": [],
        },
    ],
    "evidence": [
        {
            "evidence_id": "evidence-1",
            "claim_id": "claim-1",
            "paper_id": "paper-a",
            "evidence_level": "fulltext",
            "stance": "supports",
            "status": "available",
            "locator": {
                "document_id": "document-a",
                "chunk_ids": ["document-a:v1:7"],
                "page": 3,
                "page_end": 4,
                "quote_digest": _digest("paper A exact source text"),
                "source_sha256": "a" * 64,
                "manifest_generation": "generation-1",
                "manifest_fingerprint": "b" * 64,
                "chunker": "v1",
            },
        },
        {
            "evidence_id": "evidence-2",
            "claim_id": "claim-1",
            "paper_id": "paper-b",
            "evidence_level": "fulltext",
            "stance": "contradicts",
            "status": "available",
            "locator": {
                "document_id": "document-b",
                "chunk_ids": ["document-b:v1:2"],
                "page": 8,
                "page_end": 8,
                "quote_digest": _digest("paper B exact source text"),
                "source_sha256": "c" * 64,
                "manifest_generation": "generation-1",
                "manifest_fingerprint": "d" * 64,
                "chunker": "v1",
            },
        },
        {
            "evidence_id": "evidence-3",
            "claim_id": "claim-1",
            "paper_id": "paper-c",
            "evidence_level": "abstract",
            "stance": "contextual",
            "status": "available",
            "locator": {
                "catalog_snapshot_id": "snapshot-1",
                "abstract_digest": _digest("paper C abstract excerpt"),
            },
        },
    ],
    "cells": [
        {"claim_id": "claim-1", "paper_id": "paper-a", "relation": "supports", "evidence_ids": ["evidence-1"]},
        {"claim_id": "claim-1", "paper_id": "paper-b", "relation": "contradicts", "evidence_ids": ["evidence-2"]},
        {"claim_id": "claim-1", "paper_id": "paper-c", "relation": "contextual", "evidence_ids": ["evidence-3"]},
        {
            "claim_id": "claim-2",
            "paper_id": "paper-d",
            "relation": "missing",
            "evidence_ids": [],
            "missing_reason": "No approved abstract or full-text locator exists.",
        },
    ],
    "citation_manifest": {
        "manifest_version": 1,
        "report_id": "report-030-1",
        "citations": [
            {"citation_no": 1, "paper_id": "paper-a", "evidence_ids": ["evidence-1"]},
            {"citation_no": 2, "paper_id": "paper-b", "evidence_ids": ["evidence-2"]},
            {"citation_no": 3, "paper_id": "paper-c", "evidence_ids": ["evidence-3"]},
        ],
    },
    "limitations": ["claim-2 has no approved evidence locator."],
}


def _index(report: dict) -> tuple[dict, dict, dict, dict]:
    claims = {item["claim_id"]: item for item in report["claims"]}
    evidence = {item["evidence_id"]: item for item in report["evidence"]}
    cells = {(item["claim_id"], item["paper_id"]): item for item in report["cells"]}
    citations = {item["citation_no"]: item for item in report["citation_manifest"]["citations"]}
    return claims, evidence, cells, citations


def _validate_report(report: dict) -> None:
    """Validate the normative v1 invariants used by later report writers."""
    assert report["schema_version"] == "evidence-report-v1"
    assert report["status"] in {"draft", "generating", "completed", "partial", "failed"}
    claims, evidence, cells, citations = _index(report)
    assert claims and all(item["evidence_ids"] == list(item["evidence_ids"]) for item in claims.values())
    referenced_evidence = {eid for claim in claims.values() for eid in claim["evidence_ids"]}
    assert referenced_evidence <= set(evidence)
    for claim in claims.values():
        assert claim["task_id"] == report["task_id"]
        assert claim["status"] in {"supported", "contested", "unresolved"}
        if not claim["evidence_ids"]:
            assert claim["status"] == "unresolved"
        assert all(evidence[eid]["status"] == "available" for eid in claim["evidence_ids"])
        if claim["status"] == "contested":
            assert any(evidence[eid]["stance"] == "contradicts" for eid in claim["evidence_ids"])

    for item in evidence.values():
        assert item["stance"] in {"supports", "contradicts", "contextual"}
        assert item["evidence_level"] in {"catalog", "abstract", "fulltext"}
        assert item["status"] in {"available", "unavailable", "revalidation_required"}
        assert item["claim_id"] in claims
        locator = item["locator"]
        if item["evidence_level"] == "fulltext":
            assert locator["document_id"] and locator["chunk_ids"]
            assert locator["page"] > 0 and locator["page_end"] >= locator["page"]
            assert re.fullmatch(r"[0-9a-f]{64}", locator["source_sha256"])
            assert re.fullmatch(r"[0-9a-f]{64}", locator["manifest_fingerprint"])
            assert locator["manifest_generation"] and locator["chunker"]
        else:
            assert "document_id" not in locator

    for cell in cells.values():
        assert cell["relation"] in {"supports", "contradicts", "contextual", "missing"}
        if cell["relation"] == "missing":
            assert cell["evidence_ids"] == []
            assert cell.get("missing_reason")
            continue
        assert cell["evidence_ids"]
        for evidence_id in cell["evidence_ids"]:
            assert evidence_id in evidence
            assert evidence[evidence_id]["claim_id"] == cell["claim_id"]
            assert evidence[evidence_id]["paper_id"] == cell["paper_id"]
            assert evidence[evidence_id]["stance"] == cell["relation"]

    missing = [cell for cell in cells.values() if cell["relation"] == "missing"]
    assert all(not cell["evidence_ids"] and cell.get("missing_reason") for cell in missing)
    assert all(item["citation_no"] > 0 for item in citations.values())
    assert sorted(citations) == list(range(1, len(citations) + 1))
    assert len(citations) == len(report["citation_manifest"]["citations"])
    assert report["citation_manifest"]["report_id"] == report["report_id"]
    for citation in citations.values():
        assert citation["paper_id"]
        assert citation["evidence_ids"]
        assert all(evidence_id in evidence for evidence_id in citation["evidence_ids"])
        assert all(evidence[evidence_id]["status"] == "available" for evidence_id in citation["evidence_ids"])
        assert all(evidence[evidence_id]["paper_id"] == citation["paper_id"] for evidence_id in citation["evidence_ids"])


def _semantic_projection(report: dict) -> dict:
    claims, evidence, cells, citations = _index(report)
    return {
        "report_id": report["report_id"],
        "status": report["status"],
        "claims": sorted((key, value["statement"], tuple(value["evidence_ids"])) for key, value in claims.items()),
        "evidence": sorted((key, value["paper_id"], value["evidence_level"], value["stance"], value["status"]) for key, value in evidence.items()),
        "cells": sorted((key, value["relation"], tuple(value["evidence_ids"])) for key, value in cells.items()),
        "citations": sorted((key, value["paper_id"], tuple(value["evidence_ids"])) for key, value in citations.items()),
        "limitations": tuple(report["limitations"]),
    }


def test_fixed_sample_freezes_claim_evidence_relations_and_locators():
    _validate_report(_SAMPLE_REPORT)
    _, evidence, cells, _ = _index(_SAMPLE_REPORT)
    assert {cell["relation"] for cell in cells.values()} == {"supports", "contradicts", "contextual", "missing"}
    assert evidence["evidence-1"]["locator"]["page_end"] == 4
    assert evidence["evidence-3"]["evidence_level"] == "abstract"


def test_invalid_citation_or_locator_is_rejected_fail_closed():
    missing_citation = copy.deepcopy(_SAMPLE_REPORT)
    missing_citation["citation_manifest"]["citations"][0]["evidence_ids"] = ["deleted-evidence"]
    with pytest.raises(AssertionError):
        _validate_report(missing_citation)

    bad_locator = copy.deepcopy(_SAMPLE_REPORT)
    bad_locator["evidence"][0]["locator"]["page"] = 0
    with pytest.raises(AssertionError):
        _validate_report(bad_locator)

    wrong_chunk = copy.deepcopy(_SAMPLE_REPORT)
    wrong_chunk["cells"][0]["evidence_ids"] = ["evidence-2"]
    with pytest.raises(AssertionError):
        _validate_report(wrong_chunk)


def test_missing_evidence_is_explicit_and_never_promoted_to_fact():
    _, _, cells, _ = _index(_SAMPLE_REPORT)
    missing = cells[("claim-2", "paper-d")]
    assert missing["relation"] == "missing"
    assert missing["evidence_ids"] == []
    assert _SAMPLE_REPORT["status"] == "partial"
    assert _SAMPLE_REPORT["limitations"]

    unavailable = copy.deepcopy(_SAMPLE_REPORT)
    unavailable["evidence"][0]["status"] = "unavailable"
    unavailable["claims"][0]["evidence_ids"] = ["evidence-2", "evidence-3"]
    unavailable["cells"][0]["relation"] = "missing"
    unavailable["cells"][0]["evidence_ids"] = []
    unavailable["cells"][0]["missing_reason"] = "Source document was deleted."
    unavailable["citation_manifest"]["citations"] = [
        {"citation_no": 1, "paper_id": "paper-b", "evidence_ids": ["evidence-2"]},
        {"citation_no": 2, "paper_id": "paper-c", "evidence_ids": ["evidence-3"]},
    ]
    unavailable["limitations"].append("evidence-1 is unavailable after source deletion.")
    _validate_report(unavailable)


def test_markdown_html_json_views_preserve_one_semantic_model():
    canonical = _semantic_projection(_SAMPLE_REPORT)
    json_view = json.loads(json.dumps(_SAMPLE_REPORT, ensure_ascii=False))
    markdown_view = (
        "# Report\n\n"
        "Claim: Paper A reports an improvement under the evaluated setting. [1][2][3]\n\n"
        "Limitations: claim-2 has no approved evidence locator."
    )
    html_view = (
        "<h1>Report</h1>"
        '<p data-claim-id="claim-1">Paper A reports an improvement under the evaluated setting. '
        '<sup data-citation-no="1">[1]</sup><sup data-citation-no="2">[2]</sup><sup data-citation-no="3">[3]</sup></p>'
        '<p data-limitation="true">claim-2 has no approved evidence locator.</p>'
    )

    assert _semantic_projection(json_view) == canonical
    assert re.findall(r"\[(\d+)\]", markdown_view) == ["1", "2", "3"]
    assert re.findall(r'data-citation-no="(\d+)"', html_view) == ["1", "2", "3"]
    assert html.escape(_SAMPLE_REPORT["claims"][0]["statement"]) in html_view
    assert _SAMPLE_REPORT["limitations"][0] in markdown_view and _SAMPLE_REPORT["limitations"][0] in html_view
