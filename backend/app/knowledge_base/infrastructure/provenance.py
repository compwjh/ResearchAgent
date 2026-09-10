"""Task02A-C source provenance bundle assembly.

This module is an adapter around the production PDF/Markdown parser DTOs and
the existing v1/v2 chunkers.  It deliberately does not create a manifest,
embed text, or access Qdrant.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
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
_MAPPING_ALGORITHM_VERSION = "source-anchor-v2"
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


def _pdf_reference_start(provenance: Any) -> Optional[int]:
    """Return the reference-zone page used by the page chunk projection."""
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
    return locate_reference_start(raw_pages)


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
) -> Tuple[
    List[Chunk],
    bool,
    Tuple[str, ...],
    Optional[Tuple[str, ...]],
    Tuple[str, ...],
]:
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
        return (
            chunks,
            False,
            (),
            tuple(chunk_block_ids),
            tuple(f"block:{block_id}" for block_id in chunk_block_ids),
        )
    if chunker == "v1":
        chunks: List[Chunk] = []
        source_keys: List[str] = []
        if media_type == "application/pdf":
            page_keys = [f"page:{page}" for page, _ in pages]
        else:
            source_blocks = [block for block in getattr(provenance, "blocks", ()) if block.text.strip()]
            page_keys = [f"block:{block.block_id}" for block in source_blocks]
        for (page, text), source_key in zip(pages, page_keys, strict=True):
            page_chunks = build_chunks_v1(
                [(page, text)],
                chunk_size=int(config.get("chunk_size", 1000)),
                overlap=int(config.get("overlap", 200)),
            )
            for chunk in page_chunks:
                chunk.chunk_index = len(chunks)
                chunks.append(chunk)
                source_keys.append(source_key)
        return chunks, False, (), None, tuple(source_keys)
    if chunker == "v2":
        chunks, llm_used = build_chunks_v2(
            pages,
            max_chars=int(config.get("max_chars", 1200)),
            llm=llm,
        )
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        diagnostics = () if llm_used else ("V2_RULES_ONLY_LLM_NOT_USED",)
        return chunks, llm_used, diagnostics, None, ("document",) * len(chunks)
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


@dataclass(frozen=True)
class _SourceBlockRange:
    """A parser block's half-open interval in one normalized source stream."""

    block: Any
    start: int
    end: int


@dataclass(frozen=True)
class _SourceStream:
    """Normalized source text and the parser blocks that occupy its ranges."""

    key: str
    text: str
    blocks: Tuple[_SourceBlockRange, ...]
    valid: bool = True


def _non_empty_source_blocks(provenance: Any) -> List[Any]:
    return [
        block
        for block in getattr(provenance, "blocks", ())
        if (getattr(block, "text", "") or "").strip()
    ]


def _ordered_pdf_blocks(provenance: Any) -> List[Any]:
    return sorted(
        _non_empty_source_blocks(provenance),
        key=lambda block: (
            int(block.page),
            int(getattr(block, "display_ordinal", block.ordinal)),
        ),
    )


def _stream_with_block_ranges(
    key: str,
    text: str,
    blocks: Sequence[Any],
    block_texts: Optional[Sequence[str]] = None,
) -> _SourceStream:
    """Attach parser blocks to exact occurrences in an already-built stream.

    A block's position is resolved in parser order, not by textual similarity.
    If a parser/normalizer change means that an expected block is absent from
    the stream, the stream is marked invalid and all chunks using it fail
    closed as ``SOURCE_RANGE_UNRESOLVED``.
    """
    # Normalize only the mapping copy.  Chunker input/output remains the
    # parser/chunker text; this haystack must use the same NFKC/whitespace
    # projection as chunk lookup so ligatures and line endings do not make
    # otherwise exact ranges appear absent.
    source = _mapping_text(text or "")
    cursor = 0
    ranges: List[_SourceBlockRange] = []
    mapped_block_texts = (
        tuple(block_texts)
        if block_texts is not None
        else tuple(_mapping_text(getattr(block, "text", "") or "") for block in blocks)
    )
    for block, block_text in zip(blocks, mapped_block_texts, strict=True):
        if not block_text:
            continue
        start = source.find(block_text, cursor)
        if start < 0:
            return _SourceStream(key=key, text=source, blocks=(), valid=False)
        end = start + len(block_text)
        ranges.append(_SourceBlockRange(block=block, start=start, end=end))
        cursor = end
    return _SourceStream(key=key, text=source, blocks=tuple(ranges))


