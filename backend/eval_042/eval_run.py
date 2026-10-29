"""spec-042 Task 04 评测闭环模块（把 task-02-run-eval.py 的脚本逻辑收敛为可复用模块）。

复用既有能力（禁止第二套实现）：
- config        : PRIMARY_JUDGE / REPEATS / ENUM_MAPS 等
- judge_client  : judge_repeats(温度0重复评分) / enum_to_score / parse_r4
- langfuse_export: classify_output / post_score / list_scores（均经 offline_guard 守卫 loopback）

职责：
- classify_for_task : 分类单条（空 output / Intake / 边界9 no_prior_context / scored）
- run               : 逐条跑判官、写回、独立回查、分批落盘 NDJSON，返回完整 summary dict
- human_agree       : 判官多数标签 vs 人工 gold 的一致率 / 混淆矩阵 / 不一致明细

离线硬约束：所有对外 HTTP（Ollama/Langfuse）必须经 offline_guard.assert_loopback，
本模块不直接发请求，全部委托给 judge_client / langfuse_export（它们已守卫）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from contextlib import nullcontext
from typing import Optional

# 支持两种运行方式：
#   python -m eval_042.eval_run            （推荐；相对导入可用）
#   python backend/eval_042/eval_run.py    （脚本方式：把 backend/ 加入 sys.path 后改绝对导入）
if __name__ == "__main__" and __package__ in (None, ""):
    _PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _PARENT not in sys.path:
        sys.path.insert(0, _PARENT)
    import importlib

    _mod = importlib.import_module("eval_042.eval_run")
    raise SystemExit(_mod.main())

from . import config, judge_client, langfuse_export

# chat_quality 的人工 gold 与判官标签同域；human_agree 的混淆矩阵维度固定为 good/partial/poor
QUALITY_LABELS = ["good", "partial", "poor"]


def classify_for_task(item: dict, task: str) -> tuple[str, Optional[str]]:
    """对单条样本做前分类，决定是否需要调用判官。

    返回 (status, reason)：
    - ("skipped", "empty_output")      : 空/空白 output（来自 classify_output）
    - ("skipped", "intake_text")       : 命中 Intake 路由文案（来自 classify_output）
    - ("skipped", "no_prior_context")  : 边界 9 —— task==memory_correctness 且无有效 prior_context
    - ("scored", None)                : 允许调用判官

    设计：先走 langfuse_export.classify_output（空/Intake），再追加边界 9。
    synthetic 处理在 run 内进行（skipped_synthetic），不污染本函数的四分支语义。
    """
    status, reason = langfuse_export.classify_output(item.get("output"))
    if status != "scored":
        return status, reason
    if task == "memory_correctness":
        prior = item.get("prior_context")
        if prior is None or (isinstance(prior, str) and prior.strip() == ""):
            return "skipped", "no_prior_context"
    return "scored", None


def human_agree(results: list[dict], reference_labels: dict) -> dict:
    """判官多数标签 vs 人工 gold 的一致率统计（纯函数，无网络）。

    - 只统计「判官多数标签存在 且 人工 gold 存在」的项（缺标注不计入分母）；
    - 输出 agree_rate / n / confusion_matrix（3x3，行=人工 gold，列=判官多数标签）/ disagreements；
    - 阈值写回 verdict：ok(>=0.70) / needs_calibration(0.60-0.70) / trigger_fallback_review(<0.60)。
    """
    n = 0
    agree = 0
    confusion: dict[str, dict[str, int]] = {g: dict.fromkeys(QUALITY_LABELS, 0) for g in QUALITY_LABELS}
    disagreements: list[dict] = []
    for rec in results:
        if rec.get("status") != "scored":
            continue
        label = rec.get("label")
        if label is None:
            continue
        tid = rec.get("trace_id")
        gold = reference_labels.get(tid)
        if gold is None:
            continue  # 缺人工标注不计入分母
        n += 1
        if label == gold:
            agree += 1
        else:
            disagreements.append({
                "trace_id": tid,
                "human": gold,
                "judge": label,
                "explanation": rec.get("comment") or rec.get("explanation") or "",
            })
        if gold in confusion and label in confusion.get(gold, {}):
            confusion[gold][label] += 1
    agree_rate = (agree / n) if n else None
    if agree_rate is None:
        verdict = "no_data"
    elif agree_rate >= 0.70:
        verdict = "ok"
    elif agree_rate >= 0.60:
        verdict = "needs_calibration"
    else:
        verdict = "trigger_fallback_review"
    return {
        "agree_rate": agree_rate,
        "n": n,
        "confusion_matrix": confusion,
        "disagreements": disagreements,
        "verdict": verdict,
    }


def _latest_same_name(scores: list[dict], task: str, trace_id: Optional[str] = None) -> Optional[dict]:
    """在 scores 中按 name==task（且 traceId==trace_id，若给定）精确过滤，返回『最新一条』（用于 delta write 比对）。

    口径：优先按 timestamp / createdAt 取最大；若所有候选都缺时间字段，
    则按 list_scores 返回顺序的【最后一条】作为最新（Langfuse 默认按时间倒序返回，
    但缺时间字段时不依赖该假设，明确退化为返回顺序末位）。绝不触碰其它 name 的 score。

    注意：本实例 Langfuse public scores API 实测会【忽略 traceId 查询参数、返回全局 score】
    （见 task-05-report「策略修订」）。因此必须在此按 traceId 二次过滤，才能真正做到
    「同 trace 同维度」的 delta 比对，避免把其它 trace 的最新值误当作本 trace 的最新值。
    """
    cq = [s for s in scores if s.get("name") == task]
    if trace_id is not None:
        cq = [s for s in cq if s.get("traceId") == trace_id]
    if not cq:
        return None

    def _ts(s: dict) -> object:
        t = s.get("timestamp")
        if t is None:
            t = s.get("createdAt")
        return t

    if any(_ts(s) is not None for s in cq):
        return max(cq, key=lambda s: _ts(s) if _ts(s) is not None else "")
    return cq[-1]


def _value_equal(target: object, existing: object, tol: float = 1e-9) -> bool:
    """比较『将写入的 value』与『既有最新 score 的 value』是否相同（浮点容差 tol）。

    - target / existing 任一为 None -> 视为不同（保守写入，由调用方记 idempotent_check_error）；
    - 任一无法解析为浮点 -> 视为不同（解析异常，保守写入）；
    - 否则按 abs(target-existing) <= tol 判等。
    """
    if target is None or existing is None:
        return False
    try:
        return abs(float(target) - float(existing)) <= tol
    except (TypeError, ValueError):
        return False


def _process_one(item: dict, task: str, judge: str, repeats: int,
                 write_back: bool, idempotent: bool = False,
                 state: Optional[dict] = None) -> tuple[dict, bool]:
    """处理单条。返回 (rec, judge_called:bool)。

    state：可选的本地幂等状态表（{f"{task}:{trace_id}": {...}}）。
    存在的理由：本实例 Langfuse public scores API 实测**忽略 traceId 查询参数、返回全局 score**，
    导致 list_scores 取不到「本 trace 最新那一条」，纯服务端比对会漏判而重复写。
    本地状态表记录「我们确实写过的值」，是本模块**唯一可靠**的幂等判据源。
    """
    tid = item.get("trace_id")
    status, reason = classify_for_task(item, task)

    # synthetic 条目不得写回真实 Langfuse（沿用既有 skipped_synthetic 处理）
    if status == "scored" and item.get("synthetic"):
        return ({"trace_id": tid, "status": "skipped",
                 "skip_reason": "skipped_synthetic", "label": None, "score": None}, False)

    if status != "scored":
        return ({"trace_id": tid, "status": status, "skip_reason": reason,
                 "label": None, "score": None}, False)

    # scored：调用判官（温度0，REPEATS 次取多数）
    q, a = item.get("input", ""), item.get("output", "")
    ctx = item.get("prior_context")
    calls = judge_client.judge_repeats(judge, task, q, a, repeats, ctx=ctx)
    labels = [c["label"] for c in calls if c["status"] == "scored"]
    explanations = [c["explanation"] for c in calls if c["status"] == "scored"]

    if not labels:
        # 判官全 unavailable -> status=unavailable，绝不静默记 0 分
        return ({
            "trace_id": tid, "status": "unavailable", "label": None, "score": None,
            "skip_reason": "judge_all_unavailable",
            "errors": [c.get("error") for c in calls],
        }, True)

    label = Counter(labels).most_common(1)[0][0]
    expl = next((e for e, lab in zip(explanations, labels, strict=True) if lab == label), "")
    score = judge_client.enum_to_score(task, label)
    rec: dict = {
        "trace_id": tid, "status": "scored", "label": label, "score": score,
        "name": task, "raw_labels": labels,
    }

    if write_back:
        comment = f"Explanation: {expl} Answer: {label}"
        rec["comment"] = comment
        if idempotent:
            # ---- delta write 语义（D 节修订，取代 delete-then-write）----
            # 默认评测流程不再触发任何 delete；删除交给独立的 --prune-duplicates。
            rec["deleted_preexisting"] = 0
            rec["delete_errors"] = 0
            rec["skipped_unchanged"] = False
            rec["idempotent_check_error"] = None
            # ① 本地幂等状态表优先（唯一可靠判据源，见 _process_one docstring）
            state_key = f"{task}:{tid}"
            prev = (state or {}).get(state_key)
            if prev is not None and _value_equal(score, prev.get("value")):
                rec["skipped_unchanged"] = True
                rec["score_id"] = prev.get("score_id")
                rec["verify_source"] = "local_state"
                rec["verified"] = True
                return rec, True
            try:
                all_scores = langfuse_export.list_scores(tid, limit=100)
            except Exception as exc:
                # list_scores 失败：无法确认既有分 -> 保守写入一条新分（不静默跳过）
                all_scores = []
                rec["idempotent_check_error"] = f"list_failed:{type(exc).__name__}"
            # 精确按 name == task 且 traceId == tid 过滤（Langfuse API 忽略 traceId，须客户端二次过滤），
            # 绝不触碰 ttft_ms/eval_ms/is_cold_start 等观测 score，也绝不误用其它 trace 的分
            existing = _latest_same_name(all_scores, task, tid)
            if existing is not None:
                ex_val = existing.get("value")
                same = _value_equal(score, ex_val)
                if not same:
                    if ex_val is None:
                        # 现有同名 score 的 value 为 None -> 保守写入并记录检查异常
                        rec["idempotent_check_error"] = "existing_value_none"
                    else:
                        try:
                            float(ex_val)
                        except (TypeError, ValueError):
                            # 现有 value 无法解析为浮点 -> 保守写入并记录检查异常
                            rec["idempotent_check_error"] = "existing_value_unparseable"
                if same:
                    # 同值跳过：不删、不写，视为已落地（计入 verified）
                    rec["skipped_unchanged"] = True
                    rec["score_id"] = existing.get("id")
                    return rec, True
            # 否则：无同名 / 值不同 / 解析异常 -> 只写一条新分（不删旧分）
        try:
            posted = langfuse_export.post_score(
                name=task, value=score, trace_id=tid, comment=comment)
            rec["score_id"] = posted.get("id")
            # ② 写回成功 -> 记录本地幂等状态（下次同值即跳过）
            if idempotent and state is not None and rec.get("score_id"):
                state[state_key] = {"task": task, "value": score, "label": label,
                                    "score_id": rec["score_id"]}
        except Exception as exc:  # 写回失败如实记录，不静默记 0
            rec["write_error"] = f"{type(exc).__name__}: {exc}"
            rec["score_id"] = None

    return rec, True


def _verify_written(results: list[dict], attempts: int = 5, sleep_s: float = 1.5) -> int:
    """独立回查：逐条 scored 记录的 trace 上确有本 name 的 score（分页 + 重试克服最终一致竞态）。"""
    verified = 0
    for rec in results:
        # 由本地幂等状态表判定的「同值跳过」：已在上轮真实写回并回查过，无需重复联网校验
        if rec.get("verify_source") == "local_state":
            rec["verified"] = True
            verified += 1
            continue
        if rec.get("status") != "scored" or not rec.get("score_id"):
            rec["verified"] = None  # 未写回（dry_run/no_write_back/unavailable）不适用
            continue
        tid, name = rec["trace_id"], rec["name"]
        ok = False
        last_err = None
        for _ in range(attempts):
            try:
                # Langfuse public scores API 的 limit 上限为 100，超出返回 400
                scores = langfuse_export.list_scores(tid, limit=100)
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                scores = []
            if any(s.get("name") == name and s.get("traceId") == tid for s in scores):
                ok = True
                break
            time.sleep(sleep_s)
        rec["verified"] = ok
        rec["verify_error"] = None if ok else last_err
        if ok:
            verified += 1
    return verified


def _load_state(path: Optional[str]) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # 状态文件损坏 -> 退化为纯服务端比对，不阻断评测


def _save_state(path: Optional[str], state: dict) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"entries": state}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # 原子写，避免中断留下半截状态


def run(dataset: list[dict], task: str, judge: str, repeats: int, write_back: bool,
        reference_path: Optional[str] = None,
        progress_path: Optional[str] = None,
        idempotent: bool = False,
        state_path: Optional[str] = None) -> dict:
    """评测主流程。返回完整 summary dict（调用方负责落盘；progress_path 为增量 NDJSON）。

    state_path：本地幂等状态表路径（仅 idempotent=True 时生效）。
    本实例 Langfuse `GET /api/public/scores?traceId=` 实测忽略 traceId，
    故服务端比对不可靠，必须以来地状态表作为「我们写过什么」的判据源。

    - skipped -> 不调用判官、不写 score；
    - scored  -> judge_repeats 取多数标签 -> enum_to_score -> 写回（write_back 时）；
    - 全 unavailable -> status=unavailable（绝不静默记 0）；
    - 写完后独立回查标记 verified；
    - reference_path 存在 -> human_agree 并入汇总。
    """
    results: list[dict] = []
    n_items = len(dataset)
    written = 0
    skipped_by_reason: Counter = Counter()
    unavailable = 0
    judge_calls = 0
    label_distribution: Counter = Counter()
    score_sum = 0.0
    score_count = 0
    write_errors = 0
    deleted_preexisting = 0
    delete_errors = 0
    skipped_unchanged = 0
    idempotent_check_errors = 0
    state = _load_state(state_path) if idempotent else {}

    with (open(progress_path, "a", encoding="utf-8") if progress_path else nullcontext()) as progress_fh:
        for item in dataset:
            rec, called = _process_one(item, task, judge, repeats, write_back,
                                       idempotent=idempotent, state=state)
            judge_calls += 1 if called else 0

            if rec["status"] == "scored":
                if rec.get("skipped_unchanged"):
                    skipped_unchanged += 1  # 同值跳过：计入已落地但不计为本次新写
                else:
                    written += 1 if rec.get("score_id") else 0
                if rec.get("write_error"):
                    write_errors += 1
                deleted_preexisting += rec.get("deleted_preexisting", 0)
                delete_errors += rec.get("delete_errors", 0)
                idempotent_check_errors += 1 if rec.get("idempotent_check_error") else 0
                if rec.get("label") is not None:
                    label_distribution[rec["label"]] += 1
                if isinstance(rec.get("score"), (int, float)):
                    score_sum += rec["score"]
                    score_count += 1
            elif rec["status"] == "unavailable":
                unavailable += 1
            else:  # skipped（含 empty_output / intake_text / no_prior_context / skipped_synthetic）
                reason = rec.get("skip_reason") or rec["status"]
                skipped_by_reason[reason] += 1

            results.append(rec)
            if progress_fh is not None:
                progress_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                progress_fh.flush()

    verified_on_trace = _verify_written(results)
    if idempotent:
        _save_state(state_path, state)

    human = None
    if reference_path:
        with open(reference_path, encoding="utf-8") as f:
            ref = json.load(f)
        human = human_agree(results, ref.get("labels", {}))

    summary = {
        "task": task,
        "judge": judge,
        "repeats": repeats,
        "write_back": write_back,
        "n_items": n_items,
        "written": written,
        "skipped": dict(skipped_by_reason),
        "unavailable": unavailable,
        "verified_on_trace": verified_on_trace,
        "write_errors": write_errors,
        "deleted_preexisting": deleted_preexisting,
        "delete_errors": delete_errors,
        "skipped_unchanged": skipped_unchanged,
        "idempotent_check_errors": idempotent_check_errors,
        "idempotent": idempotent,
        "state_path": state_path,
        "state_entries": len(state) if idempotent else 0,
        "label_distribution": dict(label_distribution),
        "mean_score": (round(score_sum / score_count, 4) if score_count else None),
        "judge_calls": judge_calls,
        "reference": reference_path,
        "human_agree": human,
        "results": results,
    }
    return summary


# ---------- CLI 入口（仅 backend/eval_042 内，落盘产物在 docs/sdd/plans/042/task-05-*） ----------

def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)


def _score_counts(scores: list[dict], task: str) -> dict:
    non = [s for s in scores if s.get("name") != task]
    return {"total": len(scores), "non_chat_quality": len(non)}


def _cmd_cleanup(args) -> int:
    """受控清理：对数据集里已评分的 trace，保留最新一条同名 score，删除其余。

    实现要点（2026-09-24 修正）：
    - 本实例 Langfuse 的 `?traceId=` 查询参数**被服务端忽略**，`list_scores(tid)` 返回的是
      **同一份全局集合**。旧实现按 trace 循环 20 次，等于把同一批 id 重复下发删除 20 次。
      故改为**一次性全局拉取**（`list_scores_global`）后，在客户端按 `traceId` 分组、
      按 `id` 去重，再删除。
    - 只处理 `name == task` 的 score，绝不触碰观测类 score；
    - 清理前先落盘备份被删 score 到 --backup（可回滚）；
    - 清理后回查（同样是全局口径）统计每 trace 的剩余条数。
    """
    dataset_path = _resolve(args.dataset)
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)
    task = args.task
    trace_ids = [it["trace_id"] for it in items
                 if it.get("status") == "scored" and not it.get("synthetic")]
    target = set(trace_ids)

    # 一次性全局拉取（服务端忽略 traceId，客户端分组）
    all_scores = langfuse_export.list_scores_global(limit=100)
    misdelete_before = {
        "global_total": len(all_scores),
        "global_non_target": len([s for s in all_scores if s.get("name") != task]),
    }

    # 按 trace 分组，仅保留 name==task 且在目标 trace 集合内的；每组按时间保留最新一条
    by_trace: dict[str, list[dict]] = {}
    for s in all_scores:
        if s.get("name") != task:
            continue
        tid = s.get("traceId")
        if tid in target:
            by_trace.setdefault(tid, []).append(s)

    to_delete: list[dict] = []
    seen_ids: set = set()
    for tid, cq in by_trace.items():
        if len(cq) <= 1:
            continue
        cq_sorted = sorted(
            cq, key=lambda s: s.get("timestamp") or s.get("createdAt") or "",
            reverse=True)
        for s in cq_sorted[1:]:
            sid = s.get("id")
            if sid in seen_ids:  # 全局去重：同一个 id 只下发一次删除
                continue
            seen_ids.add(sid)
            to_delete.append({
                "id": sid, "value": s.get("value"),
                "name": s.get("name"), "traceId": s.get("traceId"),
                "timestamp": s.get("timestamp"),
            })

    # 先落盘备份，再删除（可回滚到「可重跑」状态）
    backup_path = _resolve(args.backup)
    os.makedirs(os.path.dirname(backup_path) or ".", exist_ok=True)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump({
            "task": task,
            "n_trace_ids": len(trace_ids),
            "n_to_delete": len(to_delete),
            "deleted_scores": to_delete,
            "misdelete_before": misdelete_before,
        }, f, ensure_ascii=False, indent=2)

    # 执行删除（失败如实记录，不静默兜底）
    delete_failures: list[dict] = []
    for rec in to_delete:
        try:
            ok = langfuse_export.delete_score(rec["id"])
            if not ok:
                delete_failures.append({"id": rec["id"], "error": "delete returned False"})
        except Exception as exc:
            delete_failures.append({"id": rec["id"],
                                    "error": f"{type(exc).__name__}: {exc}"})

    # 回查（全局口径）：统计每个目标 trace 的剩余同名 score 条数
    after = langfuse_export.list_scores_global(limit=100)
    per_trace: dict = {tid: 0 for tid in trace_ids}
    for s in after:
        if s.get("name") == task and s.get("traceId") in per_trace:
            per_trace[s["traceId"]] += 1

    misdelete_after = {
        "global_total": len(after),
        "global_non_target": len([s for s in after if s.get("name") != task]),
    }

    summary = {
        "task": task,
        "n_trace_ids": len(trace_ids),
        "deleted_count": len(to_delete),
        "delete_failures": delete_failures,
        "per_trace_chat_quality_count": per_trace,
        "all_exactly_one": all(v == 1 for v in per_trace.values()),
        "misdelete_check": {"before": misdelete_before, "after": misdelete_after},
        "backup": backup_path,
        "note": "score 删除为异步队列，回查为下发后立即查询，故 per_trace 仍可能>1，"
                "需等队列排空后复跑本命令收敛；本次不伪造为即时生效。",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="spec-042 Task 05 评测写回（幂等）/ 存量清理")
    ap.add_argument("--dataset", default="docs/sdd/plans/042/task-02-eval-dataset.json")
    ap.add_argument("--out", default="docs/sdd/plans/042/task-05-run-summary.json")
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--task", default="chat_quality")
    ap.add_argument("--judge", default=config.PRIMARY_JUDGE)
    ap.add_argument("--repeats", type=int, default=config.REPEATS)
    ap.add_argument("--reference", default=None)
    ap.add_argument("--progress", default=None)
    ap.add_argument("--no-write-back", action="store_true")
    ap.add_argument("--idempotent", action="store_true",
                    help="开启 delta write 幂等写回：写回前比对同名最新 score，值相同则跳过"
                         "（不删不写），值不同仅追加写一条新分（默认关闭，保持 Task 04 语义）")
    ap.add_argument("--state", default="docs/sdd/plans/042/task-05-score-state.json",
                    help="本地幂等状态表路径（仅 --idempotent 生效）：记录已写回的 (trace,task)->value/score_id，"
                         "用于绕过 Langfuse 忽略 traceId 参数导致的服务端比对不可靠")
    ap.add_argument("--cleanup-duplicates", action="store_true",
                    help="受控清理重复 chat_quality score（保留最新，删除其余）")
    ap.add_argument("--backup", default="docs/sdd/plans/042/task-05-cleanup-backup.json")
    args = ap.parse_args()

    if args.cleanup_duplicates:
        return _cmd_cleanup(args)

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
        # 保留 Task 02 dry-run 语义：仅分类计数，绝不调用判官（零网络）。复用 classify_for_task。
        results = []
        skipped: Counter = Counter()
        for it in items:
            status, reason = classify_for_task(it, args.task)
            if status != "scored":
                results.append({"trace_id": it.get("trace_id"), "status": status,
                                "skip_reason": reason})
                skipped[reason] += 1
            else:
                results.append({"trace_id": it.get("trace_id"), "status": "dry_run_scored",
                                "label": None, "score": None})
        summary = {
            "task": args.task, "judge": args.judge, "repeats": args.repeats,
            "dry_run": True, "idempotent": args.idempotent, "n_items": len(items),
            "written": 0, "skipped": dict(skipped), "unavailable": 0,
            "verified_on_trace": 0, "label_distribution": {}, "mean_score": None,
            "judge_calls": 0, "reference": reference_path, "human_agree": None,
            "results": results,
        }
    else:
        # 唯一实跑入口：eval_run.run（内部含分类/判官/写回/幂等删除/回查/人工一致率/分批落盘）
        summary = run(items, args.task, args.judge, args.repeats, write_back,
                     reference_path=reference_path, progress_path=progress_path,
                     idempotent=args.idempotent,
                     state_path=_resolve(args.state) if args.idempotent else None)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    ha = summary.get("human_agree") or {}
    print(f"[eval_run] task={summary['task']} judge={summary['judge']} "
          f"repeats={summary['repeats']} write_back={write_back} "
          f"idempotent={summary.get('idempotent')}")
    print(f"[eval_run] n_items={summary['n_items']} written={summary['written']} "
          f"skipped={summary['skipped']} unavailable={summary['unavailable']} "
          f"verified_on_trace={summary['verified_on_trace']} "
          f"deleted_preexisting={summary.get('deleted_preexisting')} "
          f"delete_errors={summary.get('delete_errors')} "
          f"judge_calls={summary['judge_calls']}")
    if ha:
        print(f"[eval_run] human_agree: n={ha['n']} agree_rate={ha['agree_rate']} "
              f"verdict={ha['verdict']}")
    print(f"[eval_run] summary -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
