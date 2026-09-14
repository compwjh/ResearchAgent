#!/usr/bin/env python3
"""HITL publisher login: plain Chrome (subprocess) + CDP attach.

Why this exists instead of `acm_login.py`
-----------------------------------------
Playwright's `launch_persistent_context` injects automation signals
(`--enable-automation`, blink `AutomationControlled`, CDP driving from the
very first navigation). Even with `--disable-blink-features=AutomationControlled`
and `ignore_default_args=["--enable-automation"]` — which *does* flip
`navigator.webdriver` to false — Cloudflare's Turnstile reliably stalls on
"Performing security verification" and never reveals a clickable checkbox.
Measured repeatedly on 2026-09-14 across Chromium 136 and Chrome 152.

So the browser that meets Cloudflare must be an **ordinary Chrome** with no
automation attached. This script:

1. launches Chrome as a **plain subprocess** (no Playwright involvement at all)
   on the persistent profile, with `--remote-debugging-port`
2. waits while a human clears the Cloudflare challenge and signs in — the
   browser is 100% normal during this phase
3. **afterwards** attaches Playwright over CDP and drives only the download

Phases
------
    1. launch plain Chrome + open the landing page
    2. HUMAN: clear Cloudflare, sign in to the publisher
    3. attach over CDP and probe-download a PDF every 30s
    4. LOGIN CONFIRMED only when real `%PDF-` bytes come back

Usage
-----
    python3 acm_login_cdp.py
    python3 acm_login_cdp.py --doi 10.1145/3719027.3765064
    python3 acm_login_cdp.py --port 9222 --timeout 1800

Notes
-----
- Leaves the Chrome window open on success so you can keep using it; the
  profile is already saved. Close it whenever you like.
- Progress is printed every poll — you can watch the log instead of guessing.

Exit codes
----------
    0  LOGIN CONFIRMED — real probe PDF downloaded
    1  could not start Chrome / reach the CDP port
    2  not confirmed within the timeout
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

#: 在**已通过挑战的 tab 内**做同源 fetch 取 PDF。
#: 关键：绝不 goto、绝不 new_page —— Cloudflare 会把它们当成新导航重新挑战。
_FETCH_PDF_JS = """
async (url) => {
  try {
    const r = await fetch(url, {credentials: 'include'});
    const ct = r.headers.get('content-type') || '';
    const buf = await r.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return {status: r.status, ct: ct, len: bytes.length, b64: btoa(bin)};
  } catch (e) {
    return {error: String(e)};
  }
}
"""

# 沙箱/CI 常设 http_proxy，会把 127.0.0.1:<port> 也送进代理，
# Playwright 的 connect_over_cdp 因此拿到 502 "does not look like a DevTools server"。
# 本地调试端口必须直连。
os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
DEFAULT_PORT = 9222
DEFAULT_TIMEOUT_S = 1800
POLL_INTERVAL_S = 10
PROBE_INTERVAL_S = 30
NAV_TIMEOUT_MS = 60_000

SITES = {
    "acm": {
        "landing": "https://dl.acm.org/doi/{doi}",
        "pdf": "https://dl.acm.org/doi/pdf/{doi}",
        "default_doi": "10.1145/3719027.3765064",
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


def find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def default_profile_dir() -> Path:
    env = os.getenv("PAPER_DISCOVERY_BROWSER_PROFILE_DIR")
    if env:
        return Path(env)
    # repo root = parents[4] of this file (…/ResearchAgent/.codebuddy/skills/<skill>/scripts)
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "browser-profile" / "security-papers-chrome"


def is_challenged(title: str, url: str) -> bool:
    low = (title or "").lower()
    if any(marker in low for marker in CHALLENGE_TITLE_MARKERS):
        return True
    low_url = (url or "").lower()
    return any(marker in low_url for marker in CHALLENGE_URL_MARKERS)


def cdp_version(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return json.load(resp)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="HITL login via plain Chrome + CDP attach.")
    parser.add_argument("--publisher", default="acm", choices=sorted(SITES), help="publisher (default: acm)")
    parser.add_argument("--doi", default=None, help="probe paper DOI (must be readable by your account)")
    parser.add_argument("--profile", default=None, help="persistent profile directory")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="CDP port (default 9222)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="seconds to wait (default 1800)")
    parser.add_argument("--out", default=None, help="where to save the probe PDF (default: don't save)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("Playwright not installed. Run: python -m playwright install chromium", file=sys.stderr)
        return 1

    chrome = find_chrome()
    if chrome is None:
        print("Could not find Google Chrome. Set CHROME_CANDIDATES or install Chrome.", file=sys.stderr)
        return 1

    site = SITES[args.publisher]
    doi = args.doi or site["default_doi"]
    landing_url = site["landing"].format(doi=doi)
    pdf_url = site["pdf"].format(doi=doi)

    profile = Path(args.profile) if args.profile else default_profile_dir()
    if not profile.exists():
        profile.mkdir(parents=True)

    print(f"chrome    : {chrome}")
    print(f"profile   : {profile}")
    print(f"cdp port  : {args.port}")
    print(f"landing   : {landing_url}")
    print(f"probe pdf : {pdf_url}")
    print()
    print(">>> A NORMAL Chrome window is opening (no automation attached). <<<")
    print("    1. clear the Cloudflare verification (tick the box if one appears)")
    print("    2. sign in to the publisher (institutional access recommended)")
    print()
    print("    This script verifies success by actually downloading the probe PDF.")
    print("    Progress prints below every few seconds — watch it, don't guess.")
    print()

    # --- Phase 1: launch plain Chrome (zero Playwright involvement) ---------
    deadline = time.time() + args.timeout
    # 端口上已有调试 Chrome（例如上一轮跑到一半）就复用，别让用户白操作一遍。
    version = cdp_version(args.port)
    proc = None
    if version is not None:
        print(f"[reuse] 端口 {args.port} 已有调试 Chrome：{version.get('Browser', 'Chrome')}")
        print("[reuse] 直接附着，不再开新窗口（你在窗口里的操作会保留）。")
    else:
        proc = subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={args.port}",
                f"--user-data-dir={profile}",
                # 沙箱/受限环境里 Chrome 少了这两个会静默退出（端口起不来）。
                # Playwright 自己启动时会带上，所以之前用 launch_persistent_context 没暴露这个问题。
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                landing_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        while time.time() < deadline:
            version = cdp_version(args.port)
            if version is not None:
                break
            if proc.poll() is not None:
                print("Chrome exited before the debug port came up.", file=sys.stderr)
                return 1
            time.sleep(1)

        if version is None:
            print("Timed out waiting for the CDP port.", file=sys.stderr)
            proc.terminate()
            return 1

    print(f"[cdp] attached to {version.get('Browser', 'Chrome')}")
    print()

    # --- Phase 2/3: attach, poll, probe -------------------------------------
    confirmed = False
    last_state = "not started"
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                # Use a dedicated probe page so the human's own tab is never navigated away.
                next_probe_at = 0.0
                tick = 0
                while time.time() < deadline:
                    time.sleep(POLL_INTERVAL_S)
                    tick += 1

                    # Is any page still showing a challenge?
                    try:
                        pages = list(context.pages)
                    except Exception:  # noqa: BLE001
                        last_state = "context unreachable"
                        break
                    if not pages:
                        last_state = "all browser tabs were closed"
                        break

                    titles = []
                    cleared_page = None
                    for page in pages:
                        try:
                            t, u = (page.title() or ""), (page.url or "")
                            titles.append((t, u))
                            if not is_challenged(t, u):
                                cleared_page = page
                        except Exception:  # noqa: BLE001,S110
                            pass
                    challenged = any(is_challenged(t, u) for t, u in titles) if titles else True
                    head = titles[0][0][:40] if titles else ""
                    print(
                        f"[poll {tick}] challenged={challenged} tabs={len(pages)} "
                        f"cleared={cleared_page is not None} title={head!r}",
                        flush=True,
                    )

                    if challenged:
                        last_state = "cloudflare challenge still pending"
                        continue

                    now = time.time()
                    if now < next_probe_at:
                        continue
                    next_probe_at = now + PROBE_INTERVAL_S

                    # --- probe: 同源 fetch，在已通过挑战的 tab 里 ---
                    if cleared_page is None:
                        last_state = "no cleared tab to fetch from"
                        continue
                    try:
                        res = cleared_page.evaluate(_FETCH_PDF_JS, pdf_url)
                    except Exception as exc:  # noqa: BLE001
                        last_state = f"fetch failed ({type(exc).__name__}: {str(exc)[:80]})"
                        continue

                    if res.get("error"):
                        last_state = f"fetch error: {str(res['error'])[:80]}"
                        continue
                    status, ct = res.get("status"), res.get("ct")
                    if status != 200 or not res.get("b64"):
                        last_state = f"fetch status={status} ct={ct}"
                        continue
                    body = base64.b64decode(res["b64"])
                    if body[:4] != b"%PDF":
                        last_state = f"fetch 200 but not a PDF (ct={ct}, magic={body[:8]!r})"
                        continue

                    print(f"\nPROBE OK: real PDF, {len(body)} bytes")
                    out_path = Path(args.out) if args.out else None
                    if out_path is not None:
                        if not out_path.parent.exists():
                            out_path.parent.mkdir(parents=True)
                        out_path.write_bytes(body)
                        print(f"  saved -> {out_path}")
                    confirmed = True
                    break
            finally:
                # disconnect only — never kill the human's browser
                try:
                    browser.close()
                except Exception:  # noqa: BLE001,S110
                    pass
    finally:
        pass

    if confirmed:
        print(f"\nLOGIN CONFIRMED -- profile saved at: {profile}")
        print("Chrome stays open; downloads can reuse this profile via CDP on the same port.")
        return 0

    print(f"\nLOGIN NOT CONFIRMED within {args.timeout}s.")
    print(f"  last state: {last_state}")
    print()
    print("  If the log above shows challenged=True the whole time, Cloudflare")
    print("  never let the browser through — try:")
    print("   - clicking the checkbox yourself in the opened window")
    print("   - a different network (campus/VPN) before retrying")
    print("   - a fresh --profile directory")
    if proc is not None and proc.poll() is None:
        print()
        print("  Chrome is still open on the debug port; leaving it for you to inspect.")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130) from None
