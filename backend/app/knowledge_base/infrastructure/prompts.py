"""RAG 提示词与引用构建（spec-011）。"""

from typing import List


def _page_label(hit) -> str:
    """出处页码文案（spec-012）：跨页片段显示 `第 3-4 页`，单页仍为 `第 3 页`。"""
    start = int(getattr(hit, "page", 0) or 0)
    end = int(getattr(hit, "page_end", 0) or 0)
    if end and end > start:
        return f"第 {start}-{end} 页"
    return f"第 {start} 页"


def build_context(hits) -> str:
    """把命中片段拼成带编号与出处的上下文。"""
    blocks = []
    for position, hit in enumerate(hits, start=1):
        blocks.append(f"[{position}] 来源：{hit.file_name} {_page_label(hit)}\n{hit.text}")
    return "\n\n".join(blocks)


def build_prompt(question: str, hits) -> str:
    context = build_context(hits)
    return (
        "你是一个严谨的论文助手。请只依据下列来自用户个人知识库的上下文回答问题。\n"
        "要求：\n"
        "1. 引用时使用 [编号]，编号与上下文中的片段一一对应；\n"
        "2. 不要编造上下文中没有的信息；\n"
        "3. 若上下文不足以回答，直接说明“知识库中没有足够信息”，并指出还缺什么。\n\n"
        f"上下文：\n{context}\n\n问题：{question}\n回答："
    )


def citation_payloads(hits: List) -> List[dict]:
    return [
        {
            "file_name": hit.file_name,
            "page": hit.page,
            # spec-012：v2 跨页合并片段的结束页，前端据此显示 `p.3-4`
            "page_end": int(getattr(hit, "page_end", 0) or 0) or int(hit.page or 0),
            "chunk_index": hit.chunk_index,
            "paper_id": hit.paper_id,
            "score": round(hit.score, 6),
            "text": hit.text,  # 供前端点击引用后展开原文片段
        }
        for hit in hits
    ]
