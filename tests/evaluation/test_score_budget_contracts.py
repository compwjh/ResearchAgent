"""打分预算与内置集加载契约：三常量单一真源、max_items 边界、chat 集唯一数据源。

P1-2：contracts 为唯一真源，service 不再重复定义 SCORE_TIMEOUT_SECONDS。
P1-4：load_chat_items 只读 builtin-chat-quality.json 的 items，不再读 042 文件、
不再按条目级 synthetic 过滤；list_datasets 的 item_count 与打分对象同源。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.evaluation import contracts, datasets, service
from backend.app.evaluation.contracts import EvaluationError


def test_three_budget_constants_are_the_confirmed_values():
    assert contracts.DEFAULT_MAX_ITEMS == 100
    assert contracts.MAX_ITEMS == 200
    assert contracts.SCORE_TIMEOUT_SECONDS == 900.0


def test_service_shares_the_single_timeout_source_with_contracts():
    assert service.SCORE_TIMEOUT_SECONDS is contracts.SCORE_TIMEOUT_SECONDS == 900.0
    source = Path(service.__file__).read_text(encoding="utf-8")
    assert "SCORE_TIMEOUT_SECONDS = 300.0" not in source
    assert "SCORE_TIMEOUT_SECONDS = 900.0" not in source


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 100), (0, 100), (-7, 100), (True, 100), (False, 100),
        ("abc", 100), (3.5, 100), (1, 1), (100, 100), (200, 200), (99999, 200),
    ],
)
def test_clamp_max_items_keeps_boundary_semantics(raw, expected):
    assert service._clamp_max_items(raw) == expected


def _write_chat_gold(gold: Path, items: list) -> None:
    (gold / "builtin-chat-quality.json").write_text(
        json.dumps({
            "dataset_id": "chat-quality", "schema_version": "builtin-evaluation-dataset-v1",
            "source": "builtin-fixture", "synthetic": True,
            "label_source": "kb-derived + frozen-042-trace", "item_count": 999, "items": items,
        }),
        encoding="utf-8",
    )


def test_load_chat_items_reads_gold_items_and_does_not_filter_entry_level_synthetic(monkeypatch, tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    items = [
        {"id": "a", "status": "scored", "input": "q1", "output": "a1",
         "synthetic": False, "reference_source": "frozen-042-trace"},
        {"id": "b", "status": "scored", "input": "q2", "output": "a2",
         "synthetic": True, "reference_source": "kb-chunk"},
        {"id": "c", "status": "skipped", "input": "q3", "output": "a3", "synthetic": True},
        {"id": "d", "status": "scored", "input": "q4", "output": "   ", "synthetic": True},
    ]
    _write_chat_gold(gold, items)
    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    # 042 文件即使被指向一个根本不存在的路径，也不得再参与加载（P1-4 唯一数据源）。
    monkeypatch.setattr(datasets, "CHAT_DATASET_PATH", tmp_path / "does-not-exist.json")
    loaded = datasets.load_chat_items()
    assert [item["id"] for item in loaded] == ["a", "b"]
    assert [item["reference_source"] for item in loaded] == ["frozen-042-trace", "kb-chunk"]


def test_list_datasets_chat_item_count_is_same_source_as_scored_items(monkeypatch, tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    items = [
        {"id": f"c{i}", "status": "scored", "input": f"q{i}", "output": f"a{i}", "synthetic": True}
        for i in range(7)
    ]
    _write_chat_gold(gold, items)
    for dataset_id in ("rag-retrieval", "intent-classification"):
        (gold / f"builtin-{dataset_id}.json").write_text(
            json.dumps({
                "dataset_id": dataset_id, "source": "builtin-fixture", "synthetic": True,
                "label_source": "x", "items": [{"i": 1}, {"i": 2}],
            }),
            encoding="utf-8",
        )
    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    listed = {entry["id"]: entry for entry in datasets.list_datasets()}
    assert listed["chat-quality"]["item_count"] == 7 == len(datasets.load_chat_items())
    assert listed["rag-retrieval"]["item_count"] == 2


def test_safe_dataset_path_whitelist_still_rejects_traversal():
    with pytest.raises(EvaluationError) as exc:
        datasets.load_dataset("../../etc/passwd")
    assert exc.value.code == "EVAL_DATASET_INVALID"


def test_malformed_document_still_returns_eval_dataset_invalid(monkeypatch, tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "builtin-chat-quality.json").write_text('{"source": "not-builtin"}', encoding="utf-8")
    monkeypatch.setattr(datasets, "GOLD_DIR", gold)
    with pytest.raises(EvaluationError) as exc:
        datasets.load_dataset("chat-quality")
    assert exc.value.code == "EVAL_DATASET_INVALID"
