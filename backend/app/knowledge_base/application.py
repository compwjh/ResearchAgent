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

import contextlib
import hashlib
import inspect
import json
import logging
import os
import re
import tempfile
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
    MetadataStoreError,
    PaperRecord,
    compensate_import_resource,
    get_chunker_state,
    get_paper,
    immutable_directory_lock,
    immutable_lock_domain,
    is_chunker_auto_requeued,
    iter_failed_chunkers,
    load_papers,
    load_papers_strict,
    mark_chunker_auto_requeued,
    new_record,
    record_id,
    register_import_capability,
    remove_canonical_document,
    resolve_paper_path,
    save_papers,
    update_chunker_state,
)
from backend.app.knowledge_base.infrastructure.store import (
    _unlink_owned_source as _store_unlink_owned_source,
)
from backend.app.knowledge_base.infrastructure.tasks import (
    run_index_task_sync,
    running_count,
    submit_index_task,
)
from backend.app.platform.config import KB_META_PATH, KB_PAPERS_DIR
from backend.app.platform.ports import (
    ImportIndexStatus,
    ImportResourceCapability,
    PaperImportErrorCode,
    PaperImportPort,
    PaperImportRequest,
)
from backend.app.platform.ports import (
    PaperImportResult as PortImportResult,
)

# 导入失败在 port 边界会被压成稳定错误码，异常文本不会进入 API 或批次记录。
# 没有日志就只剩一个"论文导入失败"，无法区分下载产物、generation 漂移、
# Ollama embedding 超时等完全不同的故障；这里把真实原因留在服务端日志里。
logger = logging.getLogger(__name__)

_UPLOAD_LOCK = threading.RLock()
_SAFE_SERVER_BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _source_token(stream: Any) -> tuple[int, int]:
    """Return the device/inode identity for a source owned by this call."""
    stat_result = os.fstat(stream.fileno())
    return stat_result.st_dev, stat_result.st_ino


def _unlink_owned_source(path: Path, token: tuple[int, int] | None) -> bool:
    """Probe a failed source target without deleting its directory entry.

    The store-level helper uses the same lockfile and opens the target with
    ``O_NOFOLLOW`` before comparing its fd identity, but intentionally never
    unlinks by pathname.  Failed creates remain identifiable orphans for
    compensation/maintenance, avoiding a replacement race after ``fstat``.
    """
    return _store_unlink_owned_source(path, token, process_locked=True)


def _remove_created_metadata(document_id: str, meta_path: Path) -> None:
    """Roll back this create's metadata without deleting any source path."""
    records = load_papers_strict(meta_path)
    if not any(record_id(item) == document_id for item in records):
        return
    save_papers([item for item in records if record_id(item) != document_id], meta_path)


