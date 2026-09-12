"""Skill 注册表服务（业务逻辑层）。

组合磁盘扫描（SkillScanner）与状态存储（SkillStateStore），向 API 暴露：
- ``list_skills``：只读列表（无 body）
- ``get_skill``：详情（含 body）
- ``set_enabled``：按 name 启停，返回更新后的投影；name 不存在返回 None

状态文件缺失/损坏时 ``enabled`` 默认 True（不阻塞）。
"""

from __future__ import annotations

from pathlib import Path

from backend.app.skills.models import SkillDetail, SkillRecord, SkillSummary
from backend.app.skills.scanner import SkillScanner
from backend.app.skills.state_store import SkillStateStore


class SkillRegistryService:
    def __init__(self, skills_dir: Path, state_path: Path) -> None:
        self._scanner = SkillScanner(skills_dir)
        self._state = SkillStateStore(state_path)

    def _enabled_for(self, name: str) -> bool:
        entry = self._state.load_skill_states().get(name) or {}
        if not isinstance(entry, dict):
            return True
        return bool(entry.get("enabled", True))

    def list_skills(self) -> list[SkillSummary]:
        return [
            SkillSummary(
                name=record.name,
                description=record.description,
                tools=record.tools,
                enabled=self._enabled_for(record.name),
                legacy=getattr(record, "legacy", False),
            )
            for record in self._scanner.scan()
        ]

    def get_skill(self, name: str) -> SkillDetail | None:
        for record in self._scanner.scan():
            if record.name == name:
                return SkillDetail(
                    name=record.name,
                    description=record.description,
                    tools=record.tools,
                    enabled=self._enabled_for(record.name),
                    legacy=getattr(record, "legacy", False),
                    body=record.body,
                )
        return None

    def set_enabled(self, name: str, enabled: bool) -> SkillSummary | None:
        record = self._find_record(name)
        if record is None:
            return None
        self._state.set_enabled(name, enabled)
        return SkillSummary(
            name=record.name,
            description=record.description,
            tools=record.tools,
            enabled=bool(enabled),
            legacy=getattr(record, "legacy", False),
        )

    def _find_record(self, name: str) -> SkillRecord | None:
        for record in self._scanner.scan():
            if record.name == name:
                return record
        return None
