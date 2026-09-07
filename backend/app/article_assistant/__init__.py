"""文章助手限界上下文（Spec017 Task06）。

本包属文章助手上下文。依赖方向 `api → application → domain / infrastructure`；
其它上下文与 `api` 层不得直接 import 本包的 `infrastructure` 内部模块
（Task07 会用 architecture test 强制）。

本包**不做包级 re-export / wildcard**：`__all__` 恒为空列表。
"""

__all__ = []
