"""评测台共享契约：稳定错误码、策略预设注册表、指标结果构造器。

稳定错误体只携带 code / message / retryable / request_id，绝不携带原始异常文本
（回归清单第 11、14 条）。所有指标结果都由 ``build_metric`` 构造，保证
``status != computed`` 时 ``value`` 恒为 ``None``。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.eval_042.config import PRIMARY_JUDGE

# 判官固定取既有 042 配置，不由请求中的 model（被测模型）指定。
JUDGE_MODEL = PRIMARY_JUDGE
JUDGE_REPEATS = 1
# spec-047 追加范围三 §13.1 P1-2：三常量收敛到本文件为唯一真源。
# 900s 是 Go/No-Go 硬判据的时间预算（300s 仅为优化目标线，不是失败线）。
DEFAULT_MAX_ITEMS = 100
MAX_ITEMS = 200
SCORE_TIMEOUT_SECONDS = 900.0

ERROR_SPECS: dict[str, tuple[int, str, bool]] = {
    "EVAL_OPTION_NOT_FOUND": (404, "评测选项不存在", False),
    "EVAL_DATASET_INVALID": (400, "评测集或运行标识无效", False),
    "EVAL_BACKEND_UNAVAILABLE": (503, "评测依赖暂时不可用", True),
    "EVAL_SCORE_TIMEOUT": (504, "评测打分超时", True),
    "EVAL_NOT_COMPARABLE": (409, "两次运行不可比较", False),
}

DATASET_IDS = ("rag-retrieval", "intent-classification", "chat-quality")
DATASET_LABELS = {
    "rag-retrieval": "RAG 检索召回",
    "intent-classification": "意图识别分类",
    "chat-quality": "回答质量（既有判官轨迹）",
}
# 注册表顺序固定：先既有 6 项（顺序与语义不变），再追加 16 项。
# score 的 metrics[] 与 compare 的 deltas[] 都以本元组为唯一遍历源。
METRIC_KEYS = (
    "recall@k",
    "precision@k",
    "mrr@k",
    "intent_accuracy",
    "chat_quality",
    "memory_correctness",
    "hit_rate@k",
    "ndcg@k",
    "retrieval_relevance",
    "intent_macro_f1",
    "intent_confusion_count",
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
METRIC_LABELS = {
    "recall@k": "召回率@k",
    "precision@k": "准确率@k",
    "mrr@k": "MRR@k",
    "intent_accuracy": "意图识别准确率",
    "chat_quality": "回答质量（判官均分）",
    "memory_correctness": "记忆正确性（判官均分）",
    "hit_rate@k": "命中率@k",
    "ndcg@k": "nDCG@k（二值相关性）",
    "retrieval_relevance": "检索片段相关性",
    "intent_macro_f1": "意图宏平均 F1",
    "intent_confusion_count": "意图误判样本数",
    "answer_relevance": "回答切题度",
    "conciseness": "回答简洁度",
    "helpfulness": "回答有用性",
    "groundedness": "回答有据性",
    "hallucination_free": "无幻觉比例",
    "answer_exact_match": "回答字面完全一致率",
    "levenshtein_similarity": "回答编辑相似度",
    "generation_success_rate": "实时生成成功率",
    "answer_length_avg": "实时回答平均字符数",
    "toxicity_free": "无有害内容比例",
    "pii_leakage_free": "无个人信息泄漏比例",
}
# 5 个分组；历史 run 无 group 时由前端兜底 other，compare 用 .get(key, "other")。
METRIC_GROUPS: dict[str, str] = {
    "recall@k": "retrieval",
    "precision@k": "retrieval",
    "mrr@k": "retrieval",
    "hit_rate@k": "retrieval",
    "ndcg@k": "retrieval",
    "retrieval_relevance": "retrieval",
    "intent_accuracy": "intent",
    "intent_macro_f1": "intent",
    "intent_confusion_count": "intent",
    "chat_quality": "answer_quality",
    "memory_correctness": "answer_quality",
    "answer_relevance": "answer_quality",
    "conciseness": "answer_quality",
    "helpfulness": "answer_quality",
    "groundedness": "answer_quality",
    "hallucination_free": "answer_quality",
    "answer_exact_match": "answer_quality",
    "levenshtein_similarity": "answer_quality",
    "generation_success_rate": "generation",
    "answer_length_avg": "generation",
    "toxicity_free": "safety",
    "pii_leakage_free": "safety",
}
# 联合判官的枚举→分数映射（登记在契约层，rubrics.py 只负责解析与传输）。
# 对 *_free / hallucination_free，good 表示未发现该问题，方向统一「越高越好」。
RUBRIC_ENUM_MAPS: dict[str, float] = {"good": 1.0, "mixed": 0.5, "poor": 0.0}
COMPUTED = "computed"
DEGRADED = "degraded"
NEEDS_GROUND_TRUTH = "needs_ground_truth"
UNAVAILABLE = "unavailable"


class EvaluationError(Exception):
    """可预期的评测失败；``str(exc)`` 只有稳定错误码，不含内部细节。"""

    def __init__(self, code: str) -> None:
        if code not in ERROR_SPECS:
            code = "EVAL_BACKEND_UNAVAILABLE"
        super().__init__(code)
        self.code = code
        self.status, self.message, self.retryable = ERROR_SPECS[code]


def error_payload(code: str, request_id: str) -> dict[str, Any]:
    """构造稳定错误体（同时提供顶层 error_code 与 error.code 两种读取方式）。"""
    status, message, retryable = ERROR_SPECS[code]
    del status  # 状态码由 JSONResponse 使用，不重复进 payload
    return {
        "error_code": code,
        "message": message,
        "retryable": retryable,
        "request_id": request_id,
        "error": {"code": code, "message": message},
    }


@dataclass(frozen=True)
class Strategy:
    id: str
    label: str
    chunker: str
    top_k: int
    reranker: bool


# 策略预设注册表：参数真实传给 hybrid_search（chunker / top_k）；reranker 由
# retrieve.py 内部按 RERANKER_ENABLED 真实启用，并用 reranker_health() 探测可用性。
STRATEGIES: dict[str, Strategy] = {
    "baseline": Strategy("baseline", "基线（v1 / top_k=5 / reranker=off）", "v1", 5, False),
    "chunker-v2": Strategy("chunker-v2", "切分 v2（top_k=5 / reranker=off）", "v2", 5, False),
    "topk-10": Strategy("topk-10", "扩大召回（v1 / top_k=10 / reranker=off）", "v1", 10, False),
    "rerank-on": Strategy("rerank-on", "启用重排（v1 / top_k=5 / reranker=on）", "v1", 5, True),
}


def get_strategy(strategy_id: str) -> Strategy:
    strategy = STRATEGIES.get(strategy_id)
    if strategy is None:
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    return strategy


def strategy_to_dict(strategy: Strategy) -> dict[str, Any]:
    return {
        "id": strategy.id,
        "label": strategy.label,
        "chunker": strategy.chunker,
        "top_k": strategy.top_k,
        "reranker": "on" if strategy.reranker else "off",
    }


def build_metric(
    key: str,
    *,
    value: float | None = None,
    status: str = COMPUTED,
    sample_count: int = 0,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造单个指标；非 computed 一律 null，且 detail 必须带 reason。"""
    payload_detail = dict(detail or {})
    if status != COMPUTED:
        value = None
        if not payload_detail.get("reason"):
            raise ValueError(f"metric {key} with status={status} must carry detail.reason")
    return {
        "key": key,
        "label": METRIC_LABELS[key],
        "group": METRIC_GROUPS.get(key, "other"),
        "value": value,
        "status": status,
        "sample_count": int(sample_count),
        "detail": payload_detail,
    }


def uncomputed_metric(key: str, status: str, reason: str, **detail: Any) -> dict[str, Any]:
    return build_metric(key, status=status, sample_count=0, detail={**detail, "reason": reason})