def _write_source_exclusive(path: Path, content: bytes) -> tuple[int, int]:
    """Create and fsync a source, returning an ownership token.

    The token is returned only after this call successfully created and
    durably wrote the target.  If writing/fsyncing fails after ``O_EXCL`` has
    created the file, the failed target is retained as an identifiable orphan
    for later compensation/maintenance; callers never infer ownership from a
    failed open.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    token: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            token = _source_token(stream)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
        return token
    except Exception:
        _unlink_owned_source(path, token)
        raise
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def _generation_root(meta_path: Path) -> Path:
    """Resolve the project root used by the generation marker store."""
    parent = Path(meta_path).resolve().parent
    if parent.name == "kb" and parent.parent.name == "data":
        return parent.parent.parent
    return parent


def _active_generation_collection(meta_path: Path, *, allow_stale_metadata: bool = False) -> str:
    """Return the marker-bound collection; never fall back to fixed ``papers``.

    ``allow_stale_metadata`` 只放宽「摘要过期」这一种情况：并发的导入/索引正在写
    ``papers.json`` 时，marker 里记的 ``metadata_sha256`` 会短暂对不上，这是瞬时竞态，
    稍后写方会 ``_refresh_generation_digests`` 修正。此时仍然校验 marker 结构并读取
    当前的 ``alias_target``，所以**真正的代次切换（集合换掉了）照样会被
    ``INDEX_GENERATION_DRIFT`` 拦下**。读取路径（启动闸门、状态、检索）一律保持
    fail-closed，不传这个参数。
    """
    try:
        marker = FinalizeBundleStore(_generation_root(meta_path)).require_generation()
    except ManifestStoreError as error:
        if allow_stale_metadata and getattr(error, "code", "") == "INDEX_FINALIZE_REQUIRED":
            return _read_marker_collection_after_state_write(meta_path)
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


def _capability_collection(capability: ImportResourceCapability | None) -> str | None:
    """Return a capability's immutable collection binding, if it has one.

    A capability is the proof for the generation which created its source.
    Treat a malformed non-empty binding as an error rather than silently
    falling back to the current marker (which may now point at a new index).
    """
    if capability is None:
        return None
    value = capability.destination_collection
    if value is None:
        # A capability is an explicit proof of the generation that created
        # its resource.  Falling back to the live marker here would let a
        # stale or forged capability write/delete in a newer generation.
        raise KnowledgeDocumentMigrationError("COMPENSATION_CAPABILITY_INVALID")
    try:
        return GenerationBoundIndexPort(value).destination_collection
    except Exception as error:
        raise KnowledgeDocumentMigrationError("COMPENSATION_CAPABILITY_INVALID") from error


def _read_marker_collection_after_state_write(meta_path: Path) -> str:
    """Read the marker binding when metadata digests are intentionally stale.

    A canonical metadata write makes the marker's old digest stale until the
    following refresh.  ``require_generation`` therefore cannot be used in
    that narrow pre-refresh window.  We still validate the marker shape and
    collection name, and all ordinary reads remain fail-closed through
    ``require_generation``.
    """
    marker_path = FinalizeBundleStore(_generation_root(meta_path)).live_root / "index-generation.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeDocumentMigrationError("INDEX_FINALIZE_REQUIRED") from error
    if not isinstance(marker, Mapping) or marker.get("schema_version") != "index-generation-v1":
        raise KnowledgeDocumentMigrationError("GENERATION_MARKER_INVALID")
    destination = marker.get("alias_target")
    try:
        return GenerationBoundIndexPort(destination).destination_collection
    except Exception as error:
        raise KnowledgeDocumentMigrationError("GENERATION_MARKER_INVALID") from error


def _assert_generation_binding(
    meta_path: Path,
    destination_collection: str | None,
    *,
    allow_stale_metadata: bool = False,
) -> None:
    """Reject a paper import when its captured generation has drifted.

    Marker-less custom indexer fixtures intentionally pass ``None`` and keep
    their existing test seam.  The canonical/default paper-import path always
    captures a collection and must prove it is still live before a metadata
    state transition or digest refresh.
    """
    if destination_collection is None:
        return
    current = _active_generation_collection(meta_path, allow_stale_metadata=allow_stale_metadata)
    if current != destination_collection:
        raise KnowledgeDocumentMigrationError("INDEX_GENERATION_DRIFT")


def _capture_import_generation(meta_path: Path, *, required: bool) -> str | None:
    """Capture the marker-bound destination before creating an import resource.

    Custom injected indexers remain usable in marker-less temporary fixtures.
    The default composition path is fail-closed before it writes source or
    metadata, so an import can never be created without a generation binding.

    放宽摘要过期：并发导入/索引写 ``papers.json`` 期间 marker 摘要会瞬时对不上，
    这里仍然要从**当前** marker 取到 binding（结构校验 + alias_target），
    真正的代次切换由后续 ``_assert_generation_binding`` 拦下。
    """
    generation_store = FinalizeBundleStore(_generation_root(meta_path))
    marker_path = generation_store.live_root / "index-generation.json"
    if not marker_path.exists() and not required:
        return None
    return _active_generation_collection(meta_path, allow_stale_metadata=True)


def _refresh_generation_digests(
    meta_path: Path,
    *,
    expected_destination_collection: str | None = None,
) -> None:
    """Keep a committed generation coherent after a canonical state write."""
    store = FinalizeBundleStore(_generation_root(meta_path))
    if expected_destination_collection is None:
        # Preserve the no-argument compatibility seam used by marker-less
        # fixtures and injected stores.
        store.refresh_live_digests()
    else:
        store.refresh_live_digests(
            expected_destination_collection=expected_destination_collection,
        )


def _unique_server_name(root: Path, requested_name: str, document_id: str, media_type: str) -> str:
    """Return a safe server-owned basename without replacing an existing object."""
    suffix = ".md" if media_type == "text/markdown" else ".pdf"
    requested = str(requested_name or "").strip()
    candidate = Path(requested).name if requested and Path(requested).name == requested else ""
    if (
        not _SAFE_SERVER_BASENAME_RE.fullmatch(candidate)
        or not candidate.lower().endswith(suffix)
    ):
        candidate = f"{document_id}{suffix}"
    if len(candidate.encode("utf-8")) > 255:
        candidate = f"{document_id}{suffix}"
    target = root / candidate
    if not target.exists():
        return candidate
    stem = Path(candidate).stem
    sequence = 2
    while (root / f"{stem}-{sequence}{suffix}").exists():
        sequence += 1
    return f"{stem}-{sequence}{suffix}"


def create_immutable_document(
    file_name: str,
    media_type: str,
    content: bytes | bytearray | memoryview | None = None,
    *,
    source_path: Path | None = None,
    metadata: Mapping[str, Any] | None = None,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    owner: str | None = None,
    token: str | None = None,
    attempt_owner: str | None = None,
    attempt_token: str | None = None,
    destination_collection: str | None = None,
) -> dict[str, Any]:
    """Create or deduplicate one immutable canonical document.

    This is the sole source-creation seam for HTTP uploads and paper imports.
    The document id and stored basename are always server-owned, source bytes
    are written exclusively, and hash/media dedupe happens while the same
    process-wide lock protects the metadata append.  ``metadata`` is limited
    to paper display/provenance fields and never controls source identity.
    """
    owner = owner if owner is not None else attempt_owner
    token = token if token is not None else attempt_token
    if media_type not in {"application/pdf", "text/markdown"}:
        raise KnowledgeDocumentMigrationError("MIGRATION_INPUT_INVALID")
    if (
        not isinstance(file_name, str)
        or not file_name.strip()
        or "/" in file_name
        or "\\" in file_name
        or len(file_name.encode("utf-8")) > 255
    ):
        raise KnowledgeDocumentMigrationError("MIGRATION_INPUT_INVALID")
    if destination_collection is not None:
        try:
            destination_collection = GenerationBoundIndexPort(destination_collection).destination_collection
        except Exception as error:
            raise KnowledgeDocumentMigrationError("INDEX_TOPOLOGY_AMBIGUOUS") from error
    if content is not None and source_path is not None:
        raise KnowledgeDocumentMigrationError("MIGRATION_INPUT_INVALID")
    source = Path(source_path).resolve() if source_path is not None else None
    if source is not None:
        try:
            source_content = source.read_bytes()
        except OSError as error:
            raise KnowledgeDocumentMigrationError("SOURCE_NOT_FOUND") from error
    elif content is not None:
        try:
            source_content = bytes(content)
        except (TypeError, ValueError) as error:
            raise KnowledgeDocumentMigrationError("MIGRATION_INPUT_INVALID") from error
        validate_source_bytes(source_content, media_type)
    else:
        raise KnowledgeDocumentMigrationError("MIGRATION_INPUT_INVALID")
    if media_type == "text/markdown":
        normalized = source_content[3:] if source_content.startswith(b"\xef\xbb\xbf") else source_content
        if not normalized.decode("utf-8").strip():
            raise DocumentReadError("MARKDOWN_PARSE_FAILED", status=400)
    digest = hashlib.sha256(source_content).hexdigest()
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    try:
        lock_domain = immutable_lock_domain(meta, root)
    except MetadataStoreError as error:
        raise KnowledgeDocumentMigrationError(error.code) from error
    # The metadata directory is the shared lock domain for the source and its
    # canonical append. Keeping the lockfile beside papers.json avoids making
    # it look like an immutable source to existing directory inventories.
    with _UPLOAD_LOCK, immutable_directory_lock(lock_domain):
        records = load_papers_strict(meta)
        for item in records:
            if item.get("schema_version") != "knowledge-document-v1":
                continue
            if item.get("source_sha256") != digest or item.get("media_type") != media_type:
                continue
            existing_path = resolve_paper_path(item, root)
            if existing_path.is_file():
                try:
                    existing_digest = hashlib.sha256(existing_path.read_bytes()).hexdigest()
                except OSError:
                    existing_digest = None
                if existing_digest == digest:
                    return {
                        "document": dict(item),
                        "deduplicated": True,
                        "etag": f'"sha256:{digest}"',
                        "task_id": None,
                    }

        document_id = uuid.uuid4().hex
        stored_name = _unique_server_name(root, file_name, document_id, media_type)
        target = root / stored_name
        source_token: tuple[int, int] | None = None
        resource_capability: ImportResourceCapability | None = None
        try:
            source_token = _write_source_exclusive(target, source_content)
            if metadata is None:
                document = build_uploaded_knowledge_document(
                    document_id=document_id,
                    file_name=file_name,
                    stored_name=stored_name,
                    media_type=media_type,
                    source_path=target,
                )
            else:
                values = dict(metadata)
                record = new_record(
                    file_name,
                    uploaded_at=None,
                    title=values.get("title"),
                    authors=list(values.get("authors") or []),
                    year=values.get("year"),
                    conference_id=values.get("conference_id"),
                    conference_name=values.get("conference_name"),
                    doi=values.get("doi"),
                    dblp_key=values.get("dblp_key"),
                    source_url=values.get("source_url"),
                    import_source=values.get("import_source"),
                    stored_name=stored_name,
                )
                record.paper_id = document_id
                record.status = STATUS_INDEXING
                document = build_import_knowledge_document(record, target)
            if document.get("source_sha256") != digest:
                raise KnowledgeDocumentMigrationError("SOURCE_HASH_MISMATCH")
            if owner is not None or token is not None:
                if not owner or not token or source_token is None:
                    raise KnowledgeDocumentMigrationError("COMPENSATION_CAPABILITY_INVALID")
                resource_capability = ImportResourceCapability(
                    owner=str(owner),
                    token=str(token),
                    document_id=document_id,
                    source_sha256=digest,
                    stored_name=stored_name,
                    source_dev=source_token[0],
                    source_ino=source_token[1],
                    destination_collection=destination_collection,
                )
                # The ledger is intentionally separate from papers.json, whose
                # frozen schema must remain compatible with older readers.
                register_import_capability(resource_capability, meta, process_locked=True)
            # Paper imports carry a captured generation.  Check immediately
            # before the canonical metadata write so an already-drifted marker
            # cannot make a resource look valid in the new generation.
            #
            # 这里必须容忍摘要过期：并发的索引任务正在写 papers.json 时摘要会瞬时
            # 对不上（INDEX_FINALIZE_REQUIRED），而那是正常竞态、不是代次切换。
            # 真正需要拦的是 alias_target 变化，由 INDEX_GENERATION_DRIFT 负责。
            _assert_generation_binding(meta, destination_collection, allow_stale_metadata=True)
            write_import_knowledge_document(document, meta)
            # The marker can drift while metadata is being written.  Check
            # again before refreshing its digest; on failure the surrounding
            # rollback/compensation path retains no successful metadata.
            _assert_generation_binding(meta, destination_collection, allow_stale_metadata=True)
            # Re-check and refresh under the manifest-store lock.  This closes
            # the gap where commit could switch the marker after the check but
            # before the digest write, which would bless old metadata in the
            # new generation.
            _refresh_generation_digests(
                meta,
                expected_destination_collection=destination_collection,
            )
        except Exception as error:
            _unlink_owned_source(target, source_token)
            # A metadata writer may fail after exposing a partial append.  Roll
            # back only the generated id and deliberately keep source cleanup
            # separate, so a target replaced by another process is untouched.
            with suppress(Exception):
                _remove_created_metadata(document_id, meta)
            if resource_capability is not None:
                error.resource_capability = resource_capability
            raise
        return {
            "document": document,
            "deduplicated": False,
            "etag": f'"sha256:{digest}"',
            "task_id": None,
            "resource_capability": resource_capability,
        }


def create_uploaded_document(
    file_name: str,
    media_type: str,
    content: bytes,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for the canonical upload application seam."""
    return create_immutable_document(
        file_name,
        media_type,
        content,
        meta_path=meta_path,
        papers_dir=papers_dir,
    )


