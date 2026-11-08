#!/usr/bin/env python3
"""Generate demo literature-map data from the local paper catalog.

The maps are inserted through the application store (never raw SQL against
business tables), so revisions, job state machine and ownership guards all
stay consistent with a real map-generation run.

Usage:
    .venv/bin/python scripts/seed_demo_literature_maps.py
    .venv/bin/python scripts/seed_demo_literature_maps.py --clean

Demo maps are bound to the tag ``演示数据``; the tag is the sole marker used
for idempotent re-generation and clean-up.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.literature_maps.domain.models import MapEdge, MapPaper  # noqa: E402
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore  # noqa: E402
from backend.app.memory.repository import OWNER_ID  # noqa: E402

CATALOG_DB = ROOT / "data" / "paper_search" / "state.sqlite3"
SEED_TAG_NAME = "演示数据"
SEED_TAG_COLOR = "#845ef7"

SPECS = (
    {
        "name": "隐私测量与追踪生态",
        "topic": "privacy measurement and web tracking",
        "terms": ("privacy", "track", "trackers", "ads", "advertis", "cookie", "fingerprint", "leak", "data collect", "gdpr"),
        "size": 13,
    },
    {
        "name": "漏洞挖掘与模糊测试",
        "topic": "vulnerability discovery and fuzzing",
        "terms": ("fuzz", "vulnerab", "exploit", "bug", "crash", "memory", "sanitiz", "patch", "attack", "malware"),
        "size": 12,
    },
    {
        "name": "认证与协议安全",
        "topic": "authentication and protocol security",
        "terms": ("authentic", "password", "tls", "protocol", "crypto", "key", "certificat", "ssh", "encryption", "login"),
        "size": 11,
    },
)


def _json_list(raw: object) -> list[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))][:8]


def _pick_papers(size: int, terms: tuple[str, ...], used: set[str]) -> list[sqlite3.Row]:
    with sqlite3.connect(CATALOG_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT catalog_paper_id, year, title, authors_json, abstract, keywords_json, official_page_url "
            "FROM catalog_papers WHERE title IS NOT NULL AND title <> ''"
        ).fetchall()
    scored = []
    for row in rows:
        title = str(row["title"]).lower()
        score = sum(1 for term in terms if term in title)
        scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["catalog_paper_id"])))
    chosen: list[sqlite3.Row] = []
    for _score, row in scored:
        key = str(row["catalog_paper_id"])
        if key in used:
            continue
        used.add(key)
        chosen.append(row)
        if len(chosen) == size:
            break
    return chosen


def _positions(count: int) -> list[tuple[float, float]]:
    cx, cy, radius = 480.0, 340.0, 215.0
    return [
        (
            round(cx + radius * math.cos(2 * math.pi * i / count), 2),
            round(cy + radius * math.sin(2 * math.pi * i / count), 2),
        )
        for i in range(count)
    ]


def _build_node(map_id: str, row: sqlite3.Row, pos: tuple[float, float], index: int) -> MapPaper:
    raw_year = row["year"]
    year = int(raw_year) if str(raw_year or "").isdigit() else None
    return MapPaper.new(
        map_id,
        semantic_scholar_id=f"seed:{row['catalog_paper_id']}",
        title=str(row["title"]),
        authors=tuple(_json_list(row["authors_json"])),
        year=year,
        venue="USENIX Security",
        abstract=(str(row["abstract"])[:1400] or None) if row["abstract"] else None,
        keywords=tuple(_json_list(row["keywords_json"])),
        citation_count=max(0, 240 - index * 13),
        source_url=row["official_page_url"],
        provenance={"source": "seed-demo", "catalog_paper_id": str(row["catalog_paper_id"])},
        catalog_paper_id=str(row["catalog_paper_id"]),
        position={"x": pos[0], "y": pos[1]},
    )


def _build_edges(map_id: str, nodes: list[MapPaper]) -> list[MapEdge]:
    edges: list[MapEdge] = []
    by_year = sorted(nodes, key=lambda node: (node.year or 0, node.node_id), reverse=True)
    for newer, older in zip(by_year, by_year[1:], strict=False):
        edges.append(MapEdge.new(map_id, "citation", newer.node_id, older.node_id, provenance={"source": "seed-demo"}))
    for step in (2, 4):
        for newer, older in zip(by_year, by_year[step:], strict=False):
            if len(edges) >= len(nodes) + 5:
                break
            edges.append(MapEdge.new(map_id, "citation", newer.node_id, older.node_id, provenance={"source": "seed-demo"}))
    for i in range(0, len(nodes) - 1, 3):
        edges.append(
            MapEdge.new(
                map_id,
                "similarity",
                nodes[i].node_id,
                nodes[i + 1].node_id,
                score=round(0.62 + (i % 5) * 0.06, 2),
                provenance={"source": "seed-demo"},
            )
        )
    return edges


def _find_seed_tag(store: LiteratureMapStore):
    return next((tag for tag in store.list_tags(OWNER_ID) if tag.name == SEED_TAG_NAME), None)


def clean(store: LiteratureMapStore) -> int:
    tag = _find_seed_tag(store)
    if tag is None:
        return 0
    removed = 0
    for item in store.list_maps(OWNER_ID, limit=100):
        bound = store.list_map_tags(item.map_id, OWNER_ID)
        if any(entry["tag_id"] == tag.tag_id for entry in bound) and store.delete_map(item.map_id, OWNER_ID):
            removed += 1
    store.delete_tag(OWNER_ID, tag.tag_id)
    return removed


def generate(store: LiteratureMapStore) -> None:
    tag = store.create_tag(OWNER_ID, SEED_TAG_NAME, SEED_TAG_COLOR)
    used: set[str] = set()
    for spec in SPECS:
        rows = _pick_papers(spec["size"], spec["terms"], used)
        if not rows:
            print(f"  skip {spec['name']}: no papers available")
            continue
        item, job, _created = store.create_map_with_job(
            OWNER_ID,
            topic=spec["topic"],
            name=spec["name"],
            filters={"source_ids": ["usenix"], "seed_demo": True},
            requested_count=30,
            idempotency_key=uuid.uuid4().hex,
        )
        if store.claim_job(job.job_id, item.map_id, OWNER_ID) is None:
            raise RuntimeError(f"cannot claim job for {item.map_id}")
        nodes = [
            _build_node(item.map_id, row, pos, index)
            for index, (row, pos) in enumerate(zip(rows, _positions(len(rows)), strict=True))
        ]
        store.add_nodes(item.map_id, OWNER_ID, nodes, job_id=job.job_id)
        edges = _build_edges(item.map_id, nodes)
        store.add_edges(item.map_id, OWNER_ID, edges, job_id=job.job_id)
        store.set_map_tags(item.map_id, OWNER_ID, [tag.tag_id])
        store.finish_job(
            job.job_id,
            item.map_id,
            OWNER_ID,
            status="completed",
            counts={"nodes": len(nodes), "edges": len(edges)},
        )
        print(f"  {spec['name']}: {len(nodes)} nodes, {len(store.list_edges(item.map_id, OWNER_ID))} edges, map_id={item.map_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo literature maps")
    parser.add_argument("--clean", action="store_true", help="remove demo maps and exit")
    args = parser.parse_args()
    store = LiteratureMapStore()
    print(f"db: {store.database_path}")
    removed = clean(store)
    print(f"cleaned: {removed} demo map(s)")
    if args.clean:
        return
    generate(store)
    print(f"total maps now: {len(store.list_maps(OWNER_ID, limit=100))}")


if __name__ == "__main__":
    main()
