"""内置标注集数据契约：三份各 >=100 条真实派生样本、schema、两层 synthetic、生成幂等。

只读核验 gold 文件与生成脚本的纯构造入口，不改文件、不触网。KB 真实 chunk 身份
以文档内 kb_snapshot（生成时从运行中主服务只读派生）留痕为准，可离线复核。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
GOLD = BASE / "docs" / "sdd" / "plans" / "047" / "gold"
FROZEN = BASE / "docs" / "sdd" / "plans" / "042" / "task-02-eval-dataset.json"
SCRIPT = BASE / "scripts" / "generate_evaluation_samples.py"
DATASETS = ("rag-retrieval", "intent-classification", "chat-quality")
GENERATOR = "scripts/generate_evaluation_samples.py"
STAMP = "2026-11-11T00:00:00Z"


def _load(dataset_id: str) -> dict:
    return json.loads((GOLD / f"builtin-{dataset_id}.json").read_text(encoding="utf-8"))


def _script():
    spec = importlib.util.spec_from_file_location("gen_eval_samples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _digest(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _snapshot(n_cases: int = 112, n_chunks: int = 100, n_frozen: int = 20) -> dict:
    paper_ids = [f"{i:032x}" for i in range(1, 5)]
    return {
        "health": {"qdrant": True, "embedding": True, "papers": 4, "chunks": 400},
        "paper_ids": paper_ids,
        "retrieval_cases": [
            {
                "question": f"What does the knowledge base say about topic {i}?",
                "paper_id": paper_ids[i % 4], "chunker": "v1", "chunk_index": i,
                "page": 1 + i % 7, "excerpt": f"real chunk text {i}", "rank": 1 + i % 10,
            }
            for i in range(n_cases)
        ],
        "kb_chunks": [
            {
                "paper_id": paper_ids[i % 4], "chunk_index": i, "page": 1 + i % 7,
                "file_name": f"paper-{i % 4}.pdf", "text": f"real chunk text {i} from the knowledge base.",
            }
            for i in range(n_chunks)
        ],
        "frozen_traces": [
            {"trace_id": f"trace-{i}", "input": f"question {i}", "output": f"frozen answer {i}"}
            for i in range(n_frozen)
        ],
        "tool_names": [
            "paper_discovery", "search_paper_catalog", "download_and_import_paper",
            "fetch_paper_detail", "kb_search", "kb_ask", "session_search",
        ],
        "baseline": {
            "rag-retrieval": _load("rag-retrieval"),
            "intent-classification": _load("intent-classification"),
            "chat-quality": _load("chat-quality"),
        },
    }


@pytest.mark.parametrize("dataset_id", DATASETS)
def test_gold_dataset_has_at_least_100_real_items(dataset_id):
    doc = _load(dataset_id)
    assert doc["dataset_id"] == dataset_id
    assert doc["source"] == "builtin-fixture"
    assert doc["synthetic"] is True  # 文档级：内置 fixture 集，不冒充人工标注
    assert isinstance(doc["label_source"], str) and doc["label_source"].strip()
    items = doc["items"]
    assert isinstance(items, list) and len(items) >= 100
    assert doc["item_count"] == len(items)
    assert doc["generated_at"] and doc["generator"] == GENERATOR
    assert isinstance(doc["derivation_rule"], str) and doc["derivation_rule"].strip()
    assert isinstance(doc["kb_snapshot"]["paper_ids"], list) and doc["kb_snapshot"]["paper_ids"]
    for item in items:
        assert "value" not in item and "score" not in item and "label" not in item


def test_rag_relevant_doc_ids_are_current_kb_chunk_identities():
    doc = _load("rag-retrieval")
    paper_ids = set(doc["kb_snapshot"]["paper_ids"])
    assert len(paper_ids) > 0
    for item in doc["items"]:
        assert isinstance(item["question"], str) and item["question"].strip()
        assert isinstance(item["relevant_doc_ids"], list) and item["relevant_doc_ids"]
        for ref in item["relevant_doc_ids"]:
            assert ref["paper_id"] in paper_ids
            assert ref["chunker"] == "v1"
            assert isinstance(ref["chunk_index"], int) and not isinstance(ref["chunk_index"], bool)
            assert ref["chunk_index"] >= 0
        assert isinstance(item["derived_chunk_excerpt"], str) and item["derived_chunk_excerpt"].strip()
    # 追加范围二冻结的 8 条与 kb_alignment 结论逐字保留
    assert doc["kb_alignment"]["aligned_from_current_kb"]["aligned_items"] == 8
    assert [item["id"] for item in doc["items"][:8]] == [f"rag-{n:02d}" for n in range(1, 9)]


def test_intent_items_only_use_real_registry_tool_names():
    from backend.app.skills.registry import build_default_tool_registry

    names = {entry.name for entry in build_default_tool_registry()}
    assert len(names) == 7
    doc = _load("intent-classification")
    assert set(doc["registry_tool_names"]) == names
    for item in doc["items"]:
        assert isinstance(item["message"], str) and item["message"].strip()
        assert item["expected_intent"] in names | {"none"}
    covered = {item["expected_intent"] for item in doc["items"]}
    assert names <= covered and "none" in covered


def test_chat_items_are_20_frozen_traces_plus_kb_derived_with_two_layer_synthetic():
    doc = _load("chat-quality")
    items = doc["items"]
    assert len(items) >= 100 and doc["item_count"] == len(items)
    assert doc["scoreable_item_count"] == len(items)
    frozen = [i for i in items if i["reference_source"] == "frozen-042-trace"]
    derived = [i for i in items if i["reference_source"] == "kb-chunk"]
    assert len(frozen) == 20
    assert len(derived) >= 80
    assert len(frozen) + len(derived) == len(items)
    assert all(i["synthetic"] is False for i in frozen)
    assert all(i["synthetic"] is True for i in derived)
    raw = json.loads(FROZEN.read_text(encoding="utf-8"))
    expected = [
        r for r in raw
        if r.get("status") == "scored" and r.get("synthetic") is False
        and isinstance(r.get("input"), str) and isinstance(r.get("output"), str)
        and r["output"].strip()
    ]
    assert len(expected) == 20
    assert [i["input"] for i in frozen] == [r["input"] for r in expected]
    assert [i["output"] for i in frozen] == [r["output"] for r in expected]
    for item in items:
        assert item["status"] == "scored"
        assert isinstance(item["input"], str)
        assert isinstance(item["output"], str) and item["output"].strip()
    for item in derived:
        assert item["kb_source"]["paper_id"] in set(doc["kb_snapshot"]["paper_ids"])
        assert isinstance(item["kb_source"]["chunk_index"], int)
    assert "frozen" in doc["label_source"] and "kb" in doc["label_source"].lower()


def test_generator_is_deterministic_and_idempotent_on_its_own_output():
    mod = _script()
    snap = _snapshot()
    first = mod.build_documents(snap, STAMP)
    assert _digest(first) == _digest(mod.build_documents(snap, STAMP))
    snap2 = dict(snap)
    snap2["baseline"] = first  # 第二次运行以第一次产物为基线，不得累积重复条目
    second = mod.build_documents(snap2, STAMP)
    assert _digest(first) == _digest(second)
    for doc in first.values():
        assert len(doc["items"]) >= 100
        assert doc["item_count"] == len(doc["items"])
        for item in doc["items"]:
            assert "value" not in item and "score" not in item
