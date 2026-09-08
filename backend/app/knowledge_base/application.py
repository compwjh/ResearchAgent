"""知识库限界上下文的受控应用入口（Spec017 Task05）。

本模块是知识库上下文对外的**唯一受控入口**，用于替代并拆除原
`backend.app.services.kb.__init__` 的包级 facade。

依赖方向：其它上下文（如论文发现上下文 `services.paper_import`）、
`api` 层与脚本**只能**依赖本模块，不得直接 import 知识库内部的
`store` / `index` / `tasks` / `prompts` / `retrieve` / `parse` / `embed`
等 infrastructure 模块（Task07 会用 architecture test 强制此约束）。

与旧 facade 的区别：旧 facade 是**包级** `__init__` 的隐式 re-export；
本模块是**显式** `application` 入口，全部导出集中在 `__all__`，便于审计
与逐步收窄。当前导出面沿用迁移前的对外契约，未新增能力。

本模块只做导入与文档，不新增业务逻辑、不改函数签名与常量值。
"""

from backend.app.knowledge_base.infrastructure.embed import embed_texts, encode_sparse
from backend.app.knowledge_base.infrastructure.index import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    backfill_chunker_defaults,
    count_points,
    delete_paper,
    delete_paper_chunker,
    ensure_collection,
    get_client,
    index_paper,
    index_paper_chunker,
    reset_client,
)
from backend.app.knowledge_base.infrastructure.parse import (
    PdfParseError,
    build_chunks,
    extract_pages,
    split_text,
)
from backend.app.knowledge_base.infrastructure.prompts import (
    build_prompt,
    citation_payloads,
)
from backend.app.knowledge_base.infrastructure.retrieve import (
    Hit,
    hybrid_search,
    reranker_available,
    reranker_health,
    rerank_hits,
    rrf_fuse,
)
from backend.app.knowledge_base.infrastructure.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    CHUNKERS,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
    STATUS_PENDING,
    PaperRecord,
    get_chunker_state,
    get_paper,
    load_papers,
    mark_interrupted_tasks,
    new_record,
    remove_paper,
    resolve_paper_path,
    save_upload,
    update_chunker_state,
    upsert_paper,
)
from backend.app.knowledge_base.infrastructure.tasks import (
    mark_interrupted_on_startup,
    run_index_task_sync,
    running_count,
    submit_index_task,
)

__all__ = [
    # 常量与类型
    "CHUNKERS",
    "CHUNKER_V1",
    "CHUNKER_V2",
    "DENSE_VECTOR",
    "SPARSE_VECTOR",
    "Hit",
    "PaperRecord",
    "PdfParseError",
    "STATUS_FAILED",
    "STATUS_INDEXED",
    "STATUS_INDEXING",
    "STATUS_PARTIAL",
    "STATUS_PENDING",
    # 生命周期
    "backfill_chunker_defaults",
    "mark_interrupted_on_startup",
    "mark_interrupted_tasks",
    "running_count",
    # 解析与分块
    "build_chunks",
    "extract_pages",
    "split_text",
    # 向量化与索引
    "embed_texts",
    "encode_sparse",
    "index_paper",
    "index_paper_chunker",
    "delete_paper",
    "delete_paper_chunker",
    "count_points",
    "ensure_collection",
    "get_client",
    "reset_client",
    # 检索与重排
    "hybrid_search",
    "reranker_available",
    "reranker_health",
    "rerank_hits",
    "rrf_fuse",
    # 提示词
    "build_prompt",
    "citation_payloads",
    # 元数据仓储
    "get_chunker_state",
    "get_paper",
    "load_papers",
    "new_record",
    "remove_paper",
    "resolve_paper_path",
    "save_upload",
    "update_chunker_state",
    "upsert_paper",
    # 索引任务
    "run_index_task_sync",
    "submit_index_task",
]
