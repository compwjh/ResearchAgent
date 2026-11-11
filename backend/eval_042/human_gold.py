"""Spec-047 Task-04 (P2①): 脱敏人工 gold 集加载与一致率计算。

只提供两个纯能力（复用 eval_042 既有 report 结构，不建第二套评测框架）：

- :func:`load_human_gold` 读取脱敏 gold JSON，逐条做字段白名单 / gold_source
  字面 / label 合法域 / item_id 非空校验，返回合法条目列表；
- :func:`compute_human_agree_rate` 以 report ``items[].trace_id`` 与 gold
  ``item_id`` join，按「判官多数标签 == human_label」计算一致率。

隐私约束（spec-042:236）：gold 文件只含 item_id + human_label + annotator +
annotated_at + gold_source，绝不含 input/output/prompt/prior_context/凭据原文；
report 层只把统计数字写进报告，gold 条目原文不落盘。

反伪造（spec-042:245）：``gold_source`` 必须字面为 ``"human"``；构造/合成
gold 一律剔除。本期用户未提供真实人工标签，gold 文件以空 items 落盘，
``human_agree_rate`` 保持 ``null``（真实值待人工标注后回填）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import MEMORY_ENUMS, QUALITY_ENUMS

HUMAN_GOLD_SCHEMA_VERSION = "human-gold-v1"
MIN_HUMAN_GOLD_ITEMS = 20
HUMAN_GOLD_SOURCE = "human"

# item 级字段白名单：任何白名单外的键（尤其 input/output/prompt/credentials）
# 都使该条目无效，从源头杜绝把含原文的数据集当作人工 gold 复用。
_HUMAN_GOLD_ITEM_FIELDS = frozenset(
    {"item_id", "human_label", "annotator", "annotated_at", "gold_source"}
)
# 顶层允许键（其余键出现即拒绝加载，不读取、不落盘）。
_HUMAN_GOLD_TOP_FIELDS = frozenset(
    {"schema_version", "note", "source", "annotated_at", "items"}
)
# human_label 合法域：与 config.py:53-59 的 QUALITY_ENUMS / MEMORY_ENUMS 对齐。
_VALID_HUMAN_LABELS = frozenset(QUALITY_ENUMS) | frozenset(MEMORY_ENUMS)


@dataclass(frozen=True)
class HumanGoldFile:
    """一次 gold 加载的可信结果（由 report.py 显式传入，不来自不可信 document）。"""

    items: tuple[dict[str, Any], ...]
    sha256: str
    error: str | None = None
    skipped: int = 0

    @property
    def source(self) -> str:
        return HUMAN_GOLD_SOURCE


def _valid_item(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    if not set(raw.keys()).issubset(_HUMAN_GOLD_ITEM_FIELDS):
        # 脱敏护栏：含白名单外字段（prompt / input / ...）的条目一律拒绝。
        return None
    item_id = raw.get("item_id")
    if not isinstance(item_id, str) or not item_id.strip():
        return None
    human_label = raw.get("human_label")
    if not isinstance(human_label, str) or human_label not in _VALID_HUMAN_LABELS:
        return None
    if raw.get("gold_source") != HUMAN_GOLD_SOURCE:
        return None
    return dict(raw)


def load_human_gold_file(path: str | Path) -> HumanGoldFile:
    """读取并校验脱敏人工 gold 文件，永远返回 ``HumanGoldFile``。

    文件不存在 / JSON 非法 / 顶层字段越界 / schema_version 不匹配 / items 非列表
    均以 ``error`` 承载原因且 ``items`` 为空；report 层据此降级为
    ``human_agree_rate=null``，绝不因 gold 异常影响评测主流程。
    """
    if not path:
        return HumanGoldFile((), "", error="gold path missing")
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as exc:
        return HumanGoldFile((), "", error=f"gold file unreadable: {type(exc).__name__}")
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return HumanGoldFile(
            (), sha256, error=f"gold file is not valid JSON: {type(exc).__name__}"
        )
    if not isinstance(data, Mapping):
        return HumanGoldFile((), sha256, error="gold file root must be an object")
    if set(data.keys()) - _HUMAN_GOLD_TOP_FIELDS:
        return HumanGoldFile((), sha256, error="gold file has non-schema top-level fields")
    schema_version = data.get("schema_version")
    if schema_version is not None and schema_version != HUMAN_GOLD_SCHEMA_VERSION:
        return HumanGoldFile((), sha256, error="unsupported schema_version")
    raw_items = data.get("items")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        return HumanGoldFile((), sha256, error="gold items must be a list")

    valid: list[dict[str, Any]] = []
    skipped = 0
    for raw in raw_items:
        item = _valid_item(raw)
        if item is None:
            skipped += 1
        else:
            valid.append(item)
    return HumanGoldFile(tuple(valid), sha256, skipped=skipped)


def load_human_gold(path: str | Path) -> list[dict[str, Any]]:
    """返回 gold 文件中所有合法人工标注条目（空文件 / 全非法 -> ``[]``）。"""
    return list(load_human_gold_file(path).items)


def _scored_by_trace(report_items: object) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    if not isinstance(report_items, Sequence) or isinstance(
        report_items, (str, bytes, bytearray)
    ):
        return index
    for item in report_items:
        if not isinstance(item, Mapping) or item.get("status") != "scored":
            continue
        trace_id = item.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            index[trace_id] = item
    return index


def human_agree_metrics(report_items: object, gold_items: object) -> dict[str, Any]:
    """按口径计算分子/分母，返回可复算 metrics（rate 为 None 表示不计算）。

    分母 ``n_evaluated`` = gold 条目中能与 report scored item 的 trace_id join、
    且 ``gold_source == "human"``、``human_label`` 合法的条数；
    分子 ``n_agree`` = 其中判官多数标签（report item ``label``，由 runner 的
    ``_majority_label`` 多数投票产生）== human_label 的条数。
    ``n_evaluated == 0`` 或 ``< MIN_HUMAN_GOLD_ITEMS``（N<20）-> rate=None + reason。
    """
    n_min = MIN_HUMAN_GOLD_ITEMS
    n_agree = 0
    n_evaluated = 0
    scored = _scored_by_trace(report_items)
    gold_list = (
        gold_items
        if isinstance(gold_items, Sequence)
        and not isinstance(gold_items, (str, bytes, bytearray))
        else []
    )
    for gold in gold_list:
        if not isinstance(gold, Mapping):
            continue
        if gold.get("gold_source") != HUMAN_GOLD_SOURCE:
            continue
        human_label = gold.get("human_label")
        if not isinstance(human_label, str) or human_label not in _VALID_HUMAN_LABELS:
            continue
        item_id = gold.get("item_id")
        if not isinstance(item_id, str) or item_id not in scored:
            continue
        n_evaluated += 1
        if scored[item_id].get("label") == human_label:
            n_agree += 1
    rate: float | None = None
    if n_evaluated == 0:
        reason = "no scored human-gold items joined the report"
    elif n_evaluated < n_min:
        reason = f"n_evaluated={n_evaluated} below n_min={n_min}"
    else:
        rate = round(n_agree / n_evaluated, 4)
        reason = "computed"
    return {
        "n_agree": n_agree,
        "n_evaluated": n_evaluated,
        "n_min": n_min,
        "rate": rate,
        "reason": reason,
    }


def compute_human_agree_rate(report_items: object, gold_items: object) -> float | None:
    """判官多数标签与人工标签一致率 ``round(n_agree / n_evaluated, 4)``。

    分母为 0、N<20 或无有效人工标注时返回 ``None``（不伪造数值）。
    """
    return human_agree_metrics(report_items, gold_items)["rate"]


__all__ = [
    "HUMAN_GOLD_SCHEMA_VERSION",
    "HUMAN_GOLD_SOURCE",
    "MIN_HUMAN_GOLD_ITEMS",
    "HumanGoldFile",
    "compute_human_agree_rate",
    "human_agree_metrics",
    "load_human_gold",
    "load_human_gold_file",
]
