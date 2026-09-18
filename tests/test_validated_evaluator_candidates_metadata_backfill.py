"""P0: aggregate evaluator metadata backfill (spec029/030/031).

Regression guard for the synthesizer-skip bug: when a Search Worker's
tool_results omit ``catalog_metadata``, the recall allowlist (proven by the
Search Worker's actual recall) must still expand aggregate evaluator refs,
backfilling metadata from the local catalog directory.  Model evaluator
output must never supply metadata.
"""

from backend.app.research.application.orchestrator import (
    _validated_evaluator_candidates,
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
