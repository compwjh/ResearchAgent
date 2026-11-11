"""含 API key 形状字段的 payload 隐私回归 + thinking 正文可见性（真实链路复核）。

与既有的值级脱敏契约测试互补：这里走**真实写入链路**——
`MemoryRepository.append_raw_event`（真实 SQLite）、`routes_conversations._redact_sensitive`、
`spans.record_ollama_generation`（真实上报函数，仅把 Langfuse client 换成内存捕获桩），
验证：
① payload 含 api_key / Bearer / URL userinfo / Authorization 形状字段时凭据不落地；
② 学术文本里出现 "token" 一词不被误伤（不过度脱敏）；
③ thinking 正文仍逐字可见（凭据过滤不得把思考正文一起抹掉）；
④ 统一 request_id 仍写入落盘 payload。

说明：这是可重复的链路级回归护栏，非真实 E2E；真实 E2E 隐私取证见
`docs/sdd/plans/045/runs/task-08/sdk-smoke.json` 的 privacy_real_chain 段。

运行：
  .venv/bin/python -m pytest tests/observability/test_privacy_thinking_chain.py -q
"""

import contextlib
import json
from unittest import mock

import pytest

from backend.app.api.routes_conversations import _redact_sensitive
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability import request_id as rid_mod
from backend.app.platform.observability.spans import record_ollama_generation
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings

# —— 精确凭据样本（全部为合成占位串，不是真实密钥）——
SK = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnopqrstuvwxyz"
URL = "https://alice:s3cr3t-pass@api.example.com/v1/data"
PLAIN_MARKERS = (SK, BEARER_TOKEN, "s3cr3t-pass", "alice:s3cr3t-pass@")
THINKING_TEXT = "先检索再推理，最后汇总证据"
ACADEMIC_TEXT = "论文标题：token 化与 attention 机制研究"

CRED_TEXT = (
    f"请用 api_key={SK} 与 Authorization: Bearer {BEARER_TOKEN} 访问 {URL} 完成调研"
)


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


def _capture_client(captured):
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


@pytest.fixture(autouse=True)
def _clean():
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()
    yield
    obs_client.reset_for_tests()
    obs_config.reset_sample_decision()
    rid_mod.reset_request_id()


@pytest.fixture
def repo(tmp_path):
    return MemoryRepository(tmp_path / "memory.sqlite3")


def _enabled(captured):
    return (
        mock.patch.object(config, "LANGFUSE_ENABLED", True),
        mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"),
        mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"),
        mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "1.0"),
        mock.patch.object(obs_client, "get_client", return_value=_capture_client(captured)),
    )


# ---------------------------------------------------------------- ① 凭据不落地

def test_raw_event_payload_with_api_key_shaped_fields_has_no_plaintext(repo):
    """payload 含 api_key / Bearer / URL 形状字段，落盘后不得含任何明文凭据。"""
    cid = repo.create_conversation(OWNER_ID).conversation_id
    # 值级精确凭据模式（redaction.py 声明的契约）：sk-* / Bearer / URL userinfo /
    # 显式 key=value 赋值。"按 key 名过滤裸 token" 属已知边界，见本文件末尾的
    # test_key_named_credential_with_opaque_value_is_documented_boundary 与交付报告。
    payload = {
        "content": CRED_TEXT,
        "api_key": SK,
        "authorization": f"Bearer {BEARER_TOKEN}",
        "endpoint": URL,
        "note": "普通文本",
        "nested": {"secret": f"secret={SK}", "token": f"Bearer {BEARER_TOKEN}"},
    }
    event = repo.append_raw_event(OWNER_ID, cid, "user_message", payload)

    stored_rows = repo.list_raw_events(cid, OWNER_ID)
    assert len(stored_rows) == 1
    encoded = json.dumps(stored_rows[0].payload, ensure_ascii=False)
    for marker in PLAIN_MARKERS:
        assert marker not in encoded, f"raw_events.payload 仍含明文 {marker!r}"
    assert "[REDACTED]" in encoded, "应发生值级替换而非整段丢弃"
    assert "普通文本" in encoded
    assert "完成调研" in encoded
    assert event.event_id, "脱敏后事件本身不得被丢弃"


def test_langfuse_input_with_api_key_shaped_prompt_has_no_plaintext():
    """prompt 含 api_key/Bearer/URL 时，上报 Langfuse 的 input 不含明文凭据。"""
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
    assert "完成调研" in reported, "只做值级过滤，不整段清空 prompt"


