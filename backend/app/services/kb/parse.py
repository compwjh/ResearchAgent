"""PDF 解析与切片（spec-011）。

- `pymupdf` 按页提取，保留 1-based 页码，用于回答引用。
- 自研递归切分器，不引入 `langchain-text-splitters`（见 011-tech-review R6）。
"""

from dataclasses import dataclass
from typing import List, Tuple

_SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]


class PdfParseError(RuntimeError):
    """PDF 无法解析（加密、损坏、无页面）。"""


@dataclass
class Chunk:
    text: str
    page: int
    chunk_index: int


def extract_pages(path) -> List[Tuple[int, str]]:
    """返回 [(页码, 该页纯文本)]，页码从 1 开始。"""
    import pymupdf

    try:
        document = pymupdf.open(str(path))
    except Exception as error:  # pymupdf 对损坏文件抛各类异常
        raise PdfParseError(f"无法打开 PDF：{error}") from error
    try:
        if document.is_encrypted and not document.authenticate(""):
            raise PdfParseError("PDF 已加密，无法提取文本")
        if document.page_count == 0:
            raise PdfParseError("PDF 没有任何页面")
        return [
            (number, (page.get_text("text") or "").strip())
            for number, page in enumerate(document, start=1)
        ]
    finally:
        document.close()


def total_chars(pages) -> int:
    return sum(len(text) for _, text in pages)


def split_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """按分隔符递归降级切分，重叠保留上下文。"""
    content = (text or "").strip()
    if not content:
        return []
    if len(content) <= chunk_size:
        return [content]
    return _apply_overlap(_split_recursive(content, chunk_size, overlap, 0), chunk_size, overlap)


def _split_recursive(text: str, size: int, overlap: int, level: int) -> List[str]:
    if len(text) <= size:
        return [text]
    if level >= len(_SEPARATORS):
        step = max(1, size - overlap)
        return [text[index : index + size] for index in range(0, len(text), step)]

    separator = _SEPARATORS[level]
    pieces = [piece for piece in text.split(separator) if piece]
    chunks: List[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{separator}{piece}" if current else piece
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(piece) > size:
            sub_chunks = _split_recursive(piece, size, overlap, level + 1)
            if sub_chunks:
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1]
        else:
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _apply_overlap(chunks: List[str], size: int, overlap: int) -> List[str]:
    if len(chunks) <= 1 or overlap <= 0:
        return chunks
    merged: List[str] = []
    for index, chunk in enumerate(chunks):
        if index == 0:
            merged.append(chunk)
            continue
        tail = chunks[index - 1][-overlap:]
        candidate = f"{tail}{chunk}"
        merged.append(candidate if len(candidate) <= size else chunk)
    return merged


def build_chunks(pages, chunk_size: int = 1000, overlap: int = 200) -> List[Chunk]:
    """逐页切片：不跨页合并，保证引用页码准确。"""
    chunks: List[Chunk] = []
    for page, text in pages:
        if not text:
            continue
        for piece in split_text(text, chunk_size, overlap):
            chunks.append(Chunk(text=piece, page=page, chunk_index=len(chunks)))
    return chunks
