"""spec-045 Task 06 红测：链路标识与脱敏统一（先红后绿）。

四类验收：
① prompt 含 sk-* / Bearer / URL userinfo 时三处落盘均不含明文；
② 超长 raw_events.payload 被截断并带标记（不丢事件）；
③ 同一次请求三套记录 ID 一致；
④ 思考正文在 generation 独立字段可读（与 content 分离）。

未实现的新模块用方法内延迟导入（对齐 test_task05_decoupling 的做法），
缺失只让对应用例失败，不破坏整模块收集。
"""

import contextlib
import json
from unittest import mock

import pytest

from backend.app.memory.repository import MemoryRepository, OWNER_ID
from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.spans import (
    record_ollama_generation,
    record_routing_observation,
    redact_prompt_messages,
)
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

# 精确凭据样本：sk-* / Bearer / URL userinfo
SK = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnopqrstuvwxyz"
BEARER = f"Bearer {BEARER_TOKEN}"
URL = "https://alice:s3cr3t-pass@api.example.com/v1/data"
CRED_TEXT = f"请用 {SK} 与 {BEARER} 访问 {URL} 完成调研"
PLAIN_MARKERS = (SK, BEARER_TOKEN, "s3cr3t-pass", "alice:s3cr3t-pass@")

# raw_events.payload 上限（与 repository 既有 _PROCESSING_DETAIL_MAX_CHARS 同口径）
MAX_RAW_EVENT_PAYLOAD_CHARS = 4000

THINKING_TEXT = "先检索再推理，最后汇总证据"


def _result(**overrides):
    payload = {
        "content": "答案",
        "thinking": THINKING_TEXT,
        "timings": OllamaTimings(
            load_ms=7000.0, prompt_eval_ms=300.0, eval_ms=1100.0,
            total_ms=8400.0, prompt_tokens=15, completion_tokens=27,
        ),
        "timings_available": True,
        "first_token_ms": 7300.0,
        "client_wall_ms": 8500.0,
        "chunk_intervals_ms": (40.0, 41.0),
    }
    payload.update(overrides)
    return OllamaChatResult(**payload)


@pytest.fixture(autouse=True)
def _clean_observability():
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    yield
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    try:
        from backend.app.platform.observability import request_id as rid_mod
    except ImportError:
        return
    rid_mod.reset_request_id()


@pytest.fixture
def repo(tmp_path):
    return MemoryRepository(tmp_path / "memory.sqlite3")


def _conversation(repository):
    return repository.create_conversation(OWNER_ID).conversation_id


def _fake_client(captured):
    class _Observation:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, **kwargs):
            captured.setdefault("update", []).append(kwargs)

        def score(self, **kwargs):
            captured.setdefault("scores", []).append(kwargs)

    class _Client:
        def create_trace_id(self):
            return "a" * 32

        def start_as_current_observation(self, **kwargs):
            captured.setdefault("starts", []).append(kwargs)
            return _Observation()

    return _Client()


def _enabled(captured):
    """启用 Langfuse 并固定采样为 True，使上报路径稳定可断言。"""
    return (
        mock.patch.object(config, "LANGFUSE_ENABLED", True),
        mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"),
        mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"),
        mock.patch.object(obs_config, "should_sample", return_value=True),
        mock.patch.object(obs_client, "get_client", return_value=_fake_client(captured)),
    )


def _load_request_id():
    try:
        from backend.app.platform.observability import request_id as rid_mod
    except ImportError:
        pytest.fail("统一 request_id 模块缺失（Task 06 未实现）")
    return rid_mod


# ---------------------------------------------------------------- ① 凭据不落地

def test_langfuse_input_has_no_plaintext_credentials():
    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m",
            prompt_messages=[{"role": "user", "content": CRED_TEXT}],
            result=_result(),
            route="direct",
        )
    reported = captured["starts"][0]["input"]
    for marker in PLAIN_MARKERS:
        assert marker not in reported, f"Langfuse input 仍含明文 {marker!r}"
    # spec-041 裁决：只做值级凭据过滤，不整段清空 prompt
    assert "完成调研" in reported


