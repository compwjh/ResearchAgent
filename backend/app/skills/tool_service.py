"""Tool 注册表服务（业务逻辑层）。

组合代码注册表（registry.build_default_tool_registry）与状态存储
（SkillStateStore 的 tools 段），向 API 暴露：
- ``list_tools``：只读列表（name/description/enabled）
- ``get_tool``：按 name 取单个 Tool，不存在返回 None
- ``get_tool_entry``：按 name 取**注册项本身**（含 entry/parameters），供源码审计
- ``set_enabled``：按 name 启停，返回更新后的 Tool；name 不存在返回 None

状态文件缺失/损坏时 ``enabled`` 默认 True（不阻塞）；注册项本身来自代码，
禁用只改状态、不删除注册项。

另含 spec-034 的只读源码解析：``resolve_tool_source(entry)`` 把注册项自带的
点分 ``entry`` 解析为「入口函数源码 + 仓库相对 文件:行号」，**只读**、不加缓存。
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Sequence

from backend.app.platform.config import BASE_DIR
from backend.app.skills.models import ToolEntry
from backend.app.skills.state_store import SkillStateStore

logger = logging.getLogger(__name__)

# 仓库根：由 backend 包位置推导（platform.config.BASE_DIR = 该文件的 parents[3]），
# 禁止硬编码绝对路径。源码文件必须落在本目录内，否则视为不可用。
_REPO_ROOT = BASE_DIR


class _SourceUnavailable(Exception):
    """内部信号：``entry`` 无法解析为「函数/方法」源码。

    细节（含绝对路径与 stack）只进服务端日志，绝不进 API 响应体（M-04）。
    """


def _import_entry_object(entry: str) -> tuple[Any, list[str]]:
    """把点分 ``entry`` 拆成「模块路径 + 属性链」并取到目标对象。

    从长到短尝试 ``importlib.import_module``，返回首个可导入的模块与**剩余属性链**。
    属性链为空时返回的是模块对象本身 —— 调用方必须做类型校验（M-03），
    不得把模块/类当作解析终点，否则 ``inspect.getsource`` 会返回整个文件/整个类体。
    """
    parts = [part for part in entry.split(".") if part]
    for split in range(len(parts), 0, -1):
        try:
            obj: Any = importlib.import_module(".".join(parts[:split]))
        except Exception:  # 非法/不存在的模块名一律降级重试更短的前缀
            continue
        attrs = parts[split:]
        try:
            for attr in attrs:
                obj = getattr(obj, attr)
        except AttributeError:
            continue
        return obj, attrs
    raise _SourceUnavailable("entry is not importable")


def resolve_tool_source(entry: str) -> dict | None:
    """把注册项 ``entry`` 解析为入口函数源码视图；不可用时返回 None。

    成功返回 ``{file, lineno, language, code}``：
    - ``file``：**仓库相对** POSIX 路径；解析结果越界（含软链指向仓库外）一律不可用；
    - ``lineno``：``inspect.getsourcelines`` 的源码块首行（1-based）。对带装饰器的函数
      该行是**装饰器行**（M-01，如 ``routes_kb.py`` 的 ``kb_ask``）；
    - ``code``：``inspect.getsource`` 原文，**含装饰器行与签名**；
    - ``language``：固定 ``"python"``。

    **M-03**：解析终点必须是函数或方法（属性链非空且
    ``inspect.isfunction(obj) or inspect.ismethod(obj)``），否则不可用 —— 禁止返回
    整个模块文件或整个类体。

    只读：不执行、不 eval、不写文件、不改注册表；不加缓存（每次实时解析，避免行号漂移）。
    失败详情（含 stack 与绝对路径）只进服务端日志。
    """
    try:
        obj, attrs = _import_entry_object(entry)
        if not attrs or not (inspect.isfunction(obj) or inspect.ismethod(obj)):
            raise _SourceUnavailable("resolved object is not a function or method")
        source_file = inspect.getsourcefile(obj)
        if not source_file:
            raise _SourceUnavailable("source file is not available")
        lines, lineno = inspect.getsourcelines(obj)
        relative = Path(source_file).resolve().relative_to(_REPO_ROOT)
        return {
            "file": relative.as_posix(),
            "lineno": lineno,
            "language": "python",
            "code": "".join(lines),
        }
    except Exception:  # 所有失败统一收敛为「不可用」，细节只进服务端日志
        logger.warning("tool source unavailable for entry %r", entry, exc_info=True)
        return None


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

    def get_tool_entry(self, name: str) -> ToolEntry | None:
        """按注册名返回**注册项本身**（含 ``entry`` / ``parameters``），不存在返回 None。

        与 ``get_tool`` 的区别：不读状态文件、不掺入 ``enabled`` 状态 —— 供 spec-034
        的只读源码审计使用（代码可见性不受启停状态影响）。名称**精确相等**匹配，
        不做前缀/模糊/大小写归一化，也不回退文件系统查找（M-06）。
        返回对象仅供只读使用，调用方不得修改（M-07）。
        """
        for template in self._registry:
            if template.name == name:
                return template
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
