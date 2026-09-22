"""线上模型注册表解析测试（spec-035 Task02）。

覆盖任务书「边界」全部场景：空值、无冒号、多冒号、空项、重复项、大小写不一致、
缺 Key、未知 provider 无地址、非 https 且非 loopback、前后空格；以及 loopback http
接受、内置默认地址表、get_online_model 查询、字段与 source、api_key 绝不写日志。

用 monkeypatch 注入 env，不依赖真实网络与真实 Key。
"""
import logging

import pytest

from backend.app.platform import config
from backend.app.platform.model_catalog import (
    OnlineModelEntry,
    get_online_model,
    get_online_models,
)

# 测试用假 Key（绝不可能是真实凭据）
FAKE_KEY = "sk-test-fake-key-not-real"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    # 隔离 load_dotenv 注入的真实 .env，避免污染；各测试按需 setenv。
    for key in (
        "ONLINE_MODELS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_empty_value_returns_empty_list(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "")
    assert get_online_models() == []


def test_no_colon_skipped_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek")
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert result == []
    assert any("need exactly one" in r.message for r in caplog.records)


def test_multiple_colons_skipped_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "a:b:c")
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert result == []
    assert any("need exactly one" in r.message for r in caplog.records)


def test_empty_items_ignored(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", ",,deepseek:deepseek-chat,")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    result = get_online_models()
    assert [e.id for e in result] == ["deepseek:deepseek-chat"]


def test_duplicate_keeps_first_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat,deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert len(result) == 1
    assert result[0].id == "deepseek:deepseek-chat"
    assert any("duplicate" in r.message.lower() for r in caplog.records)


def test_case_insensitive_provider(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "DeepSeek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    result = get_online_models()
    assert len(result) == 1
    assert result[0].provider == "deepseek"
    assert result[0].id == "deepseek:deepseek-chat"


def test_missing_api_key_not_registered(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    # 不设置 DEEPSEEK_API_KEY
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert result == []
    assert caplog.records == []  # 缺 Key 静默，不 warning（对应 Q9 不展示）


def test_unknown_provider_without_url_skipped_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "weird:model")
    monkeypatch.setenv("WEIRD_API_KEY", FAKE_KEY)
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert result == []
    assert any("not in default table" in r.message.lower() for r in caplog.records)


def test_non_https_non_loopback_rejected_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://example.com")
    with caplog.at_level(logging.WARNING):
        result = get_online_models()
    assert result == []
    assert any("scheme" in r.message.lower() for r in caplog.records)


def test_whitespace_trimmed(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "  DeepSeek:deepseek-chat  ")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    result = get_online_models()
    assert [e.id for e in result] == ["deepseek:deepseek-chat"]


def test_loopback_http_accepted(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "openai:gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")
    result = get_online_models()
    assert len(result) == 1
    assert result[0].provider == "openai"
    assert result[0].base_url == "http://localhost:8080"


def test_default_base_url_for_known_provider(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    result = get_online_models()
    assert result[0].base_url == "https://api.deepseek.com"


def test_default_base_url_openai(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "openai:gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    result = get_online_models()
    assert result[0].base_url == "https://api.openai.com/v1"


def test_get_online_model_by_id(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat,openai:gpt-4o")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    hit = get_online_model("openai:gpt-4o")
    assert hit is not None
    assert hit.provider == "openai"
    assert hit.model == "gpt-4o"
    assert get_online_model("not:exists") is None


def test_entry_fields_and_source(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    entries = get_online_models()
    assert len(entries) == 1
    e = entries[0]
    assert e.id == "deepseek:deepseek-chat"
    assert e.provider == "deepseek"
    assert e.model == "deepseek-chat"
    assert e.display_name == e.id
    assert e.base_url == "https://api.deepseek.com"
    assert e.api_key == FAKE_KEY
    assert e.source == "online"


def test_api_key_never_in_logs(monkeypatch, caplog):
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://example.com")  # 触发 warning
    with caplog.at_level(logging.WARNING):
        get_online_models()
    for record in caplog.records:
        assert FAKE_KEY not in record.getMessage()


def test_config_exposes_online_models_constant():
    assert hasattr(config, "ONLINE_MODELS")
    assert isinstance(config.ONLINE_MODELS, str)
