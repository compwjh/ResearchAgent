"""Bounded report-content transport through the existing synthesis envelope."""

import copy

import pytest

from backend.app.research.application.report_synthesis import (
    REPORT_SYNTHESIS_OUTPUT_SCHEMA,
    ReportSynthesisError,
    ReportSynthesisOutput,
    ReportSynthesizer,
    report_output_hash,
    validate_report_synthesis_output,
)


def _report_content():
    paper_ids = [f"paper-{index}" for index in range(1, 6)]
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": "研究问题"},
        "evidence_scope": {"text": "已批准的证据范围", "paper_ids": paper_ids},
        "paper_analyses": [
            {
                "paper_id": paper_id,
                "method": {"status": "not_stated", "text": "", "evidence_ids": []},
                "findings": {
                    "status": "supported", "text": f"发现 {index}",
                    "evidence_ids": [f"evidence:{paper_id}"],
                },
                "limitations": {"status": "unavailable", "text": "", "evidence_ids": []},
            }
            for index, paper_id in enumerate(paper_ids, start=1)
        ],
        "cross_paper_comparisons": [{
            "dimension_id": "dimension-1",
            "paper_ids": paper_ids[:2],
            "statement": "比较陈述",
            "evidence_ids": ["evidence:paper-1", "evidence:paper-2"],
        }],
        "synthesis_findings": [
            {
                "finding_id": f"finding-{index}",
                "statement": f"综合发现 {index}",
                "paper_ids": paper_ids[:2],
                "evidence_ids": ["evidence:paper-1", "evidence:paper-2"],
            }
            for index in range(1, 4)
        ],
        "research_gaps": [],
    }


def _output(*, report_content=None):
    payload = {
        "schema_version": "report-synthesis-v1",
        "report_version": 1,
        "sections": [{"heading": "证据", "candidate_ids": ["candidate-1"]}],
        "citation_manifest": [{"citation_ref": "catalog:candidate-1", "candidate_id": "candidate-1"}],
        "artifact_ids": [],
        "safe_summary": {"candidate_count": 1},
        "source_refs": ["catalog:candidate-1"],
    }
    if report_content is not None:
        payload["report_content"] = report_content
    payload["output_hash"] = report_output_hash(payload)
    return payload


def test_legacy_synthesis_output_keeps_its_original_shape_and_hash():
    payload = _output()

    normalized = validate_report_synthesis_output(payload)
    round_trip = ReportSynthesisOutput.model_validate(normalized).model_dump(mode="json")

    assert "report_content" not in normalized
    assert "report_content" not in round_trip
    assert normalized == payload
    assert normalized["output_hash"] == report_output_hash(normalized)


def test_report_content_is_validated_and_included_in_the_envelope_hash():
    payload = _output(report_content=_report_content())

    normalized = validate_report_synthesis_output(payload)

    assert normalized["report_content"] == payload["report_content"]
    assert normalized["output_hash"] == report_output_hash(normalized)

    changed = copy.deepcopy(payload)
    changed["report_content"]["research_question"]["text"] = "改过的问题"
    with pytest.raises(ReportSynthesisError, match="output_hash"):
        validate_report_synthesis_output(changed)


def test_report_content_schema_is_optional_but_strictly_bounded_when_present():
    payload = _output(report_content=_report_content())
    invalid_candidates = []

    wrong_version = copy.deepcopy(payload)
    wrong_version["report_content"]["schema_version"] = "research-report-content-v2"
    invalid_candidates.append(wrong_version)

    missing_field = copy.deepcopy(payload)
    del missing_field["report_content"]["research_question"]
    invalid_candidates.append(missing_field)

    duplicate_ids = copy.deepcopy(payload)
    duplicate_ids["report_content"]["evidence_scope"]["paper_ids"].append("paper-1")
    invalid_candidates.append(duplicate_ids)

    too_many_papers = copy.deepcopy(payload)
    too_many_papers["report_content"]["paper_analyses"] *= 13
    invalid_candidates.append(too_many_papers)

    for invalid in invalid_candidates:
        invalid["output_hash"] = report_output_hash(invalid)
        with pytest.raises(ReportSynthesisError, match="schema validation"):
            validate_report_synthesis_output(invalid)

    schema = REPORT_SYNTHESIS_OUTPUT_SCHEMA
    report_schema = schema["properties"]["report_content"]
    assert "report_content" not in schema["required"]
    assert report_schema["properties"]["schema_version"]["const"] == "research-report-content-v1"
    assert report_schema["properties"]["paper_analyses"]["minItems"] == 5
    assert report_schema["properties"]["paper_analyses"]["maxItems"] == 64
    assert report_schema["additionalProperties"] is False


@pytest.mark.parametrize("overlong_id", [" " + "p" * 200, "p" * 200 + " "])
def test_report_content_rejects_raw_overlong_ids_before_whitespace_trimming(overlong_id):
    payload = _output(report_content=_report_content())
    payload["report_content"]["paper_analyses"][0]["paper_id"] = overlong_id
    payload["output_hash"] = report_output_hash(payload)

    assert len(overlong_id) == 201
    assert len(overlong_id.strip()) == 200
    with pytest.raises(ReportSynthesisError, match="schema validation"):
        validate_report_synthesis_output(payload)


def test_structured_content_passes_through_without_quality_or_publication_claims():
    payload = _output(report_content=_report_content())
    result = ReportSynthesizer().consume_validated_output(
        output=payload,
        validated_candidates=[{
            "candidate_id": "candidate-1", "verified": True,
            "evidence_refs": ["catalog:candidate-1"],
        }],
    )
    output = result.output.model_dump(mode="json")

    assert output["report_content"] == payload["report_content"]
    assert "quality_validation" not in output
    assert "quality_status" not in output
    assert output["output_hash"] == report_output_hash(output)
    assert "研究问题" not in result.markdown


def test_report_content_does_not_bypass_existing_citation_allowlist():
    payload = _output(report_content=_report_content())
    payload["citation_manifest"] = [{
        "citation_ref": "catalog:forged", "candidate_id": "candidate-1",
    }]
    payload["source_refs"] = ["catalog:forged"]
    payload["output_hash"] = report_output_hash(payload)

    with pytest.raises(ReportSynthesisError, match="outside evaluator evidence allowlist"):
        ReportSynthesizer().consume_validated_output(
            output=payload,
            validated_candidates=[{
                "candidate_id": "candidate-1", "verified": True,
                "evidence_refs": ["catalog:candidate-1"],
            }],
        )


def test_legacy_fixed_candidate_synthesis_does_not_claim_quality_success():
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[{"candidate_id": "candidate-1", "verified": True}],
        citation_manifest=["catalog:candidate-1"],
    )
    output = result.output.model_dump(mode="json")

    assert "report_content" not in output
    assert "quality_validation" not in output
    assert "quality_status" not in output
