"""spec-042 Task 05 幂等写回单测（纯函数、无网络：monkeypatch 注入 list_scores/delete_score/post_score/judge_repeats）。

delta write 语义（D 节修订，取代 delete-then-write）：

- 同值跳过：写回前 list_scores 按 name==task 精确过滤，取最新一条（timestamp/createdAt 最大；
  缺时间字段按返回顺序末位），其 value 与本次将写入 value 相同（浮点容差 1e-9）
  -> 不删、不写，计 skipped_unchanged，视为已落地（计入 verified）；
- 值不同 / 无同名 / 现有 value 为 None 或不可解析 -> 只 post 一条新分，绝不 delete；
- 默认评测流程不再触发任何 delete：idempotent=True 时 deleted_preexisting 恒为 0；
- write_back=False / dry_run / skipped / unavailable -> 零 delete、零 post。
"""
from __future__ import annotations

import json

import eval_042.judge_client as jc
import eval_042.langfuse_export as lf
import pytest
from eval_042.eval_run import _latest_same_name, run


def _judge_good(*_a, **_k):
    # chat_quality good -> enum_to_score -> 1.0
    return [{"status": "scored", "label": "good", "score": 1.0, "explanation": "e"}] * 3


def _judge_all_unavailable(*_a, **_k):
    return [{"status": "unavailable", "label": None, "score": None,
             "explanation": "", "error": "boom"}] * 3


@pytest.fixture
def fake_io(monkeypatch):
    # chat_quality 的 good/poor 映射：good=1.0, poor=0.0
    state = {"scores": [], "deleted": [], "posted": [], "list_calls": 0}

    def fake_list(trace_id, limit=100):
        state["list_calls"] += 1
        return list(state["scores"])

    def fake_post(name, value, trace_id, comment, observation_id=None):
        sid = f"new-{len(state['posted'])}"
        rec = {"id": sid, "name": name, "value": value, "traceId": trace_id}
        state["posted"].append(rec)
        state["scores"].append(rec)
        return {"id": sid}

    def fake_delete(score_id):
        # 默认评测流程不应触发任何 delete；若被调用则记下来以暴露回归
        state["deleted"].append(score_id)
        state["scores"] = [s for s in state["scores"] if s.get("id") != score_id]
        return True

    monkeypatch.setattr(lf, "list_scores", fake_list)
    monkeypatch.setattr(lf, "post_score", fake_post)
    monkeypatch.setattr(lf, "delete_score", fake_delete)
    monkeypatch.setattr(jc, "judge_repeats", _judge_good)
    return state


def _scored_item(tid="tid-1", output="某条真实回答"):
    return {"trace_id": tid, "task": "chat_quality", "input": "q",
            "output": output, "prior_context": None, "synthetic": False}


def _skipped_item(tid="tid-skip"):
    return {"trace_id": tid, "task": "chat_quality", "input": "q",
            "output": "", "prior_context": None, "synthetic": False}


def test_idempotent_same_value_skips_zero_post_zero_delete(fake_io):
    tid = "tid-1"
    # 现有同名最新 score value == good(1.0) -> 同值跳过
    fake_io["scores"] = [{"id": "old1", "name": "chat_quality", "value": 1.0,
                          "traceId": tid, "timestamp": "2026-01-01T00:00:00Z"}]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 0
    assert summary["skipped_unchanged"] == 1
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    assert summary["idempotent_check_errors"] == 0
    assert summary["verified_on_trace"] == 1  # 视为已落地
    assert fake_io["deleted"] == []
    assert fake_io["posted"] == []


def test_idempotent_different_value_writes_one_zero_delete(fake_io):
    tid = "tid-2"
    # 现有同名最新 score value == poor(0.0) != good(1.0) -> 仅写一条新分
    fake_io["scores"] = [{"id": "old1", "name": "chat_quality", "value": 0.0,
                          "traceId": tid, "timestamp": "2026-01-01T00:00:00Z"}]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    assert summary["verified_on_trace"] == 1
    assert fake_io["deleted"] == []  # 不触发删除
    assert len(fake_io["posted"]) == 1


def test_idempotent_no_existing_writes_one_zero_delete(fake_io):
    tid = "tid-3"
    fake_io["scores"] = []
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert summary["deleted_preexisting"] == 0
    assert fake_io["deleted"] == []
    assert len(fake_io["posted"]) == 1


