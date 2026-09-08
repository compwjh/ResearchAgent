"""切分器（spec-012）。

两个版本共用清洗后的文本（来自 `normalize.normalize_text`）：

- **v1**（`build_chunks_v1`）：spec-011 的逐页递归切分，**行为与迁移前完全一致**，
  仅从 `parse.py` 迁来以便与 v2 并列管理。逐页切分、**不跨页合并**。
- **v2**（`build_chunks_v2`）：结构感知切分。
  1. 按空行切 blocks（自然段落），**每个 block 携带自己的页码**；
  2. **规则预筛**：编号小节、`Abstract`/`References` 等章节名、全大写短标题、
     表格/图题、参考文献条目 → 直接判为边界，不消耗 LLM 调用；
  3. **LLM 批量判定**：把规则没判定的候选分批（默认 8 个/批）问
     `CHUNK_V2_LLM_MODEL`，只让模型回答"哪些编号是新结构体开始"；
  4. **固定上限合并**：同一结构体内连续 blocks 在 `CHUNK_V2_MAX_CHARS` 内合并，
     单个结构体超上限则按句子再切，**硬上限不得突破**；
  5. **跨章节绝不合并**，但 v2 **允许跨页合并**（v1 不允许），
     此时 `page` 记起始页、`page_end` 记结束页。

**降级策略（重要）**：LLM 不可用 / 超时 / 返回不可解析时，只用规则边界生成 v2，
**不抛异常、不阻塞上传**；是否用到 LLM 由返回的 `llm_used` 告知调用方。

LLM 由外部注入（`llm` 可调用对象，`llm(prompt) -> str`），便于单测 mock；
默认实现见 `ollama_boundary_judge`。
"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import httpx

from backend.app.platform.config import (
    CHUNK_V2_LLM_BATCH,
    CHUNK_V2_LLM_MODEL,
    CHUNK_V2_LLM_TIMEOUT,
    CHUNK_V2_MAX_CHARS,
    OLLAMA_BASE_URL,
)

# v1 递归切分的分隔符（按此顺序降级）。
_SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]

# v2 规则预筛：编号小节（1 / 1.1 / 3.2.1 后紧跟标题文字）。
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")

# v2 规则预筛：论文常见章节名（独立成行，可带冒号/句号）。
_KNOWN_SECTION = re.compile(
    r"^(abstract|introduction|related work|background|method(ology)?|approach|"
    r"experiment(s|al setup)?|results?|discussion|conclusion|limitations?|"
    r"future work|acknowledg(e)?ments?|references|bibliography|appendix)\s*[:.]?\s*$",
    re.IGNORECASE,
)

# v2 规则预筛：表格 / 图 / 算法题注（这些是独立结构体，标题常以句号结尾）。
_TABLE_FIGURE = re.compile(r"^(table|figure|fig\.|algorithm|tab\.)\s*\d*[:.]?", re.IGNORECASE)

# v2 规则预筛：参考文献条目行 `[1]` / `[1, 2]`。
_REF_ENTRY = re.compile(r"^\[\d+(?:\s*,\s*\d+)*\]")

# v2 规则预筛：标题行最大长度，超过则不当标题（避免把整段正文当小节）。
_HEADING_MAX_LEN = 80

# 句末标点：以这些结尾的行多为正文首句而非标题（表格/图题除外）。
_SENTENCE_END = ".!?;:。！？；："

# v2 句子边界（中英混合），用于把超上限的结构体按句子再切。
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")

# LLM 回复里提取编号列表（形如 [1, 4] / [] ）。
_LLM_NUMBERS = re.compile(r"\[([^\]]*)\]")

# 送给 LLM 的上下文长度上限（前块尾部 / 当前块 / 后块开头）。
_CONTEXT_PREV = 60
_CONTEXT_SELF = 160
_CONTEXT_NEXT = 40


class BoundaryLLMError(RuntimeError):
    """LLM 结构分析失败（不可达、超时、返回结构异常或空内容）。"""


@dataclass
class Chunk:
    """一个切片。

    `page_end` / `section` 是 spec-012 为 v2 新增的字段，均带默认值，
    保证既有 `Chunk(text=..., page=..., chunk_index=...)` 写法不被破坏。
    """

    text: str
    page: Optional[int]
    chunk_index: int
    page_end: Optional[int] = 0
    section: str = ""

    def __post_init__(self) -> None:
        # Markdown provenance intentionally carries null page coordinates.
        # Preserve that contract instead of coercing null to page 0.
        if self.page is None:
            self.page_end = None
            return
        if self.page_end is None:
            return
        # 页码从 1 开始，故用 <=0 判断"未显式指定"。
        if not self.page_end or int(self.page_end) <= 0:
            self.page_end = int(self.page)


# ---------------------------------------------------------------------------
# v1：spec-011 的递归切分，行为零变更
# ---------------------------------------------------------------------------


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


def build_chunks_v1(
    pages: Sequence[Tuple[Optional[int], str]],
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Chunk]:
    """逐页切片：不跨页合并，保证引用页码准确。"""
    chunks: List[Chunk] = []
    for page, text in pages:
        if not text:
            continue
        for piece in split_text(text, chunk_size, overlap):
            chunks.append(Chunk(text=piece, page=page, chunk_index=len(chunks)))
    return chunks


# ---------------------------------------------------------------------------
# v2：结构感知切分
# ---------------------------------------------------------------------------


def build_chunks_v2(
    pages: Sequence[Tuple[Optional[int], str]],
    *,
    max_chars: Optional[int] = None,
    llm: Optional[Callable[[str], str]] = None,
    progress: Optional[Callable[[int], None]] = None,
) -> Tuple[List[Chunk], bool]:
    """结构感知切分：规则预筛 + LLM 判定边界 + 固定上限合并。

    - `max_chars`：chunk 硬上限，默认取 `CHUNK_V2_MAX_CHARS`。
    - `llm`：可调用对象 `llm(prompt) -> str`；为 `None` 时纯规则切分。
      调用失败/超时/返回不可解析 → 降级为纯规则切分，**不抛异常**。
    - `progress`：`Callable[[int], None]`，接收本函数**自身**的 0-100 相对进度
      （分块 10、LLM 阶段 10→70、分组合并 70→100）；由调用方映射到全局区间。

    返回 `(chunks, llm_used)`：`llm_used=False` 表示该次结果由降级产出。
    """
    limit = max(1, int(max_chars or CHUNK_V2_MAX_CHARS))
    _report(progress, 0)

    # 阶段 1：分块（每个 block 记住自己的页码，后续 page_end 才能准确）
    blocks = _to_blocks(pages)
    if not blocks:
        _report(progress, 100)
        return [], False

    # 阶段 2：规则预筛（不消耗 LLM 调用）
    boundaries = _rule_boundaries(blocks)
    _report(progress, 10)

    # 阶段 3：把规则没判定的候选批量送 LLM
    llm_used = False
    if llm is not None:
        llm_used = _judge_by_llm(blocks, boundaries, llm, progress)
    _report(progress, 70)

    # 阶段 4：按边界分组 → 上限内合并 → 产出 chunk
    chunks: List[Chunk] = []
    for group in _group_by_boundary(blocks, boundaries):
        page = group[0][0]
        page_end = group[-1][0]
        section = _heading_of(group[0][1]) or ""
        for piece in _pack_blocks([block[1] for block in group], limit):
            chunks.append(
                Chunk(
                    text=piece,
                    page=page,
                    chunk_index=len(chunks),
                    page_end=page_end,
                    section=section,
                )
            )
    _report(progress, 100)
    return chunks, llm_used


def _to_blocks(pages: Sequence[Tuple[Optional[int], str]]) -> List[Tuple[Optional[int], str]]:
    """把清洗后的页文本按空行切成 blocks，并保留各自页码。"""
    blocks: List[Tuple[int, str]] = []
    for page, text in pages:
        for raw in (text or "").split("\n\n"):
            block = raw.strip()
            if block:
                blocks.append((int(page), block))
    return blocks


def _heading_of(block_text: str) -> Optional[str]:
    """规则预筛：命中明确结构信号则返回该块文本（可作 section 标题），否则 None。

    覆盖：参考文献条目、表格/图/算法题注、编号小节（`1. Introduction`、
    `3.2 Method`）、章节关键词行、全大写短标题（`ABSTRACT`）。
    以句末标点结尾的行多为正文首句，不作为标题（表格/图题除外）。
    """
    content = (block_text or "").strip()
    if not content:
        return None
    if _REF_ENTRY.match(content):
        return content
    if _TABLE_FIGURE.match(content):
        return content
    if len(content) > _HEADING_MAX_LEN or content[-1] in _SENTENCE_END:
        return None
    if _NUMBERED_HEADING.match(content):
        return content
    if _KNOWN_SECTION.match(content):
        return content
    if content.isupper() and any(ch.isalpha() for ch in content):
        return content
    return None


def _rule_boundaries(blocks: Sequence[Tuple[int, str]]) -> List[int]:
    """规则预筛出的边界下标。首个 block 恒为边界（其后才有内容可合并）。"""
    return [
        index
        for index, (_, text) in enumerate(blocks)
        if index == 0 or _heading_of(text) is not None
    ]


def _judge_by_llm(
    blocks: Sequence[Tuple[int, str]],
    boundaries: List[int],
    llm: Callable[[str], str],
    progress: Optional[Callable[[int], None]],
) -> bool:
    """把规则未判定的候选批量送 LLM；任何异常都只放弃 LLM 阶段，不抛出。

    返回是否**成功解析并采用** LLM 结果（合法空列表也算 True）。
    不修改调用方持有的其它状态；失败时 `boundaries` 仅含规则结果。
    """
    rule_set = set(boundaries)
    candidates = [
        index for index in range(len(blocks)) if index not in rule_set and blocks[index][1]
    ]
    if not candidates:
        return False

    batch_size = max(1, int(CHUNK_V2_LLM_BATCH))
    total = len(candidates)
    proposed_boundaries: List[int] = []
    for start in range(0, total, batch_size):
        batch = candidates[start : start + batch_size]
        try:
            reply = llm(_build_prompt(blocks, batch))
        except Exception:
            # 单次失败即放弃整个 LLM 阶段（27B 慢，重试会拖垮上传）
            return False
        parsed = _parse_verdicts_result(reply, len(batch))
        if parsed is None:
            return False
        for offset in parsed:
            proposed_boundaries.append(batch[offset])
        _report(progress, 10 + int(60 * (start + len(batch)) / total))
    boundaries.extend(proposed_boundaries)
    return True


def _group_by_boundary(
    blocks: Sequence[Tuple[int, str]],
    boundaries: Sequence[int],
) -> List[List[Tuple[int, str]]]:
    """按边界把 blocks 分组；**跨边界绝不合并**。"""
    boundary_set = set(boundaries)
    groups: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    for index, block in enumerate(blocks):
        if index in boundary_set and current:
            groups.append(current)
            current = []
        current.append(block)
    if current:
        groups.append(current)
    return groups


def _pack_blocks(texts: Sequence[str], limit: int) -> List[str]:
    """同一结构体内连续 blocks 在硬上限内合并；超限则按句子再切。

    顺序一次性推进，**不会产出重复内容**（每个 block 只归属一个 piece）。
    """
    pieces: List[str] = []
    buffer = ""
    for text in texts:
        candidate = f"{buffer}\n\n{text}" if buffer else text
        if len(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            pieces.append(buffer)
            buffer = ""
        if len(text) <= limit:
            buffer = text
            continue
        # 单个 block 就超上限：按句子切，仍超限则硬切，保证硬上限不被突破。
        sub_pieces = _split_by_sentence(text, limit)
        if sub_pieces:
            pieces.extend(sub_pieces[:-1])
            buffer = sub_pieces[-1]
    if buffer:
        pieces.append(buffer)
    return [piece for piece in pieces if piece.strip()]


def _split_by_sentence(text: str, limit: int) -> List[str]:
    """按句子边界切分，尽量让每片贴近但不超过 `limit`。

    切不动时（无句子边界）直接硬切，**不递归**，避免无限递归。
    """
    if len(text) <= limit:
        return [text]
    parts = [part for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
    if len(parts) <= 1:
        # 没有任何句子边界（如长表格 / 无标点串）：硬切，必须守住上限。
        return [text[index : index + limit] for index in range(0, len(text), limit)]

    pieces: List[str] = []
    buffer = ""
    for part in parts:
        candidate = f"{buffer} {part}" if buffer else part
        if len(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            pieces.append(buffer)
            buffer = ""
        if len(part) <= limit:
            buffer = part
        else:
            # 单个"句子"仍超上限：硬切
            pieces.extend(part[index : index + limit] for index in range(0, len(part), limit))
    if buffer:
        pieces.append(buffer)
    return [piece for piece in pieces if piece.strip()]


def _build_prompt(blocks: Sequence[Tuple[int, str]], batch: Sequence[int]) -> str:
    """构造边界判定 prompt。

    编号**严格按批内 1-based**（1..len(batch)），与 `_parse_verdicts` 的解析口径一致；
    若用全局编号，第二批次起会整体错位导致判定失效。
    """
    lines = [
        "下列编号取自一篇论文清洗后的正文，是按阅读顺序排列的候选段落，"
        "每段给出前块尾部、本段开头与后块开头作为上下文。",
        "",
    ]
    for offset, index in enumerate(batch, start=1):
        previous = blocks[index - 1][1] if index > 0 else ""
        following = blocks[index + 1][1] if index + 1 < len(blocks) else ""
        tail = previous[-_CONTEXT_PREV:].replace("\n", " ") if previous else "(全文开始)"
        head = following[:_CONTEXT_NEXT].replace("\n", " ") if following else "(全文结束)"
        snippet = blocks[index][1][:_CONTEXT_SELF].replace("\n", " ")
        lines.append(f"[{offset}] 前文结尾：{tail}")
        lines.append(f"     本段开头：{snippet}")
        lines.append(f"     后文开头：{head}")
        lines.append("")
    lines.append(
        "请判断哪些编号标志着一个『新结构体的开始』"
        "（新的章节 / 小节 / 表格 / 图 / 算法 / 参考文献区域的起点）。"
    )
    lines.append("只输出命中编号的列表，形如 [1, 4]；若都不算，输出 []。不要输出其他文字。")
    return "\n".join(lines)


def _parse_verdicts(raw: str, size: int) -> List[int]:
    """解析 LLM 回复为**批内 0-based** 下标列表；越界/重复/不可解析一律丢弃。

    保守原则：解析不出就不新增边界（宁可少切，不可乱切）。
    """
    parsed = _parse_verdicts_result(raw, size)
    return [] if parsed is None else parsed


def _parse_verdicts_result(raw: str, size: int) -> Optional[List[int]]:
    """Return parsed offsets, or ``None`` when the response is not parseable.

    ``[]`` is a valid LLM decision and must remain distinguishable from a
    transport/protocol failure so callers can report ``llm_used`` accurately.
    """
    text = (raw or "").strip()
    if not text:
        return None
    match = _LLM_NUMBERS.search(text)
    if not match:
        return None
    content = match.group(1).strip()
    if not content:
        return []
    offsets: List[int] = []
    for token in re.split(r"[,，\s]+", content):
        token = token.strip()
        if not token.isdigit():
            return None
        offset = int(token) - 1  # 批内编号是 1-based
        if not 0 <= offset < size:
            return None
        if offset not in offsets:
            offsets.append(offset)
    return offsets


def _report(progress: Optional[Callable[[int], None]], value: int) -> None:
    """进度回调；回调自身抛错绝不能影响主流程。"""
    if progress is None:
        return
    try:
        progress(max(0, min(100, int(value))))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 默认 LLM 实现
# ---------------------------------------------------------------------------


def ollama_boundary_judge(
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> str:
    """默认 LLM 实现：调本地 Ollama `/api/chat`，返回模型回复文本。

    `think: false` **不可删除**：`CHUNK_V2_LLM_MODEL` 是 thinking 模型，
    不关思考会耗尽输出预算导致 `content` 为空（项目已踩过此坑）。
    失败直接抛 `BoundaryLLMError`，由 `build_chunks_v2` 捕获后降级。
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": model or CHUNK_V2_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2},
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=float(timeout or CHUNK_V2_LLM_TIMEOUT),
            trust_env=False,
        )
    except httpx.HTTPError as error:
        raise BoundaryLLMError(f"无法连接 Ollama：{error}") from error

    if response.status_code != 200:
        detail = ""
        try:
            detail = str(response.json().get("error", ""))
        except ValueError:
            detail = response.text[:200]
        raise BoundaryLLMError(f"Ollama 结构分析失败（HTTP {response.status_code}）{detail}")

    try:
        content = (response.json().get("message") or {}).get("content") or ""
    except ValueError as error:
        raise BoundaryLLMError("Ollama 返回非 JSON") from error
    if not content.strip():
        raise BoundaryLLMError("Ollama 返回空内容（可能是思考未关闭）")
    return content
