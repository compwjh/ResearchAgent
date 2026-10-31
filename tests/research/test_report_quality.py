from __future__ import annotations

import pytest

from backend.app.research.application.report_quality import (
    ReportQualityContext,
    ReportQualityError,
    count_report_content_cjk,
    validate_report_content,
)

TASK_ID = "task-a"
PLAN_VERSION = 2
PAPER_IDS = [f"paper-{number}" for number in range(1, 6)]


def _context() -> ReportQualityContext:
    claims = []
    evidence = []
    for number, paper_id in enumerate(PAPER_IDS, start=1):
        claim_id = f"claim-{number}"
        evidence_id = f"evidence-{number}"
        claims.append({
            "claim_id": claim_id,
            "task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "status": "supported",
            "evidence_ids": [evidence_id],
        })
        evidence.append({
            "evidence_id": evidence_id,
            "claim_id": claim_id,
            "task_id": TASK_ID,
            "research_task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "paper_id": paper_id,
            "evidence_level": "catalog",
            "stance": "supports",
            "status": "available",
            "locator": {"catalog_snapshot_id": f"snapshot-{number}"},
        })
    dimensions = [{
        "dimension_id": "dimension-method",
        "id": "dimension-method",
        "task_id": TASK_ID,
        "research_task_id": TASK_ID,
        "plan_version": PLAN_VERSION,
    }]
    return ReportQualityContext(
        task_id=TASK_ID,
        plan_version=PLAN_VERSION,
        selected_paper_ids=PAPER_IDS,
        evidence_matrix={
            "schema_version": "evidence-report-v1",
            "task_id": TASK_ID,
            "research_task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "claims": claims,
            "evidence": evidence,
            "dimensions": dimensions,
            "cells": [],
            "limitations": [],
        },
        evidence_upgrades=[],
    )


def _report(question: str = "研究问题") -> dict:
    analyses = []
    for number, paper_id in enumerate(PAPER_IDS, start=1):
        analyses.append({
            "paper_id": paper_id,
            "method": {"status": "supported", "text": f"method {number}", "evidence_ids": [f"evidence-{number}"]},
            "findings": {"status": "not_stated", "text": "", "evidence_ids": []},
            "limitations": {"status": "unavailable", "text": "", "evidence_ids": []},
        })
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": question},
        "evidence_scope": {"text": "scope", "paper_ids": PAPER_IDS},
        "paper_analyses": analyses,
        "cross_paper_comparisons": [{
            "dimension_id": "dimension-method",
            "paper_ids": PAPER_IDS[:2],
            "statement": "comparison",
            "evidence_ids": ["evidence-1", "evidence-2"],
        }],
        "synthesis_findings": [
            {
                "finding_id": f"finding-{number}",
                "statement": f"finding {number}",
                "paper_ids": PAPER_IDS[:2],
                "evidence_ids": ["evidence-1", "evidence-2"],
            }
            for number in range(1, 4)
        ],
        "research_gaps": [],
    }


def test_quality_validation_passes_at_1500_cjk_characters():
    result = validate_report_content(_report("研" * 1500), _context())

    assert result.to_dict() == {
        "schema_version": "report-quality-v1",
        "status": "pass",
        "cjk_count": 1500,
        "count_method": "report-quality-v1",
        "paper_count": 5,
        "comparison_count": 1,
        "supported_finding_count": 3,
        "invalid_evidence_count": 0,
        "failure_codes": [],
        "revision_count": 0,
    }


def test_quality_validation_fails_one_below_cjk_threshold():
    result = validate_report_content(_report("研" * 1499), _context())

    assert result.status == "fail"
    assert result.cjk_count == 1499
    assert result.failure_codes == ("CJK_COUNT_BELOW_MINIMUM",)


def test_cjk_counter_ignores_markup_links_ids_headings_and_code():
    text = "## 中文标题\n正文中文 [123] [证据ID] [链接标签](https://例子.cn/路径)\n```代码块中文```\n`行内代码中文`\n<h2>HTML标题</h2><a href=\"https://例子.cn\">链接中文</a><h2>参考文献</h2>HTML引用中文\n参考文献\n---\n引用说明中文\n## 附录\n附录中文"
    report = _report(text)

    assert count_report_content_cjk(report) == 4


def test_cjk_counter_uses_only_the_frozen_unicode_ranges():
    report = _report(chr(0x3400) + chr(0x323AF) + chr(0x323B0) + "😀")

    assert count_report_content_cjk(report) == 2


def test_unknown_analysis_states_are_allowed_and_do_not_add_body_text():
    report = _report("研究")
    report["paper_analyses"][0]["findings"] = {
        "status": "unavailable",
        "text": "",
        "evidence_ids": [],
    }

    result = validate_report_content(report, _context())

    assert result.status == "fail"
    assert result.paper_count == 5
    assert result.cjk_count == 2


