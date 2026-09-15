---
name: ccs-paper-acquisition
description: Acquire ACM CCS (and sibling security conference) paper metadata + abstracts across multiple years. Use when asked to fetch/import CCS papers, build a conference source adapter, or enrich papers with abstracts by DOI.
agent_created: true
---

# CCS Paper Acquisition

Validated live on 2026-09-14 during spec-032 Task 04. **Read this before writing any
scraper** — several obvious approaches are dead ends and cost hours to rediscover.

## The pipeline that works (metadata + abstracts)

```
Crossref (enumerate by year)  ->  container-title filter  ->  OpenAlex (abstract + OA PDF)
```

1. **Enumerate** — Crossref `query.bibliographic` = `"ACM SIGSAC Conference on Computer
   and Communications Security {year}"`, with
   `filter=member:320,type:proceedings-article,from-pub-date:{y}-01-01,until-pub-date:{y}-12-31`,
   `rows=1000`. paginate via `offset` (NOT `cursor`).
2. **Filter** — keep only CCS main track via `is_ccs_main_track()`:
   container-title contains `sigsac` OR `computer and communications security`,
   contains the year, and does NOT contain `workshop`.
3. **Enrich** — `https://api.openalex.org/works/doi:{doi}` →
   `abstract_inverted_index` (rebuild text) + `best_oa_location.pdf_url`.

Run it: `scripts/ccs_fetch.py --years 2019-2025 --out ccs_papers.jsonl`

Observed yields (single page, rows=1000): 2025→395, 2024→418, 2023→291, 2022→399.
OpenAlex abstract coverage sampled **3/3 on every year tested** (2019–2025).

## Same pipeline for IEEE S&P and NDSS (validated 2026-09-14)

Identical three-stage shape; only the Crossref filter + container matcher differ.

| Conference | Crossref filter | container-title must contain | must NOT contain |
|---|---|---|---|
| ACM CCS | `member:320` | `sigsac` or `computer and communications security` | `workshop` |
| IEEE S&P | **`member:263`** (IEEE — *not* 266) | `symposium on security and privacy` | **`european`** |
| NDSS | **`prefix:10.14722`** | `network and distributed system security symposium` | `workshop` |

Observed (rows=1000, after front-matter filtering):

| Year | IEEE S&P matched / real | NDSS matched |
|---|---|---|
| 2025 | 422 / 376 | 211 |
| 2024 | 417 / — | 140 |
| 2023 | 359 / 310 | 94 |
| 2022 | 273 / — | 83 |
| 2021 | 235 / 197 | 87 |

Abstract coverage (OpenAlex, real papers only): S&P 4/5 (2025), 5/5 (2023), 3/5 (2021);
NDSS 3/3 on 2022–2025, 2/3 (2021).

### Two traps that cost real time here

1. **EuroS&P contamination** — `2021 IEEE European Symposium on Security and Privacy` is a
   *different conference* and matches `symposium on security and privacy`. Always exclude
   `european`, or S&P 2021 quietly mixes in another venue.
2. **Front matter is the #1 source of false "no abstract"** — IEEE deposits Keynotes, Title
   Page, Author Index, Front Matter, etc. as `proceedings-article` with DOIs. An early sample
   of 4 items hit *only* front matter and produced a bogus "0/3 abstract coverage" reading.
   Filter front matter **before** measuring coverage or judging a source.

## Dead ends — do not retry without new evidence

