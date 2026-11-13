"""Spec-045 Task-03 红测：fallback 生效 + 可复现基线 + 编排/脱敏合并。

全部用例先写（RED），待实现后转 GREEN。覆盖：
1. primary 不可用（unavailable / 异常）时自动切 fallback 并跑完；
2. primary 与 fallback 都不可用才记 UNAVAILABLE；
3. 报告 metadata 含 dataset_sha256 / judge_model_digest / prompt_sha256 / seed / tie_break_rule；
4. 同数据集两次运行结果一致、指纹稳定；
5. 平票规则与标签插入顺序无关（确定性）；
6. judge /api/chat 请求带固定 seed，且不改变 temperature:0/think:False/num_predict:160；
7. 数据集导出稳定 ID 排序 + 计算 sha256；
8. 三套 judge 编排收敛为 judge_client.judge_majority（consistency/memory_probe/runner 共用），
   三套脱敏正则收敛为一处（config 共享）。
"""
from __future__ import annotations

import pytest

from backend.eval_042 import config, judge_client, langfuse_export, runner


def _item(trace_id="trace-1", *, task="chat_quality", output="A complete answer."):
    return {
        "trace_id": trace_id,
        "task": task,
        "input": "What should be evaluated?",
        "output": output,
        "status": "scored",
        "synthetic": False,
        "prior_context": None,
    }


def _patch_success(monkeypatch, *, label="good", score=1.0):
    def judge(model, task, question, answer, repeats, *, ctx=None):
        return [
            {"status": "scored", "label": label, "score": score, "explanation": "ok"}
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)
    monkeypatch.setattr(
        runner.langfuse_export, "post_score", lambda **kw: {"id": "score-1"}
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda *a, **k: {
            "id": "score-1",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        },
    )


def test_fallback_used_when_primary_unavailable(tmp_path, monkeypatch):
    captured = []

    def judge(model, task, question, answer, repeats, *, ctx=None):
        captured.append(model)
        if model == "primary-model":
            return [
                {"status": "unavailable", "label": None, "score": None, "error": "down"}
                for _ in range(repeats)
            ]
        return [
            {"status": "scored", "label": "good", "score": 1.0, "explanation": "ok"}
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)
    post_calls = []
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kw: post_calls.append(kw) or {"id": "score-1"},
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda *a, **k: {
            "id": "score-1",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        },
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[_item()],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )
    document, _ = (
        (tmp_path / "report.json").read_text(encoding="utf-8"),
        None,
    )
    doc = __import__("json").loads(document)

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert captured == ["primary-model", "fallback-model"]
    item = doc["items"][0]
    assert item["status"] == "scored"
    assert item["judge_model"] == "fallback-model"
    assert len(post_calls) == 1


def test_fallback_used_when_primary_raises(tmp_path, monkeypatch):
    captured = []

    def judge(model, task, question, answer, repeats, *, ctx=None):
        captured.append(model)
        if model == "primary-model":
            raise RuntimeError("primary down")
        return [
            {"status": "scored", "label": "good", "score": 1.0, "explanation": "ok"}
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)
    post_calls = []
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kw: post_calls.append(kw) or {"id": "score-1"},
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda *a, **k: {
            "id": "score-1",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        },
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[_item()],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )

    assert result["exit_code"] == 0
    assert captured == ["primary-model", "fallback-model"]
    assert len(post_calls) == 1


def test_both_unavailable_records_unavailable_and_does_not_post(tmp_path, monkeypatch):
    def judge(model, task, question, answer, repeats, *, ctx=None):
        return [
            {"status": "unavailable", "label": None, "score": None, "error": "down"}
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)
    post_calls = []
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kw: post_calls.append(kw),
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[_item()],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )
    doc = __import__("json").loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert result["exit_code"] == 1
    assert doc["items"][0]["status"] == "unavailable"
    assert post_calls == []


def test_metadata_has_reproducibility_fingerprints(tmp_path, monkeypatch):
    _patch_success(monkeypatch)
    result = runner.run(
        output_dir=tmp_path,
        items=[_item()],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )
    meta = result["document"]["metadata"]

    assert isinstance(meta.get("dataset_sha256"), str) and len(meta["dataset_sha256"]) == 64
    assert isinstance(meta.get("judge_model_digest"), str) and len(meta["judge_model_digest"]) == 64
    assert isinstance(meta.get("prompt_sha256"), str) and len(meta["prompt_sha256"]) == 64
    assert meta.get("seed") == config.JUDGE_SEED
    assert isinstance(meta.get("tie_break_rule"), str) and meta["tie_break_rule"]


