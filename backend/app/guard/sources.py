"""外部内容来源区分与有界窗口（Spec050 VIGIL 线 / Task03）。

网页、PDF、工具结果、历史记忆与模型生成文字都不能授予或扩大动作权限。
本模块只负责给它们打来源标识并按官方推理口径切成有界窗口，
**不**做 PIGuard 推理（属另一条开发线的 Task08）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.app.guard.signals import SOURCE_KINDS

MAX_WINDOW_TOKENS = 256
MAX_WINDOWS = 64
UNTRUSTED_KINDS = frozenset(SOURCE_KINDS)


@dataclass(frozen=True)
class ExternalWindow:
    source_kind: str
    source_ref: str
    window_index: int
    window_count: int
    text: str
    truncated: bool

    def signal_kwargs(self) -> dict[str, object]:
        """交给 PIGuard 接入方填充 label/score/model_version 后调用 signals.report。"""
        return {
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "window_index": self.window_index,
            "window_count": self.window_count,
            "truncated": self.truncated,
            "uncovered_windows": 0,
        }


def source_ref(source_kind: str, document_id: str, *, locator: str = "") -> str:
    """脱敏来源定位：不含原文、URL 或凭据。"""
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source_kind: {source_kind}")
    digest = hashlib.sha256(f"{document_id}:{locator}".encode("utf-8")).hexdigest()[:12]
    return f"{source_kind}:{digest}"


def split_windows(text: str, *, source_kind: str, document_id: str,
                  locator: str = "", max_tokens: int = MAX_WINDOW_TOKENS,
                  max_windows: int = MAX_WINDOWS) -> tuple[list[ExternalWindow], int]:
    """按字符近似 token 切成有界窗口；返回 (窗口列表, 未覆盖窗口数)。

    官方口径单窗口最多 256 token。这里用 `max_tokens * 4` 字符做保守上界，
    避免在本层引入 tokenizer 依赖；真实 token 数由 PIGuard 接入方复核，
    超出时由对方置 `truncated=True` 并上报。
    """
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source_kind: {source_kind}")
    limit = max(1, int(max_tokens)) * 4
    chunks = [text[i:i + limit] for i in range(0, len(text), limit)] if text else []
    covered = chunks[:max(1, int(max_windows))]
    uncovered = max(0, len(chunks) - len(covered))
    ref = source_ref(source_kind, document_id, locator=locator)
    return [
        ExternalWindow(
            source_kind=source_kind,
            source_ref=ref,
            window_index=index,
            window_count=len(covered),
            text=chunk,
            truncated=len(chunk) >= limit,
        )
        for index, chunk in enumerate(covered)
    ], uncovered


def can_grant_authority(source_kind: str) -> bool:
    """来源能否授予或扩大权限：永远不能。保留函数以便调用点显式表达。"""
    return False


def is_untrusted(source_kind: str) -> bool:
    return source_kind in UNTRUSTED_KINDS
