"""受控 KnowledgeDocument 原件读取边界。

This module is deliberately read-only: it resolves a validated canonical
document to a server-owned basename, verifies the current source hash, and
implements the GET/HEAD/single-Range semantics used by the HTTP layer.  It
does not create metadata, call an indexer, or access Qdrant.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend.app.knowledge_base.infrastructure.store import load_papers_strict, record_id

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
MAX_RANGE_BYTES = 8 * 1024 * 1024


def validate_source_bytes(content: bytes, media_type: str) -> None:
    """Validate upload/source bytes without invoking a parser or indexer."""
    if not isinstance(content, (bytes, bytearray, memoryview)) or not content:
        raise DocumentReadError("SOURCE_EMPTY", status=400)
    if media_type == "application/pdf":
        # Require the complete PDF magic prefix.  A bare ``%PDF`` or forged
        # ``%PDFx`` prefix is not a PDF header; the parser/indexer remains the
        # authority for full document readability after this cheap gate.
        if not bytes(content).startswith(b"%PDF-"):
            raise DocumentReadError("INVALID_PDF", status=400)
        return
    if media_type == "text/markdown":
        if b"\x00" in bytes(content):
            raise DocumentReadError("INVALID_ENCODING", status=400)
        try:
            bytes(content).decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentReadError("INVALID_UTF8", status=400) from error
        return
    raise DocumentReadError("SOURCE_MEDIA_TYPE_UNSUPPORTED", status=415)


class DocumentReadError(RuntimeError):
    """Stable, path-free source read failure."""

    def __init__(self, code: str, *, status: int = 404, size: int | None = None) -> None:
        self.code = code
        self.status = int(status)
        self.size = size
        super().__init__(code)


@dataclass(frozen=True)
class SourceHead:
    document_id: str
    media_type: str
    file_name: str
    size: int
    sha256: str
    etag: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "ETag": self.etag,
            "Content-Type": self.media_type,
            "Content-Length": str(self.size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{self.file_name}"',
        }


@dataclass(frozen=True)
class SourceRead:
    head: SourceHead
    status: int
    body: bytes
    start: int = 0
    end: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        headers = dict(self.head.headers)
        if self.status == 304:
            headers["Content-Length"] = "0"
        elif self.end is not None:
            headers["Content-Length"] = str(self.end - self.start + 1)
        else:
            headers["Content-Length"] = str(self.head.size)
        if self.status == 206 and self.end is not None:
            headers["Content-Range"] = f"bytes {self.start}-{self.end}/{self.head.size}"
        return headers


def _safe_id(value: Any) -> str:
    result = str(value or "")
    if not _ID_RE.fullmatch(result):
        raise DocumentReadError("INVALID_DOCUMENT_ID", status=400)
    return result


def _safe_name(value: Any) -> str:
    result = str(value or "")
    if not _NAME_RE.fullmatch(result) or Path(result).name != result:
        raise DocumentReadError("SOURCE_PATH_INVALID", status=404)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise DocumentReadError("SOURCE_NOT_FOUND", status=404) from error
    return digest.hexdigest()


def _parse_range(value: str, size: int) -> tuple[int, int]:
    if not isinstance(value, str) or not value.startswith("bytes="):
        raise DocumentReadError("INVALID_RANGE", status=416, size=size)
    expression = value[6:].strip()
    if not expression or "," in expression or expression.count("-") != 1:
        raise DocumentReadError("INVALID_RANGE", status=416, size=size)
    start_text, end_text = (part.strip() for part in expression.split("-"))
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = size - 1 if not end_text else int(end_text)
    except (TypeError, ValueError):
        raise DocumentReadError("INVALID_RANGE", status=416, size=size) from None
    if start < 0 or end < start or start >= size or end >= size:
        raise DocumentReadError("INVALID_RANGE", status=416, size=size)
    if end - start + 1 > MAX_RANGE_BYTES:
        raise DocumentReadError("INVALID_RANGE", status=416, size=size)
    return start, end


class DocumentSourceReader:
    """Resolve and read only canonical server-owned source objects."""

    def __init__(self, *, meta_path: Path, papers_dir: Path) -> None:
        self.meta_path = Path(meta_path)
        self.papers_dir = Path(papers_dir).resolve()

    def _record(self, document_id: str) -> Mapping[str, Any]:
        identifier = _safe_id(document_id)
        try:
            records = load_papers_strict(self.meta_path)
        except Exception as error:
            if getattr(error, "code", None) == "METADATA_INVALID":
                raise DocumentReadError("METADATA_INVALID", status=503) from error
            raise
        record = next((item for item in records if record_id(item) == identifier), None)
        if not isinstance(record, Mapping):
            raise DocumentReadError("DOCUMENT_NOT_FOUND", status=404)
        if record.get("schema_version") != "knowledge-document-v1":
            raise DocumentReadError("INDEX_REBUILD_REQUIRED", status=409)
        return record

    def _path(self, record: Mapping[str, Any]) -> Path:
        stored_name = _safe_name(record.get("stored_name"))
        candidate = (self.papers_dir / stored_name).resolve()
        if candidate.parent != self.papers_dir:
            raise DocumentReadError("SOURCE_PATH_INVALID", status=404)
        if not candidate.is_file():
            raise DocumentReadError("SOURCE_NOT_FOUND", status=404)
        return candidate

    def head(self, document_id: str) -> SourceHead:
        record = self._record(document_id)
        path = self._path(record)
        digest = _sha256(path)
        expected = record.get("source_sha256")
        if not isinstance(expected, str) or digest != expected:
            raise DocumentReadError("SOURCE_HASH_MISMATCH", status=409)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise DocumentReadError("SOURCE_NOT_FOUND", status=404) from error
        media_type = str(record.get("media_type") or "")
        if media_type not in {"application/pdf", "text/markdown"}:
            raise DocumentReadError("SOURCE_MEDIA_TYPE_UNSUPPORTED", status=415)
        file_name = str(record.get("file_name") or record.get("stored_name") or "source")
        if "/" in file_name or "\\" in file_name:
            raise DocumentReadError("SOURCE_PATH_INVALID", status=404)
        return SourceHead(
            document_id=str(record["document_id"]),
            media_type=media_type,
            file_name=file_name,
            size=size,
            sha256=digest,
            etag=f'"sha256:{digest}"',
        )

    def read(
        self,
        document_id: str,
        *,
        range_header: str | None = None,
        if_none_match: str | None = None,
        head_only: bool = False,
    ) -> SourceRead:
        head = self.head(document_id)
        if if_none_match and if_none_match.strip() == head.etag:
            return SourceRead(head=head, status=304, body=b"")
        path = self._path(self._record(document_id))
        if range_header is None:
            start, end, status = 0, head.size - 1, 200
        else:
            start, end = _parse_range(range_header, head.size)
            status = 206
        if head_only:
            return SourceRead(head=head, status=status, body=b"", start=start, end=end)
        try:
            with path.open("rb") as stream:
                stream.seek(start)
                body = stream.read(end - start + 1)
        except OSError as error:
            raise DocumentReadError("SOURCE_NOT_FOUND", status=404) from error
        if len(body) != end - start + 1:
            raise DocumentReadError("SOURCE_CHANGED_DURING_READ", status=409)
        return SourceRead(head=head, status=status, body=body, start=start, end=end)


__all__ = [
    "DocumentReadError",
    "DocumentSourceReader",
    "MAX_RANGE_BYTES",
    "SourceHead",
    "SourceRead",
    "validate_source_bytes",
]
