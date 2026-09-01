"""文本清洗层与参考文献定位（spec-012）。

论文 PDF 由 LaTeX 排版，`get_text` 提取后残留两种噪声：
- 行末连字符断词（hyphenation）：`proce-\ndural`
- 段落内硬换行：句子未结束就换行（每行末尾都是 `\n`）

本模块提供**纯函数**，无网络、无文件 IO，便于单测：
- `normalize_text`：合并断词、把软换行转空格，同时保护列表/参考文献等结构行。
- `locate_reference_start`：定位「参考文献」起始页（1-based）。
- `detect_citation`：保守判定某页文本是否为参考文献条目区。

已知局限（012-tech-review T5）：LaTeX 把复合词折行（如 `state-\nof`）
会被合并成 `stateof`，无法与真断词区分，此为固有局限，不追求消除。
"""

import re
from typing import List, Optional, Sequence, Tuple

# 规则 1：行末连字符断词 —— 仅命中「词-换行-词」，行内真连字符中间无 \n，不受影响。
_HYPHEN_BREAK = re.compile(r"(?<=\w)-\n(?=\w)")

# 规则 3：结构行 —— 这些行开头的换行必须保留（列表 / 参考文献条目 / 编号小节）。
_STRUCT_PREFIX = re.compile(r"^(\s*)(\[\d+\]|\[[\d,\s]+\]|[\u2022\u2219\*\-]|\d+\.)\s")

# 全大写短标题行（长度限制，避免把整句全大写误判为标题）。
_UPPERCASE_HEADING_MAX_LEN = 48

# 句末标点：上一行以这些结尾时，换行保留（自然断句）。
_SENTENCE_END = ".!?;:"

# 连续空白（不含换行）折叠为单空格。
_WHITESPACE_RUN = re.compile(r"[ \t\r]+")

# 参考文献小节标题（独立成行，允许数字编号前缀，忽略大小写）。
_REFERENCE_HEADING = re.compile(
    r"^\s*(?:\d+\.?\s+)?(references|bibliography|works\s+cited|参考文献)\s*$",
    re.IGNORECASE,
)

# 参考文献条目行：以 [数字] 或 [数字,数字] 开头。
_REF_ENTRY = re.compile(r"^\[(\d+(?:\s*,\s*\d+)*)\]")

# 特征词：命中种类数超阈值即视为参考文献区。
# 说明：年份写成 `\b(19|20)\d{2}\b`（不强制括号），因参考文献年份常作 ", 2023,"；
# 会议名写成 `\bin\s+[A-Z]{2,}\b`（in + 全大写缩写，如 ICML），覆盖 in-会议/缩写形态。
_CITATION_FEATURES = [
    re.compile(r"arXiv:", re.IGNORECASE),
    re.compile(r"\bet\s+al\."),
    re.compile(r"\bin\s+proceedings of", re.IGNORECASE),
    re.compile(r"\bin\s+[A-Z]{2,}\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
]

# 特征词命中阈值。
_CITATION_FEATURE_THRESHOLD = 3


def _is_structural_line(line: str) -> bool:
    """判断一行是否为结构行（列表项 / 参考文献条目 / 编号小节 / 全大写短标题）。"""
    content = line.strip()
    if not content:
        return False
    if _STRUCT_PREFIX.match(line):
        return True
    if (
        len(content) <= _UPPERCASE_HEADING_MAX_LEN
        and content.isupper()
        and any(ch.isalpha() for ch in content)
    ):
        return True
    return False


def _rejoin_lines(lines: List[str], ref_zone: bool = False) -> str:
    """把块内的物理行按规则合并。

    分隔符依据**当前行**与**上一行**判定：
    - 当前行是结构行（列表项 / 参考文献条目 / 编号小节 / 全大写短标题）→ 保留换行；
    - 上一行以句末标点结尾（`. ! ? : ;`）→ 保留换行（自然断句）；
    - 其余视为段落内硬换行 → 转空格。

    `ref_zone=True`（参考文献区内）时改用更宽松的规则：
    **只有新条目（`[数字]` 开头）才换行，其余一律合并**。
    原因：参考文献标题常含行末冒号（如 `...pixelated sheep:`），
    按句末标点保留换行会把同一条目切成两半，问参考文献时会召回到半截内容。
    """
    parts: List[str] = []
    for raw_line in lines:
        segment = raw_line.strip()
        if not segment:
            continue
        if parts:
            prev = parts[-1]
            if ref_zone:
                separator = "\n" if _REF_ENTRY.match(segment) else " "
            else:
                separator = (
                    "\n"
                    if _is_structural_line(raw_line) or (prev and prev[-1] in _SENTENCE_END)
                    else " "
                )
            parts.append(separator)
        parts.append(segment)
    return "".join(parts)


def normalize_text(raw: str, *, ref_zone: bool = False) -> str:
    """清洗 LaTeX 排版噪声：合并断词、软换行转空格，保护结构行与段落边界。

    `ref_zone=True` 时按参考文献区规则合并（仅新条目换行，见 `_rejoin_lines`）。
    """
    if not raw:
        return ""

    text = _HYPHEN_BREAK.sub("", raw)

    # 按空行切分成块：空行是段落边界，块间用 \n\n 连接，块内换行逐行决策。
    normalized_blocks: List[str] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        joined = _rejoin_lines(block.split("\n"), ref_zone=ref_zone)
        joined = _WHITESPACE_RUN.sub(" ", joined).strip()
        if joined:
            normalized_blocks.append(joined)

    return "\n\n".join(normalized_blocks).strip()


def locate_reference_start(pages: Sequence[Tuple[int, str]]) -> Optional[int]:
    """定位「参考文献」起始页（1-based），找不到返回 None。"""
    for page, text in pages:
        for line in text.split("\n"):
            if _REFERENCE_HEADING.match(line):
                return int(page)
    return None


def detect_citation(text: str, page: int, *, ref_start_page: Optional[int]) -> bool:
    """保守判定某页文本是否为参考文献条目区。

    - 未定位到参考文献区（ref_start_page 为 None）→ 一律不判为 citation。
    - 位于起始页之前 → 不判为 citation。
    - 起始页之后：`^[数字]` 条目 ≥ 2，或特征词命中 ≥ 阈值 → citation。
    """
    if ref_start_page is None:
        return False
    if page < ref_start_page:
        return False

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    entry_count = sum(1 for line in lines if _REF_ENTRY.match(line))
    if entry_count >= 2:
        return True

    feature_hits = 0
    for pattern in _CITATION_FEATURES:
        for line in lines:
            if pattern.search(line):
                feature_hits += 1
                break
    return feature_hits >= _CITATION_FEATURE_THRESHOLD
