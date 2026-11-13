"""评测 run 产物：本地只读白名单目录 JSON，无 DB 表 / 无迁移。

``run_id`` 与 ``dataset_id`` 同样做严格的白名单字符校验 + resolve 归属校验，
防止 ``../`` 与绝对路径穿越（回归清单第 7 条）。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from backend.app.platform.config import BASE_DIR

from .contracts import EvaluationError

RUNS_DIR = BASE_DIR / "docs" / "sdd" / "plans" / "047" / "runs" / "evaluation"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_SUMMARY_KEYS = ("run_id", "strategy", "model", "dataset", "judge_model", "created_at")


def safe_run_path(run_id: Any, *, must_exist: bool = False) -> Path:
    if not isinstance(run_id, str) or not run_id or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise EvaluationError("EVAL_DATASET_INVALID")
    root = RUNS_DIR.resolve()
    path = (root / f"{run_id}.json").resolve()
    if path.parent != root or path.name != f"{run_id}.json":
        raise EvaluationError("EVAL_DATASET_INVALID")
    if must_exist and not path.is_file():
        raise EvaluationError("EVAL_OPTION_NOT_FOUND")
    return path


def save_run(document: dict[str, Any]) -> dict[str, Any]:
    path = safe_run_path(document.get("run_id"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    except OSError:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    return document


def load_run(run_id: Any) -> dict[str, Any]:
    path = safe_run_path(run_id, must_exist=True)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    if not isinstance(document, dict):
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE")
    return document


def list_runs() -> list[dict[str, Any]]:
    try:
        paths = sorted(RUNS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        raise EvaluationError("EVAL_BACKEND_UNAVAILABLE") from None
    result = []
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            continue
        if isinstance(document, dict):
            result.append({key: document.get(key) for key in _SUMMARY_KEYS})
    return result
