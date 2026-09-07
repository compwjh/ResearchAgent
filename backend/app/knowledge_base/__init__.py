"""知识库限界上下文（Spec017 Task05）包入口。

本包为知识库（kb / RAG）限界上下文。按 Spec017 的依赖方向
`api -> application -> domain / infrastructure`，跨上下文**只能**依赖
`backend.app.knowledge_base.application`（受控应用入口）。

**禁止**任何其它上下文直接 import 本包的内部实现模块，例如
`backend.app.knowledge_base.infrastructure.*`（Task07 将用 architecture
test 强制此约束）。

本包**不做包级 re-export / wildcard**：`__all__` 恒为空列表，明确不做
`services.kb.__init__` 那样的第二套 facade。所有对外契约均收敛到
`backend.app.knowledge_base.application`。
"""

__all__ = []