def _pdf_mapping_block_texts(
    blocks: Sequence[Any],
    *,
    ref_zone: bool,
    trim_cross_block_hyphenation: bool = True,
) -> Tuple[str, ...]:
    """Project PDF blocks with the same page normalization as the source.

    The page chunk projection normalizes the concatenated raw page.  A PDF
    line-break hyphen can therefore cross a parser block boundary (for
    example ``transac-`` + ``tion``); trim that one boundary hyphen from the
    mapping copy only so both sides still occupy exact source intervals.
    """
    mapped: List[str] = []
    for index, block in enumerate(blocks):
        raw_text = getattr(block, "raw_text", None) or getattr(block, "text", "")
        block_text = _mapping_text(normalize_text(raw_text, ref_zone=ref_zone))
        if (
            trim_cross_block_hyphenation
            and index + 1 < len(blocks)
            and re.search(r"(?<=\w)-\n$", raw_text or "")
            and re.match(r"\w", getattr(blocks[index + 1], "raw_text", None)
                         or getattr(blocks[index + 1], "text", ""))
            and block_text.endswith("-")
        ):
            block_text = block_text[:-1]
        mapped.append(block_text)
    return tuple(mapped)


def _source_streams(provenance: Any, chunker: str) -> Tuple[_SourceStream, ...]:
    """Build the exact normalized source streams consumed by each chunker."""
    media_type = getattr(provenance, "media_type", "")
    if media_type == "application/pdf":
        ordered_blocks = _ordered_pdf_blocks(provenance)
        if chunker == "v1":
            pages = _pdf_chunk_pages(provenance)
            reference_start = _pdf_reference_start(provenance)
            streams: List[_SourceStream] = []
            for page, text in pages:
                page_blocks = [block for block in ordered_blocks if int(block.page) == int(page)]
                streams.append(
                    _stream_with_block_ranges(
                        f"page:{page}",
                        text,
                        page_blocks,
                        _pdf_mapping_block_texts(
                            page_blocks,
                            ref_zone=reference_start is not None and page >= reference_start,
                        ),
                    )
                )
            return tuple(streams)

        pages = _pdf_chunk_pages_v2(provenance)
        source = "\n\n".join(text for _, text in pages)
        reference_start = _pdf_reference_start(provenance)
        block_texts = tuple(
            _mapping_text(
                normalize_text(
                    getattr(block, "raw_text", None) or getattr(block, "text", ""),
                    ref_zone=reference_start is not None and int(block.page) >= reference_start,
                )
            )
            for block in ordered_blocks
        )
        return (
            _stream_with_block_ranges(
                "document",
                source,
                ordered_blocks,
                block_texts,
            ),
        )

    if media_type == "text/markdown":
        source_blocks = _non_empty_source_blocks(provenance)
        if chunker in {"v1", "markdown-block-v1"}:
            return tuple(
                _stream_with_block_ranges(
                    f"block:{block.block_id}",
                    _mapping_text(block.text),
                    (block,),
                )
                for block in source_blocks
            )
        source = "\n\n".join(_mapping_text(block.text) for block in source_blocks)
        return (_stream_with_block_ranges("document", source, source_blocks),)

    return ()


def _exact_positions(source: str, needle: str) -> Tuple[int, ...]:
    """Return every exact occurrence, including overlapping occurrences."""
    if not needle:
        return ()
    positions: List[int] = []
    cursor = 0
    while True:
        position = source.find(needle, cursor)
        if position < 0:
            return tuple(positions)
        positions.append(position)
        cursor = position + 1


