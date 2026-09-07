"""观测埋点的安全包裹（spec-013）。

硬约束：**埋点的任何异常都不得冒泡到业务**。
对话失败可以是模型或网络问题，但绝不能是因为"想记录一下慢不慢"而失败。
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def safe_call(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Optional[Any]:
    """执行一个埋点动作，捕获并吞掉所有异常。

    返回被包裹函数的返回值；异常时返回 None 并记 warning 日志（不重复堆栈刷屏）。
    """
    try:
        return action(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 — 观测层必须兜住一切
        logger.warning("观测上报失败（已忽略，不影响业务）：%s: %s", type(error).__name__, error)
        return None
