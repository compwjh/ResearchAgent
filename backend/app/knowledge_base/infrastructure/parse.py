"""PDF 解析与切片（spec-011 / spec-012）。

- `pymupdf` 按页提取，保留 1-based 页码，用于回答引用。
- **切分逻辑已迁至 `chunkers.py`**（spec-012 第 3 项）：`Chunk` / `split_text` /
  `build_chunks_v1` 均从那里 re-export 或委派；本模块只负责 PDF 抽取。
  `build_chunks` 保留为 `build_chunks_v1` 的委派别名（name 不变，v1 行为零变更）。
- 清洗层（spec-012）：`extract_pages_normalized` 在抽取后套一层
  `normalize_text`，合并行末断词、把段落内硬换行转空格，保护列表/参考文献
  等结构行，提升召回文本可读性；`extract_pages` 保留原始行为不变（供单测/排查）。
"""

import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

from backend.app.knowledge_base.infrastructure.chunkers import (
    Chunk,
    build_chunks_v1,
    split_text,
)
from backend.app.knowledge_base.infrastructure.normalize import locate_reference_start, normalize_text

__all__ = [
    "Chunk",
    "PdfBlockProvenanceV1",
    "PdfLineProvenanceV1",
    "PdfPageProvenanceV1",
    "PdfParseError",
    "PdfSourceProvenanceV1",
    "build_chunks",
    "build_chunks_v1",
    "extract_pages",
    "extract_pages_normalized",
    "extract_pdf_provenance",
    "split_text",
    "total_chars",
]


class PdfParseError(RuntimeError):
    """PDF 无法解析（加密、损坏、无页面）。"""

    def __init__(self, message: str, *, code: str = "PDF_PARSE_FAILED") -> None:
        super().__init__(message)
        self.code = code


_BBox = Tuple[float, float, float, float]
_PDF_PROVENANCE_PARSER_VERSION = "pymupdf-display-dict-insertion-v2"
_PDF_PROVENANCE_NORMALIZE_VERSION = "normalize.py-v1"
_MAX_PDF_BYTES = 50 * 1024 * 1024
_PDF_SOURCE_READ_FAILED = "PDF_SOURCE_READ_FAILED"
_PDF_TOO_LARGE = "PDF_TOO_LARGE"
_PDF_SOURCE_HASH_INVALID = "PDF_SOURCE_HASH_INVALID"
_PDF_SOURCE_HASH_MISMATCH = "PDF_SOURCE_HASH_MISMATCH"
_PDF_OPEN_FAILED = "PDF_OPEN_FAILED"
_PDF_ENCRYPTED = "PDF_ENCRYPTED"
_PDF_EMPTY = "PDF_EMPTY"
_PDF_PROVENANCE_UNAVAILABLE = "PDF_PROVENANCE_UNAVAILABLE"
_BBOX_NORMALIZED_TOLERANCE = 0.005
_ACTIVE_ACTION_RE = re.compile(
    r"/(?:JavaScript|JS|EmbeddedFiles|XFA|RichMedia|OpenAction|AA)\b"
    r"|/S\s*/(?:JavaScript|Launch|SubmitForm|ImportData|GoToR|RichMedia)\b",
    re.IGNORECASE,
)


def _as_bbox(value) -> _BBox:
    """Convert and validate a finite, ordered PyMuPDF rectangle."""
    try:
        coordinates = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as error:
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE) from error
    if len(coordinates) != 4 or not all(math.isfinite(item) for item in coordinates):
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    if coordinates[0] > coordinates[2] or coordinates[1] > coordinates[3]:
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    return coordinates  # type: ignore[return-value]


def _validate_bbox_in_crop(bbox: _BBox, crop_box: _BBox) -> bool:
    """Validate crop bounds; return true only for a small renderer overflow."""
    crop_width = crop_box[2] - crop_box[0]
    crop_height = crop_box[3] - crop_box[1]
    if crop_width <= 0 or crop_height <= 0:
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    x_overflow = max(crop_box[0] - bbox[0], bbox[2] - crop_box[2], 0.0) / crop_width
    y_overflow = max(crop_box[1] - bbox[1], bbox[3] - crop_box[3], 0.0) / crop_height
    if max(x_overflow, y_overflow) > _BBOX_NORMALIZED_TOLERANCE:
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    return x_overflow > 0 or y_overflow > 0


