from types import SimpleNamespace

from backend.app.research.application.orchestrator import (
    Orchestrator,
    _promote_catalog_floor,
    _sanitize_evaluator_binding,
    _validated_evaluator_candidates,
)
from backend.app.research.application.report_synthesis import ReportSynthesizer, report_output_hash


def test_report_renders_catalog_metadata_and_explicit_missing_fields():
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[
            {
                "candidate_id": "paper-1",
                "verified": True,
                "evidence_refs": ["catalog:paper-1"],
                "title": "Official title",
                "abstract": "Official abstract",
                "keywords": ["defense", "supply chain"],
                "method": "Official method description",
                "source": "usenix",
                "year": 2024,
                "official_url": "https://www.usenix.org/paper-1",
            },
            {"candidate_id": "paper-2", "verified": True, "evidence_refs": ["catalog:paper-2"]},
        ],
        citation_manifest=["catalog:paper-1", "catalog:paper-2"],
    )
    assert "Official title" in result.markdown
    assert "- 摘要：Official abstract" in result.markdown
    assert "- 关键词：defense、supply chain" in result.markdown
    assert "- 研究方法：Official method description" in result.markdown
    assert "- 来源：usenix" in result.markdown
    assert "- 年份：2024" in result.markdown
    assert "- 官方 URL：https://www.usenix.org/paper-1" in result.markdown
    assert result.markdown.count("摘要：官方未提供") == 1
    assert result.markdown.count("关键词：官方未提供") == 1
    assert result.markdown.count("研究方法：官方未提供") == 1


def test_catalog_metadata_resolver_reuses_store_and_exposes_provenance_fields():
    paper = SimpleNamespace(
        title="Directory title", abstract=None, keywords=[], year=2023,
        conference_id="ieee-sp", official_page_url="https://example.org/paper",
    )

    class Store:
        def get_catalog_paper(self, paper_id):
            assert paper_id == "paper-1"
            return paper

        def get_catalog_source_kinds(self, paper_id):
            return ["ieee-sp"]

    adapter = SimpleNamespace(_store=Store())
    orchestrator = object.__new__(Orchestrator)
    orchestrator._adapter = adapter
    resolver = orchestrator._catalog_metadata_resolver()
    assert resolver is not None
    assert resolver("paper-1") == {
        "title": "Directory title", "year": 2023, "source_kinds": ["ieee-sp"],
        "source": "ieee-sp", "official_url": "https://example.org/paper",
    }


def test_consume_repairs_unique_catalog_reference_when_model_repeats_candidate_id():
    candidates = [
        {"candidate_id": "paper-1", "verified": True, "evidence_refs": ["catalog:paper-1"], "title": "One"},
        {"candidate_id": "paper-2", "verified": True, "evidence_refs": ["catalog:paper-2"], "title": "Two"},
    ]
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=candidates,
        citation_manifest=["catalog:paper-1", "catalog:paper-2"],
    )
    payload = result.output.model_dump(mode="json")
    payload["citation_manifest"][1]["candidate_id"] = "paper-1"
    payload["output_hash"] = report_output_hash({key: value for key, value in payload.items() if key != "output_hash"})

    consumed = ReportSynthesizer().consume_validated_output(
        output=payload,
        validated_candidates=candidates,
    )

    assert "Two" in consumed.markdown
    assert "`catalog:paper-2` → `paper-2`" in consumed.markdown


def test_evaluator_parallel_arrays_expand_into_catalog_bound_candidates():
    ids = ["paper-1", "paper-2", "paper-3"]
    allowed = {f"catalog:{item}" for item in ids}
    normalized = _sanitize_evaluator_binding(
        {
            "candidate_id": ids,
            "relevance_score": [0.9, 0.8, 0.7],
            "keep": True,
            "evidence_refs": sorted(allowed),
            "source_refs": sorted(allowed),
        },
        allowed,
    )
    records = _validated_evaluator_candidates(
        [normalized],
        metadata_by_id={},
        recall_allowlist=set(ids),
    )
    assert [item["candidate_id"] for item in records] == ids
    assert [item["evidence_refs"] for item in records] == [[f"catalog:{item}"] for item in ids]


def test_evaluator_batch_refs_expand_when_one_representative_id_is_returned():
    ids = ["paper-1", "paper-2", "paper-3"]
    refs = [f"catalog:{item}" for item in ids]
    records = _validated_evaluator_candidates(
        [{"candidate_id": ids[0], "keep": True, "evidence_refs": refs}],
        metadata_by_id={},
        recall_allowlist=set(ids),
    )
    assert [item["candidate_id"] for item in records] == ids
    assert [item["evidence_refs"] for item in records] == [[ref] for ref in refs]


def test_catalog_floor_promotes_from_recalled_ids_when_evaluator_returns_none():
    ids = [f"paper-{index}" for index in range(1, 6)]
    records = _promote_catalog_floor([], ids, {}, None, "USENIX Security")
    assert [item["candidate_id"] for item in records] == ids
    assert all(item["verified"] is True for item in records)


def test_synthesis_accepts_bounded_section_summary_for_real_report_content():
    candidate = {"candidate_id": "paper-1", "verified": True, "evidence_refs": ["catalog:paper-1"], "title": "Paper"}
    base = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[candidate],
        citation_manifest=["catalog:paper-1"],
    ).output.model_dump(mode="json")
    base["sections"] = [{
        "heading": "方法比较",
        "candidate_ids": ["paper-1"],
        "summary": "这是一个用于展示真实报告内容的较长摘要。" * 40,
    }]
    base["output_hash"] = report_output_hash({key: value for key, value in base.items() if key != "output_hash"})
    consumed = ReportSynthesizer().consume_validated_output(output=base, validated_candidates=[candidate])
    assert "方法比较" in consumed.markdown
