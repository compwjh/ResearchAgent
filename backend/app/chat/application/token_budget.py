"""Spec025：全链路唯一的 token 计量实现（无 tokenizer 依赖）。

换算系数 CHARS_PER_TOKEN 采用「中英混排保守口径」：1 token ≈ 1.6 字符。
真 token 只从 ``platform/ollama_direct.py`` 回读做观测，本模块不引入 tiktoken 等依赖。
全仓库只允许此文件一处做 chars↔tokens 换算（替换 repository.py 旧有的 ``token_budget * 4`` 英文口径）。
"""
from __future__ import annotations

import math

# 中英混排保守估算系数：1 token ≈ 1.6 字符（替换旧 ``* 4`` 英文口径，旧口径与真实用量偏差可达 2 倍）。
CHARS_PER_TOKEN: float = 1.6


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数：``chars / CHARS_PER_TOKEN`` 向上取整。

    空串或 ``None`` 返回 0。全链路唯一实现，禁止在别处重复换算。
    """
    return math.ceil(len(text or "") / CHARS_PER_TOKEN)


def chars_for_tokens(tokens: int) -> int:
    """tokens → chars 的逆换算：``max(0, int(tokens)) * CHARS_PER_TOKEN`` 向下取整。

    供既有按 token 传参的调用点（如 ``repository.list_recall_context`` 的 ``token_budget``）复用，
    使「1 token ≈ ? 字符」的口径与 :func:`estimate_tokens` 收敛到同一系数。
    """
    return int(max(0, int(tokens)) * CHARS_PER_TOKEN)