def _unique_exact_position(source: str, needle: str, minimum: int = 0) -> Optional[int]:
    positions = _exact_positions(source, needle)
    if len(positions) != 1 or positions[0] < minimum:
        return None
    return positions[0]


def _map_v1_chunks(
    chunks: Sequence[dict],
    stream: _SourceStream,
    overlap: int,
) -> Dict[int, Optional[Tuple[Tuple[int, int], ...]]]:
    """Map v1 chunks to exact source pieces, preserving overlap evidence.

    ``build_chunks_v1`` forms an overlap chunk by concatenating the tail of
    the preceding source piece with the next piece.  The separator discarded
    by that concatenation is allowed only when it contains whitespace; the
    two exact source ranges remain separate evidence intervals.
    """
    result: Dict[int, Optional[Tuple[Tuple[int, int], ...]]] = {}
    previous_piece: Optional[Tuple[str, int, int, str]] = None
    cursor = 0
    overlap = max(0, int(overlap))
    for chunk in chunks:
        chunk_index = int(chunk["chunk_index"])
        chunk_text = _mapping_text(chunk.get("text", ""))
        if not stream.valid or not chunk_text:
            result[chunk_index] = None
            previous_piece = None
            cursor = 0
            continue

        overlap_text = ""
        if previous_piece is not None and overlap:
            # The chunker slices overlap in source code points, while the
            # mapping copy may expand NFKC ligatures (e.g. ``ﬁ`` -> ``fi``).
            # Map the raw suffix first so the overlap boundary stays exact.
            overlap_text = _mapping_text(previous_piece[3][-overlap:])
        has_overlap = bool(overlap_text and chunk_text.startswith(overlap_text))
        piece_text = chunk_text[len(overlap_text):] if has_overlap else chunk_text
        position = _unique_exact_position(stream.text, piece_text, cursor)
        if position is None or (
            previous_piece is not None
            and stream.text[previous_piece[2] : position].strip()
        ):
            result[chunk_index] = None
            previous_piece = None
            cursor = 0
            continue

        piece_end = position + len(piece_text)
        if has_overlap and previous_piece is not None:
            segments = (
                (previous_piece[2] - len(overlap_text), previous_piece[2]),
                (position, piece_end),
            )
        else:
            segments = ((position, piece_end),)
        result[chunk_index] = segments
        previous_piece = (piece_text, position, piece_end, chunk.get("text", ""))
        cursor = piece_end
    return result


def _map_v2_chunks(
    chunks: Sequence[dict],
    stream: _SourceStream,
) -> Dict[int, Optional[Tuple[Tuple[int, int], ...]]]:
    """Map v2 chunks only when their complete text has one exact occurrence."""
    result: Dict[int, Optional[Tuple[Tuple[int, int], ...]]] = {}
    for chunk in chunks:
        chunk_index = int(chunk["chunk_index"])
        chunk_text = _mapping_text(chunk.get("text", ""))
        if not stream.valid or not chunk_text:
            result[chunk_index] = None
            continue
        position = _unique_exact_position(stream.text, chunk_text)
        result[chunk_index] = (
            ((position, position + len(chunk_text)),)
            if position is not None
            else None
        )
    return result


def _range_intersection_length(
    ranges: Sequence[Tuple[int, int]],
    start: int,
    end: int,
) -> int:
    intersections = sorted(
        (
            max(range_start, start),
            min(range_end, end),
        )
        for range_start, range_end in ranges
        if range_end > start and range_start < end
    )
    total = 0
    merged_end = -1
    for intersection_start, intersection_end in intersections:
        if intersection_end <= intersection_start:
            continue
        if intersection_start <= merged_end:
            merged_end = max(merged_end, intersection_end)
            continue
        total += intersection_end - intersection_start
        merged_end = intersection_end
    return total


