"""评测台业务编排层：三选一打分、run 历史、两次运行的按维度对比。

API 层只做校验与编排；本层复用既有 ``/api/models`` 数据源、``hybrid_search``、
``detect_skill`` 与 ``eval_042`` 判官，不新建第二套评测框架。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from backend.app.api import routes_models
from backend.app.platform.config import RERANKER_ENABLED

from . import datasets, metrics, store
from .contracts import (
    COMPUTED,
    DEFAULT_MAX_ITEMS,
    DEGRADED,
    JUDGE_MODEL,
    MAX_ITEMS,
    METRIC_GROUPS,
    METRIC_KEYS,
    METRIC_LABELS,
    NEEDS_GROUND_TRUTH,
    SCORE_TIMEOUT_SECONDS,
    STRATEGIES,
    EvaluationError,
    get_strategy,
    strategy_to_dict,
    uncomputed_metric,
)

logger = logging.getLogger(__name__)
# P1-2：超时预算收敛到 contracts.SCORE_TIMEOUT_SECONDS 单一真源（由上方 import 提供），
# 本模块不再重复定义，避免 ``score()`` 实际生效值与契约常量不一致。

_NO_RAG_LABELS = "该评测集没有 relevant_doc_ids（当前 KB 真实片段身份）标注，不能计算检索召回指标"
_NO_INTENT_LABELS = "该评测集没有 expected_intent 标注，不能计算意图识别准确率"
_NO_JUDGE_TRACES = "该评测集没有 042 判官轨迹（input/output），不能计算回答质量"
_NO_ANSWER_QUALITY_TRACES = "所选评测集不含 042 判官轨迹，请切换到 chat-quality 评测集查看回答质量维度"
_NO_V2_LABELS = "内置 RAG 标注集只登记 v1 切分身份；v2 切分没有对应真值，跨切分版本不可比，不编造数值"


def _available_models() -> list[str]:
    """复用 GET /api/models 的构造逻辑，禁止自建第二套模型清单。"""
    local = routes_models._build_local_models()
    online = routes_models._build_online_models(False, time.monotonic())
    return [
        entry["id"]
        for entry in (*local, *online)
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
    ]


def options() -> dict[str, Any]:
    try:
        return {
            "strategies": [strategy_to_dict(strategy) for strategy in STRATEGIES.values()],
            "models": _available_models(),
            "datasets": datasets.list_datasets(),
        }
    except EvaluationError:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    except Exception:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None


def _clamp_max_items(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return DEFAULT_MAX_ITEMS
    return min(value, MAX_ITEMS)


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise EvaluationError("EVAL_SCORE_TIMEOUT")


def _call_with_deadline(fn: Callable[[], Any], timeout: float) -> Any:
    """给判官这类可能长期阻塞的外部调用加硬截止；超时返回稳定错误码。

    工作线程为 daemon，超时后不会阻止进程退出；异常只以类型名进入服务端日志，
    原始异常文本绝不进入响应 payload。
    """
    if timeout <= 0:
        raise EvaluationError("EVAL_SCORE_TIMEOUT")
    box: dict[str, Any] = {}
    done = threading.Event()

    def worker() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - 统一转成稳定错误体
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    if not done.wait(timeout):
        raise EvaluationError("EVAL_SCORE_TIMEOUT")
    error = box.get("error")
    if error is not None:
        if isinstance(error, EvaluationError):
            raise error
        logger.warning("evaluation judge failure: %s", type(error).__name__)
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    return box.get("value")


def _reranker_state() -> dict[str, Any]:
    try:
        state = metrics.reranker_state()
    except Exception:
        return {"enabled": RERANKER_ENABLED, "available": False, "reason": "health_probe_failed"}
    if not isinstance(state, dict):
        return {"enabled": RERANKER_ENABLED, "available": False, "reason": "health_probe_failed"}
    return state


def _rag_metrics(
    *,
    dataset_id: str,
    items: list[dict],
    strategy: Any,
    max_items: int,
    deadline: float,
) -> dict[str, dict]:
    keys = (
        "recall@k",
        "precision@k",
        "mrr@k",
        "hit_rate@k",
        "ndcg@k",
        "retrieval_relevance",
    )
    if strategy.reranker:
        state = _reranker_state()
        available = bool(state.get("available")) and bool(RERANKER_ENABLED)
        reason = (
            "策略请求 reranker=on，但当前 reranker available=false"
            f"（enabled={state.get('enabled')}, reason={state.get('reason')}）；"
            "hybrid_search 未产生重排收益，不出分、不伪造收益"
        ) if not available else ""
        if not available:
            return {
                key: uncomputed_metric(
                    key,
                    DEGRADED,
                    reason,
                    strategy_id=strategy.id,
                    reranker_requested=True,
                    reranker_available=False,
                    reranker_config_enabled=RERANKER_ENABLED,
                )
                for key in keys
            }
    if strategy.chunker == "v2":
        return {key: uncomputed_metric(key, NEEDS_GROUND_TRUTH, _NO_V2_LABELS, chunker="v2") for key in keys}
    if dataset_id != "rag-retrieval":
        return {key: uncomputed_metric(key, NEEDS_GROUND_TRUTH, _NO_RAG_LABELS) for key in keys}
    computed = metrics.retrieval_metrics(items, strategy, max_items)
    # 新增检索判官与检索调用共用同一个 deadline，纳入既有硬截止，不新开无截止线程。
    remaining = deadline - time.monotonic()
    computed.update(
        _call_with_deadline(
            lambda: metrics.retrieval_relevance_metrics(items, strategy, max_items, deadline=deadline),
            remaining,
        )
    )
    return computed


def _intent_metrics(*, dataset_id: str, items: list[dict], max_items: int) -> dict[str, dict]:
    keys = ("intent_accuracy", "intent_macro_f1", "intent_confusion_count")
    if dataset_id != "intent-classification":
        return {key: uncomputed_metric(key, NEEDS_GROUND_TRUTH, _NO_INTENT_LABELS) for key in keys}
    return metrics.intent_metrics(items, max_items)


def _judge_metrics(
    *, dataset_id: str, max_items: int, model: str, deadline: float,
    chat_items: list[dict] | None = None,
    live: tuple[list[str | None], list[str]] | None = None,
) -> dict[str, dict]:
    if dataset_id != "chat-quality":
        return {
            "chat_quality": uncomputed_metric("chat_quality", NEEDS_GROUND_TRUTH, _NO_JUDGE_TRACES),
            "memory_correctness": uncomputed_metric(
                "memory_correctness",
                NEEDS_GROUND_TRUTH,
                "内置 042 集没有 memory_correctness 标注，缺少可判定的记忆真值",
            ),
        }
    selected_chat_items = chat_items if chat_items is not None else datasets.load_chat_items()
    remaining = deadline - time.monotonic()
    return _call_with_deadline(
        lambda: metrics.judge_metrics(
            selected_chat_items, max_items, model, deadline=deadline, live=live
        ),
        remaining,
    )


def _answer_quality_metrics(
    *, dataset_id: str, max_items: int, model: str, deadline: float,
    chat_items: list[dict] | None = None,
    live: tuple[list[str | None], list[str]] | None = None,
) -> dict[str, dict]:
    """回答质量 / 生成 / 安全的 11 个新维度：复用 042 chat 轨迹 + 共用 deadline。

    跨 dataset 口径与 _rag_metrics / _intent_metrics / _judge_metrics 一致：
    所选评测集不是 chat-quality 时一律 needs_ground_truth + reason，不加载 042
    轨迹、不启动任何实时生成或联合判官调用（所选评测集必须真实决定评分对象）。
    ``chat_items`` / ``live`` 由 score() 编排层一次加载、一次实时生成后注入，
    与 _judge_metrics 共用同一批 answers，避免同一请求把 100 条生成两遍；
    直接调用（None）仍各自加载并实时生成，行为不变。
    """
    keys = (
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
    if dataset_id != "chat-quality":
        return {
            key: uncomputed_metric(key, NEEDS_GROUND_TRUTH, _NO_ANSWER_QUALITY_TRACES)
            for key in keys
        }
    selected_chat_items = chat_items if chat_items is not None else datasets.load_chat_items()
    remaining = deadline - time.monotonic()
    return _call_with_deadline(
        lambda: metrics.answer_quality_metrics(
            selected_chat_items, max_items, model, deadline, live=live
        ),
        remaining,
    )


def score(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    strategy_id = payload.get("strategy_id")
    model = payload.get("model")
    dataset_id = payload.get("dataset_id")
    if not all(isinstance(value, str) and value.strip() for value in (strategy_id, model, dataset_id)):
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    try:
        strategy = get_strategy(strategy_id)
        if model not in _available_models():
            raise EvaluationError("EVAL_OPTION_NOT_FOUND")
        document = datasets.load_dataset(dataset_id)
    except EvaluationError:
        raise
    except Exception:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None

    max_items = _clamp_max_items(payload.get("max_items"))
    items = document["items"] if isinstance(document["items"], list) else []
    deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS
    try:
        _check_deadline(deadline)
        computed: dict[str, dict] = {}
        computed.update(
            _rag_metrics(
                dataset_id=dataset_id,
                items=items,
                strategy=strategy,
                max_items=max_items,
                deadline=deadline,
            )
        )
        _check_deadline(deadline)
        computed.update(_intent_metrics(dataset_id=dataset_id, items=items, max_items=max_items))
        _check_deadline(deadline)
        # 同一次 chat-quality 请求只做一遍批量实时生成：judge 与 answer_quality 两族共用
        # 同一批 answers / failure_types，避免 100 条被被测模型生成两遍（10 批 → 5 批）。
        # 跨 dataset 一律早退：不加载 042 轨迹、不发任何生成 / 判官调用（原口径逐字保留）。
        shared_chat_items: list[dict] | None = None
        shared_live: tuple[list[str | None], list[str]] | None = None
        if dataset_id == "chat-quality":
            shared_chat_items = datasets.load_chat_items()
            questions = [str(item.get("input", "")) for item in shared_chat_items[:max_items]]
            shared_live = _call_with_deadline(
                lambda: metrics.generate_live_answers(questions, model, deadline),
                deadline - time.monotonic(),
            )
        computed.update(
            _judge_metrics(
                dataset_id=dataset_id, max_items=max_items, model=model, deadline=deadline,
                chat_items=shared_chat_items, live=shared_live,
            )
        )
        _check_deadline(deadline)
        computed.update(
            _answer_quality_metrics(
                dataset_id=dataset_id, max_items=max_items, model=model, deadline=deadline,
                chat_items=shared_chat_items, live=shared_live,
            )
        )
        _check_deadline(deadline)
        missing = [key for key in METRIC_KEYS if key not in computed]
        if missing:
            # 注册表缺项不能让 run_document 直接 KeyError 裸 500；转稳定 503。
            logger.warning("evaluation metric registry incomplete: %d keys", len(missing))
            raise EvaluationError("EVAL_BACKEND_UNAVAILABLE")
    except EvaluationError:
        raise
    except Exception as exc:
        logger.warning("evaluation dependency failure: %s", type(exc).__name__)
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None

    run_document = {
        "run_id": f"eval-{uuid.uuid4().hex}",
        "metrics": [computed[key] for key in METRIC_KEYS],
        "strategy": strategy_to_dict(strategy),
        "model": model,
        "dataset": dataset_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "judge_model": JUDGE_MODEL,
    }
    try:
        store.save_run(run_document)
    except EvaluationError:
        raise
    except Exception:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    return run_document


def runs() -> dict[str, Any]:
    return {"runs": store.list_runs()}


def run(run_id: str) -> dict[str, Any]:
    return store.load_run(run_id)


def compare(a: str | None, b: str | None) -> dict[str, Any]:
    if not isinstance(a, str) or not a or not isinstance(b, str) or not b:
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    if a == b:
        raise EvaluationError("EVAL_NOT_COMPARABLE")
    first = store.load_run(a)
    second = store.load_run(b)
    if first.get("dataset") != second.get("dataset") or first.get("judge_model") != second.get("judge_model"):
        raise EvaluationError("EVAL_NOT_COMPARABLE")
    first_metrics = {
        entry.get("key"): entry for entry in first.get("metrics", []) if isinstance(entry, dict)
    }
    second_metrics = {
        entry.get("key"): entry for entry in second.get("metrics", []) if isinstance(entry, dict)
    }
    deltas = []
    for key in METRIC_KEYS:
        if key not in first_metrics or key not in second_metrics:
            continue
        left, right = first_metrics[key], second_metrics[key]
        value_a = left.get("value") if left.get("status") == COMPUTED else None
        value_b = right.get("value") if right.get("status") == COMPUTED else None
        delta = value_b - value_a if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)) else None
        deltas.append(
            {
                "key": key,
                "label": METRIC_LABELS[key],
                "group": METRIC_GROUPS.get(key, "other"),
                "value_a": value_a,
                "value_b": value_b,
                "delta": delta,
                "status_a": left.get("status"),
                "status_b": right.get("status"),
            }
        )
    return {
        "a": a,
        "b": b,
        "dataset": first.get("dataset"),
        "judge_model": first.get("judge_model"),
        "deltas": deltas,
    }
