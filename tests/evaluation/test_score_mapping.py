"""P2② 单向分数映射契约测试（纯离线，无网络）。

覆盖定稿口径五类断言：
1. 映射方向单向（业务 outcome -> Langfuse score，outcome 不被改动/反写）；
2. NUMERIC 值与 traceId 绑定（float 数值 + name + traceId + 来源 comment）；
3. score 幂等重跑 delta=0（复用 post_score_idempotent + find_score_by_id）；
4. 业务表未被反写（真实 ResearchStore 逐行快照前后一致）；
5. quality_score 缺失/非法时不写 score 且不抛异常。
"""
from __future__ import annotations

import sqlite3
import urllib.error
from urllib.parse import urlsplit

import pytest

from backend.eval_042 import langfuse_export, score_mapping


class _FakeScoreService:
    """内存 Langfuse score 端点：exact-ID GET 404/200，POST 逐次记录。"""

    def __init__(self):
        self.scores: dict = {}
        self.posts: list = []
        self.gets: list = []

    def get(self, url):
        score_id = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        self.gets.append(score_id)
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


def _outcome(quality_score=0.8, decision_id="dec-1"):
    return {
        "decision_id": decision_id,
        "quality_score": quality_score,
        "created_at": "2026-11-09T00:00:00Z",
    }


# ---- 1. 映射方向单向 ----------------------------------------------------
def test_mapping_direction_is_single_way_outcome_to_langfuse(monkeypatch):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    outcome = _outcome(0.8)
    snapshot = dict(outcome)

    result = score_mapping.map_quality_score(outcome, "trace-abc")

    assert result["status"] == "mapped"
    assert len(service.posts) == 1                    # 只写 Langfuse 一侧
    assert service.posts[0]["value"] == 0.8           # 值来自业务 outcome
    assert service.posts[0]["name"] == score_mapping.SCORE_NAME
    assert outcome == snapshot                        # outcome 只读、未被反向改动
    assert result["decision_id"] == "dec-1"


# ---- 2. NUMERIC 值与 traceId 绑定 ---------------------------------------
def test_numeric_value_is_bound_to_trace_id(monkeypatch):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    result = score_mapping.map_quality_score(_outcome(0.8, "dec-2"), "trace-xyz")

    assert result["status"] == "mapped"
    body = service.posts[0]
    assert body["name"] == "research_quality_score"
    assert isinstance(body["value"], float) and not isinstance(body["value"], bool)
    assert body["value"] == 0.8                       # NUMERIC 值 = 原 quality_score
    assert 0.0 <= body["value"] <= 1.0
    assert body["traceId"] == "trace-xyz"            # 绑定到该决策关联的真实 trace
    assert "dec-2" in body["comment"]                # comment 记来源 decision_id
    assert score_mapping.MAPPING_VERSION in body["comment"]
    assert isinstance(body.get("id"), str) and body["id"]  # 确定性幂等键


# ---- 3. score 幂等重跑 delta=0 ------------------------------------------
def test_rerun_is_idempotent_delta_zero(monkeypatch):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    outcome = _outcome(0.65, "dec-3")

    first = score_mapping.map_quality_score(outcome, "trace-idem")
    after_first = len(service.posts)
    second = score_mapping.map_quality_score(outcome, "trace-idem")

    assert first["status"] == "mapped"
    assert after_first == 1
    assert len(service.posts) == 1                    # 重跑不产生第二条 score
    assert len(service.posts) - after_first == 0     # delta = 0
    assert first["score_id"] == second["score_id"]
    assert service.gets                              # 用了 exact-ID 回查（先查后写）
    assert len(service.scores) == 1


# ---- 4. 业务表未被反写 --------------------------------------------------
def _forbid_write(self, *args, **kwargs):
    raise AssertionError("business table write-back is forbidden")


