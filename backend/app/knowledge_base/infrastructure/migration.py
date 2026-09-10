"""Fail-closed migration of legacy ``papers.json`` metadata.

The migration deliberately knows nothing about Qdrant or embeddings.  It only
creates the durable ``KnowledgeDocument`` metadata record and computes the
current source hash when the immutable source is present.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from backend.app.knowledge_base.infrastructure.store import (
    CHUNKERS,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
    STATUS_PENDING,
    default_chunker_state,
)

MIGRATION_VERSION = "018-document-v1"
SCHEMA_VERSION = "knowledge-document-v1"
MIGRATION_INPUT_INVALID = "MIGRATION_INPUT_INVALID"
METADATA_INVALID = "METADATA_INVALID"
METADATA_NOT_MIGRATED = "METADATA_NOT_MIGRATED"
DOCUMENT_ID_CONFLICT = "DOCUMENT_ID_CONFLICT"
MIGRATION_BACKUP_CONFLICT = "MIGRATION_BACKUP_CONFLICT"
MIGRATION_WRITE_FAILED = "MIGRATION_WRITE_FAILED"
SOURCE_MISSING = "SOURCE_MISSING"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_MEDIA_SUFFIXES = {".md": "text/markdown", ".markdown": "text/markdown"}
_STATUSES = {STATUS_PENDING, STATUS_INDEXING, STATUS_INDEXED, STATUS_PARTIAL, STATUS_FAILED}
_LEGACY_FIELDS = {
    "paper_id", "file_name", "status", "page_count", "chunk_count", "uploaded_at",
    "error", "chunkers", "title", "authors", "year", "conference_id",
    "conference_name", "doi", "dblp_key", "source_url", "import_source", "stored_name",
}


class KnowledgeDocumentMigrationError(RuntimeError):
    """Stable, path-free migration error."""

    def __init__(self, code: str, message: str = "metadata migration failed") -> None:
        self.code = code
        super().__init__(message)


def _schema_path(schema_path: Path | None = None) -> Path:
    if schema_path is not None:
        return Path(schema_path)
    return Path(__file__).resolve().parents[4] / "docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json"


def _read_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID) from error
    return digest.hexdigest()


def _is_safe_basename(value: Any) -> bool:
    text = str(value or "")
    return bool(_SAFE_NAME_RE.fullmatch(text)) and Path(text).name == text


def _normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # The historical store used datetime.now().isoformat() without a
        # zone.  Freeze that legacy wall-clock value as UTC; never consult the
        # host's current timezone, so repeated migrations are deterministic.
        parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    return value


def _safe_id(value: Any) -> str:
    result = str(value or "")
    if not _ID_RE.fullmatch(result):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    return result


def _media_and_name(record: Mapping[str, Any], document_id: str) -> tuple[str, str, str]:
    supplied = record.get("stored_name")
    if supplied is not None and not _is_safe_basename(supplied):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    file_name = record.get("file_name")
    if not isinstance(file_name, str) or not file_name or "/" in file_name or "\\" in file_name:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    suffix = Path(str(supplied or file_name)).suffix.lower()
    media_type = _MEDIA_SUFFIXES.get(suffix, "application/pdf")
    stored_name = str(supplied) if supplied else f"{document_id}{'.md' if media_type == 'text/markdown' else '.pdf'}"
    if not _is_safe_basename(stored_name):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    return file_name, stored_name, media_type


def _chunkers(record: Mapping[str, Any], status: str, chunk_count: int) -> dict[str, dict[str, Any]]:
    states = record.get("chunkers")
    result: dict[str, dict[str, Any]] = {}
    for name in CHUNKERS:
        value = states.get(name) if isinstance(states, Mapping) else None
        base = default_chunker_state(status if name == "v1" else STATUS_PENDING)
        if isinstance(value, Mapping):
            for key in base:
                if key in value:
                    base[key] = value[key]
        if name == "v1" and not isinstance(value, Mapping):
            base["chunk_count"] = chunk_count
            base["progress"] = 100 if status in {STATUS_INDEXED, STATUS_PARTIAL} else 0
            base["error"] = record.get("error")
        result[name] = base
    return result


def _canonical_record(record: Mapping[str, Any], papers_dir: Path) -> dict[str, Any]:
    if set(record) - _LEGACY_FIELDS:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    document_id = _safe_id(record.get("paper_id"))
    file_name, stored_name, media_type = _media_and_name(record, document_id)
    uploaded_at = _normalize_timestamp(record.get("uploaded_at"))
    if uploaded_at is None:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    status = str(record.get("status") or STATUS_PENDING)
    if status not in _STATUSES:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    try:
        page_count = int(record.get("page_count", 0) or 0)
        chunk_count = int(record.get("chunk_count", 0) or 0)
    except (TypeError, ValueError):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID) from None
    if page_count < 0 or chunk_count < 0:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    if media_type == "text/markdown":
        page_count_value: int | None = None
    else:
        page_count_value = page_count
    source = papers_dir / stored_name
    source_hash: str | None = _sha256(source) if source.is_file() else None
    if source_hash is None:
        status = STATUS_FAILED
        error = SOURCE_MISSING
    else:
        error = record.get("error")
    authors = record.get("authors")
    if authors is not None and (not isinstance(authors, list) or not all(isinstance(item, str) for item in authors)):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "migration_version": MIGRATION_VERSION,
        "document_id": document_id,
        "file_name": file_name,
        "media_type": media_type,
        "source_sha256": source_hash,
        "indexed_source_sha256": None,
        "source_hash_state": "legacy_unknown",
        "stored_name": stored_name,
        "source_immutable": True,
        "status": status,
        "created_at": uploaded_at,
        "page_count": page_count_value,
        "chunk_count": chunk_count,
        "chunkers": _chunkers(record, status, chunk_count),
        "error": error,
        "title": record.get("title"),
        "authors": authors,
        "year": record.get("year"),
        "conference_id": record.get("conference_id"),
        "conference_name": record.get("conference_name"),
        "doi": record.get("doi"),
        "dblp_key": record.get("dblp_key"),
        "source_url": record.get("source_url"),
        "import_source": record.get("import_source"),
    }
    return result


def _validate(records: list[dict[str, Any]], schema_path: Path) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeDocumentMigrationError(MIGRATION_WRITE_FAILED) from error
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for record in records:
        if list(validator.iter_errors(record)):
            raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)


def _read_metadata_for_write(meta_path: Path) -> tuple[bytes, list[dict[str, Any]], bool]:
    """Read metadata strictly before any write-path operation."""
    if not meta_path.exists():
        return b"", [], False
    try:
        raw = meta_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeDocumentMigrationError(METADATA_INVALID) from error
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise KnowledgeDocumentMigrationError(METADATA_INVALID)
    records = [dict(item) for item in value]
    for item in records:
        if item.get("schema_version") != SCHEMA_VERSION:
            raise KnowledgeDocumentMigrationError(METADATA_NOT_MIGRATED)
    _validate(records, _schema_path())
    return raw, records, True


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def build_import_knowledge_document(record: Any, source_path: Path) -> dict[str, Any]:
    """Build a complete canonical document for a newly imported PDF."""
    document_id = _safe_id(_value(record, "paper_id") or _value(record, "document_id"))
    stored_name = str(_value(record, "stored_name") or _value(record, "file_name") or "")
    if not _is_safe_basename(stored_name) or not stored_name.lower().endswith(".pdf"):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    source = Path(source_path)
    if not source.is_file():
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    created_at = _normalize_timestamp(_value(record, "uploaded_at") or _value(record, "created_at"))
    if created_at is None:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    document = {
        "schema_version": SCHEMA_VERSION,
        "migration_version": MIGRATION_VERSION,
        "document_id": document_id,
        "file_name": str(_value(record, "file_name") or stored_name),
        "media_type": "application/pdf",
        "source_sha256": _sha256(source),
        "indexed_source_sha256": None,
        "source_hash_state": "legacy_unknown",
        "stored_name": stored_name,
        "source_immutable": True,
        "status": STATUS_INDEXING,
        "created_at": created_at,
        "page_count": 0,
        "chunk_count": 0,
        "chunkers": {
            "v1": {"status": STATUS_INDEXING, "chunk_count": 0, "progress": 0, "error": None},
            "v2": {"status": STATUS_PENDING, "chunk_count": 0, "progress": 0, "error": None},
        },
        "error": None,
        "title": _value(record, "title"),
        "authors": _value(record, "authors"),
        "year": _value(record, "year"),
        "conference_id": _value(record, "conference_id"),
        "conference_name": _value(record, "conference_name"),
        "doi": _value(record, "doi"),
        "dblp_key": _value(record, "dblp_key"),
        "source_url": _value(record, "source_url"),
        "import_source": _value(record, "import_source"),
    }
    _validate([document], _schema_path())
    return document


def build_uploaded_knowledge_document(
    *,
    document_id: str,
    file_name: str,
    stored_name: str,
    media_type: str,
    source_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the canonical, not-yet-indexed record for an HTTP upload.

    Uploads are deliberately separate from legacy ``PaperRecord`` creation:
    the source is already server-owned and immutable when this function is
    called, while all derived index state starts as ``pending``.  ``legacy_unknown``
    is the frozen metadata enum for a source that has not been indexed yet;
    no historical indexed hash is invented here.
    """
    document_id = _safe_id(document_id)
    if (
        not isinstance(file_name, str)
        or not file_name.strip()
        or "/" in file_name
        or "\\" in file_name
        or len(file_name.encode("utf-8")) > 255
    ):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    if not _is_safe_basename(stored_name):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    if media_type not in {"application/pdf", "text/markdown"}:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    source = Path(source_path)
    if not source.is_file():
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    normalized_created_at = _normalize_timestamp(created_at or datetime.now(timezone.utc).isoformat())
    if normalized_created_at is None:
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    source_hash = _sha256(source)
    document = {
        "schema_version": SCHEMA_VERSION,
        "migration_version": MIGRATION_VERSION,
        "document_id": document_id,
        "file_name": file_name,
        "media_type": media_type,
        "source_sha256": source_hash,
        "indexed_source_sha256": None,
        "source_hash_state": "legacy_unknown",
        "stored_name": stored_name,
        "source_immutable": True,
        "status": STATUS_PENDING,
        "created_at": normalized_created_at,
        "page_count": None if media_type == "text/markdown" else 0,
        "chunk_count": 0,
        "chunkers": {
            CHUNKERS[0]: default_chunker_state(STATUS_PENDING),
            CHUNKERS[1]: default_chunker_state(STATUS_PENDING),
        },
        "error": None,
    }
    _validate([document], _schema_path())
    return document


