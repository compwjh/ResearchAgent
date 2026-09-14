#!/usr/bin/env python3
"""One-time publisher login for the persistent browser profile (HITL).

Why this exists
---------------
`dl.acm.org/doi/pdf/{doi}` (and IEEE equivalents) return **403 to every
non-browser request** — Cloudflare `Just a moment...` challenge. Institutional
IP does not help (verified 2026-09-14). The paywalled majority of papers can
therefore only be fetched through a *real* browser whose profile already holds
a logged-in session.

Run this ONCE. Complete the Cloudflare verification and sign in. This script
**verifies** success by actually downloading a probe PDF — it never claims
success just because time elapsed.

CRITICAL — why you must use the window this script opens
-------------------------------------------------------
The `cf_clearance` cookie Cloudflare issues is bound to the *browser instance*
(UA + TLS + fingerprint) that solved the challenge. A clearance obtained in
your own Chrome, or in Playwright's bundled Chromium, will NOT be accepted by
the browser this script launches (measured 2026-09-14: 403 on every request).
You must solve the challenge in the window **this script opens**.

Launch flags matter too: `--disable-blink-features=AutomationControlled` and
`ignore_default_args=["--enable-automation"]` remove `navigator.webdriver`.
Without them Cloudflare re-challenges on every navigation — the "infinite
refresh" symptom. Whatever flags you log in with, you must download with.

Usage
-----
    python3 acm_login.py                          # open ACM landing, wait for you
    python3 acm_login.py --doi 10.1145/3719027.3765064
    python3 acm_login.py --publisher ieee --doi 10.1109/SP.2024.00001 \
                         --pdf-url https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10600000
    python3 acm_login.py --timeout 900            # seconds (default 900)
    python3 acm_login.py --channel chromium       # bundled Chromium (worse fingerprint)

Exit codes
----------
    0  LOGIN CONFIRMED — a real probe PDF was downloaded
    1  browser could not start / Playwright missing
    2  not confirmed within the timeout
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

DEFAULT_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
PROBE_INTERVAL_S = 30
NAV_TIMEOUT_MS = 60_000

SITES = {
    "acm": {
        "landing": "https://dl.acm.org/doi/{doi}",
        "pdf": "https://dl.acm.org/doi/pdf/{doi}",
        "default_doi": "10.1145/3719027.3765064",
    },
    "ieee": {
        "landing": "https://ieeexplore.ieee.org/document/{doc}",
        "pdf": None,  # needs arnumber -> caller must pass --pdf-url
    },
}

#: Substrings Cloudflare puts in <title> while a challenge is pending.
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


def default_profile_dir() -> Path:
    env = os.getenv("PAPER_DISCOVERY_BROWSER_PROFILE_DIR")
    if env:
        return Path(env)
    # repo root = parents[4] of this file (…/ResearchAgent/.codebuddy/skills/<skill>/scripts)
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "browser-profile" / "security-papers"


def is_challenged(title: str, url: str) -> bool:
    """True while a Cloudflare interstitial is showing."""
    low = (title or "").lower()
    if any(marker in low for marker in CHALLENGE_TITLE_MARKERS):
        return True
    low_url = (url or "").lower()
    return any(marker in low_url for marker in CHALLENGE_URL_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser(description="One-time publisher login (persistent profile, HITL).")
    parser.add_argument("--publisher", default="acm", choices=sorted(SITES), help="publisher site (default: acm)")
    parser.add_argument("--doi", default=None, help="probe paper DOI (must be readable from your account)")
    parser.add_argument("--url", default=None, help="page to open (default: landing page of --doi)")
    parser.add_argument("--pdf-url", default=None, help="explicit probe PDF URL (required for IEEE)")
    parser.add_argument("--profile", default=None, help="persistent profile directory")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="seconds to wait (default 900)")
    parser.add_argument("--channel", default="chrome", help="browser channel: chrome (default) or chromium")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("Playwright not installed. Run: python -m playwright install chromium", file=sys.stderr)
        return 1

    site = SITES[args.publisher]
    doi = args.doi or site.get("default_doi")
    if not doi:
        parser.error(f"--doi is required for publisher {args.publisher}")
    if args.pdf_url:
        pdf_url = args.pdf_url
    elif site.get("pdf"):
        pdf_url = site["pdf"].format(doi=doi)
    else:
        parser.error(f"--pdf-url is required for publisher {args.publisher}")
    landing_url = args.url or site["landing"].format(doi=doi, doc=doi)

    profile = Path(args.profile) if args.profile else default_profile_dir()
    if not profile.exists():
        profile.mkdir(parents=True)

    print(f"profile   : {profile}")
    print(f"publisher : {args.publisher}")
    print(f"landing   : {landing_url}")
    print(f"probe pdf : {pdf_url}")
    print()
    print(">>> A browser window is opening. In THAT window: <<<")
    print("    1. complete the Cloudflare verification (tick the box if one appears)")
    print("    2. sign in to the publisher (institutional access recommended)")
    print()
    print("    This script verifies success by actually downloading the probe PDF.")
    print("    It will NOT report success just because time passed.")
    print()

    launch_kwargs: dict = {
        "headless": False,
        "accept_downloads": True,
        "viewport": {"width": 1440, "height": 1000},
        "args": ANTI_AUTOMATION_ARGS,
        "ignore_default_args": ["--enable-automation"],
    }
    if args.channel != "chromium":
        launch_kwargs["channel"] = args.channel

    confirmed = False
    last_state = "not started"

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
            try:
                page.goto(landing_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except Exception as exc:  # noqa: BLE001
                print(f"navigation warning: {type(exc).__name__}: {exc}")

            deadline = time.time() + args.timeout
            next_probe_at = 0.0

            while time.time() < deadline:
                time.sleep(POLL_INTERVAL_S)
                if not ctx.pages:
                    last_state = "browser window was closed before login could be confirmed"
                    break
                try:
                    title = page.title() or ""
                    url = page.url or ""
                except Exception as exc:  # noqa: BLE001
                    last_state = f"page unreachable ({type(exc).__name__})"
                    continue

                if is_challenged(title, url):
                    last_state = f"cloudflare challenge pending (title={title[:40]!r})"
                    continue

                now = time.time()
                if now < next_probe_at:
                    last_state = f"challenge cleared, waiting to probe (title={title[:40]!r})"
                    continue
                next_probe_at = now + PROBE_INTERVAL_S

                try:
                    resp = page.goto(pdf_url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
                    status = getattr(resp, "status", None)
                    if resp is not None and status == 200:
                        body = resp.body()
                        if body[:4] == b"%PDF":
                            print(f"\nPROBE OK: got a real PDF ({len(body)} bytes)")
                            confirmed = True
                            break
                        last_state = f"probe returned 200 but not a PDF ({body[:16]!r})"
                    else:
                        last_state = f"probe returned status={status}"
                        # Show the human something useful again.
                        try:
                            page.goto(landing_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                        except Exception:  # noqa: BLE001,S110
                            pass
                except Exception as exc:  # noqa: BLE001
                    last_state = f"probe failed ({type(exc).__name__}: {str(exc)[:80]})"
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001,S110
                pass

    if confirmed:
        print(f"\nLOGIN CONFIRMED -- profile saved at: {profile}")
        print("Unattended downloads can now reuse this profile (with the SAME launch flags).")
        return 0

    print(f"\nLOGIN NOT CONFIRMED within {args.timeout}s.")
    print(f"  last state: {last_state}")
    print("\n  Common causes:")
    print("   - Cloudflare verification was never completed in the opened window")
    print("   - you signed in, but this account/IP cannot read the probe paper")
    print("     -> retry with --doi <a paper you know you can read>")
    print("   - the profile was created by a different browser build")
    print("     -> retry with a fresh --profile directory")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
