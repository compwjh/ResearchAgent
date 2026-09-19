"""provider 分发与并集校验测试（spec-035 Task03）。

覆盖 `ollama.create_chat_model` 的 provider 分发（线上→ChatOpenAI，
否则→ChatOllama，行为零变化）与 `model_catalog.is_model_available` 的
本地 ∪ 线上并集语义。全部用 monkeypatch 注入 env / 桩函数，不依赖真实网络与真实 Key。
"""
import logging

import httpx
import pytest
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from backend.app.platform import config
from backend.app.platform.model_catalog import is_model_available
from backend.app.platform.ollama import create_chat_model

# 测试用假 Key（绝不可能是真实凭据）
FAKE_KEY = "sk-test-fake-key-not-real"
ONLINE_ID = "deepseek:deepseek-chat"
LOCAL_NAME = "qwen3.5:9b"


def _raise_connect(*_args, **_kwargs):
    raise httpx.ConnectError("ollama down")


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


def _enable_online(monkeypatch, online_id=ONLINE_ID):
    provider, _m = online_id.split(":", 1)
    monkeypatch.setenv("ONLINE_MODELS", online_id)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", FAKE_KEY)


# ---------- create_chat_model 分发 ----------

def test_online_id_returns_chat_openai(monkeypatch):
    _enable_online(monkeypatch)
    model = create_chat_model(ONLINE_ID)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-chat"
    assert model.openai_api_base == "https://api.deepseek.com"


def test_local_name_returns_chat_ollama(monkeypatch):
    # 未配置 ONLINE_MODELS：本地名走原样 ChatOllama 分支（行为不变）。
    model = create_chat_model(LOCAL_NAME)
    assert isinstance(model, ChatOllama)
    assert model.client_kwargs["trust_env"] is False
    assert model.async_client_kwargs["trust_env"] is False
    assert model.sync_client_kwargs["trust_env"] is False
    assert model.base_url == config.OLLAMA_BASE_URL


def test_nonexistent_name_falls_through_to_chat_ollama(monkeypatch):
    # 既不在线上注册表、本地也未枚举时，仍按原样构造 ChatOllama（不发起网络）。
    model = create_chat_model("does-not-exist:xyz")
    assert isinstance(model, ChatOllama)
    assert model.client_kwargs["trust_env"] is False


def test_empty_registry_local_name_still_chat_ollama(monkeypatch):
    monkeypatch.setenv("ONLINE_MODELS", "")
    model = create_chat_model(LOCAL_NAME)
    assert isinstance(model, ChatOllama)
    assert model.base_url == config.OLLAMA_BASE_URL


def test_reasoning_passthrough_for_local_chat_ollama(monkeypatch):
    model = create_chat_model(LOCAL_NAME, reasoning=True)
    assert isinstance(model, ChatOllama)
    assert model.reasoning is True
    model_false = create_chat_model(LOCAL_NAME, reasoning=False)
    assert model_false.reasoning is False


# ---------- 线上分支对 reasoning 的忽略 + 日志 ----------

@pytest.mark.parametrize("reasoning", [True, False, None, "xhigh"])
def test_online_ignores_reasoning_and_logs_debug(monkeypatch, caplog, reasoning):
    _enable_online(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        model = create_chat_model(ONLINE_ID, reasoning=reasoning)
    assert isinstance(model, ChatOpenAI)
    # api_key 绝不出现在任何日志中
    for record in caplog.records:
        assert FAKE_KEY not in record.getMessage()
    # reasoning 不为 None 时打 debug 忽略日志；为 None 时不打
    messages = [r.getMessage() for r in caplog.records]
    if reasoning is not None:
        assert any("线上模型不支持 think 参数，已忽略" in m for m in messages)
    else:
        assert not any("线上模型不支持 think 参数，已忽略" in m for m in messages)


def test_online_api_key_not_leaked_in_logs(monkeypatch, caplog):
    _enable_online(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        create_chat_model(ONLINE_ID, reasoning=True)
    for record in caplog.records:
        assert FAKE_KEY not in record.getMessage()


# ---------- 线上模型被删除 → 回退 ChatOllama ----------

def test_online_model_removed_falls_back_to_chat_ollama(monkeypatch):
    _enable_online(monkeypatch)
    # 前置：删除前能返回 ChatOpenAI
    assert isinstance(create_chat_model(ONLINE_ID), ChatOpenAI)
    # 模拟该线上模型被删除（注册表查不到）
    monkeypatch.setattr(
        "backend.app.platform.model_catalog.get_online_model", lambda _id: None
    )
    model = create_chat_model(ONLINE_ID)
    assert isinstance(model, ChatOllama)
    assert model.client_kwargs["trust_env"] is False


# ---------- is_model_available：本地 ∪ 线上 并集 ----------

def test_is_available_online_hit(monkeypatch):
    _enable_online(monkeypatch)
    assert is_model_available(ONLINE_ID) is True


def test_is_available_local_hit(monkeypatch):
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models",
        lambda: [LOCAL_NAME],
    )
    assert is_model_available(LOCAL_NAME) is True


def test_is_available_both_miss(monkeypatch):
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models",
        lambda: ["other:local"],
    )
    assert is_model_available("nope:model") is False


def test_is_available_empty_name(monkeypatch):
    assert is_model_available("") is False
    assert is_model_available(None) is False  # type: ignore[arg-type]


def test_is_available_ollama_unreachable_online_still_true(monkeypatch):
    # Ollama 不可达（本地枚举抛异常），但线上注册表仍命中 → True
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", _raise_connect
    )
    _enable_online(monkeypatch)
    assert is_model_available(ONLINE_ID) is True


def test_is_available_ollama_unreachable_no_online_false(monkeypatch):
    # Ollama 不可达且无线上模型 → False
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", _raise_connect
    )
    assert is_model_available(LOCAL_NAME) is False


def test_is_available_online_registry_fails_local_still_true(monkeypatch):
    # 反之：线上侧异常，本地侧仍命中 → True（单侧失败互不影响）
    monkeypatch.setattr(
        "backend.app.platform.model_catalog.get_online_model",
        _raise_connect,
    )
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models",
        lambda: [LOCAL_NAME],
    )
    assert is_model_available(LOCAL_NAME) is True
