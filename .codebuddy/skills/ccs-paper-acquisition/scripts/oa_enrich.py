#!/usr/bin/env python3
"""Bulk-enrich a `ccs_fetch.py --no-enrich` JSONL with abstracts + OA PDF links.

Why this exists
---------------
`ccs_fetch.py` enriches **one DOI per HTTP request**. For a 400-paper year that
is ~400 round trips and takes well over 10 minutes. OpenAlex supports a batched
`filter=doi:a|b|c|...` (up to 50 per call), which turns it into ~8 requests.

Same output contract as `ccs_fetch.py`'s own enrichment:
    - `abstract`        (rebuilt from `abstract_inverted_index`)
    - `pdf_url`         (OpenAlex `best_oa_location.pdf_url`, else None)
    - `pdf_access`      "open_access" | "unknown"
    - `provenance`      gets "openalex:abstract" appended

Usage
-----
    # 1. fast enumerate, no per-paper HTTP
    python3 scripts/ccs_fetch.py --years 2024 --no-enrich --out raw.jsonl
    # 2. bulk enrich
    python3 scripts/oa_enrich.py raw.jsonl enriched.jsonl
    # 3. download the OA ones
    python3 scripts/oa_pdf_fetch.py --jsonl enriched.jsonl --out ./pdfs

Optionally set OPENALEX_MAILTO to get into OpenAlex's polite pool.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx not installed: pip install httpx", file=sys.stderr)
    raise SystemExit(1) from None

OPENALEX = "https://api.openalex.org/works"
BATCH = 50
SELECT = "doi,best_oa_location,open_access,abstract_inverted_index,locations"
SLEEP_S = 0.3

# Hosts that are "open access" on paper but unreachable unattended in practice,
# because they sit behind Cloudflare / bot walls. Measured on CCS 2024:
# 9 of 10 OpenAlex `best_oa_location.pdf_url` pointed at dl.acm.org -> all 403.
GATED_HOSTS = {
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "www.sciencedirect.com",
    "sciencedirect.com",
}


def host_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        return url.split("//", 1)[-1].split("/", 1)[0].lower()
    except Exception:  # noqa: BLE001
        return ""


def pick_pdf(work: dict) -> tuple[str | None, bool]:
    """Pick the best *downloadable* PDF for a work.

    Returns (pdf_url, is_gated). OpenAlex' `best_oa_location` prefers the
    publisher, so for ACM it hands back dl.acm.org even when an arXiv mirror
    exists. We therefore scan all `locations` and prefer any non-gated host.
    """
    candidates: list[str] = []
    best = (work.get("best_oa_location") or {}).get("pdf_url")
    if best:
        candidates.append(best)
    for loc in work.get("locations") or []:
        url = (loc or {}).get("pdf_url")
        if url:
            candidates.append(url)
    for url in candidates:
        if host_of(url) not in GATED_HOSTS:
            return url, False
    return (candidates[0] if candidates else None), True


def invert_abstract(index: dict | None) -> str | None:
    """Rebuild plain text from OpenAlex' inverted index."""
    if not index:
        return None
    slots: dict[int, str] = {}
    for word, positions in index.items():
        for position in positions or []:
            slots[position] = word
    if not slots:
        return None
    return " ".join(slots[key] for key in sorted(slots))


def normalize(doi: str | None) -> str:
    return (doi or "").replace("https://doi.org/", "").strip().lower()


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oa_enrich.py <input.jsonl> <output.jsonl>", file=sys.stderr)
        return 1

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    if not source.exists():
        print(f"no such file: {source}", file=sys.stderr)
        return 1

    records = [json.loads(line) for line in source.open(encoding="utf-8") if line.strip()]
    dois = [normalize(r.get("doi")) for r in records]
    dois = [d for d in dois if d]
    print(f"records: {len(records)}   dois: {len(dois)}")

    mailto = os.getenv("OPENALEX_MAILTO", "")

    lookup: dict[str, dict] = {}
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for start in range(0, len(dois), BATCH):
            chunk = dois[start : start + BATCH]
            # NOTE: pass the query as `params`, never embedded in the URL string.
            # Passing `params=` at all (even an empty dict) makes httpx rebuild the
            # query string and DROP whatever was already in `url`, silently turning
            # the request into "list all works" (hit rate 0, no error raised).
            params = {
                "filter": "doi:" + "|".join(chunk),
                "select": SELECT,
                "per-page": str(BATCH),
            }
            if mailto:
                params["mailto"] = mailto
            try:
                response = client.get(OPENALEX, params=params)
            except Exception as exc:  # noqa: BLE001
                print(f"batch {start // BATCH + 1}: {type(exc).__name__}: {str(exc)[:60]}")
                continue
            if response.status_code != 200:
                print(f"batch {start // BATCH + 1}: HTTP {response.status_code}")
                continue
            results = response.json().get("results", [])
            before = len(lookup)
            for work in results:
                key = normalize(work.get("doi"))
                if key:
                    lookup[key] = work
            hits = sum(1 for d in chunk if d in lookup)
            print(
                f"batch {start // BATCH + 1}: +{len(results)} results, "
                f"{hits}/{len(chunk)} hit  (total {len(lookup)})"
            )
            if results and hits == 0:
                print("  !! 返回 0 命中，疑似 query 未生效，请检查 filter 构造", file=sys.stderr)
            time.sleep(SLEEP_S)

    enriched = 0
    with_oa = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            work = lookup.get(normalize(record.get("doi")))
            if work:
                enriched += 1
                abstract = invert_abstract(work.get("abstract_inverted_index"))
                if abstract:
                    record["abstract"] = abstract
                    record.setdefault("provenance", []).append("openalex:abstract")
                pdf, gated = pick_pdf(work)
                if pdf:
                    record["pdf_url"] = pdf
                    record["pdf_host"] = host_of(pdf)
                    record["pdf_gated"] = gated
                    record["pdf_access"] = "blocked" if gated else "open_access"
                    if not gated:
                        with_oa += 1
                else:
                    record["pdf_url"] = None
                    record["pdf_access"] = "unknown"
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    pct = (with_oa * 100 // len(records)) if records else 0
    print(f"\nenriched: {enriched}/{len(records)}")
    print(f"真正可下载的 OA PDF: {with_oa} ({pct}%)")
    hosts: dict[str, int] = {}
    for record in records:
        h = host_of(record.get("pdf_url")) or "-"
        hosts[h] = hosts.get(h, 0) + 1
    print("PDF 域名分布:")
    for h, n in sorted(hosts.items(), key=lambda kv: -kv[1]):
        flag = "  [受限域名]" if h in GATED_HOSTS else ""
        print(f"  {n:4d}  {h}{flag}")
    print(f"written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
