"""论文发现限界上下文的受控应用入口（Spec017 Task04）。

静态边界规则禁止 `api` 直连任何上下文的 `infrastructure`，但 `api` 的组合装配
（构造检索服务、批量服务与浏览器管理器）确实需要一批基础设施符号。本模块即
这些符号的**唯一受控出口**：`api` 一律从本模块导入，不得再直接 import
`paper_discovery.infrastructure.*`。

与知识库侧的处理保持一致：导出集中在显式 `__all__`，便于审计与逐步收窄。
本模块只做导入与文档，不新增业务逻辑、不改函数签名与常量值。
"""

from backend.app.paper_discovery.infrastructure.dblp_publication_source import (
    DBLPPublicationSource,
)
from backend.app.paper_discovery.infrastructure.openalex_enricher import OpenAlexEnricher
from backend.app.paper_discovery.infrastructure.paper_browser_manager import (
    BrowserManagerError,
    PaperBrowserManager,
)
from backend.app.paper_discovery.infrastructure.paper_discovery_store import (
    PaperDiscoveryStore,
)
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    PaperDownloadError,
)
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import (
    PaperImportBatchStore,
)

__all__ = [
    # 数据源
    "DBLPPublicationSource",
    "OpenAlexEnricher",
    # 浏览器
    "BrowserManagerError",
    "PaperBrowserManager",
    # 仓储
    "PaperDiscoveryStore",
    "PaperImportBatchStore",
    # 下载错误码与异常
    "DOWNLOAD_BLOCKED",
    "DOWNLOAD_TIMEOUT",
    "INVALID_PDF",
    "LOGIN_REQUIRED",
    "PDF_NOT_FOUND",
    "PDF_TOO_LARGE",
    "PaperDownloadError",
]
