"""P1-3 唯一例外：call_ollama 增加可选 num_predict，但默认 160 逐字不变。

ENUM_MAPS / PROMPTS / KNOWN_TASKS / judge_one / judge_majority 的行为不回归。
"""
from __future__ import annotations

from backend.eval_042 import config, judge_client
from backend.eval_042.runner import KNOWN_TASKS


def _capture(monkeypatch):
    bodies: list[dict] = []

    def fake_post(url, body, headers=None, timeout=None):
        bodies.append(body)
        return {"message": {"content": "Explanation: ok\nAnswer: good"}}

    monkeypatch.setattr(judge_client, "http_post_json", fake_post)
    return bodies


def test_call_ollama_without_num_predict_keeps_body_at_160(monkeypatch):
    bodies = _capture(monkeypatch)
    judge_client.call_ollama("judge-model", [{"role": "user", "content": "q"}])
    assert bodies[0]["options"]["num_predict"] == 160
    assert bodies[0]["think"] is False
    assert bodies[0]["options"]["temperature"] == 0
    assert bodies[0]["seed"] == config.JUDGE_SEED
    assert bodies[0]["stream"] is False


def test_call_ollama_explicit_num_predict_overrides_only_that_call(monkeypatch):
    bodies = _capture(monkeypatch)
    judge_client.call_ollama("judge-model", [], num_predict=2048)
    judge_client.call_ollama("judge-model", [])
    assert bodies[0]["options"]["num_predict"] == 2048
    assert bodies[1]["options"]["num_predict"] == 160


def test_judge_one_majority_and_task_registry_are_unchanged(monkeypatch):
    _capture(monkeypatch)
    one = judge_client.judge_one("judge-model", "chat_quality", "q", "a")
    assert one["status"] == "scored"
    assert one["label"] == "good"
    assert one["score"] == 1.0 == config.ENUM_MAPS["chat_quality"]["good"]
    majority = judge_client.judge_majority("judge-model", "chat_quality", "q", "a", repeats=2)
    assert majority.majority == "good"
    assert majority.all_unavailable is False
    assert "chat_quality" in KNOWN_TASKS
    assert set(config.ENUM_MAPS) == {"chat_quality", "memory_correctness"}
