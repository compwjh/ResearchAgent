#!/usr/bin/env python3
"""用**生产适配器**（不是我的独立脚本）跑真实数据。

前面所有验收都用 .codebuddy/skills 下的独立脚本，验证不了 spec-032 Task04 的交付物。
这里直接实例化三个生产 Source Adapter，走 discover_units -> sync_units 真实网络。
"""
from __future__ import annotations

import sys

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

YEAR = 2024


def run(name: str, source: object) -> None:
    print(f"\n===== {name}  source_id={source.source_id} =====")
    try:
        print("health():", source.health())
    except Exception as exc:  # noqa: BLE001
        print(f"  health() 异常: {type(exc).__name__}: {exc}")
    try:
        units = source.discover_units({"years": [YEAR]})
        print(f"discover_units -> {len(units)} 个单元: {[u.fetch_unit_id for u in units][:5]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  discover_units 异常: {type(exc).__name__}: {exc}")
        return
    try:
        result = source.sync_units({"years": [YEAR]})
    except Exception as exc:  # noqa: BLE001
        print(f"  sync_units 异常: {type(exc).__name__}: {str(exc)[:120]}")
        return
    print(f"status={result.status}  records={len(result.records)}  failed_years={result.failed_years}")
    if result.warnings:
        print(f"warnings: {list(result.warnings)[:3]}")
    for record in list(result.records)[:3]:
        print(
            f"  - doi={getattr(record, 'doi', None)} "
            f"| abstract={'有' if getattr(record, 'abstract', None) else '无'} "
            f"| pdf={'有' if getattr(record, 'pdf_url', None) else '无'} "
            f"| {str(getattr(record, 'title', ''))[:45]}"
        )


if __name__ == "__main__":
    run("NDSS", NdssPublicationSource())
    run("CCS", CcsPublicationSource())
    run("IEEE S&P", IeeeSpPublicationSource())
