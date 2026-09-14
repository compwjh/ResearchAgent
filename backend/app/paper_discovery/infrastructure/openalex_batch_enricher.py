"""OpenAlex **批量**富化：把「每条 DOI 一次请求」降到「每 50 条一次请求」。

为什么需要它
------------
三个会议适配器的 ``enrich_record()`` 原本对每条记录单独请求
``https://api.openalex.org/works/doi:{doi}``。实测 NDSS 2024（140 条）耗时
**142 秒**，且条件请求/ETag 缓存只覆盖目录抓取（Crossref 层），**不覆盖富化**，
所以重复同步也省不掉这笔开销（第二次 142.1 秒，``cached_years=()``）。

OpenAlex 支持 ``filter=doi:a|b|c|...``（一次最多 50 个），本模块提供构造与解析，
把同样的工作压到每批一次请求（实测 418 条约 10 秒，约 40 倍）。

安全：DOI 注入防护（本模块最重要的约束）
----------------------------------------
``filter=doi:`` 后面拼的是**查询语法**，不是普通参数值。如果直接把任意字符串拼进去，
一个形如 ``10.1/x|foo`` 或带空格的 DOI 就能注入额外过滤条件、改变整个查询语义。
因此：

- 只有符合严格 DOI 形态、且**不含任何分隔符/空白/引号/括号**的字符串才会进批量；
- 其余一律返回 ``None``，调用方**退回单条请求**（保证行为不变，绝不静默丢弃）；
- 最终 URL 用 ``urlencode`` 构造，并仍由调用方过既有的 ``validate_url``
  （含 DNS / 内网隔离 / 主机白名单）。

本模块只做「拼 URL + 解析响应」，**不自己发请求**：HTTP 出口、限流、``validate_url``、
告警码语义全部留在各适配器里，避免第二套网络栈。
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlencode

#: OpenAlex ``filter=doi:`` 单次最多支持的 DOI 个数（官方上限 50）。
OPENALEX_BATCH_SIZE = 50

#: 严格的 DOI 形态：``10.<注册码>/<后缀>``。注册码 4–9 位数字，后缀非空。
_DOI_STRICT = re.compile(r"^10\.\d{4,9}/\S+$")
#: 任何可能改变 OpenAlex 查询语义的字符：管道/与号/空白/引号/括号/尖括号。
#: 命中即视为不可安全拼入 filter，调用方退回单条请求。
_UNSAFE_CHARS = re.compile(r"[|&\s\"'<>()]")


def batch_safe_doi(doi: Any) -> Optional[str]:
    """返回可安全拼进 ``filter=doi:`` 的 DOI；不可信时返回 ``None``。

    返回 ``None`` **不代表这条记录不富化**，而是「不能进批量」——调用方必须退回
    原有的单条请求路径，保证富化结果与改动前完全一致。
    """
    if not isinstance(doi, str):
        return None
    value = doi.strip()
    if not value or _UNSAFE_CHARS.search(value) or not _DOI_STRICT.match(value):
        return None
    return value


def build_batch_url(base: str, dois: list[str], *, select: str, per_page: int) -> str:
    """构造批量查询 URL；``dois`` 必须是已通过 :func:`batch_safe_doi` 的列表。"""
    safe = [doi for doi in (batch_safe_doi(item) for item in dois) if doi]
    if not safe:
        raise ValueError("no batch-safe DOI")
    query = urlencode(
        {
            "filter": "doi:" + "|".join(safe),
            "select": select,
            "per-page": str(per_page),
        }
    )
    return f"{base}?{query}"


def works_by_doi(payload: Any) -> dict[str, dict[str, Any]]:
    """把 OpenAlex 批量响应的 ``results`` 按规范化 DOI 索引。

    只接受形态正常的条目；任何异常条目直接跳过（由调用方按「未命中」处理），
    绝不让脏数据盖掉已有字段。
    """
    indexed: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return indexed
    results = payload.get("results")
    if not isinstance(results, list):
        return indexed
    for work in results:
        if not isinstance(work, dict):
            continue
        key = _normalize(work.get("doi"))
        if key:
            indexed[key] = work
    return indexed


def _normalize(doi: Any) -> str:
    return str(doi or "").replace("https://doi.org/", "").strip().lower()


__all__ = [
    "OPENALEX_BATCH_SIZE",
    "batch_safe_doi",
    "build_batch_url",
    "works_by_doi",
]
