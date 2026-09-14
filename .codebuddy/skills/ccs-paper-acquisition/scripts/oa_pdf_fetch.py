#!/usr/bin/env python3
"""Batch-download the OPEN ACCESS PDFs identified by `ccs_fetch.py`.

This is the layer that needs **no browser, no login, and no Cloudflare
clearance**: OpenAlex points at arXiv / institutional repositories /
publisher OA mirrors, and those serve PDFs to plain HTTP clients.

MEASURED coverage (CCS 2024, n=418, 2026-09-14):
  - 417/418 (99.8%) enriched with an abstract from OpenAlex
  - 240/418 (57%)  have *some* pdf_url in OpenAlex
  -  70/418 (16%)  are TRULY downloadable here — the other 170 point at
                   dl.acm.org, which 403s every non-browser client.
Beware the trap: OpenAlex labels dl.acm.org links "open access" (no paywall),
but Cloudflare still blocks them. Always judge by *host*, never by `pdf_access`
alone — `oa_enrich.py` already tags those rows `pdf_access="blocked"`.
The remaining ~84% needs the HITL browser route — see `acm_login_cdp.py`.

Works on any JSONL produced by `ccs_fetch.py`, for CCS / IEEE S&P / NDSS.

Usage
-----
    python3 oa_pdf_fetch.py --jsonl ccs_2024.jsonl --out ./pdfs
    python3 oa_pdf_fetch.py --jsonl ccs_2024.jsonl --out ./pdfs --limit 10
    python3 oa_pdf_fetch.py --jsonl papers.jsonl --out ./pdfs --allow-host arxiv.org

Exit codes
----------
    0  all requested papers downloaded
    1  bad input / missing dependency
    3  at least one failed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx not installed: pip install httpx", file=sys.stderr)
    raise SystemExit(1) from None

#: Hosts we are willing to fetch from by default. Deliberately conservative —
#: pass --allow-host to widen. (Pirate mirrors are intentionally NOT included.)
DEFAULT_OA_HOSTS = (
    "arxiv.org",
    "export.arxiv.org",
    "www.arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "www.usenix.org",
    "www.ndss-symposium.org",
    "eprint.iacr.org",
    "link.springer.com",
    "rd.springer.com",
    "www.tandfonline.com",
    "academic.oup.com",
)

#: Institutional / subject repositories. These are legit self-archived copies
#: (Green OA) and serve PDFs to plain HTTP clients. Matched by pattern because
#: there are thousands of them and enumerating is hopeless. Measured on CCS 2024
#: these contributed 26 of the 70 downloadable PDFs — without them you lose
#: more than a third of the OA harvest.
REPO_HOST_PATTERNS = (
    r"^dspace\.",
    r"^eprints\.",
    r"^ir\.",
    r"^lirias\.",
    r"^repository\.",
    r"^digitalcommons\.",
    r"^scholarship\.",
    r"^works\.be\.press$",
    # subdomain-agnostic: inria.hal.science is as legit as hal.science
    r"hal\.science$",
    r"escholarship\.org$",
    r"zora\.uzh\.ch$",
    r"unige\.it$",
    r"vtechworks\.lib\.vt\.edu$",
    r"worktribe\.com$",
    r"ru\.nl$",
    r"ac\.uk$",
    r"\.edu$",
    # repositorio / repositori / repositories (ES, IT, PT, NL…)
    r"repositor",
    r"^oar\.",
    r"^oa\.",
)

#: DOI resolvers are not PDF hosts — OpenAlex hands back `https://doi.org/10.14722/...`
#: for NDSS, which redirects to the real file on ndss-symposium.org. Rejecting
#: doi.org would throw away a conference that is 100% open access. Instead we
#: follow the redirect and re-check the FINAL host against the allowlist.
DOI_RESOLVERS = {"doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"}

#: Minimum seconds between two requests to the same host, per arXiv's published
#: rate-limit guidance. Overridden by --delay when that is larger.
POLITE_HOST_DELAYS = {"arxiv.org": 3.0, "export.arxiv.org": 3.0}

MAX_BYTES = 50 * 1024 * 1024
#: A real browser UA, not a "bot/1.0" one — several repositories (Worktribe,
#: DSpace 7) reject any custom UA outright while accepting a Chrome string.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def is_repo_host(host: str) -> bool:
    return any(re.search(pattern, host) for pattern in REPO_HOST_PATTERNS)


def safe_name(value: str) -> str:
    kept = [ch if (ch.isalnum() or ch in "._-") else "_" for ch in (value or "")]
    return ("".join(kept) or "paper")[:120]


def load_oa_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if not record.get("pdf_url"):
                continue
            # `oa_enrich.py` marks Cloudflare-gated hosts as "blocked"; skip them
            # even though OpenAlex calls them open access.
            if record.get("pdf_access") == "blocked" or record.get("pdf_gated"):
                continue
            records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch download open-access PDFs from a ccs_fetch JSONL.")
    parser.add_argument("--jsonl", required=True, help="JSONL produced by ccs_fetch.py (enriched)")
    parser.add_argument("--out", default="./pdfs", help="output directory (default ./pdfs)")
    parser.add_argument("--limit", type=int, default=0, help="only the first N OA papers (0 = all)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between downloads (default 1.0)")
    parser.add_argument("--allow-host", action="append", default=[], help="extra host to allow (repeatable)")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES, help="per-file size cap")
    parser.add_argument(
        "--host-fail-limit",
        type=int,
        default=3,
        help="after N transport/5xx failures on one host, skip its remaining papers (default 3)",
    )
    parser.add_argument(
        "--host-delay",
        action="append",
        default=[],
        help="per-host minimum delay, e.g. --host-delay arxiv.org=3 (repeatable)",
    )
    args = parser.parse_args()

    source = Path(args.jsonl)
    if not source.exists():
        print(f"no such file: {source}", file=sys.stderr)
        return 1

    allowed = {host.lower() for host in DEFAULT_OA_HOSTS}
    allowed.update(host.lower() for host in args.allow_host)
    # institutional repositories are frequently slow or stalled (repository.ubn.ru.nl
    # hung a whole 13-minute run) -> fail fast instead of burning 60s per row.
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
    host_failures: dict[str, int] = {}
    breaker = max(1, args.host_fail_limit)
    # Per-host politeness. arXiv's own rate-limit guidance is >=3s between
    # requests; hammering it at 0.3s earns 403/429 and, with a naive per-host
    # circuit breaker, silently skips 24 of 44 papers. BEWARE: only count
    # *transport* failures / 5xx toward the breaker — a 403/429 means "slow
    # down", not "this host is dead".
    polite = dict(POLITE_HOST_DELAYS)
    for item in args.host_delay:
        name, _, value = item.partition("=")
        if name and value:
            try:
                polite[name.lower()] = float(value)
            except ValueError:
                pass

    records = load_oa_records(source)
    if args.limit:
        records = records[: args.limit]

    out_dir = Path(args.out)
    if not out_dir.exists():
        out_dir.mkdir(parents=True)

    print(f"source  : {source}")
    print(f"output  : {out_dir}")
    print(f"OA rows : {len(records)}")
    print()

    ok = 0
    failures: list[tuple[str, str]] = []

    with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        for index, record in enumerate(records, start=1):
            doi = record.get("doi", "") or ""
            url = record["pdf_url"]
            host = host_of(url)
            label = doi or url

            resolving = host in DOI_RESOLVERS
            if not resolving and host not in allowed and not is_repo_host(host):
                failures.append((label, f"host not allowed: {host}"))
                print(f"[{index}/{len(records)}] SKIP  host={host}")
                continue

            if host_failures.get(host, 0) >= breaker:
                print(f"[{index}/{len(records)}] SKIP  host={host} (熔断：已失败 {host_failures[host]} 次)")
                continue

            host_delay = max(args.delay, polite.get(host, 0.0))

            def _note_failure(hard: bool = True) -> None:
                """`hard` = transport error or 5xx. 4xx is 'slow down', not 'dead host'."""
                if hard:
                    host_failures[host] = host_failures.get(host, 0) + 1

            try:
                with client.stream("GET", url) as response:
                    if resolving:
                        # re-evaluate after the DOI redirect lands
                        final_host = host_of(str(response.url))
                        if final_host not in allowed and not is_repo_host(final_host):
                            failures.append((label, f"host not allowed after redirect: {final_host}"))
                            print(f"[{index}/{len(records)}] SKIP  重定向到未授权 host={final_host}")
                            continue
                    if response.status_code != 200:
                        failures.append((label, f"HTTP {response.status_code}"))
                        print(f"[{index}/{len(records)}] HTTP {response.status_code}  {label}")
                        # 429/403 = rate limited: back off hard, but do NOT trip the
                        # breaker — the host is fine, we are just too fast.
                        if response.status_code in (403, 429):
                            polite[host] = min(polite.get(host, host_delay) * 2, 30.0)
                            print(f"          限速，{host} 间隔提高到 {polite[host]:.1f}s")
                            _note_failure(False)
                        else:
                            _note_failure(response.status_code >= 500)
                        time.sleep(host_delay)
                        continue
                    chunks: list[bytes] = []
                    total = 0
                    too_big = False
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total > args.max_bytes:
                            too_big = True
                            break
                    if too_big:
                        failures.append((label, f"too large (>{args.max_bytes} bytes)"))
                        print(f"[{index}/{len(records)}] TOO LARGE  {label}")
                        _note_failure(False)
                        time.sleep(host_delay)
                        continue
                    body = b"".join(chunks)
            except Exception as exc:  # noqa: BLE001
                failures.append((label, f"{type(exc).__name__}: {str(exc)[:60]}"))
                print(f"[{index}/{len(records)}] FAIL {type(exc).__name__}  {label}")
                _note_failure()
                time.sleep(host_delay)
                continue

            if body[:4] != b"%PDF":
                failures.append((label, f"not a PDF (magic={body[:8]!r})"))
                print(f"[{index}/{len(records)}] NOT A PDF  {label}")
                _note_failure(False)
                time.sleep(host_delay)
                continue

            target = out_dir / f"{safe_name(doi)}.pdf"
            # resume: never re-download a file we already have intact
            if target.exists() and target.stat().st_size > 1024 and target.read_bytes()[:4] == b"%PDF":
                ok += 1
                print(f"[{index}/{len(records)}] 已存在  {target.name}")
                time.sleep(0.05)
                continue
            target.write_bytes(body)
            ok += 1
            print(f"[{index}/{len(records)}] OK {len(body):>9,} bytes  {target.name}")
            time.sleep(host_delay)

    print(f"\nSummary: ok={ok} fail={len(failures)} total={len(records)}")
    if failures:
        print("\nFailures (first 10):")
        for label, why in failures[:10]:
            print(f"  {label}: {why}")
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
