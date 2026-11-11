"""评测台五个端点的后端契约测试（离线 fake 依赖，产品代码不得 mock 分数）。

覆盖：三选一校验、五个稳定错误码、只读白名单防穿越、不可比不含 delta、
非 computed 维度 value=null + reason、指标可复算、重复提交独立 run_id、
run 产物与响应一致、按维度 delta。所有外部依赖在用例内以可控 fake 替换。
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from batch_transport_doubles import batch_transport, chat_items
from fastapi.testclient import TestClient

from backend.app.api import routes_models
from backend.app.evaluation import datasets, metrics, service, store
from backend.app.evaluation.contracts import METRIC_GROUPS, METRIC_KEYS
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.main import app
from backend.app.skills.intent import SkillDecision

RAG_DATASET_ID = "rag-retrieval"
INTENT_DATASET_ID = "intent-classification"
CHAT_DATASET_ID = "chat-quality"
MODEL_ID = "fake-model"
STRATEGY_ID = "baseline"


def _hit(paper: str, chunker: str, index: int) -> Hit:
    return Hit(
        paper_id=paper,
        file_name=f"{paper}.pdf",
        page=1,
        chunk_index=index,
        text="fixture chunk",
        score=1.0,
        chunker=chunker,
    )


def _gold_rag() -> dict:
    return {
        "dataset_id": RAG_DATASET_ID,
        "schema_version": "builtin-evaluation-dataset-v1",
        "source": "builtin-fixture",
        "synthetic": True,
        "label_source": "kb-derived:retrieval-rank",
        "items": [
            {
                "id": "rag-1",
                "question": "Q1",
                "relevant_doc_ids": [{"paper_id": "p1", "chunker": "v1", "chunk_index": 1, "page": 1}],
            },
            {
                "id": "rag-2",
                "question": "Q2",
                "relevant_doc_ids": [{"paper_id": "p2", "chunker": "v1", "chunk_index": 2, "page": 2}],
            },
        ],
    }


def _gold_intent() -> dict:
    return {
        "dataset_id": INTENT_DATASET_ID,
        "schema_version": "builtin-evaluation-dataset-v1",
        "source": "builtin-fixture",
        "synthetic": True,
        "label_source": "registry-derived",
        "items": [
            {"id": "intent-1", "message": "请使用 kb_search 技能检索片段", "expected_intent": "kb_search"},
            {"id": "intent-2", "message": "请解释一下 TCP 三次握手", "expected_intent": "none"},
        ],
    }


def _gold_chat() -> dict:
    return {
        "dataset_id": CHAT_DATASET_ID,
        "schema_version": "builtin-evaluation-dataset-v1",
        "source": "builtin-fixture",
        "synthetic": True,
        "label_source": "frozen-trace-reference",
        "source_path": "docs/sdd/plans/042/task-02-eval-dataset.json",
        "item_count": 2,
        "items": chat_items(2),
    }


def _chat_source() -> list:
    return [
        {"trace_id": "c1", "task": "chat_quality", "input": "q1", "output": "a1", "status": "scored", "synthetic": False},
        {"trace_id": "c2", "task": "chat_quality", "input": "q2", "output": "a2", "status": "scored", "synthetic": False},
        {"trace_id": "c3", "task": "chat_quality", "input": "q3", "output": "a3", "status": "skipped", "synthetic": True},
    ]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sandbox(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="evaluation-contract-"))
    gold = base / "gold"
    runs = base / "runs"
    gold.mkdir()
    runs.mkdir()
    (gold / f"builtin-{RAG_DATASET_ID}.json").write_text(json.dumps(_gold_rag()), encoding="utf-8")
    (gold / f"builtin-{INTENT_DATASET_ID}.json").write_text(json.dumps(_gold_intent()), encoding="utf-8")
    (gold / f"builtin-{CHAT_DATASET_ID}.json").write_text(json.dumps(_gold_chat()), encoding="utf-8")
    chat_source = base / "chat.json"
    chat_source.write_text(json.dumps(_chat_source()), encoding="utf-8")

    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    monkeypatch.setattr(datasets, "CHAT_DATASET_PATH", chat_source)
    monkeypatch.setattr(store, "RUNS_DIR", runs)
    monkeypatch.setattr(routes_models, "_build_local_models", lambda: [{"id": MODEL_ID}])
    monkeypatch.setattr(routes_models, "_build_online_models", lambda *a, **k: [])
    monkeypatch.setattr(
        metrics,
        "reranker_health",
        lambda *a, **k: {"enabled": True, "available": False, "reason": "connection"},
    )
    monkeypatch.setattr(metrics, "_judge_score", lambda *a, **k: 1.0)
    # 隔离被测模型实时生成的外部依赖：契约测试不触碰 Ollama，产品代码仍真实调用。
    # 批量生成 / 批量判官协议替身（唯一传输层仍是 call_ollama，不触网）
    monkeypatch.setattr(metrics, "call_ollama", batch_transport, raising=False)

    def fake_hybrid_search(question, *, top_k=None, chunker=None, **kwargs):
        table = {
            "Q1": [_hit("p1", "v1", 1), _hit("p9", "v1", 8), _hit("p8", "v1", 9)],
            "Q2": [_hit("p7", "v1", 3), _hit("p6", "v1", 4), _hit("p2", "v1", 2)],
        }
        return table.get(question, [])[: top_k or 5]

    monkeypatch.setattr(metrics, "hybrid_search", fake_hybrid_search)

    def fake_detect_skill(message, available_skills):
        if "kb_search" in message:
            return SkillDecision(status="matched", skill="kb_search", source="rule")
        return SkillDecision(status="none")

    monkeypatch.setattr(metrics, "detect_skill", fake_detect_skill)
    try:
        yield SimpleNamespace(base=base, gold=gold, runs=runs, chat_source=chat_source)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _score_body(**overrides) -> dict:
    body = {
        "strategy_id": STRATEGY_ID,
        "model": MODEL_ID,
        "dataset_id": RAG_DATASET_ID,
    }
    body.update(overrides)
    return body


def _assert_error(response, code: int, error_code: str):
    assert response.status_code == code
    payload = response.json()
    assert payload["error_code"] == error_code
    assert payload["error"]["code"] == error_code
    assert isinstance(payload["message"], str) and payload["message"]
    assert isinstance(payload["retryable"], bool)
    assert payload["request_id"]
    return payload


def _computed(payload, key: str) -> dict:
    return next(metric for metric in payload["metrics"] if metric["key"] == key)


def test_options_returns_strategies_models_and_datasets(client, sandbox):
    response = client.get("/api/evaluation/options")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"strategies", "models", "datasets"}
    strategy_ids = {entry["id"] for entry in payload["strategies"]}
    assert {"baseline", "chunker-v2", "topk-10", "rerank-on"} <= strategy_ids
    assert payload["models"] == [MODEL_ID]
    assert {entry["id"] for entry in payload["datasets"]} == {
        RAG_DATASET_ID,
        INTENT_DATASET_ID,
        CHAT_DATASET_ID,
    }


@pytest.mark.parametrize(
    "body",
    [
        {"strategy_id": ""},
        {"model": ""},
        {"dataset_id": ""},
        {"strategy_id": None},
        {"model": "unknown-model"},
        {"strategy_id": "unknown-strategy"},
    ],
)
def test_score_rejects_empty_or_unknown_options(client, sandbox, body):
    response = client.post("/api/evaluation/score", json=_score_body(**body))
    _assert_error(response, 404, "EVAL_OPTION_NOT_FOUND")


@pytest.mark.parametrize(
    "dataset_id",
    ["unknown-dataset", "../gold/builtin-rag-retrieval", "/etc/passwd", "nested/path"],
)
def test_score_rejects_unknown_and_traversing_dataset_ids(client, sandbox, dataset_id):
    response = client.post("/api/evaluation/score", json=_score_body(dataset_id=dataset_id))
    _assert_error(response, 400, "EVAL_DATASET_INVALID")


def test_run_id_path_traversal_is_rejected(sandbox):
    from backend.app.evaluation.contracts import EvaluationError

    with pytest.raises(EvaluationError) as excinfo:
        store.load_run("../outside")
    assert excinfo.value.code == "EVAL_DATASET_INVALID"
    with pytest.raises(EvaluationError) as excinfo:
        store.load_run("/etc/passwd")
    assert excinfo.value.code == "EVAL_DATASET_INVALID"


def test_all_five_error_codes_have_stable_error_bodies(client, sandbox, monkeypatch):
    # EVAL_OPTION_NOT_FOUND：未知模型
    _assert_error(
        client.post("/api/evaluation/score", json=_score_body(model="missing")),
        404,
        "EVAL_OPTION_NOT_FOUND",
    )
    # EVAL_DATASET_INVALID：白名单外评测集
    _assert_error(
        client.post("/api/evaluation/score", json=_score_body(dataset_id="missing")),
        400,
        "EVAL_DATASET_INVALID",
    )
    # EVAL_BACKEND_UNAVAILABLE：外部依赖抛异常，且异常文本不进 payload
    def exploding_search(*args, **kwargs):
        raise RuntimeError("SENSITIVE /etc/passwd SELECT * FROM secrets")

    monkeypatch.setattr(metrics, "hybrid_search", exploding_search)
    backend_error = client.post("/api/evaluation/score", json=_score_body())
    payload = _assert_error(backend_error, 503, "EVAL_BACKEND_UNAVAILABLE")
    assert "SENSITIVE" not in json.dumps(payload)
    assert "/etc/passwd" not in json.dumps(payload)
    assert "str(exc)" not in json.dumps(payload)

    # EVAL_SCORE_TIMEOUT：判官实时生成超过服务端截止时间
    monkeypatch.setattr(service, "SCORE_TIMEOUT_SECONDS", 0.05)

    def slow_judge(*args, **kwargs):
        time.sleep(0.4)
        return {}

    monkeypatch.setattr(metrics, "judge_metrics", slow_judge)
    timeout_error = client.post("/api/evaluation/score", json=_score_body(dataset_id=CHAT_DATASET_ID))
    _assert_error(timeout_error, 504, "EVAL_SCORE_TIMEOUT")

    # EVAL_NOT_COMPARABLE：跨 dataset，响应里不带 delta
    store.save_run({"run_id": "run-a", "dataset": RAG_DATASET_ID, "judge_model": "qwen3.5:9b", "metrics": []})
    store.save_run({"run_id": "run-b", "dataset": INTENT_DATASET_ID, "judge_model": "qwen3.5:9b", "metrics": []})
    not_comparable = client.get("/api/evaluation/compare?a=run-a&b=run-b")
    payload = _assert_error(not_comparable, 409, "EVAL_NOT_COMPARABLE")
    assert "delta" not in payload
    assert "deltas" not in payload
    assert "delta" not in json.dumps(payload)


def test_compare_rejects_cross_judge_and_identical_runs_without_delta(client, sandbox):
    store.save_run({"run_id": "run-a", "dataset": RAG_DATASET_ID, "judge_model": "qwen3.5:9b", "metrics": []})
    store.save_run({"run_id": "run-b", "dataset": RAG_DATASET_ID, "judge_model": "other-judge", "metrics": []})
    payload = _assert_error(client.get("/api/evaluation/compare?a=run-a&b=run-b"), 409, "EVAL_NOT_COMPARABLE")
    assert "deltas" not in payload
    payload = _assert_error(client.get("/api/evaluation/compare?a=run-a&b=run-a"), 409, "EVAL_NOT_COMPARABLE")
    assert "deltas" not in payload
    _assert_error(client.get("/api/evaluation/compare?a=missing&b=run-a"), 404, "EVAL_OPTION_NOT_FOUND")


def test_non_computed_metrics_have_null_value_and_reason(client, sandbox):
    for dataset_id in (RAG_DATASET_ID, INTENT_DATASET_ID, CHAT_DATASET_ID):
        response = client.post("/api/evaluation/score", json=_score_body(dataset_id=dataset_id))
        assert response.status_code == 200
        payload = response.json()
        # 追加范围二：注册表 6 → 22 项，每项带 group；历史 6 项的语义断言逐字保留。
        assert {m["key"] for m in payload["metrics"]} == set(METRIC_KEYS)
        for metric in payload["metrics"]:
            assert metric["sample_count"] >= 0
            assert set(metric) == {"key", "label", "value", "status", "sample_count", "detail", "group"}
            assert metric["group"] == METRIC_GROUPS[metric["key"]]
            if metric["status"] != "computed":
                assert metric["value"] is None
                assert isinstance(metric["detail"].get("reason"), str) and metric["detail"]["reason"]
            else:
                assert isinstance(metric["value"], (int, float)) and not isinstance(metric["value"], bool)


def test_rerank_on_reports_degraded_when_reranker_unavailable(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body(strategy_id="rerank-on"))
    assert response.status_code == 200
    payload = response.json()
    for key in ("recall@k", "precision@k", "mrr@k"):
        metric = _computed(payload, key)
        assert metric["status"] == "degraded"
        assert metric["value"] is None
        assert "reranker" in metric["detail"]["reason"]
        assert metric["detail"]["reason"]


def test_chunker_v2_without_v2_labels_reports_needs_ground_truth(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body(strategy_id="chunker-v2"))
    assert response.status_code == 200
    payload = response.json()
    for key in ("recall@k", "precision@k", "mrr@k"):
        metric = _computed(payload, key)
        assert metric["status"] == "needs_ground_truth"
        assert metric["value"] is None
        assert metric["detail"]["reason"]


def test_retrieval_metrics_are_recomputed_from_hybrid_search_hits(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body())
    assert response.status_code == 200
    payload = response.json()
    recall = _computed(payload, "recall@k")
    precision = _computed(payload, "precision@k")
    mrr = _computed(payload, "mrr@k")
    assert recall["status"] == "computed"
    assert recall["sample_count"] == 2
    assert recall["value"] == 1.0  # 两题的相关片段都在 top-k 中
    assert precision["value"] == 2 / 6  # 每题 3 条真实命中
    assert mrr["value"] == (1 + 1 / 3) / 2
    assert recall["detail"]["k"] == 5
    assert recall["detail"]["chunker"] == "v1"
    assert recall["detail"]["effective_max_items"] == 2


def test_intent_accuracy_is_recomputed_from_detect_skill(client, sandbox, monkeypatch):
    monkeypatch.setattr(
        metrics,
        "detect_skill",
        lambda message, available_skills: SkillDecision(status="matched", skill="kb_search", source="rule"),
    )
    response = client.post("/api/evaluation/score", json=_score_body(dataset_id=INTENT_DATASET_ID))
    assert response.status_code == 200
    metric = _computed(response.json(), "intent_accuracy")
    assert metric["status"] == "computed"
    assert metric["value"] == 0.5  # 第二条期望 none，fake 仍返回 kb_search
    assert metric["sample_count"] == 2


def test_chat_quality_uses_existing_judge_and_keeps_judge_separate_from_model(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body(dataset_id=CHAT_DATASET_ID))
    assert response.status_code == 200
    payload = response.json()
    metric = _computed(payload, "chat_quality")
    assert metric["status"] == "computed"
    assert metric["value"] == 1.0
    assert metric["sample_count"] == 2
    assert metric["detail"]["judge_model"] == "qwen3.5:9b"
    assert metric["detail"]["under_test_model"] == MODEL_ID
    assert _computed(payload, "memory_correctness")["status"] == "needs_ground_truth"


def test_repeated_submissions_get_independent_run_ids(client, sandbox):
    first = client.post("/api/evaluation/score", json=_score_body())
    second = client.post("/api/evaluation/score", json=_score_body())
    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] != second.json()["run_id"]
    assert (sandbox.runs / f"{first.json()['run_id']}.json").is_file()
    assert (sandbox.runs / f"{second.json()['run_id']}.json").is_file()


def test_run_artifact_matches_post_response_and_run_endpoints(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body())
    assert response.status_code == 200
    posted = response.json()
    assert set(posted) >= {"run_id", "metrics", "strategy", "model", "dataset", "created_at"}
    assert posted["created_at"].endswith("Z") or posted["created_at"].endswith("+00:00")
    artifact = json.loads((sandbox.runs / f"{posted['run_id']}.json").read_text(encoding="utf-8"))
    assert artifact == posted
    listing = client.get("/api/evaluation/runs")
    assert listing.status_code == 200
    assert posted["run_id"] in [entry["run_id"] for entry in listing.json()["runs"]]
    detail = client.get(f"/api/evaluation/runs/{posted['run_id']}")
    assert detail.status_code == 200
    assert detail.json() == posted
    _assert_error(client.get("/api/evaluation/runs/does-not-exist"), 404, "EVAL_OPTION_NOT_FOUND")


def test_compare_same_dataset_reports_per_dimension_delta(client, sandbox):
    def run(run_id: str, value: float) -> dict:
        return {
            "run_id": run_id,
            "dataset": RAG_DATASET_ID,
            "judge_model": "qwen3.5:9b",
            "metrics": [
                {"key": "recall@k", "label": "召回率", "value": value, "status": "computed"},
                {"key": "mrr@k", "label": "MRR", "value": None, "status": "needs_ground_truth"},
            ],
        }

    store.save_run(run("run-a", 0.5))
    store.save_run(run("run-b", 0.75))
    response = client.get("/api/evaluation/compare?a=run-a&b=run-b")
    assert response.status_code == 200
    payload = response.json()
    deltas = {entry["key"]: entry for entry in payload["deltas"]}
    assert deltas["recall@k"]["delta"] == pytest.approx(0.25)
    assert deltas["recall@k"]["value_a"] == 0.5
    assert deltas["recall@k"]["value_b"] == 0.75
    assert deltas["mrr@k"]["delta"] is None


def test_max_items_is_clamped_to_server_cap(client, sandbox):
    response = client.post("/api/evaluation/score", json=_score_body(max_items=10_000))
    assert response.status_code == 200
    assert _computed(response.json(), "recall@k")["detail"]["effective_max_items"] == 2
    response = client.post("/api/evaluation/score", json=_score_body(max_items=0))
    assert response.status_code == 200
    assert _computed(response.json(), "recall@k")["sample_count"] == 2
