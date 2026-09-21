"""观测配置的读取与校验（spec-013）。

设计原则：**观测永远不影响业务**。
任何配置缺失或取值非法，都退化为「不上报」而不是抛异常。
"""

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


def should_sample() -> bool:
    """本次调用是否应被采样上报。"""
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
