"""service 编排契约：22 项按组出分、共用 deadline、compare 分组 delta、历史 run 兼容。

五端点路径 / 请求体 / 稳定错误码不变；新增判官与检索调用必须落在既有
_call_with_deadline(fn, remaining) 之内，不得新开无截止线程。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from batch_transport_doubles import batch_transport, chat_items

from backend.app.api import routes_models
from backend.app.evaluation import datasets, metrics, service, store
from backend.app.evaluation.contracts import (
    METRIC_GROUPS,
    METRIC_KEYS,
    EvaluationError,
    build_metric,
    get_strategy,
)
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.skills.intent import SkillDecision

RAG = "rag-retrieval"
INTENT = "intent-classification"
CHAT = "chat-quality"
MODEL = "fake-model"


def _hit(paper: str, index: int) -> Hit:
    return Hit(paper_id=paper, file_name=f"{paper}.pdf", page=1, chunk_index=index,
               text="fixture chunk", score=1.0, chunker="v1")


def _gold(dataset_id: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "schema_version": "builtin-evaluation-dataset-v1",
        "source": "builtin-fixture",
        "synthetic": True,
        "label_source": "kb-derived:retrieval-rank",
        "items": [],
    }


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    gold = tmp_path / "gold"
    gold.mkdir()
    rag = _gold(RAG)
    rag["items"] = [
        {"question": "Q1", "relevant_doc_ids": [{"paper_id": "p1", "chunker": "v1", "chunk_index": 1}]},
        {"question": "Q2", "relevant_doc_ids": [{"paper_id": "p2", "chunker": "v1", "chunk_index": 2}]},
    ]
    intent = _gold(INTENT)
    intent["items"] = [
        {"message": "m1", "expected_intent": "kb_search"},
        {"message": "m2", "expected_intent": "none"},
    ]
    (gold / f"builtin-{RAG}.json").write_text(json.dumps(rag), encoding="utf-8")
    (gold / f"builtin-{INTENT}.json").write_text(json.dumps(intent), encoding="utf-8")
    chat_gold = _gold(CHAT)
    chat_gold["items"] = chat_items(2)  # P1-4：chat 集唯一数据源是 gold 的 items
    (gold / f"builtin-{CHAT}.json").write_text(json.dumps(chat_gold), encoding="utf-8")
    chat_source = tmp_path / "chat.json"
    chat_source.write_text(
        json.dumps([
            {"trace_id": "c1", "input": "q1", "output": "a1", "status": "scored", "synthetic": False},
            {"trace_id": "c2", "input": "q2", "output": "a2", "status": "scored", "synthetic": False},
        ]),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    monkeypatch.setattr(datasets, "CHAT_DATASET_PATH", chat_source)
    monkeypatch.setattr(store, "RUNS_DIR", runs)
    monkeypatch.setattr(routes_models, "_build_local_models", lambda: [{"id": MODEL}])
    monkeypatch.setattr(routes_models, "_build_online_models", lambda *a, **k: [])
    monkeypatch.setattr(metrics, "reranker_health", lambda *a, **k: {"enabled": True, "available": False, "reason": "connection"})
    monkeypatch.setattr(metrics, "_judge_score", lambda *a, **k: 1.0)
    monkeypatch.setattr(
        metrics, "detect_skill",
        lambda message, skills: SkillDecision(status="matched", skill="kb_search", source="rule")
        if message == "m1" else SkillDecision(status="none"),
    )

    def fake_hybrid_search(question, *, top_k=None, chunker=None, **kwargs):
        table = {
            "Q1": [_hit("p1", 1), _hit("p9", 8), _hit("p8", 9)],
            "Q2": [_hit("p7", 3), _hit("p6", 4), _hit("p2", 2)],
            "q1": [_hit("p1", 1)],
            "q2": [_hit("p2", 2)],
        }
        return table.get(question, [_hit("p0", 0)])[: top_k or 5]

    monkeypatch.setattr(metrics, "hybrid_search", fake_hybrid_search)

    # 批量生成 / 批量判官协议替身（唯一传输层仍是 call_ollama，不触网）
    monkeypatch.setattr(metrics, "call_ollama", batch_transport, raising=False)
    return runs


def _body(**overrides) -> dict:
    body = {"strategy_id": "baseline", "model": MODEL, "dataset_id": RAG}
    body.update(overrides)
    return body


def _metric(payload: dict, key: str) -> dict:
    return next(entry for entry in payload["metrics"] if entry["key"] == key)


def test_score_returns_22_grouped_metrics_and_persists_full_run(sandbox):
    document = service.score(_body())

    assert len(document["metrics"]) == 22
    assert [entry["key"] for entry in document["metrics"]] == list(METRIC_KEYS)
    assert all(entry["group"] == METRIC_GROUPS[entry["key"]] for entry in document["metrics"])
    for entry in document["metrics"]:
        if entry["status"] != "computed":
            assert entry["value"] is None
            assert isinstance(entry["detail"].get("reason"), str) and entry["detail"]["reason"]
        else:
            assert isinstance(entry["value"], (int, float)) and not isinstance(entry["value"], bool)
    assert set(document) == {"run_id", "metrics", "strategy", "model", "dataset", "created_at", "judge_model"}
    assert store.load_run(document["run_id"]) == document  # save_run 不裁剪 group / 新 key


def test_new_external_calls_share_one_deadline_through_call_with_deadline(sandbox, monkeypatch):
    real = service._call_with_deadline
    timeouts: list[float] = []

    def spy(fn, timeout):
        timeouts.append(timeout)
        return real(fn, timeout)

    monkeypatch.setattr(service, "_call_with_deadline", spy)
    assert service.SCORE_TIMEOUT_SECONDS == 900.0
    # chat-quality 才会真实启动回答质量的生成 + 联合判官；跨 dataset 必须早退不出分。
    service.score(_body(dataset_id=CHAT))

    assert len(timeouts) >= 2  # chat-quality 下 judge_metrics + answer_quality 两次调用共用同一 deadline
    assert all(0 < value <= 900.0 for value in timeouts)
    assert timeouts == sorted(timeouts, reverse=True)  # 同一个 deadline，remaining 单调不增


def test_new_judge_timeout_returns_stable_score_timeout(sandbox, monkeypatch):
    monkeypatch.setattr(service, "SCORE_TIMEOUT_SECONDS", 0.05)

    def slow_metrics(*args, **kwargs):
        time.sleep(0.4)
        return {}

    monkeypatch.setattr(metrics, "answer_quality_metrics", slow_metrics)
    with pytest.raises(EvaluationError) as excinfo:
        service.score(_body(dataset_id=CHAT))
    assert excinfo.value.code == "EVAL_SCORE_TIMEOUT"


def test_compare_historical_six_metric_runs_still_work_and_deltas_get_group(sandbox):
    def old(run_id: str, value: float) -> dict:
        return {
            "run_id": run_id,
            "dataset": RAG,
            "judge_model": "qwen3.5:9b",
            "metrics": [
                {"key": "recall@k", "label": "召回率@k", "value": value, "status": "computed"},
                {"key": "mrr@k", "label": "MRR@k", "value": None, "status": "needs_ground_truth", "detail": {}},
            ],
        }

    store.save_run(old("run-a", 0.5))
    store.save_run(old("run-b", 0.75))
    payload = service.compare("run-a", "run-b")

    assert {entry["key"] for entry in payload["deltas"]} == {"recall@k", "mrr@k"}
    deltas = {entry["key"]: entry for entry in payload["deltas"]}
    assert deltas["recall@k"]["delta"] == pytest.approx(0.25)
    assert deltas["recall@k"]["group"] == "retrieval"
    assert deltas["mrr@k"]["delta"] is None
    assert deltas["mrr@k"]["group"] == "retrieval"


def test_compare_22_metric_runs_deltas_all_carry_correct_group(sandbox):
    def run(run_id: str, value: float) -> dict:
        return {
            "run_id": run_id,
            "dataset": RAG,
            "judge_model": "qwen3.5:9b",
            "metrics": [build_metric(key, value=value, sample_count=1) for key in METRIC_KEYS],
        }

    store.save_run(run("run-a", 0.5))
    store.save_run(run("run-b", 0.75))
    payload = service.compare("run-a", "run-b")

    assert len(payload["deltas"]) == 22
    for entry in payload["deltas"]:
        assert entry["group"] == METRIC_GROUPS[entry["key"]]
        assert entry["delta"] == pytest.approx(0.25)


def test_rerank_on_degrades_all_six_retrieval_keys_with_reason(sandbox):
    # 同一 dataset 内其余组仍照常真实出分：用 chat-quality 让生成维度真实出分。
    document = service.score(_body(strategy_id="rerank-on", dataset_id=CHAT))
    for key in ("recall@k", "precision@k", "mrr@k", "hit_rate@k", "ndcg@k", "retrieval_relevance"):
        metric = _metric(document, key)
        assert metric["status"] == "degraded"
        assert metric["value"] is None
        assert "reranker" in metric["detail"]["reason"]
    assert _metric(document, "generation_success_rate")["status"] == "computed"


def test_v2_without_truth_degrades_all_six_retrieval_keys(sandbox):
    document = service.score(_body(strategy_id="chunker-v2"))
    for key in ("recall@k", "precision@k", "mrr@k", "hit_rate@k", "ndcg@k", "retrieval_relevance"):
        metric = _metric(document, key)
        assert metric["status"] == "needs_ground_truth"
        assert metric["value"] is None
        assert metric["detail"]["reason"]


def test_cross_dataset_degrades_retrieval_and_intent_with_reason(sandbox):
    document = service.score(_body(dataset_id=CHAT))
    for key in (*METRIC_KEYS[:6], "intent_accuracy", "intent_macro_f1", "intent_confusion_count"):
        if METRIC_GROUPS[key] not in ("retrieval", "intent"):
            continue
        metric = _metric(document, key)
        assert metric["status"] in ("degraded", "needs_ground_truth", "unavailable")
        assert metric["value"] is None
        assert metric["detail"]["reason"]
    assert _metric(document, "chat_quality")["status"] == "computed"
    assert _metric(document, "answer_relevance")["status"] == "computed"


def test_stable_error_codes_and_run_id_traversal_are_unchanged(sandbox):
    with pytest.raises(EvaluationError) as excinfo:
        service.score(_body(model="unknown"))
    assert excinfo.value.code == "EVAL_OPTION_NOT_FOUND"
    with pytest.raises(EvaluationError) as excinfo:
        service.score(_body(dataset_id="../gold/builtin-rag-retrieval"))
    assert excinfo.value.code == "EVAL_DATASET_INVALID"
    with pytest.raises(EvaluationError) as excinfo:
        store.load_run("../outside")
    assert excinfo.value.code == "EVAL_DATASET_INVALID"
    store.save_run({"run_id": "run-a", "dataset": RAG, "judge_model": "qwen3.5:9b", "metrics": []})
    with pytest.raises(EvaluationError) as excinfo:
        service.compare("run-a", "run-a")
    assert excinfo.value.code == "EVAL_NOT_COMPARABLE"


def test_strategy_registry_and_max_items_defaults_are_unchanged(sandbox):
    assert get_strategy("baseline").top_k == 5
    assert service._clamp_max_items(None) == 100
    assert service._clamp_max_items(10_000) == 200
    document = service.score(_body(max_items=10_000))
    assert _metric(document, "recall@k")["detail"]["effective_max_items"] == 2


# --- P1 修复契约：所选评测集必须真实决定评分对象，跨 dataset 不得用 042 chat 轨迹冒充出分 ---
ANSWER_QUALITY_NEW_KEYS = (
    "answer_relevance",
    "conciseness",
    "helpfulness",
    "groundedness",
    "hallucination_free",
    "answer_exact_match",
    "levenshtein_similarity",
    "generation_success_rate",
    "answer_length_avg",
    "toxicity_free",
    "pii_leakage_free",
)
CROSS_DATASET_REASON = "所选评测集不含 042 判官轨迹，请切换到 chat-quality 评测集查看回答质量维度"


def _assert_22_grouped_metrics(document: dict) -> None:
    assert len(document["metrics"]) == 22
    assert [entry["key"] for entry in document["metrics"]] == list(METRIC_KEYS)
    assert all(entry["group"] == METRIC_GROUPS[entry["key"]] for entry in document["metrics"])


@pytest.mark.parametrize("dataset_id", [RAG, INTENT])
def test_cross_dataset_new_dimensions_need_ground_truth_without_042_traces(sandbox, monkeypatch, dataset_id):
    """rag / intent 集不含 042 判官轨迹：11 项一律 needs_ground_truth，且绝不加载 042 轨迹或启动生成/判官。"""
    forbidden_calls: list[str] = []

    def forbidden_load_chat_items():
        forbidden_calls.append("load_chat_items")
        return []

    def forbidden_answer_quality(*args, **kwargs):
        forbidden_calls.append("answer_quality_metrics")
        return {}

    def forbidden_judge_metrics(*args, **kwargs):
        forbidden_calls.append("judge_metrics")
        return {}

    monkeypatch.setattr(datasets, "load_chat_items", forbidden_load_chat_items)
    monkeypatch.setattr(metrics, "answer_quality_metrics", forbidden_answer_quality)
    monkeypatch.setattr(metrics, "judge_metrics", forbidden_judge_metrics)

    document = service.score(_body(dataset_id=dataset_id))

    _assert_22_grouped_metrics(document)
    for key in ANSWER_QUALITY_NEW_KEYS:
        metric = _metric(document, key)
        assert metric["status"] == "needs_ground_truth"
        assert metric["value"] is None
        assert metric["detail"]["reason"] == CROSS_DATASET_REASON
        assert metric["group"] == METRIC_GROUPS[key]
    assert not forbidden_calls  # 不加载 042 轨迹、不启动回答质量生成 / 联合判官 / 既有判官


def test_chat_quality_dataset_keeps_11_new_dimensions_computed_with_stub(sandbox, monkeypatch):
    """chat-quality 时 11 项行为完全不变：仍真实生成 + 联合判官出分（call_ollama 用 fake 桩，不触网）。"""
    ollama_calls: list[dict] = []
    monkeypatch.setattr(
        metrics, "call_ollama",
        lambda *args, **kwargs: batch_transport(*args, **kwargs, calls=ollama_calls),
        raising=False,
    )

    document = service.score(_body(dataset_id=CHAT))

    _assert_22_grouped_metrics(document)
    for key in ANSWER_QUALITY_NEW_KEYS:
        metric = _metric(document, key)
        assert metric["status"] == "computed"
        assert isinstance(metric["value"], (int, float)) and not isinstance(metric["value"], bool)
    assert _metric(document, "chat_quality")["status"] == "computed"
    assert ollama_calls  # 真实走了实时生成 + 联合判官（fake 传输层，未触网）