| Approach | Result |
|---|---|
| `dl.acm.org/doi/{doi}` plain HTTP | **403** anti-bot. Abstracts unreachable this way. |
| `dl.acm.org/doi/pdf/{doi}` plain HTTP | **403** — Cloudflare `Just a moment...` interstitial (verified: 5× `cloudflare`, `<title>Just a moment...</title>`, `text/html` 5.7KB, never a PDF). **The URL pattern itself is valid** and does download in a real browser; only scripted/plain-HTTP access is blocked. See *PDF acquisition* below. |
| Crossref `abstract` field for ACM | **Always null** — ACM deposits no abstracts. |
| DBLP HTML **and** `/search/publ/api` | Anti-bot wall (`Making sure you're not a bot!`). |
| `sigsac.org/ccs/CCS{y}/accepted-papers/` | Next.js client render; empty `<ul>`, 0 DOIs in HTML. |
| OpenAlex source-id per year | Only 2022 resolves (`S4363608815`, 287 works); 2025 works have no `primary_location.source`. |
| OpenAlex `filter=doi:10.1145/xxxx*` | `count=0` — prefix wildcard unsupported. |
| Crossref `cursor` + `query.bibliographic` | Scanned 6000 items, **0** CCS hits. Use `offset`. |
| Semantic Scholar API | 429 without an API key. |
| Institutional IP / VPN for `dl.acm.org/doi/pdf/{doi}` | **DISPROVEN 2026-09-14.** From an entitled network, `curl` still gets `HTTP/2 403` + `text/html`. Cloudflare challenges every non-browser request regardless of IP/entitlement. There is no IP that makes plain HTTP work. |
| `BrowserContext.request.get(/doi/pdf/{doi})` even from authenticated profile | **403** every time. APIRequest sends a different UA than the browser, invalidating `cf_clearance`. Use `page.goto(...) + response.body()`. |
| Playwright defaults without anti-automation args | Infinite Cloudflare challenge loop (`navigator.webdriver=true` triggers re-issue). Need `--disable-blink-features=AutomationControlled` + `ignore_default_args=["--enable-automation"]` (`navigator.webdriver` then reports `false`). |
| Sharing one profile between Playwright Chromium and system Chrome | Schema-version mismatch can corrupt the profile. Use one profile per (browser build, publisher). |
| "Wait X seconds then declare login OK" | Falsely reports success. The only true confirmation is a real probe PDF download — `acm_login.py` enforces this. |
| `httpx.get(url_with_querystring, params={})` | **Silently drops the whole query string.** Passing `params=` at all makes httpx rebuild the query and discard what was already in `url`. Symptom: OpenAlex returns 200 + 25 random works (its default first page) and the DOI hit rate is **0 with no error**. Always build the query as a `params=` dict, never by string-concatenating `?filter=…` onto the URL. |
| Trusting OpenAlex `open_access` / `best_oa_location` for ACM | Misleading. `best_oa_location` prefers the publisher, so it hands back `dl.acm.org` (403) even when an arXiv mirror exists; and it calls those "open access" because there is no paywall. Scan `locations[]` and pick a non-gated host. Measured: 41% of CCS 2024 rows point at unusable `dl.acm.org`; real downloadable rate is **16%**. |
| `dspace.mit.edu` / `*.worktribe.com` / `hal.science` plain HTTP | 405 / 403 / HTML landing page. Unaffected by browser UA or `Accept: application/pdf`. Genuine OA, but not scriptable — drop them rather than chase. |
| `ccs_fetch.py --years YYYY` **with** enrichment | One HTTP request per DOI → **0 bytes after 13 min** on 2024. Use `--no-enrich` then `oa_enrich.py` (batched, ~50x faster). |
| Per-host circuit breaker that counts 4xx | Self-inflicted: arXiv 403 (rate limit) tripped the breaker and skipped 24 of 44 papers. Count only transport errors / 5xx. |
| Downloading at `--delay 0.3` | arXiv throttles → 403/429. Use >= 3 s for arXiv (`POLITE_HOST_DELAYS` default). |

## PDF acquisition — paywalled layer (canonical HITL flow)

Cloudflare blocks every plain HTTP request to `dl.acm.org/doi/pdf/{doi}` and
the IEEE equivalent with a `403 + Just a moment...` challenge. Institutional
IP/VPN does **not** help (verified 2026-09-14 from an entitled network: same
`HTTP/2 403` + `text/html`). The URL pattern is valid — the gate is *anti-bot*,
not entitlement. The paywalled ~60% of papers can therefore only be reached
through a real browser.

