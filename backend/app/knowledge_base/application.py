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

from __future__ import annotations

import inspect
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

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
from backend.app.knowledge_base.infrastructure.migration import (
    KnowledgeDocumentMigrationError,
    build_import_knowledge_document,
    migrate_papers_json,
    patch_knowledge_document,
    write_import_knowledge_document,
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
    rerank_hits,
    reranker_available,
    reranker_health,
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
    copy_source_exclusive,
    get_chunker_state,
    get_paper,
    load_papers,
    load_papers_strict,
    mark_interrupted_tasks,
    new_record,
    record_id,
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
from backend.app.platform.config import KB_META_PATH, KB_PAPERS_DIR
from backend.app.platform.ports import (
    ImportIndexStatus,
    PaperImportErrorCode,
    PaperImportPort,
    PaperImportRequest,
)
from backend.app.platform.ports import (
    PaperImportResult as PortImportResult,
)


def _snapshot_value(snapshot: Mapping[str, Any], name: str, default: Any = None) -> Any:
    return snapshot.get(name, default)


def _identity_parts(value: Any) -> tuple[str, str, str, str, str]:
    """Build the storage-side identity without importing paper-discovery code."""
    doi = str(value.get("doi") or "").strip().casefold()
    dblp = str(value.get("dblp_key") or value.get("dblp") or "").strip().casefold()
    title = re.sub(r"\s+", " ", str(value.get("title") or "").strip()).casefold()
    year = str(value.get("year") or "").strip()
    conference = str(value.get("conference_id") or value.get("conference") or "").strip().casefold()
    return doi, dblp, title, year, conference


def _same_identity(candidate: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    left = _identity_parts(candidate)
    right = _identity_parts(record)
    left_doi, left_dblp, left_title, left_year, left_conf = left
    right_doi, right_dblp, right_title, right_year, right_conf = right
    if left_doi or right_doi:
        if left_doi and right_doi:
            return left_doi == right_doi
        return bool(
            left_dblp and right_dblp and left_dblp == right_dblp
            and left_year == right_year and left_conf == right_conf
        )
    if left_dblp and right_dblp:
        return left_dblp == right_dblp and left_year == right_year and left_conf == right_conf
    return bool(
        left_title and left_title == right_title and left_year
        and left_year == right_year and left_conf and left_conf == right_conf
    )


def _port_status(value: Any) -> ImportIndexStatus:
    status = str(value or STATUS_PENDING)
    if status == STATUS_INDEXED:
        return ImportIndexStatus.INDEXED
    if status == STATUS_FAILED:
        return ImportIndexStatus.FAILED
    return ImportIndexStatus.PENDING


def _index_succeeded(value: Any) -> bool:
    if value is True:
        return True
    status = getattr(value, "status", None)
    if status is None and isinstance(value, Mapping):
        status = value.get("status")
        if status is None and isinstance(value.get("paper"), Mapping):
            status = value["paper"].get("status")
        if value.get("error") and status is None:
            return False
    return status == STATUS_INDEXED


def _call_supported(function: Callable[..., Any], positional: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return function(*positional, **kwargs)
    accepts_kwargs = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters)
    accepted = kwargs if accepts_kwargs else {
        key: value for key, value in kwargs.items() if key in inspect.signature(function).parameters
    }
    positional_parameters = [
        item for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return function(*positional[: len(positional_parameters)], **accepted)


class KnowledgeBasePaperImportAdapter:
    """知识库侧 ``PaperImportPort`` 实现。

    论文发现只交给本适配器一个候选快照和受信任的本地 PDF。元数据写入、
    文件归档、v1 索引及失败补偿均在知识库上下文内完成，避免跨上下文读取
    ``store`` / ``index`` / ``tasks`` 内部实现。
    """

    def __init__(
        self,
        *,
        papers_dir: Path | None = None,
        meta_path: Path | None = None,
        indexer: Callable[..., Any] | None = None,
        deleter: Callable[..., Any] | None = None,
        client: Any = None,
    ) -> None:
        self.papers_dir = Path(papers_dir or KB_PAPERS_DIR).resolve()
        self.meta_path = Path(meta_path or KB_META_PATH).resolve()
        self.indexer = indexer
        self.deleter = deleter
        self.client = client
        self._lock = threading.RLock()

    def existing_names(self) -> set[str]:
        names = {
            str(item.get("stored_name"))
            for item in load_papers_strict(self.meta_path)
            if isinstance(item, dict) and item.get("stored_name")
        }
        try:
            names.update(item.name for item in self.papers_dir.iterdir() if item.is_file())
        except OSError:
            pass
        return names

    def find_existing(self, candidate_snapshot: Mapping[str, Any]) -> PortImportResult | None:
        with self._lock:
            for record in load_papers_strict(self.meta_path):
                if not isinstance(record, dict) or not _same_identity(candidate_snapshot, record):
                    continue
                existing_id = record_id(record)
                if not existing_id:
                    continue
                return PortImportResult(
                    paper_id=existing_id,
                    index_status=_port_status(record.get("status")),
                    error_code=None,
                    stored_name=record.get("stored_name") or record.get("file_name"),
                    existing=True,
                )
        return None

    def _cleanup(self, paper_id: str | None, target: Path | None) -> None:
        if paper_id:
            try:
                remove_paper(paper_id, self.meta_path, self.papers_dir)
            except Exception:
                pass
        if target is not None:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass

    def _default_indexer(self, record: PaperRecord, path: Path) -> Any:
        return run_index_task_sync(
            record.paper_id,
            CHUNKER_V1,
            lambda progress: index_paper_chunker(
                record,
                path,
                CHUNKER_V1,
                progress=progress,
                client=self.client,
                meta_path=self.meta_path,
            ),
        )

    def _default_deleter(self, paper_id: str) -> None:
        delete_paper_chunker(paper_id, CHUNKER_V1, client=self.client)

    def import_paper(self, request: PaperImportRequest) -> PortImportResult:
        snapshot = request.candidate_snapshot
        source = Path(request.trusted_pdf_path).resolve()
        if not source.is_file():
            return PortImportResult(
                paper_id=None,
                index_status=ImportIndexStatus.FAILED,
                error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
            )

        with self._lock:
            existing = self.find_existing(snapshot)
            if existing is not None:
                return existing
            requested_name = str(_snapshot_value(snapshot, "_stored_name") or source.name)
            safe_name = Path(requested_name).name
            if safe_name != requested_name or not safe_name.lower().endswith(".pdf"):
                safe_name = f"{source.stem}.pdf"
            self.papers_dir.mkdir(parents=True, exist_ok=True)
            target = self.papers_dir / safe_name
            if target.exists():
                stem, suffix = target.stem, target.suffix
                sequence = 2
                while target.exists():
                    target = self.papers_dir / f"{stem}-{sequence}{suffix}"
                    sequence += 1
                safe_name = target.name
            identity_doi, identity_dblp, _, _, _ = _identity_parts(snapshot)
            record = new_record(
                safe_name,
                title=_snapshot_value(snapshot, "title"),
                authors=list(_snapshot_value(snapshot, "authors", []) or []),
                year=_snapshot_value(snapshot, "year"),
                conference_id=_snapshot_value(snapshot, "conference_id"),
                conference_name=_snapshot_value(snapshot, "conference_name"),
                doi=identity_doi or None,
                dblp_key=identity_dblp or None,
                source_url=_snapshot_value(snapshot, "article_url"),
                import_source="paper-discovery",
                stored_name=safe_name,
            )
            record.status = STATUS_INDEXING
            try:
                copy_source_exclusive(source, target)
                document = build_import_knowledge_document(record, target)
                write_import_knowledge_document(document, self.meta_path)
                # Keep the legacy failure-injection seam for callers that
                # still patch ``upsert_paper``; the canonical record already
                # exists, and store.upsert_paper is forbidden from downgrading
                # it back to PaperRecord shape.
                upsert_paper(record, self.meta_path)
            except Exception:
                self._cleanup(record.paper_id, target)
                return PortImportResult(
                    paper_id=None,
                    index_status=ImportIndexStatus.FAILED,
                    error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
                )

        try:
            index_result = _call_supported(
                self.indexer or self._default_indexer,
                (record, target),
                {"meta_path": self.meta_path, "client": self.client},
            )
            if not _index_succeeded(index_result):
                raise RuntimeError("index failed")
            updates: dict[str, Any] = {"status": STATUS_INDEXED, "error": None}
            if isinstance(index_result, Mapping):
                if isinstance(index_result.get("chunkers"), dict):
                    updates["chunkers"] = index_result["chunkers"]
                for field in ("page_count", "chunk_count", "error"):
                    if field in index_result:
                        updates[field] = index_result[field]
            patch_knowledge_document(self.meta_path, record.paper_id, **updates)
            return PortImportResult(
                paper_id=record.paper_id,
                index_status=ImportIndexStatus.INDEXED,
                error_code=None,
                stored_name=safe_name,
            )
        except Exception:
            try:
                _call_supported(
                    self.deleter or self._default_deleter,
                    (record.paper_id, CHUNKER_V1),
                    {"client": self.client},
                )
            except Exception:
                pass
            self._cleanup(record.paper_id, target)
            return PortImportResult(
                paper_id=None,
                index_status=ImportIndexStatus.FAILED,
                error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
            )


def create_paper_import_port(
    *,
    papers_dir: Path | None = None,
    meta_path: Path | None = None,
    indexer: Callable[..., Any] | None = None,
    deleter: Callable[..., Any] | None = None,
    client: Any = None,
) -> PaperImportPort:
    """创建知识库侧论文导入适配器；参数仅用于 composition root 与测试替换。"""
    return KnowledgeBasePaperImportAdapter(
        papers_dir=papers_dir,
        meta_path=meta_path,
        indexer=indexer,
        deleter=deleter,
        client=client,
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
    "record_id",
    "save_upload",
    "update_chunker_state",
    "upsert_paper",
    # 索引任务
    "run_index_task_sync",
    "submit_index_task",
    "KnowledgeBasePaperImportAdapter",
    "create_paper_import_port",
    "KnowledgeDocumentMigrationError",
    "build_import_knowledge_document",
    "migrate_papers_json",
    "patch_knowledge_document",
    "write_import_knowledge_document",
]
