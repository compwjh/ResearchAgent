#!/usr/bin/env python3
"""spec-042 Task 02 第三步（核心闭环）：自建判官 -> 写回 Langfuse score。

复用 backend/eval_042：
- config : 判官模型(primary=qwen3.5:9b / fallback=qwen3.8:27b)、REPEATS、ENUM_MAPS、INTAKE_MARKERS
- judge_client.judge_repeats : 温度0重复评分，R4 范式解析，异常 -> status=unavailable
- langfuse_export.post_score/list_scores : 写回/回查 score（均经 offline_guard 守卫 loopback）
- offline_guard : 任何非 loopback 主机立即拒绝，结构性保证离线

行为约束（spec-042 R4/R5、边界）：
- 仅对 status=='scored' 的真 trace（非 synthetic）打分并写回 score；
- status=='skipped'（空 output / 技能路由 Intake 文案）-> 不写任何 score（禁止记 0）；
- 判官全 unavailable -> 标记 UNAVAILABLE，不写 score；
- score 必带 name / value / comment(Explanation+Answer 理由) / traceId。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

# 让脚本可从 docs/sdd/plans/042/ 直接运行，复用 backend/eval_042
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "../../../../backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from eval_042 import config, judge_client, langfuse_export  # noqa: E402


def majority_label(labels: list[str | None]) -> tuple[str | None, str | None]:
    """返回 (majority_label, explanation_of_a_matching_call)。全空 -> (None,None)。"""
    scored = [c for c in labels]
    if not scored:
        return None, None
    cnt = Counter(scored)
    label = cnt.most_common(1)[0][0]
    return label, None


def score_and_write(item: dict) -> dict:
    """对单条 scored 项打分并写回 Langfuse。返回结果记录。"""
    task = item["task"]
    tid = item["trace_id"]
    q, a = item.get("input", ""), item.get("output", "")
    calls = judge_client.judge_repeats(config.PRIMARY_JUDGE, task, q, a, config.REPEATS)
    labels = [c["label"] for c in calls if c["status"] == "scored"]
    explanations = [c["explanation"] for c in calls if c["status"] == "scored"]
    if not labels:
        return {
            "trace_id": tid, "status": "unavailable", "label": None, "score": None,
            "reason": "judge_all_unavailable",
            "errors": [c.get("error") for c in calls],
        }
    label = Counter(labels).most_common(1)[0][0]
    # 取与多数标签一致的一条的 explanation 作为 comment
    expl = next((e for e, l in zip(explanations, labels) if l == label), "")
    score = judge_client.enum_to_score(task, label)
    comment = f"Explanation: {expl} Answer: {label}"
    posted = langfuse_export.post_score(name=task, value=score, trace_id=tid, comment=comment)
    return {
        "trace_id": tid, "status": "scored", "label": label, "score": score,
        "name": task, "comment": comment, "score_id": posted.get("id"),
        "raw_labels": labels,
    }


def _verify_written(records: list[dict], attempts: int = 5, sleep_s: float = 1.5) -> int:
    """写完后独立回查验证：每条 scored 记录的 trace 上确有本 name 的 score。

    Langfuse score 写回为最终一致，故多次重试，避免写完即查的竞态导致误判。
    """
    import time

    verified = 0
    for rec in records:
        if rec.get("status") != "scored":
            continue
        tid, name = rec["trace_id"], rec["name"]
        ok = False
        for _ in range(attempts):
            try:
                scores = langfuse_export.list_scores(tid, limit=200)
            except Exception:
                scores = []
            if any(s.get("name") == name and s.get("traceId") == tid for s in scores):
                ok = True
                break
            time.sleep(sleep_s)
        rec["verified"] = ok
        if ok:
            verified += 1
    return verified


def run(dataset_path: str, summary_path: str, max_items: int | None = None,
        dry_run: bool = False) -> dict:
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)
    results: list[dict] = []
    written = 0
    skipped = 0
    unavailable = 0
    for it in items:
        if max_items is not None and (written + skipped + unavailable) >= max_items:
            break
        if it.get("status") != "scored":
            # 空 output / Intake 文案：明确 SKIPPED，不写 0 分
            results.append({"trace_id": it.get("trace_id"), "status": "skipped",
                            "reason": it.get("skip_reason")})
            skipped += 1
            continue
        if it.get("synthetic"):
            # 合成 Intake fixture 不应写回真实 Langfuse
            results.append({"trace_id": it.get("trace_id"), "status": "skipped_synthetic",
                            "reason": "synthetic_intake"})
            skipped += 1
            continue
        if dry_run:
            results.append({"trace_id": it.get("trace_id"), "status": "dry_run_scored",
                            "label": None, "score": None})
            written += 1
            continue
        rec = score_and_write(it)
        results.append(rec)
        if rec["status"] == "scored":
            written += 1
        elif rec["status"] == "unavailable":
            unavailable += 1

    # 写完后独立回查验证（重试克服最终一致竞态）
    verified = _verify_written(results) if not dry_run else 0

    summary = {
        "dataset": dataset_path,
        "primary_judge": config.PRIMARY_JUDGE,
        "repeats": config.REPEATS,
        "n_items": len(items),
        "written": written,
        "skipped": skipped,
        "unavailable": unavailable,
        "verified_on_trace": verified,
        "dry_run": dry_run,
        "results": results,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description="自建判官打分并写回 Langfuse score")
    ap.add_argument("--dataset", default="docs/sdd/plans/042/task-02-eval-dataset.json")
    ap.add_argument("--out", default="docs/sdd/plans/042/task-02-eval-run-summary.json")
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="不写回，仅统计分类")
    args = ap.parse_args()
    if not os.path.isabs(args.dataset):
        args.dataset = os.path.join(os.getcwd(), args.dataset)
    if not os.path.isabs(args.out):
        args.out = os.path.join(os.getcwd(), args.out)
    s = run(args.dataset, args.out, args.max_items, args.dry_run)
    print(f"[run-eval] written={s['written']} skipped={s['skipped']} "
          f"unavailable={s['unavailable']} verified_on_trace={s['verified_on_trace']} "
          f"dry_run={s['dry_run']}")
    print(f"[run-eval] summary -> {args.out}")


if __name__ == "__main__":
    main()
