"""Skill 启用状态持久化（数据访问层）。

状态文件 ``data/kb/skill-state.json`` 结构：
    {"schema_version":"skill-state-v1","skills":{<name>:{"enabled":bool}},"tools":{}}

缺失/损坏一律回退为「全部启用」，且写操作复用 ``manifest_store._atomic_bytes``
做原子落盘（临时文件 + fsync + os.replace）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.knowledge_base.infrastructure.manifest_store import _atomic_bytes

SCHEMA_VERSION = "skill-state-v1"


class SkillStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def load_skill_states(self) -> dict[str, dict]:
        skills = self.load().get("skills")
        if not isinstance(skills, dict):
            return {}
        return skills

    def load_tool_states(self) -> dict[str, dict]:
        tools = self.load().get("tools")
        if not isinstance(tools, dict):
            return {}
        return tools

    def set_enabled(self, name: str, enabled: bool) -> None:
        data = self.load()
        if not isinstance(data, dict):
            data = {}
        skills = data.get("skills")
        if not isinstance(skills, dict):
            skills = {}
            data["skills"] = skills
        entry = skills.get(name)
        if not isinstance(entry, dict):
            entry = {}
            skills[name] = entry
        entry["enabled"] = bool(enabled)
        data["schema_version"] = SCHEMA_VERSION
        if "tools" not in data:
            data["tools"] = {}
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        _atomic_bytes(self.state_path, payload)

    def set_tool_enabled(self, name: str, enabled: bool) -> None:
        """写 tools 段，且必须与 skills 段共存（不覆盖、不丢失）。"""
        data = self.load()
        if not isinstance(data, dict):
            data = {}
        skills = data.get("skills")
        if not isinstance(skills, dict):
            skills = {}
            data["skills"] = skills
        tools = data.get("tools")
        if not isinstance(tools, dict):
            tools = {}
            data["tools"] = tools
        entry = tools.get(name)
        if not isinstance(entry, dict):
            entry = {}
            tools[name] = entry
        entry["enabled"] = bool(enabled)
        data["schema_version"] = SCHEMA_VERSION
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        _atomic_bytes(self.state_path, payload)
