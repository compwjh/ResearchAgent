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

import hashlib
import inspect
import os
import re
import threading
import uuid
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable

from backend.app.knowledge_base.infrastructure.document_read import (
    DocumentReadError,
    DocumentSourceReader,
    SourceHead,
    SourceRead,
    validate_source_bytes,
)
from backend.app.knowledge_base.infrastructure.embed import embed_texts, encode_sparse
from backend.app.knowledge_base.infrastructure.index import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    GenerationBoundIndexPort,
    count_points,
    ensure_collection,
    get_client,
    reset_client,
)
from backend.app.knowledge_base.infrastructure.inspection import (
    ChunkSnapshot,
    InspectionError,
    InspectionManifest,
    SourceAnchor,
    SourceBlock,
    build_inspection_manifest,
)
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestClaim,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.migration import (
    KnowledgeDocumentMigrationError,
    build_import_knowledge_document,
    build_uploaded_knowledge_document,
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
    new_record,
    record_id,
    remove_canonical_document,
    resolve_paper_path,
    update_chunker_state,
)
from backend.app.knowledge_base.infrastructure.tasks import (
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

_UPLOAD_LOCK = threading.RLock()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_source_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _generation_root(meta_path: Path) -> Path:
    """Resolve the project root used by the generation marker store."""
    parent = Path(meta_path).resolve().parent
    if parent.name == "kb" and parent.parent.name == "data":
        return parent.parent.parent
    return parent


def _active_generation_collection(meta_path: Path) -> str:
    """Return the marker-bound collection; never fall back to fixed ``papers``."""
    try:
        marker = FinalizeBundleStore(_generation_root(meta_path)).require_generation()
    except ManifestStoreError as error:
        raise KnowledgeDocumentMigrationError(getattr(error, "code", "INDEX_REBUILD_REQUIRED")) from error
    destination = marker.get("alias_target") if isinstance(marker, Mapping) else None
    if not isinstance(destination, str) or not destination:
        raise KnowledgeDocumentMigrationError("INDEX_REBUILD_REQUIRED")
    return destination


def _generation_bound_collection(meta_path: Path, requested: str | None = None) -> str:
    """Resolve a destination and reject caller-supplied marker bypasses."""
    active = _active_generation_collection(meta_path)
    if requested is not None and requested != active:
        raise KnowledgeDocumentMigrationError("INDEX_TOPOLOGY_AMBIGUOUS")
    return active


def _refresh_generation_digests(meta_path: Path) -> None:
    """Keep a committed generation coherent after a canonical state write."""
    FinalizeBundleStore(_generation_root(meta_path)).refresh_live_digests()


def create_uploaded_document(
    file_name: str,
    media_type: str,
    content: bytes,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
) -> dict[str, Any]:
    """Create or deduplicate one immutable canonical document.

    This is the sole HTTP upload application entry.  It writes only a
    server-generated basename and a canonical metadata record; indexing is a
    separate explicit operation and is never invoked from this function.
    """
    if not isinstance(content, bytes):
        content = bytes(content)
    validate_source_bytes(content, media_type)
    if media_type == "text/markdown":
        normalized = content[3:] if content.startswith(b"\xef\xbb\xbf") else content
        if not normalized.decode("utf-8").strip():
            raise DocumentReadError("MARKDOWN_PARSE_FAILED", status=400)
    digest = hashlib.sha256(content).hexdigest()
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    with _UPLOAD_LOCK:
        records = load_papers_strict(meta)
        for item in records:
            if item.get("schema_version") != "knowledge-document-v1":
                continue
            if item.get("source_sha256") != digest or item.get("media_type") != media_type:
                continue
            existing_path = resolve_paper_path(item, root)
            if existing_path.is_file():
                return {"document": dict(item), "deduplicated": True, "task_id": None}

        document_id = uuid.uuid4().hex
        suffix = ".md" if media_type == "text/markdown" else ".pdf"
        stored_name = f"{document_id}{suffix}"
        target = root / stored_name
        try:
            _write_source_exclusive(target, content)
            document = build_uploaded_knowledge_document(
                document_id=document_id,
                file_name=file_name,
                stored_name=stored_name,
                media_type=media_type,
                source_path=target,
            )
            write_import_knowledge_document(document, meta)
            _refresh_generation_digests(meta)
        except Exception:
            with suppress(OSError):
                target.unlink(missing_ok=True)
            raise
        return {"document": document, "deduplicated": False, "task_id": None}


def submit_document_reindex(
    document_id: str,
    chunker: str,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    client: Any = None,
    destination_collection: str | None = None,
) -> dict[str, Any]:
    """Queue reindexing for a canonical document without touching its source."""
    if chunker not in CHUNKERS and chunker != "all":
        raise KnowledgeDocumentMigrationError("CHUNKER_UNSUPPORTED")
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    document = next((item for item in load_papers_strict(meta) if record_id(item) == document_id), None)
    if not isinstance(document, dict) or document.get("schema_version") != "knowledge-document-v1":
        raise KnowledgeDocumentMigrationError("DOCUMENT_NOT_FOUND")
    source = resolve_paper_path(document, root)
    if not source.is_file():
        raise KnowledgeDocumentMigrationError("SOURCE_NOT_FOUND")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise KnowledgeDocumentMigrationError("SOURCE_NOT_FOUND") from error
    expected_hash = document.get("source_sha256")
    if not isinstance(expected_hash, str) or digest.hexdigest() != expected_hash:
        raise KnowledgeDocumentMigrationError("SOURCE_HASH_MISMATCH")
    destination = _generation_bound_collection(meta, destination_collection)
    index_port = GenerationBoundIndexPort(destination, client=client)
    targets = CHUNKERS if chunker == "all" else (chunker,)
    task_id = uuid.uuid4().hex
    submitted: dict[str, bool] = {}
    for name in targets:
        update_chunker_state(document_id, name, status=STATUS_INDEXING, progress=0, error=None, meta_path=meta)

        def runner(progress, selected=name):
            return index_port.index_document(
                document,
                source,
                selected,
                progress=progress,
                meta_path=meta,
            )

        submitted[name] = submit_index_task(document_id, name, runner)
    return {"task_id": task_id, "document_id": document_id, "chunker": chunker, "submitted": submitted}


def delete_document(
    document_id: str,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    manifest_root: Path | None = None,
    destination_collection: str | None = None,
) -> dict[str, Any] | None:
    """Delete one canonical document only after derived vector deletion succeeds."""
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    records = load_papers_strict(meta)
    document = next((item for item in records if record_id(item) == document_id), None)
    if not isinstance(document, dict):
        return None
    tombstoned = False
    store_root = Path(manifest_root or root.parent)
    try:
        destination = _generation_bound_collection(meta, destination_collection)
        GenerationBoundIndexPort(destination).delete_document(document_id)
        manifest_store = InspectionManifestStore(store_root)
        for name in CHUNKERS:
            try:
                manifest_store.tombstone(document_id, name, reason="document_deleted", owner="document-api")
                tombstoned = True
            except ManifestStoreError:
                return {
                    "document_id": document_id,
                    "status": "DELETE_PENDING",
                    "error_code": "DELETE_PENDING",
                    "tombstoned": tombstoned,
                }
        if not remove_canonical_document(document_id, meta, root):
            raise KnowledgeDocumentMigrationError("DOCUMENT_NOT_FOUND")
    except Exception:
        return {
            "document_id": document_id,
            "status": "DELETE_PENDING",
            # Deletion retries expose one stable public state regardless of
            # whether the vector port, generation marker, or tombstone failed.
            "error_code": "DELETE_PENDING",
            "tombstoned": tombstoned,
        }
    return {
        "document_id": document_id,
        "status": "completed",
        "deleted": {"source": True, "metadata": True, "manifests": tombstoned, "vectors": True},
    }


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
        with suppress(OSError):
            names.update(item.name for item in self.papers_dir.iterdir() if item.is_file())
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
            with suppress(Exception):
                remove_canonical_document(paper_id, self.meta_path, self.papers_dir)
        if target is not None:
            with suppress(OSError):
                target.unlink(missing_ok=True)

    def _default_indexer(self, record: PaperRecord, path: Path) -> Any:
        destination = _active_generation_collection(self.meta_path)
        index_port = GenerationBoundIndexPort(destination, client=self.client)
        return run_index_task_sync(
            record.paper_id,
            CHUNKER_V1,
            lambda progress: index_port.index_document(
                record,
                path,
                CHUNKER_V1,
                progress=progress,
                meta_path=self.meta_path,
            ),
        )

    def _default_deleter(self, paper_id: str) -> None:
        destination = _active_generation_collection(self.meta_path)
        GenerationBoundIndexPort(destination, client=self.client).delete_document(paper_id, CHUNKER_V1)

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
                _refresh_generation_digests(self.meta_path)
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
            _refresh_generation_digests(self.meta_path)
            return PortImportResult(
                paper_id=record.paper_id,
                index_status=ImportIndexStatus.INDEXED,
                error_code=None,
                stored_name=safe_name,
            )
        except Exception:
            with suppress(Exception):
                _call_supported(
                    self.deleter or self._default_deleter,
                    (record.paper_id, CHUNKER_V1),
                    {"client": self.client},
                )
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


def create_source_reader(*, meta_path: Path | None = None, papers_dir: Path | None = None) -> DocumentSourceReader:
    """Create the read-only source boundary for document endpoints."""
    return DocumentSourceReader(
        meta_path=Path(meta_path or KB_META_PATH),
        papers_dir=Path(papers_dir or KB_PAPERS_DIR),
    )


def read_document_source(
    document_id: str,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    range_header: str | None = None,
    if_none_match: str | None = None,
    head_only: bool = False,
) -> SourceRead:
    """Read a source through the application-owned, immutable boundary."""
    return create_source_reader(meta_path=meta_path, papers_dir=papers_dir).read(
        document_id,
        range_header=range_header,
        if_none_match=if_none_match,
        head_only=head_only,
    )


def create_manifest_store(*, live_root: Path, claim_root: Path | None = None) -> InspectionManifestStore:
    """Create a manifest store with an explicit root (tempfile in tests)."""
    return InspectionManifestStore(live_root, claim_root=claim_root)

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
    "running_count",
    # 解析与分块
    "build_chunks",
    "extract_pages",
    "split_text",
    # 向量化与索引
    "embed_texts",
    "encode_sparse",
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
    "resolve_paper_path",
    "record_id",
    "update_chunker_state",
    # 索引任务
    "KnowledgeBasePaperImportAdapter",
    "create_paper_import_port",
    "create_uploaded_document",
    "submit_document_reindex",
    "delete_document",
    "create_source_reader",
    "read_document_source",
    "build_inspection_manifest",
    "create_manifest_store",
    "DocumentReadError",
    "SourceHead",
    "SourceRead",
    "validate_source_bytes",
    "InspectionError",
    "InspectionManifest",
    "SourceBlock",
    "ChunkSnapshot",
    "SourceAnchor",
    "FinalizeBundleStore",
    "InspectionManifestStore",
    "ManifestClaim",
    "ManifestStoreError",
    "KnowledgeDocumentMigrationError",
    "build_import_knowledge_document",
    "migrate_papers_json",
    "patch_knowledge_document",
    "write_import_knowledge_document",
    "build_uploaded_knowledge_document",
]
