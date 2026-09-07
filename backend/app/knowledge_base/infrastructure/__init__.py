"""知识库上下文的 infrastructure 层（Spec017 Task05 子任务 5.2）。

本包承载知识库（kb / RAG）上下文的实现细节，包括解析、分块、向量化、
检索、仓储等模块。

**仅限知识库上下文内部使用**：其它上下文（如论文发现上下文
`services.paper_import`）**只能**依赖 `backend.app.knowledge_base.application`
（受控应用入口），不得直接 import 本包或其下任何模块。Task07 将用
architecture test 强制此约束。

本包**不做包级 re-export / wildcard**：`__all__` 恒为空列表。
"""

__all__ = []