def _normalized_bbox(
    bbox: _BBox,
    page_width: float,
    page_height: float,
    *,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    tolerate_renderer_overflow: bool = False,
) -> _BBox:
    """Normalize raw PDF coordinates against the unrotated crop box."""
    if page_width <= 0 or page_height <= 0:
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    normalized = (
        (bbox[0] - origin_x) / page_width,
        (bbox[1] - origin_y) / page_height,
        (bbox[2] - origin_x) / page_width,
        (bbox[3] - origin_y) / page_height,
    )
    if not all(math.isfinite(value) for value in normalized):
        raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
    if not all(0 <= value <= 1 for value in normalized):
        if not tolerate_renderer_overflow:
            raise PdfParseError(_PDF_PROVENANCE_UNAVAILABLE, code=_PDF_PROVENANCE_UNAVAILABLE)
        normalized = tuple(min(1.0, max(0.0, value)) for value in normalized)
    return normalized  # type: ignore[return-value]


@dataclass(frozen=True)
class PdfLineProvenanceV1:
    """A display-order line and its source-local character interval."""

    ordinal: int
    text: str
    start: int
    end: int
    bbox: _BBox
    normalized_bbox: _BBox

    def to_dict(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "bbox": list(self.bbox),
            "normalized_bbox": list(self.normalized_bbox),
        }


@dataclass(frozen=True)
class PdfPageProvenanceV1:
    """Page geometry in the same display coordinate space as its blocks."""

    page: int
    width: float
    height: float
    rotation: int
    crop_box: _BBox

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "crop_box": list(self.crop_box),
        }


@dataclass(frozen=True)
class PdfBlockProvenanceV1:
    """A stable display-order text block with raw and normalized coordinates."""

    block_id: str
    ordinal: int
    display_ordinal: int
    page: int
    text: str
    raw_text: str
    start: int
    end: int
    bbox: _BBox
    normalized_bbox: _BBox
    lines: Tuple[PdfLineProvenanceV1, ...] = ()
    block_type: str = "paragraph"
    heading_path: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "ordinal": self.ordinal,
            "display_ordinal": self.display_ordinal,
            "page": self.page,
            "text": self.text,
            "raw_text": self.raw_text,
            "start": self.start,
            "end": self.end,
            "bbox": list(self.bbox),
            "normalized_bbox": list(self.normalized_bbox),
            "lines": [line.to_dict() for line in self.lines],
            "block_type": self.block_type,
            "heading_path": list(self.heading_path),
        }


@dataclass(frozen=True)
class PdfSourceProvenanceV1:
    """Versioned PDF provenance produced from one PyMuPDF display extraction.

    ``text`` and each block's bbox are deliberately carried together.  Consumers
    must use this object for source anchors instead of re-extracting page text.
    Word extraction is intentionally omitted: line data is diagnostic only and
    is never a hard gate for accepting a block.
    """

    SCHEMA_VERSION: ClassVar[str] = "pdf-source-provenance-v1"

    document_id: str
    pages: Tuple[PdfPageProvenanceV1, ...]
    blocks: Tuple[PdfBlockProvenanceV1, ...]
    source_sha256: Optional[str]
    status: str
    error: Optional[str]
    sample_id: Optional[str] = None
    media_type: str = "application/pdf"
    source_parser_version: str = _PDF_PROVENANCE_PARSER_VERSION
    normalize_version: str = _PDF_PROVENANCE_NORMALIZE_VERSION

    @property
    def metrics(self) -> dict:
        return {
            "page_count": len(self.pages),
            "block_count": len(self.blocks),
            "line_count": sum(len(block.lines) for block in self.blocks),
        }

    def to_dict(self) -> dict:
        """Return the pure parser DTO; Task02A-C adds bundle/index fields later."""
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "document_id": self.document_id,
            "media_type": self.media_type,
            "source_sha256": self.source_sha256,
            "source_parser_version": self.source_parser_version,
            "normalize_version": self.normalize_version,
            "status": self.status,
            "error": self.error,
            "pages": [page.to_dict() for page in self.pages],
            "blocks": [block.to_dict() for block in self.blocks],
            "metrics": self.metrics,
        }
        if self.sample_id is not None:
            payload["sample_id"] = self.sample_id
        return payload


