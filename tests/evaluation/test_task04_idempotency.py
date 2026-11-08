"""Spec-045 Task-04 红绿测试：score 幂等接线 + 报告目录文件锁。

全部离线：Langfuse 用内存 fake transport，判官用 fake judge，报告写本地
tmp_path；不启动服务、不连真实 Langfuse / Ollama。
"""
from __future__ import annotations

import json
import multiprocessing as mp
import urllib.error
from urllib.parse import urlsplit

import pytest

from backend.eval_042 import langfuse_export, runner
from backend.eval_042.report import (
    REPORT_JSON_NAME,
    REPORT_MARKDOWN_NAME,
    REPORT_SCHEMA_VERSION,
    ReportWriter,
)


def _item(trace_id="trace-idem", *, task="chat_quality"):
    return {
        "trace_id": trace_id,
        "task": task,
        "input": "What should be evaluated?",
        "output": "A complete answer.",
        "status": "scored",
        "synthetic": False,
        "prior_context": None,
    }


class _FakeScoreService:
    """内存 Langfuse score 端点：exact-ID GET 404/200，POST 逐次记录。"""

    def __init__(self):
        self.scores = {}
        self.posts = []
        self.gets = []
        self.lookup_error = None

    def get(self, url):
        score_id = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        self.gets.append(score_id)
        if self.lookup_error is not None:
            error, self.lookup_error = self.lookup_error, None
            raise error
        if score_id in self.scores:
            return dict(self.scores[score_id])
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def post(self, url, body):
        self.posts.append(dict(body))
        score_id = body.get("id") or f"auto-score-{len(self.posts)}"
        score = {
            "id": score_id,
            "traceId": body["traceId"],
            "name": body["name"],
            "value": body["value"],
        }
        self.scores[score_id] = score
        return dict(score)


def _install_transport(monkeypatch, service):
    monkeypatch.setattr(langfuse_export, "_get", service.get)
    monkeypatch.setattr(langfuse_export, "_post", service.post)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    def judge(model, task, question, answer, repeats, *, ctx=None):
        return [
            {
                "status": "scored",
                "label": "good",
                "score": 1.0,
                "explanation": "safe judge rationale",
            }
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)


def _score_kwargs():
    return dict(
        name="chat_quality",
        value=1.0,
        trace_id="trace-idem",
        comment="Explanation: safe judge rationale; Label: good",
        report_version=REPORT_SCHEMA_VERSION,
        task="chat_quality",
    )


def test_rerun_same_trace_writes_exactly_one_score(tmp_path, monkeypatch):
    """RED: 接线前两次 run 会 POST 两次；GREEN: 幂等后仅一条 score。"""
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    for index in range(2):
        result = runner.run(
            output_dir=tmp_path / f"run-{index}",
            items=[_item()],
            repeats=3,
        )
        assert result["exit_code"] == 0, result["errors"]

    assert len(service.posts) == 1
    assert len(service.scores) == 1


def test_first_write_posts_exactly_once_with_deterministic_id(tmp_path, monkeypatch):
    """POST 恰好一次且不重试；接线后携带确定性幂等 id。"""
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    result = runner.run(output_dir=tmp_path, items=[_item()], repeats=3)

    assert result["exit_code"] == 0, result["errors"]
    assert len(service.posts) == 1
    body = service.posts[0]
    assert body["name"] == "chat_quality"
    assert body["value"] == 1.0
    assert body["traceId"] == "trace-idem"
    assert isinstance(body.get("id"), str) and body["id"]


def test_404_lookup_still_posts_exactly_once(monkeypatch):
    """404 = 尚未可见，仍恰好一次 POST，不重放。"""
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    posted = langfuse_export.post_score_idempotent(**_score_kwargs())

    assert len(service.posts) == 1
    assert posted["id"] == service.posts[0]["id"]


def test_hit_on_dedupe_id_reuses_existing_score_without_second_post(monkeypatch):
    """命中去重 id 时复用既有 score，不发第二条 POST。"""
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    first = langfuse_export.post_score_idempotent(**_score_kwargs())
    second = langfuse_export.post_score_idempotent(**_score_kwargs())

    assert len(service.posts) == 1
    assert second["id"] == first["id"]


@pytest.mark.parametrize("code", [401, 403, 500])
def test_non_404_lookup_error_does_not_fall_back_to_post(monkeypatch, code):
    """精确查询遇非 404 错误：直接失败，不回退重放 POST。"""
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    service.lookup_error = urllib.error.HTTPError(
        "http://127.0.0.1:3000/api/public/scores/x", code, "error", {}, None
    )

    with pytest.raises(urllib.error.HTTPError):
        langfuse_export.post_score_idempotent(**_score_kwargs())

    assert service.posts == []


def _concurrent_checkpoint(output_dir, marker):
    """子进程：反复 checkpoint 同一输出目录，双投影必须始终成对。"""
    writer = ReportWriter(output_dir, metadata={"writer": marker})
    try:
        for index in range(24):
            document = dict(writer.document)
            document["items"] = [
                {
                    "trace_id": marker,
                    "status": "scored",
                    "score": float(index),
                    "score_id": f"{marker}-{index}",
                }
            ]
            writer.checkpoint(document)
    finally:
        writer.close()
    return marker


def test_concurrent_writers_share_output_dir_without_overwriting(tmp_path):
    """双进程共用 --output-dir：既有 flock 保证 report.json/md 不被覆盖。"""
    output_dir = tmp_path / "shared"
    ctx = mp.get_context("fork")
    processes = [
        ctx.Process(target=_concurrent_checkpoint, args=(str(output_dir), f"writer-{index}"))
        for index in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
    assert all(process.exitcode == 0 for process in processes)

    json_path = output_dir / REPORT_JSON_NAME
    markdown_path = output_dir / REPORT_MARKDOWN_NAME
    document = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert document["schema_version"] == REPORT_SCHEMA_VERSION
    assert document["items"]
    assert "# Agent evaluation report" in markdown
    # 双投影来自同一次 checkpoint：JSON 的 trace_id / score_id 必须在 Markdown 可见。
    assert document["items"][0]["trace_id"] in markdown
    assert document["items"][0]["score_id"] in markdown
    assert not list(output_dir.glob(".report.json.*.tmp"))
    assert not list(output_dir.glob(".report.md.*.tmp"))
