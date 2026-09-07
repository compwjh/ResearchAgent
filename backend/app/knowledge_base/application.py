"""知识库限界上下文的受控应用入口（Spec017 Task05）。

本模块是知识库上下文对外的**唯一受控入口**，用于替代并将拆除的
`backend.app.services.kb.__init__` 包级 facade。其它上下文（如论文发现
上下文 `services.paper_import`）及其它消费方**只能**依赖本模块，不得
直接 import 知识库内部的 `store` / `index` / `tasks` / `prompts` /
`retrieve` 等模块。

当前实现委托 `backend.app.services.kb.*`；Task05 后续子任务会把实现迁到
`knowledge_base/infrastructure/`，届时**只改本模块的导入来源**，对外契约
（符号名、签名）保持不变。

本模块只做导入与文档，不新增业务逻辑、不改函数名与签名、不写
try/except 包装。
"""

# 生命周期
# 供论文发现等其它上下文使用的操作
# 其它外部消费方用到的能力
from backend.app.knowledge_base.infrastructure.prompts import build_prompt
from backend.app.services.kb.index import backfill_chunker_defaults, delete_paper_chunker, index_paper_chunker
from backend.app.services.kb.retrieve import hybrid_search

# 常量与类型
from backend.app.services.kb.store import (
    CHUNKER_V1,
    STATUS_INDEXED,
    STATUS_INDEXING,
    PaperRecord,
    load_papers,
    new_record,
    remove_paper,
    upsert_paper,
)
from backend.app.services.kb.tasks import mark_interrupted_on_startup, run_index_task_sync, running_count

__all__ = [
    # 生命周期
    "backfill_chunker_defaults",
    "mark_interrupted_on_startup",
    "running_count",
    # 供其它上下文使用的操作
    "delete_paper_chunker",
    "index_paper_chunker",
    "load_papers",
    "new_record",
    "remove_paper",
    "run_index_task_sync",
    "upsert_paper",
    # 常量与类型
    "CHUNKER_V1",
    "PaperRecord",
    "STATUS_INDEXED",
    "STATUS_INDEXING",
    # 其它外部消费方用到的能力
    "build_prompt",
    "hybrid_search",
]
