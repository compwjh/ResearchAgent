"""spec-042 Task 03 — 记忆探针集与评测器（合成数据，synthetic=True，绝不冒充真实 trace）。

设计前提（见 task-03-memory-probe.md）：
- 用专门构造的「用户先陈述偏好/事实 → 后续追问 → agent 回答」探针，重测 memory_correctness；
- 每条带构造真值 gold（非人工标注），用于验证判官在该维度上的判别有效性下界；
- 三类门禁：G1 自一致（>=0.90）、G2 判别有效性（多数标签==gold，>=0.80）、
  G3 跨判官一致（9b 多数==27b 多数，>=0.80）；
- 裁决链：G1∧G2∧G3 全过 → adopt:qwen3.5:9b；9b 不过而 27b 过 → fallback:qwen3.8:27b；
  否则 no-go。
- 全部判官调用经 offline_guard 守卫，仅指本机 Ollama loopback，不触外网。
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass

from .config import (
    CROSS_AGREE_THRESHOLD,
    GOLD_ACC_THRESHOLD,
    OLLAMA_BASE,
    SELF_CONSISTENCY_THRESHOLD,
)
from .judge_client import judge_repeats
from .offline_guard import assert_loopback


@dataclass
class MemoryProbe:
    probe_id: str
    prior_context: str
    question: str
    answer: str
    gold: str
    synthetic: bool = True


# 20 条探针：四类 gold 各 5 条。构造要求——不带偏见的读者能一眼判定 gold，
# answer 的措辞让 gold 客观可判，禁止模棱两可样本。
MEMORY_PROBES: list[MemoryProbe] = [
    # ---------- remembered（明确、完整复述先前陈述） ----------
    MemoryProbe(
        probe_id="mp-rem-01",
        prior_context="我平时只喝美式咖啡，不加糖也不加奶。",
        question="那给我推荐一款咖啡？",
        answer="根据您之前说的，您平时只喝美式咖啡，不加糖也不加奶，所以我推荐您点一杯美式咖啡。",
        gold="remembered",
    ),
    MemoryProbe(
        probe_id="mp-rem-02",
        prior_context="我每周三晚上固定去健身房练腿。",
        question="我今晚该练什么？",
        answer="您之前说过每周三晚上固定去健身房练腿，所以今晚建议您安排腿部训练。",
        gold="remembered",
    ),
    MemoryProbe(
        probe_id="mp-rem-03",
        prior_context="我对花生严重过敏，任何含花生的食物都不能碰。",
        question="这个沙拉我能吃吗？",
        answer="您提到对花生严重过敏、任何含花生的食物都不能碰，这份沙拉含花生酱，所以您不能吃。",
        gold="remembered",
    ),
    MemoryProbe(
        probe_id="mp-rem-04",
        prior_context="我的母语是粤语，更习惯看繁体中文。",
        question="界面语言帮我设成什么？",
        answer="您说过母语是粤语、更习惯看繁体中文，那就把界面语言设为繁体中文。",
        gold="remembered",
    ),
    MemoryProbe(
        probe_id="mp-rem-05",
        prior_context="我住在上海，通勤靠地铁，不开车。",
        question="明天出门怎么安排？",
        answer="您之前说住上海、通勤靠地铁、不开车，所以建议您明天坐地铁出行。",
        gold="remembered",
    ),
    # ---------- partially_remembered（复述了但遗漏关键项或细节说错） ----------
    MemoryProbe(
        probe_id="mp-par-01",
        prior_context="我喝咖啡只要美式，不加糖不加奶，而且只要冰的。",
        question="帮我点杯咖啡。",
        answer="您说过只喝美式、不加糖不加奶，我帮您点一杯美式。",
        gold="partially_remembered",  # 遗漏「只要冰的」
    ),
    MemoryProbe(
        probe_id="mp-par-02",
        prior_context="我每周三、周五晚上去健身房，周三练腿、周五练背。",
        question="我今晚（周五）练什么？",
        answer="您每周三、周五去健身房，今晚您练腿。",
        gold="partially_remembered",  # 周五应是练背，答成练腿（细节说错）
    ),
    MemoryProbe(
        probe_id="mp-par-03",
        prior_context="我对花生和芒果都过敏。",
        question="这个甜点能吃吗？",
        answer="您提过对花生过敏，这个甜点含花生，所以您不能吃。",
        gold="partially_remembered",  # 遗漏芒果过敏
    ),
    MemoryProbe(
        probe_id="mp-par-04",
        prior_context="我的预算是 5000 元以内，想买一台轻薄笔记本，并且要 16G 内存。",
        question="按我的条件推荐？",
        answer="您预算 5000 元以内、想买轻薄笔记本，推荐这款轻薄本。",
        gold="partially_remembered",  # 遗漏 16G 内存要求
    ),
    MemoryProbe(
        probe_id="mp-par-05",
        prior_context="我是素食主义者，不吃肉也不吃蛋。",
        question="这个三明治适合我吗？",
        answer="您是素食主义者、不吃肉，这款三明治没有肉，可以吃。",
        gold="partially_remembered",  # 遗漏不吃蛋（且该三明治可能含蛋）
    ),
    # ---------- forgotten（完全没提 / 说不了解偏好 / 给出通用无关回答） ----------
    MemoryProbe(
        probe_id="mp-for-01",
        prior_context="我只在周末看电影，工作日不看的。",
        question="今晚陪我选部电影？",
        answer="好的，我为您推荐几部近期热门电影：《奥本海默》《芭比》《封神》。",
        gold="forgotten",  # 未召回周末-only 偏好，给通用推荐
    ),
    MemoryProbe(
        probe_id="mp-for-02",
        prior_context="我对乳糖不耐受，不能喝牛奶。",
        question="给我配杯饮品。",
        answer="我不太了解您的饮品偏好，为您推荐一款畅销拿铁。",
        gold="forgotten",  # 明确表示不了解偏好
    ),
    MemoryProbe(
        probe_id="mp-for-03",
        prior_context="我养了一只叫「豆豆」的柯基犬。",
        question="我家宠物叫什么？",
        answer="抱歉，我目前没有关于您宠物的信息，无法回答。",
        gold="forgotten",  # 完全没召回
    ),
    MemoryProbe(
        probe_id="mp-for-04",
        prior_context="我工作用 Windows，不用 Mac。",
        question="帮我把软件装好？",
        answer="好的，这是通用安装步骤，适用于大多数电脑系统。",
        gold="forgotten",  # 未召回 Windows 偏好，给通用步骤
    ),
    MemoryProbe(
        probe_id="mp-for-05",
        prior_context="我身高 185，买衣服要 XL。",
        question="我穿什么码？",
        answer="一般成年男性建议选 L 码，您可以先试穿看看。",
        gold="forgotten",  # 未召回，给通用尺码建议
    ),
    # ---------- fabricated（编造先前从未陈述过的偏好/事实） ----------
    MemoryProbe(
        probe_id="mp-fab-01",
        prior_context="我平时只喝美式咖啡。",
        question="我口味偏甜吗？",
        answer="您之前说过您特别喜欢甜食、口味偏甜，所以美式对您可能太苦了。",
        gold="fabricated",  # 先前只说美式，从未说「喜欢甜食/偏甜」
    ),
    MemoryProbe(
        probe_id="mp-fab-02",
        prior_context="我住在上海。",
        question="我老家是哪的？",
        answer="您之前说过您老家在成都，是个美食之都。",
        gold="fabricated",  # 先前只说上海，从未说成都
    ),
    MemoryProbe(
        probe_id="mp-fab-03",
        prior_context="我每周三去健身房。",
        question="我有什么运动习惯？",
        answer="您说过您每天晨跑 5 公里，还每周游泳三次。",
        gold="fabricated",  # 先前只说周三健身，编造晨跑/游泳
    ),
    MemoryProbe(
        probe_id="mp-fab-04",
        prior_context="我对花生过敏。",
        question="我饮食要注意什么？",
        answer="您对花生和海鲜都严重过敏，千万要避开这两类。",
        gold="fabricated",  # 先前只说花生，编造海鲜过敏
    ),
    MemoryProbe(
        probe_id="mp-fab-05",
        prior_context="我的预算是 5000 元。",
        question="我偏好什么品牌？",
        answer="您说过您只买苹果品牌的产品，其他一概不考虑。",
        gold="fabricated",  # 先前从未提品牌偏好
    ),
]


def build_probe_dataset() -> list[dict]:
    """转成与 EvalItem 兼容的 dict 列表（task=memory_correctness）。

    每条含：trace_id(synthetic-memory-probe-N)、input(=prior_context+"\\n\\n追问："+question)、
    output(=answer)、status=scored、synthetic=True、gold、probe_id。
    """
    items: list[dict] = []
    for i, p in enumerate(MEMORY_PROBES, start=1):
        items.append({
            "task": "memory_correctness",
            "trace_id": f"synthetic-memory-probe-{i}",
            "input": f"{p.prior_context}\n\n追问：{p.question}",
            "output": p.answer,
            "status": "scored",
            "synthetic": True,
            "gold": p.gold,
            "probe_id": p.probe_id,
        })
    return items


def _judge_block(calls: list[dict], gold: str) -> dict:
    """把一次（探针×判官）的 repeats 次评分汇总成一个判定块。"""
    labels = [c["label"] for c in calls if c["status"] == "scored"]
    unavail = sum(1 for c in calls if c["status"] != "scored")
    majority = Counter(labels).most_common(1)[0][0] if labels else None
    return {
        "labels": labels,
        "majority": majority,
        "gold": gold,
        "gold_match": (majority == gold) if majority is not None else False,
        "unavailable_count": unavail,
    }


def _consistent(block: dict, repeats: int) -> int:
    """该判官在该探针上是否自一致：全 unavailable 计为不一致；否则标签唯一即一致。"""
    if block["unavailable_count"] == repeats:
        return 0
    return 1 if len(set(block["labels"])) == 1 else 0


def run_probe(primary: str, fallback: str, repeats: int, out_path: str,
              progress_path: str | None = None) -> dict:
    """对 20 条探针用 primary/fallback 各评分 repeats 次（温度 0，ctx=prior_context）。

    逐条记录 labels/majority/gold/gold_match/unavailable_count，汇总 G1/G2/G3 与裁决链 decision；
    每完成一条 append 到 progress（NDJSON），最终写完整 JSON 到 out_path。
    """
    assert_loopback(OLLAMA_BASE)
    gold_counter = Counter(p.gold for p in MEMORY_PROBES)
    gold_distribution = {g: gold_counter.get(g, 0) for g in
                         ("remembered", "partially_remembered", "forgotten", "fabricated")}

    records: list[dict] = []
    per_gold = {g: {"n": 0, "g2_hit": 0} for g in gold_distribution}
    total_unavail = 0
    total_calls = 0

    for p in MEMORY_PROBES:
        p_calls = judge_repeats(primary, "memory_correctness", p.question, p.answer,
                                repeats, ctx=p.prior_context)
        f_calls = judge_repeats(fallback, "memory_correctness", p.question, p.answer,
                                repeats, ctx=p.prior_context)
        p_block = _judge_block(p_calls, p.gold)
        f_block = _judge_block(f_calls, p.gold)
        cross_match = (p_block["majority"] is not None and f_block["majority"] is not None
                       and p_block["majority"] == f_block["majority"])
        rec = {
            "probe_id": p.probe_id,
            "gold": p.gold,
            "prior_context": p.prior_context,
            "question": p.question,
            "answer": p.answer,
            "primary": p_block,
            "fallback": f_block,
            "cross_match": cross_match,
        }
        records.append(rec)
        total_unavail += p_block["unavailable_count"] + f_block["unavailable_count"]
        total_calls += 2 * repeats
        # per-gold 命中统计（primary 多数标签 == gold 即计为命中）
        per_gold[p.gold]["n"] += 1
        if p_block["gold_match"]:
            per_gold[p.gold]["g2_hit"] += 1
        if progress_path:
            with open(progress_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- 门禁统计 ----
    g1_all, g2_all, g3_all = [], [], []
    per_model = {}
    for model_key, block_key in (("primary", "primary"), ("fallback", "fallback")):
        g1_m, g2_m = [], []
        for r in records:
            blk = r[block_key]
            g1_m.append(_consistent(blk, repeats))
            g2_m.append(1 if blk["gold_match"] else 0)
            g1_all.append(_consistent(blk, repeats))
            g2_all.append(1 if blk["gold_match"] else 0)
        per_model[model_key] = {
            "G1_self_consistency": round(statistics.fmean(g1_m), 4) if g1_m else 0.0,
            "G2_gold_accuracy": round(statistics.fmean(g2_m), 4) if g2_m else 0.0,
        }
    for r in records:
        if r["primary"]["majority"] is not None and r["fallback"]["majority"] is not None:
            g3_all.append(1 if r["cross_match"] else 0)
    G1 = round(statistics.fmean(g1_all), 4) if g1_all else 0.0
    G2 = round(statistics.fmean(g2_all), 4) if g2_all else 0.0
    G3 = round(statistics.fmean(g3_all), 4) if g3_all else 0.0

    # ---- 裁决链（沿用 Q8=A） ----
    primary_ok = (per_model["primary"]["G1_self_consistency"] >= SELF_CONSISTENCY_THRESHOLD
                  and per_model["primary"]["G2_gold_accuracy"] >= GOLD_ACC_THRESHOLD)
    fallback_ok = (per_model["fallback"]["G1_self_consistency"] >= SELF_CONSISTENCY_THRESHOLD
                   and per_model["fallback"]["G2_gold_accuracy"] >= GOLD_ACC_THRESHOLD)
    g3_ok = G3 >= CROSS_AGREE_THRESHOLD
    if primary_ok and g3_ok:
        decision = f"adopt:{primary}"
        reason = (f"primary(9b) G1={per_model['primary']['G1_self_consistency']}>="
                  f"{SELF_CONSISTENCY_THRESHOLD} 且 G2={per_model['primary']['G2_gold_accuracy']}>="
                  f"{GOLD_ACC_THRESHOLD}，且 G3={G3}>={CROSS_AGREE_THRESHOLD}：全过")
    elif fallback_ok and g3_ok:
        decision = f"fallback:{fallback}"
        reason = (f"primary(9b) 未过（G1={per_model['primary']['G1_self_consistency']}/"
                  f"G2={per_model['primary']['G2_gold_accuracy']}），但 fallback(27b) 过"
                  f"（G1={per_model['fallback']['G1_self_consistency']}/"
                  f"G2={per_model['fallback']['G2_gold_accuracy']}），且 G3={G3}>="
                  f"{CROSS_AGREE_THRESHOLD}")
    else:
        decision = "no-go"
        reason = (f"primary_ok={primary_ok}, fallback_ok={fallback_ok}, g3_ok={g3_ok}；"
                  f"G1={G1}, G2={G2}, G3={G3} 未同时满足门禁")

    per_gold_breakdown = {
        g: {
            "n": v["n"],
            "g2_hit": v["g2_hit"],
            "g2_rate": round(v["g2_hit"] / v["n"], 4) if v["n"] else 0.0,
        } for g, v in per_gold.items()
    }

    summary = {
        "task": "memory_correctness",
        "primary": primary,
        "fallback": fallback,
        "repeats": repeats,
        "n_probes": len(MEMORY_PROBES),
        "gold_distribution": gold_distribution,
        "per_gold_breakdown": per_gold_breakdown,
        "G1_self_consistency": G1,
        "G2_gold_accuracy": G2,
        "G3_cross_agreement": G3,
        "G3_cross_agreement_n": len(g3_all),
        "thresholds": {
            "self_consistency": SELF_CONSISTENCY_THRESHOLD,
            "gold_accuracy": GOLD_ACC_THRESHOLD,
            "cross_agreement": CROSS_AGREE_THRESHOLD,
        },
        "per_model": per_model,
        "unavailable_rate": round(total_unavail / total_calls, 4) if total_calls else 0.0,
        "unavailable_total": total_unavail,
        "unavailable_calls": total_calls,
        "decision": decision,
        "decision_reason": reason,
        "gold_is_constructed_not_human": True,
        "gold_note": ("gold 为构造真值（constructed gold），由探针设计决定，"
                      "非真实人工标注；仅验证判官在该维度上的判别有效性下界。"),
        "records": records,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
