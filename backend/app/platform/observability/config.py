"""观测配置的读取与校验（spec-013）。

设计原则：**观测永远不影响业务**。
任何配置缺失或取值非法，都退化为「不上报」而不是抛异常。
"""

import contextlib
import contextvars
import logging
import random

from backend.app.platform import config

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """是否启用观测上报。"""
    return config.LANGFUSE_ENABLED


def credentials_ready() -> bool:
    """Langfuse 的 public/secret key 是否都配好了。"""
    return bool(config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY)


def sample_rate() -> float:
    """解析采样率。

    越界值（非数字、<0、>1）回退到 1.0 并告警——宁可多采，也不要静默丢数据。
    """
    raw = config.LANGFUSE_SAMPLE_RATE_RAW
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        logger.warning("LANGFUSE_SAMPLE_RATE 不是数字（%r），回退为 1.0", raw)
        return 1.0
    if rate < 0.0 or rate > 1.0:
        logger.warning("LANGFUSE_SAMPLE_RATE 越界（%s），回退为 1.0", rate)
        return 1.0
    return rate


# 采样决策 ContextVar（spec-045 Task 05，F11）：同一 trace/请求级只随机决策一次，
# 全链路（record_event / record_ollama_generation / record_routing_observation /
# 各 phase span）共用，避免同一 trace 内各阶段采样不一致撕碎瀑布图。
_sample_decision = contextvars.ContextVar("obs_sample_decision", default=None)
_sample_token = contextvars.ContextVar("obs_sample_token", default=None)


def _compute_decision() -> bool:
    """enabled / credentials / 采样率校验 + 随机决策（不缓存）。"""
    if not enabled():
        return False
    if not credentials_ready():
        return False
    rate = sample_rate()
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    return random.random() < rate


def decide_sampling() -> bool:
    """做出 trace/请求级单次采样决策并缓存到 ContextVar，全链路共用；幂等。

    确定性结果（rate<=0 或 rate>=1）不缓存——它们与配置强相关，配置变化时同上下文
    内的后续判断应反映最新配置，同时不影响 0<rate<1 随机采样的链路一致性。
    """
    cached = _sample_decision.get()
    if cached is not None:
        return cached
    if not enabled() or not credentials_ready():
        return False
    rate = sample_rate()
    if rate <= 0.0 or rate >= 1.0:
        return rate >= 1.0
    decision = random.random() < rate
    token = _sample_decision.set(decision)
    _sample_token.set(token)
    return decision


def should_sample() -> bool:
    """本次调用是否应被采样上报（spec-045 Task 05：同 trace 内返回同一决策）。"""
    cached = _sample_decision.get()
    if cached is not None:
        return cached
    return decide_sampling()


def reset_sample_decision() -> None:
    """复位采样决策 ContextVar（供 trace.end_trace 与测试清理调用）。"""
    token = _sample_token.get()
    if token is not None:
        with contextlib.suppress(ValueError, LookupError):
            _sample_decision.reset(token)
        _sample_token.set(None)


def route() -> str:
    """对话链路选择：`direct`（默认，spec-041：采集 Ollama 服务端原生 timings 支撑
    5 阶段瀑布观测）或 `langchain`（A6 双链路对比可显式指定）。

    未知取值一律回退到 `langchain`，保持稳定行为。
    """
    value = config.OLLAMA_ROUTE
    if value not in ("langchain", "direct"):
        if value:
            logger.warning("OLLAMA_ROUTE 取值非法（%r），回退为 langchain", value)
        return "langchain"
    return value


def cold_start_threshold_ms() -> float:
    return config.OBS_COLD_START_THRESHOLD_MS


def max_input_chars() -> int:
    return config.OBS_MAX_INPUT_CHARS


def max_output_chars() -> int:
    return config.OBS_MAX_OUTPUT_CHARS
