from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")


def test_retry_and_provider_fallback_states_are_user_visible():
    assert "waiting_retry: '等待重试'" in RESEARCH
    assert "retryInsightText" in RESEARCH
    assert "资源繁忙，等待自动重试" in RESEARCH
    assert "正在切换备用模型" in RESEARCH
    assert "下一次：" in RESEARCH


def test_runtime_error_codes_have_safe_frontend_copy():
    assert "MODEL_TIMEOUT: '本地模型响应超时，将按退避策略重试。'" in RESEARCH
    assert "MODEL_RATE_LIMITED: '模型服务限流，将按退避策略重试。'" in RESEARCH
    assert "PROVIDER_FALLBACK: '本地模型不可用，正在切换备用模型。'" in RESEARCH
    assert "RETRY_EXHAUSTED: '重试次数已耗尽，任务需要人工恢复。'" in RESEARCH
    assert "ONLINE_FALLBACK_DISABLED" in RESEARCH
