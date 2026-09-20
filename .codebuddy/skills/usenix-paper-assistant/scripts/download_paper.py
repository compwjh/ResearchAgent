#!/usr/bin/env python3
"""Import one server-owned search candidate through ResearchAgent."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _request(base_url: str, search_id: str, candidate_id: str) -> dict:
    body = json.dumps({"search_id": search_id, "candidate_id": candidate_id}).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/api/papers/imports",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed localhost base URL
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {}
        message = detail.get("message") if isinstance(detail, dict) else None
        raise RuntimeError(f"产品服务返回 HTTP {error.code}：{message or '导入失败'}") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError(
            f"无法连接本地 ResearchAgent 服务（{base_url.rstrip('/') }）。请先执行 ./deploy/start.sh。"
        ) from None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("产品服务返回了无法解析的响应，未确认导入结果。") from None
    if not isinstance(value, dict):
        raise RuntimeError("产品服务返回了无效导入响应。")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入一次 USENIX 搜索结果中的论文")
    parser.add_argument("--search-id", required=True, help="search_papers.py 返回的 search_id")
    parser.add_argument("--candidate-id", required=True, help="search_papers.py 返回的 candidate_id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = _request(args.base_url, args.search_id, args.candidate_id)
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