def test_route_layer_redaction_drops_api_key_shaped_credentials():
    """SSE 错误/进度摘要走同一处值级过滤，凭据不进摘要。"""
    out = _redact_sensitive(CRED_TEXT)
    for marker in PLAIN_MARKERS:
        assert marker not in out, f"路由层摘要仍含明文 {marker!r}"
    assert "完成调研" in out


# ---------------------------------------------------------------- ② 不过度脱敏

def test_academic_text_mentioning_token_survives_all_three_paths(repo):
    """含 token 一词的普通学术文本在三套写入路径都逐字保留。"""
    cid = repo.create_conversation(OWNER_ID).conversation_id
    event = repo.append_raw_event(
        OWNER_ID, cid, "user_message", {"content": ACADEMIC_TEXT}
    )
    assert event.payload["content"] == ACADEMIC_TEXT
    assert _redact_sensitive(ACADEMIC_TEXT) == ACADEMIC_TEXT

    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m",
            prompt_messages=[{"role": "user", "content": ACADEMIC_TEXT}],
            result=_result(),
            route="direct",
        )
    assert ACADEMIC_TEXT in captured["starts"][0]["input"]


# ---------------------------------------------------------------- ③ thinking 仍可见

def test_thinking_text_still_visible_when_prompt_contains_api_key():
    """凭据被过滤的同时，thinking 正文必须在 generation 独立字段逐字可见。"""
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

    assert len(captured["update"]) == 1, "generation.update 仍应恰好一次"
    update = captured["update"][0]
    independent = update.get("thinking")
    if independent is None:
        independent = (update.get("metadata") or {}).get("thinking")
    assert independent == THINKING_TEXT, "thinking 正文必须逐字可读"

    # 正文与正式输出分离
    assert update["output"] == "答案"
    assert THINKING_TEXT not in update["output"]
    # 既有 allowlist 字段保留
    metadata = captured["starts"][0]["metadata"]
    assert metadata["reasoning_present"] is True
    assert metadata["reasoning_chars"] == len(THINKING_TEXT)

    # 上报内容整体不含明文凭据
    reported_blob = json.dumps(captured, ensure_ascii=False, default=str)
    for marker in PLAIN_MARKERS:
        assert marker not in reported_blob, f"上报内容仍含明文 {marker!r}"


def test_thinking_absent_does_not_invent_thinking_field():
    """无思考正文时不得凭空新增 thinking 字段。"""
    captured = {}
    with contextlib.ExitStack() as stack:
        for patch in _enabled(captured):
            stack.enter_context(patch)
        record_ollama_generation(
            model="m",
            prompt_messages=[{"role": "user", "content": "q"}],
            result=_result(thinking=""),
            route="direct",
        )
    assert len(captured["update"]) == 1
    assert "thinking" not in captured["update"][0]
    assert captured["starts"][0]["metadata"]["reasoning_present"] is False


# ---------------------------------------------------------------- 已知边界（如实记录）

def test_key_named_credential_with_opaque_value_is_documented_boundary():
    """KNOWN LIMITATION（已回报主会话，不属本次修复范围）：

    ``redaction.redact_value`` 只按**值**里的精确凭据正则替换，不按 dict 的
    **key 名**过滤。因此形如 ``{"api_key": "<无 sk-/Bearer/URL 特征的裸串>"}``
    的字段不会被替换。这是 redaction.py:9-13 明确的设计取舍
    （「不按 token 之类宽泛关键字过滤，避免误伤正常的学术文本」），
    但对「payload 含 API key 形状字段」仍是一处残余风险。

    本用例只**刻画当前真实行为**，绝不宣称该场景已满足脱敏；若主会话决定
    补 key 名白名单，本断言应随之更新。复现命令见交付报告。
    """
    from backend.app.platform.observability import redaction

    opaque = "opaqueBareSecret0123456789"
    out = redaction.redact_payload({"api_key": opaque, "token": opaque})
    assert out["api_key"] == opaque, "当前实现不按 key 名过滤（已知边界）"
    assert out["token"] == opaque
    # 对照：一旦值里出现精确模式，仍必须被替换
    assert redaction.redact_payload({"api_key": SK})["api_key"] == "[REDACTED]"


# ---------------------------------------------------------------- ④ request_id 串联

def test_raw_event_payload_keeps_unified_request_id(repo):
    """脱敏 + 截断后仍带统一 request_id，三套记录可用同一 ID 串联。"""
    rid = rid_mod.bind_request_id()
    cid = repo.create_conversation(OWNER_ID).conversation_id
    event = repo.append_raw_event(
        OWNER_ID, cid, "user_message", {"content": CRED_TEXT}
    )
    assert event.payload.get("request_id") == rid
    assert "truncated" not in event.payload