@dataclass(frozen=True)
class _DisplayBlockRecord:
    """Internal one-pass record retaining insertion and source coordinates."""

    display_ordinal: int
    raw_text: str
    lines: Tuple[PdfLineProvenanceV1, ...]
    bbox: _BBox
    coordinate_adjusted: bool


def _block_lines(
    block: dict,
    page_width: float,
    page_height: float,
    crop_box: _BBox,
    *,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
) -> Tuple[str, Tuple[PdfLineProvenanceV1, ...], bool]:
    """Build raw block text and line DTOs from one ``dict`` extraction block."""
    raw_parts: List[str] = []
    lines: List[PdfLineProvenanceV1] = []
    coordinate_adjusted = False
    offset = 0
    for line_ordinal, line in enumerate(block.get("lines", ())):
        line_text = "".join(str(span.get("text", "")) for span in line.get("spans", ()))
        if not line_text:
            continue
        line_start = offset
        line_end = line_start + len(line_text)
        raw_parts.append(line_text)
        raw_parts.append("\n")
        offset = line_end + 1
        line_bbox = _as_bbox(line.get("bbox"))
        line_adjusted = _validate_bbox_in_crop(line_bbox, crop_box)
        coordinate_adjusted = coordinate_adjusted or line_adjusted
        lines.append(
            PdfLineProvenanceV1(
                ordinal=line_ordinal,
                text=line_text,
                start=line_start,
                end=line_end,
                bbox=line_bbox,
                normalized_bbox=_normalized_bbox(
                    line_bbox,
                    page_width,
                    page_height,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    tolerate_renderer_overflow=line_adjusted,
                ),
            )
        )
    raw_text = "".join(raw_parts)
    if not lines and block.get("text"):
        raw_text = str(block["text"])
        if not raw_text.endswith("\n"):
            raw_text += "\n"
    return raw_text, tuple(lines), coordinate_adjusted


