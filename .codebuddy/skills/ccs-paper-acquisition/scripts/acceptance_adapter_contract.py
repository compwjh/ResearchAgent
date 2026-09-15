#!/usr/bin/env python3
"""spec-032 Task02「Source Adapter 合同」符合性检查。

Task02 在计划里仍是「待执行」，但它是 Task03/04/05/06 的依赖。
这里用运行时检查给出可判定证据：三个适配器是否都满足合同要求的成员与语义。
"""
from __future__ import annotations

import inspect
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

REQUIRED_ATTRS = ["source_id", "authority_rank"]
REQUIRED_METHODS = [
    "discover_units",
    "fetch_unit",
    "parse_catalog",
    "normalize_identity",
    "health",
]

print(f"{'检查项':<26}{'NDSS':<12}{'CCS':<12}{'S&P':<12}")
sources = [("NDSS", NdssPublicationSource()), ("CCS", CcsPublicationSource()), ("S&P", IeeeSpPublicationSource())]


def row(label: str, values: list[str]) -> None:
    print(f"{label:<26}" + "".join(f"{v:<12}" for v in values))


# 1. 必需属性
for attr in REQUIRED_ATTRS:
    row(f"属性 {attr}", [str(getattr(s, attr, "缺失")) for _, s in sources])

# 2. 必需方法（可调用）
for method in REQUIRED_METHODS:
    row(f"方法 {method}()", ["✓" if callable(getattr(s, method, None)) else "缺失" for _, s in sources])

# 3. source_id 全局唯一
ids = [s.source_id for _, s in sources]
row("source_id 唯一", ["✓" if len(set(ids)) == len(ids) else "重复"] + ["", ""])
print(f"  source_id 取值: {ids}")

# 4. health() 无副作用/无网络：可重复调用且结果稳定
health_stable = []
for _, s in sources:
    try:
        a = s.health()
        b = s.health()
        health_stable.append("✓" if a == b and isinstance(a, dict) else "不稳定")
    except Exception:  # noqa: BLE001
        health_stable.append("异常")
row("health() 幂等", health_stable)

# 5. normalize_identity：同一 DOI 稳定、DOI 优先于标题
stable = []
for _, s in sources:
    try:
        rec = type("R", (), {"doi": "10.1000/xyz", "title": "Some Title", "year": 2024})()
        first = s.normalize_identity(rec)
        rec2 = type("R", (), {"doi": "10.1000/xyz", "title": "Different", "year": 2024})()
        stable.append("✓" if first == s.normalize_identity(rec2) and "doi:" in str(first) else str(first)[:10])
    except Exception as exc:  # noqa: BLE001
        stable.append(f"异常:{type(exc).__name__}")
row("normalize_identity 稳定", stable)

# 6. discover_units 签名
sigs = []
for _, s in sources:
    try:
        sigs.append(str(inspect.signature(s.discover_units)))
    except (TypeError, ValueError):
        sigs.append("?")
print("\ndiscover_units 签名:")
for (name, _), sig in zip(sources, sigs):
    print(f"  {name:<6}{sig}")

# 7. 字段级 provenance：富化后记录应带 provenance 映射
print("\n字段级 provenance（需联网，取 2024 前 3 条）:")
for name, s in sources:
    try:
        result = s.sync_units({"years": [2024]})
        samples = list(result.records)[:3]
        prov = [sorted((getattr(r, "provenance", None) or {}).keys()) for r in samples]
        print(f"  {name:<6}{prov}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {name:<6}异常 {type(exc).__name__}: {str(exc)[:60]}")