def _dump_outcomes(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM research_model_outcomes ORDER BY decision_id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def test_business_outcome_table_is_never_written_back(tmp_path, monkeypatch):
    from backend.app.research.application.routing_observation import (
        ModelOutcome,
        RoutingDecision,
    )
    from backend.app.research.infrastructure.research_store import ResearchStore

    store = ResearchStore(tmp_path / "research.sqlite3")
    store.save_routing_decision(RoutingDecision(
        decision_id="dec-db-1", owner_id="owner-1", task_type="chat",
        features={}, candidate_models=["m1"], chosen_model="m1",
        reason="r", policy_version="v1", created_at="2026-11-09T00:00:00Z",
    ))
    store.save_model_outcome(
        ModelOutcome(decision_id="dec-db-1", quality_score=0.8,
                     created_at="2026-11-09T00:00:00Z"),
        owner_id="owner-1",
    )
    before = _dump_outcomes(store.database_path)

    # 任何「反写业务表」的调用都会让本用例立即失败（非空守卫，防止静默失效）。
    monkeypatch.setattr(type(store), "save_model_outcome", _forbid_write)
    monkeypatch.setattr(type(store), "record_model_outcome", _forbid_write)

    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    outcome = store.get_model_outcome("dec-db-1", owner_id="owner-1")
    result = score_mapping.map_quality_score(outcome, "trace-db-1")

    assert result["status"] == "mapped"
    after = _dump_outcomes(store.database_path)
    assert after == before                            # 逐行逐列完全一致
    assert len(after) == 1                            # 未新增/未迁移历史行
    assert after[0]["quality_score"] == 0.8
    assert service.posts[0]["value"] == 0.8


# ---- 5. quality_score 缺失/非法时不写 score 且不抛异常 -----------------
@pytest.mark.parametrize("bad_value", [
    None, "0.8", True, False, -0.1, 1.5, float("nan"), float("inf"), "abc", [],
])
def test_invalid_quality_score_writes_nothing_and_never_raises(monkeypatch, bad_value):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    result = score_mapping.map_quality_score(
        _outcome(bad_value, "dec-invalid"), "trace-invalid"
    )  # 必须不抛异常

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_or_invalid_quality_score"
    assert service.posts == []                        # 一条 score 都不写


def test_missing_quality_score_key_writes_nothing_and_never_raises(monkeypatch):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    result = score_mapping.map_quality_score(
        {"decision_id": "dec-no-score"}, "trace-no-score"
    )

    assert result["status"] == "skipped"
    assert service.posts == []


# ---- 附加：不伪造 traceId / fail-open 不冒泡 ----------------------------
@pytest.mark.parametrize("trace_id", [None, "", "   "])
def test_missing_trace_id_is_skipped_without_fabricating(monkeypatch, trace_id):
    service = _FakeScoreService()
    _install_transport(monkeypatch, service)

    result = score_mapping.map_quality_score(_outcome(0.8), trace_id)

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_trace_id"
    assert service.posts == []


def test_score_write_failure_is_fail_open_and_never_bubbles(monkeypatch):
    def exploding_writer(**kwargs):
        raise RuntimeError("langfuse down")

    result = score_mapping.map_quality_score(
        _outcome(0.8), "trace-fail", score_writer=exploding_writer
    )  # 必须不抛异常

    assert result["status"] == "failed"
    assert result["reason"] == "score_write_failed"


# ---- 读侧适配器：走 research_store 既有 get_model_outcome（只读）--------
def test_read_adapter_maps_from_store_and_never_writes_back(tmp_path, monkeypatch):
    from backend.app.research.application.routing_observation import (
        ModelOutcome,
        RoutingDecision,
    )
    from backend.app.research.infrastructure.research_store import ResearchStore

    store = ResearchStore(tmp_path / "research.sqlite3")
    store.save_routing_decision(RoutingDecision(
        decision_id="dec-read-1", owner_id="owner-1", task_type="chat",
        features={}, candidate_models=["m1"], chosen_model="m1",
        reason="r", policy_version="v1", created_at="2026-11-09T00:00:00Z",
    ))
    store.save_model_outcome(
        ModelOutcome(decision_id="dec-read-1", quality_score=0.55,
                     created_at="2026-11-09T00:00:00Z"),
        owner_id="owner-1",
    )
    before = _dump_outcomes(store.database_path)
    monkeypatch.setattr(type(store), "save_model_outcome", _forbid_write)
    monkeypatch.setattr(type(store), "record_model_outcome", _forbid_write)

    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    result = score_mapping.map_decision_quality_score(
        store, decision_id="dec-read-1", owner_id="owner-1",
        trace_id="trace-read-1",
    )

    assert result["status"] == "mapped"
    assert service.posts[0]["value"] == 0.55
    assert _dump_outcomes(store.database_path) == before


def test_read_adapter_missing_outcome_is_skipped(monkeypatch):
    class _EmptyStore:
        def get_model_outcome(self, decision_id, *, owner_id):
            return None

    service = _FakeScoreService()
    _install_transport(monkeypatch, service)
    result = score_mapping.map_decision_quality_score(
        _EmptyStore(), decision_id="dec-none", owner_id="o", trace_id="t"
    )
    assert result["status"] == "skipped"
    assert service.posts == []


def test_read_adapter_read_failure_is_fail_open(monkeypatch):
    class _BrokenStore:
        def get_model_outcome(self, decision_id, *, owner_id):
            raise RuntimeError("db down")

    result = score_mapping.map_decision_quality_score(
        _BrokenStore(), decision_id="dec-x", owner_id="o", trace_id="t"
    )  # 必须不抛异常
    assert result["status"] == "failed"
    assert result["reason"] == "score_write_failed"
