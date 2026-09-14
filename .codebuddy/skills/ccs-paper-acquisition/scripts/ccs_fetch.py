#!/usr/bin/env python3
"""ACM CCS paper acquisition (validated pipeline, spec-032 Task 04).

Pipeline (all three stages verified live 2026-09):
  1. ENUMERATE  Crossref  -> candidate DOIs (ACM member 320 + year window)
  2. FILTER     container-title fuzzy match -> keep CCS main track only
  3. ENRICH     OpenAlex  -> abstract (abstract_inverted_index) + OA PDF

Rejected approaches (do NOT re-try without new evidence):
  - dl.acm.org direct HTTP ....... 403 (anti-bot). Abstracts are NOT reachable this way.
  - Crossref abstract field ...... always None for ACM (ACM deposits no abstract).
  - DBLP (HTML + API) ............ anti-bot wall ("Making sure you're not a bot!").
  - sigsac.org accepted-papers ... pure client-side render; empty <ul>, 0 DOIs in HTML.
  - OpenAlex source-id per year .. only 2022 resolves; 2025 papers have no source.
  - OpenAlex DOI prefix wildcard . filter=doi:10.1145/xxxxx* -> count=0 (unsupported).

Usage:
  python3 ccs_fetch.py --years 2019-2025 --out ccs_papers.jsonl
  python3 ccs_fetch.py --years 2025 --no-enrich --out quick.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
ACM_MEMBER = 320  # Crossref member id for ACM


def _get(url: str, timeout: int = 40, retries: int = 3) -> tuple[int, str]:
    """GET with light backoff. Returns (status, body); status -1 means transport error."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read()[:200].decode("utf-8", "replace") if exc.fp else ""
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return exc.code, body
        except Exception as exc:  # noqa: BLE001 - surfaced to caller as -1
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return -1, f"{type(exc).__name__}: {exc}"
    return -1, "exhausted retries"


def is_ccs_main_track(container_title: str, year: int) -> bool:
    """Keep CCS main-track proceedings, drop co-located workshops.

    Handles the ACM naming drift, e.g.
      2025 -> "Proceedings of the 2025 ACM SIGSAC Conference on ..."
      2024 -> "Proceedings of the 2024 on ACM SIGSAC Conference on ..."   <- extra "on"
    """
    text = (container_title or "").lower()
    if "workshop" in text:
        return False
    is_ccs = "sigsac" in text or "computer and communications security" in text
    return is_ccs and str(year) in text


def enumerate_year(year: int, rows: int = 1000, max_pages: int = 5, sleep: float = 0.3) -> list[dict[str, Any]]:
    """Crossref enumeration for one CCS year, deduped by DOI."""
    query = f"ACM SIGSAC Conference on Computer and Communications Security {year}"
    found: dict[str, dict[str, Any]] = {}
    for page in range(max_pages):
        params = {
            "query.bibliographic": query,
            "filter": (
                f"member:{ACM_MEMBER},type:proceedings-article,"
                f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
            ),
            "rows": str(rows),
            "offset": str(page * rows),
            "select": "DOI,title,container-title,author,issued,URL,abstract",
        }
        url = f"{CROSSREF}?{urllib.parse.urlencode(params)}"
        status, body = _get(url)
        if status != 200:
            print(f"  [{year}] crossref page {page}: HTTP {status} {body[:100]}")
            break
        items = json.loads(body)["message"].get("items", [])
        if not items:
            break
        for item in items:
            container = (item.get("container-title") or [""])[0]
            if not is_ccs_main_track(container, year):
                continue
            doi = (item.get("DOI") or "").strip().lower()
            if not doi or doi in found:
                continue
            found[doi] = {
                "doi": doi,
                "title": (item.get("title") or [""])[0],
                "container_title": container,
                "year": year,
                "authors": [
                    " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
                    for a in (item.get("author") or [])
                ],
                "crossref_url": item.get("URL"),
                "crossref_abstract": item.get("abstract"),  # always None for ACM
                "provenance": ["crossref"],
            }
        time.sleep(sleep)
        if len(items) < rows:
            break
    return list(found.values())


def invert_abstract(index: dict[str, list[int]] | None) -> str | None:
    """Rebuild text from OpenAlex abstract_inverted_index."""
    if not index:
        return None
    slots: dict[int, str] = {}
    for word, positions in index.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[key] for key in sorted(slots))


def enrich_openalex(record: dict[str, Any], sleep: float = 0.12) -> dict[str, Any]:
    """Add abstract + OA PDF from OpenAlex. Never raises; degrades to crossref-only."""
    url = f"{OPENALEX}/doi:{record['doi']}?select=doi,title,publication_year,abstract_inverted_index,best_oa_location,open_access"
    status, body = _get(url)
    time.sleep(sleep)
    if status != 200:
        record["openalex_status"] = status
        return record
    try:
        work = json.loads(body)
    except json.JSONDecodeError:
        return record
    abstract = invert_abstract(work.get("abstract_inverted_index"))
    if abstract:
        record["abstract"] = abstract
        record["provenance"].append("openalex:abstract")
    oa = work.get("best_oa_location") or {}
    pdf = oa.get("pdf_url")
    if pdf:
        record["pdf_url"] = pdf
        record["pdf_access"] = "open_access"
        record["provenance"].append("openalex:oa_pdf")
    else:
        record["pdf_url"] = None
        record["pdf_access"] = "unknown"  # ACM paywalled; needs institution/legal route
    record["openalex_status"] = 200
    return record


def parse_years(spec: str) -> list[int]:
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(part) for part in spec.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire ACM CCS papers across years.")
    parser.add_argument("--years", default="2019-2025", help="e.g. 2025 or 2019-2025")
    parser.add_argument("--out", default="ccs_papers.jsonl", help="output JSONL path")
    parser.add_argument("--rows", type=int, default=1000, help="crossref page size (max 1000)")
    parser.add_argument("--max-pages", type=int, default=5, help="crossref pages per year")
    parser.add_argument("--no-enrich", action="store_true", help="skip OpenAlex abstract step")
    args = parser.parse_args()

    years = parse_years(args.years)
    total = 0
    with open(args.out, "w", encoding="utf-8") as handle:
        for year in years:
            papers = enumerate_year(year, rows=args.rows, max_pages=args.max_pages)
            print(f"[{year}] crossref -> {len(papers)} CCS main-track papers")
            if not args.no_enrich:
                with_abstract = 0
                for paper in papers:
                    enrich_openalex(paper)
                    if paper.get("abstract"):
                        with_abstract += 1
                print(f"[{year}] openalex -> abstracts {with_abstract}/{len(papers)}")
            for paper in papers:
                handle.write(json.dumps(paper, ensure_ascii=False) + "\n")
            total += len(papers)
    print(f"\ntotal {total} papers -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
