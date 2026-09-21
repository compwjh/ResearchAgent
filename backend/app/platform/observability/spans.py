"""把 Ollama 原生 timings 组织成 Langfuse 上报（spec-013）。

## 上报结构

一个 generation 承载一次 LLM 调用：

- `input`  = prompt 的完整组成（逐条消息，超长截断）
- `output` = 正式输出（超长截断）
- `completion_start_time` = 首 token 到达时刻 → Langfuse 据此原生计算 TTFT
- `metadata` = 完整耗时分解，供 UI 展示与自研视图读取
- numeric score = 关键指标，供原生 Dashboard 做分位与聚合

## 阶段子 span（spec-041 T-E）

`start_as_current_observation` 不接受 `start_time`，SDK 主路径下 generation 主体的
startTime≈endTime（实测差约 4ms）。为满足"瀑布图直接显示各阶段时间条"，本任务绕开 SDK 主路径：
进入 `with langfuse.start_as_current_observation(...)` 之后，直接用与 SDK 同款的私有 tracer
（`langfuse._otel_tracer`）创建 4 个带精确 `start_time`/`end_time` 的 OTel child span：

- `phase:load`     = [started_at, started_at + load_ms]
- `phase:prefill`  = [started_at + load_ms, started_at + load_ms + prompt_eval_ms]
- `phase:decode`   = [started_at + first_token_ms, started_at + first_token_ms + eval_ms]
- `phase:overhead` = [started_at + first_token_ms + eval_ms, started_at + client_wall_ms]

`first_token` 不单独成 span，而是写入 generation 主体的 `completion_start_time`（SDK 原生支持，供 TTFT）。
每个阶段独立 try：单个阶段上报失败不影响其余阶段与 generation 上报（fail-open）。
metadata + numeric score 仍照常上报，作为双保险与自研视图数据源。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

# Langfuse 私有符号：升版改名/移除时不得让整个 observability 模块在**导入期**崩溃
# （导入期异常不在 safe_call 保护范围内，会连 record_event 一起挂）。故容错导入：
# 缺失时降级为 None，运行期跳过富化属性，但仍照常创建并上报子 span。
try:
    from langfuse._client.attributes import create_span_attributes as _create_span_attributes
except ImportError:  # pragma: no cover - 仅在 langfuse 私有符号变动时触发
    _create_span_attributes = None

from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.safe import safe_call
from backend.app.platform.observability.trace import get_current_trace_id
from backend.app.platform.ollama_direct import OllamaChatResult
from backend.app.research.application.routing_observation import (
    _bounded_text,
    _safe_features,
    _safe_models,
    _validate_outcome,
)

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
    metadata: Dict[str, Any] = {
        "model": model,
        "route": route,
        "reasoning_present": bool(result.thinking),
        "reasoning_chars": len(result.thinking or ""),
    }
    if extra:
        metadata.update({
            key: value for key, value in extra.items()
            if key in {"reasoning_status", "reasoning_duration_ms", "answer_duration_ms", "error_code", "stable_error_code", "reasoning_present", "reasoning_chars", "model", "route"}
        })
    return metadata


def _to_ns(dt: datetime) -> int:
    """把带时区的时间戳转成 OTel 所需的纳秒整数（int(dt.timestamp() * 1e9)）。"""
    return int(dt.timestamp() * 1_000_000_000)


# Langfuse 私有属性 key（硬编码字符串而非 import，避免依赖私有符号导致导入失败）。
# 即使没有 _create_span_attributes helper，也必须给子 span 打上 observation.type=span，
# 否则 dual 模式下不被识别为 observation。这是「最小属性集」，保证 fail-open 下子 span 仍有效。
_LF_OBSERVATION_TYPE = "langfuse.observation.type"


def _set_phase_span_attributes(span, phase_name: str) -> None:
    """给阶段子 span 打 Langfuse 约定属性（fail-open）。

    最小属性集始终打 `langfuse.observation.type=span`（硬编码字符串），保证私有
    helper 缺失时子 span 仍被识别为 observation。富化 metadata（phase 名）仅在
    `_create_span_attributes` 可用时进行；缺失时跳过，不影响 4 个子 span 的时间戳上报。
    """
    span.set_attribute(_LF_OBSERVATION_TYPE, "span")
    if _create_span_attributes is not None:
        span.set_attributes(
            _create_span_attributes(observation_type="span", metadata={"phase": phase_name})
        )


def _report_phase_spans(
    langfuse: Any,
    result: OllamaChatResult,
    started_at: Optional[datetime],
) -> None:
    """为一次 LLM 调用反推 4 个阶段子 span（load/prefill/decode/overhead）。

    Langfuse SDK 的 `start_as_current_observation` 不接受 `start_time`，主路径下
    generation 主体的 startTime≈endTime。为让瀑布图显示各阶段时间条，这里绕开主路径，
    直接用与 SDK 同款的私有 tracer（`langfuse._otel_tracer`）创建带精确起止时间的
    OTel child span，并打 `langfuse.observation.type=span` 属性，保证 dual 模式下
    落回 legacy observations。

    `first_token` 不在此成 span（由 generation 主体的 `completion_start_time` 承载）。

    fail-open：tracer 缺失/不可用时直接返回；每个阶段独立 try，单个阶段上报失败
    不影响其余阶段与 generation 上报。整段已处在 `_report` 的 `safe_call` 内，
    任何意外都不会冒泡到业务。
    """
    tracer = getattr(langfuse, "_otel_tracer", None)
    if tracer is None:
        return

    # 与 completion_start_time 同源：优先用调用方传入的请求起点
    base = started_at or (
        datetime.now(timezone.utc) - timedelta(milliseconds=result.client_wall_ms)
    )
    timings = result.timings

    phases = [
        ("phase:load", base, base + timedelta(milliseconds=timings.load_ms)),
        (
            "phase:prefill",
            base + timedelta(milliseconds=timings.load_ms),
            base + timedelta(milliseconds=timings.load_ms + timings.prompt_eval_ms),
        ),
        (
            "phase:decode",
            base + timedelta(milliseconds=result.first_token_ms),
            base + timedelta(milliseconds=result.first_token_ms + timings.eval_ms),
        ),
        (
            "phase:overhead",
            base + timedelta(milliseconds=result.first_token_ms + timings.eval_ms),
            base + timedelta(milliseconds=result.client_wall_ms),
        ),
    ]

    for phase_name, start_dt, end_dt in phases:
        try:
            with tracer.start_as_current_span(
                phase_name, start_time=_to_ns(start_dt), end_on_exit=False
            ) as span:
                try:
                    _set_phase_span_attributes(span, phase_name)
                finally:
                    # end_on_exit=False，必须显式结束；即使 set_attributes 抛错也要结束，避免 span 泄漏
                    span.end(end_time=_to_ns(end_dt))
        except Exception as error:  # noqa: BLE001 — 单阶段失败不得影响其它阶段与 generation
            logger.warning(
                "阶段 span '%s' 上报失败（已忽略，不影响业务与 generation）：%s: %s",
                phase_name, type(error).__name__, error,
            )


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

    # 首 token 时刻（TTFT）是本次诊断的核心指标，不能因为调用方漏传 started_at 就丢失：
    # 没有起点时，用「当前时刻 - 客户端墙钟」反推请求起点，再叠加首 token 延迟。
    completion_start_time: Optional[datetime] = None
    if result.first_token_ms > 0:
        base = started_at or (datetime.now(timezone.utc) - timedelta(milliseconds=result.client_wall_ms))
        completion_start_time = base + timedelta(milliseconds=result.first_token_ms)

    def _report() -> None:
        # spec-041：用户裁决「无需隐私设计，input 与 output 全量可见」，
        # 故 redact_prompt_messages 保留原文 content。把输入格式化搬进 safe_call
        # 内部，任何格式化异常都会被 fail-open 吞掉，绝不波及业务主链路。
        formatted_input = _format_messages(redact_prompt_messages(prompt_messages))
        # input_chars 必须是**截断前**的原始长度：量的是 prompt_messages 原文，
        # 而上报的 input 由 _truncate 另行截断，二者解耦。
        input_chars = sum(len(str(message.get("content", "") or "")) for message in prompt_messages)
        metadata = _build_metadata(
            result,
            metrics,
            model=model,
            route=route,
            input_chars=input_chars,
            extra=extra_metadata,
        )
        if error_type and not success:
            metadata["error_code"] = str(error_type)

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
            # spec-041 T-E：反推 4 个阶段子 span（load/prefill/decode/overhead），
            # 带精确起止时间，让 Langfuse 瀑布图显示各阶段时间条。处于 safe_call 内，
            # 且各阶段独立 try，单阶段失败不影响 generation 上报与业务。
            _report_phase_spans(langfuse, result, started_at)

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


def redact_prompt_messages(messages: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    """Return observation input for a prompt, preserving role and content.

    spec-041：用户已裁决「无需隐私设计，input 与 output 全量可见」，因此
    ``content`` 原样保留（不再清零）。仅做 role 归一化与 content 缺省兜底，
    返回结构（逐条 ``{role, content}``）与签名保持不变，调用方用法无需改动。
    """
    return [
        {"role": str(message.get("role", "unknown")), "content": str(message.get("content", "") or "")}
        for message in messages
    ]


def prompt_observation_metadata(messages: Sequence[Dict[str, str]], *, system_rule_enabled: Optional[bool] = None) -> Dict[str, Any]:
    roles = [str(message.get("role", "unknown")) for message in messages]
    chars = [len(str(message.get("content", "") or "")) for message in messages]
    metadata: Dict[str, Any] = {
        "role_count": len(roles),
        "role_names": roles,
        "char_counts": chars,
    }
    if system_rule_enabled is not None:
        metadata["system_rule_enabled"] = bool(system_rule_enabled)
    return metadata


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


def record_routing_observation(
    *,
    task_type: str,
    features: Dict[str, Any],
    candidate_models: List[str],
    chosen_model: str,
    reason: str,
    policy_version: str,
    outcome: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort Spec031 observation with an explicit redaction allowlist.

    This seam never accepts prompt/answer/reasoning text.  Keeping the
    allowlist here protects callers that route through Langfuse as well as
    SQLite observation storage; ``record_event``/``safe_call`` ensure a
    telemetry outage cannot affect the model call.
    """
    # Apply the same value-level contract as SQLite before touching sampling,
    # client initialization, or Langfuse.  Rejection is intentionally quiet
    # and diagnostic only by field name; values are never logged or emitted.
    try:
        allowed_keys = {"tier", "role", "attempt", "worker_grant", "quality_profile", "has_evidence"}
        safe_features = _safe_features({
            str(key): value for key, value in (features or {}).items()
            if str(key) in allowed_keys
        })
        metadata: Dict[str, Any] = {
            "task_type": _bounded_text(task_type, name="task_type", limit=80),
            "features": safe_features,
            "candidate_models": _safe_models(list(candidate_models or [])[:16]),
            "chosen_model": _bounded_text(chosen_model, name="chosen_model", limit=128),
            "reason": _bounded_text(reason, name="reason", limit=256),
            "policy_version": _bounded_text(policy_version, name="policy_version", limit=80),
        }
        if outcome is not None:
            metadata["outcome"] = {
                key: _validate_outcome(outcome.get(key), field=key)
                for key in ("schema_valid", "quality_score", "ttft", "duration", "tokens", "error_code")
                if key in outcome
            }
    except Exception as exc:  # noqa: BLE001 - observation must never block routing
        logger.warning("路由观测值被拒绝（已忽略）：%s", type(exc).__name__)
        return

    # should_sample()/get_client() are deliberately inside safe_call as well:
    # a broken config or SDK client must be a no-op, not a routing failure.
    safe_call(record_event, name="research-routing", metadata=metadata)


def utc_now() -> datetime:
    """统一的当前时刻取值（带时区），供业务层记录请求开始时间。"""
    return datetime.now(timezone.utc)
