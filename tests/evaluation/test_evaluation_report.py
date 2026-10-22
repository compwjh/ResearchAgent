"""Local JSON/Markdown evaluation report contract tests.

The report is a filesystem-only artifact.  Tests use pytest temporary paths and
mocked write failures; no service, database, model, or network is involved.
"""
from __future__ import annotations

import json

import pytest

from backend.eval_042 import report as report_module
from backend.eval_042.report import (
    REPORT_SCHEMA_VERSION,
    ReportWriteError,
    ReportWriter,
    make_report,
    render_markdown,
)


SUMMARY_KEYS = {
    "scored",
    "skipped",
    "unavailable",
    "written",
    "verified",
    "failed",
    "no_prior_context",
}


def _load_artifacts(output_dir):
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    return json.loads(json_path.read_text(encoding="utf-8")), markdown_path.read_text(
        encoding="utf-8"
    )


def test_report_writer_initializes_json_and_markdown_skeleton(tmp_path):
    writer = ReportWriter(
        tmp_path,
        metadata={"task": "chat_quality", "judge_model": "qwen3.5:9b"},
    )

    document, markdown = _load_artifacts(tmp_path)

    assert writer.document["status"] == "running"
    assert document["schema_version"] == REPORT_SCHEMA_VERSION
    assert document["status"] == "running"
    assert document["finished_at"] is None
    assert document["items"] == []
    assert document["errors"] == []
    assert set(document["summary"]) == SUMMARY_KEYS
    assert all(value == 0 for value in document["summary"].values())
    assert document["human_agree_rate"] is None
    assert document["constructed_gold_only"] is True
    assert "constructed gold" in document["constructed_gold_note"].lower()
    assert document["metadata"] == {
        "task": "chat_quality",
        "judge_model": "qwen3.5:9b",
    }
    assert "# Agent evaluation report" in markdown
    assert "## Summary" in markdown
    assert "| <code>no_prior_context</code> | <code>0</code> |" in markdown


def test_checkpoint_preserves_summary_and_trace_score_model_fields_in_both_projections(
    tmp_path,
):
    writer = ReportWriter(tmp_path)
    document = writer.document
    document["items"] = [
        {
            "trace_id": "trace-42",
            "status": "scored",
            "judge_model": "qwen3.5:9b",
            "score": 1.0,
            "score_id": "score-42",
            "expected_value": 1.0,
            "verified": True,
        }
    ]
    document["summary"].update(
        {
            "scored": 1,
            "written": 1,
            "verified": 1,
            "no_prior_context": 2,
        }
    )

    saved = writer.checkpoint(document)
    persisted, markdown = _load_artifacts(tmp_path)

    item = persisted["items"][0]
    assert saved["summary"]["scored"] == 1
    assert saved["summary"]["no_prior_context"] == 2
    assert item["trace_id"] == "trace-42"
    assert item["judge_model"] == "qwen3.5:9b"
    assert item["score"] == 1.0
    assert item["score_id"] == "score-42"
    assert item["verified"] is True
    for value in ("trace-42", "qwen3.5:9b", "score-42"):
        assert value in markdown
    assert "| <code>scored</code> | <code>1</code> |" in markdown
    assert "| <code>written</code> | <code>1</code> |" in markdown
    assert "| <code>verified</code> | <code>1</code> |" in markdown
    assert "| <code>no_prior_context</code> | <code>2</code> |" in markdown


def test_finish_records_terminal_status_errors_and_finished_time(tmp_path):
    writer = ReportWriter(tmp_path)
    finished = writer.finish("failed", errors=[{"code": "SCORE_WRITE"}])
    persisted, markdown = _load_artifacts(tmp_path)

    assert finished["status"] == "failed"
    assert finished["finished_at"]
    assert finished["errors"] == [{"code": "SCORE_WRITE"}]
    assert persisted["status"] == "failed"
    assert persisted["finished_at"] == finished["finished_at"]
    assert persisted["errors"] == [{"code": "SCORE_WRITE"}]
    assert "SCORE_WRITE" in markdown


