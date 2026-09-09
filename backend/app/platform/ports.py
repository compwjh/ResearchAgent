"""跨域 port 契约定义（论文导入 → 知识库）。

本模块仅定义跨限界上下文的抽象契约，**不持有任何实现**。
实现由 Task05（知识库上下文）提供，由 Task04（论文发现上下文）消费。
依赖方向固定为 api → application → domain / infrastructure，platform 为跨业务
适配层，禁止 import 任何业务模块（services / domain / qdrant / store / task 等）。
"""

import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ImportIndexStatus",
    "PaperImportErrorCode",
    "PaperImportRequest",
    "PaperImportResult",
    "ImportResourceCapability",
    "PaperImportPort",
]


def _new_attempt_owner() -> str:
    """Return a non-secret, server-owned attempt identity."""
    return f"paper-import:{uuid.uuid4().hex}"


def _new_attempt_token() -> str:
    """Return the secret capability half of an import attempt."""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class ImportResourceCapability:
    """Internal proof for resources created by one paper-import attempt.

    This object is deliberately not part of the HTTP result serializer.  The
    token is only passed between the import adapter and its compensation seam.
    ``source_dev``/``source_ino`` bind cleanup to the directory entry observed
    at create time, rather than to a reusable document id or pathname.
    """

    owner: str
    token: str
    document_id: str
    source_sha256: str
    stored_name: str
    source_dev: int
    source_ino: int
    destination_collection: str | None = None

    def to_internal_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "token": self.token,
            "document_id": self.document_id,
            "source_sha256": self.source_sha256,
            "stored_name": self.stored_name,
            "source_dev": self.source_dev,
            "source_ino": self.source_ino,
            "destination_collection": self.destination_collection,
        }


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
    attempt_owner: str = field(default_factory=_new_attempt_owner)
    attempt_token: str = field(default_factory=_new_attempt_token)
    source_sha256: str | None = None

    @property
    def owner(self) -> str:
        """Compatibility alias for callers using the shorter capability name."""
        return self.attempt_owner

    @property
    def token(self) -> str:
        """Compatibility alias for callers using the shorter capability name."""
        return self.attempt_token


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
    source_sha256: str | None = None   # 内部对账字段；API 不回传。
    cleanup_status: str | None = None   # ``cleanup_pending`` 表示未知补偿结果。
    resource_capability: ImportResourceCapability | None = None

    @property
    def created_resource(self) -> ImportResourceCapability | None:
        """Internal alias; never included in the HTTP serialization."""
        return self.resource_capability


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

    def compensate_import(self, capability: ImportResourceCapability) -> str:
        """补偿本次 attempt 创建的资源，返回稳定 cleanup 状态。"""
        ...
