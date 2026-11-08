"""Langfuse 私有 SDK 符号兼容层（spec-045 Task 05，F16 / Q7）。

把分散在 `spans.py` 里的三处私有符号访问收拢到本模块，对外暴露稳定语义：

  - ``langfuse._client.attributes.create_span_attributes`` 富化属性
  - ``langfuse._otel_tracer`` 私有 tracer
  - ``generation._otel_span._start_time`` 回填起点

符号缺失时**显式降级 + 告警**（不再静默跳过），主链路 fail-open 不受影响。
修复点唯一：本文件——升版导致符号改名/移除时，只改这里。

> 不保证「从根上不会坏」：私有符号消失后精确时间轴仍可能退化；本层只保证
> 「退化可发现（显式降级 + 告警）」与「修复点唯一（一个文件）」。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# 私有符号 1：create_span_attributes（导入期容错 + 缺失告警）
# 升版改名/移除时不得让整个 observability 模块在**导入期**崩溃（导入期异常不在
# safe_call 保护范围内，会连 record_event 一起挂）。缺失时降级为 None 并显式告警。
try:
    from langfuse._client.attributes import create_span_attributes as _create_span_attributes
except ImportError:  # pragma: no cover - 仅在 langfuse 私有符号变动时触发
    _create_span_attributes = None
    logger.warning(
        "Langfuse 私有符号 langfuse._client.attributes.create_span_attributes 缺失："
        "阶段子 span 退化为仅打最小属性集（langfuse.observation.type=span），"
        "瀑布图富化 metadata 不可用。修复点唯一："
        "backend/app/platform/observability/sdk_compat.py"
    )


def create_span_attributes(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """稳定语义封装：返回 Langfuse observation 富化属性。

    底层私有符号缺失时**显式降级 + 告警**并返回空 dict（最小属性集仍由调用方
    直接打），绝不静默跳过、绝不抛异常。
    """
    if _create_span_attributes is None:
        logger.warning(
            "create_span_attributes 不可用（私有符号缺失），跳过富化属性"
            "（最小属性集 langfuse.observation.type=span 仍生效）。"
            "修复点唯一：backend/app/platform/observability/sdk_compat.py"
        )
        return {}
    return _create_span_attributes(*args, **kwargs)


# 私有符号 2：langfuse._otel_tracer
def get_otel_tracer(langfuse: Any) -> Optional[Any]:
    """返回 langfuse 私有的 ``_otel_tracer``；缺失时显式降级 + 告警，返回 None。

    调用方收到 None 后应跳过阶段子 span 的反推（已有 4 段时间戳的核心上报不受影响）。
    """
    tracer = getattr(langfuse, "_otel_tracer", None)
    if tracer is None:
        logger.warning(
            "Langfuse 私有符号 _otel_tracer 缺失：无法反推阶段子 span"
            "（退化为不创建子 span）。修复点唯一："
            "backend/app/platform/observability/sdk_compat.py"
        )
    return tracer


# 私有符号 3：generation._otel_span._start_time
def get_otel_span(generation: Any) -> Optional[Any]:
    """返回 generation 私有的底层 OTel span；缺失时显式降级 + 告警，返回 None。"""
    span = getattr(generation, "_otel_span", None)
    if span is None:
        logger.warning(
            "generation 底层 _otel_span 缺失：无法回填起点"
            "（退化为起点≈上报时刻）。修复点唯一："
            "backend/app/platform/observability/sdk_compat.py"
        )
        return None
    return span


def set_otel_span_start_time(span: Any, target_ns: int) -> None:
    """把底层 OTel span 的私有 ``_start_time`` 写为 ``target_ns``（fail-open）。

    写入失败（只读属性等）时**显式告警**且不冒泡，generation 上报照常。
    """
    try:
        span._start_time = target_ns
    except Exception as error:  # noqa: BLE001 — 回填失败不得影响 generation 上报
        logger.warning(
            "generation 起点回填失败（已忽略）：%s: %s", type(error).__name__, error
        )
