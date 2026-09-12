"""从磁盘扫描 `.agents/skills/*/SKILL.md` 并解析 frontmatter（数据访问层）。

唯一事实源是磁盘上的 SKILL.md；本模块只读取、不写入。解析对缺失/损坏
frontmatter 做容错：name 回退为目录名，description/tools 为空，正文保留。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.app.skills.models import SkillRecord

_DELIMITER = "---"


def _strip_body(text: str) -> str:
    return text.strip()


def parse_skill_markdown(text: str) -> tuple[dict[str, Any], str]:
    """返回 ``(metadata, body)``。

    - 无 frontmatter（首行非 ``---``）或缺少闭合 ``---`` 或 YAML 损坏：
      返回 ``({}, 全文)``，交由上层按目录名回退。
    - frontmatter 解析成功：返回元数据 dict 与去掉 frontmatter 的正文。
    """
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIMITER:
        return {}, _strip_body(text)
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            end_index = index
            break
    if end_index is None:
        return {}, _strip_body(text)
    frontmatter_text = "".join(lines[1:end_index])
    body = _strip_body("".join(lines[end_index + 1:]))
    try:
        meta = yaml.safe_load(frontmatter_text)
    except (yaml.YAMLError, UnicodeDecodeError, ValueError):
        return {}, _strip_body(text)
    if not isinstance(meta, dict):
        return {}, _strip_body(text)
    return meta, body


def _normalize_tools(value: Any) -> list[str]:
    """frontmatter 的 ``tools`` 容错为 list[str]。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _is_legacy(value: Any) -> bool:
    """frontmatter 的 ``status`` 容错判定：仅字符串且等于 ``legacy``（忽略大小写/空白）为 True。

    字段缺失、``None``、非字符串（数字/列表/字典）一律 False，不得抛异常。
    """
    if not isinstance(value, str):
        return False
    return value.strip().lower() == "legacy"


class SkillScanner:
    """扫描技能目录，逐个解析 SKILL.md。"""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = Path(skills_dir)

    def scan(self) -> list[SkillRecord]:
        if not self.skills_dir.is_dir():
            return []
        records: list[SkillRecord] = []
        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # 单文件不可读不得拖垮整个列表
                continue
            meta, body = parse_skill_markdown(text)
            name = meta.get("name") or entry.name
            description = meta.get("description") or ""
            if not isinstance(description, str):
                description = str(description)
            records.append(
                SkillRecord(
                    name=name,
                    description=description,
                    tools=_normalize_tools(meta.get("tools")),
                    body=body,
                    dir_name=entry.name,
                    legacy=_is_legacy(meta.get("status")),
                )
            )
        return records