def _read_pdf_bytes(path: Path) -> bytes:
    """Read at most the configured PDF budget plus one sentinel byte."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_PDF_BYTES + 1)
    except (OSError, ValueError) as error:
        raise PdfParseError(_PDF_SOURCE_READ_FAILED, code=_PDF_SOURCE_READ_FAILED) from error
    if len(payload) > _MAX_PDF_BYTES:
        raise PdfParseError(_PDF_TOO_LARGE, code=_PDF_TOO_LARGE)
    return payload


def _inspect_active_features(document) -> str:
    """Inspect PDF object dictionaries without fetching or executing actions.

    ``safe`` means no active capability was found, ``hostile`` means a known
    action/form/embedded capability exists, and ``unavailable`` is fail-closed.
    Ordinary ``/S /URI`` link annotations are intentionally not considered
    hostile: the parser never follows them.
    """
    try:
        catalog = int(document.pdf_catalog())
        if catalog <= 0:
            return "unavailable"
        for key in ("OpenAction", "AA", "AcroForm"):
            kind, value = document.xref_get_key(catalog, key)
            if kind not in ("null", "none") and value not in ("null", ""):
                return "hostile"
        for xref in range(1, document.xref_length()):
            obj = document.xref_object(xref, compressed=False)
            if _ACTIVE_ACTION_RE.search(obj):
                return "hostile"
        return "safe"
    except Exception:
        return "unavailable"


def _display_dict(page) -> dict:
    """One passive display extraction; kept as a spyable seam for regression tests."""
    return page.get_text("dict", sort=False)


def extract_pdf_provenance(
    path,
    *,
    document_id: Optional[str] = None,
    sample_id: Optional[str] = None,
    source_sha256: Optional[str] = None,
) -> PdfSourceProvenanceV1:
    """Extract a pure PDF provenance DTO from one passive display pass.

    The original insertion order is retained for the legacy normalized-page
    projection.  Provenance blocks use an explicit stable coordinate order
    ``(page, bbox.y0, bbox.x0, display_ordinal)``.  No second text extraction is
    used for either view.
    """
    import pymupdf

    try:
        file_path = Path(path)
    except (TypeError, ValueError) as error:
        raise PdfParseError(_PDF_SOURCE_READ_FAILED, code=_PDF_SOURCE_READ_FAILED) from error
    source_bytes = _read_pdf_bytes(file_path)
    computed_sha256 = sha256(source_bytes).hexdigest()
    if source_sha256 is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha256):
            raise PdfParseError(_PDF_SOURCE_HASH_INVALID, code=_PDF_SOURCE_HASH_INVALID)
        if source_sha256.lower() != computed_sha256:
            raise PdfParseError(_PDF_SOURCE_HASH_MISMATCH, code=_PDF_SOURCE_HASH_MISMATCH)
    resolved_source_sha256 = computed_sha256
    resolved_document_id = document_id or file_path.stem

    try:
        document = pymupdf.open(stream=source_bytes, filetype="pdf")
    except Exception as error:  # pymupdf 对损坏文件抛各类异常
        raise PdfParseError(_PDF_OPEN_FAILED, code=_PDF_OPEN_FAILED) from error
    try:
        if document.is_encrypted and not document.authenticate(""):
            raise PdfParseError(_PDF_ENCRYPTED, code=_PDF_ENCRYPTED)
        if document.page_count == 0:
            raise PdfParseError(_PDF_EMPTY, code=_PDF_EMPTY)

        pages: List[PdfPageProvenanceV1] = []
        blocks: List[PdfBlockProvenanceV1] = []
        page_display_blocks: Dict[int, Tuple[_DisplayBlockRecord, ...]] = {}
        coordinate_adjusted = False
        for page_number, page in enumerate(document, start=1):
            try:
                crop_box = _as_bbox(page.cropbox)
                _validate_bbox_in_crop(crop_box, crop_box)
                crop_origin_x, crop_origin_y = crop_box[0], crop_box[1]
                page_width = crop_box[2] - crop_origin_x
                page_height = crop_box[3] - crop_origin_y
                if page_width <= 0 or page_height <= 0:
                    raise PdfParseError(
                        _PDF_PROVENANCE_UNAVAILABLE,
                        code=_PDF_PROVENANCE_UNAVAILABLE,
                    )
                pages.append(
                    PdfPageProvenanceV1(
                        page=page_number,
                        width=page_width,
                        height=page_height,
                        rotation=int(page.rotation),
                        crop_box=crop_box,
                    )
                )
                display = _display_dict(page)
                display_records: List[_DisplayBlockRecord] = []
                for display_ordinal, display_block in enumerate(display.get("blocks", ())):
                    if int(display_block.get("type", 0)) != 0:
                        continue
                    raw_text, lines, block_adjusted = _block_lines(
                        display_block,
                        page_width,
                        page_height,
                        crop_box,
                        origin_x=crop_origin_x,
                        origin_y=crop_origin_y,
                    )
                    if not raw_text or not normalize_text(raw_text):
                        continue
                    block_bbox = _as_bbox(display_block.get("bbox"))
                    block_adjusted = _validate_bbox_in_crop(block_bbox, crop_box) or block_adjusted
                    coordinate_adjusted = coordinate_adjusted or block_adjusted
                    display_records.append(
                        _DisplayBlockRecord(
                            display_ordinal=display_ordinal,
                            raw_text=raw_text,
                            lines=lines,
                            bbox=block_bbox,
                            coordinate_adjusted=block_adjusted,
                        )
                    )
                page_display_blocks[page_number] = tuple(display_records)
            except PdfParseError:
                raise
            except Exception as error:
                raise PdfParseError(
                    _PDF_PROVENANCE_UNAVAILABLE,
                    code=_PDF_PROVENANCE_UNAVAILABLE,
                ) from error

        active_state = _inspect_active_features(document)
        if active_state == "unavailable":
            status, error = "failed", _PDF_PROVENANCE_UNAVAILABLE
        else:
            block_ordinal = 0
            block_id_prefix = sample_id or resolved_document_id
            for page_number, records in page_display_blocks.items():
                ordered_records = sorted(
                    records,
                    key=lambda record: (
                        record.bbox[1],
                        record.bbox[0],
                        record.display_ordinal,
                    ),
                )
                for page_block_ordinal, record in enumerate(ordered_records):
                    normalized_text = normalize_text(record.raw_text)
                    blocks.append(
                        PdfBlockProvenanceV1(
                            block_id=f"{block_id_prefix}:p{page_number}:b{page_block_ordinal}",
                            ordinal=block_ordinal,
                            display_ordinal=record.display_ordinal,
                            page=page_number,
                            text=normalized_text,
                            raw_text=record.raw_text,
                            start=0,
                            end=len(record.raw_text),
                            bbox=record.bbox,
                            normalized_bbox=_normalized_bbox(
                                record.bbox,
                                pages[page_number - 1].width,
                                pages[page_number - 1].height,
                                origin_x=pages[page_number - 1].crop_box[0],
                                origin_y=pages[page_number - 1].crop_box[1],
                                tolerate_renderer_overflow=record.coordinate_adjusted,
                            ),
                            lines=record.lines,
                        )
                    )
                    block_ordinal += 1
            if not blocks:
                status, error = "failed", "PDF_NO_TEXT"
            elif active_state == "hostile":
                status, error = "partial", "HOSTILE_FEATURES_NOT_EXECUTED"
            elif coordinate_adjusted:
                status, error = "partial", _PDF_PROVENANCE_UNAVAILABLE
            else:
                status, error = "ready", None
        return PdfSourceProvenanceV1(
            document_id=resolved_document_id,
            sample_id=sample_id,
            pages=tuple(pages),
            blocks=tuple(blocks),
            source_sha256=resolved_source_sha256,
            status=status,
            error=error,
        )
    finally:
        document.close()


def extract_pages(path) -> List[Tuple[int, str]]:
    """返回 [(页码, 该页纯文本)]，页码从 1 开始。"""
    import pymupdf

    try:
        document = pymupdf.open(str(path))
    except Exception as error:  # pymupdf 对损坏文件抛各类异常
        raise PdfParseError(_PDF_OPEN_FAILED, code=_PDF_OPEN_FAILED) from error
    try:
        if document.is_encrypted and not document.authenticate(""):
            raise PdfParseError(_PDF_ENCRYPTED, code=_PDF_ENCRYPTED)
        if document.page_count == 0:
            raise PdfParseError(_PDF_EMPTY, code=_PDF_EMPTY)
        return [
            (number, (page.get_text("text") or "").strip())
            for number, page in enumerate(document, start=1)
        ]
    finally:
        document.close()


def extract_pages_normalized(path) -> List[Tuple[int, str]]:
    """从 `PdfSourceProvenanceV1` 投影每页文本并套 `normalize_text` 清洗。

    返回结构同 `extract_pages`：`[(页码, 清洗后文本)]`，页码 1-based。
    规范化文本与 block bbox 来自同一次 display extraction；旧返回结构仍为
    `[(页码, 清洗后文本)]`。**参考文献页（`page >= locate_reference_start`）传 `ref_zone=True`**：
    该模式下只有新条目（`[数字]` 开头）才保留换行，避免条目被标题里的
    行末冒号切成两半（详见 `normalize._rejoin_lines`）。
    清洗后空白的页跳过；原 `extract_pages` 保持不变，供单测与排查使用。
    """
    provenance = extract_pdf_provenance(path)
    raw_by_page = {page.page: [] for page in provenance.pages}
    for block in sorted(provenance.blocks, key=lambda item: (item.page, item.display_ordinal)):
        raw_by_page.setdefault(block.page, []).append(block.raw_text)
    pages = [(page, "".join(raw_by_page.get(page, ()))) for page in raw_by_page]
    ref_start = locate_reference_start(pages)
    normalized: List[Tuple[int, str]] = []
    for page, text in pages:
        is_ref_zone = ref_start is not None and int(page) >= ref_start
        cleaned = normalize_text(text, ref_zone=is_ref_zone)
        if not cleaned:
            continue
        normalized.append((int(page), cleaned))
    return normalized


def total_chars(pages) -> int:
    return sum(len(text) for _, text in pages)


def build_chunks(pages, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
    """v1 委派别名（spec-012）：逐页切片，不跨页合并，行为与旧 `build_chunks` 完全一致。

    新代码请直接使用 `chunkers.build_chunks_v1` / `build_chunks_v2`。
    """
    return build_chunks_v1(pages, chunk_size, overlap)
