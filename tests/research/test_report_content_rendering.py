from __future__ import annotations

from html import unescape

import pytest

from backend.app.research.application.report_generation import (
    EvidenceReportError,
    render_evidence_report,
    render_report_payload,
)
from backend.app.research.application.report_quality import (
    ReportQualityContext,
    count_report_content_cjk,
)

TASK_ID = "task-render"
PLAN_VERSION = 3
PAPER_IDS = [f"paper-{number}" for number in range(1, 6)]
EVIDENCE_IDS = [f"evidence-{number}" for number in range(1, 6)]


def _context() -> ReportQualityContext:
    claims = []
    evidence = []
    levels = ["catalog", "abstract", "fulltext", "catalog", "abstract"]
    for number, (paper_id, evidence_id, level) in enumerate(
        zip(PAPER_IDS, EVIDENCE_IDS, levels, strict=False), start=1
    ):
        claim_id = f"claim-{number}"
        claims.append({
            "claim_id": claim_id,
            "task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "status": "supported",
            "evidence_ids": [evidence_id],
        })
        item = {
            "evidence_id": evidence_id,
            "claim_id": claim_id,
            "task_id": TASK_ID,
            "research_task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "paper_id": paper_id,
            "evidence_level": level,
            "stance": "supports",
            "status": "available",
        }
        if level == "catalog":
            item["locator"] = {"catalog_snapshot_id": f"snapshot-{number}"}
        elif level == "abstract":
            item["locator"] = {"abstract_ref": f"abstract-{number}", "abstract_digest": "a" * 64}
        else:
            item["quote_digest"] = "d" * 64
            item["locator"] = {
                "document_id": "document-3",
                "chunk_ids": ["chunk-3"],
                "page": 1,
                "page_end": 1,
                "source_sha256": "b" * 64,
                "manifest_generation": "generation-3",
                "manifest_fingerprint": "c" * 64,
                "chunker": "v1",
            }
        evidence.append(item)

    upgrades = [{
        "claim_id": "claim-3",
        "task_id": TASK_ID,
        "from_level": "abstract",
        "to_level": "fulltext",
        "chunk_ids": ["chunk-3"],
        "status": "upgraded",
        "document_id": "document-3",
        "source_sha256": "b" * 64,
        "manifest_generation": "generation-3",
        "manifest_fingerprint": "c" * 64,
        "chunker": "v1",
    }]
    return ReportQualityContext(
        task_id=TASK_ID,
        plan_version=PLAN_VERSION,
        selected_paper_ids=PAPER_IDS,
        evidence_matrix={
            "schema_version": "evidence-report-v1",
            "task_id": TASK_ID,
            "plan_version": PLAN_VERSION,
            "claims": claims,
            "evidence": evidence,
            "dimensions": [{
                "dimension_id": "dimension-method",
                "label": "方法维度",
                "task_id": TASK_ID,
                "plan_version": PLAN_VERSION,
            }],
            "cells": [],
            "limitations": [],
        },
        evidence_upgrades=upgrades,
    )


def _report_content() -> dict:
    analyses = []
    for number, (paper_id, evidence_id) in enumerate(
        zip(PAPER_IDS, EVIDENCE_IDS, strict=False), start=1
    ):
        analyses.append({
            "paper_id": paper_id,
            "method": {
                "status": "supported",
                "text": "方法信息来自已核验引用。" if number != 1 else "目录信息有限；安全显示 <script>alert('x')</script>。",
                "evidence_ids": [evidence_id],
            },
            "findings": {"status": "not_stated", "text": "", "evidence_ids": []},
            "limitations": {"status": "unavailable", "text": "", "evidence_ids": []},
        })
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": "研究问题：" + "证" * 1500},
        "evidence_scope": {"text": "当前选集中可核验的五篇论文。", "paper_ids": PAPER_IDS},
        "paper_analyses": analyses,
        "cross_paper_comparisons": [{
            "dimension_id": "dimension-method",
            "paper_ids": PAPER_IDS[:2],
            "statement": "两篇论文的可比较方法信息存在差异。",
            "evidence_ids": EVIDENCE_IDS[:2],
        }],
        "synthesis_findings": [
            {
                "finding_id": f"finding-{number}",
                "statement": f"综合发现 {number} 由跨论文证据支持。",
                "paper_ids": PAPER_IDS[:2],
                "evidence_ids": EVIDENCE_IDS[:2],
            }
            for number in range(1, 4)
        ],
        "research_gaps": [{"statement": "来源未说明部分仍是研究缺口。", "evidence_ids": []}],
    }