def test_invalid_report_evidence_reference_fails_closed_and_is_counted():
    report = _report("研" * 1500)
    report["research_gaps"] = [{"statement": "gap", "evidence_ids": ["untrusted-evidence"]}]

    result = validate_report_content(report, _context())

    assert result.status == "fail"
    assert result.invalid_evidence_count == 1
    assert "INVALID_EVIDENCE_REFERENCE" in result.failure_codes


def test_mixed_valid_and_invalid_evidence_refs_do_not_increase_coverage_counts():
    report = _report("研" * 1500)
    report["paper_analyses"][0]["method"]["evidence_ids"].append("forged-evidence")
    report["cross_paper_comparisons"][0]["evidence_ids"].append("forged-evidence")
    for finding in report["synthesis_findings"]:
        finding["evidence_ids"].append("forged-evidence")

    result = validate_report_content(report, _context())

    assert result.status == "fail"
    assert result.paper_count == 4
    assert result.comparison_count == 0
    assert result.supported_finding_count == 0
    assert result.invalid_evidence_count == 1


def test_comparison_refs_must_cover_two_declared_papers():
    report = _report("研" * 1500)
    report["cross_paper_comparisons"][0]["evidence_ids"] = ["evidence-1", "evidence-3"]

    result = validate_report_content(report, _context())

    assert result.status == "fail"
    assert result.comparison_count == 0
    assert "INVALID_EVIDENCE_REFERENCE" in result.failure_codes


def test_comparison_dimension_must_be_in_the_current_plan():
    report = _report("研" * 1500)
    report["cross_paper_comparisons"][0]["dimension_id"] = "unapproved-dimension"

    result = validate_report_content(report, _context())

    assert result.status == "fail"
    assert result.comparison_count == 0
    assert "INVALID_DIMENSION_REFERENCE" in result.failure_codes


def test_context_rejects_evidence_from_another_plan_version():
    context = _context()
    context.evidence_matrix["evidence"][0]["plan_version"] = PLAN_VERSION - 1

    with pytest.raises(ReportQualityError, match="plan_version"):
        validate_report_content(_report("研" * 1500), context)


def test_context_rejects_unsupported_evidence_source_level():
    context = _context()
    context.evidence_matrix["evidence"][0]["evidence_level"] = "fulltext-ish"

    with pytest.raises(ReportQualityError, match="evidence_level"):
        validate_report_content(_report("研" * 1500), context)


def test_context_rejects_dimensions_from_another_task_or_plan():
    context = _context()
    context.evidence_matrix["dimensions"][0]["task_id"] = "task-other"

    with pytest.raises(ReportQualityError, match="dimension"):
        validate_report_content(_report("研" * 1500), context)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "research-report-content-v2"),
        ("research_question", {"text": ""}),
        ("paper_analyses", []),
        ("research_gaps", [{"statement": "x" * 2001, "evidence_ids": []}]),
    ],
)
def test_report_content_schema_bounds_are_enforced(field, value):
    report = _report("研" * 1500)
    report[field] = value

    with pytest.raises(ReportQualityError):
        validate_report_content(report, _context())


def test_supported_block_requires_evidence_and_unknown_block_cannot_fabricate_text():
    report = _report("研" * 1500)
    report["paper_analyses"][0]["method"]["evidence_ids"] = []

    with pytest.raises(ReportQualityError, match="supported"):
        validate_report_content(report, _context())

    report = _report("研" * 1500)
    report["paper_analyses"][0]["findings"]["text"] = "unverified result"
    with pytest.raises(ReportQualityError, match="not_stated|unavailable"):
        validate_report_content(report, _context())


def test_fulltext_reference_requires_current_upgrade_provenance():
    context = _context()
    evidence = context.evidence_matrix["evidence"][0]
    evidence.update({
        "evidence_level": "fulltext",
        "quote_digest": "a" * 64,
        "locator": {
            "document_id": "document-1",
            "chunk_ids": ["chunk-1"],
            "page": 1,
            "page_end": 1,
            "source_sha256": "b" * 64,
            "manifest_generation": "generation-1",
            "manifest_fingerprint": "c" * 64,
            "chunker": "v1",
        },
    })
    context.evidence_upgrades = [{
        "claim_id": "claim-1",
        "task_id": TASK_ID,
        "from_level": "abstract",
        "to_level": "fulltext",
        "chunk_ids": ["chunk-1"],
        "status": "upgraded",
        "document_id": "document-1",
        "source_sha256": "b" * 64,
        "manifest_generation": "generation-1",
        "manifest_fingerprint": "c" * 64,
        "chunker": "v1",
    }]

    assert validate_report_content(_report("研" * 1500), context).status == "pass"

    context.evidence_upgrades[0]["task_id"] = "task-other"
    result = validate_report_content(_report("研" * 1500), context)
    assert result.status == "fail"
    assert result.invalid_evidence_count >= 1


def test_report_payload_is_limited_to_512_kibibytes():
    report = _report("研" * 1500)
    report["overflow"] = "x" * (512 * 1024)

    with pytest.raises(ReportQualityError, match="512 KiB|512 KiB"):
        validate_report_content(report, _context())