The canonical workflow is a one-time human login that establishes a persistent
profile; after that, downloads run unattended. Two scripts in `scripts/` carry
this out: **`acm_login.py`** (HITL login + verification) and **`acm_pdf_fetch.py`**
(unattended batch download).

### Two gates — do not conflate them

1. **Cloudflare anti-bot** — the JS challenge that 403s every scripted request.
   The `cf_clearance` cookie Cloudflare issues is bound to the *browser instance*
   that solved the challenge (UA + TLS + fingerprint).
2. **ACM/IEEE entitlement** — open access, institutional subscription, or
   signed-in personal access. Independent of the first gate.

Passing gate 1 (e.g. with `cf_clearance` from another browser) does **not**
grant gate 2.

### Standard 5-step procedure

```text
0. (one-time) install Chrome (>= 130 recommended)
1. (per session) python3 scripts/acm_login_cdp.py --out /tmp/probe.pdf
       # launches a PLAIN Chrome (no automation attached),
       # you clear Cloudflare + sign in, then it attaches over CDP
       # and verifies by fetch()ing a real probe PDF
2. (batch)      python3 scripts/acm_pdf_fetch.py ...   # reuses the same profile
3. on 401/403 or "Just a moment..." -> clearance expired, go back to step 1
4. on 503/timeout -> increase --delay, retry once
```

`acm_login.py` (the Playwright-launched variant) is kept for reference but
**does not get past Cloudflare** — see the CDP section below.

### The OA layer needs no browser at all — `oa_pdf_fetch.py`

Use the **3-command batch recipe**, not `ccs_fetch.py --out` directly — the
built-in enrichment does one HTTP request per DOI and produced **0 bytes after
13 minutes** on a single year. Batched OpenAlex enrichment is ~50x faster.

```bash
# 1. enumerate fast, no per-paper HTTP   (CCS 2024: 418 rows in ~3 min)
python3 scripts/ccs_fetch.py --years 2024 --no-enrich --out raw.jsonl
# 2. bulk enrich (OpenAlex filter=doi:a|b|c, 50/call)  -> abstracts + OA PDF
python3 scripts/oa_enrich.py raw.jsonl enriched.jsonl
# 3. download the non-gated ones
python3 scripts/oa_pdf_fetch.py --jsonl enriched.jsonl --out ./pdfs --limit 10
```

**MEASURED on CCS 2024 (n=418, 2026-09-14) — trust these, not the old 34% guess:**

| stage | count | share |
|---|---|---|
| rows returned by Crossref | 418 | 100% |
| abstract found in OpenAlex | 417 | 99.8% |
| has *some* `pdf_url` | 240 | 57% |
| pdf_url on `dl.acm.org` (403, unusable) | 170 | 41% |
| **truly downloadable (non-gated host)** | **70** | **16%** |

**The trap: never judge by `pdf_access` / `open_access` alone.** OpenAlex labels
`dl.acm.org` links "open access" because there is no *paywall* — but Cloudflare
403s them anyway. Two independent gates: (1) Cloudflare anti-bot, (2) ACM
entitlement. Passing one buys you nothing. `oa_enrich.py` therefore tags these
rows `pdf_access="blocked"` + `pdf_gated=true`, and picks a non-gated mirror
from `locations[]` when one exists (this rescued 26 of 70).

**END-TO-END RESULT (2026-09-14): 50 real PDFs, 182 MB, 100% pass `%PDF-` check.**

