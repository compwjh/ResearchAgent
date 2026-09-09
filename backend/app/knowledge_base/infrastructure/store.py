"""论文原件与元数据的本地存储（spec-011）。

元数据落在 `data/kb/papers.json`，原件落在 `data/kb/papers/{paper_id}.pdf`。
所有写操作用同一把锁串行化，避免并发上传/删除产生半截状态。
"""

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import threading
import uuid
from contextlib import contextmanager, nullcontext, suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from backend.app.platform.config import KB_META_PATH, KB_PAPERS_DIR

STATUS_PENDING = "pending"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_PARTIAL = "indexed_partial"
STATUS_FAILED = "failed"

# 切分版本（spec-012）：上传时 v1 同步、v2 异步，两版各自维护状态与进度。
CHUNKER_V1 = "v1"
CHUNKER_V2 = "v2"
CHUNKERS = (CHUNKER_V1, CHUNKER_V2)

_lock = threading.RLock()

_COMPENSATION_LEDGER_SUFFIX = ".paper-import-compensation.json"


@contextmanager
def immutable_directory_lock(directory: Path):
    """Serialize immutable source/metadata creates across processes.

    The lockfile lives in the metadata directory shared by the source and its
    canonical record. Every writer that participates in the create protocol
    uses this same path, so a process cannot observe metadata, choose a
    basename, and append a record concurrently with another create.
    """
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".immutable-create.lock"
    descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        with suppress(OSError):
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _unlink_owned_source(
    path: Path,
    token: tuple[int, int] | None,
    *,
    process_locked: bool = False,
) -> bool:
    """Probe a failed source target without deleting any directory entry.

    There is deliberately no pathname deletion in this helper.
    The caller's process lock is part of the ownership protocol; the open fd
    remains held while ownership is probed. If the target cannot be opened
    without following a symlink, or its fd identity differs, the function
    fails closed and leaves the object as an identifiable orphan. Even a
    matching inode is retained for later compensation/maintenance because a
    replacement can occur immediately after ``fstat``.
    """
    if token is None:
        return False
    lock = nullcontext() if process_locked else immutable_directory_lock(path.parent)
    with lock:
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(str(path), flags)
            stat_result = os.fstat(descriptor)
            if (stat_result.st_dev, stat_result.st_ino) != token or stat_result.st_nlink != 1:
                return False
            # Never unlink by pathname after this check: the directory entry
            # may have been replaced immediately after fstat(). Retain the
            # failed create as an identifiable orphan for later compensation.
            return False
        except OSError:
            return False
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)

# 用于区分"不更新 error"与"把 error 置为 None"
_UNSET = object()
_SERVER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class MetadataStoreError(RuntimeError):
    """Stable error for metadata write-path corruption."""

    def __init__(self, code: str = "METADATA_INVALID") -> None:
        self.code = code
        super().__init__(code)


IMMUTABLE_LOCK_DOMAIN_MISMATCH = "IMMUTABLE_LOCK_DOMAIN_MISMATCH"


def immutable_lock_domain(meta_path: Path, papers_dir: Path) -> Path:
    """Return the canonical lock domain shared by metadata and source paths.

    The metadata file and source directory must resolve beneath the same
    physical parent domain. Rejecting a mismatch is safer than letting the
    two writers acquire different lockfiles and claiming process safety.
    """
    metadata_parent = Path(meta_path).resolve().parent
    source_parent = Path(papers_dir).resolve().parent
    if metadata_parent != source_parent:
        raise MetadataStoreError(IMMUTABLE_LOCK_DOMAIN_MISMATCH)
    return metadata_parent


def _compensation_ledger_path(meta_path: Optional[Path] = None) -> Path:
    meta = Path(meta_path or KB_META_PATH)
    return meta.with_name(meta.name + _COMPENSATION_LEDGER_SUFFIX)


def _capability_value(capability: Any, name: str, default: Any = None) -> Any:
    if isinstance(capability, Mapping):
        return capability.get(name, default)
    return getattr(capability, name, default)


