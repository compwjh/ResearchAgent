#!/usr/bin/env python3
"""spec-042 Task 04 薄封装入口：把评测闭环逻辑收敛到 backend/eval_042/eval_run.py。

本文件**不再**保留第二套评分/写回逻辑，仅做：加载数据集 -> 调用 eval_run.run -> 落盘 summary。
复用 backend/eval_042：
- config : PRIMARY_JUDGE / REPEATS / ENUM_MAPS 等
- eval_run.run : 分类 / 判官打分 / 写回 Langfuse / 独立回查 / 人工一致率 / NDJSON 分批落盘
- eval_run 内部委托 judge_client / langfuse_export，全部经 offline_guard 守卫 loopback（离线硬约束）

CLI 参数（保留 Task 02 语义）：
  --dataset / --out / --max-items / --dry-run
扩展参数（供 Task 04 实跑 A/B/C）：
  --task / --judge / --repeats / --reference / --progress / --no-write-back
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

from eval_042 import config, eval_run  # noqa: E402


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)


def main() -> int:
    ap = argparse.ArgumentParser(description="自建判官打分并写回 Langfuse score（薄封装）")
    # 保留 Task 02 既有参数语义
    ap.add_argument("--dataset", default="docs/sdd/plans/042/task-02-eval-dataset.json")
    ap.add_argument("--out", default="docs/sdd/plans/042/task-02-eval-run-summary.json")
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="不写回，仅统计分类")
    # Task 04 扩展参数（供 A/B/C 实跑）
    ap.add_argument("--task", default="chat_quality")
    ap.add_argument("--judge", default=config.PRIMARY_JUDGE)
    ap.add_argument("--repeats", type=int, default=config.REPEATS)
    ap.add_argument("--reference", default=None, help="人工 gold 标注文件（含 labels 字段）")
    ap.add_argument("--progress", default=None, help="NDJSON 分批进度落盘路径")
    ap.add_argument("--no-write-back", action="store_true", help="禁止写回 Langfuse（如边界 9 验证）")
    args = ap.parse_args()

    dataset_path = _resolve(args.dataset)
    out_path = _resolve(args.out)
    progress_path = _resolve(args.progress) if args.progress else None
    reference_path = _resolve(args.reference) if args.reference else None

    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)
    if args.max_items is not None:
        items = items[: args.max_items]

    write_back = (not args.dry_run) and (not args.no_write_back)

    if args.dry_run:
        # 保留 Task 02 dry-run 语义：仅分类计数，绝不调用判官（零网络）。
        # 复用 eval_run.classify_for_task，不引入第二套评分/写回逻辑。
        results = []
        skipped: Counter = Counter()
        for it in items:
            status, reason = eval_run.classify_for_task(it, args.task)
            if status != "scored":
                results.append({"trace_id": it.get("trace_id"), "status": status,
                                "skip_reason": reason})
                skipped[reason] += 1
            else:
                results.append({"trace_id": it.get("trace_id"), "status": "dry_run_scored",
                                "label": None, "score": None})
        summary = {
            "task": args.task, "judge": args.judge, "repeats": args.repeats,
            "dry_run": True, "n_items": len(items), "written": 0,
            "skipped": dict(skipped), "unavailable": 0, "verified_on_trace": 0,
            "label_distribution": {}, "mean_score": None, "judge_calls": 0,
            "reference": reference_path, "human_agree": None, "results": results,
        }
    else:
        # 唯一实跑入口：eval_run.run（内部已含分类/判官/写回/回查/人工一致率/分批落盘）
        summary = eval_run.run(
            items, args.task, args.judge, args.repeats, write_back,
            reference_path=reference_path, progress_path=progress_path,
        )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    ha = summary.get("human_agree") or {}
    print(f"[run-eval] task={summary['task']} judge={summary['judge']} "
          f"repeats={summary['repeats']} write_back={write_back}")
    print(f"[run-eval] n_items={summary['n_items']} written={summary['written']} "
          f"skipped={summary['skipped']} unavailable={summary['unavailable']} "
          f"verified_on_trace={summary['verified_on_trace']} judge_calls={summary['judge_calls']}")
    if ha:
        print(f"[run-eval] human_agree: n={ha['n']} agree_rate={ha['agree_rate']} "
              f"verdict={ha['verdict']}")
    print(f"[run-eval] summary -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