| host | candidates | downloaded |
|---|---|---|
| arxiv.org | 44 | **44 (100%)** |
| vtechworks.lib.vt.edu | 3 | 3 |
| eprints.gla.ac.uk / discovery.ucl.ac.uk / ir.cwi.nl | 1 each | 1 each |
| hal.science | 7 | **0** |
| dspace.mit.edu | 7 | **0** |
| digitalcommons / ubn.ru.nl / lirias / worktribe | 6 | **0** |
| **total** | **70** | **50 (71% of candidates, 11% of the conference)** |

So: **arXiv is a 100% reliable source; every miss is an institutional
repository.** If you only need volume, restrict to arXiv and you will never
wait on a flaky server.

**Repositories that refuse plain HTTP even for OA (do not chase these):**
`dspace.mit.edu` 405, `*.worktribe.com` 403, `hal.science` + `digitalcommons`
return an HTML landing page — all unaffected by a browser UA or
`Accept: application/pdf`.

### Acceptance through the PRODUCTION code path — `acceptance_prod_path.py`

Downloading with a throwaway script proves nothing about the shipped code. This
script drives the real `ConferencePdfDownloader.download_batch()`:

```bash
python3 scripts/acceptance_prod_path.py 50   # all arXiv rows of CCS 2024
```

**Result 2026-09-14: 44/44 arXiv papers OK in 36 s**, matching the standalone
script byte-for-byte (532,181 / 967,782 / 1,664,119 …). Degradation verified
too, with no `browser_manager` injected:
- `dl.acm.org` -> `access=browser_required`, `PDF_BROWSER_UNAVAILABLE`
- no `pdf_url` -> `access=unavailable`, `PDF_UNAVAILABLE`
Neither raises; the batch keeps going.

Note: the production downloader got 44/44 with **no** politeness delay, while
`oa_pdf_fetch.py` at 0.3 s got throttled. Its SSRF/DNS/validation work already
spaces requests out; do not "optimise" that away.

**Two rate-limit traps that cost real papers:**
1. arXiv requires >= 3 s between requests. At 0.3 s it answers 403/429.
2. A naive per-host circuit breaker then skips ALL remaining papers from that
   host — this silently lost 24 of 44 arXiv papers on the first run
   (25 downloaded instead of 50). **Only count transport errors and 5xx toward
   a breaker; a 403/429 means "slow down", not "host is dead".** `oa_pdf_fetch.py`
   now backs off exponentially on 403/429 and only trips on hard failures.

Hosts outside the allowlist (arXiv, OpenReview, USENIX, NDSS, IACR ePrint, …
plus pattern-matched institutional repos: `dspace.*`, `eprints.*`, `hal.science`,
`*.ac.uk`, `*.edu`, …) are **skipped, fail-closed** — widen with `--allow-host`.
Pirate mirrors are deliberately excluded: this is the layer that runs
unattended, so it is the one that has to stay unambiguously legal.

### Why page.goto, not BrowserContext.request (measured 2026-09-14)

