"""跨域 port 契约定义（论文导入 → 知识库）。

本模块仅定义跨限界上下文的抽象契约，**不持有任何实现**。
实现由 Task05（知识库上下文）提供，由 Task04（论文发现上下文）消费。
依赖方向固定为 api → application → domain / infrastructure，platform 为跨业务
适配层，禁止 import 任何业务模块（services / domain / qdrant / store / task 等）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ImportIndexStatus",
    "PaperImportErrorCode",
    "PaperImportRequest",
    "PaperImportResult",
    "PaperImportPort",
]


class ImportIndexStatus(str, Enum):
    """论文入库后的索引状态。

    本 port 仅定义契约；实现由 Task05（知识库上下文）提供，Task04（论文发现上下文）消费。
    """

    INDEXED = "indexed"   # 已成功写入向量索引，可被检索。
    PENDING = "pending"   # 已导入但索引尚未完成。
    FAILED = "failed"   # 索引失败。


class PaperImportErrorCode(str, Enum):
    """论文导入 / 索引失败的稳定错误码。

    取值为稳定字符串，供跨域对账使用；实现由 Task05（知识库上下文）提供，
    Task04（论文发现上下文）消费。
    """

    KB_IMPORT_FAILED = "KB_IMPORT_FAILED"   # 写入知识库失败。
    KB_INDEX_FAILED = "KB_INDEX_FAILED"   # 构建 / 写入向量索引失败。


@dataclass(frozen=True)
class PaperImportRequest:
    """论文导入请求（只读）。

    仅承载候选快照与受信任的本地 PDF 路径，不暴露任何基础设施类型。
    本 port 仅定义契约；实现由 Task05（知识库上下文）提供，Task04（论文发现上下文）消费。
    """

    candidate_snapshot: Mapping[str, Any]   # 候选论文快照（只读映射）。
    trusted_pdf_path: Path   # 受信任的本地 PDF 路径。


@dataclass(frozen=True)
class PaperImportResult:
    """论文导入结果（只读）。

    本 port 仅定义契约；实现由 Task05（知识库上下文）提供，Task04（论文发现上下文）消费。
    """

    paper_id: str | None   # 论文标识；失败时可为空。
    index_status: ImportIndexStatus   # 索引状态。
    error_code: PaperImportErrorCode | None   # 失败时的错误码，成功为 None。
    stored_name: str | None = None   # 知识库侧最终保存的文件名。
    existing: bool = False   # 是否命中幂等已有记录。


@runtime_checkable
class PaperImportPort(Protocol):
    """论文导入 → 知识库 跨域 port。

    只定义契约；实现由 Task05（知识库上下文）提供，Task04（论文发现上下文）消费。
    不得暴露 Qdrant 客户端、store 对象、task 对象或任何基础设施类型。
    """

    def import_paper(self, request: PaperImportRequest) -> PaperImportResult:
        """将一篇论文导入知识库并返回结果。

        本 port 仅定义契约；实现由 Task05（知识库上下文）提供，Task04（论文发现上下文）消费。
        """
        ...

    def find_existing(self, candidate_snapshot: Mapping[str, Any]) -> PaperImportResult | None:
        """按候选快照查询已有记录，避免重复下载。

        该查询仍属于知识库适配器的幂等边界；论文发现侧只消费稳定 DTO，
        不读取知识库元数据仓储。
        """
        ...

    def existing_names(self) -> set[str]:
        """返回知识库侧已占用的展示文件名，供论文发现生成安全文件名。"""
        ...
