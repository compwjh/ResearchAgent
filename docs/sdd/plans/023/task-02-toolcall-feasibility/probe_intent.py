"""spec-023 Task02 探测脚本 B — Skill 意图识别准确率。

对 20 条用户消息（10 条期望命中某个 Skill、10 条期望不命中任何 Skill）跑两轮：
- B-rule : 纯规则/关键词匹配（Task06 会用的第一条触发途径），零模型成本，确定性基线
- B-llm-t2: LLM 意图识别，**2 选 1**（先判是否需要 Skill，再判是哪个），输出受控 JSON
- B-llm-t3: LLM 意图识别，**3 选 1**（none / usenix-paper-catalog-search / usenix-accepted-papers）单次调用

输出误判数与误判率。LLM 调用统一 think=False。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

BASE_URL = "http://192.168.31.180:11434"
MODEL = "qwen3.8:27b-mlx"
CHAT_URL = f"{BASE_URL}/api/chat"

OUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUT_DIR / "raw" / "intent"
RAW_DIR.mkdir(parents=True, exist_ok=True)

SKILL_CATALOG = "usenix-paper-catalog-search"
SKILL_DOWNLOAD = "usenix-accepted-papers"
SKILLS = [SKILL_CATALOG, SKILL_DOWNLOAD]
NONE = "none"

# (id, 用户消息, 期望 skill 或 none)
CASES: list[tuple[str, str, str]] = [
    # ---- 期望命中 Skill（10） ----
    ("P01-explicit-full-name", "使用 usenix-paper-catalog-search 技能，检索 2024 年 USENIX Security 的 fuzzing 论文。", SKILL_CATALOG),
    ("P02-explicit-short-name", "帮我用 usenix-accepted-papers 技能，把选中的论文下载并导入知识库。", SKILL_DOWNLOAD),
    ("P03-explicit-chinese", "请使用「检索技能」搜索 2023 年 USENIX Security 隐私方向论文。", SKILL_CATALOG),
    ("P04-year-keyword", "找一下 USENIX Security 2024 accepted papers 里关于模糊测试的论文。", SKILL_CATALOG),
    ("P05-accepted-page", "列出 USENIX Security 2022 年接受论文的元数据，我要按方向筛。", SKILL_CATALOG),
    ("P06-import-request", "把 search-abc 里 catalog_paper_id=42 那篇论文下载并导入我的知识库。", SKILL_DOWNLOAD),
    ("P07-prepublication", "这篇 USENIX 的 prepublication PDF 能帮我验证并导入吗？", SKILL_DOWNLOAD),
    ("P08-dblp-meta", "帮我从 DBLP 补齐 2021 年 USENIX Security 论文的 DOI 信息。", SKILL_CATALOG),
    ("P09-batch-import", "把刚才选中的 5 篇论文批量导入知识库，失败的要能恢复。", SKILL_DOWNLOAD),
    ("P10-skill-name-literal", "usenix-paper-catalog-search：搜索 2025 年 USENIX Security 供应链安全论文。", SKILL_CATALOG),
    # ---- 期望不命中 Skill（10） ----
    ("N01-greeting", "你好，你能做什么？", NONE),
    ("N02-self-intro", "介绍一下你自己。", NONE),
    ("N03-general-qa", "TCP 三次握手为什么需要三次？", NONE),
    ("N04-code-help", "帮我写一个 Python 函数，把列表倒序输出。", NONE),
    ("N05-other-conf", "帮我查一下 CCS 2024 有哪些论文。", NONE),
    ("N06-vague-search", "我想找点论文看看。", NONE),
    ("N07-typo-skill", "帮我用 usenix-papper-catalog-search 搜论文。", NONE),
    ("N08-disabled-topic", "今天天气怎么样？", NONE),
    ("N09-meta-admin", "页面上的 Skill 开关是怎么存的？", NONE),
    ("N10-weak-mention", "我听说过 usenix-paper-catalog-search 这个东西。", NONE),
]

# 规则匹配用关键词（Task06 的第一条触发途径的近似实现）
RULE_SKILL_PATTERNS = [
    r"usenix-paper-catalog-search",
    r"usenix-accepted-papers",
    r"检索技能",
    r"搜索技能",
    r"下载技能",
    r"导入技能",
    r"usenix\s*security",
    r"usenix",
    r"accepted\s*papers?",
    r"prepublication",
    r"dblp",
    r"知识库",
    r"catalog_paper_id",
]
RULE_DOWNLOAD_PATTERNS = [
    r"usenix-accepted-papers",
    r"下载",
    r"导入",
    r"prepublication",
    r"catalog_paper_id",
    r"批量导入",
]


def rule_classify(text: str) -> str:
    low = text.lower()
    if any(re.search(p, low) for p in RULE_DOWNLOAD_PATTERNS):
        if any(re.search(p, low) for p in [r"usenix-accepted-papers", r"下载", r"导入", r"prepublication", r"catalog_paper_id"]):
            return SKILL_DOWNLOAD
    if any(re.search(p, low) for p in RULE_SKILL_PATTERNS):
        return SKILL_CATALOG
    return NONE


def build_prompt(text: str, three_way: bool) -> list[dict]:
    if three_way:
        options = (
            f'- "{SKILL_CATALOG}"：检索 USENIX Security 论文目录元数据（不下载 PDF）\n'
            f'- "{SKILL_DOWNLOAD}"：对已选定论文做 PDF 验证、下载与知识库导入\n'
            f'- "{NONE}"：不需要任何 Skill（寒暄、通用问答、其他会议、其他技能名等）'
        )
        instruction = f"只能输出下列之一的 name 值：{SKILL_CATALOG} / {SKILL_DOWNLOAD} / {NONE}"
    else:
        options = (
            f'- "yes"：需要调用 {SKILL_CATALOG} 或 {SKILL_DOWNLOAD}\n'
            '- "no"：不需要任何 Skill'
        )
        instruction = '只能输出 "yes" 或 "no"'
    system = (
        "你是 ResearchAgent 的 Skill 路由分类器。\n"
        f"可用 Skill：\n{options}\n\n"
        "判断规则：\n"
        "1) 用户消息中出现完整无误的 Skill 名，或明确要求检索 USENIX Security 论文目录 → 命中对应 Skill。\n"
        "2) 明确要求下载/导入已选定论文 → 命中下载 Skill。\n"
        "3) 仅提到相似词、拼写错误、其他会议、闲聊、通用问答 → none。\n\n"
        f"{instruction}。只输出 JSON，不要解释：\n"
        '{"reason": "<20字以内>", "name": "<值>"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


def llm_classify(client: httpx.Client, text: str, three_way: bool) -> tuple[str, dict, float]:
    payload = {
        "model": MODEL,
        "messages": build_prompt(text, three_way),
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    started = time.perf_counter()
    resp = client.post(CHAT_URL, json=payload, timeout=300.0)
    elapsed = time.perf_counter() - started
    content = (resp.json().get("message") or {}).get("content", "") if resp.status_code == 200 else ""
    raw = {"http_status": resp.status_code, "content": content, "elapsed_s": round(elapsed, 2)}
    if not three_way:
        # 二选一：先把 yes/no 判出来，yes 再走一次三选一
        m = re.search(r'"?(yes|no)"?', content, re.I)
        verdict = SKILLS[0] if m and m.group(1).lower() == "yes" else NONE
        if verdict == NONE:
            return NONE, raw, elapsed
        second, raw2, elapsed2 = llm_classify(client, text, three_way=True)
        raw["second_stage"] = raw2
        return second, raw, elapsed + elapsed2
    try:
        parsed = json.loads(content)
        name = str(parsed.get("name", "")).strip()
    except Exception:
        name = ""
    name = re.sub(r'^["\']|["\']$', "", name).strip()
    if name not in SKILLS + [NONE]:
        name = f"INVALID:{name}" if name else "INVALID:empty"
    return name, raw, elapsed


def main() -> int:
    results = {"model": MODEL, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": []}
    with httpx.Client(trust_env=False, timeout=300.0) as client:
        for cid, text, expected in CASES:
            rows = {"id": cid, "text": text, "expected": expected}
            rule_pred = rule_classify(text)
            rows["B-rule"] = rule_pred
            rows["B-rule_ok"] = rule_pred == expected
            print(f"[{cid}] rule={rule_pred} exp={expected} {'OK' if rows['B-rule_ok'] else 'MISS'}", flush=True)

            for mode, three in (("B-llm-t2", False), ("B-llm-t3", True)):
                try:
                    pred, raw, elapsed = llm_classify(client, text, three)
                except Exception as exc:  # noqa: BLE001
                    pred, raw, elapsed = f"ERROR:{type(exc).__name__}", {"error": str(exc)}, 0.0
                rows[mode] = pred
                rows[f"{mode}_ok"] = pred == expected
                rows[f"{mode}_elapsed_s"] = round(elapsed, 2)
                raw_path = RAW_DIR / f"{cid}.{mode}.json"
                raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"    {mode}={pred} {'OK' if rows[f'{mode}_ok'] else 'MISS'} ({elapsed:.2f}s)", flush=True)
            results["cases"].append(rows)

    n = len(results["cases"])
    for mode in ("B-rule", "B-llm-t2", "B-llm-t3"):
        ok = sum(1 for r in results["cases"] if r[f"{mode}_ok"])
        results[f"{mode}_summary"] = {
            "correct": ok,
            "total": n,
            "error_rate": round((n - ok) / n, 4),
            "avg_elapsed_s": round(
                sum(r.get(f"{mode}_elapsed_s", 0) for r in results["cases"]) / n, 2
            ),
        }
        print(f"{mode}: {ok}/{n} correct, error_rate={results[f'{mode}_summary']['error_rate']}")

    (OUT_DIR / "result_intent.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
