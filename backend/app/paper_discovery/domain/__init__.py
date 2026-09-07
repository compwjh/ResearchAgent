"""论文发现上下文的 domain 层（Spec017 Task04）。

本包属论文发现限界上下文。依赖方向 `api → application → domain / infrastructure`；
其它上下文只能依赖本上下文的 application 入口，不得直接 import 本包内部模块
（Task07 会用 architecture test 强制）。

本包**不做包级 re-export / wildcard**：`__all__` 恒为空列表。
"""

__all__ = []