def test_idempotent_filters_only_same_name(fake_io):
    tid = "tid-filter"
    fake_io["scores"] = [
        {"id": "cq", "name": "chat_quality", "value": 0.0, "traceId": tid},  # 值不同 -> 会写新分
        {"id": "ttft", "name": "ttft_ms", "value": 12.0, "traceId": tid},
        {"id": "eval", "name": "eval_ms", "value": 34.0, "traceId": tid},
        {"id": "cold", "name": "is_cold_start", "value": 1.0, "traceId": tid},
    ]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 1
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    # 只比较/只看 name==chat_quality 的；其它 name 未被触碰（也未删除）
    assert fake_io["deleted"] == []
    remaining_ids = {s["id"] for s in fake_io["scores"]}
    assert {"ttft", "eval", "cold", "cq"} <= remaining_ids  # 原 chat_quality 也未删


def test_idempotent_latest_by_timestamp_matches_skips(fake_io):
    tid = "tid-ts"
    # 多条同名：较旧 value=0.0，最新(t2) value=1.0 == good -> 跳过
    fake_io["scores"] = [
        {"id": "old", "name": "chat_quality", "value": 0.0, "traceId": tid,
         "timestamp": "2026-01-01T00:00:00Z"},
        {"id": "new", "name": "chat_quality", "value": 1.0, "traceId": tid,
         "timestamp": "2026-02-01T00:00:00Z"},
    ]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["skipped_unchanged"] == 1
    assert summary["written"] == 0
    assert fake_io["posted"] == []


def test_idempotent_latest_fallback_returned_order(fake_io):
    tid = "tid-order"
    # 缺时间字段 -> 按返回顺序末位作为最新：末位 value=1.0 == good -> 跳过
    fake_io["scores"] = [
        {"id": "a", "name": "chat_quality", "value": 0.0, "traceId": tid},
        {"id": "b", "name": "chat_quality", "value": 1.0, "traceId": tid},
    ]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["skipped_unchanged"] == 1
    assert summary["written"] == 0
    assert fake_io["posted"] == []


def test_idempotent_existing_value_none_writes_and_records_check_error(fake_io):
    tid = "tid-none"
    # 现有同名 value=None -> 保守写入一条新分，并记录 idempotent_check_error
    fake_io["scores"] = [{"id": "old1", "name": "chat_quality", "value": None,
                          "traceId": tid, "timestamp": "2026-01-01T00:00:00Z"}]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    assert summary["idempotent_check_errors"] == 1
    assert len(fake_io["posted"]) == 1
    assert fake_io["deleted"] == []


def test_idempotent_skipped_zero_delete_zero_post(fake_io):
    summary = run([_skipped_item()], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 0
    assert summary["skipped_unchanged"] == 0
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    assert fake_io["deleted"] == []
    assert fake_io["posted"] == []


def test_idempotent_unavailable_zero_delete_zero_post(monkeypatch, fake_io):
    monkeypatch.setattr(jc, "judge_repeats", _judge_all_unavailable)
    summary = run([_scored_item()], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["unavailable"] == 1
    assert summary["written"] == 0
    assert summary["deleted_preexisting"] == 0
    assert fake_io["deleted"] == []
    assert fake_io["posted"] == []


def test_idempotent_write_back_false_zero_delete_zero_post(fake_io):
    summary = run([_scored_item()], "chat_quality", "qwen3.5:9b", 3, False, idempotent=True)
    assert summary["written"] == 0
    assert summary["skipped_unchanged"] == 0
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    # 判官仍被调用，但不再发生删除/写回
    assert fake_io["deleted"] == []
    assert fake_io["posted"] == []


def test_non_idempotent_unchanged(fake_io):
    # 默认 idempotent=False：行为与 Task 04 一致，不删除直接写
    tid = "tid-nonidem"
    fake_io["scores"] = [{"id": "old1", "name": "chat_quality", "value": 0.0, "traceId": tid}]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True)
    assert summary["deleted_preexisting"] == 0
    assert summary["delete_errors"] == 0
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert fake_io["deleted"] == []   # 未删除旧分
    assert len(fake_io["posted"]) == 1


def test_latest_same_name_scopes_by_trace_id():
    # Langfuse public scores API 实测忽略 traceId 查询参数，故必须客户端按 traceId 二次过滤
    scores = [
        {"id": "a", "name": "chat_quality", "value": 1.0,
         "traceId": "other", "timestamp": "2026-03-01T00:00:00Z"},
        {"id": "b", "name": "chat_quality", "value": 0.0,
         "traceId": "THIS", "timestamp": "2026-01-01T00:00:00Z"},
    ]
    # 不给定 trace_id -> 取全局最新（other 的 1.0 @ 2026-03）
    got = _latest_same_name(scores, "chat_quality")
    assert got["id"] == "a"
    # 给定 trace_id=THIS -> 只看 THIS 的（0.0 @ 2026-01）
    got2 = _latest_same_name(scores, "chat_quality", "THIS")
    assert got2["id"] == "b"
    # 给定不存在的 trace_id -> None（不误用其它 trace 的分）
    assert _latest_same_name(scores, "chat_quality", "nope") is None


def test_idempotent_other_trace_same_name_does_not_skip(fake_io):
    tid = "tid-scope"
    # 另一条 trace 上有同 name 同 value 的分：本 trace 无同 name 分 -> 应写 1 条（不跳过）
    fake_io["scores"] = [{"id": "x", "name": "chat_quality", "value": 1.0,
                          "traceId": "different-trace"}]
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True, idempotent=True)
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert len(fake_io["posted"]) == 1
    assert fake_io["deleted"] == []