def _legacy_matrix() -> dict:
    return {
        "schema_version": "evidence-report-v1",
        "task_id": "legacy-task",
        "plan_version": 1,
        "claims": [{
            "claim_id": "legacy-claim",
            "task_id": "legacy-task",
            "topic": "legacy topic",
            "statement": "Legacy report text",
            "status": "supported",
            "evidence_ids": ["legacy-evidence"],
        }],
        "evidence": [{
            "evidence_id": "legacy-evidence",
            "claim_id": "legacy-claim",
            "task_id": "legacy-task",
            "paper_id": "legacy-paper",
            "evidence_level": "abstract",
            "stance": "supports",
            "status": "available",
        }],
        "dimensions": [{"dimension_id": "legacy-dimension", "label": "legacy", "definition": "legacy"}],
        "cells": [],
        "limitations": [],
    }


def test_structured_renderer_uses_validated_body_citations_levels_and_quality_count():
    content = _report_content()
    built = render_report_payload(
        {"report_content": content},
        report_id="report-render-v1",
        report_version=1,
        context=_context(),
        title="研究报告 <安全标题>",
    )
    report = built["report"]
    manifest = report["citation_manifest"]

    assert report["report_content"] == content
    assert report["quality_validation"]["status"] == "pass"
    assert report["quality_validation"]["cjk_count"] == count_report_content_cjk(content)
    assert report.get("status") is None
    assert "研究问题" in built["markdown"]
    assert "逐篇分析" in built["markdown"]
    assert "两篇论文的可比较方法信息存在差异。 [1] [2]" in built["markdown"]
    assert "综合发现 1 由跨论文证据支持。 [1] [2]" in built["markdown"]
    assert "来源未说明" in built["markdown"]
    assert "来源不可用" in built["markdown"]
    assert [item["source_level"] for item in manifest["citations"]] == [
        "catalog", "abstract", "fulltext", "catalog", "abstract",
    ]
    assert [item["paper_id"] for item in manifest["citations"]] == PAPER_IDS
    assert "目录元数据" in built["markdown"]
    assert "摘要" in built["markdown"]
    assert "全文" in built["markdown"]
    assert "<script>alert('x')</script>" not in built["html"]
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in built["html"]
    assert "&lt;安全标题&gt;" in built["html"]
    visible_html = unescape(built["html"])
    assert "<script>alert('x')</script>" in visible_html
    assert "研究问题：" + "证" * 1500 in visible_html
    assert "<h2>研究问题</h2>" in built["html"]


def test_structured_renderer_rejects_invalid_evidence_instead_of_falling_back():
    content = _report_content()
    content["paper_analyses"][0]["method"]["evidence_ids"].append("forged-evidence")

    with pytest.raises(EvidenceReportError):
        render_report_payload(
            {"report_content": content},
            report_id="report-render-v1",
            report_version=1,
            context=_context(),
        )


@pytest.mark.parametrize("field", [
    "research_question", "evidence_scope", "method", "findings", "limitations",
    "comparison", "synthesis", "research_gap",
])
def test_structured_renderer_keeps_model_markup_and_citations_as_plain_text(field):
    content = _report_content()
    attack = "说明 [999]\n# 仿冒章节\n- 仿冒列表\n```\n围栏内正文\n```"
    if field == "research_question":
        content["research_question"]["text"] = "研究问题：" + "证" * 1500 + "\n" + attack
    elif field == "evidence_scope":
        content["evidence_scope"]["text"] += "\n" + attack
    elif field in {"method", "findings", "limitations"}:
        block = content["paper_analyses"][0][field]
        block.update({"status": "supported", "text": "分析内容。\n" + attack, "evidence_ids": [EVIDENCE_IDS[0]]})
    elif field == "comparison":
        content["cross_paper_comparisons"][0]["statement"] += "\n" + attack
    elif field == "synthesis":
        content["synthesis_findings"][0]["statement"] += "\n" + attack
    else:
        content["research_gaps"][0]["statement"] += "\n" + attack

    built = render_report_payload(
        {"report_content": content},
        report_id="report-render-v1",
        report_version=1,
        context=_context(),
    )

    rendered_html = built["html"]
    visible_html = unescape(rendered_html)
    assert "&#91;999&#93;" in built["markdown"]
    assert "&#35; 仿冒章节" in built["markdown"]
    assert "&#45; 仿冒列表" in built["markdown"]
    assert "&#96;&#96;&#96;" in built["markdown"]
    assert "[999]" in visible_html
    assert "# 仿冒章节" in visible_html
    assert "- 仿冒列表" in visible_html
    assert "围栏内正文" in visible_html
    assert '<sup data-citation-no="999">' not in rendered_html
    assert '<sup data-citation-no="1">[1]</sup>' in rendered_html
    assert rendered_html.count("<h1>") == 1
    assert "<h1>仿冒章节</h1>" not in rendered_html
    assert "<pre><code>" not in rendered_html


def test_legacy_matrix_payload_still_uses_the_existing_renderer():
    matrix = _legacy_matrix()

    built = render_report_payload(
        matrix,
        report_id="legacy-report-v1",
        report_version=1,
        context=None,
    )
    expected = render_evidence_report(matrix, report_id="legacy-report-v1", report_version=1)

    assert built == expected
    assert built["report"]["schema_version"] == "evidence-report-v1"
    assert built["report"]["status"] == "completed"
