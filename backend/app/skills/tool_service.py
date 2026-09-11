"""Tool 注册表服务（业务逻辑层）。

组合代码注册表（registry.build_default_tool_registry）与状态存储
（SkillStateStore 的 tools 段），向 API 暴露：
- ``list_tools``：只读列表（name/description/enabled）
- ``get_tool``：按 name 取单个 Tool，不存在返回 None
- ``set_enabled``：按 name 启停，返回更新后的 Tool；name 不存在返回 None

状态文件缺失/损坏时 ``enabled`` 默认 True（不阻塞）；注册项本身来自代码，
禁用只改状态、不删除注册项。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from backend.app.skills.models import ToolEntry
from backend.app.skills.state_store import SkillStateStore


class ToolRegistryService:
    def __init__(self, registry: Sequence[ToolEntry], state_path: Path) -> None:
        # 复制注册项，避免外部可变序列影响实例状态
        # 注意：parameters 是 function-calling / 计划 JSON 校验用的 JSON Schema，
        # 必须原样透传，否则校验会因拿到空 schema 而误杀合法参数（见 Task07）。
        self._registry = [
            ToolEntry(
                name=t.name,
                description=t.description,
                enabled=True,
                entry=t.entry,
                parameters=t.parameters,
            )
            for t in registry
        ]
        self._state = SkillStateStore(state_path)

    def _enabled_for(self, name: str) -> bool:
        entry = self._state.load_tool_states().get(name) or {}
        if not isinstance(entry, dict):
            return True
        return bool(entry.get("enabled", True))

    def _to_tool(self, template: ToolEntry) -> ToolEntry:
        return ToolEntry(
            name=template.name,
            description=template.description,
            enabled=self._enabled_for(template.name),
            entry=template.entry,
            parameters=template.parameters,
        )

    def list_tools(self) -> list[ToolEntry]:
        return [self._to_tool(t) for t in self._registry]

    def get_tool(self, name: str) -> ToolEntry | None:
        for template in self._registry:
            if template.name == name:
                return self._to_tool(template)
        return None

    def set_enabled(self, name: str, enabled: bool) -> ToolEntry | None:
        template = None
        for candidate in self._registry:
            if candidate.name == name:
                template = candidate
                break
        if template is None:
            return None
        self._state.set_tool_enabled(name, enabled)
        return ToolEntry(
            name=template.name,
            description=template.description,
            enabled=bool(enabled),
            entry=template.entry,
            parameters=template.parameters,
        )
