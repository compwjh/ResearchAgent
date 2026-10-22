"""Langfuse trace -> EvalItem 数据集导出（只读 public API，全部 loopback）。

spec-042 边界：
- 空 output / 极短 Intake 文案类 trace -> status=skipped（不记 0 分）
- Langfuse 不可达 -> 明确抛错，不产出空数据集冒充成功
"""
from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode

from .config import INTAKE_MARKERS, LANGFUSE_BASE, LANGFUSE_PK, LANGFUSE_SK
from .offline_guard import http_get_json, http_post_json


class EmptyTraceExportError(RuntimeError):
    """Langfuse 成功返回但没有任何真实 trace。"""

    def __init__(
        self,
        message: str,
        *,
        real_trace_count: int = 0,
        real_item_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.real_trace_count = real_trace_count
        self.real_item_count = real_item_count


class ScoreResponseError(ValueError):
    """Langfuse score 写回响应缺少可用于精确回查的 id。"""


def _auth_header() -> dict:
    token = base64.b64encode(f"{LANGFUSE_PK}:{LANGFUSE_SK}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _get(url: str) -> dict:
    payload = http_get_json(url, headers=_auth_header(), timeout=30)
    if not isinstance(payload, dict):
        raise ValueError(f"Langfuse GET returned non-object JSON: {type(payload).__name__}")
    return payload


def _post(url: str, body: dict) -> dict:
    """POST JSON 到本机 Langfuse public API（loopback 守卫）。返回解析后的 JSON。"""
    payload = http_post_json(
        url,
        body,
        headers=_auth_header(),
        timeout=30,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Langfuse POST returned non-object JSON: {type(payload).__name__}")
    return payload


def post_score(name: str, value: float, trace_id: str, comment: str,
               observation_id: str | None = None) -> dict:
    """写回一条 score 到指定 trace（自建判官 -> Langfuse 仅作 score 落点）。

    R4 范式：comment 承载「Explanation / Answer」理由；绝不给 SKIPPED/UNAVAILABLE 记 0 分。
    """
    body = {"name": name, "value": value, "traceId": trace_id, "comment": comment}
    if observation_id:
        body["observationId"] = observation_id
    payload = _post(f"{LANGFUSE_BASE}/api/public/scores", body)
    score_id = payload.get("id")
    if not isinstance(score_id, str) or not score_id.strip():
        raise ScoreResponseError("Langfuse score response missing non-empty id")
    return payload


def list_scores(trace_id: str, limit: int = 100) -> list[dict]:
    """按 trace 回查已挂的 score 列表（分页，用于验证写回）。

    注意：Langfuse public scores API 的 limit 上限为 100，超出返回 400；
    故分页直到 meta.totalPages，避免单次大 limit 报错。
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid score list limit: {limit!r}") from exc
    if limit < 1:
        raise ValueError("score list limit must be positive")
    # Langfuse public API rejects values above 100.  Clamp for compatibility
    # with old callers rather than allowing a bad request to reach the service.
    limit = min(limit, 100)
    out: list[dict] = []
    page = 1
    while True:
        query = urlencode({"traceId": trace_id, "limit": limit, "page": page})
        d = _get(f"{LANGFUSE_BASE}/api/public/scores?{query}")
        data = d.get("data")
        if not isinstance(data, list):
            raise ValueError("Langfuse scores response missing list data")
        out.extend(item for item in data if isinstance(item, dict))
        meta = d.get("meta", {}) or {}
        total = meta.get("totalPages") or 1
        if page >= total:
            break
        page += 1
    return out


def find_score_by_id(score_id: str, trace_id: str, limit: int = 100) -> dict | None:
    """在指定 trace 的 score 列表中按精确 ``id`` 查找一条 score。"""
    if not isinstance(score_id, str) or not score_id.strip():
        raise ValueError("score_id must be a non-empty string")
    for score in list_scores(trace_id, limit=limit):
        if score.get("id") == score_id:
            return score
    return None


# ---------- 纯函数：分类（便于单测，无网络） ----------
def _normalize_prior_context(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def extract_prior_context(trace: Mapping[str, Any]) -> str | None:
    """只从 trace 或其显式 ``metadata.prior_context`` 字段读取上下文。

    不从 input/output、observation 文本或其它相似字段推测记忆上下文。
    """
    if not isinstance(trace, Mapping):
        return None
    direct = _normalize_prior_context(trace.get("prior_context"))
    if direct is not None:
        return direct
    metadata = trace.get("metadata")
    if isinstance(metadata, Mapping):
        return _normalize_prior_context(metadata.get("prior_context"))
    return None


def classify_output(
    output_text,
    intake_markers=INTAKE_MARKERS,
    min_answer_chars=1,
    *,
    task: str = "chat_quality",
    prior_context: str | None = None,
):
    """返回 (status, reason)。

    - 空/空白 -> ('skipped','empty_output')
    - 命中 Intake 文案标记 -> ('skipped','intake_text')
    - 其它 -> ('scored', None)
    真实短回答（如 'Hi there'）仍判 scored，由判官打 poor。
    """
    if output_text is None:
        return "skipped", "empty_output"
    text = output_text if isinstance(output_text, str) else str(output_text)
    if text.strip() == "":
        return "skipped", "empty_output"
    low = text.lower()
    for mk in intake_markers:
        if mk.lower() in low:
            return "skipped", "intake_text"
    if task == "memory_correctness" and _normalize_prior_context(prior_context) is None:
        return "skipped", "no_prior_context"
    return "scored", None


@dataclass
class EvalItem:
    trace_id: str
    task: str
    input: str
    output: str
    reference: object
    trajectory: object
    status: str
    skip_reason: object = None
    synthetic: bool = False
    prior_context: str | None = None


def extract_io(trace: dict):
    """从 trace 抽取 (input, output)。优先 trace 级，缺失时回退最长 observation。"""
    out = (trace.get("output") or "") if isinstance(trace.get("output"), str) else ""
    inp = (trace.get("input") or "") if isinstance(trace.get("input"), str) else ""
    obs = trace.get("observations") or []
    if not out:
        cand = ""
        for o in obs:
            oot = o.get("output") or ""
            if isinstance(oot, str) and len(oot) > len(cand):
                cand = oot
        out = cand
    if not inp:
        cand = ""
        for o in obs:
            oin = o.get("input") or ""
            if isinstance(oin, str) and len(oin) > len(cand):
                cand = oin
        inp = cand
    return inp, out


def build_eval_item(trace_id: str, input_text: str, output_text: str,
                    task: str = "chat_quality", synthetic: bool = False,
                    prior_context: str | None = None) -> EvalItem:
    status, reason = classify_output(
        output_text,
        task=task,
        prior_context=prior_context,
    )
    return EvalItem(
        trace_id=trace_id,
        task=task,
        input=input_text,
        output=output_text,
        reference=None,
        trajectory=None,
        status=status,
        skip_reason=reason,
        synthetic=synthetic,
        prior_context=_normalize_prior_context(prior_context),
    )


def count_item_sources(
    items: list[EvalItem | Mapping[str, Any]],
) -> dict[str, int]:
    """返回真实与 synthetic item 数量，供报告层区分两类来源。"""
    synthetic_count = sum(
        bool(item.synthetic if isinstance(item, EvalItem) else item.get("synthetic", False))
        for item in items
    )
    return {
        "real_trace_count": len(items) - synthetic_count,
        "synthetic_count": synthetic_count,
    }


# ---------- 网络：拉取 ----------
def list_ollama_chat_trace_ids(limit: int = 100) -> list[str]:
    ids: list[str] = []
    page = 1
    while len(ids) < limit:
        d = _get(f"{LANGFUSE_BASE}/api/public/traces?name=ollama-chat"
                 f"&limit=100&page={page}&orderBy=timestamp.desc")
        batch = [t["id"] for t in d["data"]]
        if not batch:
            break
        ids.extend(batch)
        if page >= d["meta"]["totalPages"]:
            break
        page += 1
    return ids[:limit]


def fetch_trace(trace_id: str) -> dict:
    return _get(f"{LANGFUSE_BASE}/api/public/traces/{trace_id}")


def collect_eval_items(n_scoreable: int = 20, n_intake_fixtures: int = 0,
                       n_blank_samples: int = 2,
                       task: str = "chat_quality",
                       include_synthetic: bool = False) -> list[EvalItem]:
    """导出数据集：真实 ollama-chat trace，可显式附加 Intake fixture。

    - 优先纳入长回答（output 长）当作 scored 样本；
    - 补齐短回答直到达到 n_scoreable；
    - 同时纳入最多 n_blank_samples 条**真实**空 output trace（skipped/empty_output），
      实证「失败/空 trace 不记 0 分」；
    - 只有 ``include_synthetic=True`` 时才注入 n_intake_fixtures 条合成 Intake
      文案；真实 trace 为空时始终失败，不能用 fixture 冒充成功。
    """
    if n_intake_fixtures and not include_synthetic:
        raise ValueError(
            "synthetic fixtures require include_synthetic=True; "
            "they are only for explicit classification tests"
        )
    ids = list_ollama_chat_trace_ids(limit=200)
    if not ids:
        raise EmptyTraceExportError(
            "Langfuse returned zero real ollama-chat traces; refusing synthetic-only export",
            real_trace_count=0,
            real_item_count=0,
        )
    items: list[EvalItem] = []
    real_trace_count = len(ids)
    real_item_count = 0
    scored = 0
    blanks = 0
    # 先按 output 长度排序，长回答优先（更有评分价值）
    ranked = []
    for tid in ids:
        tr = fetch_trace(tid)
        inp, out = extract_io(tr)
        ranked.append((tid, inp, out, len(out), extract_prior_context(tr)))
    ranked.sort(key=lambda x: x[3], reverse=True)

    for tid, inp, out, _, prior_context in ranked:
        it = build_eval_item(
            tid,
            inp,
            out,
            task=task,
            prior_context=prior_context,
        )
        if it.status == "scored":
            if scored >= n_scoreable:
                continue
            items.append(it)
            real_item_count += 1
            scored += 1
        elif it.skip_reason == "no_prior_context":
            # Missing memory context is a first-class skipped item.  Keep it
            # visible to the runner instead of silently dropping the trace.
            items.append(it)
            real_item_count += 1
        elif it.skip_reason == "empty_output":
            if blanks >= n_blank_samples:
                continue
            items.append(it)
            real_item_count += 1
            blanks += 1

    if real_item_count == 0:
        raise EmptyTraceExportError(
            "real traces were found but no real evaluation items were selected; "
            "refusing synthetic-only export",
            real_trace_count=real_trace_count,
            real_item_count=real_item_count,
        )

    # 合成 Intake 文案 fixture（不冒充真实数据，明确标记）
    for i in range(n_intake_fixtures if include_synthetic else 0):
        fixture = (
            "研究 Intake 已保存：已为你创建研究任务「本地 Agent 评测综述」，"
            "后续将进入多轮调研流程，本消息由技能路由生成，未调用模型生成答案。"
        )
        items.append(build_eval_item(
            f"synthetic-intake-{i+1}", "帮我研究一下本地 Agent 评测方案", fixture,
            task=task, synthetic=True))

    return items


def save_dataset(items: list[EvalItem], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(it) for it in items], f, ensure_ascii=False, indent=2)


def main():
    import argparse

    ap = argparse.ArgumentParser(description="导出 Langfuse ollama-chat -> EvalItem 数据集")
    ap.add_argument("--out", default="docs/sdd/plans/042/task-02-eval-dataset.json")
    ap.add_argument("--n-scoreable", type=int, default=20)
    ap.add_argument("--n-intake-fixtures", type=int, default=0)
    ap.add_argument("--n-blank-samples", type=int, default=2)
    ap.add_argument("--task", default="chat_quality")
    ap.add_argument(
        "--include-synthetic",
        action="store_true",
        help="仅在明确的分类测试中追加 synthetic Intake fixture",
    )
    args = ap.parse_args()
    items = collect_eval_items(
        n_scoreable=args.n_scoreable,
        n_intake_fixtures=args.n_intake_fixtures,
        n_blank_samples=args.n_blank_samples,
        task=args.task,
        include_synthetic=args.include_synthetic,
    )
    save_dataset(items, args.out)
    from collections import Counter

    c = Counter((it.status, it.skip_reason) for it in items)
    print(f"saved {len(items)} items -> {args.out}")
    for k, v in c.items():
        print("  ", k, v)


if __name__ == "__main__":
    main()
