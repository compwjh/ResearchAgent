"""Langfuse client 单例与降级（spec-013）。

未启用、未配 key、SDK 不可用时一律返回 None，调用方按"无需上报"处理。
"""

import logging
from typing import Optional

from backend.app.core import config
from backend.app.observability import config as obs_config

logger = logging.getLogger(__name__)

_client: Optional[object] = None
_client_initialized = False
_warned_missing_credentials = False


def get_client() -> Optional[object]:
    """返回 Langfuse client 单例；不可用时返回 None。

    只初始化一次：失败后不再反复重试，避免每次请求都付一次异常开销。
    """
    global _client, _client_initialized, _warned_missing_credentials

    if not obs_config.enabled():
        return None

    if not obs_config.credentials_ready():
        if not _warned_missing_credentials:
            logger.info("观测已启用但缺少 Langfuse 凭据（LANGFUSE_PUBLIC_KEY / SECRET_KEY），跳过上报")
            _warned_missing_credentials = True
        return None

    if _client_initialized:
        return _client

    _client_initialized = True
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST,
            timeout=config.LANGFUSE_TIMEOUT,
        )
        logger.info("Langfuse client 已初始化（host=%s）", config.LANGFUSE_HOST)
    except Exception as error:  # noqa: BLE001 — 初始化失败只降级
        logger.warning("Langfuse client 初始化失败，本次运行不再上报：%s", error)
        _client = None

    return _client


def flush() -> None:
    """把排队中的事件立即送出。失败只记日志。"""
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as error:  # noqa: BLE001
        logger.warning("Langfuse flush 失败（已忽略）：%s", error)


def reset_for_tests() -> None:
    """重置单例（仅供测试使用）。"""
    global _client, _client_initialized, _warned_missing_credentials
    _client = None
    _client_initialized = False
    _warned_missing_credentials = False
