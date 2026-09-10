"""安全、可追踪的 Markdown source provenance parser。

本模块只负责把当前 Markdown 原件变成纯 parser DTO。它不渲染 HTML、不加载
图片、不访问网络，也不创建 chunk、anchor 或 manifest；后续索引层可消费
``MarkdownSourceProvenanceV1.blocks`` 并复用既有 chunk DTO。
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, ClassVar, List, Optional, Sequence, Tuple, Union

__all__ = [
    "MarkdownBlockProvenanceV1",
    "MarkdownInlineResourceV1",
    "MarkdownParseError",
    "MarkdownSourceProvenanceV1",
    "extract_markdown_provenance",
]


_MAX_MARKDOWN_BLOCKS = 200_000
_MAX_MARKDOWN_BYTES = 50 * 1024 * 1024
_MAX_MARKDOWN_BLOCK_BYTES = 1 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024
_MARKDOWN_MEDIA_TYPE = "text/markdown"
_MARKDOWN_PARSER_VERSION = "markdown-source-parser-v1"
_MARKDOWN_NORMALIZE_VERSION = "nfkc-crlf-lf-trim-horizontal-space-v1"
_INVALID_ENCODING = "INVALID_ENCODING"
_MARKDOWN_PARSE_FAILED = "MARKDOWN_PARSE_FAILED"
_MARKDOWN_SOURCE_READ_FAILED = "MARKDOWN_SOURCE_READ_FAILED"
_SOURCE_HASH_INVALID = "SOURCE_HASH_INVALID"
_SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
_MARKDOWN_BLOCK_LIMIT = "MARKDOWN_BLOCK_LIMIT"
_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
_MARKDOWN_BLOCK_TOO_LARGE = "MARKDOWN_BLOCK_TOO_LARGE"
_HOSTILE_MARKDOWN = "HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE"

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)\s*|)$")
_SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)\s*$")
_LIST_RE = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])(?:[ \t]+|$)")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_BLOCKQUOTE_RE = re.compile(r"^ {0,3}>")
_HORIZONTAL_RULE_RE = re.compile(r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_HTML_BLOCK_RE = re.compile(
    r"^ {0,3}(?:<!--|<![A-Z]|<\?|</?(?:address|article|aside|base|blockquote|body|"
    r"caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|"
    r"figcaption|figure|footer|form|h[1-6]|head|header|hr|html|iframe|legend|"
    r"li|link|main|menu|menuitem|nav|ol|p|pre|script|section|summary|table|"
    r"tbody|td|tfoot|th|thead|title|tr|track|ul)(?:\s|/?>|$))",
    re.IGNORECASE,
)
_SINGLE_LINE_HTML_RE = re.compile(
    r"^ {0,3}<([A-Za-z][A-Za-z0-9-]*)\b[^>]*>.*</\1\s*>\s*$",
    re.IGNORECASE,
)
_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\"']([^\"']*)[\"'])?\s*\)"
)
_HTML_IMAGE_RE = re.compile(
    r"<img\b[^>]*?\bsrc\s*=\s*(?:[\"']([^\"']+)[\"']|([^\s>]+))[^>]*>",
    re.IGNORECASE,
)
_HOSTILE_SCRIPT_RE = re.compile(r"<\s*/?\s*script\b|\bon[a-z][\w-]*\s*=|javascript\s*:", re.IGNORECASE)


class MarkdownParseError(ValueError):
    """Stable, path-free Markdown parser error."""

    def __init__(self, message: str, *, code: str = _MARKDOWN_PARSE_FAILED) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MarkdownInlineResourceV1:
    """An image reference retained as metadata; it is never loaded."""

    resource_id: str
    alt: str
    destination: str
    title: Optional[str]
    loadable: bool
    placeholder: str
    kind: str = "image"

    def to_dict(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "alt": self.alt,
            "destination": self.destination,
            "title": self.title,
            "loadable": self.loadable,
            "placeholder": self.placeholder,
        }


@dataclass(frozen=True)
class MarkdownBlockProvenanceV1:
    """One source block with offsets into the normalized LF document."""

    block_id: str
    ordinal: int
    text: str
    start: int
    end: int
    start_line: int
    end_line: int
    heading_path: Tuple[str, ...]
    block_type: str
    inline_resources: Tuple[MarkdownInlineResourceV1, ...] = ()
    diagnostics: Tuple[str, ...] = ()

    @property
    def normalized_text(self) -> str:
        """Alias used by callers that want to make normalization explicit."""
        return self.text

    @property
    def page(self) -> None:
        return None

    @property
    def page_end(self) -> None:
        return None

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "locator": {
                "start_line": self.start_line,
                "end_line": self.end_line,
            },
            "heading_path": list(self.heading_path),
            "block_type": self.block_type,
            "start": self.start,
            "end": self.end,
            "page": None,
            "page_end": None,
            "inline_resources": [item.to_dict() for item in self.inline_resources],
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class MarkdownSourceProvenanceV1:
    """Versioned, pure Markdown parser output; no bundle or manifest fields."""

    SCHEMA_VERSION: ClassVar[str] = "markdown-source-provenance-v1"

    document_id: str
    source_sha256: str
    normalized_text: str
    blocks: Tuple[MarkdownBlockProvenanceV1, ...]
    status: str
    error: Optional[str]
    sample_id: Optional[str] = None
    source_parser_version: str = _MARKDOWN_PARSER_VERSION
    normalize_version: str = _MARKDOWN_NORMALIZE_VERSION
    media_type: str = _MARKDOWN_MEDIA_TYPE
    line_count: int = 0

    def to_dict(self) -> dict:
        diagnostics = [
            diagnostic
            for block in self.blocks
            for diagnostic in block.diagnostics
        ]
        result = {
            "schema_version": self.SCHEMA_VERSION,
            "document_id": self.document_id,
            "media_type": self.media_type,
            "source_sha256": self.source_sha256,
            "source_parser_version": self.source_parser_version,
            "normalize_version": self.normalize_version,
            "status": self.status,
            "error": self.error,
            "normalized_text": self.normalized_text,
            "blocks": [block.to_dict() for block in self.blocks],
            "metrics": {
                "page_count": None,
                "line_count": self.line_count,
                "block_count": len(self.blocks),
                "image_count": sum(len(block.inline_resources) for block in self.blocks),
                "diagnostic_count": len(diagnostics),
                "markdown_line_exact_rate": 1.0,
            },
        }
        if self.sample_id is not None:
            result["sample_id"] = self.sample_id
        return result


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    start: int
    end: int


def _read_stream(stream: BinaryIO) -> bytes:
    chunks: List[bytes] = []
    total = 0
    while total <= _MAX_MARKDOWN_BYTES:
        try:
            chunk = stream.read(min(_READ_CHUNK_BYTES, _MAX_MARKDOWN_BYTES + 1 - total))
        except (OSError, ValueError) as error:
            raise MarkdownParseError(_MARKDOWN_SOURCE_READ_FAILED, code=_MARKDOWN_SOURCE_READ_FAILED) from error
        if chunk in (b"", None):
            break
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise MarkdownParseError(_MARKDOWN_SOURCE_READ_FAILED, code=_MARKDOWN_SOURCE_READ_FAILED)
        chunk_bytes = bytes(chunk)
        total += len(chunk_bytes)
        if total > _MAX_MARKDOWN_BYTES:
            raise MarkdownParseError(_PAYLOAD_TOO_LARGE, code=_PAYLOAD_TOO_LARGE)
        chunks.append(chunk_bytes)
    return b"".join(chunks)


def _read_source(
    source: Union[bytes, bytearray, memoryview, BinaryIO, os.PathLike, str]
) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        if len(source) > _MAX_MARKDOWN_BYTES:
            raise MarkdownParseError(_PAYLOAD_TOO_LARGE, code=_PAYLOAD_TOO_LARGE)
        return bytes(source)
    if isinstance(source, os.PathLike):
        try:
            with Path(source).open("rb") as stream:
                return _read_stream(stream)
        except MarkdownParseError:
            raise
        except (OSError, ValueError) as error:
            raise MarkdownParseError(_MARKDOWN_SOURCE_READ_FAILED, code=_MARKDOWN_SOURCE_READ_FAILED) from error
    if hasattr(source, "read"):
        return _read_stream(source)  # type: ignore[arg-type]
    if isinstance(source, str):
        # String input is raw Markdown by design; callers with files should pass Path.
        try:
            encoded = source.encode("utf-8")
        except UnicodeEncodeError as error:
            raise MarkdownParseError(_INVALID_ENCODING, code=_INVALID_ENCODING) from error
        if len(encoded) > _MAX_MARKDOWN_BYTES:
            raise MarkdownParseError(_PAYLOAD_TOO_LARGE, code=_PAYLOAD_TOO_LARGE)
        return encoded
    raise MarkdownParseError(_MARKDOWN_SOURCE_READ_FAILED, code=_MARKDOWN_SOURCE_READ_FAILED)


def _decode_and_normalize(raw: bytes) -> Tuple[str, int]:
    payload = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MarkdownParseError(_INVALID_ENCODING, code=_INVALID_ENCODING) from error
    if "\x00" in decoded:
        raise MarkdownParseError(_INVALID_ENCODING, code=_INVALID_ENCODING)

    text = unicodedata.normalize("NFKC", decoded)
    had_final_newline = text.endswith(("\n", "\r"))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = text.split("\n") if text else []
    if raw_lines and had_final_newline:
        raw_lines.pop()
    lines = [line.rstrip(" \t") for line in raw_lines]
    normalized = "\n".join(lines)
    if had_final_newline and lines:
        normalized += "\n"
    return normalized, len(lines)


def _make_lines(normalized: str) -> List[_Line]:
    if not normalized:
        return []
    content = normalized[:-1] if normalized.endswith("\n") else normalized
    texts = content.split("\n")
    lines: List[_Line] = []
    offset = 0
    for number, text in enumerate(texts, start=1):
        lines.append(_Line(number=number, text=text, start=offset, end=offset + len(text)))
        offset += len(text) + 1
    return lines


def _heading_match(text: str) -> Optional[Tuple[int, str]]:
    match = _HEADING_RE.match(text)
    if not match:
        return None
    title = (match.group(2) or "").strip()
    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
    return len(match.group(1)), title


def _setext_match(lines: Sequence[_Line], index: int) -> Optional[str]:
    if index + 1 >= len(lines) or not lines[index].text.strip():
        return None
    if _SETEXT_RE.match(lines[index + 1].text) and not _is_block_start(lines[index].text):
        return lines[index].text.strip()
    return None


def _is_table_start(lines: Sequence[_Line], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index].text:
        return False
    return bool(_TABLE_SEPARATOR_RE.match(lines[index + 1].text))


def _is_block_start(text: str) -> bool:
    return bool(
        _heading_match(text)
        or _FENCE_RE.match(text)
        or _LIST_RE.match(text)
        or _BLOCKQUOTE_RE.match(text)
        or _HORIZONTAL_RULE_RE.match(text)
        or _HTML_BLOCK_RE.match(text)
    )


def _is_multiline_html_block(text: str) -> bool:
    return bool(_HTML_BLOCK_RE.match(text) and not _SINGLE_LINE_HTML_RE.match(text))


def _consume_fence(lines: Sequence[_Line], index: int, match: re.Match) -> int:
    marker = match.group(1)
    char = marker[0]
    length = len(marker)
    for cursor in range(index + 1, len(lines)):
        if re.match(rf"^ {{0,3}}{re.escape(char)}{{{length},}}\s*$", lines[cursor].text):
            return cursor
    return len(lines) - 1


def _consume_list(lines: Sequence[_Line], index: int) -> int:
    cursor = index + 1
    while cursor < len(lines):
        text = lines[cursor].text
        if not text.strip():
            if cursor + 1 < len(lines) and (
                _LIST_RE.match(lines[cursor + 1].text)
                or lines[cursor + 1].text.startswith((" ", "\t"))
            ):
                cursor += 1
                continue
            break
        if _LIST_RE.match(text) or text.startswith((" ", "\t")):
            cursor += 1
            continue
        # Markdown permits a lazy continuation line inside a list item.
        if not _is_block_start(text):
            cursor += 1
            continue
        break
    return cursor - 1


def _consume_table(lines: Sequence[_Line], index: int) -> int:
    cursor = index + 2
    while cursor < len(lines) and lines[cursor].text.strip() and "|" in lines[cursor].text:
        cursor += 1
    return cursor - 1


def _consume_blockquote(lines: Sequence[_Line], index: int) -> int:
    cursor = index + 1
    while cursor < len(lines):
        text = lines[cursor].text
        if not text.strip():
            if cursor + 1 < len(lines) and _BLOCKQUOTE_RE.match(lines[cursor + 1].text):
                cursor += 1
                continue
            break
        if _BLOCKQUOTE_RE.match(text) or not _is_block_start(text):
            cursor += 1
            continue
        break
    return cursor - 1


def _consume_html(lines: Sequence[_Line], index: int) -> int:
    opening = re.match(r"^ {0,3}<([A-Za-z][A-Za-z0-9-]*)\b", lines[index].text)
    if opening and not re.search(rf"</{re.escape(opening.group(1))}\s*>", lines[index].text, re.IGNORECASE):
        close_re = re.compile(rf"</{re.escape(opening.group(1))}\s*>", re.IGNORECASE)
        for cursor in range(index + 1, len(lines)):
            if close_re.search(lines[cursor].text):
                return cursor
    cursor = index + 1
    while cursor < len(lines) and lines[cursor].text.strip():
        cursor += 1
    return cursor - 1


def _extract_resources(block_id: str, text: str) -> Tuple[MarkdownInlineResourceV1, ...]:
    matches = []
    for match in _IMAGE_RE.finditer(text):
        destination = match.group(2) or match.group(3) or ""
        matches.append((match.group(1), destination, match.group(4)))
    for match in _HTML_IMAGE_RE.finditer(text):
        matches.append(("", match.group(1) or match.group(2) or "", None))
    resources = []
    for index, (alt, destination, title) in enumerate(matches):
        resources.append(
            MarkdownInlineResourceV1(
                resource_id=f"{block_id}:r{index}",
                alt=alt,
                destination=destination,
                title=title,
                loadable=False,
                placeholder=f"[image: {alt or 'unnamed'}]",
            )
        )
    return tuple(resources)


def _diagnostics(text: str, block_type: str, resources: Sequence[MarkdownInlineResourceV1]) -> Tuple[str, ...]:
    diagnostics: List[str] = []
    if block_type == "html":
        diagnostics.append("HTML_REQUIRES_SANITIZER")
    if _HOSTILE_SCRIPT_RE.search(text):
        diagnostics.extend(["HOSTILE_HTML_OR_JAVASCRIPT", "NO_ACTIVE_CONTENT_EXECUTION"])
    if any(resource.destination.lower().startswith("javascript:") for resource in resources):
        if "HOSTILE_HTML_OR_JAVASCRIPT" not in diagnostics:
            diagnostics.append("HOSTILE_HTML_OR_JAVASCRIPT")
        if "NO_ACTIVE_CONTENT_EXECUTION" not in diagnostics:
            diagnostics.append("NO_ACTIVE_CONTENT_EXECUTION")
    return tuple(dict.fromkeys(diagnostics))


def _build_blocks(
    lines: Sequence[_Line],
    *,
    document_id: str,
    sample_id: Optional[str],
) -> Tuple[MarkdownBlockProvenanceV1, ...]:
    blocks: List[MarkdownBlockProvenanceV1] = []
    heading_stack: List[Tuple[int, str]] = []
    index = 0
    block_prefix = sample_id or document_id
    while index < len(lines):
        if not lines[index].text.strip():
            index += 1
            continue

        heading = _heading_match(lines[index].text)
        setext_title = _setext_match(lines, index)
        if heading:
            block_type = "heading"
            end_index = index
            level, title = heading
            heading_title = title
        elif setext_title is not None:
            block_type = "heading"
            end_index = index + 1
            level = 1 if lines[index + 1].text.startswith("=") else 2
            heading_title = setext_title
        else:
            level = None
            heading_title = None
            fence = _FENCE_RE.match(lines[index].text)
            if fence:
                block_type = "code"
                end_index = _consume_fence(lines, index, fence)
            elif _is_table_start(lines, index):
                block_type = "table"
                end_index = _consume_table(lines, index)
            elif _LIST_RE.match(lines[index].text):
                block_type = "list"
                end_index = _consume_list(lines, index)
            elif _BLOCKQUOTE_RE.match(lines[index].text):
                block_type = "blockquote"
                end_index = _consume_blockquote(lines, index)
            elif _HORIZONTAL_RULE_RE.match(lines[index].text):
                block_type = "horizontal_rule"
                end_index = index
            elif _is_multiline_html_block(lines[index].text):
                block_type = "html"
                end_index = _consume_html(lines, index)
            else:
                block_type = "paragraph"
                end_index = index
                while end_index + 1 < len(lines) and lines[end_index + 1].text.strip():
                    if _setext_match(lines, end_index + 1) is not None or _is_block_start(lines[end_index + 1].text):
                        break
                    end_index += 1

        if len(blocks) >= _MAX_MARKDOWN_BLOCKS:
            raise MarkdownParseError(_MARKDOWN_BLOCK_LIMIT, code=_MARKDOWN_BLOCK_LIMIT)
        if heading_title is not None and level is not None:
            heading_stack = [(item_level, item_title) for item_level, item_title in heading_stack if item_level < level]
            heading_stack.append((level, heading_title))
        start = lines[index].start
        end = lines[end_index].end
        block_id = f"{block_prefix}:b{len(blocks)}"
        text = ""  # populated by caller after offsets are known
        # The caller replaces this temporary value using the normalized document.
        block = MarkdownBlockProvenanceV1(
            block_id=block_id,
            ordinal=len(blocks),
            text=text,
            start=start,
            end=end,
            start_line=lines[index].number,
            end_line=lines[end_index].number,
            heading_path=tuple(title for _, title in heading_stack),
            block_type=block_type,
        )
        blocks.append(block)
        index = end_index + 1
    return tuple(blocks)


def extract_markdown_provenance(
    source: Union[bytes, bytearray, memoryview, BinaryIO, os.PathLike, str],
    *,
    document_id: str = "markdown-document",
    sample_id: Optional[str] = None,
    source_sha256: Optional[str] = None,
) -> MarkdownSourceProvenanceV1:
    """Parse one Markdown source without rendering or loading external content."""
    raw = _read_source(source)
    digest = sha256(raw).hexdigest()
    if source_sha256 is not None:
        if not isinstance(source_sha256, str):
            raise MarkdownParseError(_SOURCE_HASH_INVALID, code=_SOURCE_HASH_INVALID)
        supplied = source_sha256.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", supplied):
            raise MarkdownParseError(_SOURCE_HASH_INVALID, code=_SOURCE_HASH_INVALID)
        if supplied != digest:
            raise MarkdownParseError(_SOURCE_HASH_MISMATCH, code=_SOURCE_HASH_MISMATCH)

    normalized, line_count = _decode_and_normalize(raw)
    if not normalized.strip():
        raise MarkdownParseError(_MARKDOWN_PARSE_FAILED, code=_MARKDOWN_PARSE_FAILED)
    lines = _make_lines(normalized)
    blocks = list(_build_blocks(lines, document_id=document_id, sample_id=sample_id))
    finalized: List[MarkdownBlockProvenanceV1] = []
    for block in blocks:
        text = normalized[block.start : block.end]
        if len(text.encode("utf-8")) > _MAX_MARKDOWN_BLOCK_BYTES:
            raise MarkdownParseError(_MARKDOWN_BLOCK_TOO_LARGE, code=_MARKDOWN_BLOCK_TOO_LARGE)
        resources = _extract_resources(block.block_id, text)
        diagnostics = _diagnostics(text, block.block_type, resources)
        finalized.append(
            MarkdownBlockProvenanceV1(
                block_id=block.block_id,
                ordinal=block.ordinal,
                text=text,
                start=block.start,
                end=block.end,
                start_line=block.start_line,
                end_line=block.end_line,
                heading_path=block.heading_path,
                block_type=block.block_type,
                inline_resources=resources,
                diagnostics=diagnostics,
            )
        )
    status = "partial" if any(
        "HOSTILE_HTML_OR_JAVASCRIPT" in block.diagnostics for block in finalized
    ) else "ready"
    error = _HOSTILE_MARKDOWN if status == "partial" else None
    return MarkdownSourceProvenanceV1(
        document_id=document_id,
        source_sha256=digest,
        normalized_text=normalized,
        blocks=tuple(finalized),
        status=status,
        error=error,
        sample_id=sample_id,
        line_count=line_count,
    )
