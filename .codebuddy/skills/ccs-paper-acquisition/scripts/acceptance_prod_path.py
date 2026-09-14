#!/usr/bin/env python3
"""spec-032 验收：用生产 ConferencePdfDownloader 跑真实 OA 记录。

目的：验证「发现 -> 富化 -> 生产下载器」这条真实链路，而不是只验证我写的
独立脚本 oa_pdf_fetch.py。走 download_batch()，公开层用 allowed_hosts 放开
arxiv.org，浏览器层留空（无 browser_manager）以确认降级不崩。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/wjh/work/ResearchAgent-2/ResearchAgent")
sys.path.insert(0, "/Users/wjh/work/ResearchAgent-2/ResearchAgent/backend")

from app.paper_discovery.infrastructure.conference_pdf_downloader import (  # noqa: E402
    ConferencePdfDownloader,
    classify_pdf_access,
)

SRC = Path("/tmp/ccs_2024_enriched.jsonl")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ALLOWED = ("arxiv.org",)


def main() -> int:
    records = [json.loads(line) for line in SRC.open(encoding="utf-8") if line.strip()]
    # 只挑 arXiv 且未被标记为受限的（对应生产里 classify 为 open_access 的那批）
    picked = [
        r
        for r in records
        if (r.get("pdf_url") or "").startswith("https://arxiv.org/")
        and not r.get("pdf_gated")
        and classify_pdf_access(r) == "open_access"
    ][:LIMIT]

    print(f"候选总数 {len(records)}，挑出 arXiv 可用 {len(picked)} 条\n")
    if not picked:
        return 1

    downloader = ConferencePdfDownloader(allowed_hosts=ALLOWED)
    batch = downloader.download_batch(picked)

    ok = 0
    for outcome in batch.outcomes:
        if outcome.ok:
            ok += 1
            print(
                f"OK   {outcome.identity[:42]:<42} layer={outcome.layer:<12} "
                f"{outcome.file_size or 0:>10,}B  {outcome.url}"
            )
        else:
            print(
                f"FAIL {outcome.identity[:42]:<42} code={outcome.error_code:<26} "
                f"{outcome.reason}  attempts={outcome.attempts}"
            )

    print(f"\n生产路径结果: ok={ok}/{len(picked)}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
