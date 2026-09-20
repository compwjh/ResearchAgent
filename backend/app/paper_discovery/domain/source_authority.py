"""Spec032 来源权威级别与 source_kind 枚举（唯一事实来源）。

权威方向（**全局唯一**）：**数值越小，权威越高**。
- ``AUTHORITY_OFFICIAL_VENUE = 10``：会议官方目录（如 USENIX accepted papers、
  DBLP 会议流、IEEE S&P / ACM CCS / NDSS 官方会议列表）。
- ``AUTHORITY_OFFICIAL_DOI  = 20``：出版方/学会自提交到 Crossref 的官方 DOI 元数据
  （ACM/IEEE/Internet Society member 记录的标题、作者、年份、DOI、容器、官方页面）。
- ``AUTHORITY_AGGREGATE     = 30``：聚合书目来源（OpenAlex，以及未来明确标注为聚合
  富化的来源记录）。Crossref publisher/member DOI metadata 使用 ``20``，不会因为
  会议过滤而自动获得官方会议目录的 ``10``。

所有「高权威覆盖低权威」的合并逻辑都必须基于这一方向：只有 ``incoming_rank < base_rank``
（incoming 数值更小 = 更权威）才允许覆盖 base 的已存在字段。禁止再出现第二套
「数值越大越权威」的反向判定——此前三会议 parser 用的是 3/2/1，与聚合 adapter 的
10/20/30 方向相反，已在 Task05 统一为上述方向。
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping

# 权威级别：数值越小越权威。
AUTHORITY_OFFICIAL_VENUE = 10
AUTHORITY_OFFICIAL_DOI = 20
AUTHORITY_AGGREGATE = 30
#: 兼容别名：三会议 parser 沿用 ``AUTHORITY_AGGREGATOR`` 这一命名（与聚合 adapter 的
#: ``AUTHORITY_AGGREGATE`` 指向同一数值，避免再出现两套方向相反的常量）。
AUTHORITY_AGGREGATOR = AUTHORITY_AGGREGATE


class SourceKind(str, Enum):
    """已注册来源的种类（与 ``SourceRegistry`` 对齐）。

    既是 ``search_source_progress`` 等表的 CHECK 约束取值来源，也是各 parser /
    adapter 的 ``source_kind`` 取值。新增来源必须在此登记，禁止在别处再硬编码一套
    种类字符串集合。
    """

    USENIX = "usenix"
    DBLP = "dblp"
    IEEE_SP = "ieee_sp"
    CCS = "ccs"
    NDSS = "ndss"
    OPENALEX = "openalex"
    CROSSREF = "crossref"


#: ``source_kind`` 的全部合法取值（CHECK 约束与注册表共用）。
SOURCE_KINDS: frozenset[str] = frozenset(kind.value for kind in SourceKind)

# Source IDs are persisted in fetch units, source records and field provenance.  Keep
# this list independent from ``SourceKind``'s implementation details so callers can
# validate an external source ID without accepting arbitrary URL/host input.
CANONICAL_SOURCE_IDS: frozenset[str] = frozenset(SOURCE_KINDS)

# Task05 adapters shipped two spellings before the cross-source contract was frozen.
# They remain readable, but all new writes and public projections use the canonical
# spellings below.  ``ieee_sp`` is intentionally both a canonical ID and an alias of
# itself so callers can normalize values without a special case.
SOURCE_ID_ALIASES: Mapping[str, str] = {
    "usenix": "usenix",
    "dblp": "dblp",
    "ieee_sp": "ieee_sp",
    "ieee-sp": "ieee_sp",
    "ccs": "ccs",
    "acm_ccs": "ccs",
    "acm-ccs": "ccs",
    "ndss": "ndss",
    "openalex": "openalex",
    "crossref": "crossref",
}

#: 来源 id → 权威级别（默认；聚合来源以聚合待之）。
DEFAULT_SOURCE_AUTHORITY: Mapping[str, int] = {
    # Official venue records: only sources whose current adapter is backed by an
    # official venue directory receive this rank.  IEEE S&P, CCS and NDSS are
    # currently enumerated through Crossref DOI metadata; they must remain at the
    # DOI rank until their official-page adapters are actually enabled.
    "usenix": AUTHORITY_OFFICIAL_VENUE,
    "dblp": AUTHORITY_OFFICIAL_VENUE,
    "ieee_sp": AUTHORITY_OFFICIAL_DOI,
    "ccs": AUTHORITY_OFFICIAL_DOI,
    "ndss": AUTHORITY_OFFICIAL_DOI,
    # Crossref publisher/member metadata is authoritative DOI metadata, while
    # OpenAlex is an aggregate enrichment source.
    "crossref": AUTHORITY_OFFICIAL_DOI,
    "openalex": AUTHORITY_AGGREGATE,
}

#: 未知来源按最高权威（最小数值）处理：宁可少写一次，也不可被未知来源覆盖官方字段。
UNKNOWN_SOURCE_AUTHORITY = AUTHORITY_OFFICIAL_VENUE


def canonical_source_id(source_id: object, *, strict: bool = False) -> str:
    """Return the stable source ID for a stored or request-supplied value.

    ``strict=True`` is for boundaries that accept a source selector (for example a
    planner or API); it rejects unknown values instead of silently treating an
    arbitrary string as a source.  Internal provenance reads use the default
    non-strict mode so historical/extension IDs remain observable and are assigned
    the fail-closed unknown authority rank.
    """
    value = str(source_id or "").strip().casefold()
    canonical = SOURCE_ID_ALIASES.get(value)
    if canonical is None:
        if strict:
            raise ValueError(f"unknown source id: {value or '<empty>'}")
        return value
    return canonical


def authority_rank_for(source_id: object) -> int:
    """Resolve the rank for a source ID after applying controlled aliases."""
    return DEFAULT_SOURCE_AUTHORITY.get(canonical_source_id(source_id), UNKNOWN_SOURCE_AUTHORITY)


def may_overwrite(existing_source_id: str | None, incoming_source_id: str) -> bool:
    """字段级 provenance 合并门禁：incoming 是否允许写入 base 的该字段。

    - 字段尚无归属来源（``existing_source_id is None``）→ 始终可写。
    - 仅当 ``incoming`` **严格比** ``existing`` 更权威（数值更小）时才允许覆盖。
    - 未知来源按最高权威对待，因此任何已知来源都**不能**覆盖未知的既有值。

    方向唯一：使用 ``incoming < existing``（数值越小越权威）。
    """
    if existing_source_id is None:
        return True
    existing = authority_rank_for(existing_source_id)
    incoming = authority_rank_for(incoming_source_id)
    return incoming < existing


__all__ = [
    "AUTHORITY_AGGREGATE",
    "AUTHORITY_AGGREGATOR",
    "AUTHORITY_OFFICIAL_DOI",
    "AUTHORITY_OFFICIAL_VENUE",
    "CANONICAL_SOURCE_IDS",
    "DEFAULT_SOURCE_AUTHORITY",
    "SOURCE_ID_ALIASES",
    "SOURCE_KINDS",
    "SourceKind",
    "UNKNOWN_SOURCE_AUTHORITY",
    "authority_rank_for",
    "canonical_source_id",
    "may_overwrite",
]
