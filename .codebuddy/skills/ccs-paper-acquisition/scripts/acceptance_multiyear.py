#!/usr/bin/env python3
"""Task04 验收点「多年度/track」：三个适配器在多个年份上的真实表现。

只测过 2024 不足以说明适配器稳定——Crossref 每年的 container-title 措辞都在变
（例如 "Proceedings of the 2024 on ACM SIGSAC Conference..." 里多一个 "on"），
年份边界和相关性排序也可能翻车。这里逐年跑，记录记录数、摘要覆盖率与耗时。
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/Users/wjh/work/ResearchAgent-2/ResearchAgent")

from backend.app.paper_discovery.infrastructure.ccs_publication_source import (  # noqa: E402
    CcsPublicationSource,
)
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import (  # noqa: E402
    IeeeSpPublicationSource,
)
from backend.app.paper_discovery.infrastructure.ndss_publication_source import (  # noqa: E402
    NdssPublicationSource,
)

YEARS = [2022, 2023, 2024, 2025]


def run(name: str, source) -> None:
    print(f"\n===== {name} =====")
    for year in YEARS:
        started = time.time()
        try:
            result = source.sync_units({"years": [year]})
        except Exception as exc:  # noqa: BLE001
            print(f"  {year}: 异常 {type(exc).__name__}: {str(exc)[:70]}")
            continue
        elapsed = time.time() - started
        records = result.records
        with_abs = sum(1 for r in records if (getattr(r, "abstract", "") or "").strip())
        with_pdf = sum(1 for r in records if getattr(r, "pdf_url", None))
        print(
            f"  {year}: {elapsed:5.1f}s  记录={len(records):4d}  有摘要={with_abs:4d}  "
            f"有pdf={with_pdf:4d}  status={result.status}  failed={result.failed_years}  "
            f"warnings={len(result.warnings)}"
        )


if __name__ == "__main__":
    run("NDSS", NdssPublicationSource())
    run("CCS", CcsPublicationSource())
    run("IEEE S&P", IeeeSpPublicationSource())
