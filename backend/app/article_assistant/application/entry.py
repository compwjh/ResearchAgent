"""文章助手限界上下文的受控应用入口（Spec017 Task06）。

静态边界规则禁止 `api` 直连任何上下文的 `infrastructure`，但 `api` 的装配与
文章下载/检索确需一批基础设施符号。本模块即这些符号的**唯一受控出口**：
`api` 一律从本模块导入，不得再直接 import
`article_assistant.infrastructure.*`。

与知识库、论文发现两侧的处理保持一致：导出集中在显式 `__all__`，便于审计与
逐步收窄。本模块只做导入与文档，不新增业务逻辑、不改函数签名与常量值。
"""

from backend.app.article_assistant.infrastructure.article_download import (
    download_article,
    probe_pdf_url,
)
from backend.app.article_assistant.infrastructure.article_search import search_articles
from backend.app.article_assistant.infrastructure.task_store import TaskStore

__all__ = [
    # 任务仓储（api 装配用）
    "TaskStore",
    # 文章检索与下载
    "search_articles",
    "download_article",
    "probe_pdf_url",
]