def _read_compensation_ledger(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MetadataStoreError("COMPENSATION_LEDGER_INVALID") from error
    if not isinstance(value, dict) or any(not isinstance(item, dict) for item in value.values()):
        raise MetadataStoreError("COMPENSATION_LEDGER_INVALID")
    return {str(key): dict(item) for key, item in value.items()}


def _write_compensation_ledger(path: Path, ledger: Mapping[str, Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        payload = json.dumps(dict(ledger), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # The replacement is not durable until the containing directory has
        # been flushed.  If this fails the caller must retain cleanup_pending;
        # it must never infer a durable capability from an unknown result.
        descriptor = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        with suppress(OSError):
            temporary.unlink()


def register_import_capability(
    capability: Any,
    meta_path: Optional[Path] = None,
    *,
    process_locked: bool = False,
) -> None:
    """Persist an attempt capability outside the public document schema."""
    owner = str(_capability_value(capability, "owner") or "")
    token = str(_capability_value(capability, "token") or "")
    document_id = str(_capability_value(capability, "document_id") or "")
    if not owner or not token or not document_id:
        raise MetadataStoreError("COMPENSATION_CAPABILITY_INVALID")
    meta = Path(meta_path or KB_META_PATH)
    lock = nullcontext() if process_locked else immutable_directory_lock(meta.parent)
    with _lock, lock:
        path = _compensation_ledger_path(meta)
        ledger = _read_compensation_ledger(path)
        current = ledger.get(token)
        value = {
            "owner": owner,
            "document_id": document_id,
            "source_sha256": str(_capability_value(capability, "source_sha256") or ""),
            "stored_name": str(_capability_value(capability, "stored_name") or ""),
            "source_dev": int(_capability_value(capability, "source_dev", -1)),
            "source_ino": int(_capability_value(capability, "source_ino", -1)),
            "destination_collection": _capability_value(capability, "destination_collection"),
            "status": "created",
        }
        immutable_fields = tuple(key for key in value if key != "status")
        if current is not None and any(current.get(key) != value[key] for key in immutable_fields):
            raise MetadataStoreError("COMPENSATION_CAPABILITY_CONFLICT")
        # A retry must not resurrect a capability already compensated.
        if current is not None and current.get("status") == "completed":
            value["status"] = "completed"
        ledger[token] = value
        _write_compensation_ledger(path, ledger)


def _set_compensation_status(meta: Path, token: str, status: str, error_code: str | None = None) -> None:
    path = _compensation_ledger_path(meta)
    ledger = _read_compensation_ledger(path)
    entry = ledger.get(token)
    if entry is None:
        raise MetadataStoreError("COMPENSATION_CAPABILITY_UNKNOWN")
    entry["status"] = status
    if error_code:
        entry["last_error"] = error_code
    else:
        entry.pop("last_error", None)
    ledger[token] = entry
    _write_compensation_ledger(path, ledger)


def compensate_import_resource(
    capability: Any,
    meta_path: Optional[Path] = None,
    papers_dir: Optional[Path] = None,
) -> str:
    """Delete only a capability-owned source and metadata record.

    Any owner/token/document/hash/inode mismatch fails closed.  A completed
    capability is idempotent; uncertain I/O is recorded as ``cleanup_pending``
    and never reported as completed.
    """
    meta = Path(meta_path or KB_META_PATH)
    root = Path(papers_dir or KB_PAPERS_DIR)
    token = str(_capability_value(capability, "token") or "")
    owner = str(_capability_value(capability, "owner") or "")
    document_id = str(_capability_value(capability, "document_id") or "")
    source_hash = str(_capability_value(capability, "source_sha256") or "")
    stored_name = str(_capability_value(capability, "stored_name") or "")
    try:
        source_dev = int(_capability_value(capability, "source_dev"))
        source_ino = int(_capability_value(capability, "source_ino"))
    except (TypeError, ValueError) as error:
        raise MetadataStoreError("COMPENSATION_CAPABILITY_INVALID") from error
    if not all((token, owner, document_id, source_hash, stored_name)) or source_dev < 0 or source_ino < 0:
        raise MetadataStoreError("COMPENSATION_CAPABILITY_INVALID")
    try:
        lock_domain = immutable_lock_domain(meta, root)
    except MetadataStoreError:
        raise
    with _lock, immutable_directory_lock(lock_domain):
        ledger = _read_compensation_ledger(_compensation_ledger_path(meta))
        entry = ledger.get(token)
        expected = {
            "owner": owner,
            "document_id": document_id,
            "source_sha256": source_hash,
            "stored_name": stored_name,
            "source_dev": source_dev,
            "source_ino": source_ino,
        }
        if entry is None or any(entry.get(key) != value for key, value in expected.items()):
            raise MetadataStoreError("COMPENSATION_DENIED")
        if entry.get("status") == "completed":
            return "completed"
        records = load_papers_strict(meta)
        record = next((item for item in records if _record_id(item) == document_id), None)
        target = resolve_paper_path(record or {"document_id": document_id, "stored_name": stored_name}, root)
        if record is not None and (
            record.get("stored_name") != stored_name
            or record.get("source_sha256") != source_hash
            or record.get("document_id") != document_id
        ):
            _set_compensation_status(meta, token, "cleanup_pending", "COMPENSATION_DENIED")
            raise MetadataStoreError("COMPENSATION_DENIED")
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(str(target), flags)
            except FileNotFoundError:
                # The source is already absent.  This is the only state in
                # which compensation can complete without deleting a path.
                if record is not None:
                    save_papers([item for item in records if _record_id(item) != document_id], meta)
                _set_compensation_status(meta, token, "completed")
                return "completed"
            try:
                stat_result = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(stat_result.st_mode)
                    or stat_result.st_nlink != 1
                    or (stat_result.st_dev, stat_result.st_ino) != (source_dev, source_ino)
                ):
                    raise MetadataStoreError("COMPENSATION_DENIED")
                digest = hashlib.sha256()
                while True:
                    block = os.read(descriptor, 1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                if digest.hexdigest() != source_hash:
                    raise MetadataStoreError("COMPENSATION_DENIED")
            finally:
                os.close(descriptor)

            # There is no POSIX compare-and-unlink primitive.  Even while the
            # immutable lock-domain lock is held, a process that does not
            # cooperate with that advisory lock can replace the pathname
            # after the fd/hash check.  Retain the verified source as an
            # identifiable orphan and let a future maintenance operation make
            # an independently reviewed deletion decision.
            _set_compensation_status(meta, token, "cleanup_pending", "COMPENSATION_SOURCE_DELETE_UNPROVEN")
            return "cleanup_pending"
        except MetadataStoreError:
            _set_compensation_status(meta, token, "cleanup_pending", "COMPENSATION_DENIED")
            raise
        except Exception as error:
            with suppress(Exception):
                _set_compensation_status(meta, token, "cleanup_pending", type(error).__name__)
            raise MetadataStoreError("COMPENSATION_RESULT_UNKNOWN") from error


def record_id(item: Any) -> str:
    """Return the canonical record identity with legacy compatibility.

    A canonical record wins when both fields are present; callers must never
    use the legacy field to replace a ``KnowledgeDocument`` identity.
    """
    if isinstance(item, Mapping):
        return str(item.get("document_id") or item.get("paper_id") or "")
    return str(getattr(item, "document_id", None) or getattr(item, "paper_id", None) or "")


_record_id = record_id


def default_chunkers() -> Dict[str, Any]:
    """双版本初始状态：v1 立即开始，v2 排队等待异步任务。"""
    return {
        CHUNKER_V1: {"status": STATUS_INDEXING, "chunk_count": 0, "progress": 0, "error": None},
        CHUNKER_V2: {"status": STATUS_PENDING, "chunk_count": 0, "progress": 0, "error": None},
    }


def default_chunker_state(status: str = STATUS_PENDING) -> Dict[str, Any]:
    return {"status": status, "chunk_count": 0, "progress": 0, "error": None}


@dataclass
class PaperRecord:
    paper_id: str
    file_name: str
    status: str = STATUS_INDEXING
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: str = ""
    error: Optional[str] = None
    # spec-012：双版本状态。顶层 status/chunk_count 保留以兼容既有接口与前端。
    chunkers: Dict[str, Any] = field(default_factory=default_chunkers)
    # spec-015：论文检索导入的可选元数据。None 保持旧上传记录兼容。
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    conference_id: Optional[str] = None
    conference_name: Optional[str] = None
    doi: Optional[str] = None
    dblp_key: Optional[str] = None
    source_url: Optional[str] = None
    import_source: Optional[str] = None
    stored_name: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_dirs(papers_dir: Optional[Path] = None, meta_path: Optional[Path] = None) -> None:
    Path(papers_dir or KB_PAPERS_DIR).mkdir(parents=True, exist_ok=True)
    meta = Path(meta_path or KB_META_PATH)
    meta.parent.mkdir(parents=True, exist_ok=True)


def load_papers(meta_path: Optional[Path] = None) -> List[dict]:
    """读取全部论文元数据。

    spec-012：对**缺少 `chunkers` 字段的旧记录**在内存中补齐双版本状态，
    使所有读取路径（列表接口、单条查询、状态更新）都无需各自处理兼容问题。
    仅改内存，不即刻写盘。
    """
    meta = Path(meta_path or KB_META_PATH)
    if not meta.exists():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    for item in data:
        if isinstance(item, dict):
            ensure_chunkers(item)
    return data


def load_papers_strict(meta_path: Optional[Path] = None) -> List[dict]:
    """Read metadata for a write path; corruption is never an empty database."""
    meta = Path(meta_path or KB_META_PATH)
    if not meta.exists():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        raise MetadataStoreError() from error
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise MetadataStoreError()
    try:
        for item in data:
            ensure_chunkers(item)
    except (TypeError, ValueError, KeyError) as error:
        raise MetadataStoreError() from error
    return data


def save_papers(papers: List[dict], meta_path: Optional[Path] = None) -> None:
    meta = Path(meta_path or KB_META_PATH)
    with _lock:
        # Verify the existing bytes before accepting any replacement.  The
        # compatibility read API may return [], but write paths fail closed.
        if meta.exists():
            load_papers_strict(meta)
        ensure_dirs(meta_path=meta)
        meta.write_text(
            json.dumps(papers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # A committed generation binds the live metadata digest.  Refresh it
        # only for the canonical live path and only when a marker already
        # exists; custom test/legacy paths and marker creation remain inert.
        if meta.resolve().name == "papers.json" and meta.resolve().parent.name == "kb" and meta.resolve().parent.parent.name == "data":
            marker_path = meta.resolve().parent / "index-generation.json"
            if marker_path.exists():
                from backend.app.knowledge_base.infrastructure.manifest_store import FinalizeBundleStore

                FinalizeBundleStore(meta.resolve().parent.parent.parent).refresh_live_digests()


def upsert_paper(record: PaperRecord, meta_path: Optional[Path] = None) -> PaperRecord:
    with _lock:
        papers = load_papers_strict(meta_path)
        payload = record.to_dict()
        for index, item in enumerate(papers):
            if _record_id(item) == record.paper_id:
                if item.get("schema_version") == "knowledge-document-v1":
                    # A legacy PaperRecord is metadata-only once a canonical
                    # document exists.  It can never erase source identity,
                    # hashes, media type, migration markers, or state-machine
                    # fields; explicit state changes use patch_knowledge_document.
                    merged = dict(item)
                    optional_metadata = {
                        "title", "authors", "year", "conference_id", "conference_name",
                        "doi", "dblp_key", "source_url", "import_source",
                    }
                    for key in (
                        "title", "authors", "year", "conference_id", "conference_name",
                        "doi", "dblp_key", "source_url", "import_source",
                    ):
                        if key in payload and not (key in optional_metadata and payload[key] is None):
                            merged[key] = payload[key]
                    papers[index] = merged
                else:
                    papers[index] = payload
                break
        else:
            papers.append(payload)
        save_papers(papers, meta_path)
    return record


def get_paper(paper_id: str, meta_path: Optional[Path] = None) -> Optional[dict]:
    for item in load_papers(meta_path):
        if _record_id(item) == paper_id:
            return item
    return None


def resolve_paper_path(
    paper: Union[str, Mapping[str, Any], PaperRecord],
    papers_dir: Optional[Path] = None,
) -> Path:
    """Resolve a paper's physical path with legacy filename compatibility.

    New imports may store a readable basename in ``stored_name``. Records
    written before spec-015 have no such field and continue using the legacy
    ``{paper_id}.pdf`` layout. Invalid path-like metadata is ignored rather
    than allowing a record to escape the configured papers directory.
    """
    if isinstance(paper, str):
        paper_id = paper
        stored_name = None
    elif isinstance(paper, Mapping):
        paper_id = str(paper.get("document_id") or paper.get("paper_id") or "")
        stored_name = paper.get("stored_name")
    else:
        paper_id = str(getattr(paper, "document_id", None) or getattr(paper, "paper_id", "") or "")
        stored_name = getattr(paper, "stored_name", None)

    candidate = str(stored_name or "").strip()
    if candidate:
        candidate_path = Path(candidate)
        if candidate_path.name == candidate and candidate not in {".", ".."}:
            return Path(papers_dir or KB_PAPERS_DIR) / candidate
    return Path(papers_dir or KB_PAPERS_DIR) / f"{paper_id}.pdf"


def remove_paper(paper_id: str, meta_path: Optional[Path] = None, papers_dir: Optional[Path] = None) -> bool:
    """删除元数据与原件；返回是否命中。"""
    with _lock:
        papers = load_papers_strict(meta_path)
        record = next((item for item in papers if _record_id(item) == paper_id), None)
        remaining = [item for item in papers if _record_id(item) != paper_id]
        if len(remaining) == len(papers):
            return False
        save_papers(remaining, meta_path)
        target = resolve_paper_path(record or paper_id, papers_dir)
        try:
            if target.exists():
                target.unlink()
        except OSError:
            # Do not report a completed delete while the immutable source is
            # still present.  Restore the metadata snapshot so the caller can
            # retry deterministically and surface DELETE_PENDING.
            with suppress(Exception):
                save_papers(papers, meta_path)
            return False
    return True


def remove_canonical_document(
    document_id: str,
    meta_path: Optional[Path] = None,
    papers_dir: Optional[Path] = None,
) -> bool:
    """Delete a canonical document after its application boundary is gated.

    This named adapter keeps application consumers off the legacy
    ``remove_paper`` symbol while preserving its atomic source/metadata
    compensation behavior.
    """
    return remove_paper(document_id, meta_path, papers_dir)


def save_upload(
    file_name: str,
    content: bytes,
    papers_dir: Optional[Path] = None,
    paper_id: Optional[str] = None,
) -> tuple:
    """Legacy source writer with create-exclusive semantics.

    New callers must use the application immutable-create seam.  The optional
    id remains only for old maintenance/tests, and an existing target is a
    stable conflict rather than an invitation to replace immutable bytes.
    Failed writes retain their target for fail-closed compensation/maintenance
    instead of attempting a pathname unlink that could remove a replacement.
    """
    directory = Path(papers_dir or KB_PAPERS_DIR)
    identifier = paper_id or uuid.uuid4().hex
    if not _SERVER_ID_RE.fullmatch(str(identifier)):
        raise MetadataStoreError("SERVER_ID_REQUIRED")
    target = directory / f"{identifier}.pdf"
    directory.mkdir(parents=True, exist_ok=True)
    with _lock, immutable_directory_lock(directory.parent):
        source_token: tuple[int, int] | None = None
        try:
            descriptor = os.open(
                str(target),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = -1
                    stat_result = os.fstat(stream.fileno())
                    source_token = stat_result.st_dev, stat_result.st_ino
                    stream.write(bytes(content))
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor != -1:
                    os.close(descriptor)
            descriptor = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except FileExistsError as error:
            raise MetadataStoreError("SOURCE_ID_CONFLICT") from error
        except Exception:
            _unlink_owned_source(target, source_token, process_locked=True)
            raise
    return identifier, target


def copy_source_exclusive(source: Path, target: Path) -> Path:
    """Copy a trusted source into a server-owned basename without overwrite.

    ``Path.write_bytes`` and ``os.rename`` are intentionally not used here:
    both can replace an existing object on POSIX.  The destination is opened
    with ``xb`` and fsynced before the temporary download is removed.
    """
    source_path = Path(source)
    target_path = Path(target)
    if source_path.resolve() == target_path.resolve():
        raise FileExistsError("source and destination must differ")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source_path.open("rb") as input_stream, target_path.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        try:
            descriptor = os.open(str(target_path.parent), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            # The object itself is durable; directory durability is recorded as
            # a production security debt until the Task06 cutover gate.
            pass
        source_path.unlink()
    except Exception:
        with suppress(OSError):
            target_path.unlink(missing_ok=True)
        raise
    return target_path


def new_record(
    file_name: str,
    uploaded_at: Optional[str] = None,
    *,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    conference_id: Optional[str] = None,
    conference_name: Optional[str] = None,
    doi: Optional[str] = None,
    dblp_key: Optional[str] = None,
    source_url: Optional[str] = None,
    import_source: Optional[str] = None,
    stored_name: Optional[str] = None,
) -> PaperRecord:
    return PaperRecord(
        paper_id=uuid.uuid4().hex,
        file_name=file_name,
        uploaded_at=uploaded_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        title=title,
        authors=authors,
        year=year,
        conference_id=conference_id,
        conference_name=conference_name,
        doi=doi,
        dblp_key=dblp_key,
        source_url=source_url,
        import_source=import_source,
        stored_name=stored_name,
    )


# ---------------------------------------------------------------------------
# 双版本切分状态（spec-012）
# ---------------------------------------------------------------------------


def ensure_chunkers(item: dict) -> Dict[str, Any]:
    """补齐旧记录（无 chunkers 字段）的双版本状态，返回规范化后的 dict。

    **对 spec-011 遗留记录必须沿用其顶层 `status`**：
    若一律按 `indexing` 补 v1，启动时的 `mark_interrupted_tasks` 会把这些
    本已 `indexed` 的论文误判为"中断任务"并标记 failed，导致旧论文全部失效。
    v2 一律 `pending`——旧数据没有 v2，需由用户点「重建索引」补建。
    """
    states = item.get("chunkers") if isinstance(item, dict) else None
    if not isinstance(states, dict):
        states = {}

    if isinstance(item, dict):
        legacy_status = item.get("status") or STATUS_INDEXING
        legacy_count = int(item.get("chunk_count", 0) or 0)
    else:
        legacy_status = STATUS_INDEXING
        legacy_count = 0

    merged = {
        CHUNKER_V1: {
            "status": legacy_status,
            "chunk_count": legacy_count,
            "progress": 100 if legacy_status in (STATUS_INDEXED, STATUS_PARTIAL) else 0,
            "error": (item.get("error") if isinstance(item, dict) else None),
        },
        CHUNKER_V2: default_chunker_state(),
    }

    # 记录里已有的显式状态优先，逐字段覆盖
    for name in CHUNKERS:
        current = states.get(name)
        if isinstance(current, dict):
            base = dict(merged[name])
            base.update({key: current[key] for key in base if key in current})
            merged[name] = base

    if isinstance(item, dict):
        item["chunkers"] = merged
    return merged


def get_chunker_state(paper_id: str, chunker: str, meta_path: Optional[Path] = None) -> Optional[dict]:
    """读取某论文某切分版本的状态；论文不存在返回 None。"""
    for item in load_papers(meta_path):
        if _record_id(item) == paper_id:
            return ensure_chunkers(item).get(chunker)
    return None


def update_chunker_state(
    paper_id: str,
    chunker: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    chunk_count: Optional[int] = None,
    error: Any = _UNSET,
    meta_path: Optional[Path] = None,
) -> Optional[dict]:
    """局部更新某论文某切分版本的状态，返回更新后的状态；论文不存在返回 None。

    同时维护顶层 `status` / `chunk_count` 兼容字段（取 v1 的值），
    使既有接口与前端无需改动即可继续工作。
    """
    with _lock:
        papers = load_papers_strict(meta_path)
        for item in papers:
            if _record_id(item) != paper_id:
                continue
            states = ensure_chunkers(item)
            state = dict(states.get(chunker) or default_chunker_state())
            if status is not None:
                state["status"] = status
            if progress is not None:
                state["progress"] = max(0, min(100, int(progress)))
            if chunk_count is not None:
                state["chunk_count"] = max(0, int(chunk_count))
            if error is not _UNSET:
                state["error"] = error
            states[chunker] = state
            item["chunkers"] = states
            # 顶层兼容字段跟随 v1
            primary = states.get(CHUNKER_V1) or {}
            item["status"] = primary.get("status", item.get("status"))
            item["chunk_count"] = primary.get("chunk_count", item.get("chunk_count", 0))
            save_papers(papers, meta_path)
            return state
    return None


def mark_interrupted_tasks(meta_path: Optional[Path] = None, reason: str = "服务重启导致中断") -> int:
    """启动时把仍为 `indexing` 的版本标记失败，返回被标记的数量。

    异步任务无法跨进程存活，残留的 `indexing` 会永远卡住进度条，
    因此启动时统一置为 `failed`，由用户点「重建索引」重新触发。
    """
    marked = 0
    with _lock:
        papers = load_papers_strict(meta_path)
        changed = False
        for item in papers:
            states = ensure_chunkers(item)
            for name in CHUNKERS:
                state = states.get(name)
                if isinstance(state, dict) and state.get("status") == STATUS_INDEXING:
                    state["status"] = STATUS_FAILED
                    state["progress"] = 0
                    state["error"] = reason
                    marked += 1
                    changed = True
            item["chunkers"] = states
            if isinstance(states.get(CHUNKER_V1), dict):
                item["status"] = states[CHUNKER_V1].get("status", item.get("status"))
        if changed:
            save_papers(papers, meta_path)
    return marked
