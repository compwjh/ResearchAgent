"""受控评测传输与 Langfuse 导出契约测试（完全离线）。

所有 HTTP 场景都使用内存 response、fake opener 或 monkeypatch；本文件不
启动 HTTP 服务，也不允许测试意外触发真实网络连接。
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.eval_042 import langfuse_export, offline_guard
from backend.eval_042.langfuse_export import (
    EmptyTraceExportError,
    ScoreResponseError,
)
from backend.eval_042.offline_guard import OfflineGuardError


class _MemoryResponse:
    """最小的 urllib response 替身，支持 ``with`` 与 ``read``。"""

    def __init__(self, payload: object):
        self._raw = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._raw


class _SequenceOpener:
    """按调用顺序返回内存 response 或抛出预先构造的异常。"""

    def __init__(self, outcomes, seen):
        self._outcomes = list(outcomes)
        self._seen = seen
        self._index = 0

    def open(self, request, *, timeout):
        self._seen.append((request, timeout))
        outcome = self._outcomes[min(self._index, len(self._outcomes) - 1)]
        self._index += 1
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _http_error(code: int):
    return urllib.error.HTTPError(
        "http://127.0.0.1:3000/api/public/scores",
        code,
        f"status {code}",
        {},
        None,
    )


def _install_fake_opener(monkeypatch, outcomes):
    seen = []
    opener = _SequenceOpener(outcomes, seen)
    monkeypatch.setattr(
        offline_guard,
        "build_offline_opener",
        lambda: opener,
    )
    return seen


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:3000/api",
        "file:///tmp/langfuse.json",
        "ftp://127.0.0.1:3000/api",
        "http://user@localhost:3000/api",
        "http://user:password@127.0.0.1:3000/api",
        "http://example.com:3000/api",
    ],
)
def test_offline_transport_rejects_non_http_non_loopback_or_userinfo(
    monkeypatch, url
):
    opened = []

    def fail_if_opened():
        opened.append(True)
        raise AssertionError("guard rejection must happen before opener creation")

    monkeypatch.setattr(offline_guard, "build_offline_opener", fail_if_opened)

    with pytest.raises(OfflineGuardError):
        offline_guard.offline_urlopen(url)

    assert opened == []


def test_offline_opener_disables_environment_proxy_without_changing_global_opener(
    monkeypatch,
):
    monkeypatch.setenv("HTTP_PROXY", "http://outside.example:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://outside.example:8080")
    monkeypatch.setattr(
        urllib.request,
        "getproxies",
        lambda: pytest.fail("environment proxy discovery must not be used"),
    )
    sentinel = object()
    monkeypatch.setattr(urllib.request, "_opener", sentinel)

    opener = offline_guard.build_offline_opener()

    # An empty ProxyHandler has no protocol callbacks and is omitted by
    # build_opener; importantly, no environment proxy discovery was invoked.
    assert not any(
        hasattr(handler, "proxy_open") for handler in opener.handlers
    )
    assert urllib.request._opener is sentinel


@pytest.mark.parametrize("code", [300, 301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1:3000/api/public/traces",
        "https://outside.example/redirect",
    ],
)
def test_redirect_handler_rejects_loopback_and_external_locations(code, location):
    request = urllib.request.Request("http://127.0.0.1:3000/api/public/traces")
    handler = offline_guard._RejectRedirectHandler()

    with pytest.raises(OfflineGuardError, match="redirect"):
        getattr(handler, f"http_error_{code}")(
            request,
            None,
            code,
            "redirect",
            {"Location": location},
        )


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(lambda: _http_error(429), id="http-429"),
        pytest.param(lambda: _http_error(503), id="http-5xx"),
        pytest.param(lambda: TimeoutError("read timeout"), id="timeout"),
        pytest.param(lambda: urllib.error.URLError(socket.timeout()), id="url-timeout"),
    ],
)
def test_get_retries_only_transient_failures_at_most_three_times(
    monkeypatch, failure
):
    url = "http://127.0.0.1:3000/api/public/traces"
    seen = _install_fake_opener(monkeypatch, [failure, failure, failure])
    sleeps = []
    guards = []
    original_guard = offline_guard.assert_loopback
    monkeypatch.setattr(offline_guard.time, "sleep", sleeps.append)

    def observe_guard(value):
        guards.append(value)
        return original_guard(value)

    monkeypatch.setattr(offline_guard, "assert_loopback", observe_guard)

    with pytest.raises((urllib.error.HTTPError, TimeoutError, urllib.error.URLError)):
        offline_guard.http_get_json(url, max_attempts=99)

    assert len(seen) == 3
    assert len(guards) == 3
    assert guards == [url, url, url]
    assert sleeps == [0.05, 0.1]


def test_get_returns_after_transient_failures_and_does_not_exceed_three_attempts(
    monkeypatch,
):
    url = "http://127.0.0.1:3000/api/public/traces"
    seen = _install_fake_opener(
        monkeypatch,
        [lambda: _http_error(500), lambda: TimeoutError("timeout"), _MemoryResponse({"ok": True})],
    )
    sleeps = []
    monkeypatch.setattr(offline_guard.time, "sleep", sleeps.append)

    assert offline_guard.http_get_json(url, max_attempts=3) == {"ok": True}
    assert len(seen) == 3
    assert [request.get_method() for request, _ in seen] == ["GET", "GET", "GET"]
    assert sleeps == [0.05, 0.1]


@pytest.mark.parametrize(
    "failure,expected",
    [
        (lambda: _http_error(400), urllib.error.HTTPError),
        (lambda: _http_error(401), urllib.error.HTTPError),
        (lambda: _MemoryResponse(b"not-json"), ValueError),
    ],
)
def test_get_does_not_retry_auth_parameter_or_json_errors(
    monkeypatch, failure, expected
):
    seen = _install_fake_opener(monkeypatch, [failure, failure, failure])
    monkeypatch.setattr(offline_guard.time, "sleep", lambda _: pytest.fail("unexpected retry"))

    with pytest.raises(expected):
        offline_guard.http_get_json("http://127.0.0.1:3000/api/public/traces")

    assert len(seen) == 1


def test_score_post_is_exactly_once_and_carries_json_payload(monkeypatch):
    seen = _install_fake_opener(monkeypatch, [_MemoryResponse({"id": "score-1"})])
    monkeypatch.setattr(langfuse_export, "LANGFUSE_BASE", "http://127.0.0.1:3000")

    result = langfuse_export.post_score(
        "chat_quality",
        1.0,
        "trace-1",
        "Explanation: complete. Answer: good",
    )

    assert result["id"] == "score-1"
    assert len(seen) == 1
    request, timeout = seen[0]
    assert timeout == 30
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {
        "name": "chat_quality",
        "value": 1.0,
        "traceId": "trace-1",
        "comment": "Explanation: complete. Answer: good",
    }


def test_score_post_does_not_retry_after_transport_failure(monkeypatch):
    seen = _install_fake_opener(monkeypatch, [lambda: _http_error(503)])
    monkeypatch.setattr(langfuse_export, "LANGFUSE_BASE", "http://127.0.0.1:3000")

    with pytest.raises(urllib.error.HTTPError):
        langfuse_export.post_score("chat_quality", 0.0, "trace-1", "failed")

    assert len(seen) == 1


def test_prior_context_uses_only_explicit_trace_or_metadata_fields():
    assert langfuse_export.extract_prior_context(
        {"input": "prior_context: should not be inferred", "output": "answer"}
    ) is None
    assert langfuse_export.extract_prior_context(
        {"context": "unknown field", "metadata": {"context": "also unknown"}}
    ) is None
    assert langfuse_export.extract_prior_context(
        {"prior_context": "direct", "metadata": {"prior_context": "metadata"}}
    ) == "direct"
    assert langfuse_export.extract_prior_context(
        {"metadata": {"prior_context": "metadata"}}
    ) == "metadata"


def test_memory_context_mapping_and_missing_context_skip_are_explicit():
    from_metadata = langfuse_export.build_eval_item(
        "trace-1",
        "What coffee do I prefer?",
        "You prefer espresso.",
        task="memory_correctness",
        prior_context="User prefers espresso.",
    )
    assert from_metadata.prior_context == "User prefers espresso."
    assert from_metadata.status == "scored"
    assert from_metadata.skip_reason is None

    missing = langfuse_export.build_eval_item(
        "trace-2",
        "What coffee do I prefer?",
        "You prefer espresso.",
        task="memory_correctness",
    )
    assert missing.prior_context is None
    assert missing.status == "skipped"
    assert missing.skip_reason == "no_prior_context"


def test_empty_real_export_is_not_masked_by_synthetic_fixtures(monkeypatch):
    monkeypatch.setattr(langfuse_export, "list_ollama_chat_trace_ids", lambda limit: [])

    with pytest.raises(EmptyTraceExportError, match="zero real"):
        langfuse_export.collect_eval_items(
            n_scoreable=0,
            n_intake_fixtures=2,
            include_synthetic=True,
        )


def test_synthetic_fixture_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(langfuse_export, "list_ollama_chat_trace_ids", lambda limit: [])

    with pytest.raises(ValueError, match="include_synthetic=True"):
        langfuse_export.collect_eval_items(n_intake_fixtures=1)


def test_source_count_keeps_real_empty_trace_distinct_from_synthetic(monkeypatch):
    monkeypatch.setattr(
        langfuse_export,
        "list_ollama_chat_trace_ids",
        lambda limit: ["real-empty"],
    )
    monkeypatch.setattr(
        langfuse_export,
        "fetch_trace",
        lambda trace_id: {"input": "question", "output": ""},
    )

    items = langfuse_export.collect_eval_items(
        n_scoreable=0,
        n_blank_samples=1,
        n_intake_fixtures=1,
        include_synthetic=True,
    )

    assert [item.trace_id for item in items] == ["real-empty", "synthetic-intake-1"]
    assert langfuse_export.count_item_sources(items) == {
        "real_trace_count": 1,
        "synthetic_count": 1,
    }
    assert items[0].synthetic is False
    assert items[1].synthetic is True


@pytest.mark.parametrize("payload", [{}, {"id": None}, {"id": ""}, {"id": 123}])
def test_score_response_requires_nonempty_string_id(monkeypatch, payload):
    monkeypatch.setattr(langfuse_export, "_post", lambda *args, **kwargs: payload)

    with pytest.raises(ScoreResponseError, match="missing non-empty id"):
        langfuse_export.post_score("chat_quality", 1.0, "trace-1", "good")


def test_list_scores_clamps_limit_to_public_api_maximum(monkeypatch):
    urls = []

    def fake_get(url):
        urls.append(url)
        return {"data": [{"id": "score-1"}], "meta": {"totalPages": 1}}

    monkeypatch.setattr(langfuse_export, "_get", fake_get)

    assert langfuse_export.list_scores("trace-1", limit=101) == [{"id": "score-1"}]
    query = parse_qs(urlsplit(urls[0]).query)
    assert query["traceId"] == ["trace-1"]
    assert query["limit"] == ["100"]


@pytest.mark.parametrize("limit", [0, -1, None, "not-an-int"])
def test_list_scores_rejects_non_positive_or_invalid_limit(monkeypatch, limit):
    monkeypatch.setattr(
        langfuse_export,
        "_get",
        lambda url: pytest.fail("invalid limit must not call Langfuse"),
    )

    with pytest.raises(ValueError):
        langfuse_export.list_scores("trace-1", limit=limit)


def test_find_score_by_id_uses_exact_score_endpoint_not_trace_score_list(monkeypatch):
    urls = []

    def fake_get(url):
        urls.append(url)
        return {
            "id": "new-score",
            "name": "chat_quality",
            "traceId": "trace-1",
            "value": 1.0,
        }

    monkeypatch.setattr(langfuse_export, "_get", fake_get)

    assert langfuse_export.find_score_by_id("new-score", "trace-1") == {
        "id": "new-score",
        "name": "chat_quality",
        "traceId": "trace-1",
        "value": 1.0,
    }
    assert urls == [f"{langfuse_export.LANGFUSE_BASE}/api/public/scores/new-score"]
    assert parse_qs(urlsplit(urls[0]).query) == {}


def test_find_score_by_id_treats_exact_404_as_not_visible_yet(monkeypatch):
    urls = []

    def fake_get(url):
        urls.append(url)
        raise _http_error(404)

    monkeypatch.setattr(langfuse_export, "_get", fake_get)

    assert langfuse_export.find_score_by_id("new-score", "trace-1") is None
    assert urls == [f"{langfuse_export.LANGFUSE_BASE}/api/public/scores/new-score"]


@pytest.mark.parametrize("failure", ["unauthorized", "forbidden", "bad_json"])
def test_find_score_by_id_fails_fast_for_non_visibility_errors(monkeypatch, failure):
    urls = []

    def fake_get(url):
        urls.append(url)
        if failure == "unauthorized":
            raise _http_error(401)
        if failure == "forbidden":
            raise _http_error(403)
        raise ValueError("bad score JSON")

    monkeypatch.setattr(langfuse_export, "_get", fake_get)

    with pytest.raises((urllib.error.HTTPError, ValueError)):
        langfuse_export.find_score_by_id("new-score", "trace-1")

    assert len(urls) == 1
    assert urls[0] == f"{langfuse_export.LANGFUSE_BASE}/api/public/scores/new-score"


def test_collect_keeps_real_memory_trace_without_context_as_skipped(monkeypatch):
    monkeypatch.setattr(
        langfuse_export,
        "list_ollama_chat_trace_ids",
        lambda limit: ["memory-no-context"],
    )
    monkeypatch.setattr(
        langfuse_export,
        "fetch_trace",
        lambda trace_id: {
            "input": "What preference did I state?",
            "output": "I cannot find a stated preference.",
        },
    )

    items = langfuse_export.collect_eval_items(
        n_scoreable=0,
        n_blank_samples=0,
        task="memory_correctness",
    )

    assert len(items) == 1
    assert items[0].trace_id == "memory-no-context"
    assert items[0].synthetic is False
    assert items[0].status == "skipped"
    assert items[0].skip_reason == "no_prior_context"


def test_collect_rejects_synthetic_when_real_traces_filter_to_no_items(monkeypatch):
    monkeypatch.setattr(
        langfuse_export,
        "list_ollama_chat_trace_ids",
        lambda limit: ["real-filtered"],
    )
    monkeypatch.setattr(
        langfuse_export,
        "fetch_trace",
        lambda trace_id: {"input": "question", "output": "real answer"},
    )

    with pytest.raises(langfuse_export.EmptyTraceExportError) as captured:
        langfuse_export.collect_eval_items(
            n_scoreable=0,
            n_blank_samples=0,
            n_intake_fixtures=1,
            include_synthetic=True,
        )

    assert captured.value.real_trace_count == 1
    assert captured.value.real_item_count == 0
    assert "synthetic-only" in str(captured.value)


def test_offline_guard_userinfo_and_query_secrets_are_absent_from_error_text():
    url = (
        "http://guard-user:guard-password@localhost:3000/api"
        "?api_key=guard-query-secret"
    )

    with pytest.raises(OfflineGuardError) as captured:
        offline_guard.assert_loopback(url)

    message = str(captured.value)
    for secret in ("guard-user", "guard-password", "guard-query-secret"):
        assert secret not in message
    assert "offline guard blocked URL userinfo" in message
    assert "scheme='http'" in message
    assert "host=localhost" in message


def test_redirect_location_secrets_are_absent_from_error_text():
    request = urllib.request.Request(
        "http://localhost:3000/api?token=redirect-request-secret"
    )
    location = (
        "http://redirect-user:redirect-password@localhost:3000/next"
        "?api_key=redirect-location-secret"
    )

    with pytest.raises(OfflineGuardError) as captured:
        offline_guard._RejectRedirectHandler().http_error_302(
            request,
            None,
            302,
            "redirect",
            {"Location": location},
        )

    message = str(captured.value)
    for secret in (
        "redirect-request-secret",
        "redirect-user",
        "redirect-password",
        "redirect-location-secret",
    ):
        assert secret not in message
    assert "status=302" in message
