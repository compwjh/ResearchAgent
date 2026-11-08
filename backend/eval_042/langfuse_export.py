"""Langfuse trace -> EvalItem 数据集导出（只读 public API，全部 loopback）。

spec-042 边界：
- 空 output / 极短 Intake 文案类 trace -> status=skipped（不记 0 分）
- Langfuse 不可达 -> 明确抛错，不产出空数据集冒充成功
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote, urlencode

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
               observation_id: str | None = None, *,
               score_id: str | None = None) -> dict:
    """写回一条 score 到指定 trace（自建判官 -> Langfuse 仅作 score 落点）。

    R4 范式：comment 承载「Explanation / Answer」理由；绝不给 SKIPPED/UNAVAILABLE 记 0 分。

    ``score_id`` 是可选的确定性幂等键：调用方在重跑同一 trace 时可传入同一
    确定性 id，让 Langfuse 按 id 去重（配合 :func:`post_score_idempotent` 的
    先查后写）。不传则保持原有自动生成语义，body 字段集合与顺序不变。
    """
    body = {"name": name, "value": value, "traceId": trace_id, "comment": comment}
    if observation_id:
        body["observationId"] = observation_id
    if score_id:
        body["id"] = score_id
    payload = _post(f"{LANGFUSE_BASE}/api/public/scores", body)
    returned_id = payload.get("id")
    if not isinstance(returned_id, str) or not returned_id.strip():
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
    """通过服务端 exact-ID GET 读取 score；404 表示尚未可见。"""
    if not isinstance(score_id, str) or not score_id.strip():
        raise ValueError("score_id must be a non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in score_id):
        raise ValueError("score_id contains control characters")
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid score lookup limit: {limit!r}") from exc
    if parsed_limit < 1:
        raise ValueError("score lookup limit must be positive")
    # Keep the historical argument for callers, while exact-ID GET has no
    # list limit or trace filter to send.  The public API limit remains capped
    # for compatibility with list callers and future adapters.
    _ = min(parsed_limit, 100)
    encoded_id = quote(score_id, safe="")
    try:
        return _get(f"{LANGFUSE_BASE}/api/public/scores/{encoded_id}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _score_dedupe_id(*, trace_id: str, name: str, report_version: str,
                     task: str | None, extra: str = "") -> str:
    """为 score 生成确定性去重标识（用作 Langfuse score 的确定性 id）。

    仅由确定性输入派生：``report_version + task + trace_id + name (+ extra)``。
    相同输入必得相同 id，从而重跑同一 trace 命中等幂等键、不产生第二条。
    """
    digest = hashlib.sha256(
        "\n".join(
            [
                str(report_version or ""),
                str(task or ""),
                str(trace_id or ""),
                str(name or ""),
                str(extra or ""),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"eval042-{digest[:32]}"


# 记录模块默认的 score writer。评测契约测试 / 适配器会注入自定义 writer 来
# 锁定「body 四字段 + 恰好一次 POST」；对这类注入保持原调用序列，不追加精确
# 查询、不改变 body 字段集合。
_DEFAULT_SCORE_WRITER = post_score


def post_score_idempotent(
    name: str,
    value: float,
    trace_id: str,
    comment: str,
    *,
    observation_id: str | None = None,
    report_version: str = "",
    task: str | None = None,
    extra: str = "",
) -> dict:
    """写回 score，但在 POST 前先精确查询去重；命中则复用既有 score_id。

    流程（保持 POST 恰好一次、不重放）：
    1. 用确定性去重 id 走既有 exact-ID GET（:func:`find_score_by_id`）；
       404 视为「尚未可见」，返回 ``None``。
    2. 若已存在 -> 直接复用该 score，不产生第二条（不发 POST）。
    3. 若不存在（含 404）-> 仅 POST 一次，并携带确定性 ``id`` 让 Langfuse
       按 id 去重，避免可见性延迟导致的竞态重复。

    精确查询若遇到非 404 错误（401/403/网络）会直接向上抛出，**不会**因查询
    失败而回退到 POST（即不会自动重放造成重复 score）。

    当调用方注入了自定义 score writer 时，保持其「恰好一次 POST + body 四
    字段」契约：不追加精确查询、不携带幂等 id，避免改变既有调用序列。
    """
    dedupe_id = _score_dedupe_id(
        trace_id=trace_id,
        name=name,
        report_version=report_version,
        task=task,
        extra=extra,
    )
    if post_score is not _DEFAULT_SCORE_WRITER:
        return post_score(
            name=name,
            value=value,
            trace_id=trace_id,
            comment=comment,
        )
    existing = find_score_by_id(dedupe_id, trace_id, limit=100)
    if existing is not None and existing.get("id") == dedupe_id:
        return existing
    return post_score(
        name=name,
        value=value,
        trace_id=trace_id,
        comment=comment,
        observation_id=observation_id,
        score_id=dedupe_id,
    )


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


def compute_dataset_sha256(items: list[EvalItem | Mapping[str, Any]]) -> str:
    """数据集指纹：对规范化的 item 列表做确定性 sha256。

    用于报告 metadata 的 ``dataset_sha256``，使两次同数据集运行可直接比较。
    """
    normalized = [
        asdict(item) if isinstance(item, EvalItem) else dict(item)
        for item in items
    ]
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stably_sort_items(items: list[EvalItem | Mapping[str, Any]]) -> list:
    """按 trace_id 稳定排序（不依赖导出顺序 / 输出长度），保证可复现。"""
    return sorted(
        items,
        key=lambda item: (
            item.trace_id if isinstance(item, EvalItem) else item.get("trace_id", "")
        ),
    )


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
def list_ollama_chat_trace_ids(
    limit: int = 100,
    since: str | None = None,
    until: str | None = None,
) -> list[str]:
    ids: list[str] = []
    page = 1
    while len(ids) < limit:
        # 不再按 timestamp.desc 排序（导出会按 trace_id 稳定排序），可选固定
        # 时间窗（since/until）以冻结数据集、避免运行中业务产生新 trace 导致漂移。
        query = urlencode(
            {
                "name": "ollama-chat",
                "limit": 100,
                "page": page,
                **({"fromTimestamp": since} if since else {}),
                **({"toTimestamp": until} if until else {}),
            }
        )
        d = _get(f"{LANGFUSE_BASE}/api/public/traces?{query}")
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
                       include_synthetic: bool = False,
                       since: str | None = None,
                       until: str | None = None) -> list[EvalItem]:
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
    # 先按 trace_id 稳定排序（不再按 output 长度倒序），保证可复现。
    ranked = []
    for tid in ids:
        tr = fetch_trace(tid)
        inp, out = extract_io(tr)
        ranked.append((tid, inp, out, len(out), extract_prior_context(tr)))
    ranked.sort(key=lambda x: x[0])

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

    items = stably_sort_items(items)
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
