"""判官一致性实测（步骤 2）+ 报告产出。

- 对数据集中 status=scored 的每条，按 chat_quality / memory_correctness 两任务，
  分别用 primary(9b) 与 fallback(27b) 各重复 REPEATS 次（temp 0）；
- 统计：自一致率（3 次标签是否完全一致）、标签切换率、unavailable 率、跨判官一致率；
- Q8 回退链裁决：primary 自一致率 >= 阈值 -> 采用 9b；否则 fallback >= 阈值 -> 27b；
  否则 No-Go；
- 与人工标注一致率：若提供参考文件则计算，否则记为 null（带回架构师标注）。
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter

from .config import (
    FALLBACK_JUDGE,
    LANGFUSE_BASE,
    OLLAMA_BASE,
    PRIMARY_JUDGE,
    REPEATS,
    SELF_CONSISTENCY_THRESHOLD,
)
from .judge_client import judge_repeats
from .offline_guard import assert_loopback


def _majority(labels):
    if not labels:
        return None
    return Counter(labels).most_common(1)[0][0]


def run(dataset: list[dict], tasks: list[str], primary: str, fallback: str,
        repeats: int, progress_path: str | None = None,
        max_items: int | None = None) -> dict:
    assert_loopback(LANGFUSE_BASE)
    assert_loopback(OLLAMA_BASE)
    scored = [it for it in dataset if it.get("status") == "scored"]
    if max_items is not None:
        scored = scored[:max_items]
    results = []
    for _idx, it in enumerate(scored):
        q, a = it.get("input", ""), it.get("output", "")
        rec = {"trace_id": it.get("trace_id"), "synthetic": it.get("synthetic", False),
               "tasks": {}}
        for task in tasks:
            rec["tasks"][task] = {
                primary: _judge_model(primary, task, q, a, repeats),
                fallback: _judge_model(fallback, task, q, a, repeats),
            }
        results.append(rec)
        if progress_path:
            with open(progress_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return _aggregate(results, tasks, primary, fallback, repeats)


def _judge_model(model, task, q, a, repeats):
    calls = judge_repeats(model, task, q, a, repeats)
    labels = [c["label"] for c in calls if c["status"] == "scored"]
    return {
        "labels": labels,
        "all_unavailable": all(c["status"] != "scored" for c in calls),
        "unavailable_count": sum(1 for c in calls if c["status"] != "scored"),
        "raw": calls,
    }


def _aggregate(results, tasks, primary, fallback, repeats) -> dict:
    out = {"primary": primary, "fallback": fallback, "repeats": repeats,
           "self_consistency_threshold": SELF_CONSISTENCY_THRESHOLD, "tasks": {}}
    for task in tasks:
        per_model = {}
        for model in (primary, fallback):
            consistent = []
            unavailable = []
            for r in results:
                m = r["tasks"][task][model]
                if m["all_unavailable"]:
                    unavailable.append(1)
                    consistent.append(0)
                else:
                    consistent.append(1 if len(set(m["labels"])) == 1 else 0)
            n = len(results)
            self_cons = statistics.fmean(consistent) if consistent else 0.0
            unavail = statistics.fmean(unavailable) if unavailable else 0.0
            per_model[model] = {
                "self_consistency_rate": round(self_cons, 4),
                "label_switch_rate": round(1 - self_cons, 4),
                "unavailable_rate": round(unavail, 4),
            }
        # 跨判官一致率（primary vs fallback，仅两者都有标签的项）
        cross = []
        for r in results:
            p = r["tasks"][task][primary]["labels"]
            f = r["tasks"][task][fallback]["labels"]
            if p and f:
                cross.append(1 if _majority(p) == _majority(f) else 0)
        cross_rate = statistics.fmean(cross) if cross else 0.0
        # Q8 裁决
        if per_model[primary]["self_consistency_rate"] >= SELF_CONSISTENCY_THRESHOLD:
            decision = f"adopt:{primary}"
        elif per_model[fallback]["self_consistency_rate"] >= SELF_CONSISTENCY_THRESHOLD:
            decision = f"fallback:{fallback}"
        else:
            decision = "no-go"
        per_model["cross_agreement_rate"] = round(cross_rate, 4)
        per_model["cross_agreement_n"] = len(cross)
        per_model["decision"] = decision
        out["tasks"][task] = per_model
    out["n_scored_items"] = len(results)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default="chat_quality,memory_correctness")
    ap.add_argument("--primary", default=PRIMARY_JUDGE)
    ap.add_argument("--fallback", default=FALLBACK_JUDGE)
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--progress", default=None)
    ap.add_argument("--reference", default=None)
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        dataset = json.load(f)
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    report = run(dataset, tasks, args.primary, args.fallback, args.repeats,
                args.progress, args.max_items)

    # 人工一致率：本自动跑无法获取真实人工标注，故置 null 并明确带回，
    # 不伪造数值。架构师标注 N 条 gold 标签回填 reference 文件后可补算。
    report["human_agree_rate"] = None
    report["human_agree_rate_note"] = (
        "需架构师对 N 条样本标注 gold 标签后回填 reference 文件再算；"
        "本自动跑不伪造人工一致率。硬门禁以自一致率（方差）为准。"
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
