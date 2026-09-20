"""论文人类可读展示名。

研究结构里只存 ``catalog_paper_id``（Spec027 复用接缝：论文元数据不得进入 research
结构）。但 UI 上直接显示 16/32 位哈希对人毫无意义，所以展示层在这里按需把 ID 投影成
``年份_会议刊物名称_{简称}``。

这是**只读投影**：不写回任何 research 结构，不复制元数据进 research 库，也不下载全文。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from contextlib import closing
from typing import Any

_BRACED = re.compile(r"^\s*\{([^}]+)\}")
_QUOTED = re.compile(r'^\s*["“\']([^"”\']+)["”\']')

_FALLBACK_VENUES = {
    "usenix-security": "USENIX Security",
    "ccs": "CCS",
    "ieee-sp": "IEEE S&P",
    "ndss": "NDSS",
}

_EMPTY: dict[str, Any] = {
    "year": None, "venue": "", "title": "", "short_name": "", "display_label": "",
}


def short_name(title: str) -> str:
    """提取论文简称；提取不到就原样返回完整标题。

    USENIX 系论文的惯例是把简称放在标题最前面：``{SecSMT}: Securing ...`` 或
    ``"How Do You Not Lose Friends?": Synthesizing ...``。两者都取最前面那一段；
    没有这种结构时返回完整标题，绝不臆造。
    """
    text = str(title or "").strip()
    if not text:
        return ""
    for pattern in (_BRACED, _QUOTED):
        match = pattern.match(text)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return text


def display_label(year: Any, venue: Any, short: str) -> str:
    """拼成 ``年份_会议刊物名称_{简称}``。缺年份/会议时退化为可用片段，不显示空占位。"""
    parts: list[str] = []
    year_text = str(year or "").strip()
    if year_text and year_text not in {"None", "0"}:
        parts.append(year_text)
    venue_text = str(venue or "").strip()
    if venue_text:
        parts.append(venue_text)
    short_text = str(short or "").strip()
    if short_text:
        parts.append(short_text)
    return "_".join(parts)


class PaperDisplayResolver:
    """把 catalog_paper_id / candidate_id 投影为展示信息。

    两套 ID 空间并存：
    - 32 位 ``catalog_paper_id`` -> ``catalog_papers``（本地已索引目录）
    - 16 位 ``candidate_id``     -> ``paper_candidates``（外部检索候选，带 pdf_url）
    两边都查，查到即用；都查不到时返回空投影（UI 侧回落到原始 ID）。
    """

    def __init__(self, discovery_store: Any) -> None:
        self._store = discovery_store
        self._venues: dict[str, str] | None = None
        self._cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # 只读 SQL 投影（该库没有「按 id 取候选」的公开方法，只能直查）
    # ------------------------------------------------------------------ #

    def _rows(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        if self._store is None:
            return []
        try:
            with closing(self._store._connect()) as connection:  # noqa: SLF001
                cursor = connection.execute(sql, params)
                columns = [item[0] for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:  # noqa: BLE001 - 展示名不可用时静默回落，不影响主流程
            return []

    def _venue_name(self, conference_id: str, fallback: str = "") -> str:
        if not conference_id:
            return fallback or ""
        if self._venues is None:
            venues: dict[str, str] = {}
            for row in self._rows("SELECT conference_id, name, short_name FROM conference_sources", ()):
                name = str(row.get("name") or row.get("short_name") or "").strip()
                if name:
                    venues[str(row.get("conference_id") or "")] = name
            self._venues = venues
        return self._venues.get(conference_id) or fallback or _FALLBACK_VENUES.get(conference_id, conference_id)

    def _record(self, paper_id: str, year: Any, venue: str, title: str) -> dict[str, Any]:
        title_text = str(title or "").strip()
        short = short_name(title_text)
        return {
            "paper_id": paper_id,
            "year": year,
            "venue": venue,
            "title": title_text,
            "short_name": short,
            "display_label": display_label(year, venue, short),
        }

    def _from_candidates(self, paper_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "SELECT title, year, conference_id, conference_name FROM paper_candidates "
            "WHERE candidate_id=? ORDER BY rowid DESC LIMIT 1",
            (paper_id,),
        )
        for row in rows:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            venue = str(row.get("conference_name") or "").strip() or self._venue_name(
                str(row.get("conference_id") or "")
            )
            return self._record(paper_id, row.get("year"), venue, title)
        return None

    def _from_catalog(self, paper_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "SELECT title, year, conference_id FROM catalog_papers WHERE catalog_paper_id=? LIMIT 1",
            (paper_id,),
        )
        for row in rows:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            return self._record(
                paper_id, row.get("year"), self._venue_name(str(row.get("conference_id") or "")), title
            )
        return None

    def resolve(self, paper_id: str) -> dict[str, Any]:
        key = str(paper_id or "").strip()
        if not key:
            return {**_EMPTY, "paper_id": ""}
        if key in self._cache:
            return self._cache[key]
        record = self._from_candidates(key) or self._from_catalog(key)
        if record is None:
            record = {**_EMPTY, "paper_id": key}
        self._cache[key] = record
        return record

    def resolve_many(self, paper_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        for value in paper_ids or ():
            key = str(value or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result[key] = self.resolve(key)
        return result


__all__ = ["PaperDisplayResolver", "display_label", "short_name"]
