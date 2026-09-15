#!/usr/bin/env python3
"""内容正确性抽查：下载的 PDF 是否真的是那篇论文。

之前只校验了 ``%PDF-`` 魔数——那只能证明「是个 PDF」，不能证明「是对的那篇」。
这里抽取 PDF 首页文本，检查元数据里的标题是否真的出现在论文里。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

PAIRS = [
    ("/tmp/ccs_2024_enriched.jsonl", "/tmp/ccs_pdfs"),
    ("/tmp/ndss_2024_enriched.jsonl", "/tmp/ndss_pdfs"),
    ("/tmp/sp_2024_enriched.jsonl", "/tmp/sp_pdfs"),
    ("/tmp/ndss_2025_adapter.jsonl", "/tmp/ndss2025_pdfs"),
]
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def _normalize(text: str) -> str:
    """只保留字母数字，便于忽略换行/连字符/标点差异。"""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _title_words(title: str) -> list[str]:
    """取标题里最长的若干个实词作为匹配依据。"""
    cleaned = re.sub(r"<[^>]+>", "", title or "")  # Crossref 标题里有 <i> 之类标签
    words = [w for w in re.findall(r"[A-Za-z]{4,}", cleaned)]
    return sorted(set(w.lower() for w in words), key=len, reverse=True)[:6]


def check(jsonl: str, pdf_dir: str) -> tuple[int, int, list[str]]:
    meta = {}
    for line in Path(jsonl).open(encoding="utf-8"):
        row = json.loads(line)
        meta[row["doi"].replace("/", "_")] = row.get("title") or ""

    ok = fail = 0
    problems: list[str] = []
    files = sorted(Path(pdf_dir).glob("*.pdf"))[:SAMPLE]
    for path in files:
        stem = path.stem
        title = meta.get(stem, "")
        if not title:
            problems.append(f"{stem}: 元数据里找不到标题")
            fail += 1
            continue
        try:
            with pymupdf.open(path) as doc:
                first_page = doc[0].get_text() if len(doc) else ""
                if len(doc) < 2:  # 首页可能只有标题页
                    second = ""
                else:
                    second = doc[1].get_text()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{stem}: 打开失败 {type(exc).__name__}")
            fail += 1
            continue

        haystack = _normalize(first_page + second)
        words = _title_words(title)
        if not words:
            problems.append(f"{stem}: 标题无可用实词")
            fail += 1
            continue
        hits = sum(1 for w in words if w in haystack)
        ratio = hits / len(words)
        if ratio >= 0.6:
            ok += 1
            print(f"  OK   {stem}  命中 {hits}/{len(words)} 词  | {title[:52]}")
        else:
            fail += 1
            problems.append(f"{stem}: 标题命中仅 {hits}/{len(words)}（{title[:50]}）")
            print(f"  FAIL {stem}  命中 {hits}/{len(words)} 词  | {title[:52]}")
    return ok, fail, problems


def main() -> int:
    total_ok = total_fail = 0
    for jsonl, pdf_dir in PAIRS:
        if not Path(pdf_dir).exists():
            continue
        print(f"\n===== {Path(pdf_dir).name} =====")
        ok, fail, problems = check(jsonl, pdf_dir)
        total_ok += ok
        total_fail += fail
        for item in problems[:3]:
            print(f"    ! {item}")
    print(f"\n内容抽查: 匹配 {total_ok}，不匹配 {total_fail}")
    return 0 if total_fail == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
