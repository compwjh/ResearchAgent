"""P0: aggregate evaluator metadata backfill (spec029/030/031).

Regression guard for the synthesizer-skip bug: when a Search Worker's
tool_results omit ``catalog_metadata``, the recall allowlist (proven by the
Search Worker's actual recall) must still expand aggregate evaluator refs,
backfilling metadata from the local catalog directory.  Model evaluator
output must never supply metadata.
"""

from backend.app.research.application.orchestrator import (
    _validated_evaluator_candidates,
    _recall_allowlist_from_search_outputs,
    _work_item_output,
)


def _aggregate(refs, *, title=None):
    """Build an aggregate evaluator item (candidate_id is None)."""
    item = {
        "candidate_id": None,
        "keep": True,
        "evidence_refs": list(refs),
    }
    if title is not None:
        # The model-produced title/abstract must NEVER leak into the landed
        # record's metadata fields.
        item["title"] = title
        item["abstract"] = "MODEL-FAKE-ABSTRACT"
    return item


def test_aggregate_without_tool_metadata_backfills_from_local_directory():
    # Search tool_results carried no catalog_metadata (metadata_by_id empty),
    # but the ID is in the recall allowlist and the local directory has it.
    resolver = lambda cid: {"title": "Directory Title", "abstract": "dir abstract"}
    records = _validated_evaluator_candidates(
        [_aggregate(["catalog:paper-1"])],
        {},  # no metadata from search
        recall_allowlist={"paper-1"},
        metadata_resolver=resolver,
    )
    assert [r["candidate_id"] for r in records] == ["paper-1"]
    assert records[0]["title"] == "Directory Title"
    assert records[0]["abstract"] == "dir abstract"


def test_id_outside_recall_allowlist_rejected_even_if_directory_has_it():
    # Even though the resolver could return a row, an ID absent from the
    # Search Worker recall allowlist is dropped (fail-closed on the recall set).
    resolver = lambda cid: {"title": "Directory Title"}
    records = _validated_evaluator_candidates(
        [_aggregate(["catalog:paper-1", "catalog:paper-2"])],
        {},
        recall_allowlist={"paper-1"},  # paper-2 not recalled by search
        metadata_resolver=resolver,
    )
    assert [r["candidate_id"] for r in records] == ["paper-1"]


def test_metadata_never_taken_from_evaluator_model_output():
    # The evaluator item carries a model-invented title; the landed record
    # must use the directory/metadata value, not the model text.
    resolver = lambda cid: {"title": "Directory Title", "abstract": "dir abstract"}
    records = _validated_evaluator_candidates(
        [_aggregate(["catalog:paper-1"], title="MODEL-FAKE-TITLE")],
        {},
        recall_allowlist={"paper-1"},
        metadata_resolver=resolver,
    )
    assert records[0]["title"] == "Directory Title"
    assert records[0]["abstract"] == "dir abstract"
    assert "MODEL-FAKE-TITLE" not in list(records[0].values())
    assert "MODEL-FAKE-ABSTRACT" not in list(records[0].values())


def test_local_directory_missing_accepts_with_empty_metadata():
    # Decision: recall proves the candidate was returned, so even when the
    # local directory lacks the row, the candidate is accepted with empty
    # metadata (metadata is supplementary; it must not gate the validated set).
    resolver = lambda cid: None
    records = _validated_evaluator_candidates(
        [_aggregate(["catalog:paper-1"])],
        {},
        recall_allowlist={"paper-1"},
        metadata_resolver=resolver,
    )
    assert [r["candidate_id"] for r in records] == ["paper-1"]
    assert "title" not in records[0]
    assert "abstract" not in records[0]


