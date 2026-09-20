#!/usr/bin/env python3
"""Search USENIX papers through the local ResearchAgent HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
TERMINAL_STATES = {"completed", "partial", "failed"}


class ServiceError(RuntimeError):
    """A readable, non-traceback service failure."""


def _json_request(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed localhost base URL
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {}
        message = detail.get("message") if isinstance(detail, dict) else None
        raise ServiceError(f"产品服务返回 HTTP {error.code}：{message or '请求失败'}") from None
    except (URLError, TimeoutError, OSError):
        raise ServiceError(
            f"无法连接本地 ResearchAgent 服务（{base_url.rstrip('/') }）。请先执行 ./deploy/start.sh。"
        ) from None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise ServiceError("产品服务返回了无法解析的响应。") from None
    if not isinstance(value, dict):
        raise ServiceError("产品服务返回了无效响应。")
    return value


def _years(value: str) -> list[int]:
    try:
        years = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("年份必须是逗号分隔的整数，例如 2024,2025") from None
    if not years:
        raise argparse.ArgumentTypeError("至少提供一个年份")
    return years


def search(base_url: str, query: str, years: list[int], limit: int, poll_interval: float, timeout: float) -> dict:
    job = _json_request(
        base_url,
        "POST",
        "/api/papers/searches",
        {"query": query, "conference_ids": ["usenix-security"], "years": years},
    )
    search_id = job.get("search_id")
    if not isinstance(search_id, str) or not search_id:
        raise ServiceError("产品服务未返回有效 search_id，未生成可导入的结果。")
    deadline = time.monotonic() + timeout
    while True:
        status_payload = _json_request(base_url, "GET", f"/api/papers/searches/{search_id}")
        status = status_payload.get("status")
        if status in TERMINAL_STATES:
            break
        if time.monotonic() >= deadline:
            raise ServiceError("论文检索超过等待时限，未冻结结果；请稍后用产品界面重试。")
        time.sleep(poll_interval)
    if status == "failed":
        raise ServiceError("论文检索任务失败，服务未提供可读结果。")
    results = _json_request(base_url, "GET", f"/api/papers/searches/{search_id}/results?page=1")
    items = results.get("items")
    if not isinstance(items, list):
        raise ServiceError("产品服务未返回候选列表。")
    output = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else item
        output.append(
            {
                "search_id": search_id,
                "candidate_id": item.get("catalog_paper_id") or item.get("candidate_id") or snapshot.get("candidate_id"),
                "title": snapshot.get("title") or item.get("title"),
                "year": snapshot.get("year") or item.get("year"),
                # Async catalog snapshots expose the server-owned official
                # detail page as ``source_page_url``.  Keep the older aliases
                # as compatibility fallbacks, but never accept a client URL.
                "article_url": (
                    snapshot.get("source_page_url")
                    or snapshot.get("article_url")
                    or snapshot.get("official_page_url")
                    or item.get("source_page_url")
                    or item.get("article_url")
                ),
                "abstract_status": snapshot.get("abstract_status") or item.get("abstract_status"),
            }
        )
    return {"search_id": search_id, "status": status, "results": output}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过本地 ResearchAgent 服务检索 USENIX Security 论文")
    parser.add_argument("--query", required=True, help="检索关键词")
    parser.add_argument("--years", required=True, type=_years, help="年份，例如 2024 或 2023,2024")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--poll-interval", type=float, default=1.0, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=300.0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit 必须大于 0")
    try:
        result = search(args.base_url, args.query, args.years, args.limit, max(args.poll_interval, 0.1), args.timeout)
    except ServiceError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
