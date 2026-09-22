"""Langfuse trace -> EvalItem 数据集导出（只读 public API，全部 loopback）。

spec-042 边界：
- 空 output / 极短 Intake 文案类 trace -> status=skipped（不记 0 分）
- Langfuse 不可达 -> 明确抛错，不产出空数据集冒充成功
"""
from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import asdict, dataclass

from .config import INTAKE_MARKERS, LANGFUSE_BASE, LANGFUSE_PK, LANGFUSE_SK
from .offline_guard import assert_loopback


def _auth_header() -> dict:
    token = base64.b64encode(f"{LANGFUSE_PK}:{LANGFUSE_SK}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _get(url: str) -> dict:
    assert_loopback(url)
    req = urllib.request.Request(url, headers=_auth_header())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, body: dict) -> dict:
    """POST JSON 到本机 Langfuse public API（loopback 守卫）。返回解析后的 JSON。"""
    assert_loopback(url)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={**_auth_header(), "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def post_score(name: str, value: float, trace_id: str, comment: str,
               observation_id: str | None = None) -> dict:
    """写回一条 score 到指定 trace（自建判官 -> Langfuse 仅作 score 落点）。

    R4 范式：comment 承载「Explanation / Answer」理由；绝不给 SKIPPED/UNAVAILABLE 记 0 分。
    """
    body = {"name": name, "value": value, "traceId": trace_id, "comment": comment}
    if observation_id:
        body["observationId"] = observation_id
    return _post(f"{LANGFUSE_BASE}/api/public/scores", body)


def list_scores(trace_id: str, limit: int = 100) -> list[dict]:
    """按 trace 回查已挂的 score 列表（分页，用于验证写回）。

    注意：Langfuse public scores API 的 limit 上限为 100，超出返回 400；
    故分页直到 meta.totalPages，避免单次大 limit 报错。
    """
    out: list[dict] = []
    page = 1
    while True:
        d = _get(f"{LANGFUSE_BASE}/api/public/scores?traceId={trace_id}"
                 f"&limit={limit}&page={page}")
        out.extend(d.get("data", []))
        meta = d.get("meta", {}) or {}
        total = meta.get("totalPages") or 1
        if page >= total:
            break
        page += 1
    return out


# ---------- 纯函数：分类（便于单测，无网络） ----------
def classify_output(output_text, intake_markers=INTAKE_MARKERS, min_answer_chars=1):
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
                    task: str = "chat_quality", synthetic: bool = False) -> EvalItem:
    status, reason = classify_output(output_text)
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
    )


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


def collect_eval_items(n_scoreable: int = 20, n_intake_fixtures: int = 2,
                       n_blank_samples: int = 2,
                       task: str = "chat_quality") -> list[EvalItem]:
    """导出数据集：真实 ollama-chat trace + 合成 Intake fixture。

    - 优先纳入长回答（output 长）当作 scored 样本；
    - 补齐短回答直到达到 n_scoreable；
    - 同时纳入最多 n_blank_samples 条**真实**空 output trace（skipped/empty_output），
      实证「失败/空 trace 不记 0 分」；
    - 注入 n_intake_fixtures 条合成 Intake 文案（明确标记 synthetic），验证 skipped(intake_text)。
    """
    ids = list_ollama_chat_trace_ids(limit=200)
    items: list[EvalItem] = []
    scored = 0
    blanks = 0
    # 先按 output 长度排序，长回答优先（更有评分价值）
    ranked = []
    for tid in ids:
        tr = fetch_trace(tid)
        inp, out = extract_io(tr)
        ranked.append((tid, inp, out, len(out)))
    ranked.sort(key=lambda x: x[3], reverse=True)

    for tid, inp, out, _ in ranked:
        it = build_eval_item(tid, inp, out, task=task)
        if it.status == "scored":
            if scored >= n_scoreable:
                continue
            items.append(it)
            scored += 1
        elif it.skip_reason == "empty_output":
            if blanks >= n_blank_samples:
                continue
            items.append(it)
            blanks += 1

    # 合成 Intake 文案 fixture（不冒充真实数据，明确标记）
    for i in range(n_intake_fixtures):
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
    ap.add_argument("--n-intake-fixtures", type=int, default=2)
    ap.add_argument("--n-blank-samples", type=int, default=2)
    ap.add_argument("--task", default="chat_quality")
    args = ap.parse_args()
    items = collect_eval_items(
        n_scoreable=args.n_scoreable,
        n_intake_fixtures=args.n_intake_fixtures,
        n_blank_samples=args.n_blank_samples,
        task=args.task,
    )
    save_dataset(items, args.out)
    from collections import Counter

    c = Counter((it.status, it.skip_reason) for it in items)
    print(f"saved {len(items)} items -> {args.out}")
    for k, v in c.items():
        print("  ", k, v)


if __name__ == "__main__":
    main()
