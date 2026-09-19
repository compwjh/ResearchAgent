"""Spec 026 Task 02 — 能力探测失败语义与 default_effort 修正（后端契约测试）。

覆盖边界 B1/B2/B3/B4/B16：
- 5 档探测全失败不再抛异常，返回 ``unknown``（空支持集、``default_effort=None``）。
- ``default_effort`` 取「支持的最高档」（``_highest_supported``）。
- 无缓存 + 探测失败 → ``unknown``；有（过期）缓存 + 探测失败 → ``stale`` 且保留旧 ``cached_at``。
- ``refresh=True`` 真正绕过缓存重新探测。
- 探测失败不得删除/污染既有缓存条目（B16）。
"""

import time

import httpx
import pytest

from backend.app.platform import ollama
from backend.app.platform.ollama import (
    ReasoningCapabilities,
    _highest_supported,
    get_reasoning_capabilities,
    probe_reasoning_capabilities,
)


@pytest.fixture(autouse=True)
def _isolated_capability_cache():
    ollama.clear_reasoning_capability_cache()
    yield
    ollama.clear_reasoning_capability_cache()


def _post_raising(*_args, **_kwargs):
    raise httpx.ConnectError("ollama down")


def _post_non_200(*_args, **_kwargs):
    class _Response:
        status_code = 503
        content = b""

        def json(self):
            return {}

    return _Response()


def _post_all_ok(url, *, json, timeout, trust_env):  # noqa: A002 - mirrors httpx.post kwargs
    think = json.get("think")
    thinking = "" if think is False else "draft"

    class _Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return {"message": {"content": "OK", "thinking": thinking}}

    return _Response()


# --- 1) 探测全失败不再抛异常，返回 unknown（空支持集，不得回退为 ('off',)） ---

def test_probe_all_efforts_fail_returns_unknown_capabilities_without_raising(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", _post_raising)

    caps = probe_reasoning_capabilities("m")

    assert caps.source == "unknown"
    assert caps.supported_efforts == ()
    assert caps.default_effort is None


def test_probe_all_non_200_returns_unknown_capabilities(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", _post_non_200)

    caps = probe_reasoning_capabilities("m")

    assert caps.source == "unknown"
    assert caps.supported_efforts == ()
    assert caps.default_effort is None


# --- 2) default_effort 取支持的最高档 ---

@pytest.mark.parametrize(
    "supported,expected",
    [
        (("off", "low", "medium"), "medium"),
        (("off", "xhigh"), "xhigh"),
        (("off",), "off"),
        (("off", "low", "medium", "high", "xhigh"), "xhigh"),
        (("medium", "off", "low"), "medium"),  # 输入乱序也按 REASONING_EFFORTS 序位判定
        ((), None),
    ],
)
def test_highest_supported_effort_picks_ordering_top(supported, expected):
    assert _highest_supported(supported) == expected


def test_probe_default_reasoning_effort_is_highest_supported(monkeypatch):
    def partial_post(url, *, json, timeout, trust_env):  # noqa: A002
        think = json.get("think")
        effort = "off" if think is False else ("xhigh" if think is True else think)
        ok = effort in {"off", "low", "medium"}

        class _Response:
            status_code = 200 if ok else 500
            content = b"{}"

            def json(self):
                return {"message": {"content": "OK", "thinking": "" if effort == "off" else "draft"}}

        return _Response()

    monkeypatch.setattr(ollama.httpx, "post", partial_post)

    caps = probe_reasoning_capabilities("m")

    assert caps.supported_efforts == ("off", "low", "medium")
    assert caps.default_effort == "medium"  # 旧实现会给最低档 off


# --- 3) unknown：无缓存 + 探测失败 ---

def test_reasoning_capabilities_unknown_when_no_cache_and_probe_fails(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", _post_raising)

    caps = get_reasoning_capabilities("m")

    assert caps.source == "unknown"
    assert caps.supported_efforts == ()
    assert caps.default_effort is None
    assert "m" not in ollama._capability_cache


# --- 3b) stale：存在过期旧缓存 + 探测失败，保留旧 cached_at ---

def test_reasoning_capabilities_stale_reuses_old_cached_at(monkeypatch):
    old_caps = ReasoningCapabilities(
        "m", ("off", "low", "medium"), "medium", "ollama_probe", "2026-09-01T00:00:00+00:00", {"medium": "e"}
    )
    ollama._capability_cache["m"] = (time.monotonic() - 10_000.0, old_caps)  # 远超 300s TTL
    monkeypatch.setattr(ollama.httpx, "post", _post_raising)

    caps = get_reasoning_capabilities("m")

    assert caps.source == "stale"
    assert caps.supported_efforts == ("off", "low", "medium")
    assert caps.default_effort == "medium"
    assert caps.cached_at == "2026-09-01T00:00:00+00:00"


# --- 4) refresh=True 真正绕过缓存 ---

def test_reasoning_capabilities_refresh_bypasses_cache(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", _post_all_ok)

    first = get_reasoning_capabilities("m")
    assert first.source == "ollama_probe"

    cached = get_reasoning_capabilities("m")
    assert cached.source == "cache"

    refreshed = get_reasoning_capabilities("m", refresh=True)
    assert refreshed.source == "ollama_probe"


# --- 5) B16：探测失败不得删除/污染既有缓存条目 ---

def test_reasoning_capabilities_failed_probe_keeps_existing_cache(monkeypatch):
    monkeypatch.setattr(ollama.httpx, "post", _post_all_ok)
    good = get_reasoning_capabilities("m")
    assert good.source == "ollama_probe"
    stored_before = ollama._capability_cache["m"]

    monkeypatch.setattr(ollama.httpx, "post", _post_raising)
    stale = get_reasoning_capabilities("m", refresh=True)

    assert stale.source == "stale"
    stored_after = ollama._capability_cache["m"]
    assert stored_after[1] is stored_before[1]
    assert stored_after[0] == stored_before[0]
    assert get_reasoning_capabilities("m").source == "cache"