def test_raw_events_payload_has_no_plaintext_credentials(repo):
    cid = _conversation(repo)
    event = repo.append_raw_event(
        OWNER_ID, cid, "user_message",
        {"content": CRED_TEXT, "note": "普通文本"},
    )
    stored = json.dumps(event.payload, ensure_ascii=False)
    for marker in PLAIN_MARKERS:
        assert marker not in stored, f"raw_events.payload 仍含明文 {marker!r}"
    assert "普通文本" in stored
    assert "完成调研" in stored


def test_route_layer_redaction_has_no_plaintext_credentials():
    from backend.app.api.routes_conversations import _redact_sensitive

    out = _redact_sensitive(CRED_TEXT)
    for marker in PLAIN_MARKERS:
        assert marker not in out, f"路由层脱敏输出仍含明文 {marker!r}"
    assert "完成调研" in out


def test_redact_prompt_messages_keeps_non_credential_text():
    out = redact_prompt_messages([{"role": "user", "content": CRED_TEXT}])
    for marker in PLAIN_MARKERS:
        assert marker not in out[0]["content"]
    assert "完成调研" in out[0]["content"]


def test_academic_text_mentioning_token_is_not_redacted():
    """精确凭据模式不得误伤含 token 一词的普通学术文本。"""
    original = "论文标题：token 化与 attention 机制研究"
    out = redact_prompt_messages([{"role": "user", "content": original}])
    assert out[0]["content"] == original


def test_routing_decision_metadata_has_no_plaintext_credentials():
    captured = {}
    with mock.patch(
        "backend.app.platform.observability.spans.record_event",
        side_effect=lambda **kwargs: captured.update(kwargs),
    ):
        record_routing_observation(
            task_type="t", features={}, candidate_models=[],
            chosen_model="m", reason=CRED_TEXT, policy_version="v",
        )
    # 非恒真 / 非静默失效：记录必须真的落盘，而不是被敏感校验整条拒绝后
    # 拿空 dict 比对（regression-guard 第 12 条）。
    assert captured, "路由决策记录不应被整条拒绝（值级脱敏后应正常落盘）"
    assert "完成调研" in captured["metadata"]["reason"]
    encoded = json.dumps(captured["metadata"], ensure_ascii=False)
    for marker in PLAIN_MARKERS:
        assert marker not in encoded, f"路由决策记录仍含明文 {marker!r}"


# ---------------------------------------------------------------- ② payload 上限

def test_oversized_raw_event_payload_is_truncated_and_flagged(repo):
    cid = _conversation(repo)
    event = repo.append_raw_event(
        OWNER_ID, cid, "user_message",
        {"content": "A" * 50000, "kind": "long"},
    )
    # 不丢事件：行仍落库且可读回
    assert event.event_id
    assert event.event_kind == "user_message"
    stored = repo.list_raw_events(cid, OWNER_ID)
    assert len(stored) == 1
    # 有大小上限
    encoded = json.dumps(stored[0].payload, ensure_ascii=False, sort_keys=True)
    assert len(encoded) <= MAX_RAW_EVENT_PAYLOAD_CHARS
    # 带截断标记
    assert stored[0].payload.get("truncated") is True


def test_small_raw_event_payload_is_not_flagged(repo):
    cid = _conversation(repo)
    event = repo.append_raw_event(OWNER_ID, cid, "user_message", {"content": "短文本"})
    assert event.payload["content"] == "短文本"
    assert "truncated" not in event.payload


def test_oversized_payload_still_carries_request_id(repo):
    rid_mod = _load_request_id()
    rid = rid_mod.bind_request_id()
    cid = _conversation(repo)
    event = repo.append_raw_event(
        OWNER_ID, cid, "user_message", {"content": "A" * 50000},
    )
    assert event.payload.get("request_id") == rid
    assert event.payload.get("truncated") is True