def test_recall_allowlist_from_real_search_output_nonempty():
    """The real Search Worker ``output_json`` is an AgentRun wrapper; the
    durable ``candidates`` live in the nested ``output_json.output_json``.
    ``_work_item_output`` flattens it, and the recall helper must extract a
    non-empty ID set — proving the fix reads the *real* shape, not a synthetic
    one (P0 spec029/030/031; task 81241f3f01885e2c8f0490123f2215f3).
    """
    wrapper = {
        "status": "completed", "schema_version": "runtime-v1",
        "agent_run_id": "run-1", "output_hash": "h", "checkpoint_ref": "c",
        "checkpoint_hash": "ch", "model_metadata": {}, "usage": {},
        "approval_signal": None, "error_code": None, "tool_results": [],
        # Inner, durable evaluator/Search output:
        "output_json": {
            "schema_version": "runtime-v1",
            "work_item_id": "T:s1",
            "source": "usenix",
            "queries": ["side-channel attack detection"],
            "candidates": ["c1dc0e43cad8a4a3", "012003978a4883ce"],
            "source_refs": ["search:9b2c8a78e5ec455fa1ef61b42c487093"],
            "search_id": "9b2c8a78e5ec455fa1ef61b42c487093",
        },
    }
    inner = _work_item_output(wrapper)
    assert "candidates" in inner, "real candidates live under the nested output_json"
    allowlist = _recall_allowlist_from_search_outputs([inner])
    assert allowlist == {"c1dc0e43cad8a4a3", "012003978a4883ce"}, allowlist


def test_aggregate_keep_false_real_shape_returns_nonempty():
    """The real batch evaluator output (task 81241f3f01885e2c8f0490123f2215f3)
    is a single object with ``candidate_id=None`` and top-level ``keep=False``
    (its ``evidence_refs`` list the retained catalog IDs).  The previous unit
    tests masked this by using ``keep=True``.  With a populated recall
    allowlist the aggregate must expand to a non-empty validated set so the
    synthesizer is not skipped (NO_VALIDATED_EVIDENCE).
    """
    real_evaluator = {
        "candidate_id": None,
        "keep": False,
        "evidence_refs": [
            "catalog:paper-1", "catalog:paper-2", "catalog:paper-3",
        ],
        "source_refs": ["usenix_security", "catalog_metadata"],
        "relevance_score": 0.0,
        "reason": "batch evaluator emits one consolidated object",
    }
    resolver = lambda cid: None  # local dir missing -> still accept
    records = _validated_evaluator_candidates(
        [real_evaluator],
        {},  # no Search metadata
        recall_allowlist={"paper-1", "paper-2", "paper-3"},
        metadata_resolver=resolver,
    )
    assert [r["candidate_id"] for r in records] == ["paper-1", "paper-2", "paper-3"]
    # metadata is supplementary: missing locally -> empty, not gating.
    assert "title" not in records[0]
    assert "abstract" not in records[0]


def test_aggregate_keep_false_outside_allowlist_still_rejected():
    """Fail-closed: an aggregate record must NOT expand a catalog ref whose ID
    is absent from the Search recall allowlist, even though keep=False would
    otherwise be ignored for aggregates.
    """
    real_evaluator = {
        "candidate_id": None,
        "keep": False,
        "evidence_refs": ["catalog:paper-1", "catalog:paper-9"],
        "source_refs": [],
    }
    records = _validated_evaluator_candidates(
        [real_evaluator],
        {},
        recall_allowlist={"paper-1"},  # paper-9 not recalled by Search
        metadata_resolver=lambda cid: None,
    )
    assert [r["candidate_id"] for r in records] == ["paper-1"]


def test_per_candidate_reject_keep_false_still_excluded():
    """Regression: a per-candidate record (candidate_id present) with an
    explicit keep=False is still a reject and must be dropped — the aggregate
    relaxation must not turn explicit rejects into accepts.
    """
    rejected = {
        "candidate_id": "paper-2",
        "keep": False,
        "evidence_refs": ["catalog:paper-2"],
        "source_refs": [],
    }
    records = _validated_evaluator_candidates(
        [rejected],
        {},
        recall_allowlist={"paper-1", "paper-2"},
        metadata_resolver=lambda cid: None,
    )
    assert records == []
