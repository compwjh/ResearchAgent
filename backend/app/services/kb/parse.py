"""PDF 解析与切片（spec-011 / spec-012）。

- `pymupdf` 按页提取，保留 1-based 页码，用于回答引用。
- **切分逻辑已迁至 `chunkers.py`**（spec-012 第 3 项）：`Chunk` / `split_text` /
  `build_chunks_v1` 均从那里 re-export 或委派；本模块只负责 PDF 抽取。
  `build_chunks` 保留为 `build_chunks_v1` 的委派别名（name 不变，v1 行为零变更）。
- 清洗层（spec-012）：`extract_pages_normalized` 在抽取后套一层
  `normalize_text`，合并行末断词、把段落内硬换行转空格，保护列表/参考文献
  等结构行，提升召回文本可读性；`extract_pages` 保留原始行为不变（供单测/排查）。
"""

from typing import List, Tuple

from backend.app.services.kb.chunkers import (
    Chunk,
    build_chunks_v1,
    split_text,
)
from backend.app.services.kb.normalize import locate_reference_start, normalize_text

__all__ = [
    "Chunk",
    "PdfParseError",
    "build_chunks",
    "build_chunks_v1",
    "extract_pages",
    "extract_pages_normalized",
    "split_text",
    "total_chars",
]


class PdfParseError(RuntimeError):
    """PDF 无法解析（加密、损坏、无页面）。"""


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


def extract_pages_normalized(path) -> List[Tuple[int, str]]:
    """在 `extract_pages` 基础上对每页文本套 `normalize_text` 清洗（spec-012）。

    返回结构同 `extract_pages`：`[(页码, 清洗后文本)]`，页码 1-based。
    **参考文献页（`page >= locate_reference_start`）传 `ref_zone=True`**：
    该模式下只有新条目（`[数字]` 开头）才保留换行，避免条目被标题里的
    行末冒号切成两半（详见 `normalize._rejoin_lines`）。
    清洗后空白的页跳过；原 `extract_pages` 保持不变，供单测与排查使用。
    """
    pages = extract_pages(path)
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
