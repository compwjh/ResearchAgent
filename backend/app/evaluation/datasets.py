"""内置标注评测集的只读加载与白名单校验（无 DB、无迁移）。

所有 ``dataset_id`` 必须命中 ``GOLD_DIR`` 下的 ``builtin-<id>.json``，且 id
只允许小写字母/数字/连字符；任何 ``../``、绝对路径、子路径都会被拒绝。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.app.platform.config import BASE_DIR

from .contracts import DATASET_IDS, DATASET_LABELS, EvaluationError

GOLD_DIR = BASE_DIR / "docs" / "sdd" / "plans" / "047" / "gold"
# spec-047 §13.1 P1-4：chat 集唯一数据源改为 builtin-chat-quality.json 的 items。
# 本常量仅作 042 冻结 trace 的溯源留痕与历史 fixture 兼容，不再被任何加载逻辑读取。
CHAT_DATASET_PATH = BASE_DIR / "docs" / "sdd" / "plans" / "042" / "task-02-eval-dataset.json"
_DATASET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def safe_dataset_path(dataset_id: Any) -> Path:
    """把 dataset_id 映射到白名单目录内的唯一文件；越界一律稳定错误。"""
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    if not _DATASET_ID_PATTERN.fullmatch(dataset_id) or dataset_id not in DATASET_IDS:
        raise EvaluationError("EVAL_DATASET_INVALID")
    root = GOLD_DIR.resolve()
    path = (root / f"builtin-{dataset_id}.json").resolve()
    if path.parent != root or path.name != f"builtin-{dataset_id}.json":
        raise EvaluationError("EVAL_DATASET_INVALID")
    return path


def load_dataset(dataset_id: Any) -> dict[str, Any]:
    path = safe_dataset_path(dataset_id)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise EvaluationError("EVAL_DATASET_INVALID") from None
    if not isinstance(document, dict):
        raise EvaluationError("EVAL_DATASET_INVALID")
    if (
        document.get("source") != "builtin-fixture"
        or document.get("synthetic") is not True
        or not isinstance(document.get("label_source"), str)
        or not isinstance(document.get("items"), list)
        or document.get("dataset_id") != dataset_id
    ):
        raise EvaluationError("EVAL_DATASET_INVALID")
    return document


def list_datasets() -> list[dict[str, Any]]:
    result = []
    for dataset_id in DATASET_IDS:
        document = load_dataset(dataset_id)
        # P1-4：三份集统一取 len(items)，与 load_chat_items() 的打分对象同源。
        item_count = len(document["items"])
        result.append(
            {
                "id": dataset_id,
                "label": DATASET_LABELS[dataset_id],
                "item_count": item_count,
                "source": document["source"],
                "synthetic": document["synthetic"],
                "label_source": document["label_source"],
            }
        )
    return result


def load_chat_items() -> list[dict[str, Any]]:
    """P1-4 唯一数据源：``builtin-chat-quality.json`` 的 ``items``。

    文档级 ``synthetic:true`` 由 ``load_dataset`` 强制校验（内置 fixture，不冒充人工标注）；
    条目级 ``synthetic`` 只表示来源（冻结 trace=false / KB 派生=true），**不再按它过滤**。
    只校验 status=scored 与非空 input/output；白名单与路径穿越校验沿用 load_dataset 不变。
    """
    document = load_dataset("chat-quality")
    items = []
    for item in document["items"]:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "scored":
            continue
        if not isinstance(item.get("input"), str) or not isinstance(item.get("output"), str):
            continue
        if not item["output"].strip():
            continue
        items.append(item)
    return items
