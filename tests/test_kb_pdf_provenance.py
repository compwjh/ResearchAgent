"""Task02A PDF provenance contract and regression tests."""

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.app.knowledge_base.infrastructure import parse as parse_module
from backend.app.knowledge_base.infrastructure.normalize import (
    locate_reference_start,
    normalize_text,
)
from backend.app.knowledge_base.infrastructure.parse import (
    PdfParseError,
    _normalized_bbox,
    _validate_bbox_in_crop,
    extract_pages,
    extract_pages_normalized,
    extract_pdf_provenance,
)

FIXTURES = Path(__file__).parents[1] / "docs" / "sdd" / "fixtures" / "spec-018"
PROVENANCE_SCHEMA = (
    Path(__file__).parents[1]
    / "docs"
    / "sdd"
    / "plans"
    / "018"
    / "artifacts"
    / "task-02a"
    / "pdf-source-provenance.schema.json"
)


def _assert_strict_schema(instance: dict) -> None:
    schema = json.loads(PROVENANCE_SCHEMA.read_text())
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def _legacy_normalized(path: Path):
    pages = extract_pages(path)
    ref_start = locate_reference_start(pages)
    normalized = []
    for page, text in pages:
        ref_zone = ref_start is not None and page >= ref_start
        cleaned = normalize_text(text, ref_zone=ref_zone)
        if cleaned:
            normalized.append((page, cleaned))
    return normalized


@pytest.mark.parametrize(
    "sample_id",
    [
        "pdf-single-column-v1",
        "pdf-two-column-v1-overlap",
        "pdf-v2-cross-page",
        "pdf-no-text-layer",
        "pdf-hostile-features",
    ],
)
def test_pdf_provenance_matches_fixed_display_fixture(sample_id: str) -> None:
    pdf_path = FIXTURES / f"{sample_id}.pdf"
    expected = json.loads((FIXTURES / f"{sample_id}.expected.json").read_text())

    provenance = extract_pdf_provenance(
        pdf_path,
        document_id=expected["document_id"],
        sample_id=sample_id,
    )
    actual = provenance.to_dict()
    _assert_strict_schema(actual)

    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["status"] == expected["status"]
    assert actual["error"] == expected["error"]
    assert actual["pages"] == expected["pages"]
    assert len(actual["blocks"]) == len(expected["blocks"])
    for bundle_field in (
        "mapping_algorithm_version",
        "indexed_source_sha256",
        "source_hash_state",
        "chunker",
        "chunker_config",
        "payload_schema_version",
        "index_fingerprint",
        "mapped_count",
        "unmapped_count",
        "chunks",
        "anchors",
    ):
        assert bundle_field not in actual

    for actual_block, expected_block in zip(actual["blocks"], expected["blocks"], strict=False):
        for key in (
            "block_id",
            "ordinal",
            "page",
            "text",
            "raw_text",
            "start",
            "end",
            "bbox",
            "block_type",
            "heading_path",
        ):
            assert actual_block[key] == expected_block[key]
        assert actual_block["normalized_bbox"] == pytest.approx(
            expected_block["normalized_bbox"], abs=0.005
        )
        assert len(actual_block["lines"]) == len(expected_block["lines"])
        for actual_line, expected_line in zip(actual_block["lines"], expected_block["lines"], strict=False):
            for key in ("ordinal", "text", "start", "end", "bbox"):
                assert actual_line[key] == expected_line[key]
            assert actual_line["normalized_bbox"] == pytest.approx(
                expected_line["normalized_bbox"], abs=0.005
            )


def test_pdf_provenance_source_hash_is_current_lowercase_and_static_hostile_status() -> None:
    pdf_path = FIXTURES / "pdf-hostile-features.pdf"
    expected = json.loads((FIXTURES / "pdf-hostile-features.expected.json").read_text())
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert source_hash == expected["source_sha256"]

    provenance = extract_pdf_provenance(pdf_path, source_sha256=source_hash.upper())
    assert provenance.source_sha256 == source_hash
    assert provenance.status == "partial"
    assert provenance.error == "HOSTILE_FEATURES_NOT_EXECUTED"
    assert len(provenance.blocks) == 2


