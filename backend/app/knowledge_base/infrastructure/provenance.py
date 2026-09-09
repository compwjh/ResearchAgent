"""Task02A-C source provenance bundle assembly.

This module is an adapter around the production PDF/Markdown parser DTOs and
the existing v1/v2 chunkers.  It deliberately does not create a manifest,
embed text, or access Qdrant.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from backend.app.knowledge_base.infrastructure.chunkers import (
    Chunk,
    build_chunks_v1,
    build_chunks_v2,
)
from backend.app.knowledge_base.infrastructure.normalize import (
    locate_reference_start,
    normalize_text,
)

__all__ = [
    "SourceProvenanceBundleError",
    "SourceProvenanceBundle",
    "SourceProvenanceBundleV1",
    "build_source_provenance_bundle",
    "validate_source_provenance_bundle",
]


_SCHEMA_VERSION = "source-provenance-bundle-v1"
_MAPPING_ALGORITHM_VERSION = "source-anchor-v1"
_PAYLOAD_SCHEMA_VERSION = "qdrant-payload-v1"
_DEFAULT_V1_CONFIG = {"chunk_size": 1000, "overlap": 200}
_DEFAULT_V2_CONFIG = {"max_chars": 1200, "llm": "disabled"}
_DEFAULT_MARKDOWN_CONFIG = {"block_preserving": True}
_SUPPORTED_CHUNKERS = {"v1", "v2", "markdown-block-v1"}
_HORIZONTAL_SPACE = re.compile(r"[ \t\f\v]+")
_MAX_BLOCKS = 200_000
_MAX_CHUNKS = 100_000
_MAX_ANCHORS = 400_000
_MAX_BLOCK_BYTES = 1 * 1024 * 1024
_MAX_CHUNK_BYTES = 256 * 1024
_MAX_BLOCK_SERIALIZED_BYTES = 2 * 1024 * 1024
_MAX_CHUNK_SERIALIZED_BYTES = 512 * 1024
_MAX_ANCHOR_SERIALIZED_BYTES = 4 * 1024
_MAX_BUNDLE_SERIALIZED_BYTES = 256 * 1024 * 1024


class SourceProvenanceBundleError(ValueError):
    """Stable, path-free bundle assembly error."""

    def __init__(self, message: str, *, code: str = "PROVENANCE_BUNDLE_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceProvenanceBundleV1:
    """Versioned bundle; this is not an InspectionManifest."""

    document_id: str
    media_type: str
    source_sha256: str
    source_hash_state: str
    source_parser_version: str
    normalize_version: str
    chunker: str
    chunker_config: Dict[str, Any]
    chunker_config_fingerprint: str
    payload_schema_version: str
    status: str
    progress: int
    error: Optional[str]
    pages: Tuple[dict, ...]
    blocks: Tuple[dict, ...]
    chunks: Tuple[dict, ...]
    anchors: Tuple[dict, ...]
    mapped_count: int
    unmapped_count: int
    unmapped_reasons: Tuple[dict, ...]
    chunk_snapshot_fingerprint: str
    llm_used: bool = False
    degradation_diagnostics: Tuple[str, ...] = ()
    sample_id: Optional[str] = None
    indexed_source_sha256: Optional[str] = None

    def to_dict(self) -> dict:
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "mapping_algorithm_version": _MAPPING_ALGORITHM_VERSION,
            "document_id": self.document_id,
            "media_type": self.media_type,
            "source_sha256": self.source_sha256,
            "source_hash_state": self.source_hash_state,
            "source_parser_version": self.source_parser_version,
            "normalize_version": self.normalize_version,
            "chunker": self.chunker,
            "chunker_config": dict(self.chunker_config),
            "chunker_config_fingerprint": self.chunker_config_fingerprint,
            "payload_schema_version": self.payload_schema_version,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "pages": list(self.pages),
            "blocks": list(self.blocks),
            "chunks": list(self.chunks),
            "anchors": list(self.anchors),
            "mapped_count": self.mapped_count,
            "unmapped_count": self.unmapped_count,
            "unmapped_reasons": list(self.unmapped_reasons),
            "chunk_snapshot_fingerprint": self.chunk_snapshot_fingerprint,
            "llm_used": self.llm_used,
            "degradation_diagnostics": list(self.degradation_diagnostics),
        }
        if self.sample_id is not None:
            payload["sample_id"] = self.sample_id
        if self.indexed_source_sha256 is not None:
            payload["indexed_source_sha256"] = self.indexed_source_sha256
        return payload


SourceProvenanceBundle = SourceProvenanceBundleV1


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _serialized_utf8_size(value: Any) -> int:
    """Return canonical JSON UTF-8 bytes or fail closed on non-JSON values."""
    try:
        return len(_canonical_json(value).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_SERIALIZATION_FAILED",
            code="PROVENANCE_BUNDLE_SERIALIZATION_FAILED",
        ) from error


def _enforce_serialized_size(value: Any, limit: int, code: str) -> None:
    if _serialized_utf8_size(value) > limit:
        raise SourceProvenanceBundleError(code, code=code)


def _mapping_text(text: str) -> str:
    """Apply the frozen mapping normalization without crossing block boundaries."""
    normalized = unicodedata.normalize(
        "NFKC", (text or "").replace("\r\n", "\n").replace("\r", "\n")
    )
    lines = [_HORIZONTAL_SPACE.sub(" ", line).rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _match_count(block_text: str, chunk_text: str) -> int:
    # SequenceMatcher's tie-breaking is direction-sensitive for repeated
    # text.  The frozen source-anchor-v1 oracle compares chunk first, then
    # source block; keep that order stable for duplicate/overlap anchors.
    left = _mapping_text(chunk_text)
    right = _mapping_text(block_text)
    return sum(
        match.size
        for match in SequenceMatcher(None, left, right, autojunk=False).get_matching_blocks()
    )


def _parser_pages(provenance: Any) -> Tuple[dict, ...]:
    return tuple(page.to_dict() for page in getattr(provenance, "pages", ()))


def _parser_blocks(provenance: Any) -> Tuple[dict, ...]:
    blocks = []
    media_type = getattr(provenance, "media_type", "")
    for block in getattr(provenance, "blocks", ()):
        item = dict(block.to_dict())
        item.setdefault("locator", _block_locator(block, media_type))
        blocks.append(item)
    return tuple(blocks)


def _pdf_chunk_pages(provenance: Any) -> List[Tuple[int, str]]:
    raw_by_page: Dict[int, List[str]] = {
        int(page.page): [] for page in getattr(provenance, "pages", ())
    }
    ordered_blocks = sorted(
        getattr(provenance, "blocks", ()),
        key=lambda block: (int(block.page), int(getattr(block, "display_ordinal", block.ordinal))),
    )
    for block in ordered_blocks:
        raw_by_page.setdefault(int(block.page), []).append(
            getattr(block, "raw_text", None) or block.text
        )
    raw_pages = [(page, "".join(parts)) for page, parts in raw_by_page.items()]
    reference_start = locate_reference_start(raw_pages)
    pages: List[Tuple[int, str]] = []
    for page, text in raw_pages:
        cleaned = normalize_text(
            text,
            ref_zone=reference_start is not None and page >= reference_start,
        )
        if cleaned:
            pages.append((page, cleaned))
    return pages


def _pdf_chunk_pages_v2(provenance: Any) -> List[Tuple[int, str]]:
    """Prepare PDF-v2 input without erasing display-block boundaries.

    v1 intentionally keeps its historical page-level input shape.  v2 needs
    each parser display block as an observable candidate for its rule/LLM
    boundary pass; joining same-page blocks here would make that pass silently
    skip the injected LLM.
    """
    ordered_blocks = sorted(
        getattr(provenance, "blocks", ()),
        key=lambda block: (int(block.page), int(getattr(block, "display_ordinal", block.ordinal))),
    )
    raw_by_page: Dict[int, List[str]] = {}
    for block in ordered_blocks:
        raw_by_page.setdefault(int(block.page), []).append(
            getattr(block, "raw_text", None) or block.text
        )
    raw_pages = [(page, "".join(parts)) for page, parts in raw_by_page.items()]
    reference_start = locate_reference_start(raw_pages)
    pages: List[Tuple[int, str]] = []
    for block in ordered_blocks:
        page = int(block.page)
        text = getattr(block, "raw_text", None) or block.text
        cleaned = normalize_text(
            text,
            ref_zone=reference_start is not None and page >= reference_start,
        )
        if cleaned:
            pages.append((page, cleaned))
    return pages


def _markdown_chunk_pages(provenance: Any) -> List[Tuple[None, str]]:
    return [
        (None, block.text)
        for block in getattr(provenance, "blocks", ())
        if (block.text or "").strip()
    ]


def _chunker_config(
    provenance: Any,
    chunker: str,
    config: Optional[Dict[str, Any]],
    llm: Optional[Callable[[str], str]],
) -> Dict[str, Any]:
    if config is not None:
        return dict(config)
    if getattr(provenance, "media_type", "") == "text/markdown" and chunker == "markdown-block-v1":
        return dict(_DEFAULT_MARKDOWN_CONFIG)
    if chunker == "v2":
        result = dict(_DEFAULT_V2_CONFIG)
        if llm is not None:
            result["llm"] = "injected"
        return result
    return dict(_DEFAULT_V1_CONFIG)


def _build_chunks(
    provenance: Any,
    chunker: str,
    config: Dict[str, Any],
    llm: Optional[Callable[[str], str]],
) -> Tuple[List[Chunk], bool, Tuple[str, ...], Optional[Tuple[str, ...]]]:
    media_type = getattr(provenance, "media_type", "")
    if media_type == "application/pdf":
        pages: Sequence[Tuple[Optional[int], str]] = (
            _pdf_chunk_pages_v2(provenance) if chunker == "v2" else _pdf_chunk_pages(provenance)
        )
    elif media_type == "text/markdown":
        pages = _markdown_chunk_pages(provenance)
    else:
        raise SourceProvenanceBundleError("SOURCE_MEDIA_TYPE_UNSUPPORTED", code="SOURCE_MEDIA_TYPE_UNSUPPORTED")

    if chunker == "markdown-block-v1":
        chunks: List[Chunk] = []
        chunk_block_ids: List[str] = []
        source_blocks = [block for block in getattr(provenance, "blocks", ()) if block.text.strip()]
        for source_block in source_blocks:
            section = (source_block.heading_path[-1] if source_block.heading_path else "") or ""
            for chunk in build_chunks_v1(
                [(None, source_block.text)],
                chunk_size=int(config.get("chunk_size", 1000)),
                overlap=int(config.get("overlap", 200)),
            ):
                chunk.section = section
                chunk.chunk_index = len(chunks)
                chunks.append(chunk)
                chunk_block_ids.append(source_block.block_id)
        return chunks, False, (), tuple(chunk_block_ids)
    if chunker == "v1":
        chunks = build_chunks_v1(
            pages,
            chunk_size=int(config.get("chunk_size", 1000)),
            overlap=int(config.get("overlap", 200)),
        )
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        return chunks, False, (), None
    if chunker == "v2":
        chunks, llm_used = build_chunks_v2(
            pages,
            max_chars=int(config.get("max_chars", 1200)),
            llm=llm,
        )
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        diagnostics = () if llm_used else ("V2_RULES_ONLY_LLM_NOT_USED",)
        return chunks, llm_used, diagnostics, None
    raise SourceProvenanceBundleError("CHUNKER_UNSUPPORTED", code="CHUNKER_UNSUPPORTED")


def _chunk_payload(chunk: Chunk, chunker: str) -> dict:
    return {
        "chunk_index": int(chunk.chunk_index),
        "text": chunk.text,
        "page": chunk.page,
        "page_end": chunk.page_end,
        "section": chunk.section,
        "chunker": chunker,
    }


def _add_markdown_line_ranges(chunks: List[dict], anchors: Sequence[dict]) -> None:
    """Project all source line locators covered by each Markdown chunk."""
    by_chunk: Dict[int, List[dict]] = {}
    for anchor in anchors:
        locator = anchor.get("locator", {})
        if "start_line" in locator and "end_line" in locator:
            by_chunk.setdefault(int(anchor["chunk_index"]), []).append(locator)
    for chunk in chunks:
        ranges = by_chunk.get(int(chunk["chunk_index"]), ())
        if ranges:
            chunk["start_line"] = min(int(item["start_line"]) for item in ranges)
            chunk["end_line"] = max(int(item["end_line"]) for item in ranges)
        else:
            chunk["start_line"] = None
            chunk["end_line"] = None


def _validate_capacity(
    provenance: Any,
    chunks: Sequence[dict],
    anchors: Sequence[dict],
) -> None:
    blocks = tuple(getattr(provenance, "blocks", ()))
    if len(blocks) > _MAX_BLOCKS:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_BLOCK_LIMIT", code="PROVENANCE_BUNDLE_BLOCK_LIMIT"
        )
    if len(chunks) > _MAX_CHUNKS:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_CHUNK_LIMIT", code="PROVENANCE_BUNDLE_CHUNK_LIMIT"
        )
    if len(anchors) > _MAX_ANCHORS:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_ANCHOR_LIMIT", code="PROVENANCE_BUNDLE_ANCHOR_LIMIT"
        )
    for block in blocks:
        if len((getattr(block, "text", "") or "").encode("utf-8")) > _MAX_BLOCK_BYTES:
            raise SourceProvenanceBundleError(
                "PROVENANCE_BUNDLE_BLOCK_TOO_LARGE", code="PROVENANCE_BUNDLE_BLOCK_TOO_LARGE"
            )
    for chunk in chunks:
        if len((chunk.get("text", "") or "").encode("utf-8")) > _MAX_CHUNK_BYTES:
            raise SourceProvenanceBundleError(
                "PROVENANCE_BUNDLE_CHUNK_TOO_LARGE", code="PROVENANCE_BUNDLE_CHUNK_TOO_LARGE"
            )


def _validate_serialized_capacity(
    blocks: Sequence[dict],
    chunks: Sequence[dict],
    anchors: Sequence[dict],
) -> None:
    for block in blocks:
        _enforce_serialized_size(
            block,
            _MAX_BLOCK_SERIALIZED_BYTES,
            "PROVENANCE_BUNDLE_BLOCK_SERIALIZED_TOO_LARGE",
        )
    for chunk in chunks:
        _enforce_serialized_size(
            chunk,
            _MAX_CHUNK_SERIALIZED_BYTES,
            "PROVENANCE_BUNDLE_CHUNK_SERIALIZED_TOO_LARGE",
        )
    for anchor in anchors:
        _enforce_serialized_size(
            anchor,
            _MAX_ANCHOR_SERIALIZED_BYTES,
            "PROVENANCE_BUNDLE_ANCHOR_SERIALIZED_TOO_LARGE",
        )


def validate_source_provenance_bundle(
    bundle: SourceProvenanceBundleV1,
    *,
    serialized_size: Optional[int] = None,
) -> None:
    """Validate a real bundle's serialized capacity before it is published.

    ``serialized_size`` is an optional count from a caller that has already
    streamed the exact canonical UTF-8 JSON bytes.  The normal production
    path leaves it unset and performs the canonical serialization itself;
    tests and streaming callers can exercise the 256 MiB boundary without
    materializing an unnecessary 256 MiB string.
    """
    if not isinstance(bundle, SourceProvenanceBundleV1):
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_VALIDATION_FAILED",
            code="PROVENANCE_BUNDLE_VALIDATION_FAILED",
        )
    _validate_serialized_capacity(bundle.blocks, bundle.chunks, bundle.anchors)
    if serialized_size is None:
        size = _serialized_utf8_size(bundle.to_dict())
    elif isinstance(serialized_size, int) and not isinstance(serialized_size, bool) and serialized_size >= 0:
        size = serialized_size
    else:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_SERIALIZATION_FAILED",
            code="PROVENANCE_BUNDLE_SERIALIZATION_FAILED",
        )
    if size > _MAX_BUNDLE_SERIALIZED_BYTES:
        raise SourceProvenanceBundleError(
            "PROVENANCE_BUNDLE_SERIALIZED_TOO_LARGE",
            code="PROVENANCE_BUNDLE_SERIALIZED_TOO_LARGE",
        )


def _block_locator(block: Any, media_type: str) -> dict:
    if media_type == "application/pdf":
        return {
            "page": int(block.page),
            "bbox": list(block.bbox),
            "normalized_bbox": list(block.normalized_bbox),
        }
    return {
        "start_line": int(block.start_line),
        "end_line": int(block.end_line),
    }


def _anchors(
    provenance: Any,
    chunks: Sequence[dict],
    chunk_block_ids: Optional[Sequence[str]] = None,
) -> Tuple[Tuple[dict, ...], int, int, Tuple[dict, ...]]:
    media_type = getattr(provenance, "media_type", "")
    blocks = list(getattr(provenance, "blocks", ()))
    anchors: List[dict] = []
    unmapped_reasons: List[dict] = []
    mapped_indices = set()
    chunker = chunks[0]["chunker"] if chunks else ""
    for chunk in chunks:
        candidate_blocks = blocks
        if chunk_block_ids is not None:
            block_id = chunk_block_ids[int(chunk["chunk_index"])]
            candidate_blocks = [block for block in blocks if block.block_id == block_id]
        scored = [
            (_match_count(block.text, chunk["text"]), block)
            for block in candidate_blocks
        ]
        scored = [(score, block) for score, block in scored if score > 0]
        scored.sort(key=lambda item: (-item[0], int(item[1].ordinal), chunker, int(chunk["chunk_index"])))
        if not scored:
            unmapped_reasons.append(
                {"chunk_index": int(chunk["chunk_index"]), "reason": "NO_SOURCE_BLOCK_OVERLAP"}
            )
            continue
        mapped_indices.add(int(chunk["chunk_index"]))
        denominator = max(1, len(_mapping_text(chunk["text"])))
        for position, (score, block) in enumerate(scored):
            anchors.append(
                {
                    "block_id": block.block_id,
                    "chunk_index": int(chunk["chunk_index"]),
                    "coverage": round(score / denominator, 6),
                    "is_primary": position == 0,
                    "locator": _block_locator(block, media_type),
                }
            )
    return tuple(anchors), len(mapped_indices), len(unmapped_reasons), tuple(unmapped_reasons)


def build_source_provenance_bundle(
    provenance: Any,
    *,
    chunker: str = "v1",
    chunker_config: Optional[Dict[str, Any]] = None,
    llm: Optional[Callable[[str], str]] = None,
    payload_schema_version: str = _PAYLOAD_SCHEMA_VERSION,
) -> SourceProvenanceBundleV1:
    """Assemble a bundle from a formal parser DTO and an existing chunker."""
    if chunker not in _SUPPORTED_CHUNKERS:
        raise SourceProvenanceBundleError("CHUNKER_UNSUPPORTED", code="CHUNKER_UNSUPPORTED")
    source_sha256 = getattr(provenance, "source_sha256", None)
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise SourceProvenanceBundleError("SOURCE_HASH_UNAVAILABLE", code="SOURCE_HASH_UNAVAILABLE")
    # Reject oversized source blocks before invoking a chunker, so malformed
    # provenance cannot force unnecessary allocation or partial output.
    _validate_capacity(provenance, (), ())
    bundle_blocks = _parser_blocks(provenance)
    _validate_serialized_capacity(bundle_blocks, (), ())

    config = _chunker_config(provenance, chunker, chunker_config, llm)
    chunks, llm_used, diagnostics, chunk_block_ids = _build_chunks(
        provenance, chunker, config, llm
    )
    chunk_payload_list = [_chunk_payload(chunk, chunker) for chunk in chunks]
    anchors, mapped_count, unmapped_count, unmapped_reasons = _anchors(
        provenance, chunk_payload_list, chunk_block_ids
    )
    if getattr(provenance, "media_type", "") == "text/markdown":
        _add_markdown_line_ranges(chunk_payload_list, anchors)
    chunk_payloads = tuple(chunk_payload_list)
    _validate_capacity(provenance, chunk_payloads, anchors)
    _validate_serialized_capacity(bundle_blocks, chunk_payloads, anchors)
    status = getattr(provenance, "status", "failed")
    error = getattr(provenance, "error", None)
    if unmapped_count and status == "ready":
        status = "partial"
        error = "SOURCE_BLOCK_UNMAPPED"
    bundle = SourceProvenanceBundleV1(
        document_id=str(provenance.document_id),
        media_type=str(provenance.media_type),
        source_sha256=source_sha256,
        source_hash_state="verified",
        source_parser_version=str(provenance.source_parser_version),
        normalize_version=str(provenance.normalize_version),
        chunker=chunker,
        chunker_config=config,
        chunker_config_fingerprint=_fingerprint(config),
        payload_schema_version=payload_schema_version,
        status=status,
        progress=100,
        error=error,
        pages=_parser_pages(provenance),
        blocks=bundle_blocks,
        chunks=chunk_payloads,
        anchors=anchors,
        mapped_count=mapped_count,
        unmapped_count=unmapped_count,
        unmapped_reasons=unmapped_reasons,
        chunk_snapshot_fingerprint=_fingerprint(list(chunk_payloads)),
        llm_used=llm_used,
        degradation_diagnostics=diagnostics,
        sample_id=getattr(provenance, "sample_id", None),
    )
    validate_source_provenance_bundle(bundle)
    return bundle
