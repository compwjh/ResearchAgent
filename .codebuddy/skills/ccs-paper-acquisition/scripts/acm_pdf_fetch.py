#!/usr/bin/env python3
"""Unattended batch PDF download with an authenticated persistent profile.

Prerequisite
------------
Run `acm_login.py` once and get `LOGIN CONFIRMED`. This script reuses that
profile. **The launch flags must match** or Cloudflare will re-challenge.

Why page.goto and not BrowserContext.request
--------------------------------------------
Playwright's `BrowserContext.request` (APIRequest) sends its own User-Agent,
which differs from the browser's. Cloudflare binds `cf_clearance` to the UA
that solved the challenge, so APIRequest gets 403 even from an authenticated
context (measured 2026-09-14: 403 on every request). Navigating the real page
uses the browser's own network stack -> UA/TLS/fingerprint match -> 200 PDF.

Usage
-----
    python3 acm_pdf_fetch.py --doi 10.1145/3719027.3765064 --out ./pdfs
    python3 acm_pdf_fetch.py --doi 10.1145/3719027.3744787 --out ./pdfs
    python3 acm_pdf_fetch.py --jsonl papers.jsonl --out ./pdfs
    python3 acm_pdf_fetch.py --publisher ieee --pdf-url https://... --out ./pdfs

JSONL row schema: one JSON object per line, fields used:
    - doi       (preferred for ACM filename)
    - pdf_url   (required for IEEE, optional override for ACM)
    - title     (cosmetic; printed in summary)

Exit codes
----------
    0  all requested papers downloaded
    3  at least one failed
    4  session expired -> re-run acm_login.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

NAV_TIMEOUT_MS = 60_000
DEFAULT_DELAY_S = 2.0

SITES = {
    "acm": {
        "pdf": "https://dl.acm.org/doi/pdf/{doi}",
    },
    "ieee": {
        "pdf": None,  # requires arnumber; pass --pdf-url per paper
    },
}

CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "verifying you are human",
    "performing security verification",
    "ddos protection",
)
CHALLENGE_URL_MARKERS = ("__cf_chl", "cdn-cgi/challenge")

ANTI_AUTOMATION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def default_profile_dir() -> Path:
    env = os.getenv("PAPER_DISCOVERY_BROWSER_PROFILE_DIR")
    if env:
        return Path(env)
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "browser-profile" / "security-papers"


def is_challenged(title: str, url: str) -> bool:
    low = (title or "").lower()
    if any(m in low for m in CHALLENGE_TITLE_MARKERS):
        return True
    low_url = (url or "").lower()
    return any(m in low_url for m in CHALLENGE_URL_MARKERS)


def safe_filename(s: str, maxlen: int = 120) -> str:
    cleaned = _SAFE_RE.sub("_", s or "").strip("._-")
    return (cleaned or "file")[:maxlen]


def build_pdf_url(publisher: str, doi: str | None, pdf_url: str | None) -> str:
    if pdf_url:
        return pdf_url
    site = SITES.get(publisher) or {}
    pattern = site.get("pdf")
    if not pattern:
        raise ValueError(f"--pdf-url is required for publisher {publisher}")
    if not doi:
        raise ValueError("doi is required when pdf_url is not provided")
    return pattern.format(doi=doi)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unattended PDF downloader using an authenticated persistent profile.")
    parser.add_argument("--publisher", default="acm", choices=sorted(SITES), help="publisher site (default: acm)")
    parser.add_argument("--doi", action="append", default=[], help="DOI to fetch (repeatable)")
    parser.add_argument("--jsonl", default=None, help="JSONL file with {doi,pdf_url,title} per line")
    parser.add_argument("--out", default="./pdfs", help="output directory (default ./pdfs)")
    parser.add_argument("--profile", default=None, help="persistent profile directory")
    parser.add_argument("--channel", default="chrome", help="browser channel: chrome (default) or chromium")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_S, help="seconds between papers")
    args = parser.parse_args()

    if not args.doi and not args.jsonl:
        parser.error("provide --doi (repeatable) or --jsonl")

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("Playwright not installed. Run: python -m playwright install chromium", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    if not out_dir.exists():
        out_dir.mkdir(parents=True)

    records: list[dict] = []
    for d in args.doi:
        records.append({"doi": d})
    if args.jsonl:
        with open(args.jsonl, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError as exc:
                    print(f"  [jsonl:{lineno}] skip bad json: {exc}")
                    continue
                if not isinstance(rec, dict):
                    print(f"  [jsonl:{lineno}] skip non-object row")
                    continue
                records.append(rec)

    profile = Path(args.profile) if args.profile else default_profile_dir()
    if not profile.exists():
        print(f"profile not found: {profile}", file=sys.stderr)
        print("Run acm_login.py first.", file=sys.stderr)
        return 1

    launch_kwargs: dict = {
        "headless": False,
        "accept_downloads": True,
        "viewport": {"width": 1440, "height": 1000},
        "args": ANTI_AUTOMATION_ARGS,
        "ignore_default_args": ["--enable-automation"],
    }
    if args.channel != "chromium":
        launch_kwargs["channel"] = args.channel

    print(f"profile   : {profile}")
    print(f"publisher : {args.publisher}")
    print(f"output    : {out_dir}")
    print(f"count     : {len(records)}")
    print()

    results: list[dict] = []
    session_expired = False

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(str(profile), **launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            print(f"launch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.bring_to_front()
            except Exception:  # noqa: BLE001,S110
                pass

            for idx, rec in enumerate(records, start=1):
                doi = rec.get("doi") or rec.get("DOI")
                title = rec.get("title") or ""
                explicit_pdf = rec.get("pdf_url") or rec.get("pdfUrl")

                try:
                    pdf_url = build_pdf_url(args.publisher, doi, explicit_pdf)
                except ValueError as exc:
                    print(f"[{idx}/{len(records)}] skip: {exc}")
                    results.append({"ok": False, "reason": str(exc), "doi": doi})
                    continue

                label = doi or pdf_url
                print(f"[{idx}/{len(records)}] {label}  ({title[:60]})")
                try:
                    resp = page.goto(pdf_url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
                except Exception as exc:  # noqa: BLE001
                    msg = f"goto_exc={type(exc).__name__}:{str(exc)[:80]}"
                    print(f"  fail: {msg}")
                    results.append({"ok": False, "reason": msg, "doi": doi, "url": pdf_url})
                    time.sleep(args.delay)
                    continue

                status = getattr(resp, "status", None)
                try:
                    title_now = page.title() or ""
                    url_now = page.url or ""
                except Exception:  # noqa: BLE001
                    title_now, url_now = "", ""

                if is_challenged(title_now, url_now):
                    session_expired = True
                    print("  fail: Cloudflare challenge re-emerged (run acm_login.py to refresh).")
                    results.append({"ok": False, "reason": "session_expired", "doi": doi, "url": pdf_url})
                    break

                if status in (401, 403):
                    session_expired = True
                    print(f"  fail: status={status} (entitlement may have lapsed).")
                    results.append({"ok": False, "reason": f"status={status}", "doi": doi, "url": pdf_url})
                    break

                if status != 200:
                    print(f"  fail: status={status}")
                    results.append({"ok": False, "reason": f"status={status}", "doi": doi, "url": pdf_url})
                    time.sleep(args.delay)
                    continue

                try:
                    body = resp.body()
                except Exception as exc:  # noqa: BLE001
                    msg = f"body_exc={type(exc).__name__}:{str(exc)[:80]}"
                    print(f"  fail: {msg}")
                    results.append({"ok": False, "reason": msg, "doi": doi, "url": pdf_url})
                    time.sleep(args.delay)
                    continue

                if body[:4] != b"%PDF":
                    print(f"  fail: not a PDF (magic={body[:16]!r})")
                    results.append({"ok": False, "reason": "not_pdf", "doi": doi, "url": pdf_url})
                    time.sleep(args.delay)
                    continue

                fname = safe_filename(doi or pdf_url) + ".pdf"
                target = out_dir / fname
                target.write_bytes(body)
                print(f"  ok: {len(body)} bytes -> {target}")
                results.append({"ok": True, "bytes": len(body), "path": str(target), "doi": doi, "url": pdf_url})
                time.sleep(args.delay)
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001,S110
                pass

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"\nSummary: ok={ok} fail={fail} total={len(results)}")
    if session_expired:
        print("Session expired -> re-run acm_login.py and retry.")
        return 4
    if fail > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())