@pytest.mark.parametrize(
    "sample_id",
    [
        "pdf-single-column-v1",
        "pdf-two-column-v1-overlap",
        "pdf-v2-cross-page",
        "pdf-no-text-layer",
        "pdf-hostile-features",
    ],
)
def test_fixed_fixture_normalized_projection_is_exact_legacy(sample_id: str) -> None:
    path = FIXTURES / f"{sample_id}.pdf"
    assert extract_pages_normalized(path) == _legacy_normalized(path)


def test_benign_uri_annotation_is_not_hostile(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = tmp_path / "ordinary-uri.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "ordinary link")
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(72, 72, 200, 90),
            "uri": "https://example.invalid/no-fetch",
        }
    )
    document.save(pdf_path)
    document.close()

    provenance = extract_pdf_provenance(pdf_path)
    assert provenance.status == "ready"
    assert provenance.error is None


def test_pdf_provenance_rejects_source_hash_mismatch_without_path_leakage() -> None:
    with pytest.raises(PdfParseError, match="PDF_SOURCE_HASH_MISMATCH") as raised:
        extract_pdf_provenance(FIXTURES / "pdf-single-column-v1.pdf", source_sha256="0" * 64)
    assert raised.value.code == "PDF_SOURCE_HASH_MISMATCH"
    assert str(raised.value) == "PDF_SOURCE_HASH_MISMATCH"


def test_pdf_provenance_maps_io_and_open_errors_to_stable_codes(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(PdfParseError, match="PDF_SOURCE_READ_FAILED") as missing_error:
        extract_pdf_provenance(missing)
    assert str(missing_error.value) == "PDF_SOURCE_READ_FAILED"
    assert str(missing) not in str(missing_error.value)

    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"not a pdf")
    with pytest.raises(PdfParseError, match="PDF_OPEN_FAILED") as malformed_error:
        extract_pdf_provenance(malformed)
    assert str(malformed_error.value) == "PDF_OPEN_FAILED"
    assert str(malformed) not in str(malformed_error.value)


def test_pdf_provenance_fail_closed_on_active_feature_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parse_module, "_inspect_active_features", lambda _document: "unavailable")
    provenance = extract_pdf_provenance(FIXTURES / "pdf-single-column-v1.pdf")
    assert provenance.status == "failed"
    assert provenance.error == "PDF_PROVENANCE_UNAVAILABLE"


def test_pdf_provenance_rejects_malformed_bbox_without_clamping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def malformed_display(_page):
        return {"blocks": [{"type": 0, "bbox": [0, 0, 10000, 10000], "text": "bad"}]}

    monkeypatch.setattr(parse_module, "_display_dict", malformed_display)
    with pytest.raises(PdfParseError, match="PDF_PROVENANCE_UNAVAILABLE") as raised:
        extract_pdf_provenance(FIXTURES / "pdf-single-column-v1.pdf")
    assert raised.value.code == "PDF_PROVENANCE_UNAVAILABLE"


def test_bbox_renderer_overflow_uses_spec_normalized_tolerance() -> None:
    crop_box = (0.0, 0.0, 100.0, 100.0)
    tolerated = (0.0, 0.0, 100.5, 100.0)
    rejected = (0.0, 0.0, 100.51, 100.0)

    assert _validate_bbox_in_crop(tolerated, crop_box) is True
    assert _normalized_bbox(
        tolerated,
        100.0,
        100.0,
        tolerate_renderer_overflow=True,
    ) == (0.0, 0.0, 1.0, 1.0)
    with pytest.raises(PdfParseError, match="PDF_PROVENANCE_UNAVAILABLE"):
        _validate_bbox_in_crop(rejected, crop_box)


def test_pdf_size_limit_returns_stable_error(tmp_path: Path) -> None:
    path = tmp_path / "oversize.pdf"
    with path.open("wb") as stream:
        stream.seek(parse_module._MAX_PDF_BYTES)
        stream.write(b"x")

    with pytest.raises(PdfParseError, match="PDF_TOO_LARGE") as raised:
        extract_pdf_provenance(path)
    assert raised.value.code == "PDF_TOO_LARGE"
    assert str(path) not in str(raised.value)


