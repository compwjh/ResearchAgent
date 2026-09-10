"""Task02A-C SourceProvenanceBundle integration contract tests."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from backend.app.knowledge_base.infrastructure import provenance as provenance_module
from backend.app.knowledge_base.infrastructure.chunkers import Chunk
from backend.app.knowledge_base.infrastructure.markdown import (
    MarkdownBlockProvenanceV1,
    MarkdownSourceProvenanceV1,
    extract_markdown_provenance,
)
from backend.app.knowledge_base.infrastructure.parse import extract_pdf_provenance
from backend.app.knowledge_base.infrastructure.provenance import (
    SourceProvenanceBundleError,
    build_source_provenance_bundle,
    validate_source_provenance_bundle,
)

FIXTURES = Path(__file__).parents[1] / "docs" / "sdd" / "fixtures" / "spec-018"
SCHEMA = (
    Path(__file__).parents[1]
    / "docs"
    / "sdd"
    / "plans"
    / "018"
    / "artifacts"
    / "task-02a"
    / "source-provenance-bundle.schema.json"
)


def _validate(instance: dict) -> None:
    schema = json.loads(SCHEMA.read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: list(error.path),
    )
    assert not errors, "\n".join(error.message for error in errors)


def _assert_expected_projection(actual: dict, expected: dict) -> None:
    assert actual["document_id"] == expected["document_id"]
    assert actual["chunker"] == expected["chunker"]
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["source_hash_state"] == "verified"
    assert actual["source_parser_version"]
    assert actual["normalize_version"]
    assert actual["status"] == expected["status"]
    assert actual["progress"] == 100
    assert actual["error"] == expected["error"]
    assert actual["pages"] == expected["pages"]
    assert len(actual["blocks"]) == len(expected["blocks"])
    for actual_block, expected_block in zip(actual["blocks"], expected["blocks"], strict=True):
        for key, value in expected_block.items():
            assert actual_block[key] == value
    for actual_chunk, expected_chunk in zip(actual["chunks"], expected["chunks"], strict=True):
        for key, value in expected_chunk.items():
            assert actual_chunk[key] == value
    assert actual["chunker_config"] == expected["chunker_config"]
    assert actual["chunker_config_fingerprint"] == expected["chunker_config_fingerprint"]
    assert actual["payload_schema_version"] == expected["payload_schema_version"]
    assert len(actual["chunk_snapshot_fingerprint"]) == 64
    assert "index_fingerprint" not in actual
    assert all(
        set(anchor) == {"block_id", "chunk_index", "coverage", "is_primary", "locator"}
        for anchor in actual["anchors"]
    )
    assert actual["mapped_count"] == expected["mapped_count"]
    assert actual["unmapped_count"] == expected["unmapped_count"]
    assert actual["unmapped_reasons"] == expected["unmapped_reasons"]


@pytest.mark.parametrize(
    ("sample_id", "chunker"),
    [
        ("pdf-single-column-v1", "v1"),
        ("pdf-two-column-v1-overlap", "v1"),
        ("pdf-v2-cross-page", "v2"),
        ("markdown-blocks", "markdown-block-v1"),
    ],
)
def test_formal_parser_and_reused_chunker_match_fixed_bundle_projection(
    sample_id: str,
    chunker: str,
) -> None:
    expected = json.loads((FIXTURES / f"{sample_id}.expected.json").read_text())
    if expected["media_type"] == "application/pdf":
        provenance = extract_pdf_provenance(
            FIXTURES / f"{sample_id}.pdf",
            document_id=expected["document_id"],
            sample_id=sample_id,
        )
    else:
        provenance = extract_markdown_provenance(
            FIXTURES / f"{sample_id}.md",
            document_id=expected["document_id"],
            sample_id=sample_id,
        )

    bundle = build_source_provenance_bundle(provenance, chunker=chunker)
    actual = bundle.to_dict()
    _validate(actual)
    _assert_expected_projection(actual, expected)
    assert actual["source_parser_version"] == provenance.source_parser_version
    assert actual["normalize_version"] == provenance.normalize_version
    assert actual["payload_schema_version"] == "qdrant-payload-v1"
    assert actual["schema_version"] == "source-provenance-bundle-v1"
    assert actual["mapping_algorithm_version"] == "source-anchor-v2"
    if chunker == "v2":
        assert actual["llm_used"] is False
        assert actual["degradation_diagnostics"] == ["V2_RULES_ONLY_LLM_NOT_USED"]
    else:
        assert actual["llm_used"] is False
        assert actual["degradation_diagnostics"] == []
    assert "manifest" not in actual
    assert "embedding" not in actual
    assert "qdrant" not in actual


@pytest.mark.parametrize(
    ("sample_id", "chunker"),
    [
        ("pdf-no-text-layer", "v1"),
        ("markdown-hostile", "markdown-block-v1"),
    ],
)
def test_controlled_partial_and_no_text_states_are_preserved(
    sample_id: str,
    chunker: str,
) -> None:
    expected = json.loads((FIXTURES / f"{sample_id}.expected.json").read_text())
    if expected["media_type"] == "application/pdf":
        provenance = extract_pdf_provenance(
            FIXTURES / f"{sample_id}.pdf",
            document_id=expected["document_id"],
            sample_id=sample_id,
        )
    else:
        provenance = extract_markdown_provenance(
            FIXTURES / f"{sample_id}.md",
            document_id=expected["document_id"],
            sample_id=sample_id,
        )
    actual = build_source_provenance_bundle(provenance, chunker=chunker).to_dict()
    _validate(actual)
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["status"] == expected["status"]
    assert actual["error"] == expected["error"]
    if sample_id == "pdf-no-text-layer":
        assert actual["mapped_count"] == 0
    else:
        assert actual["mapped_count"] > 0
    assert actual["unmapped_count"] == 0


def test_markdown_chunks_keep_null_page_contract() -> None:
    provenance = extract_markdown_provenance(
        FIXTURES / "markdown-blocks.md",
        document_id="fixture-markdown-blocks",
        sample_id="markdown-blocks",
    )
    bundle = build_source_provenance_bundle(provenance, chunker="markdown-block-v1")
    chunks = bundle.to_dict()["chunks"]
    assert all(chunk["page"] is None and chunk["page_end"] is None for chunk in chunks)
    assert all(chunk["start_line"] <= chunk["end_line"] for chunk in chunks)


def test_unknown_chunker_is_fail_closed() -> None:
    provenance = extract_markdown_provenance("# heading", document_id="unknown")
    with pytest.raises(SourceProvenanceBundleError, match="CHUNKER_UNSUPPORTED"):
        build_source_provenance_bundle(provenance, chunker="v3")


def test_repeated_text_overlap_uses_exact_source_range_order() -> None:
    expected = json.loads((FIXTURES / "pdf-two-column-v1-overlap.expected.json").read_text())
    provenance = extract_pdf_provenance(
        FIXTURES / "pdf-two-column-v1-overlap.pdf",
        document_id=expected["document_id"],
        sample_id="pdf-two-column-v1-overlap",
    )
    bundle = build_source_provenance_bundle(provenance, chunker="v1").to_dict()
    scores = {
        (item["block_id"].split(":")[-1], item["chunk_index"]): item["coverage"]
        for item in bundle["anchors"]
    }
    assert set(scores) == {("b0", 0), ("b1", 0), ("b1", 1), ("b2", 1)}
    assert scores[("b0", 0)] == pytest.approx(769 / 979, abs=1e-6)
    assert scores[("b1", 0)] == pytest.approx(209 / 979, abs=1e-6)
    assert scores[("b1", 1)] == pytest.approx(759 / 818, abs=1e-6)
    assert scores[("b2", 1)] == pytest.approx(58 / 818, abs=1e-6)
    assert ("b2", 0) not in scores
    assert ("b0", 1) not in scores
    for chunk_index in range(2):
        primary = [item for item in bundle["anchors"] if item["chunk_index"] == chunk_index and item["is_primary"]]
        assert len(primary) == 1


def test_v2_valid_empty_llm_decision_is_used_without_degradation() -> None:
    expected = json.loads((FIXTURES / "pdf-v2-cross-page.expected.json").read_text())
    provenance = extract_pdf_provenance(
        FIXTURES / "pdf-v2-cross-page.pdf",
        document_id=expected["document_id"],
        sample_id="pdf-v2-cross-page",
    )
    actual = build_source_provenance_bundle(
        provenance, chunker="v2", llm=lambda _prompt: "[]"
    ).to_dict()
    assert actual["llm_used"] is True
    assert actual["degradation_diagnostics"] == []


def test_v2_heading_only_maps_to_chunks_with_real_source_range() -> None:
    provenance = extract_markdown_provenance(
        "# Introduction\n\nThis paragraph belongs to the introduction.\n\n"
        "# Results\n\nThis paragraph belongs to results.",
        document_id="heading-range",
    )

    bundle = build_source_provenance_bundle(
        provenance,
        chunker="v2",
        chunker_config={"max_chars": 40},
    ).to_dict()
    heading_id = provenance.blocks[0].block_id
    heading_anchors = [
        item for item in bundle["anchors"] if item["block_id"] == heading_id
    ]

    assert len(heading_anchors) == 1
    assert heading_anchors[0]["chunk_index"] == 0
    assert len(bundle["anchors"]) <= len(bundle["chunks"]) + 1
    assert bundle["mapped_count"] == len(bundle["chunks"])


def test_unresolved_chunk_has_no_anchor_and_no_fuzzy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provenance = extract_markdown_provenance(
        "alpha source block", document_id="unresolved-range"
    )

    def fake_build_chunks(*_args, **_kwargs):
        return [Chunk(text="delta absent from source", page=None, chunk_index=0)]

    monkeypatch.setattr(provenance_module, "build_chunks_v1", fake_build_chunks)
    bundle = build_source_provenance_bundle(
        provenance,
        chunker="markdown-block-v1",
    ).to_dict()

    assert bundle["anchors"] == []
    assert bundle["mapped_count"] == 0
    assert bundle["unmapped_count"] == 1
    assert bundle["unmapped_reasons"] == [
        {"chunk_index": 0, "reason": "SOURCE_RANGE_UNRESOLVED"}
    ]
    assert bundle["status"] == "partial"


def test_duplicate_exact_chunk_occurrences_are_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provenance = extract_markdown_provenance(
        "repeat repeat", document_id="duplicate-range"
    )

    def fake_build_chunks(*_args, **_kwargs):
        return [Chunk(text="repeat", page=None, chunk_index=0)]

    monkeypatch.setattr(provenance_module, "build_chunks_v1", fake_build_chunks)
    bundle = build_source_provenance_bundle(
        provenance,
        chunker="markdown-block-v1",
    ).to_dict()

    assert bundle["anchors"] == []
    assert bundle["unmapped_reasons"] == [
        {"chunk_index": 0, "reason": "SOURCE_RANGE_UNRESOLVED"}
    ]


def test_mapping_copy_normalizes_source_and_block_with_same_projection() -> None:
    block = SimpleNamespace(block_id="ligature", text="A ﬁnance block")

    stream = provenance_module._stream_with_block_ranges(
        "fixture",
        "A ﬁnance block",
        (block,),
    )

    assert stream.valid is True
    assert stream.text == "A finance block"
    assert [(item.start, item.end) for item in stream.blocks] == [(0, len(stream.text))]
    assert block.text == "A ﬁnance block"


def test_pdf_mapping_copy_keeps_cross_block_hyphen_ranges_exact() -> None:
    first = SimpleNamespace(
        block_id="first",
        text="transac-",
        raw_text="transac-\n",
    )
    second = SimpleNamespace(
        block_id="second",
        text="tion body",
        raw_text="tion body\n",
    )
    blocks = (first, second)
    mapped = provenance_module._pdf_mapping_block_texts(blocks, ref_zone=False)
    stream = provenance_module._stream_with_block_ranges(
        "fixture",
        "transaction body",
        blocks,
        mapped,
    )

    assert mapped == ("transac", "tion body")
    assert stream.valid is True
    assert [(item.start, item.end) for item in stream.blocks] == [(0, 7), (7, 16)]


@pytest.mark.parametrize(
    "sample_id",
    [
        "pdf-single-column-v1",
        "pdf-two-column-v1-overlap",
        "pdf-hostile-features",
    ],
)
def test_pdf_v2_preserves_display_blocks_for_injected_llm(sample_id: str) -> None:
    expected = json.loads((FIXTURES / f"{sample_id}.expected.json").read_text())
    provenance = extract_pdf_provenance(
        FIXTURES / f"{sample_id}.pdf",
        document_id=expected["document_id"],
        sample_id=sample_id,
    )
    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return "[]"

    actual = build_source_provenance_bundle(provenance, chunker="v2", llm=llm).to_dict()
    assert len(calls) >= 1
    assert actual["llm_used"] is True
    assert actual["degradation_diagnostics"] == []


def test_schema_rejects_malformed_anchor_locator() -> None:
    expected = json.loads((FIXTURES / "pdf-single-column-v1.expected.json").read_text())
    provenance = extract_pdf_provenance(
        FIXTURES / "pdf-single-column-v1.pdf",
        document_id=expected["document_id"],
        sample_id="pdf-single-column-v1",
    )
    actual = build_source_provenance_bundle(provenance, chunker="v1").to_dict()
    actual["anchors"][0]["locator"].pop("page")
    schema = json.loads(SCHEMA.read_text())
    errors = list(Draft202012Validator(schema).iter_errors(actual))
    assert errors


def test_bundle_rejects_oversize_source_block_before_chunking() -> None:
    block = SimpleNamespace(text="x" * (1024 * 1024 + 1))
    provenance = SimpleNamespace(
        source_sha256="0" * 64,
        blocks=(block,),
        media_type="text/markdown",
    )
    with pytest.raises(SourceProvenanceBundleError, match="PROVENANCE_BUNDLE_BLOCK_TOO_LARGE"):
        build_source_provenance_bundle(provenance, chunker="markdown-block-v1")


def _canonical_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _markdown_capacity_provenance(block: MarkdownBlockProvenanceV1) -> MarkdownSourceProvenanceV1:
    return MarkdownSourceProvenanceV1(
        document_id="capacity-boundary",
        source_sha256="0" * 64,
        normalized_text=block.text,
        blocks=(block,),
        status="ready",
        error=None,
        line_count=block.end_line,
    )


def _find_exact_public_item_boundary(
    make_bundle,
    item_key: str,
    limit: int,
) -> tuple[int, object]:
    """Find an exact serialized boundary using only the public builder path."""
    low = 0
    high = limit + 4096
    best = None
    while low <= high:
        candidate = (low + high) // 2
        try:
            bundle = make_bundle(candidate)
        except SourceProvenanceBundleError:
            high = candidate - 1
            continue
        size = _canonical_size(bundle.to_dict()[item_key][0])
        if size <= limit:
            best = (candidate, bundle)
            low = candidate + 1
        else:
            high = candidate - 1
    assert best is not None
    candidate, bundle = best
    assert _canonical_size(bundle.to_dict()[item_key][0]) == limit
    return candidate, bundle


def test_real_markdown_dto_public_builder_enforces_block_boundary() -> None:
    limit = 2 * 1024 * 1024

    def make_bundle(diagnostic_length: int):
        block = MarkdownBlockProvenanceV1(
            block_id="block-boundary",
            ordinal=0,
            text="x",
            start=0,
            end=1,
            start_line=1,
            end_line=1,
            heading_path=(),
            block_type="paragraph",
            diagnostics=("x" * diagnostic_length,),
        )
        return build_source_provenance_bundle(
            _markdown_capacity_provenance(block), chunker="markdown-block-v1"
        )

    diagnostic_length, exact = _find_exact_public_item_boundary(make_bundle, "blocks", limit)
    assert _canonical_size(exact.to_dict()["blocks"][0]) == limit
    with pytest.raises(
        SourceProvenanceBundleError,
        match="PROVENANCE_BUNDLE_BLOCK_SERIALIZED_TOO_LARGE",
    ):
        make_bundle(diagnostic_length + 1)


def test_real_markdown_dto_public_builder_enforces_chunk_boundary() -> None:
    limit = 512 * 1024

    def make_bundle(section_length: int):
        block = MarkdownBlockProvenanceV1(
            block_id="chunk-boundary",
            ordinal=0,
            text="x",
            start=0,
            end=1,
            start_line=1,
            end_line=1,
            heading_path=("x" * section_length,),
            block_type="paragraph",
        )
        return build_source_provenance_bundle(
            _markdown_capacity_provenance(block), chunker="markdown-block-v1"
        )

    section_length, exact = _find_exact_public_item_boundary(make_bundle, "chunks", limit)
    assert _canonical_size(exact.to_dict()["chunks"][0]) == limit
    with pytest.raises(
        SourceProvenanceBundleError,
        match="PROVENANCE_BUNDLE_CHUNK_SERIALIZED_TOO_LARGE",
    ):
        make_bundle(section_length + 1)


def test_real_markdown_dto_public_builder_enforces_anchor_boundary() -> None:
    limit = 4 * 1024

    def make_bundle(block_id_length: int):
        block = MarkdownBlockProvenanceV1(
            block_id="a" * block_id_length,
            ordinal=0,
            text="x",
            start=0,
            end=1,
            start_line=1,
            end_line=1,
            heading_path=(),
            block_type="paragraph",
        )
        return build_source_provenance_bundle(
            _markdown_capacity_provenance(block), chunker="markdown-block-v1"
        )

    block_id_length, exact = _find_exact_public_item_boundary(make_bundle, "anchors", limit)
    assert _canonical_size(exact.to_dict()["anchors"][0]) == limit
    with pytest.raises(
        SourceProvenanceBundleError,
        match="PROVENANCE_BUNDLE_ANCHOR_SERIALIZED_TOO_LARGE",
    ):
        make_bundle(block_id_length + 1)


def test_public_validator_enforces_bundle_boundary_with_real_bundle() -> None:
    provenance = extract_markdown_provenance(
        FIXTURES / "markdown-blocks.md",
        document_id="fixture-markdown-blocks",
        sample_id="markdown-blocks",
    )
    bundle = build_source_provenance_bundle(provenance, chunker="markdown-block-v1")
    bundle_limit = 256 * 1024 * 1024
    validate_source_provenance_bundle(bundle, serialized_size=bundle_limit)
    with pytest.raises(
        SourceProvenanceBundleError,
        match="PROVENANCE_BUNDLE_SERIALIZED_TOO_LARGE",
    ):
        validate_source_provenance_bundle(bundle, serialized_size=bundle_limit + 1)
