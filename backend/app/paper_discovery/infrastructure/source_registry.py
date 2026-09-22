"""Spec032 Task05：服务端受控的来源注册表（SourceRegistry）。

来源装配从此前的「类常量手工 new」改为集中注册：枚举所有启用来源并暴露
``source_id`` / ``source_kind`` / ``authority_rank`` / ``enabled`` / ``allowed_hosts``
/ 能力（discover_units / sync）/ 缓存范围。注册表自身不发起网络请求、不做抓取，
只作为「哪些来源可用、各自权威级别与可访问主机」的单一事实来源。

服务端配置关闭：构造时可由服务端传入 ``disabled_by_config``（一组 source_id）来关闭
默认启用的来源（例如只信任官方会议目录、关闭聚合来源）。但**内置必需源**
（见 ``REQUIRED_SOURCE_IDS`` 注释）不允许通过外部输入（HTTP 层）随意开关——调用
``set_enabled(..., via_external=True)`` 关闭/启用它们会抛 ``SourceToggleForbiddenError``，
HTTP 层应将其映射为 409。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATE,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    canonical_source_id,
)


class SourceToggleForbiddenError(RuntimeError):
    """尝试通过外部输入开关内置必需源；HTTP 层应映射为 409。"""

    def __init__(self, source_id: str, *, code: str = "SOURCE_TOGGLE_FORBIDDEN") -> None:
        super().__init__(f"内置必需来源 {source_id!r} 不允许通过外部输入开关")
        self.source_id = source_id
        self.code = code


@dataclass(frozen=True)
class SourceEntry:
    source_id: str
    source_kind: str
    authority_rank: int
    enabled: bool
    allowed_hosts: Tuple[str, ...] = ()
    capabilities: Tuple[str, ...] = ("discover_units", "sync")
    cache_scope: str = "year"
    required: bool = False  # 内置必需源：不允许外部输入开关
    verified_years: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", canonical_source_id(self.source_id))
        object.__setattr__(self, "source_kind", canonical_source_id(self.source_kind))

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "authority_rank": self.authority_rank,
            "enabled": self.enabled,
            "allowed_hosts": list(self.allowed_hosts),
            "capabilities": list(self.capabilities),
            "cache_scope": self.cache_scope,
            "required": self.required,
            "verified_years": list(self.verified_years),
        }


# 内置必需源：系统核心依赖的官方会议目录 + DBLP。聚合来源（openalex/crossref）虽默认启用，
# 但属「可配置关闭」的增强来源，不由本集合保护——尝试外部关闭/启用必需源会返回 409。
# 服务端配置（构造期 ``disabled_by_config``）可以关闭包括必需源在内的任何来源，因为那是
# 受信任的运维决策；只有逐请求的外部输入受本集合约束。
REQUIRED_SOURCE_IDS = frozenset({"usenix", "dblp", "ieee_sp", "ccs", "ndss"})

# Publication-stage fallbacks are not independent catalog sources, but their
# hosts are still fixed server-side trust decisions when a source candidate
# explicitly selects one (for example USENIX → arXiv).
_FALLBACK_DOWNLOAD_HOSTS: dict[str, Tuple[str, ...]] = {
    "arxiv": ("arxiv.org", "export.arxiv.org"),
    "usenix_accepted": ("www.usenix.org",),
}


def builtin_allowed_hosts(source_id: str) -> Tuple[str, ...]:
    """Return the fixed download hosts declared by a built-in source.

    Download callers must not derive trust from a persisted candidate URL.  This
    small accessor lets the import boundary reuse the registry's source
    authority declaration instead of maintaining a second, drifting host map.
    Unknown source ids deliberately return an empty tuple (fail closed).
    """
    raw = str(source_id or "").strip().casefold()
    fallback = _FALLBACK_DOWNLOAD_HOSTS.get(raw)
    if fallback is not None:
        return fallback
    try:
        canonical = canonical_source_id(raw, strict=True)
    except (TypeError, ValueError):
        return ()
    return next(
        (entry.allowed_hosts for entry in _builtin_entries() if entry.source_id == canonical),
        (),
    )

def _builtin_entries() -> List[SourceEntry]:
    return [
        SourceEntry("usenix", "usenix", AUTHORITY_OFFICIAL_VENUE, True,
                    ("www.usenix.org",), ("discover_units", "sync"), "year", True, tuple(range(2022, 2027))),
        SourceEntry("dblp", "dblp", AUTHORITY_OFFICIAL_VENUE, True,
                    ("dblp.org",), ("discover_units", "sync"), "year", True),
        # These adapters currently enumerate publisher/member DOI metadata;
        # they must not inherit the future official-venue rank merely from the
        # conference label.  Task07 may add an official-page path later.
        SourceEntry("ieee_sp", "ieee_sp", AUTHORITY_OFFICIAL_DOI, True,
                    ("ieeexplore.ieee.org", "doi.org"), ("discover_units", "sync"), "year", True, (2024,)),
        SourceEntry("ccs", "ccs", AUTHORITY_OFFICIAL_DOI, True,
                    ("dl.acm.org", "doi.org"), ("discover_units", "sync"), "year", True),
        # 2024 is a bounded official-page sample, not a claim of 2021–2025 full coverage.
        SourceEntry("ndss", "ndss", AUTHORITY_OFFICIAL_DOI, True,
                    ("www.ndss-symposium.org", "doi.org"), ("discover_units", "sync"), "year", True, (2024,)),
        # 聚合来源：默认启用但可被服务端配置关闭（非必需源）。
        SourceEntry("openalex", "openalex", AUTHORITY_AGGREGATE, True,
                    ("api.openalex.org",), ("discover_units", "sync"), "global", False),
        SourceEntry("crossref", "crossref", AUTHORITY_OFFICIAL_DOI, True,
                    ("api.crossref.org",), ("discover_units", "sync"), "global", False),
    ]


class SourceRegistry:
    """服务端受控的来源注册表。

    构造参数 ``disabled_by_config`` 为受信任的服务端配置（一组 source_id），可在启动期
    关闭默认启用的来源。运行时对单个来源的开关通过 ``set_enabled`` 完成；其中对内置必需源
    的开关必须使用 ``via_external=False``（服务端内部），外部 HTTP 层须传 ``via_external=True``，
    否则抛 ``SourceToggleForbiddenError``（→ 409）。
    """

    def __init__(self, disabled_by_config: Iterable[str] = (), *, store: Any = None,
                 timeout: float = 20.0) -> None:
        disabled = {canonical_source_id(value) for value in disabled_by_config}
        self._entries: dict[str, SourceEntry] = {}
        self._adapters: dict[str, Any] = {}
        self._store = store
        self._timeout = float(timeout)
        for entry in _builtin_entries():
            enabled = entry.enabled and entry.source_id not in disabled
            self._entries[entry.source_id] = SourceEntry(
                entry.source_id, entry.source_kind, entry.authority_rank,
                enabled, entry.allowed_hosts, entry.capabilities, entry.cache_scope, entry.required,
                entry.verified_years,
            )

    def get(self, source_id: str) -> Optional[SourceEntry]:
        return self._entries.get(canonical_source_id(source_id))

    def list_all(self) -> List[SourceEntry]:
        return list(self._entries.values())

    def list_by_kind(self, source_kind: str) -> List[SourceEntry]:
        canonical = canonical_source_id(source_kind)
        return [e for e in self._entries.values() if e.source_kind == canonical]

    def list_enabled(self) -> List[SourceEntry]:
        return [e for e in self._entries.values() if e.enabled]

    def set_enabled(self, source_id: str, enabled: bool, *, via_external: bool = False) -> SourceEntry:
        canonical = canonical_source_id(source_id)
        entry = self._entries.get(canonical)
        if entry is None:
            raise KeyError(source_id)
        if via_external and entry.required:
            raise SourceToggleForbiddenError(source_id)
        self._entries[canonical] = SourceEntry(
            entry.source_id, entry.source_kind, entry.authority_rank,
            enabled, entry.allowed_hosts, entry.capabilities, entry.cache_scope, entry.required,
            entry.verified_years,
        )
        return self._entries[canonical]

    def adapter(self, source_id: str, *, store: Any = None, timeout: float | None = None) -> Any:
        """Return the real, cached adapter for a registered source.

        Construction is deliberately lazy: importing/creating the registry does not
        touch the network or create a second cache.  All seven adapters are existing
        source implementations; this method is only their composition seam.
        """
        canonical = canonical_source_id(source_id, strict=True)
        entry = self._entries.get(canonical)
        if entry is None:
            raise KeyError(source_id)
        if canonical in self._adapters:
            return self._adapters[canonical]
        actual_store = store if store is not None else self._store
        actual_timeout = self._timeout if timeout is None else float(timeout)
        if canonical == "usenix":
            from backend.app.paper_discovery.infrastructure.usenix_publication_source import UsenixAcceptedSource
            if actual_store is None:
                from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
                actual_store = PaperDiscoveryStore()
            adapter = UsenixAcceptedSource(timeout=actual_timeout, store=actual_store)
        elif canonical == "dblp":
            from backend.app.paper_discovery.infrastructure.dblp_publication_source import DBLPPublicationSource
            adapter = DBLPPublicationSource(timeout=actual_timeout)
        elif canonical == "ieee_sp":
            from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import IeeeSpPublicationSource
            adapter = IeeeSpPublicationSource(timeout=actual_timeout)
        elif canonical == "ccs":
            from backend.app.paper_discovery.infrastructure.ccs_publication_source import CcsPublicationSource
            adapter = CcsPublicationSource(timeout=actual_timeout)
        elif canonical == "ndss":
            from backend.app.paper_discovery.infrastructure.ndss_publication_source import NdssPublicationSource
            adapter = NdssPublicationSource(timeout=actual_timeout)
        elif canonical == "openalex":
            from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import OpenAlexCatalogAdapter
            adapter = OpenAlexCatalogAdapter(timeout=actual_timeout)
        elif canonical == "crossref":
            from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import CrossrefCatalogAdapter
            adapter = CrossrefCatalogAdapter(timeout=actual_timeout)
        else:  # pragma: no cover - guarded by canonical source ids
            raise KeyError(source_id)
        self._adapters[canonical] = adapter
        return adapter

    # Explicit aliases make the seam discoverable to application code and tests.
    get_adapter = adapter

    def adapters(self, *, store: Any = None, timeout: float | None = None,
                 enabled_only: bool = True) -> dict[str, Any]:
        entries = self.list_enabled() if enabled_only else self.list_all()
        return {entry.source_id: self.adapter(entry.source_id, store=store, timeout=timeout)
                for entry in entries}


__all__ = [
    "REQUIRED_SOURCE_IDS",
    "SourceEntry",
    "SourceRegistry",
    "SourceToggleForbiddenError",
]