# ---------------------------------------------------------------- ③ 三套 ID 一致

def test_same_request_id_in_langfuse_raw_events_and_routing(repo):
    rid_mod = _load_request_id()
    rid = rid_mod.bind_request_id()

    cid = _conversation(repo)
    raw = repo.append_raw_event(OWNER_ID, cid, "user_message", {"content": "hi"})
    assert raw.payload.get("request_id") == rid

    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m", prompt_messages=[{"role": "user", "content": "hi"}],
            result=_result(), route="direct",
        )
    assert captured["starts"][0]["metadata"].get("request_id") == rid

    routing = {}
    with mock.patch(
        "backend.app.platform.observability.spans.record_event",
        side_effect=lambda **kwargs: routing.update(kwargs),
    ):
        record_routing_observation(
            task_type="t", features={}, candidate_models=[],
            chosen_model="m", reason="r", policy_version="v",
        )
    assert routing["metadata"].get("request_id") == rid
    # 三者确实是同一个值，且非空（非恒真断言）
    assert rid
    assert raw.payload["request_id"] == captured["starts"][0]["metadata"]["request_id"]


def test_langfuse_trace_metadata_uses_request_id():
    from backend.app.platform.observability.trace import end_trace, start_trace

    rid_mod = _load_request_id()
    rid = rid_mod.bind_request_id()
    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        tid = start_trace("kb-ask", tags=["kb"])
    assert tid == rid
    assert captured["starts"][0]["metadata"].get("request_id") == rid
    end_trace()


def test_two_requests_get_distinct_ids_and_reset_clears():
    rid_mod = _load_request_id()
    first = rid_mod.bind_request_id()
    rid_mod.reset_request_id()
    second = rid_mod.bind_request_id()
    rid_mod.reset_request_id()
    assert first != second
    assert rid_mod.get_request_id() is None


def test_request_id_rebinding_survives_sse_yield_boundary():
    """SSE generator 的 ContextVar 跨 yield 会丢，按同一 rid 重新绑定后仍一致。"""
    rid_mod = _load_request_id()
    rid = rid_mod.bind_request_id()
    rid_mod.reset_request_id()  # 模拟跨 yield 后 ContextVar 为空的新段
    assert rid_mod.get_request_id() is None
    assert rid_mod.bind_request_id(rid) == rid
    assert rid_mod.ensure_request_id() == rid


# ---------------------------------------------------------------- ④ thinking 正文

def test_thinking_text_is_reported_in_independent_field():
    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m", prompt_messages=[{"role": "user", "content": "q"}],
            result=_result(), route="direct",
        )

    # generation.update 只能有一次（既有 test_long_output_is_truncated 契约）
    updates = captured["update"]
    assert len(updates) == 1
    update = updates[0]
    # 与 content 分离：正式输出里不含思考正文
    assert update["output"] == "答案"
    assert THINKING_TEXT not in update["output"]
    # 独立字段承载思考正文，且逐字可读
    independent = update.get("thinking")
    if independent is None:
        independent = (update.get("metadata") or {}).get("thinking")
    assert independent == THINKING_TEXT

    # 既有字段保留，不破坏 Spec024 allowlist 测试
    metadata = captured["starts"][0]["metadata"]
    assert metadata["reasoning_present"] is True
    assert metadata["reasoning_chars"] == len(THINKING_TEXT)
    assert "thinking" not in metadata
    assert THINKING_TEXT not in repr(metadata)


def test_thinking_absent_does_not_add_empty_field():
    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m", prompt_messages=[{"role": "user", "content": "q"}],
            result=_result(thinking=""), route="direct",
        )
    assert len(captured["update"]) == 1
    assert captured["update"][0]["output"] == "答案"
    assert captured["starts"][0]["metadata"]["reasoning_present"] is False