def _anchors(
    provenance: Any,
    chunks: Sequence[dict],
    chunk_block_ids: Optional[Sequence[str]] = None,
    chunk_source_keys: Optional[Sequence[str]] = None,
    overlap: int = int(_DEFAULT_V1_CONFIG["overlap"]),
) -> Tuple[Tuple[dict, ...], int, int, Tuple[dict, ...]]:
    media_type = getattr(provenance, "media_type", "")
    anchors: List[dict] = []
    unmapped_reasons: List[dict] = []
    mapped_indices = set()
    chunker = chunks[0]["chunker"] if chunks else ""
    streams = {stream.key: stream for stream in _source_streams(provenance, chunker)}
    if chunk_source_keys is None:
        if chunker == "v2":
            chunk_source_keys = ("document",) * len(chunks)
        elif chunk_block_ids is not None:
            chunk_source_keys = tuple(f"block:{item}" for item in chunk_block_ids)
        elif media_type == "application/pdf":
            chunk_source_keys = tuple(
                f"page:{chunk.get('page')}" for chunk in chunks
            )
        else:
            chunk_source_keys = ("document",) * len(chunks)

    ranges_by_chunk: Dict[int, Optional[Tuple[Tuple[int, int], ...]]] = {}
    chunks_by_stream: Dict[str, List[dict]] = {}
    for chunk, source_key in zip(chunks, chunk_source_keys, strict=True):
        chunks_by_stream.setdefault(source_key, []).append(chunk)
    source_key_by_chunk = {
        int(chunk["chunk_index"]): source_key
        for chunk, source_key in zip(chunks, chunk_source_keys, strict=True)
    }
    if chunker == "v2":
        stream = streams.get("document")
        if stream is None:
            ranges_by_chunk = {int(chunk["chunk_index"]): None for chunk in chunks}
        else:
            ranges_by_chunk = _map_v2_chunks(chunks, stream)
    else:
        for source_key, grouped_chunks in chunks_by_stream.items():
            stream = streams.get(source_key)
            if stream is None:
                ranges_by_chunk.update(
                    {int(chunk["chunk_index"]): None for chunk in grouped_chunks}
                )
                continue
            ranges_by_chunk.update(_map_v1_chunks(grouped_chunks, stream, overlap))

    for chunk in chunks:
        chunk_index = int(chunk["chunk_index"])
        source_key = source_key_by_chunk[chunk_index]
        stream = streams.get(source_key)
        chunk_ranges = ranges_by_chunk.get(chunk_index)
        scored: List[Tuple[int, Any]] = []
        if stream is not None and chunk_ranges is not None:
            for block_range in stream.blocks:
                score = _range_intersection_length(
                    chunk_ranges,
                    block_range.start,
                    block_range.end,
                )
                if score > 0:
                    scored.append((score, block_range.block))
        scored.sort(
            key=lambda item: (
                -item[0],
                int(item[1].ordinal),
                chunker,
                chunk_index,
            )
        )
        if not scored:
            unmapped_reasons.append(
                {
                    "chunk_index": chunk_index,
                    "reason": "SOURCE_RANGE_UNRESOLVED",
                }
            )
            continue
        mapped_indices.add(chunk_index)
        denominator = max(1, len(_mapping_text(chunk["text"])))
        for position, (score, block) in enumerate(scored):
            anchors.append(
                {
                    "block_id": block.block_id,
                    "chunk_index": chunk_index,
                    "coverage": round(min(1.0, score / denominator), 6),
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
    chunks, llm_used, diagnostics, chunk_block_ids, chunk_source_keys = _build_chunks(
        provenance, chunker, config, llm
    )
    chunk_payload_list = [_chunk_payload(chunk, chunker) for chunk in chunks]
    anchors, mapped_count, unmapped_count, unmapped_reasons = _anchors(
        provenance,
        chunk_payload_list,
        chunk_block_ids,
        chunk_source_keys,
        int(config.get("overlap", _DEFAULT_V1_CONFIG["overlap"])),
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
        error = "SOURCE_RANGE_UNRESOLVED"
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