# ---------- 本地幂等状态表（state_path）----------
# 存在理由：本实例 Langfuse `GET /api/public/scores?traceId=` 实测**忽略 traceId 参数**，
# 服务端比对取不到「本 trace 最新一条」，故以本地状态表作为唯一可靠的幂等判据源。


def _write_state(tmp_path, entries):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return str(p)


def _read_state(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("entries", {})


def test_state_same_value_skips_without_touching_server(fake_io, tmp_path):
    tid = "tid-state"
    # 服务端可见的分属于别的 trace（模拟 traceId 被忽略），本 trace 判据只能来自 state
    fake_io["scores"] = [{"id": "x", "name": "chat_quality", "value": 1.0,
                          "traceId": "other", "timestamp": "2026-03-01T00:00:00Z"}]
    sp = _write_state(tmp_path, {f"chat_quality:{tid}": {"task": "chat_quality",
                                                         "value": 1.0, "label": "good",
                                                         "score_id": "prev-1"}})
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True,
                  idempotent=True, state_path=sp)
    assert summary["written"] == 0
    assert summary["skipped_unchanged"] == 1
    assert summary["verified_on_trace"] == 1
    assert fake_io["posted"] == []      # 未写
    assert fake_io["deleted"] == []     # 未删


def test_state_different_value_writes_and_updates_state(fake_io, tmp_path):
    tid = "tid-state-diff"
    sp = _write_state(tmp_path, {f"chat_quality:{tid}": {"task": "chat_quality",
                                                         "value": 0.0, "label": "poor",
                                                         "score_id": "prev-0"}})
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True,
                  idempotent=True, state_path=sp)
    assert summary["written"] == 1
    assert summary["skipped_unchanged"] == 0
    assert len(fake_io["posted"]) == 1
    # 状态表被持久化更新为本次写回的值与 score_id（下次同值即跳过）
    entry = _read_state(sp)[f"chat_quality:{tid}"]
    assert entry["value"] == 1.0
    assert entry["score_id"] == fake_io["posted"][0]["id"]


def test_state_absent_falls_back_to_server_check(fake_io, tmp_path):
    tid = "tid-no-state"
    fake_io["scores"] = [{"id": "old1", "name": "chat_quality", "value": 1.0,
                          "traceId": tid, "timestamp": "2026-01-01T00:00:00Z"}]
    sp = _write_state(tmp_path, {})
    summary = run([_scored_item(tid)], "chat_quality", "qwen3.5:9b", 3, True,
                  idempotent=True, state_path=sp)
    assert summary["skipped_unchanged"] == 1
    assert summary["written"] == 0
    assert fake_io["posted"] == []


def test_state_load_save_roundtrip(tmp_path):
    from eval_042.eval_run import _load_state, _save_state

    p = str(tmp_path / "state.json")
    assert _load_state(p) == {}            # 不存在 -> 空
    _save_state(p, {"chat_quality:t1": {"value": 0.5, "score_id": "s1"}})
    assert _load_state(p) == {"chat_quality:t1": {"value": 0.5, "score_id": "s1"}}
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    assert _load_state(p) == {}            # 损坏 -> 退化为空，不阻断
