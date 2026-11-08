"""spec-045 Task 06：统一值级凭据过滤与 ``raw_events.payload`` 上限。

三套写入路径共用本模块，消除 F12 的脱敏口径冲突：

- Langfuse 上报（``spans.py``）
- 自建 ``raw_events``（``memory/repository.py``）
- 路由观测 / SSE 错误摘要（``spans.py``、``routes_conversations.py``）

边界（spec-041 用户裁决）：**只替换精确凭据模式，不清空、不整段脱敏 prompt**；
不按 ``token`` 之类宽泛关键字过滤，避免误伤正常的学术文本。
URL 整段替换为 ``[REDACTED]``（含 userinfo / query 凭据），与 ``research_store``
既有的 ``_safe_event_value`` 口径一致；本模块**不改** ``research_events`` 的
``safe_payload`` 白名单形状与 SSE 事件协议。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

REDACTED = "[REDACTED]"
REQUEST_ID_KEY = "request_id"
TRUNCATED_KEY = "truncated"

# 与 repository 既有 _PROCESSING_DETAIL_MAX_CHARS 同口径，避免出现第二套额度。
MAX_RAW_EVENT_PAYLOAD_CHARS = 4000

# —— 精确凭据模式（结构化匹配，不是宽泛关键字）——
# OpenAI 类 API key：sk-proj-xxxx / sk-xxxx
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")
# Authorization: Bearer <token>（保留 Bearer 前缀，与 research_store 一致）
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=\-]+")
# Authorization: <token>（非 Bearer 形式）
_AUTHORIZATION_RE = re.compile(r"(?i)\b(Authorization\s*:\s*)[^\s,;]+")
# 显式凭据字段赋值（与 research_events 既有值级脱敏同口径）
_CREDENTIAL_ASSIGN_RE = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|token|secret|password|cookie)\s*[:=]\s*)[^\s,;]+"
)
# URL（含 userinfo 与 query 中的凭据），与 research_events 既有值级脱敏同口径
_URL_RE = re.compile(r"(?i)\bhttps?://[^\s,;\"'<>]+")


def redact_text(text: str) -> str:
    """替换字符串值里的精确凭据片段，其余文本逐字保留。

    顺序有意为之：先整体替换 URL（避免 URL 内的 userinfo / query 被后续规则
    切碎后残留），再处理 Bearer / Authorization / sk- key / 显式凭据赋值。
    """
    if not text:
        return text
    cleaned = _URL_RE.sub(REDACTED, text)
    cleaned = _BEARER_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", cleaned)
    cleaned = _AUTHORIZATION_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", cleaned)
    cleaned = _SK_KEY_RE.sub(REDACTED, cleaned)
    cleaned = _CREDENTIAL_ASSIGN_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", cleaned)
    return cleaned


def redact_value(value: Any, *, depth: int = 0) -> Any:
    """递归做值级过滤：只改字符串值，保留 dict / list 结构与其它标量。"""
    if depth > 6:
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item, depth=depth + 1) for item in value]
    return value


def redact_payload(payload: dict) -> dict:
    """``raw_events.payload`` / 观测 metadata 共用的值级过滤入口。"""
    cleaned = redact_value(payload)
    return cleaned if isinstance(cleaned, dict) else {}


def with_request_id(payload: dict, request_id: str) -> dict:
    """把统一链路 ID 写进 payload，供三套记录按同一值检索。"""
    if not request_id:
        return payload
    return {**payload, REQUEST_ID_KEY: request_id}


def bounded_payload(
    payload: dict, *, limit: int = MAX_RAW_EVENT_PAYLOAD_CHARS
) -> dict:
    """给 ``raw_events.payload`` 加大小上限：超限则截断并标记，**不丢事件**。

    保留 ``request_id``（即使超限也可串联），其余内容以序列化前缀 ``preview``
    呈现；与 repository 既有的 ``{"truncated": true}`` 标记口径一致。
    循环收缩 preview 直到序列化结果确实落在上限内（JSON 转义会放大长度）。
    """
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= limit:
        return payload

    marker: Dict[str, Any] = {TRUNCATED_KEY: True, "original_chars": len(encoded)}
    carried = {key: payload[key] for key in (REQUEST_ID_KEY,) if key in payload}
    result: Dict[str, Any] = {**carried, **marker, "preview": ""}
    overhead = len(json.dumps(result, ensure_ascii=False, sort_keys=True))
    result["preview"] = encoded[: max(0, limit - overhead)]
    # 转义可能让 preview 变长，按块收缩保证最终落盘严格有界。
    while len(json.dumps(result, ensure_ascii=False, sort_keys=True)) > limit:
        preview = result["preview"]
        if not preview:
            break
        result["preview"] = preview[: max(0, len(preview) - 64)]
    return result
