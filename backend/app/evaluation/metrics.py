"""多维度指标的真实计算（不 mock 数值、不硬编码分数）。

- RAG：调用既有 ``retrieve.hybrid_search``，把 top-k ``Hit`` 的
  ``(paper_id, chunker, chunk_index)`` 与标注集身份 join 后算 recall/precision/mrr；
- 意图：调用既有 ``intent.detect_skill``，与 ``expected_intent`` 比对；
- 回答质量：``chat_quality`` 逐字沿用既有 ``judge_majority`` + ``enum_to_score``；
  新增维度走 ``rubrics.py`` 的联合判官（复用 ``call_ollama`` 唯一传输层）+ 规则 / 诊断量。

纯数学函数（aggregate_retrieval / intent_accuracy / judge_average /
hit_rate_from_ranks / binary_ndcg / intent_macro_f1 / levenshtein_similarity）独立可复算，
便于契约测试用可控 fixture 验证，不依赖知识库或 Ollama。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Sequence

from backend.app.knowledge_base.infrastructure.retrieve import hybrid_search, reranker_health
from backend.app.skills.intent import detect_skill
from backend.app.skills.models import SkillSummary
from backend.app.skills.registry import build_default_tool_registry
from backend.eval_042.judge_client import call_ollama, enum_to_score, judge_majority
from backend.eval_042.runner import KNOWN_TASKS

from . import rubrics
from .contracts import (
    DEGRADED,
    JUDGE_MODEL,
    JUDGE_REPEATS,
    NEEDS_GROUND_TRUTH,
    SCORE_TIMEOUT_SECONDS,
    UNAVAILABLE,
    EvaluationError,
    Strategy,
    build_metric,
)

HitKey = tuple[str, str, int]

# 单批（B=20）实时生成 / 判官的硬超时上限；整批仍由 score() 的同一个 deadline
# 通过 _bounded_timeout 收紧，不新开无截止线程。
GENERATION_TIMEOUT_SECONDS = 180.0
# spec-047 追加范围三：批量实时生成与批量判官的批大小。100 条 = 5 批。
BATCH_SIZE = 20
# 批量 JSON 输出远大于 call_ollama 默认 160；显式传入覆盖，默认行为 160 不变（P1-3）。
BATCH_NUM_PREDICT = 2048
# 冻结 042 trace 的 input 是完整多轮对话记录（可达数千字符）。只取尾部最新用户问题
# 送入模型与真实检索，避免超长 prompt 拖垮本地模型；该上限在 detail 中如实标注。
MAX_QUESTION_CHARS = 600
# 真实 Hit.text 拼接进判官 prompt 前的安全截断长度（字符）。
CONTEXT_PER_HIT_MAX_CHARS = 400
CONTEXT_MAX_CHARS = 1200
_LITERAL_REFERENCE = "frozen-042-output"
_LITERAL_NOTE = "字面一致性，不代表回答质量"


@dataclass
class RetrievalCase:
    """单条评测样本：标注的相关片段身份 + 真实检索返回的 top-k 身份序列。"""

    relevant_keys: set[HitKey]
    hit_keys: list[HitKey]


def aggregate_retrieval(cases: Sequence[RetrievalCase], k: int) -> dict[str, Any]:
    """按样本平均的 recall@k / precision@k / mrr@k；k 越界按实际返回条数收敛。"""
    if not cases:
        return {
            "sample_count": 0,
            "recall": None,
            "precision": None,
            "mrr": None,
            "matched_items": 0,
            "first_relevant_ranks": [],
            "effective_k": 0,
            "hit_rate": None,
            "ndcg": None,
            "ndcg_valid_cases": 0,
            "ndcg_skipped_cases": 0,
        }
    recall_sum = 0.0
    precision_sum = 0.0
    mrr_sum = 0.0
    ranks: list[int | None] = []
    effective_ks: list[int] = []
    ndcg_values: list[float] = []
    ndcg_skipped = 0
    matched_items = 0
    for case in cases:
        effective_k = min(max(1, int(k)), len(case.hit_keys))
        effective_ks.append(effective_k)
        hits = case.hit_keys[:effective_k]
        relevant = set(case.relevant_keys)
        matched = len(relevant & set(hits))
        recall_sum += matched / len(relevant) if relevant else 0.0
        precision_sum += matched / effective_k if effective_k else 0.0
        first_rank = next((position for position, key in enumerate(hits, start=1) if key in relevant), None)
        ranks.append(first_rank)
        mrr_sum += 1.0 / first_rank if first_rank else 0.0
        if matched:
            matched_items += 1
        ndcg = binary_ndcg(hits, relevant)
        if ndcg is None:
            ndcg_skipped += 1
        else:
            ndcg_values.append(ndcg)
    count = len(cases)
    return {
        "sample_count": count,
        "recall": recall_sum / count,
        "precision": precision_sum / count,
        "mrr": mrr_sum / count,
        "matched_items": matched_items,
        "first_relevant_ranks": ranks,
        "effective_k": max(effective_ks, default=0),
        "hit_rate": hit_rate_from_ranks(ranks),
        "ndcg": sum(ndcg_values) / len(ndcg_values) if ndcg_values else None,
        "ndcg_valid_cases": len(ndcg_values),
        "ndcg_skipped_cases": ndcg_skipped,
    }


def intent_accuracy(predictions: Sequence[str | None], expected: Sequence[str]) -> float | None:
    if not expected:
        return None
    return sum(1 for predicted, label in zip(predictions, expected, strict=False) if predicted == label) / len(expected)


def judge_average(scores: Sequence[float | None]) -> float | None:
    usable = [
        float(score)
        for score in scores
        if isinstance(score, (int, float)) and not isinstance(score, bool)
    ]
    return sum(usable) / len(usable) if usable else None


def hit_rate_from_ranks(ranks: Sequence[int | None]) -> float | None:
    """至少命中 1 条相关片段的样本占比；空样本集返回 None（由调用方降级）。"""
    if not ranks:
        return None
    return sum(1 for rank in ranks if rank is not None) / len(ranks)


def binary_ndcg(hit_keys: Sequence[HitKey], relevant_keys: set[HitKey]) -> float | None:
    """二值相关性 DCG / 理想 DCG；理想 DCG=0 时返回 None，不除零、不出 0.0000 假分。"""
    relevant = set(relevant_keys)
    ideal_terms = min(len(relevant), len(hit_keys))
    if ideal_terms == 0:
        return None
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_terms + 1))
    if ideal <= 0:
        return None
    seen: set[HitKey] = set()
    dcg = 0.0
    for rank, key in enumerate(hit_keys, start=1):
        if key in relevant and key not in seen:
            dcg += 1.0 / math.log2(rank + 1)
            seen.add(key)
    return dcg / ideal


def _intent_confusion(predictions: Sequence[str | None], expected: Sequence[str]) -> dict[str, Any]:
    """单次遍历产出逐类 precision/recall/F1、宏平均与误判数，供三个意图维度共用。"""
    pairs = list(zip(predictions, expected, strict=False))
    labels = sorted({str(label) for label in (*predictions, *expected) if label is not None})
    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        tp = sum(1 for predicted, reference in pairs if predicted == label and reference == label)
        fp = sum(1 for predicted, reference in pairs if predicted == label and reference != label)
        fn = sum(1 for predicted, reference in pairs if predicted != label and reference == label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
    macro_f1 = (
        sum(float(entry["f1"]) for entry in per_class.values()) / len(per_class) if per_class else None
    )
    return {
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_count": sum(1 for predicted, reference in pairs if predicted != reference),
    }


def intent_macro_f1(predictions: Sequence[str | None], expected: Sequence[str]) -> float | None:
    return _intent_confusion(predictions, expected)["macro_f1"]


def levenshtein_similarity(a: str, b: str) -> float:
    """归一化编辑相似度 [0,1]；空串对空串 1.0，单边空串 0.0。"""
    left, right = str(a), str(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, start=1):
        current = [row]
        for column, char_right in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (0 if char_left == char_right else 1),
                )
            )
        previous = current
    distance = previous[-1]
    return max(0.0, min(1.0, 1.0 - distance / max(len(left), len(right))))


def _effective_deadline(deadline: float | None) -> float:
    """直接调用（非 service 编排）时给一个同预算的默认截止，便于单测与复用。"""
    return deadline if deadline is not None else time.monotonic() + SCORE_TIMEOUT_SECONDS


def _bounded_timeout(deadline: float, cap: float) -> float:
    """新增外部调用一律以共用 deadline 收紧 timeout；超时转稳定 EVAL_SCORE_TIMEOUT。"""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EvaluationError("EVAL_SCORE_TIMEOUT")
    return min(cap, remaining)


def _degraded(key: str, reason: str, **detail: Any) -> dict[str, Any]:
    return build_metric(key, status=DEGRADED, detail={**detail, "reason": reason})


def _unavailable(key: str, reason: str, **detail: Any) -> dict[str, Any]:
    return build_metric(key, status=UNAVAILABLE, detail={**detail, "reason": reason})


def _retrieved_context(question: str, strategy: Strategy | None = None) -> str | None:
    """复用既有 hybrid_search 取真实 Hit.text；KB 不可用返回 None，由调用方降级，不伪造。"""
    try:
        hits = hybrid_search(
            question,
            top_k=strategy.top_k if strategy else 5,
            chunker=strategy.chunker if strategy else "v1",
        )
    except Exception:  # noqa: BLE001 - 依赖失败只记状态，不外抛原始异常文本
        return None
    texts = [
        str(getattr(hit, "text", ""))[:CONTEXT_PER_HIT_MAX_CHARS].strip()
        for hit in hits
        if str(getattr(hit, "text", "")).strip()
    ]
    if not texts:
        return None
    return "\n".join(texts)[:CONTEXT_MAX_CHARS]


def _hit_key(hit: Any) -> HitKey:
    return (
        str(getattr(hit, "paper_id", "")),
        str(getattr(hit, "chunker", "v1") or "v1"),
        int(getattr(hit, "chunk_index", 0)),
    )


def _label_key(entry: Any) -> HitKey:
    return (
        str(entry.get("paper_id", "")),
        str(entry.get("chunker", "v1") or "v1"),
        int(entry.get("chunk_index", 0)),
    )


def retrieval_metrics(items: Sequence[dict], strategy: Strategy, max_items: int) -> dict[str, dict]:
    """真实调用 hybrid_search；任何依赖异常向上冒泡，由 API 层转稳定错误体。"""
    selected = list(items[:max_items])
    cases: list[RetrievalCase] = []
    for item in selected:
        labels = {
            _label_key(entry)
            for entry in item.get("relevant_doc_ids", [])
            if isinstance(entry, dict)
        }
        hits = hybrid_search(
            str(item.get("question", "")),
            top_k=strategy.top_k,
            chunker=strategy.chunker,
        )
        cases.append(RetrievalCase(relevant_keys=labels, hit_keys=[_hit_key(hit) for hit in hits]))
    aggregate = aggregate_retrieval(cases, strategy.top_k)
    common_detail = {
        "k": strategy.top_k,
        "chunker": strategy.chunker,
        "reranker": "on" if strategy.reranker else "off",
        "strategy_id": strategy.id,
        "identity": "paper_id,chunker,chunk_index",
        "effective_max_items": len(selected),
        "matched_items": aggregate["matched_items"],
        "first_relevant_ranks": aggregate["first_relevant_ranks"],
        "effective_k": aggregate["effective_k"],
        "ndcg_valid_cases": aggregate["ndcg_valid_cases"],
        "ndcg_skipped_cases": aggregate["ndcg_skipped_cases"],
        "model_participates": False,
        "model_participates_reason": "检索走固定 embedding 的 hybrid_search，所选被测模型不参与本维度",
    }
    keys = ("recall@k", "precision@k", "mrr@k", "hit_rate@k", "ndcg@k")
    if aggregate["sample_count"] == 0:
        return {
            key: build_metric(
                key,
                status=UNAVAILABLE,
                detail={**common_detail, "reason": "评测集没有可检索的标注样本，无法计算检索指标"},
            )
            for key in keys
        }
    result = {
        "recall@k": build_metric(
            "recall@k", value=aggregate["recall"], sample_count=aggregate["sample_count"], detail=common_detail
        ),
        "precision@k": build_metric(
            "precision@k", value=aggregate["precision"], sample_count=aggregate["sample_count"], detail=common_detail
        ),
        "mrr@k": build_metric(
            "mrr@k", value=aggregate["mrr"], sample_count=aggregate["sample_count"], detail=common_detail
        ),
        "hit_rate@k": build_metric(
            "hit_rate@k",
            value=aggregate["hit_rate"],
            sample_count=aggregate["sample_count"],
            detail=common_detail,
        ),
    }
    if aggregate["ndcg"] is None:
        result["ndcg@k"] = _degraded(
            "ndcg@k",
            "理想 DCG 为 0（无可用相关性真值或返回条数为 0），不出分、不除零、不记 0",
            **common_detail,
        )
    else:
        result["ndcg@k"] = build_metric(
            "ndcg@k",
            value=aggregate["ndcg"],
            sample_count=aggregate["ndcg_valid_cases"],
            detail=common_detail,
        )
    return result


def reranker_state() -> dict[str, Any]:
    """复用 retrieve.reranker_health() 的真实就绪状态（测试可 patch 其底层符号）。"""
    return reranker_health()


def _registry_skills() -> list[SkillSummary]:
    """意图分类的可用技能名对齐 backend/app/skills/registry.py 的 Tool 注册表。"""
    return [
        SkillSummary(name=entry.name, description=entry.description, tools=[entry.name], enabled=entry.enabled)
        for entry in build_default_tool_registry()
    ]


def intent_metrics(items: Sequence[dict], max_items: int) -> dict[str, dict]:
    selected = list(items[:max_items])
    skills = _registry_skills()
    predictions: list[str | None] = []
    sources: list[str | None] = []
    for item in selected:
        decision = detect_skill(str(item.get("message", "")), skills)
        predictions.append(decision.skill if decision.status == "matched" else "none")
        sources.append(decision.source)
    expected = [str(item.get("expected_intent", "none")) for item in selected]
    value = intent_accuracy(predictions, expected)
    stats = _intent_confusion(predictions, expected)  # 复用同一批预测，不重复调用 detect_skill
    detail = {
        "detector": "backend.app.skills.intent.detect_skill",
        "registry": "backend.app.skills.registry.build_default_tool_registry",
        "prediction_sources": sources,
        "matched": sum(1 for predicted, label in zip(predictions, expected, strict=False) if predicted == label),
        "generation_model_used": False,
        "model_participates": False,
        "model_participates_reason": "意图识别走 detect_skill 的规则优先 + 模块固定 LLM 兜底，所选被测模型不参与本维度",
    }
    if value is None:
        return {
            key: build_metric(
                key,
                status=UNAVAILABLE,
                detail={**detail, "reason": "评测集没有可判定的意图标注样本"},
            )
            for key in ("intent_accuracy", "intent_macro_f1", "intent_confusion_count")
        }
    return {
        "intent_accuracy": build_metric(
            "intent_accuracy", value=value, sample_count=len(selected), detail=detail
        ),
        "intent_macro_f1": build_metric(
            "intent_macro_f1",
            value=stats["macro_f1"],
            sample_count=len(selected),
            detail={**detail, "per_class": stats["per_class"], "class_count": len(stats["per_class"])},
        ),
        "intent_confusion_count": build_metric(
            "intent_confusion_count",
            value=float(stats["confusion_count"]),
            sample_count=len(selected),
            detail={**detail, "predictions": predictions, "expected": expected},
        ),
    }


def _judge_score(task: str, question: str, answer: str, ctx: str | None, judge_model: str = JUDGE_MODEL) -> float | None:
    """复用 042 既有判官：只输出枚举标签，分数由 enum_to_score 映射。"""
    if task not in KNOWN_TASKS:  # 复用 runner.py 的唯一 task 注册表
        return None
    try:
        result = judge_majority(judge_model, task, question, answer, repeats=JUDGE_REPEATS, ctx=ctx)
    except Exception:
        return None
    return enum_to_score(task, result.majority)


def _generate_live_answer(
    model: str, question: str, timeout: float = GENERATION_TIMEOUT_SECONDS
) -> str:
    """复用既有 call_ollama（http_post_json + /api/chat）让被测模型实时生成回答。

    不新建第二套客户端/框架；失败或空回答一律抛异常，由 judge_metrics 转
    degraded，绝不回退评测集冻结 output，也不静默记 0。
    """
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Answer the user's question concisely.",
        },
        {"role": "user", "content": question},
    ]
    answer = call_ollama(model, messages, timeout=timeout)
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("empty_generation")
    return answer


def _batch_ranges(total: int) -> list[tuple[int, int]]:
    """按 BATCH_SIZE 切批；空集返回空（不发任何外部调用）。"""
    return [(start, min(start + BATCH_SIZE, total)) for start in range(0, total, BATCH_SIZE)]


def _bounded_question(question: object) -> str:
    """只保留尾部最新用户问题；截断是确定性的，且上限在 detail 中如实标注。"""
    text = str(question)
    return text[-MAX_QUESTION_CHARS:] if len(text) > MAX_QUESTION_CHARS else text


def _honest_judge_detail(total_items: int, judge_sample_count: int, batch_count: int) -> dict[str, Any]:
    """判官类 detail 的三个诚实标注字段：绝不写 100 冒充、绝不只跑 3 条显示大数。"""
    return {
        "judge_sample_count": int(judge_sample_count),
        "batch_count": int(batch_count),
        "total_items": int(total_items),
    }


def generate_live_answers(
    questions: Sequence[str], under_test_model: str, deadline: float
) -> tuple[list[str | None], list[str]]:
    """按批让所选被测模型实时生成回答（唯一传输层 call_ollama，显式 num_predict）。

    每批前用 _bounded_timeout 检查同一个 deadline；解析失败/空回答的批次如实计入
    generation_failures，绝不回退评测集冻结 output，也不静默记 0。
    """
    answers: list[str | None] = [None] * len(questions)
    failure_types: list[str] = []
    for start, end in _batch_ranges(len(questions)):
        batch = [_bounded_question(question) for question in questions[start:end]]
        timeout = _bounded_timeout(deadline, GENERATION_TIMEOUT_SECONDS)
        try:
            raw = call_ollama(
                under_test_model,
                rubrics.build_batch_generation_messages(batch),
                timeout=timeout,
                num_predict=BATCH_NUM_PREDICT,
            )
            parsed = rubrics.parse_batch_generation_response(raw, len(batch))
        except EvaluationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 失败批次不伪造；按失败样本条数如实计数
            failure_types.extend([type(exc).__name__] * len(batch))
            continue
        for offset, answer in enumerate(parsed):
            answers[start + offset] = answer
    return answers, failure_types


def judge_metrics(
    chat_items: Sequence[dict], max_items: int, under_test_model: str,
    deadline: float | None = None,
    live: tuple[list[str | None], list[str]] | None = None,
) -> dict[str, dict]:
    """chat_quality：批量实时生成 + 按批判官枚举，分数仍走 ENUM_MAPS[chat_quality]。

    judge_mode 如实标注批量单次枚举（不是多数投票）；失败批次只影响该批，
    sample_count / judge_sample_count 写实际取得可计分标签的条数，其余批照常出分。
    ``live`` 由 service 编排层注入同一次请求已实时生成的 (answers, failure_types)，
    与 answer_quality_metrics 共用一遍生成；直接调用（None）仍自行实时生成，不缓存。
    """
    deadline = _effective_deadline(deadline)
    selected = list(chat_items[:max_items])
    total_items = len(selected)
    batch_count = len(_batch_ranges(total_items))
    questions = [str(item.get("input", "")) for item in selected]
    answers, failure_types = (
        generate_live_answers(questions, under_test_model, deadline) if live is None else live
    )
    samples = [
        (item, answer)
        for item, answer in zip(selected, answers, strict=False)
        if isinstance(answer, str) and answer.strip()
    ]

    scores: list[float | None] = []
    judge_failure_types: list[str] = []
    for start, end in _batch_ranges(len(samples)):
        batch = samples[start:end]
        timeout = _bounded_timeout(deadline, rubrics.JUDGE_TIMEOUT_SECONDS)
        try:
            raw = call_ollama(
                JUDGE_MODEL,
                rubrics.build_batch_chat_quality_messages(
                    [{"question": _bounded_question(item.get("input", "")), "answer": answer}
                     for item, answer in batch]
                ),
                timeout=timeout,
                num_predict=BATCH_NUM_PREDICT,
            )
            labels = rubrics.parse_batch_chat_quality_response(raw, len(batch))
            scores.extend(enum_to_score("chat_quality", label) for label in labels)
        except EvaluationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 该批判官失败，其余批照常出分
            judge_failure_types.append(type(exc).__name__)
            scores.extend([None] * len(batch))

    judge_sample_count = sum(1 for score in scores if score is not None)
    chat_detail: dict[str, Any] = {
        "judge_model": JUDGE_MODEL,
        "under_test_model": under_test_model,
        "answer_source": "live_generation",
        "generation_model_used": True,
        "answer_source_note": f"评分对象由所选被测模型实时生成（按批 B={BATCH_SIZE}），判官固定 {JUDGE_MODEL} 打分",
        "score_mapping": "backend/eval_042/config.py::ENUM_MAPS[chat_quality]",
        "judge_mode": "batch-enumeration-single-pass",
        "judge_mode_note": "按批判官枚举 + ENUM_MAPS[chat_quality]/enum_to_score 映射，每样本单次判定，非多数投票",
        "generated_count": len(samples),
        "generation_failures": len(failure_types),
        "generation_failure_types": sorted(set(failure_types)),
        "judge_failures": len(judge_failure_types),
        "unavailable_calls": sum(1 for score in scores if score is None),
        "trace_count": total_items,
        "question_max_chars": MAX_QUESTION_CHARS,
        **_honest_judge_detail(total_items, judge_sample_count, batch_count),
    }
    gap_parts: list[str] = []
    if failure_types:
        gap_parts.append(
            f"被测模型实时生成失败 {len(failure_types)}/{total_items} 条"
            f"（{', '.join(sorted(set(failure_types)))}）"
        )
    if judge_failure_types:
        gap_parts.append(
            f"批量判官解析失败 {len(judge_failure_types)} 批"
            f"（{', '.join(sorted(set(judge_failure_types)))}）"
        )
    if judge_sample_count < total_items:
        gap_parts.append(
            f"仅 {judge_sample_count}/{total_items} 条取得可计分标签，sample_count 如实写 {judge_sample_count}"
        )
    if gap_parts:
        chat_detail["reason"] = "；".join(gap_parts) + "；不回退冻结 output、不静默记 0、不写 100 冒充"

    memory_metric = build_metric(
        "memory_correctness",
        status=NEEDS_GROUND_TRUTH,
        detail={
            "reason": (
                f"内置 chat 集 {total_items} 条全部为 chat_quality 且无 prior_context / "
                "memory_correctness 标注，缺少可判定的记忆真值"
            ),
            "judge_model": JUDGE_MODEL,
            "under_test_model": under_test_model,
        },
    )
    average = judge_average(scores)
    if average is None:
        chat_metric = build_metric(
            "chat_quality",
            status=DEGRADED,
            detail={
                **chat_detail,
                "reason": chat_detail.get("reason") or "批量判官本次全部不可用，未获得任何可计分标签",
            },
        )
    else:
        chat_metric = build_metric(
            "chat_quality", value=average, sample_count=judge_sample_count, detail=chat_detail
        )
    return {"chat_quality": chat_metric, "memory_correctness": memory_metric}


def retrieval_relevance_metrics(
    items: Sequence[dict],
    strategy: Strategy,
    max_items: int,
    *,
    deadline: float | None = None,
) -> dict[str, dict]:
    """整批 question + 真实 top-k Hit.text 按批交给固定判官做相关性判定。

    检索或某批判官失败一律只影响该批并如实写 judge_sample_count，不出 0.0000 假分。
    """
    key = "retrieval_relevance"
    deadline = _effective_deadline(deadline)
    selected = list(items[:max_items])
    total_items = len(selected)
    batch_count = len(_batch_ranges(total_items))
    detail: dict[str, Any] = {
        "judge_model": JUDGE_MODEL,
        "rubric": "batch-retrieval-relevance",
        "score_mapping": "good=1.0/mixed=0.5/poor=0.0",
        "context_source": "hybrid_search(Hit.text)",
        "strategy_id": strategy.id,
        "top_k": strategy.top_k,
        "chunker": strategy.chunker,
        "effective_max_items": total_items,
        "model_participates": False,
        "model_participates_reason": "检索片段相关性由固定判官判定，所选被测模型不参与本维度",
    }
    if not selected:
        return {key: _unavailable(key, "评测集没有可检索样本，不能判定检索片段相关性", **detail)}
    batch: list[dict[str, Any]] = []
    try:
        for item in selected:
            question = str(item.get("question", ""))
            hits = hybrid_search(question, top_k=strategy.top_k, chunker=strategy.chunker)
            passages = [
                str(getattr(hit, "text", ""))[:CONTEXT_PER_HIT_MAX_CHARS]
                for hit in hits
                if str(getattr(hit, "text", "")).strip()
            ]
            if not passages:
                return {key: _degraded(key, "真实检索未返回任何 Hit.text，不能判定相关性", **detail)}
            batch.append({"question": question, "passages": passages})
    except Exception as exc:  # noqa: BLE001 - 只记错误类型，原始异常文本不进 payload
        return {key: _degraded(key, f"检索依赖不可用（{type(exc).__name__}），检索相关性不出分", **detail)}

    per_item: dict[str, float] = {}
    failure_types: list[str] = []
    for start, end in _batch_ranges(len(batch)):
        chunk = batch[start:end]
        timeout = _bounded_timeout(deadline, rubrics.JUDGE_TIMEOUT_SECONDS)
        try:
            raw = call_ollama(
                JUDGE_MODEL,
                rubrics.build_retrieval_relevance_messages(chunk),
                timeout=timeout,
                num_predict=BATCH_NUM_PREDICT,
            )
            parsed = rubrics.parse_rubric_response(
                raw, keys=tuple(str(index) for index in range(len(chunk)))
            )
            for offset, value in enumerate(parsed.values()):
                per_item[str(start + offset)] = value
        except EvaluationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 该批解析失败，其余批照常出分
            failure_types.append(type(exc).__name__)

    values = list(per_item.values())
    judge_sample_count = len(values)
    detail.update(_honest_judge_detail(total_items, judge_sample_count, batch_count))
    gap = ""
    if failure_types or judge_sample_count < len(batch):
        gap = (
            f"批量判官解析失败 {len(failure_types)} 批"
            f"（{', '.join(sorted(set(failure_types))) or 'unknown'}）；"
            f"仅 {judge_sample_count}/{total_items} 条取得可计分标签，"
            "sample_count 如实写实际条数，不编造分数、不记 0"
        )
        detail["reason"] = gap
    if not values:
        return {
            key: build_metric(
                key, status=DEGRADED,
                detail={**detail, "reason": gap or "联合判官无法解析，检索相关性整批不出分"},
            )
        }
    return {
        key: build_metric(
            key,
            value=sum(values) / len(values),
            sample_count=judge_sample_count,
            detail={**detail, "per_item_scores": per_item},
        )
    }


def answer_quality_metrics(
    chat_items: Sequence[dict],
    max_items: int,
    under_test_model: str,
    deadline: float | None = None,
    live: tuple[list[str | None], list[str]] | None = None,
) -> dict[str, dict]:
    """回答质量 / 生成可用性 / 安全的 11 个维度（不含 chat_quality / memory_correctness）。

    - 批量实时生成（B=BATCH_SIZE）一次，answers 供 7 个判官维度、2 个字面规则与 2 个诊断量共用；
      ``live`` 由 service 编排层注入同一次请求的同一批 (answers, failure_types)，
      与 judge_metrics 共用一遍生成；直接调用（None）仍自行实时生成，不缓存；
    - 批量 7-rubric 判官；解析失败只影响该批，其余批真实出分，绝不逐维度编造分数；
    - 无 LLM 维度对全部成功生成的样本真实计算，sample_count 与实际条数一致；
    - groundedness 的 context 取真实 Hit.text，KB 不可用仅该维度 degraded；
    - 不回退冻结 output、不静默记 0、不写 100 冒充。
    """
    deadline = _effective_deadline(deadline)
    selected = list(chat_items[:max_items])
    total_items = len(selected)
    batch_count = len(_batch_ranges(total_items))
    questions = [str(item.get("input", "")) for item in selected]
    answers, failure_types = (
        generate_live_answers(questions, under_test_model, deadline) if live is None else live
    )

    samples: list[tuple[dict, str, str | None]] = []
    context_failures = 0
    for item, answer in zip(selected, answers, strict=False):
        if not isinstance(answer, str) or not answer.strip():
            continue
        context = _retrieved_context(_bounded_question(item.get("input", "")))
        if context is None:
            context_failures += 1
        samples.append((item, answer, context))

    judge_scores: list[dict[str, float] | None] = [None] * len(samples)
    judge_failure_types: list[str] = []
    for start, end in _batch_ranges(len(samples)):
        chunk = samples[start:end]
        timeout = _bounded_timeout(deadline, rubrics.JUDGE_TIMEOUT_SECONDS)
        try:
            raw = call_ollama(
                JUDGE_MODEL,
                rubrics.build_batch_rubric_messages([
                    {"question": _bounded_question(item.get("input", "")),
                     "answer": answer, "context": context}
                    for item, answer, context in chunk
                ]),
                timeout=timeout,
                num_predict=BATCH_NUM_PREDICT,
            )
            parsed = rubrics.parse_batch_rubric_response(raw, len(chunk))
            for offset, score in enumerate(parsed):
                judge_scores[start + offset] = score
        except EvaluationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 整批降级，不逐维度编造分数
            judge_failure_types.append(type(exc).__name__)

    usable_scores = [score for score in judge_scores if score is not None]
    judge_sample_count = len(usable_scores)
    common_detail: dict[str, Any] = {
        "judge_model": JUDGE_MODEL,
        "under_test_model": under_test_model,
        "answer_source": "live_generation",
        "rubric": "batch-joint-rubric-json",
        "judge_mode": "batch-rubric-enumeration",
        "score_mapping": "good=1.0/mixed=0.5/poor=0.0",
        "reference_fixture": "builtin-042-chat-traces",
        "trace_count": total_items,
        "generated_count": len(samples),
        "generation_failures": len(failure_types),
        "generation_failure_types": sorted(set(failure_types)),
        "judge_failures": len(judge_failure_types),
        "context_failures": context_failures,
        "question_max_chars": MAX_QUESTION_CHARS,
        **_honest_judge_detail(total_items, judge_sample_count, batch_count),
    }
    if not samples:
        gap = (
            f"被测模型实时生成失败 {len(failure_types)}/{total_items} 条，无评分对象；"
            "7 个判官维度整批 degraded，不回退冻结输出、不记 0"
        )
    elif judge_failure_types or judge_sample_count < len(samples):
        gap = (
            f"批量判官解析失败 {len(judge_failure_types)} 批 / 缺 {len(samples) - judge_sample_count} 条"
            f"（{', '.join(sorted(set(judge_failure_types))) or 'unknown'}）；"
            f"仅 {judge_sample_count}/{total_items} 条取得可计分标签，sample_count 如实写 {judge_sample_count}，"
            "不编造分数、不记 0"
        )
    else:
        gap = ""
    if gap:
        common_detail["reason"] = gap
    base_detail = {name: value for name, value in common_detail.items() if name != "reason"}

    result: dict[str, dict] = {}
    for key in rubrics.RUBRIC_KEYS:
        extra = {"context_source": "hybrid_search(Hit.text)"} if key == "groundedness" else {}
        if not usable_scores:
            result[key] = build_metric(
                key, status=DEGRADED,
                detail={**common_detail, **extra, "reason": gap or "批量判官全部不可用，整批不出分"},
            )
        elif key == "groundedness" and context_failures:
            result[key] = build_metric(
                key, status=DEGRADED,
                detail={
                    **base_detail, **extra,
                    "reason": (
                        f"真实检索上下文不可用 {context_failures}/{len(samples)} 条，"
                        "groundedness 不出分、不伪造"
                    ),
                },
            )
        else:
            values = [score[key] for score in usable_scores]
            result[key] = build_metric(
                key,
                value=sum(values) / len(values),
                sample_count=len(values),
                detail={**common_detail, **extra},
            )

    literal_detail = {
        **base_detail,
        "reference": _LITERAL_REFERENCE,
        "note": _LITERAL_NOTE,
        "reference_note": "042 冻结参考输出仅作字面比对基线，不是质量真值",
        "evaluated_count": len(samples),
    }
    if not samples:
        literal_reason = "无成功生成的实时回答，不能计算字面一致性，不记 0"
        result["answer_exact_match"] = _degraded("answer_exact_match", literal_reason, **literal_detail)
        result["levenshtein_similarity"] = _degraded("levenshtein_similarity", literal_reason, **literal_detail)
    else:
        references = [str(item.get("output", "")) for item, _, _ in samples]
        exact = sum(1 for (_, answer, _), reference in zip(samples, references, strict=False) if answer == reference)
        result["answer_exact_match"] = build_metric(
            "answer_exact_match", value=exact / len(samples), sample_count=len(samples), detail=literal_detail
        )
        similarity = sum(
            levenshtein_similarity(reference, answer)
            for (_, answer, _), reference in zip(samples, references, strict=False)
        )
        result["levenshtein_similarity"] = build_metric(
            "levenshtein_similarity", value=similarity / len(samples), sample_count=len(samples), detail=literal_detail
        )

    if not selected:
        no_samples = "评测集没有可评分样本，不能计算生成可用性"
        result["generation_success_rate"] = _unavailable("generation_success_rate", no_samples, **base_detail)
        result["answer_length_avg"] = _unavailable("answer_length_avg", no_samples, **base_detail)
    else:
        result["generation_success_rate"] = build_metric(
            "generation_success_rate", value=len(samples) / len(selected),
            sample_count=len(selected), detail=base_detail
        )
        if not samples:
            result["answer_length_avg"] = _degraded(
                "answer_length_avg", "无成功生成的实时回答，不能计算平均字符数，不记 0", **base_detail
            )
        else:
            result["answer_length_avg"] = build_metric(
                "answer_length_avg",
                value=sum(len(answer) for _, answer, _ in samples) / len(samples),
                sample_count=len(samples), detail=base_detail,
            )
    return result
