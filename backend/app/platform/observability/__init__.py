"""观测埋点层（spec-013）。

对外只暴露少量稳定入口，业务侧按需调用；所有函数在观测未启用、
未配置或异常时都是 no-op，绝不影响业务。

典型用法：

    from backend.app.platform.observability import record_ollama_generation, utc_now

    started_at = utc_now()
    result = chat_direct(messages, model)
    record_ollama_generation(
        model=model,
        prompt_messages=messages,
        result=result,
        route="direct",
        started_at=started_at,
    )
"""

from backend.app.platform.observability import client, config, safe  # noqa: F401
from backend.app.platform.observability.client import flush, get_client
from backend.app.platform.observability.spans import (
    derive_metrics,
    prompt_observation_metadata,
    record_event,
    record_ollama_generation,
    record_routing_observation,
    redact_prompt_messages,
    utc_now,
)
from backend.app.platform.observability.trace import (
    create_trace_id,
    end_trace,
    get_current_trace_id,
    start_trace,
)

__all__ = [
 "client",
 "config",
 "safe",
 "get_client",
 "flush",
 "derive_metrics",
 "prompt_observation_metadata",
 "redact_prompt_messages",
    "record_event",
    "record_ollama_generation",
    "record_routing_observation",
 "utc_now",
 "start_trace",
 "end_trace",
 "get_current_trace_id",
 "create_trace_id",
]
