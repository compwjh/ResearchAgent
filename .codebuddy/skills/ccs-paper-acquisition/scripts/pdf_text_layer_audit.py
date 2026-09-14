#!/usr/bin/env python3
"""文本层审计：PDF 内容是对的，但能不能被检索到是另一回事。

内容校验（pdf_content_check.py）证明「下载的是对的那一篇」；
本脚本证明「这一篇能被抽取文本」——扫描件/纯图片 PDF 内容完全正确，
但入库后 RAG 会静默抽不出任何文字，和「下错论文」一样是静默故障。

判定：每页平均可抽取字符数低于阈值 => 疑似无文本层（扫描件）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

#: 默认按仓库既有产物路径审计；可用命令行参数覆盖为任意 PDF 目录。
DIRS = [
    ("/tmp/ccs_pdfs", "CCS 2024"),
    ("/tmp/ndss_pdfs", "NDSS 2024"),
    ("/tmp/ndss2025_pdfs", "NDSS 2025"),
    ("/tmp/sp_pdfs", "S&P 2024"),
]
if len(sys.argv) > 1:
    DIRS = [(a, Path(a).name) for a in sys.argv[1:]]
CHARS_PER_PAGE_THRESHOLD = 120  # 经验阈值：远低于正常论文（通常 >1500/页）


def audit(pdf_dir: str) -> tuple[int, int, list[tuple[str, int, int, float]]]:
    ok = 0
    suspicious: list[tuple[str, int, int, float]] = []
    for path in sorted(Path(pdf_dir).glob("*.pdf")):
        try:
            with pymupdf.open(path) as doc:
                pages = len(doc)
                text = "".join(page.get_text() for page in doc)
        except Exception as exc:  # noqa: BLE001
            suspicious.append((path.stem, 0, 0, 0.0))
            continue
        per_page = len(text.strip()) / pages if pages else 0
        if per_page < CHARS_PER_PAGE_THRESHOLD:
            suspicious.append((path.stem, pages, len(text.strip()), per_page))
        else:
            ok += 1
    return ok, len(suspicious), suspicious


def main() -> int:
    total_ok = total_bad = 0
    for pdf_dir, label in DIRS:
        directory = Path(pdf_dir)
        if not directory.exists():
            continue
        total = len(list(directory.glob("*.pdf")))
        ok, bad, suspicious = audit(pdf_dir)
        total_ok += ok
        total_bad += bad
        print(f"{label:<12} 共 {total:4d} 篇  有文本层 {ok:4d}  疑似扫描件 {bad}")
        for stem, pages, chars, per_page in suspicious[:5]:
            print(f"    ! {stem}  页数={pages}  可抽取字符={chars}  每页={per_page:.0f}")
    total = total_ok + total_bad
    pct = (total_bad * 100 / total) if total else 0
    print(f"\n合计 {total} 篇：有文本层 {total_ok}，疑似扫描件 {total_bad}（{pct:.1f}%）")
    return 0 if total_bad == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