def test_checkpoint_failure_keeps_previous_artifacts_and_cleans_temp_files(
    tmp_path, monkeypatch
):
    writer = ReportWriter(tmp_path)
    old_json = (tmp_path / "report.json").read_bytes()
    old_markdown = (tmp_path / "report.md").read_bytes()
    original_write_temp = report_module._write_temp
    calls = 0

    def fail_on_markdown_temp(path, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated disk full")
        return original_write_temp(path, content)

    monkeypatch.setattr(report_module, "_write_temp", fail_on_markdown_temp)

    with pytest.raises(ReportWriteError, match="report.json, report.md"):
        writer.checkpoint(
            {
                **writer.document,
                "status": "completed",
                "items": [{"trace_id": "new-trace", "status": "scored"}],
            }
        )

    assert (tmp_path / "report.json").read_bytes() == old_json
    assert (tmp_path / "report.md").read_bytes() == old_markdown
    assert not list(tmp_path.glob(".report.json.*.tmp"))
    assert not list(tmp_path.glob(".report.md.*.tmp"))


def test_human_agree_rate_is_always_null_and_constructed_gold_is_explicit(tmp_path):
    writer = ReportWriter(
        tmp_path,
        metadata={"human_agree_rate": 0.99, "constructed_gold_only": False},
    )
    writer.document["human_agree_rate"] = 1.0
    writer.document["constructed_gold_only"] = False
    writer.checkpoint(writer.document)

    persisted, markdown = _load_artifacts(tmp_path)

    assert persisted["human_agree_rate"] is None
    assert persisted["constructed_gold_only"] is True
    assert "constructed gold" in persisted["constructed_gold_note"].lower()
    assert "human annotation was not run" in persisted["constructed_gold_note"]
    assert "Human agreement: <code>not evaluated</code>" in markdown
    assert "Constructed gold only: <code>True</code>" in markdown
    assert "1.0" not in markdown


def test_nested_metadata_cannot_claim_human_agreement_or_gold_truth(tmp_path):
    writer = ReportWriter(
        tmp_path,
        metadata={
            "nested": {
                "human_agree_rate": 0.99,
                "constructed_gold_only": False,
                "constructed_gold_note": "goldhumanpass",
            }
        },
    )

    persisted, markdown = _load_artifacts(tmp_path)
    serialized = json.dumps(persisted, ensure_ascii=False) + markdown

    assert persisted["human_agree_rate"] is None
    assert persisted["constructed_gold_only"] is True
    assert "0.99" not in serialized
    assert "goldhumanpass" not in serialized
    assert "constructed_gold_only" not in json.dumps(
        persisted["metadata"].get("nested", {}), ensure_ascii=False
    )


def test_second_replace_failure_restores_previous_json_and_markdown_pair(
    tmp_path, monkeypatch
):
    writer = ReportWriter(tmp_path)
    old_json = (tmp_path / "report.json").read_bytes()
    old_markdown = (tmp_path / "report.md").read_bytes()
    original_replace = report_module.os.replace
    replace_calls = 0

    def fail_second_replace(source, destination):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated second replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(report_module.os, "replace", fail_second_replace)

    with pytest.raises(ReportWriteError, match="report.json, report.md"):
        writer.checkpoint(
            {
                **writer.document,
                "status": "completed",
                "items": [{"trace_id": "new-trace", "status": "scored"}],
            }
        )

    assert replace_calls == 2
    assert (tmp_path / "report.json").read_bytes() == old_json
    assert (tmp_path / "report.md").read_bytes() == old_markdown
    assert not list(tmp_path.glob(".report.json.*.tmp"))
    assert not list(tmp_path.glob(".report.md.*.tmp"))


@pytest.mark.parametrize(
    "output_dir",
    [None, "", "https://example.com/reports", "http://127.0.0.1:3000/reports", "s3://bucket/reports"],
)
def test_report_output_directory_rejects_missing_or_url_paths(output_dir):
    with pytest.raises(ValueError):
        ReportWriter(output_dir)


def test_sensitive_proxy_auth_key_hidden_reasoning_and_q_a_fields_are_filtered(
    tmp_path,
):
    writer = ReportWriter(tmp_path)
    writer.checkpoint(
        {
            **writer.document,
            "metadata": {
                "proxyURL": "http://proxy-user:proxy-password@127.0.0.1:8080",
                "auth": "Bearer auth-secret",
                "key": "api-key-secret",
                "authorization": "Basic auth-header-secret",
                "api_key": "api-key-secret-2",
            },
            "items": [
                {
                    "trace_id": "trace-safe",
                    "hiddenReasoning": "private chain of thought",
                    "q": "private question",
                    "a": "private answer",
                    "input": "private input",
                    "output": "private output",
                }
            ],
        }
    )

    persisted, markdown = _load_artifacts(tmp_path)
    serialized = json.dumps(persisted, ensure_ascii=False) + markdown

    for field in ("proxyURL", "auth", "key", "authorization", "api_key"):
        assert field not in persisted["metadata"]
    for field in ("hiddenReasoning", "q", "a", "input", "output"):
        assert field not in persisted["items"][0]
    for secret in (
        "proxy-password",
        "auth-secret",
        "api-key-secret",
        "auth-header-secret",
        "private chain of thought",
        "private question",
        "private answer",
        "private input",
        "private output",
    ):
        assert secret not in serialized


def test_markdown_escapes_controlled_html_and_does_not_execute_markup(tmp_path):
    controlled = "<script>alert('x')</script> [click](javascript:alert('x'))"
    markdown = render_markdown(
        {
            "metadata": {"controlled": controlled},
            "items": [{"trace_id": controlled, "status": "scored"}],
        }
    )

    assert "<script>" not in markdown
    assert "</script>" not in markdown
    assert "<a " not in markdown.lower()
    assert "&lt;script&gt;" in markdown
    assert "&lt;/script&gt;" in markdown


def test_report_retains_safe_judge_reason_or_explicit_explanation_alternative(
    tmp_path,
):
    writer = ReportWriter(tmp_path)
    writer.checkpoint(
        {
            **writer.document,
            "items": [
                {
                    "trace_id": "trace-judge",
                    "status": "scored",
                    "judge_model": "qwen3.5:9b",
                    "score": 1.0,
                    "reason": "Answer is relevant and complete.",
                    "comment": "raw judge comment may contain payload",
                    "explanation": "Safe explanation: answer is relevant and complete.",
                }
            ],
        }
    )

    persisted, markdown = _load_artifacts(tmp_path)
    item = persisted["items"][0]
    safe_reason = item.get("reason") or item.get("explanation")

    # Spec-042 requires EvalResult.reason.  If reason/comment are deliberately
    # filtered for safety, an explicit safe explanation is an acceptable
    # replacement; deleting all rationale makes the result unverifiable.
    assert safe_reason in {
        "Answer is relevant and complete.",
        "Safe explanation: answer is relevant and complete.",
    }
    assert (
        "Answer is relevant and complete." in markdown
        or "Safe explanation: answer is relevant and complete." in markdown
    )
    assert "raw judge comment may contain payload" not in json.dumps(persisted)
    assert "raw judge comment may contain payload" not in markdown


def test_make_report_returns_safe_defaults_even_with_untrusted_metadata():
    report = make_report(
        {
            "human_agree_rate": 0.8,
            "constructed_gold_only": False,
            "task": "memory_correctness",
        }
    )

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["human_agree_rate"] is None
    assert report["constructed_gold_only"] is True
    assert report["metadata"]["task"] == "memory_correctness"
