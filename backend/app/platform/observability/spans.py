"""把 Ollama 原生 timings 组织成 Langfuse 上报（spec-013）。

## 上报结构

一个 generation 承载一次 LLM 调用：

- `input`  = prompt 的完整组成（逐条消息，超长截断）
- `output` = 正式输出（超长截断）
- `completion_start_time` = 首 token 到达时刻 → Langfuse 据此原生计算 TTFT
- `metadata` = 完整耗时分解，供 UI 展示与自研视图读取
- numeric score = 关键指标，供原生 Dashboard 做分位与聚合

## 为什么不做"虚拟阶段 span"

原计划把 load → prefill → decode 映射成子 span，让瀑布图直接显示各阶段时间条。
但核实 SDK 后确认：`start_as_current_observation` **不支持指定 start_time**
（只有 `end(end_time=)` 可控），无法把服务端 timings 反推成精确的时间段；
硬做只能走 OTel 内部 API，脆弱且依赖未公开实现。

因此改为：阶段耗时以 **metadata + numeric score** 承载（Langfuse 原生就能展示与聚合），
**精确甘特图由任务 07 的自研视图从 metadata 渲染**。
这样既不依赖 SDK 内部实现，甘特图的呈现也更可控。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.safe import safe_call
from backend.app.platform.observability.trace import get_current_trace_id
from backend.app.platform.ollama_direct import OllamaChatResult

logger = logging.getLogger(__name__)

# 上报为 numeric score 的指标（供原生 Dashboard 做分位与聚合）
SCORE_METRICS = (
    "ttft_ms",
    "load_ms",
    "prompt_eval_ms",
    "eval_ms",
    "overhead_ms",
    "tokens_per_sec",
    "is_cold_start",
)


def _trace_context():
    """若当前存在活动 trace，返回 `{"trace_id": tid}` 让 observation 归入该 trace。

    没有活动 trace（chat 链路）时返回 None，调用方据此保持向后兼容
    （observation 各成独立 trace，行为完全不变）。
    """
    trace_id = get_current_trace_id()
    if trace_id:
        return {"trace_id": trace_id}
    return None


def _truncate(text: str, limit: int) -> str:
    """按字符数截断，并在截断处留下标记。"""
    if not text or len(text) <= limit:
        return text
    return f"{text[:limit]}\n…[已截断，共 {len(text)} 字符]"


def derive_metrics(result: OllamaChatResult) -> Dict[str, float]:
    """从采集结果派生诊断指标。

    两个时间轴分开呈现：
    - 服务端 timings（load / prompt_eval / eval）来自 Ollama，不含网络与框架开销
    - `overhead_ms` = 客户端墙钟 - 服务端总耗时，代表网络 + 框架（LangChain/HTTP 层）开销
      时钟误差会让它变小，故下限截断到 0，不出现负值
    """
    timings = result.timings
    # 无原生 timings（langchain 链路）时 total_ms 为 0，若仍相减会把整段墙钟
    # 当成"网络+框架开销"计入开销指标，污染统计口径 —— 此时开销记为 0。
    overhead_ms = max(0.0, result.client_wall_ms - timings.total_ms) if result.timings_available else 0.0
    eval_seconds = timings.eval_ms / 1000.0
    tokens_per_sec = (timings.completion_tokens / eval_seconds) if eval_seconds > 0 else 0.0
    cold_threshold = obs_config.cold_start_threshold_ms()

    return {
        "ttft_ms": max(0.0, result.first_token_ms),
        "load_ms": max(0.0, timings.load_ms),
        "prompt_eval_ms": max(0.0, timings.prompt_eval_ms),
        "eval_ms": max(0.0, timings.eval_ms),
        "total_ms": max(0.0, timings.total_ms),
        "overhead_ms": overhead_ms,
        "client_wall_ms": max(0.0, result.client_wall_ms),
        "tokens_per_sec": tokens_per_sec,
        "is_cold_start": 1.0 if timings.load_ms > cold_threshold else 0.0,
    }


def _build_metadata(
    result: OllamaChatResult,
    metrics: Dict[str, float],
    *,
    model: str,
    route: str,
    input_chars: int,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    intervals = result.chunk_intervals_ms
    avg_interval = (sum(intervals) / len(intervals)) if intervals else 0.0

    metadata: Dict[str, Any] = {
        "model": model,
        "route": route,
        "timings_available": result.timings_available,
        # 思考过程与正式输出分开存，便于在 UI 中区分查看
        "thinking": _truncate(result.thinking, obs_config.max_output_chars()),
        # 字符数字段一律取**截断前**的原始长度，供统计看板做不可复现的手工计算替代
        "input_chars": input_chars,
        "output_chars": len(result.content or ""),
        "thinking_chars": len(result.thinking or ""),
        "prompt_tokens": result.timings.prompt_tokens,
        "completion_tokens": result.timings.completion_tokens,
        "chunk_count": len(intervals),
        "avg_chunk_interval_ms": round(avg_interval, 3),
    }
    # 各阶段耗时（毫秒，保留 3 位小数便于阅读）
    for key, value in metrics.items():
        metadata[key] = round(value, 3)
    if extra:
        metadata.update(extra)
    return metadata


def record_ollama_generation(
    *,
    model: str,
    prompt_messages: Sequence[Dict[str, str]],
    result: OllamaChatResult,
    route: str = "langchain",
    name: str = "ollama-chat",
    started_at: Optional[datetime] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_type: Optional[str] = None,
) -> None:
    """记录一次 LLM 调用。任何异常都不冒泡到业务。

    Args:
        model: 模型名
        prompt_messages: prompt 的完整组成（逐条消息）
        result: `chat_direct` 的采集结果
        route: "langchain" | "direct"，用于 A/B 对比分组
        name: generation 名称
        started_at: 请求开始时刻；传入后据此推算 completion_start_time（首 token 时刻）
        session_id: 会话标识（写入 metadata，便于按会话聚合）
        tags: 标签（写入 metadata）
        extra_metadata: 额外元数据
        success: 本次调用是否成功；写入 metadata 的 `success`（布尔）并附带
            `success_flag`（0/1，便于数值聚合）。
        error_type: 失败时的异常类型名（如 "RuntimeError"）；成功时为空串。
            写入 metadata 的 `error_type`。
    """
    if not obs_config.should_sample():
        return

    langfuse = obs_client.get_client()
    if langfuse is None:
        return

    metrics = derive_metrics(result)
    # input_chars 必须是**截断前**的原始长度：先格式化、量长度，再交给 _truncate 截断。
    formatted_input = _format_messages(prompt_messages)
    metadata = _build_metadata(
        result,
        metrics,
        model=model,
        route=route,
        input_chars=len(formatted_input),
        extra=extra_metadata,
    )
    # 统一为 generation 提供稳定的链路类型；显式非空值优先，空值回退到名称推断。
    if not metadata.get("chain_type"):
        metadata["chain_type"] = "kb" if name.startswith("kb.") else "chat"
    # 成功/失败标记供统计看板做成功率与异常类型聚合。
    metadata["success"] = success
    metadata["success_flag"] = 1 if success else 0
    metadata["error_type"] = error_type if (error_type and not success) else ""
    if session_id:
        metadata["session_id"] = session_id
    if tags:
        metadata["tags"] = tags

    # 首 token 时刻（TTFT）是本次诊断的核心指标，不能因为调用方漏传 started_at 就丢失：
    # 没有起点时，用「当前时刻 - 客户端墙钟」反推请求起点，再叠加首 token 延迟。
    completion_start_time: Optional[datetime] = None
    if result.first_token_ms > 0:
        base = started_at or (datetime.now(timezone.utc) - timedelta(milliseconds=result.client_wall_ms))
        completion_start_time = base + timedelta(milliseconds=result.first_token_ms)

    def _report() -> None:
        with langfuse.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=_truncate(formatted_input, obs_config.max_input_chars()),
            metadata=metadata,
            completion_start_time=completion_start_time,
            trace_context=_trace_context(),
            usage_details={
                "input": result.timings.prompt_tokens,
                "output": result.timings.completion_tokens,
            },
        ) as generation:
            generation.update(output=_truncate(result.content, obs_config.max_output_chars()))
            for metric_name in SCORE_METRICS:
                generation.score(
                    name=metric_name,
                    value=metrics.get(metric_name, 0.0),
                    data_type="NUMERIC",
                )

    safe_call(_report)


def _format_messages(messages: Sequence[Dict[str, str]]) -> str:
    """把 prompt 组成格式化为可读文本，便于在 UI 中直接查看各段内容。"""
    if not messages:
        return ""
    parts: List[str] = []
    for index, message in enumerate(messages, start=1):
        role = message.get("role", "unknown")
        content = message.get("content", "") or ""
        parts.append(f"[{index}] {role}（{len(content)} 字符）:\n{content}")
    return "\n\n".join(parts)


def record_event(
    *,
    name: str,
    input_data: Optional[Any] = None,
    output_data: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """记录一个非 LLM 的阶段（供知识库检索、向量化等环节使用）。

    与 `record_ollama_generation` 一样，异常不冒泡。
    """
    if not obs_config.should_sample():
        return

    langfuse = obs_client.get_client()
    if langfuse is None:
        return

    extra: Dict[str, Any] = dict(metadata or {})
    if duration_ms is not None:
        extra["duration_ms"] = round(max(0.0, duration_ms), 3)

    def _report() -> None:
        with langfuse.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_data,
            metadata=extra or None,
            trace_context=_trace_context(),
         ) as span:
            span.update(output=output_data)

    safe_call(_report)


def utc_now() -> datetime:
    """统一的当前时刻取值（带时区），供业务层记录请求开始时间。"""
    return datetime.now(timezone.utc)