def write_import_knowledge_document(document: Mapping[str, Any], meta_path: Path) -> dict[str, Any]:
    """Append one canonical document, refusing corrupt/legacy metadata."""
    meta = Path(meta_path)
    raw, records, existed = _read_metadata_for_write(meta)
    document_id = str(document.get("document_id") or "")
    if any(item.get("document_id") == document_id for item in records):
        raise KnowledgeDocumentMigrationError(DOCUMENT_ID_CONFLICT)
    candidate = dict(document)
    _validate([candidate], _schema_path())
    records.append(candidate)
    encoded = json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _atomic_bytes(
        meta,
        encoded,
        rollback_payload=raw if existed else None,
        rollback_exists=existed,
    )
    return candidate


def patch_knowledge_document(meta_path: Path, document_id: str, **updates: Any) -> dict[str, Any]:
    """Apply an explicit status/state patch without legacy default fields."""
    allowed = {"status", "page_count", "chunk_count", "chunkers", "error"}
    if set(updates) - allowed:
        raise KnowledgeDocumentMigrationError(METADATA_INVALID)
    meta = Path(meta_path)
    raw, records, existed = _read_metadata_for_write(meta)
    target = next((item for item in records if item.get("document_id") == document_id), None)
    if target is None:
        raise KnowledgeDocumentMigrationError(METADATA_INVALID)
    target.update(updates)
    _validate(records, _schema_path())
    encoded = json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _atomic_bytes(meta, encoded, rollback_payload=raw, rollback_exists=existed)
    return target


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(str(directory), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _restore_bytes(path: Path, payload: bytes) -> None:
    """Best-effort recovery after replace-before-directory-fsync failure."""
    try:
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.restore.", suffix=".tmp", dir=path.parent)
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        with suppress(OSError):
            _fsync_directory(path.parent)
    except OSError:
        with suppress(OSError):
            path.write_bytes(payload)


def _atomic_bytes(
    path: Path,
    payload: bytes,
    *,
    rollback_payload: bytes | None = None,
    rollback_exists: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        replaced = True
        _fsync_directory(path.parent)
    except OSError as error:
        with suppress(OSError):
            temp_path.unlink(missing_ok=True)
        if replaced:
            if rollback_exists and rollback_payload is not None:
                _restore_bytes(path, rollback_payload)
            elif not rollback_exists:
                with suppress(OSError):
                    path.unlink(missing_ok=True)
        raise KnowledgeDocumentMigrationError(MIGRATION_WRITE_FAILED) from error


def _backup_path(meta_path: Path) -> Path:
    return meta_path.with_name(f"{meta_path.name}.pre-{MIGRATION_VERSION}.bak")


def _already_canonical(value: Any, schema_path: Path) -> bool:
    if not isinstance(value, list) or not value:
        return isinstance(value, list) and not value
    if not all(isinstance(item, Mapping) and item.get("schema_version") == SCHEMA_VERSION for item in value):
        return False
    _validate([dict(item) for item in value], schema_path)
    return True


def migrate_papers_json(
    meta_path: Path,
    papers_dir: Path,
    *,
    allow_missing: bool = False,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Migrate legacy metadata atomically and return a redacted audit summary.

    ``allow_missing`` is an explicit first-initialisation decision.  Without it
    a missing metadata file is an error, never an implicit empty database.
    """
    meta = Path(meta_path)
    papers = Path(papers_dir)
    schema = _schema_path(schema_path)
    if not meta.exists():
        if not allow_missing:
            raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
        raw = b"[]"
        value: Any = []
    else:
        raw, value = _read_json(meta)
    if meta.exists() and _already_canonical(value, schema):
        return {
            "migration_version": MIGRATION_VERSION,
            "already_migrated": True,
            "record_count": len(value),
            "document_ids": [item["document_id"] for item in value],
            "source_missing_count": sum(item.get("error") == SOURCE_MISSING for item in value),
            "backup_path": str(_backup_path(meta)),
        }
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
    ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for item in value:
        document_id = _safe_id(item.get("paper_id"))
        if document_id in ids:
            raise KnowledgeDocumentMigrationError(MIGRATION_INPUT_INVALID)
        ids.add(document_id)
        records.append(_canonical_record(item, papers))
    _validate(records, schema)
    encoded = json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    backup = _backup_path(meta)
    if meta.exists():
        if backup.exists():
            try:
                if backup.read_bytes() != raw:
                    raise KnowledgeDocumentMigrationError(MIGRATION_BACKUP_CONFLICT)
            except OSError as error:
                raise KnowledgeDocumentMigrationError(MIGRATION_BACKUP_CONFLICT) from error
        else:
            _atomic_bytes(backup, raw)
            with suppress(OSError):
                os.chmod(backup, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    _atomic_bytes(meta, encoded, rollback_payload=raw if meta.exists() else None, rollback_exists=meta.exists())
    return {
        "migration_version": MIGRATION_VERSION,
        "already_migrated": False,
        "record_count": len(records),
        "document_ids": [item["document_id"] for item in records],
        "source_missing_count": sum(item.get("error") == SOURCE_MISSING for item in records),
        "backup_path": str(backup),
        "source_hashes": {item["document_id"]: item["source_sha256"] for item in records},
    }


__all__ = [
    "MIGRATION_BACKUP_CONFLICT",
    "MIGRATION_INPUT_INVALID",
    "METADATA_INVALID",
    "METADATA_NOT_MIGRATED",
    "DOCUMENT_ID_CONFLICT",
    "MIGRATION_VERSION",
    "MIGRATION_WRITE_FAILED",
    "KnowledgeDocumentMigrationError",
    "SOURCE_MISSING",
    "migrate_papers_json",
    "build_import_knowledge_document",
    "build_uploaded_knowledge_document",
    "write_import_knowledge_document",
    "patch_knowledge_document",
]
