#!/usr/bin/env python3
"""开发会话上下文占比分析（估算）。

扫描会被 CodeBuddy 开发会话自动加载 / 按需加载的本地文件，逐个给出：

- 文件大小（字节 / KB）
- 估算 token 数（CJK 启发式，非精确分词）
- 占上下文窗口的百分比

并单列「IDE 框架基座」（系统提示词 + 工具定义，由 IDE 注入、非文件），
最后汇总出「会话起始固定占用」来解释界面上看到的那个 12%（或 9%）。

token 估算：CJK 字 ~1.6 tok/字，其余字符 ~0.25 tok/字（4 字/tok）。
这是上界启发式，用于看**相对占比**，不要当绝对 token 数使用。

用法：
    .venv/bin/python scripts/context_breakdown.py
    .venv/bin/python scripts/context_breakdown.py --window 256000
    .venv/bin/python scripts/context_breakdown.py --base-tokens 6000
"""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- token 估算
_CJK_RE = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def estimate_tokens(text: str) -> int:
    """CJK 字 1.6 tok，其余字符 0.25 tok（上界启发式）。"""
    cjk = len(_CJK_RE.findall(text))
    other = max(len(text) - cjk, 0)
    return int(cjk * 1.6 + other * 0.25)


# ---------------------------------------------------------------- 数据模型
@dataclass
class Entry:
    name: str
    path: Path
    bytes: int
    tokens: int


@dataclass
class Group:
    title: str
    note: str
    entries: list[Entry]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _scan(root: Path) -> list[Group]:
    groups: list[Group] = []

    # 1) 自动加载的项目规则（AGENTS.md / CONTEXT.md 在仓库根）
    rule_entries: list[Entry] = []
    for name in ("AGENTS.md", "CONTEXT.md"):
        p = root / name
        if p.is_file():
            text = _read(p)
            rule_entries.append(Entry(name, p, p.stat().st_size, estimate_tokens(text)))
    if rule_entries:
        groups.append(Group(
            "自动加载 · 项目规则",
            "每个新会话都会注入，是起始固定占用的主要来源",
            rule_entries,
        ))

    # 2) 按需/懒加载：子代理定义
    agents_dir = root / ".codebuddy" / "agents"
    agent_entries: list[Entry] = []
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*.md")):
            text = _read(p)
            agent_entries.append(Entry(p.name, p, p.stat().st_size, estimate_tokens(text)))
    if agent_entries:
        groups.append(Group(
            "按需/懒加载 · 子代理定义",
            ".codebuddy/agents/*.md，仅被引用时加载，不计入起始固定占用",
            agent_entries,
        ))

    # 3) 按需/懒加载：技能定义
    skills_dir = root / ".codebuddy" / "skills"
    skill_entries: list[Entry] = []
    if skills_dir.is_dir():
        for p in sorted(skills_dir.rglob("SKILL.md")):
            text = _read(p)
            rel = p.relative_to(root)
            skill_entries.append(Entry(str(rel), p, p.stat().st_size, estimate_tokens(text)))
    if skill_entries:
        groups.append(Group(
            "按需/懒加载 · 技能定义",
            ".codebuddy/skills/*/SKILL.md，仅触发技能时加载",
            skill_entries,
        ))

    return groups


# ---------------------------------------------------------------- 展示
def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:6.1f} MB"
    if n >= 1024:
        return f"{n / 1024:6.1f} KB"
    return f"{n:6d} B "


def _pct(tokens: int, window: int) -> str:
    return f"{tokens / window * 100:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="开发会话上下文占比分析（估算）")
    ap.add_argument("--root", type=Path, default=None, help="仓库根目录（默认脚本上级目录）")
    ap.add_argument("--window", type=int, default=200_000, help="上下文窗口 token 数（默认 200000）")
    ap.add_argument("--base-tokens", type=int, default=5_000,
                    help="IDE 框架基座估算 token（系统提示词+工具定义，非文件，默认 5000）")
    args = ap.parse_args()

    root = args.root or Path(__file__).resolve().parent.parent
    window = max(args.window, 1)
    base = max(args.base_tokens, 0)

    groups = _scan(root)

    print("=" * 70)
    print("开发会话上下文占比（估算）")
    print(f"窗口假设: {window:,} token | token 估算: CJK 1.6 tok/字 + 其余 0.25 tok/字（启发式）")
    print("=" * 70)

    auto_loaded_tokens = 0
    for g in groups:
        print()
        print(f"[{g.title}]")
        print(f"  {g.note}")
        print(f"  {'文件':42} {'大小':>10} {'~token':>9} {'占窗口':>8}")
        subtok = 0
        for e in g.entries:
            subtok += e.tokens
            print(f"  {e.name[:42]:42} {_fmt_size(e.bytes):>10} {e.tokens:>9,} {_pct(e.tokens, window):>8}")
        if g.title.startswith("自动加载"):
            auto_loaded_tokens += subtok
        print(f"  {'— 小计 —':42} {'':>10} {subtok:>9,} {_pct(subtok, window):>8}")

    # IDE 框架基座（非文件）
    print()
    print("[IDE 框架基座（非文件，估算）]")
    print("  系统提示词 + 工具定义 + 指令集，由 IDE 注入，不在仓库里")
    print(f"  {'框架基座':42} {'—':>10} {base:>9,} {_pct(base, window):>8}")

    # 会话起始固定占用
    fixed = auto_loaded_tokens + base
    alt_window = 256_000
    print()
    print("=" * 70)
    print("会话起始固定占用（自动加载规则 + 框架基座）")
    print(f"  合计 ≈ {fixed:,} token")
    print(f"    占 {window:,} 窗口 = {fixed / window * 100:.1f}%")
    if alt_window != window:
        print(f"    占 {alt_window:,} 窗口 = {fixed / alt_window * 100:.1f}%")
    print()
    print("  说明：界面上看到的 12%（或 9%）即由这个固定基线决定；")
    print("  真实对话历史在此基础上叠加增长，基线本身几乎不变。")
    print("=" * 70)


if __name__ == "__main__":
    main()