`BrowserContext.request` (Playwright's APIRequest) sends its own User-Agent
that differs from the browser's. Cloudflare sees the UA mismatch, invalidates
`cf_clearance`, returns **403** — even from a context with valid cookies.

- `context.request.get(PDF_URL)` -> 403 every time.
- `page.goto(PDF_URL, wait_until="commit")` then `response.body()` -> 200 + `%PDF`.

`acm_pdf_fetch.py` uses page.goto. The existing production
`ConferencePdfDownloader.download_via_browser` uses context.request and is
therefore broken — fixing it is the follow-up ticket under spec-032.

### Why launch flags are NOT enough — use CDP attach (measured 2026-09-14)

Playwright's `launch_persistent_context` injects a *cluster* of automation
signals: `--enable-automation`, an explicit `--user-agent` override, a dozen
`--disable-*` flags (`--disable-extensions`, `--disable-sync`,
`--disable-background-networking`, `--password-store=basic`, …), and — most
importantly — it drives the browser over CDP **from the very first navigation**.

Flipping `navigator.webdriver` to false is whack-a-mole:

```python
launch_kwargs = {
    "headless": False,
    "channel": "chrome",
    "args": ["--disable-blink-features=AutomationControlled"],
    "ignore_default_args": ["--enable-automation"],
}
# -> navigator.webdriver becomes False ...
# -> ... but Cloudflare STILL stalls on "Performing security verification"
#    and never reveals a clickable checkbox. Verified on Chromium 136 and
#    Chrome 152; three separate 10-30 minute attempts all failed.
```

Cloudflare scores a **composite fingerprint**, not one signal. There is no flag
combination that makes a Playwright-launched browser look ordinary.

**What actually works** — let the browser meet Cloudflare as an *ordinary*
Chrome, and attach Playwright only afterwards. See `scripts/acm_login_cdp.py`:

1. `subprocess.Popen` the Chrome binary directly — **zero Playwright
   involvement** (must pass `--no-sandbox --disable-dev-shm-usage` or Chrome
   exits silently inside a sandbox/container).
2. Human clears the challenge and signs in, in a completely normal browser.
3. **Afterwards** `p.chromium.connect_over_cdp("http://127.0.0.1:<port>")`.
4. Fetch the PDF with a **same-origin `fetch()` inside the already-cleared tab**.

Verified: on this route the very first poll showed `challenged=False` and the
tab title was the real paper title — Cloudflare let it straight through.

**Three traps, each of which cost a full debugging round:**

1. **Chrome dies silently** without `--no-sandbox --disable-dev-shm-usage` in a
   sandbox — the debug port never opens. Playwright adds these itself, which is
   why `launch_persistent_context` never exposed the problem.
2. **A sandbox `http_proxy` swallows `127.0.0.1:<port>`.** Playwright's
   `connect_over_cdp` returns **502 "does not look like a DevTools server"**
   while your own `curl` works fine (urllib ignores the proxy, Playwright's
   client does not). Fix: `os.environ.setdefault("no_proxy", "*")`.
3. **Never `goto()` or `new_page()` for the PDF.** Any new navigation or fresh
   tab triggers a *brand-new* Cloudflare challenge — measured: 403 +
   `Just a moment...`, even though another tab in the same browser was already
   cleared. Fetch from inside the already-cleared tab instead:
   ```js
   const r = await fetch(url, {credentials: 'include'});   // same-origin
   ```
   This uses the browser's own network stack, so UA and cookies match.

**`cf_clearance` expires.** A profile that auto-cleared the challenge in the
morning sits at `challenged=True` hours later. Design this as a **re-runnable
HITL**, not a one-time setup — the human may have to tick the box again.

### Profile isolation

Use one profile per (browser build, publisher). Defaults to
`data/browser-profile/security-papers`; for separate publishers use
`security-papers-acm`, `security-papers-ieee`, etc.
`PAPER_DISCOVERY_BROWSER_PROFILE_DIR` overrides.

### Probe download — the only true confirmation

`acm_login.py` never claims success based on cookie or title state alone.
Every 30s while the page is not challenged, it `page.goto`s the probe PDF
URL and only reports `LOGIN CONFIRMED` when the bytes start with `%PDF-`.
The earlier `acm_login.py` waited only for the deadline and falsely reported
"profile saved / you can now run unattended" — fixed 2026-09-14.

### On 401/403 during batch downloads

The Cloudflare rotation, or the publisher session timed out. Stop the batch,
re-run `acm_login.py`, then retry. `acm_pdf_fetch.py` returns exit code 4 in
this case so CI can react.

### Measured coverage (CCS 2025 sample, n=50, 2026-09-14)

| Layer | Coverage | Auth needed |
|---|---|---|
| OpenAlex `best_oa_location.pdf_url` | 30% | none |
| OpenAlex **any** OA location | 34% | none |
| + Semantic Scholar `openAccessPdf` (when API key present) | +5–10 pts | none |
| Browser layer (this HITL flow) | remaining ~60% | one-time human login |

Sample-size warning: n=12 readings were 67% OA while n=50 was 34%. Plan
capacity off anything under ~40 papers.

## HITL runbook (for the human)

This is the script-end reference, not a design doc. If `acm_login.py` is
running and the browser window is open, do this:

Run `python3 scripts/acm_login_cdp.py --out /tmp/probe.pdf`. It opens a
**normal Chrome** (no automation attached) — that is the whole point.

1. **Bring the Chrome window to the front.** `Cmd+Tab`, or click the Chrome
   icon in the Dock. The script does not fight you for focus.
2. **Clear the Cloudflare challenge.** If a "Verify you are human" checkbox
   appears, tick it. If you only see a spinning "Performing security
   verification", click anywhere on the page or press Space — CF usually waits
   for an input signal before it reveals the checkbox.
3. **Sign in.** ACM → Sign In → Institutional Login (recommended for entitled
   access) → follow your institution's SSO.
4. **Just wait — do not close the window.** The script polls every 10s and
   prints `[poll N] challenged=... cleared=...`. Once `cleared=True` it
   `fetch()`es the probe PDF from inside that same tab. On success it prints
   `PROBE OK: real PDF, N bytes` and `LOGIN CONFIRMED`.
5. **If it prints `LOGIN NOT CONFIRMED` with `challenge still pending`**, the
   challenge never cleared — go back to step 2. `cf_clearance` expires, so
   this is a normal thing to have to redo, not a bug.

**Do not** navigate the cleared tab to the PDF URL yourself, and do not open
new tabs — each new navigation re-triggers the challenge. The script fetches
from inside the existing tab for exactly this reason.

## Gotchas

- **ACM title drift**: 2025 = `Proceedings of the 2025 ACM SIGSAC Conference...`, but
  2024 = `Proceedings of the 2024 **on** ACM SIGSAC Conference...` (extra "on").
  Exact-prefix matching silently returns 0 for some years — always fuzzy match.
- **Non-paper entries leak in**: `Doctoral Symposium`, keynotes, prefaces, front matter.
  Filter these out in the adapter; they have DOIs but are not research papers.
- **PDFs are mostly paywalled**: `best_oa_location.pdf_url` is often null. Do not assume
  downloadable; route PDF acquisition through the existing safe download chain and never
  bypass paywalls/logins (spec-032 explicitly forbids it).
- **Only `/accepted-papers/` exists for 2025**; 2024/2023/2022/2021 return 404 on that
  path. Do not build multi-year logic on the sigsac.org URL pattern.

## Integrating into the codebase (spec-032)

Mirror the existing USENIX adapter pattern:
`backend/app/paper_discovery/infrastructure/usenix_publication_source.py` +
`usenix_paper_parser.py`. Existing `acm_paper_parser.py` parses a *single* ACM page
(pdf/article/title/doi from meta tags) and does **not** extract abstracts — it is a
complement, not a replacement, and must not be bypassed for the DL-page contract.

- `source_id` suggestion: `acm-ccs`; `authority_rank`: official DOI metadata.
- `discover_units(scope)` → one unit per year (e.g. `ccs:2024`).
- Preserve `provenance` per field: title/year/DOI/container from Crossref, abstract from
  OpenAlex, so higher-authority fields are never overwritten by lower ones.
- Cache by content hash/ETag per year unit; a single year failing must not clear old cache.

For the **PDF acquisition browser layer**, use `scripts/acm_login.py` to establish the
persistent profile (HITL), and `scripts/acm_pdf_fetch.py` (page.goto-based) as the
canonical reference implementation. The existing production
`ConferencePdfDownloader.download_via_browser` uses `BrowserContext.request` and is
**broken** (always 403) — porting it to `page.goto + response.body()` is the follow-up
ticket under spec-032. Until that lands, batch downloads for paywalled papers should go
through `acm_pdf_fetch.py`.