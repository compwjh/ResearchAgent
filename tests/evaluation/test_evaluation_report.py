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
    # Spec-047 Task-04: 无 --gold 时走降级态。恒 null 不再是「无条件」事实，
    # 由下方「反伪造护栏 + 有条件可计算」两组用例显式覆盖各降级条件。
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


def test_untrusted_human_agreement_claims_are_stripped_to_safe_defaults(tmp_path):
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


# ---------------------------------------------------------------------------
# Spec-047 Task-04 (P2①): 人工 gold 一致率 —— 降级态 / 可计算态 / 反伪造护栏
#
# 说明：以下 gold 文件均为「测试内构造的临时夹具」，明确标注 TEST-FIXTURE，
# 不是真实人工标注，仅用于验证「可导入 + 可计算」能力与反伪造护栏。
# ---------------------------------------------------------------------------

_TEST_GOLD_NOTE = (
    "TEST-FIXTURE ONLY: synthetic labels generated inside pytest, "
    "NOT real human annotation. Real agreement pending manual labeling."
)


def _gold_item(item_id, human_label="good", *, gold_source="human"):
    return {
        "item_id": item_id,
        "human_label": human_label,
        "annotator": "test-fixture",
        "annotated_at": "2026-11-09T00:00:00+00:00",
        "gold_source": gold_source,
    }


def _write_human_gold(path, items, *, schema_version="human-gold-v1"):
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "note": _TEST_GOLD_NOTE,
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _scored_items(n=20, *, agree=15):
    """n 条 scored report items：前 agree 条判官多数标签 good，其余 partial。"""
    return [
        {
            "trace_id": f"trace-{i}",
            "status": "scored",
            "label": "good" if i < agree else "partial",
            "score": 1.0,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "case",
    [
        "no_gold",
        "empty_items",
        "below_n_min",
        "non_human_source",
        "payload_bearing_item",
    ],
)
def test_human_agree_rate_stays_null_without_usable_human_gold(tmp_path, case):
    """降级态：无 gold / 空 / 不足 20 / 非人工来源 / 脱敏违规 -> 恒 null + True。"""
    gold_path = None
    if case == "empty_items":
        gold_path = _write_human_gold(tmp_path / "gold.json", [])
    elif case == "below_n_min":
        gold_path = _write_human_gold(
            tmp_path / "gold.json",
            [_gold_item(f"trace-{i}") for i in range(19)],
        )
    elif case == "non_human_source":
        # 构造/合成 gold 不得冒充人工标注（spec-042:245）
        gold_path = _write_human_gold(
            tmp_path / "gold.json",
            [_gold_item(f"trace-{i}", gold_source="constructed") for i in range(20)],
        )
    elif case == "payload_bearing_item":
        # gold 文件含 prompt/input 原文 -> 条目被拒，且原文绝不落入 report
        gold_path = _write_human_gold(
            tmp_path / "gold.json",
            [
                {
                    **_gold_item(f"trace-{i}"),
                    "prompt": "SECRET SYSTEM PROMPT PAYLOAD",
                    "input": "private question",
                }
                for i in range(20)
            ],
        )

    output_dir = tmp_path / "out"
    writer = ReportWriter(output_dir, gold_path=str(gold_path) if gold_path else None)
    writer.checkpoint({**writer.document, "items": _scored_items()})

    document, markdown = _load_artifacts(output_dir)

    assert document["human_agree_rate"] is None
    assert document["constructed_gold_only"] is True
    assert "Human agreement: <code>not evaluated</code>" in markdown
    assert "Constructed gold only: <code>True</code>" in markdown
    serialized = json.dumps(document, ensure_ascii=False) + markdown
    assert "SECRET SYSTEM PROMPT PAYLOAD" not in serialized
    assert "private question" not in serialized


def test_human_agree_rate_is_computable_with_valid_human_gold_fixture(tmp_path):
    """可计算态：>=20 条合法脱敏人工 gold + join 成功 -> 算出一致率、可复算。"""
    gold_path = _write_human_gold(
        tmp_path / "gold.json",
        [_gold_item(f"trace-{i}", "good") for i in range(20)],
    )
    output_dir = tmp_path / "out"
    writer = ReportWriter(output_dir, gold_path=str(gold_path))
    writer.checkpoint({**writer.document, "items": _scored_items(agree=15)})

    document, markdown = _load_artifacts(output_dir)

    assert document["human_agree_rate"] == 0.75  # round(15/20, 4)
    assert document["constructed_gold_only"] is False
    detail = document["human_agree_rate_detail"]
    assert detail["n_agree"] == 15
    assert detail["n_evaluated"] == 20
    assert detail["n_min"] == 20
    assert detail["gold_source"] == "human"
    assert len(detail["gold_file_sha256"]) == 64
    assert round(detail["n_agree"] / detail["n_evaluated"], 4) == document["human_agree_rate"]
    assert "0.75" in markdown
    assert "Constructed gold only: <code>False</code>" in markdown


def test_default_report_shape_omits_optional_human_gold_keys(tmp_path):
    """无 --gold 时 CLI 默认输出形状不变：不新增 detail / note 可选键。"""
    ReportWriter(tmp_path)

    document, _ = _load_artifacts(tmp_path)

    assert document["human_agree_rate"] is None
    assert document["constructed_gold_only"] is True
    assert "human_agree_rate_detail" not in document
    assert "human_agree_rate_note" not in document


def test_load_human_gold_enforces_desensitized_schema(tmp_path):
    """load_human_gold: 字段白名单 / gold_source 字面 / label 合法域 / item_id 非空。"""
    from backend.eval_042.human_gold import load_human_gold

    path = _write_human_gold(
        tmp_path / "gold.json",
        [
            _gold_item("trace-0", "good"),
            {**_gold_item("trace-1", "good"), "prompt": "SECRET", "input": "q"},
            _gold_item("trace-2", "good", gold_source="synthetic"),
            _gold_item("trace-3", "not_a_label"),
            {**_gold_item("trace-4", "good"), "item_id": ""},
        ],
    )

    items = load_human_gold(str(path))

    assert [item["item_id"] for item in items] == ["trace-0"]
    empty = _write_human_gold(tmp_path / "empty.json", [])
    assert load_human_gold(str(empty)) == []


def test_compute_human_agree_rate_formula_and_null_guards():
    """compute_human_agree_rate: 分子/分母公式 + 分母 0 / N<20 / 无有效标注门禁。"""
    from backend.eval_042.human_gold import (
        MIN_HUMAN_GOLD_ITEMS,
        compute_human_agree_rate,
    )

    assert MIN_HUMAN_GOLD_ITEMS == 20
    report_items = _scored_items(agree=15)
    gold_items = [_gold_item(f"trace-{i}", "good") for i in range(20)]

    assert compute_human_agree_rate(report_items, gold_items) == 0.75
    assert compute_human_agree_rate([], gold_items) is None  # 分母 0
    assert compute_human_agree_rate(report_items, gold_items[:19]) is None  # N < 20
    assert compute_human_agree_rate(
        report_items,
        [_gold_item(f"trace-{i}", "good", gold_source="constructed") for i in range(20)],
    ) is None  # 无有效人工标注
    assert compute_human_agree_rate(
        [{**item, "status": "skipped"} for item in report_items], gold_items
    ) is None  # 无 scored 条目