def test_encrypted_pdf_returns_stable_error(tmp_path: Path) -> None:
    import pymupdf

    path = tmp_path / "encrypted.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "encrypted")
    document.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="user-password",
    )
    document.close()

    with pytest.raises(PdfParseError, match="PDF_ENCRYPTED") as raised:
        extract_pdf_provenance(path)
    assert raised.value.code == "PDF_ENCRYPTED"


def test_zero_page_document_branch_returns_stable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import pymupdf

    class EmptyDocument:
        is_encrypted = False
        page_count = 0

        def close(self):
            pass

    monkeypatch.setattr(pymupdf, "open", lambda **_kwargs: EmptyDocument())
    with pytest.raises(PdfParseError, match="PDF_EMPTY") as raised:
        extract_pdf_provenance(FIXTURES / "pdf-single-column-v1.pdf")
    assert raised.value.code == "PDF_EMPTY"


def test_normalized_projection_is_exact_legacy_order_and_one_dict_call_per_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pymupdf

    calls = []
    original_get_text = pymupdf.Page.get_text
    path = FIXTURES / "pdf-v2-cross-page.pdf"
    expected = _legacy_normalized(path)

    def spy_get_text(page, kind="text", *args, **kwargs):
        calls.append(kind)
        return original_get_text(page, kind, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_text", spy_get_text)
    assert extract_pages_normalized(path) == expected
    assert calls == ["dict", "dict"]


def test_source_bytes_are_read_once_and_reused_for_hash_and_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    original_read = parse_module._read_pdf_bytes

    def spy_read(path):
        calls.append(path)
        return original_read(path)

    monkeypatch.setattr(parse_module, "_read_pdf_bytes", spy_read)
    extract_pdf_provenance(FIXTURES / "pdf-single-column-v1.pdf")
    assert len(calls) == 1


def test_non_monotonic_insertion_order_preserves_legacy_and_sorts_provenance(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = tmp_path / "non-monotonic.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 220), "LOWER INSERTED FIRST")
    page.insert_text((72, 100), "UPPER INSERTED SECOND")
    document.save(pdf_path)
    document.close()

    assert extract_pages_normalized(pdf_path) == _legacy_normalized(pdf_path)
    provenance = extract_pdf_provenance(pdf_path)
    assert [block.text for block in provenance.blocks] == [
        "UPPER INSERTED SECOND",
        "LOWER INSERTED FIRST",
    ]
    assert [block.display_ordinal for block in provenance.blocks] == [1, 0]


def test_reference_page_image_block_and_blank_page_projection(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = tmp_path / "mixed-pages.pdf"
    document = pymupdf.open()
    document.new_page()  # blank page must remain omitted after normalization
    page = document.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 540, 160),
        "References\n[1] Alpha et al. In ICML, 2023.",
    )
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 8, 8), 0)
    page.insert_image(pymupdf.Rect(72, 200, 100, 228), pixmap=pixmap)
    page.insert_text((72, 260), "Text after image")
    document.save(pdf_path)
    document.close()

    assert extract_pages_normalized(pdf_path) == _legacy_normalized(pdf_path)
    normalized = extract_pages_normalized(pdf_path)
    assert [page for page, _ in normalized] == [2]
    assert "[1] Alpha et al." in normalized[0][1]
    assert "Text after image" in normalized[0][1]


def test_rotated_pdf_uses_unrotated_crop_box_for_normalization(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = tmp_path / "rotated.pdf"
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.insert_text((100, 20), "rotated provenance")
    page.set_rotation(90)
    document.save(pdf_path)
    document.close()

    provenance = extract_pdf_provenance(pdf_path)
    assert provenance.pages[0].rotation == 90
    assert provenance.pages[0].width == 200
    assert provenance.pages[0].height == 100
    assert all(0 <= value <= 1 for value in provenance.blocks[0].normalized_bbox)