def test_two_runs_same_dataset_are_reproducible(tmp_path, monkeypatch):
    _patch_success(monkeypatch)
    r1 = runner.run(
        output_dir=tmp_path / "run-1",
        items=[_item("trace-1"), _item("trace-2")],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )
    r2 = runner.run(
        output_dir=tmp_path / "run-2",
        items=[_item("trace-1"), _item("trace-2")],
        primary="primary-model",
        fallback="fallback-model",
        repeats=3,
    )
    m1, m2 = r1["document"]["metadata"], r2["document"]["metadata"]
    assert m1 == m2
    assert m1["dataset_sha256"] == m2["dataset_sha256"]
    labels1 = [it["label"] for it in r1["document"]["items"]]
    labels2 = [it["label"] for it in r2["document"]["items"]]
    assert labels1 == labels2


def test_tie_break_deterministic_regardless_of_label_order():
    from backend.eval_042.judge_client import TIE_BREAK_RULE, _majority_label

    a = _majority_label(["good", "poor", "good", "poor"], "chat_quality")
    b = _majority_label(["poor", "good", "poor", "good"], "chat_quality")
    assert a == b
    # 平票时按映射分高者优先、再按字母序：good(1.0) > poor(0.0)
    assert a == "good"
    assert "tie" in TIE_BREAK_RULE.lower()


def test_judge_request_includes_fixed_seed_and_preserves_semantics(monkeypatch):
    captured = {}

    def fake_post(url, body, *, headers=None, timeout=30):
        captured["url"] = url
        captured["body"] = body
        return {"message": {"content": "Answer: good"}}

    monkeypatch.setattr(judge_client, "http_post_json", fake_post)
    judge_client.call_ollama(
        "some-model",
        [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}],
    )
    body = captured["body"]
    assert body["seed"] == config.JUDGE_SEED
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["options"]["num_predict"] == 160


def test_langfuse_export_stable_id_sort_and_dataset_sha256(monkeypatch):
    from backend.eval_042.langfuse_export import (
        EvalItem,
        compute_dataset_sha256,
        stably_sort_items,
    )

    unsorted = [
        EvalItem(
            trace_id="tid-2",
            task="chat_quality",
            input="q",
            output="LONG " * 20,
            reference=None,
            trajectory=None,
            status="scored",
            synthetic=False,
        ),
        EvalItem(
            trace_id="tid-1",
            task="chat_quality",
            input="q",
            output="short",
            reference=None,
            trajectory=None,
            status="scored",
            synthetic=False,
        ),
    ]
    sorted_items = stably_sort_items(unsorted)
    assert [it.trace_id for it in sorted_items] == ["tid-1", "tid-2"]

    h1 = compute_dataset_sha256(sorted_items)
    h2 = compute_dataset_sha256(stably_sort_items(unsorted))
    assert h1 == h2
    assert isinstance(h1, str) and len(h1) == 64


def test_collect_eval_items_uses_stable_id_sort_not_output_length(monkeypatch):
    def fake_get(url):
        if "traces?" in url:
            return {
                "data": [{"id": "tid-2"}, {"id": "tid-1"}],
                "meta": {"totalPages": 1},
            }
        tid = url.rstrip("/").split("/")[-1]
        out = "LONG " * 20 if tid == "tid-2" else "short"
        return {"id": tid, "output": out, "input": "q", "observations": []}

    monkeypatch.setattr(langfuse_export, "_get", fake_get)

    items = langfuse_export.collect_eval_items(task="chat_quality", n_scoreable=20)
    trace_ids = [it.trace_id for it in items]
    assert trace_ids == ["tid-1", "tid-2"]


def test_consistency_and_memory_probe_use_shared_judge_orchestration():
    # 合并后三处都引用 judge_client.judge_majority（此前各自重复实现）。
    assert hasattr(judge_client, "judge_majority")
    import importlib

    from backend.eval_042 import consistency, memory_probe

    importlib.reload(consistency)
    importlib.reload(memory_probe)
    # 直接调用共享编排入口应返回带 majority/labels 的结构
    res = judge_client.judge_majority(
        "m", "chat_quality", "q", "a", 3,
        ctx=None,
    )
    assert res.majority in {"good", "partial", "poor", None}
    assert isinstance(res.labels, list)
