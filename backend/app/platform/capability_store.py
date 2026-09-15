"""模型推理能力持久化（spec-035 Bug3）。

进程内存缓存（``ollama._capability_cache``）重启即失、多 worker 不共享，
这里提供 SQLite 二级存储：后台调度器每日探测后 upsert，读取路径在内存
未命中时回源本库（24h 内视为新鲜），避免每次切模型都实时探测 Ollama。

本模块属于 `platform` 层，只依赖 sqlite3 与 config，**禁止 import 业务模块**。
所有读写失败都不抛出（返回 None / 静默），读取路径对存储故障 fail-open：
存储坏了最多退回实时探测，绝不影响聊天主链路。
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.platform.config import BASE_DIR

_DEFAULT_DB_PATH = BASE_DIR / "data" / "model_capabilities.sqlite3"
_db_path: Optional[Path] = None
_lock = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_capabilities(
    model TEXT PRIMARY KEY,
    supported_efforts TEXT NOT NULL,
    default_effort TEXT,
    source TEXT NOT NULL,
    evidence TEXT NOT NULL,
    probed_at TEXT NOT NULL
)
"""


def set_db_path(path: Optional[Path]) -> None:
    """测试注入用：切换存储路径（None 恢复默认）。"""
    global _db_path
    with _lock:
        _db_path = Path(path) if path is not None else None


def _connect() -> sqlite3.Connection:
    path = _db_path or _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(_SCHEMA)


def upsert_capabilities(
    model: str,
    *,
    supported_efforts: tuple[str, ...],
    default_effort: Optional[str],
    source: str,
    evidence: dict[str, str],
    probed_at: str,
) -> None:
    """写入/覆盖一个模型的能力探测结果；失败静默（存储绝不阻断主链路）。"""
    with _lock:
        try:
            with _connect() as connection:
                _ensure_schema(connection)
                connection.execute(
                    "INSERT INTO model_capabilities(model, supported_efforts, default_effort, source, evidence, probed_at)"
                    " VALUES(?,?,?,?,?,?)"
                    " ON CONFLICT(model) DO UPDATE SET"
                    " supported_efforts=excluded.supported_efforts,"
                    " default_effort=excluded.default_effort,"
                    " source=excluded.source,"
                    " evidence=excluded.evidence,"
                    " probed_at=excluded.probed_at",
                    (
                        str(model),
                        json.dumps(list(supported_efforts)),
                        default_effort,
                        str(source),
                        json.dumps(dict(evidence or {})),
                        str(probed_at),
                    ),
                )
        except sqlite3.Error:
            return


def get_capabilities(model: str) -> Optional[dict[str, Any]]:
    """读取一个模型已存储的能力；无记录或存储故障返回 None。"""
    with _lock:
        try:
            with _connect() as connection:
                _ensure_schema(connection)
                row = connection.execute(
                    "SELECT model, supported_efforts, default_effort, source, evidence, probed_at"
                    " FROM model_capabilities WHERE model=?",
                    (str(model),),
                ).fetchone()
        except sqlite3.Error:
            return None
    if row is None:
        return None
    try:
        efforts = json.loads(row["supported_efforts"])
        evidence = json.loads(row["evidence"])
    except (TypeError, ValueError):
        return None
    if not isinstance(efforts, list) or not isinstance(evidence, dict):
        return None
    return {
        "model": row["model"],
        "supported_efforts": tuple(str(effort) for effort in efforts),
        "default_effort": row["default_effort"],
        "source": row["source"],
        "evidence": evidence,
        "probed_at": row["probed_at"],
    }


def probed_at_is_fresh(probed_at: str, *, max_age_seconds: float) -> bool:
    """probed_at 距今是否在 max_age_seconds 内；无法解析视为不新鲜。"""
    try:
        parsed = datetime.fromisoformat(str(probed_at))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - parsed).total_seconds()
    return 0 <= age <= max_age_seconds
