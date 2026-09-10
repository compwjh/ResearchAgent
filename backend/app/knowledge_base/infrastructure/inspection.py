"""Pure Task04 inspection DTOs and manifest construction.

The builder consumes a Task02A ``SourceProvenanceBundle`` plus payloads that
were read from the current index.  It never embeds, chunks, or writes Qdrant;
the caller owns the read-only payload port and the manifest store owns disk
publication.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CHUNKERS = {"v1", "v2"}
_SCHEMA_VERSION = "inspection-manifest-v1"
_MAPPING_VERSION = "source-anchor-v1"


class InspectionError(RuntimeError):
    """Stable, path-free inspection failure."""

    def __init__(self, code: str, *, status: int = 409) -> None:
        self.code = code
        self.status = int(status)
        super().__init__(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise InspectionError("MANIFEST_PAYLOAD_INVALID", status=409) from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[4] / "docs/sdd/plans/018/artifacts/task-03/inspection-manifest.schema.json"


def _validate_id(value: Any) -> str:
    result = str(value or "")
    if not _ID_RE.fullmatch(result):
        raise InspectionError("INVALID_DOCUMENT_ID", status=400)
    return result


def _payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    candidate = getattr(value, "payload", None)
    if isinstance(candidate, Mapping):
        result = dict(candidate)
        if getattr(value, "id", None) is not None:
            result.setdefault("_point_id", str(value.id))
        return result
    raise InspectionError("INDEX_PAYLOAD_INVALID")


def _map_status(value: Any) -> str:
    status = str(value or "failed")
    return {
        "pending": "pending",
        "indexing": "building",
        "building": "building",
        "indexed": "ready",
        "ready": "ready",
        "indexed_partial": "partial",
        "partial": "partial",
        "failed": "failed",
    }.get(status, "failed")


@dataclass(frozen=True)
class SourceBlock:
    value: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)


@dataclass(frozen=True)
class ChunkSnapshot:
    value: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)


@dataclass(frozen=True)
class SourceAnchor:
    value: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)


@dataclass(frozen=True)
class InspectionManifest:
    value: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)

    @property
    def document_id(self) -> str:
        return str(self.value["document_id"])

    @property
    def chunker(self) -> str:
        return str(self.value["chunker"])


def _manifest_block(block: Mapping[str, Any], media_type: str) -> dict[str, Any]:
    if media_type == "application/pdf":
        result = {
            key: block[key]
            for key in (
                "block_id",
                "ordinal",
                "display_ordinal",
                "page",
                "text",
                "raw_text",
                "start",
                "end",
                "bbox",
                "normalized_bbox",
                "lines",
                "block_type",
                "heading_path",
            )
            if key in block
        }
        raw_lines = block.get("lines")
        if isinstance(raw_lines, Sequence) and not isinstance(raw_lines, (str, bytes, bytearray)):
            result["lines"] = [
                {
                    key: line[key]
                    for key in ("ordinal", "text", "start", "end")
                    if key in line
                }
                if isinstance(line, Mapping)
                else line
                for line in raw_lines
            ]
        normalized = result.get("normalized_bbox")
        page = result.get("page")
        if not isinstance(normalized, list) or not isinstance(page, int):
            raise InspectionError("MANIFEST_SOURCE_BLOCK_INVALID")
        result["locator"] = {"kind": "pdf_bbox", "page": page, "bbox": list(normalized)}
    else:
        result = {
            key: block[key]
            for key in (
                "block_id",
                "ordinal",
                "text",
                "locator",
                "heading_path",
                "block_type",
                "start",
                "end",
                "page",
                "page_end",
                "inline_resources",
                "diagnostics",
            )
            if key in block
        }
        locator = result.get("locator") or {}
        if "start_line" not in locator or "end_line" not in locator:
            raise InspectionError("MANIFEST_SOURCE_BLOCK_INVALID")
        result["locator"] = {
            "kind": "markdown_lines",
            "start_line": int(locator["start_line"]),
            "end_line": int(locator["end_line"]),
        }
        result.setdefault("page", None)
        result.setdefault("page_end", None)
        result.setdefault("inline_resources", [])
        result.setdefault("diagnostics", [])
    return result


def _chunk_from_payload(payload: Mapping[str, Any], fallback: Mapping[str, Any], chunker: str) -> dict[str, Any]:
    text = payload.get("text", fallback.get("text"))
    if not isinstance(text, str):
        raise InspectionError("MANIFEST_PAYLOAD_INVALID")
    value = {
        "chunker": chunker,
        "chunk_index": payload.get("chunk_index", fallback.get("chunk_index")),
        "text": text,
        "page": payload.get("page", fallback.get("page")),
        "page_end": payload.get("page_end", fallback.get("page_end")),
        "section": str(payload.get("section", fallback.get("section", "")) or ""),
        "is_citation": bool(payload.get("is_citation", fallback.get("is_citation", False))),
    }
    for name in ("start_line", "end_line"):
        if payload.get(name, fallback.get(name)) is not None:
            value[name] = payload.get(name, fallback.get(name))
    if not isinstance(value["chunk_index"], int) or isinstance(value["chunk_index"], bool) or value["chunk_index"] < 0:
        raise InspectionError("MANIFEST_PAYLOAD_INVALID")
    value["chunk_fingerprint"] = _sha256(value)
    return value


def _unmapped_reasons(raw: Sequence[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in raw:
        reason = str(item.get("reason") if isinstance(item, Mapping) else item or "UNMAPPED")
        reason = re.sub(r"[^A-Z0-9_]", "_", reason.upper())[:128] or "UNMAPPED"
        result[reason] = result.get(reason, 0) + 1
    return result


def _anchor(
    value: Mapping[str, Any],
    *,
    chunker: str,
    blocks: Mapping[str, Mapping[str, Any]],
    chunks: Mapping[int, Mapping[str, Any]],
    media_type: str,
) -> dict[str, Any]:
    block_id = str(value.get("block_id") or "")
    index = value.get("chunk_index")
    block = blocks.get(block_id)
    chunk = chunks.get(index) if isinstance(index, int) else None
    if block is None or chunk is None:
        raise InspectionError("MANIFEST_ANCHOR_INVALID")
    block_range = [int(block.get("start", 0)), int(block.get("end", 0))]
    if media_type == "text/markdown" and chunk.get("start_line") is not None:
        chunk_range = [int(chunk["start_line"]), int(chunk["end_line"])]
    else:
        chunk_range = None
    return {
        "block_id": block_id,
        "chunker": chunker,
        "chunk_index": int(index),
        "coverage": float(value.get("coverage", 0.0)),
        "is_primary": bool(value.get("is_primary", False)),
        "block_range": block_range,
        "chunk_range": chunk_range,
        "unmapped_reason": None,
    }


def build_inspection_manifest(
    document: Mapping[str, Any],
    bundle: Any,
    payloads: Sequence[Any],
) -> InspectionManifest:
    """Build a manifest from one real provenance bundle and read-only payloads."""
    document_id = _validate_id(document.get("document_id"))
    bundle_dict = bundle.to_dict() if hasattr(bundle, "to_dict") else dict(bundle)
    if bundle_dict.get("document_id") != document_id:
        raise InspectionError("MANIFEST_DOCUMENT_ID_MISMATCH")
    source_chunker = str(bundle_dict.get("chunker") or "")
    chunker = "v1" if source_chunker == "markdown-block-v1" else source_chunker
    if chunker not in _CHUNKERS:
        raise InspectionError("CHUNKER_UNSUPPORTED", status=400)
    source_hash = bundle_dict.get("source_sha256")
    if not isinstance(source_hash, str) or document.get("source_sha256") != source_hash:
        raise InspectionError("SOURCE_HASH_MISMATCH")
    raw_payloads = [_payload(item) for item in payloads]
    if not raw_payloads:
        raise InspectionError("INDEX_REBUILD_REQUIRED")
    normalized_payloads: list[dict[str, Any]] = []
    for item in raw_payloads:
        if item.get("document_id") != document_id or item.get("chunker") != chunker:
            raise InspectionError("INDEX_REBUILD_REQUIRED")
        if item.get("source_sha256") != source_hash:
            raise InspectionError("INDEX_REBUILD_REQUIRED")
        if (
            not isinstance(item.get("text"), str)
            or not isinstance(item.get("chunk_index"), int)
            or isinstance(item.get("chunk_index"), bool)
        ):
            raise InspectionError("INDEX_PAYLOAD_INVALID")
        normalized_payloads.append(dict(item))
    normalized_payloads.sort(key=lambda item: int(item["chunk_index"]))
    indexes = [int(item["chunk_index"]) for item in normalized_payloads]
    if indexes != list(range(len(indexes))) or len(indexes) != len(set(indexes)):
        raise InspectionError("INDEX_PAYLOAD_INVALID")
    bundle_chunks = {
        int(item["chunk_index"]): item
        for item in bundle_dict.get("chunks", ())
        if isinstance(item, Mapping) and isinstance(item.get("chunk_index"), int)
    }
    chunks = []
    for payload in normalized_payloads:
        fallback = bundle_chunks.get(int(payload["chunk_index"]))
        if fallback is None or payload.get("text") != fallback.get("text"):
            raise InspectionError("MANIFEST_PAYLOAD_MISMATCH")
        chunks.append(_chunk_from_payload(payload, fallback, chunker))
    blocks = [_manifest_block(item, str(bundle_dict.get("media_type"))) for item in bundle_dict.get("blocks", ())]
    block_map = {str(item.get("block_id")): item for item in blocks}
    chunk_map = {int(item["chunk_index"]): item for item in chunks}
    anchors = [
        _anchor(item, chunker=chunker, blocks=block_map, chunks=chunk_map, media_type=str(bundle_dict.get("media_type")))
        for item in bundle_dict.get("anchors", ())
        if isinstance(item, Mapping)
    ]
    index_projection = [
        {key: value for key, value in payload.items() if key != "_point_id"}
        for payload in normalized_payloads
    ]
    status = _map_status(bundle_dict.get("status"))
    if bundle_dict.get("unmapped_count"):
        status = "partial"
    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "mapping_algorithm_version": _MAPPING_VERSION,
        "source_parser_version": str(bundle_dict.get("source_parser_version") or ""),
        "chunker_config_fingerprint": str(bundle_dict.get("chunker_config_fingerprint") or ""),
        "payload_schema_version": str(bundle_dict.get("payload_schema_version") or ""),
        "document_id": document_id,
        "media_type": str(bundle_dict.get("media_type") or ""),
        "chunker": chunker,
        "status": status,
        "progress": int(bundle_dict.get("progress", 100)),
        "source_sha256": source_hash,
        "indexed_source_sha256": source_hash,
        "source_hash_state": "verified",
        "index_fingerprint": _sha256(index_projection),
        "blocks": blocks,
        "chunks": chunks,
        "anchors": anchors,
        "mapped_count": int(bundle_dict.get("mapped_count", 0)),
        "unmapped_count": int(bundle_dict.get("unmapped_count", 0)),
        "unmapped_reasons": _unmapped_reasons(bundle_dict.get("unmapped_reasons", ())),
        "error": bundle_dict.get("error"),
    }
    try:
        errors = list(Draft202012Validator(json.loads(_schema_path().read_text(encoding="utf-8")), format_checker=FormatChecker()).iter_errors(manifest))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise InspectionError("MANIFEST_SCHEMA_UNAVAILABLE", status=503) from error
    if errors:
        raise InspectionError("MANIFEST_SCHEMA_INVALID")
    return InspectionManifest(manifest)


__all__ = [
    "ChunkSnapshot",
    "InspectionError",
    "InspectionManifest",
    "SourceAnchor",
    "SourceBlock",
    "build_inspection_manifest",
]
