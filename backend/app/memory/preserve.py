"""spec-038 P1 后半段 · 删除 ``system_rules`` 前的用户数据保全。

为什么要这一步
--------------
新基线停用了 ``system_rules`` 表，全局用户画像改由 ``USER.md`` 承载。删表即等于
删数据，因此**在删表前**必须把旧库里的 content 搬进 ``USER.md``：

- 这是本次重置中**唯一需要保留的用户数据**（``memories`` 的用户内容已由 P1 前半段
  的 MD 层接管，无需在此重复搬运）。
- 写文件一律复用 ``MarkdownMemoryStore``，**不另写文件操作**（避免出现第二套
  MD 读写实现）。

幂等与安全性
------------
- 库里没有 ``system_rules`` 表、或表内没有记录 → 空操作，不创建 ``USER.md``。
- ``USER.md`` 已有内容 → 视为用户已在编辑 MD，**不覆盖**，只记录跳过。
- 任何读取/写入异常都不得让 ``initialize()`` 崩溃：记忆文件损坏不应阻止建库。
  唯一的例外是 ``MemoryRepository`` 需要 fail-closed 的场景（schema 校验），
  与本模块无关。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from .markdown_store import MarkdownMemoryStore

logger = logging.getLogger(__name__)

__all__ = ["preserve_legacy_owner_data"]


def _legacy_system_rule_contents(connection: sqlite3.Connection) -> list[str]:
    """读取旧 ``system_rules`` 表中所有非空 content；表不存在时返回空列表。"""
    try:
        rows = connection.execute("SELECT owner_id, content FROM system_rules").fetchall()
    except sqlite3.OperationalError:
        # 表不存在（新库 / 已重建）→ 空操作。
        return []
    contents: list[str] = []
    for row in rows:
        value = row["content"] if isinstance(row, sqlite3.Row) else row[1]
        text = str(value or "").strip()
        if text:
            contents.append(text)
    return contents


def preserve_legacy_owner_data(
    connection: sqlite3.Connection,
    *,
    store: Optional[MarkdownMemoryStore] = None,
) -> bool:
    """把旧库 ``system_rules`` 内容迁移写入 ``USER.md``。

    返回 ``True`` 表示确实发生了迁移（写入了 ``USER.md``）。空操作返回 ``False``。

    迁移策略：多条历史 content 按「后写的更新」顺序追加为 Markdown 条目，与
    ``MarkdownMemoryStore.append_memory`` 的条目约定一致（``- <content>``）。
    """
    try:
        contents = _legacy_system_rule_contents(connection)
    except Exception as error:  # pragma: no cover - 防御性兜底
        logger.warning("legacy system_rules read failed; skip preservation: %s", error)
        return False

    if not contents:
        return False

    target = store or MarkdownMemoryStore()
    try:
        existing = target.read_user()
    except Exception as error:  # pragma: no cover - 防御性兜底
        logger.warning("USER.md read failed; skip preservation: %s", error)
        return False

    if existing.strip():
        # 用户已经在编辑 MD：不覆盖、不重复搬。
        logger.info("USER.md already has content; legacy system rule preservation skipped")
        return False

    try:
        target.write_user("".join(f"- {line}\n" for line in contents))
    except Exception as error:  # pragma: no cover - 防御性兜底
        logger.warning("USER.md write failed; skip preservation: %s", error)
        return False

    logger.info("preserved %d legacy system rule(s) into USER.md", len(contents))
    return True
