"""应用级依赖的组合根（composition root）与测试替换点。

本模块位于 ``platform`` 跨业务适配层，**禁止 import 任何业务模块**
（``services`` / ``domain`` / ``api`` / ``graphs`` / qdrant / store / task 等），
Task07 会用 AST 静态检查强制该约束，函数体内的延迟 import 同样算违规。

因此本模块只提供与业务无关的「provider 注册 / 解析 / 测试替换」机制：
- ``register`` 登记一个构造器（factory）；
- ``get`` 按「override > 已缓存单例 > 调用 factory」的顺序解析并提供对象；
- ``override`` 提供上下文管理器形式的测试替换点，支持嵌套与异常安全恢复。

具体业务对象的构造逻辑（如 ``PaperDiscoveryStore``、``PaperBrowserManager`` 等）
由 ``api`` 层在启动时按需注册进来，本模块不持有任何业务构造器。

设计要点：
- ``singleton=True``（默认）时，首个 ``get`` 的构造结果被缓存，后续直接返回；
- ``override`` 与单例缓存相互独立，替换退出后自动回到注册/缓存状态；
- 未注册的 name 在 ``get`` 时抛 ``KeyError``，报错信息含该 name。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

__all__ = [
    "ProviderRegistry",
    "registry",
    "register_provider",
    "get_provider",
    "override_provider",
    "reset_providers",
    "clear_provider_cache",
]


class ProviderRegistry:
    """provider 注册表：登记构造器、解析对象、支持测试替换。

    仅依赖标准库，不 import 任何业务模块。线程不安全，假设在
    应用启动阶段单线程装配；运行时解析（``get``）只读已缓存结果或
    调用无副作用的 factory，调用方自行保证一致性。
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}
        self._singletons: dict[str, bool] = {}
        self._cache: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        singleton: bool = True,
    ) -> None:
        """登记一个构造器。

        :param name: provider 名称。
        :param factory: 无参构造器，返回对象。
        :param singleton: 为 True 时首个 ``get`` 的构造结果被缓存并复用。
        """
        self._factories[name] = factory
        self._singletons[name] = singleton

    def get(self, name: str) -> Any:
        """按「override > 已缓存单例 > 调用 factory」解析并返回对象。

        未注册时抛 ``KeyError``，报错信息含 ``name``。
        """
        if name in self._overrides:
            return self._overrides[name]
        if name in self._cache:
            return self._cache[name]
        if name not in self._factories:
            raise KeyError(f"no provider registered for {name!r}")
        value = self._factories[name]()
        if self._singletons.get(name, True):
            self._cache[name] = value
        return value

    def clear_cache(self, name: str | None = None) -> None:
        """清空单例缓存。``name`` 为 None 时清空全部缓存。"""
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)

    @contextmanager
    def override(self, name: str, value: Any) -> Iterator[None]:
        """在上下文内以 ``value`` 替换 ``name`` 的解析结果。

        支持嵌套：进入时保存该 name 的旧 override，退出时恢复旧状态；
        异常路径下同样恢复（由 ``contextmanager`` 的 finally 保证）。
        """
        had_override = name in self._overrides
        previous = self._overrides.get(name)
        self._overrides[name] = value
        try:
            yield
        finally:
            if had_override:
                self._overrides[name] = previous
            else:
                self._overrides.pop(name, None)

    def reset_overrides(self) -> None:
        """清空全部 override，恢复到无替换状态。"""
        self._overrides.clear()


# 应用级单例组合根，供 api 层注册业务 provider。
registry = ProviderRegistry()


def register_provider(
    name: str,
    factory: Callable[[], Any],
    *,
    singleton: bool = True,
) -> None:
    """便捷函数：向应用级 :data:`registry` 注册 provider。"""
    registry.register(name, factory, singleton=singleton)


def get_provider(name: str) -> Any:
    """便捷函数：从应用级 :data:`registry` 解析 provider。"""
    return registry.get(name)


def override_provider(name: str, value: Any) -> "Iterator[None]":
    """便捷函数：在上下文内替换应用级 :data:`registry` 中 ``name`` 的解析结果。"""
    return registry.override(name, value)


def reset_providers() -> None:
    """便捷函数：清空应用级 :data:`registry` 的全部 override。"""
    registry.reset_overrides()


def clear_provider_cache(name: str | None = None) -> None:
    """便捷函数：清空应用级 :data:`registry` 的单例缓存。"""
    registry.clear_cache(name)