def _document_record(document_id: str, meta_path: Path) -> dict[str, Any] | None:
    """Return one canonical document record through the metadata boundary."""
    return next(
        (
            item
            for item in load_papers_strict(meta_path)
            if isinstance(item, dict)
            and item.get("schema_version") == "knowledge-document-v1"
            and record_id(item) == str(document_id)
        ),
        None,
    )


_ASSOCIATION_SCHEMA = "project-document-associations-v1"


def _association_path(meta_path: Path) -> Path:
    """Return the sidecar relation store beside canonical ``papers.json``."""
    return Path(meta_path).with_name("project-associations.json")


def _load_associations(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATIONS_INVALID") from error
    if not isinstance(value, Mapping) or value.get("schema_version") != _ASSOCIATION_SCHEMA:
        raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATIONS_INVALID")
    associations = value.get("associations")
    if not isinstance(associations, Mapping):
        raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATIONS_INVALID")
    normalized: dict[str, dict[str, str]] = {}
    for document_id, relation in associations.items():
        if not isinstance(document_id, str) or not document_id or not isinstance(relation, Mapping):
            raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATIONS_INVALID")
        owner_id = relation.get("owner_id")
        project_id = relation.get("project_id")
        if not isinstance(owner_id, str) or not owner_id or not isinstance(project_id, str) or not project_id:
            raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATIONS_INVALID")
        normalized[document_id] = {"owner_id": owner_id, "project_id": project_id}
    return normalized


def _save_associations(path: Path, associations: Mapping[str, Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"schema_version": _ASSOCIATION_SCHEMA, "associations": dict(associations)},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(OSError):
            temporary.unlink()


def _validated_project_id(project_id: str | None) -> str | None:
    if project_id is None:
        return None
    if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 100:
        raise KnowledgeDocumentMigrationError("INVALID_PROJECT_ID")
    return project_id.strip()


def _relation_owner_ok(relation: Mapping[str, str], owner_id: str | None) -> bool:
    return owner_id is None or relation.get("owner_id") == owner_id


def set_document_project(
    document_id: str,
    project_id: str | None,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    owner_id: str | None = None,
) -> dict[str, Any] | None:
    """Associate or disassociate a canonical document without touching its source.

    The relation is kept in a sidecar store rather than the closed canonical
    document schema.  The returned record is a presentation overlay only;
    ``papers.json`` remains byte/schema-valid and immutable document identity
    is unchanged.
    """
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    normalized_project = _validated_project_id(project_id)
    normalized_owner = str(owner_id or "local-user")
    try:
        lock_domain = immutable_lock_domain(meta, root)
    except MetadataStoreError as error:
        raise KnowledgeDocumentMigrationError(error.code) from error
    with _UPLOAD_LOCK, immutable_directory_lock(lock_domain):
        records = load_papers_strict(meta)
        document = next(
            (
                item
                for item in records
                if isinstance(item, dict)
                and item.get("schema_version") == "knowledge-document-v1"
                and record_id(item) == str(document_id)
            ),
            None,
        )
        if document is None:
            return None
        # Repair a record written by the pre-review implementation, but never
        # introduce this closed-schema field on the normal path.
        if "project_id" in document:
            document.pop("project_id", None)
            save_papers(records, meta)
        assoc_path = _association_path(meta)
        associations = _load_associations(assoc_path)
        current = associations.get(str(document_id))
        if current is not None and not _relation_owner_ok(current, owner_id):
            raise KnowledgeDocumentMigrationError("PROJECT_ASSOCIATION_FORBIDDEN")
        if normalized_project is None:
            associations.pop(str(document_id), None)
        else:
            associations[str(document_id)] = {
                "owner_id": normalized_owner,
                "project_id": normalized_project,
            }
        _save_associations(assoc_path, associations)
        result = dict(document)
        result["project_id"] = normalized_project
        return result


def clear_project_document_associations(
    project_id: str,
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    owner_id: str | None = None,
) -> int:
    """Detach all documents from a deleted project and retain their originals."""
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    try:
        lock_domain = immutable_lock_domain(meta, root)
    except MetadataStoreError as error:
        raise KnowledgeDocumentMigrationError(error.code) from error
    with _UPLOAD_LOCK, immutable_directory_lock(lock_domain):
        normalized_project = _validated_project_id(project_id)
        associations = _load_associations(_association_path(meta))
        removed = [
            document_id
            for document_id, relation in associations.items()
            if relation.get("project_id") == normalized_project and _relation_owner_ok(relation, owner_id)
        ]
        for document_id in removed:
            associations.pop(document_id, None)
        if removed:
            _save_associations(_association_path(meta), associations)
        changed = len(removed)
        return changed


def list_documents_for_project(
    project_id: str | None = None,
    *,
    meta_path: Path | None = None,
    owner_id: str | None = None,
) -> list[dict[str, Any]]:
    """List canonical records in one explicit scope.

    ``None`` means the unbound/shared pool; a project ID means only that
    project's documents.  Project chat must not silently absorb unrelated
    global documents merely because they are unbound.
    """
    meta = Path(meta_path or KB_META_PATH)
    records = load_papers_strict(meta)
    associations = _load_associations(_association_path(meta))
    return [
        {
            **dict(item),
            "project_id": associations[record_id(item)]["project_id"],
        }
        for item in records
        if isinstance(item, dict)
        and item.get("schema_version") == "knowledge-document-v1"
        and record_id(item) in associations
        and associations[record_id(item)].get("project_id") == project_id
        and _relation_owner_ok(associations[record_id(item)], owner_id)
    ]


def get_document_project(
    document_id: str,
    *,
    meta_path: Path | None = None,
    owner_id: str | None = None,
) -> str | None:
    associations = _load_associations(_association_path(Path(meta_path or KB_META_PATH)))
    relation = associations.get(str(document_id))
    if relation is None or not _relation_owner_ok(relation, owner_id):
        return None
    return relation["project_id"]


def decorate_document_projects(
    records: list[dict[str, Any]], *, meta_path: Path | None = None, owner_id: str | None = None
) -> list[dict[str, Any]]:
    associations = _load_associations(_association_path(Path(meta_path or KB_META_PATH)))
    return [
        {
            **dict(record),
            "project_id": (
                associations.get(record_id(record), {}).get("project_id")
                if _relation_owner_ok(associations.get(record_id(record), {}), owner_id)
                else None
            ),
        }
        for record in records
    ]


def filter_hits_for_project(
    hits: list[Hit], project_id: str | None, *, meta_path: Path | None = None, owner_id: str | None = None
) -> list[Hit]:
    """Compatibility guard for callers outside the retrieval application seam."""
    visible = {
        record_id(item)
        for item in list_documents_for_project(project_id, meta_path=meta_path, owner_id=owner_id)
    }
    return [hit for hit in hits if hit.paper_id in visible]


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


def recover_failed_reindexes(
    *,
    meta_path: Path | None = None,
    papers_dir: Path | None = None,
    client: Any = None,
    destination_collection: str | None = None,
) -> int:
    """spec-036 Task06 启动自愈：把陈旧的 `failed` 重建任务重排队一次。

    根因说明：这些 failed 是**环境故障遗留状态**（Qdrant 本地锁冲突 /
    索引代际门禁未 finalize 故障期），不是切分 / 索引逻辑 bug —— 实测手动重试
    全部成功。因此这里只做一次性机会重试，不做无限重试。

    幂等（防重启风暴）：每个 (document_id, chunker) 仅重排队一次，依据是持久化在
    chunker 状态上的 `auto_requeued_at` 标记（落盘 papers.json，跨进程重启保留）。
    重试后若仍失败，状态回到 failed 但标记已存在 → 下次启动不再重排队。

    异常安全：单篇排队失败（如源文件丢失）只记日志、跳过，不影响其它文档；本函数
    整体也不抛出，由 main.py 启动恢复按既有范式捕获记日志，绝不阻塞服务启动。
    """
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    queued = 0
    for document_id, chunker in iter_failed_chunkers(meta):
        # 已自动重排队过（标记持久化）→ 跳过，绝不二次排队（防重启风暴 / 无限重试）
        if is_chunker_auto_requeued(document_id, chunker, meta):
            continue
        try:
            submit_document_reindex(
                document_id,
                chunker,
                meta_path=meta,
                papers_dir=root,
                client=client,
                destination_collection=destination_collection,
            )
        except Exception as error:  # 单篇失败不阻断其它文档，也不阻断启动
            logger.warning(
                "启动自愈跳过文档 %s 的 %s 重建（排队失败，保持 failed 态）：%s",
                document_id, chunker, error,
            )
            continue
        mark_chunker_auto_requeued(document_id, chunker, meta)
        queued += 1
    if queued:
        logger.info("启动自愈已重排队 %d 个陈旧失败重建任务", queued)
    return queued


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


def _index_error_detail(value: Any) -> str:
    """Extract the indexer's own failure text for server-side diagnostics.

    ``_index_succeeded`` only reports a boolean; the real cause (for example
    ``索引失败：无法连接 Ollama：timed out``) lives inside the result mapping.
    This never reaches the API or durable state — it is log-only.
    """
    if value is None:
        return ""
    if not isinstance(value, Mapping):
        return str(getattr(value, "error", "") or "")
    parts: list[str] = []
    top = value.get("error")
    if top:
        parts.append(str(top))
    chunkers = value.get("chunkers")
    if isinstance(chunkers, Mapping):
        for name, state in chunkers.items():
            if isinstance(state, Mapping):
                message = state.get("error") or state.get("status")
                if message:
                    parts.append(f"{name}={message}")
    return "; ".join(parts)


def _deletion_succeeded(value: Any) -> bool:
    """Interpret an injected vector-delete result without guessing unknowns."""
    if value is None:
        # Existing tiny deleter doubles use a successful ``None`` return.
        return True
    if value is True:
        return True
    if value is False:
        return False
    status = getattr(value, "status", None)
    if status is None and isinstance(value, Mapping):
        status = value.get("status")
    if status is None:
        status = value
    return str(getattr(status, "value", status)).casefold() in {"completed", "deleted", "success"}


_STORAGE_LOCKED_MARKER = "already accessed by another instance"


def _is_storage_locked_text(value: Any) -> bool:
    """判定一段诊断文本是否说明 qdrant 存储被另一个实例独占。

    索引器常常**不抛异常**、而是把原因放进结果映射里（见 ``_index_error_detail``）；
    上层只看到一句裸的 ``RuntimeError("index failed")``。所以除了异常本身，
    也必须能从索引器返回的原文做同一窄匹配。
    """
    return _STORAGE_LOCKED_MARKER in str(value or "")


def _is_storage_locked_error(error: BaseException) -> bool:
    """窄匹配 qdrant 存储被另一个实例独占的 RuntimeError（spec-021 Task03）。

    知识库上下文不持有导入错误码表，故此处仅识别并上抛，由消费方
    （paper_discovery.application.paper_import）映射为固定文案的 KB_STORAGE_LOCKED。
    绝不把异常原文（可能含路径）作为返回内容。
    """
    return isinstance(error, RuntimeError) and _is_storage_locked_text(error)


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

    def compensate_import(self, capability: ImportResourceCapability) -> str:
        """Compensate only a resource proven to belong to this attempt."""
        return compensate_import_resource(capability, self.meta_path, self.papers_dir)

    def _cleanup(self, capability: ImportResourceCapability | None) -> str:
        """Compatibility helper retaining fail-closed compensation semantics."""
        if capability is None:
            return "cleanup_pending"
        try:
            return self.compensate_import(capability)
        except Exception:
            return "cleanup_pending"

    def _default_indexer(
        self,
        record: PaperRecord,
        path: Path,
        *,
        capability: ImportResourceCapability | None = None,
    ) -> Any:
        # Use the collection captured at immutable-create time.  If no
        # capability exists (for example a direct reindex-style test seam),
        # resolve the current marker as usual.
        destination = (
            _capability_collection(capability)
            if capability is not None
            else _active_generation_collection(self.meta_path)
        )
        index_port = GenerationBoundIndexPort(destination, client=self.client)
        # v1 同步建索引：完成后导入即可返回；v2 随后异步提交，不阻塞导入响应。
        result = run_index_task_sync(
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
        # BUG-02（spec-020 Task03）：与上传路径对齐，v1 建完后异步提交 v2。
        # 使用同一代际绑定，避免 paper-import 绕过候选 Collection 约束。
        self._submit_v2_index(record, path, destination)
        return result

    def _submit_v2_index(self, record: PaperRecord, path: Path, destination: str) -> None:
        """v1 索引成功后异步提交 v2（语义对齐上传路径 `_submit_index_task`）。

        先置 v2 为 ``indexing`` 再入单线程池，使 v2 在池中排队时前端即可看到
        「索引中 0%」而非停留在 pending。v2 失败不影响导入成功（状态置 ``failed``
        并带原因，可由 reindex 补救）；提交异常同样不得把导入判定为失败。
        """
        try:
            update_chunker_state(
                record.paper_id,
                CHUNKER_V2,
                status=STATUS_INDEXING,
                progress=0,
                error=None,
                meta_path=self.meta_path,
            )
        except Exception:
            # 状态置位失败不得拖垮已成功的导入；交由后续 reindex 补救。
            return

        def _runner(progress) -> dict:
            return GenerationBoundIndexPort(destination, client=self.client).index_document(
                record,
                path,
                CHUNKER_V2,
                progress=progress,
                meta_path=self.meta_path,
            )

        try:
            submit_index_task(record.paper_id, CHUNKER_V2, _runner)
        except Exception:
            # 提交失败同样不得判定导入失败；把 v2 状态置 failed 以便可见与补救。
            with contextlib.suppress(Exception):
                update_chunker_state(
                    record.paper_id,
                    CHUNKER_V2,
                    status=STATUS_FAILED,
                    progress=0,
                    error="v2 索引任务提交失败",
                    meta_path=self.meta_path,
                )

    def _default_deleter(self, paper_id: str, *, capability: ImportResourceCapability | None = None) -> None:
        destination = (
            _capability_collection(capability)
            if capability is not None
            else _active_generation_collection(self.meta_path)
        )
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
        try:
            source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            return PortImportResult(
                paper_id=None,
                index_status=ImportIndexStatus.FAILED,
                error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
            )
        if request.source_sha256 is not None and request.source_sha256 != source_digest:
            return PortImportResult(
                paper_id=None,
                index_status=ImportIndexStatus.FAILED,
                error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
            )

        with self._lock:
            existing = self.find_existing(snapshot)
            if existing is not None:
                return existing
            try:
                generation_collection = _capture_import_generation(
                    self.meta_path,
                    required=self.indexer is None,
                )
            except KnowledgeDocumentMigrationError as error:
                logger.error(
                    "论文导入失败：索引代次不可用 meta_path=%s code=%s（需重建索引）",
                    self.meta_path, getattr(error, "code", "INDEX_REBUILD_REQUIRED"),
                )
                return PortImportResult(
                    paper_id=None,
                    index_status=ImportIndexStatus.FAILED,
                    error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
                    source_sha256=source_digest,
                )
            requested_name = str(_snapshot_value(snapshot, "_stored_name") or source.name)
            identity_doi, identity_dblp, _, _, _ = _identity_parts(snapshot)
            try:
                created = create_immutable_document(
                    requested_name,
                    "application/pdf",
                    source_path=source,
                    metadata={
                        "title": _snapshot_value(snapshot, "title"),
                        "authors": list(_snapshot_value(snapshot, "authors", []) or []),
                        "year": _snapshot_value(snapshot, "year"),
                        "conference_id": _snapshot_value(snapshot, "conference_id"),
                        "conference_name": _snapshot_value(snapshot, "conference_name"),
                        "doi": identity_doi or None,
                        "dblp_key": identity_dblp or None,
                        "source_url": _snapshot_value(snapshot, "article_url"),
                        "import_source": "paper-discovery",
                    },
                    meta_path=self.meta_path,
                    papers_dir=self.papers_dir,
                    owner=request.attempt_owner,
                    token=request.attempt_token,
                    destination_collection=generation_collection,
                )
            except Exception as error:
                capability = getattr(error, "resource_capability", None)
                if _is_storage_locked_error(error):
                    # Preserve the stable storage-contention mapping at the
                    # paper-discovery boundary; do not flatten it to import failure.
                    raise
                logger.exception(
                    "论文导入失败：创建不可变文档出错 name=%s collection=%s",
                    requested_name, generation_collection,
                )
                return PortImportResult(
                    paper_id=None,
                    index_status=ImportIndexStatus.FAILED,
                    error_code=PaperImportErrorCode.KB_IMPORT_FAILED,
                    source_sha256=source_digest,
                    cleanup_status="cleanup_pending" if capability is not None else None,
                    resource_capability=capability,
                )
            document = created["document"]
            safe_name = str(document["stored_name"])
            target = resolve_paper_path(document, self.papers_dir)
            if created["deduplicated"]:
                return PortImportResult(
                    paper_id=record_id(document),
                    index_status=_port_status(document.get("status")),
                    error_code=None,
                    stored_name=safe_name,
                    existing=True,
                    source_sha256=document.get("source_sha256"),
                )
            record = PaperRecord(
                paper_id=record_id(document),
                file_name=str(document["file_name"]),
                status=STATUS_INDEXING,
                uploaded_at=str(document["created_at"]),
                title=document.get("title"),
                authors=list(document.get("authors") or []),
                year=document.get("year"),
                conference_id=document.get("conference_id"),
                conference_name=document.get("conference_name"),
                doi=document.get("doi"),
                dblp_key=document.get("dblp_key"),
                source_url=document.get("source_url"),
                import_source=document.get("import_source"),
                stored_name=safe_name,
            )

        # 区分两段失败：索引本身失败（KB_INDEX_FAILED，文件已落盘、可重建索引）
        # 与索引成功后的收尾失败（generation 漂移 / 元数据写回失败，KB_IMPORT_FAILED）。
        index_ok = False
        try:
            index_result = _call_supported(
                self.indexer or self._default_indexer,
                (record, target),
                {
                    "meta_path": self.meta_path,
                    "client": self.client,
                    "capability": created.get("resource_capability"),
                },
            )
            if not _index_succeeded(index_result):
                # 索引器常常不抛异常、只把原因放进结果里。裸抛 "index failed" 会把原因
                # 丢在日志里，上层（以及 paper_discovery 的窄匹配）再也认不出存储争用，
                # 最终吞成不可行动的 KB_INDEX_FAILED。这里把**已分类**的原因带上：
                # 只写判定出的类别标记，绝不把含路径的原文放进异常。
                detail = _index_error_detail(index_result)
                raise RuntimeError(
                    f"index failed: {_STORAGE_LOCKED_MARKER}"
                    if _is_storage_locked_text(detail)
                    else "index failed"
                )
            index_ok = True
            updates: dict[str, Any] = {"status": STATUS_INDEXED, "error": None}
            if isinstance(index_result, Mapping):
                if isinstance(index_result.get("chunkers"), dict):
                    updates["chunkers"] = index_result["chunkers"]
                for field in ("page_count", "chunk_count", "error"):
                    if field in index_result:
                        updates[field] = index_result[field]
            _assert_generation_binding(self.meta_path, generation_collection)
            patch_knowledge_document(self.meta_path, record.paper_id, **updates)
            _assert_generation_binding(self.meta_path, generation_collection, allow_stale_metadata=True)
            # Re-check and refresh atomically with generation publication.
            _refresh_generation_digests(
                self.meta_path,
                expected_destination_collection=generation_collection,
            )
            return PortImportResult(
                paper_id=record.paper_id,
                index_status=ImportIndexStatus.INDEXED,
                error_code=None,
                stored_name=safe_name,
                source_sha256=document.get("source_sha256"),
                resource_capability=created.get("resource_capability"),
            )
        except Exception as error:
            storage_locked = _is_storage_locked_error(error)
            capability = created.get("resource_capability")
            logger.error(
                "论文导入失败：%s paper_id=%s stored_name=%s collection=%s"
                " 索引返回=%s 异常=%s: %s",
                "向量索引未成功" if not index_ok else "索引成功但收尾失败（代次漂移/元数据写回）",
                getattr(record, "paper_id", None), safe_name, generation_collection,
                _index_error_detail(locals().get("index_result")) or "<索引器抛异常>",
                type(error).__name__, error,
            )
            vector_unknown = False
            try:
                # A caller-supplied deleter is an explicit, testable seam.  In
                # the isolated adapter (no client/marker) there is no vector
                # resource to delete; production uses the marker-bound default.
                if self.deleter is not None:
                    delete_result = _call_supported(
                        self.deleter,
                        (record.paper_id, CHUNKER_V1),
                        {"client": self.client, "capability": capability},
                    )
                elif self.client is not None:
                    delete_result = _call_supported(
                        self._default_deleter,
                        (record.paper_id, CHUNKER_V1),
                        {"client": self.client, "capability": capability},
                    )
                else:
                    delete_result = None
                if not _deletion_succeeded(delete_result):
                    vector_unknown = True
            except Exception:
                vector_unknown = True
            cleanup_status = "cleanup_pending"
            if not vector_unknown:
                cleanup_status = self._cleanup(capability)
            if storage_locked:
                # Let the paper-discovery boundary map this narrowly matched
                # storage contention to its stable, retryable error code.
                raise
            return PortImportResult(
                paper_id=record.paper_id if cleanup_status != "completed" else None,
                index_status=ImportIndexStatus.FAILED,
                # index_ok 为假说明索引本身没建起来：源文件与元数据已落盘，
                # 用专门错误码让调用方区分"根本没入库"和"已入库待重建索引"。
                # 索引成功但收尾失败（代次漂移等）仍归 KB_IMPORT_FAILED。
                error_code=(
                    PaperImportErrorCode.KB_INDEX_FAILED if not index_ok
                    else PaperImportErrorCode.KB_IMPORT_FAILED
                ),
                source_sha256=document.get("source_sha256"),
                cleanup_status=cleanup_status if cleanup_status != "completed" else None,
                resource_capability=capability if cleanup_status != "completed" else None,
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
    "create_immutable_document",
    "create_uploaded_document",
    "set_document_project",
    "clear_project_document_associations",
    "list_documents_for_project",
    "get_document_project",
    "decorate_document_projects",
    "filter_hits_for_project",
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
