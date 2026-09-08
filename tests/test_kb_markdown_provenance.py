"""Spec018 Task02A-B Markdown provenance contract tests."""

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.app.knowledge_base.infrastructure import markdown as markdown_module
from backend.app.knowledge_base.infrastructure.markdown import (
    MarkdownParseError,
    _read_source,
    extract_markdown_provenance,
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
    / "markdown-source-provenance.schema.json"
)

_PURE_METRIC_KEYS = (
    "page_count",
    "line_count",
    "block_count",
    "image_count",
    "diagnostic_count",
    "markdown_line_exact_rate",
)

# The first-round bundle fixtures predate the pure-parser DTO and therefore do
# not carry image/diagnostic counts. Freeze those two parser-only values here;
# the remaining four values come directly from each frozen expected fixture.
_PURE_PARSER_METRIC_ORACLE = {
    "markdown-blocks": {"image_count": 0, "diagnostic_count": 0},
    "markdown-hostile": {"image_count": 2, "diagnostic_count": 6},
}


def _validate(instance: dict) -> None:
    schema = json.loads(SCHEMA.read_text())
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def _assert_expected_blocks(provenance, expected: dict) -> None:
    actual_blocks = [block.to_dict() for block in provenance.blocks]
    expected_blocks = expected["blocks"]
    assert len(actual_blocks) == len(expected_blocks)
    for actual, expected_block in zip(actual_blocks, expected_blocks, strict=True):
        assert {key: actual[key] for key in expected_block} == expected_block


def _assert_pure_metrics(provenance, expected: dict, *, sample_id: str) -> None:
    """Compare the complete six-field pure-parser metrics projection exactly."""
    actual_metrics = provenance.to_dict()["metrics"]
    expected_metrics = expected["metrics"]
    parser_only = _PURE_PARSER_METRIC_ORACLE[sample_id]
    expected_projection = {
        "page_count": expected_metrics["page_count"],
        "line_count": expected_metrics["line_count"],
        "block_count": expected_metrics["block_count"],
        "image_count": parser_only["image_count"],
        "diagnostic_count": parser_only["diagnostic_count"],
        "markdown_line_exact_rate": expected_metrics["markdown_line_exact_rate"],
    }
    assert set(actual_metrics) == set(_PURE_METRIC_KEYS)
    assert {key: actual_metrics[key] for key in _PURE_METRIC_KEYS} == expected_projection


def _assert_pure_dto_fields(provenance, *, hostile: bool) -> None:
    actual = provenance.to_dict()
    assert all(
        block["page"] is None and block["page_end"] is None
        for block in actual["blocks"]
    )
    assert [block["diagnostics"] for block in actual["blocks"]] == (
        [
            [],
            ["HOSTILE_HTML_OR_JAVASCRIPT", "NO_ACTIVE_CONTENT_EXECUTION"],
            ["HOSTILE_HTML_OR_JAVASCRIPT", "NO_ACTIVE_CONTENT_EXECUTION"],
            ["HOSTILE_HTML_OR_JAVASCRIPT", "NO_ACTIVE_CONTENT_EXECUTION"],
            [],
            [],
        ]
        if hostile
        else [[] for _ in actual["blocks"]]
    )
    if not hostile:
        assert all(block["inline_resources"] == [] for block in actual["blocks"])
        return
    assert actual["blocks"][0]["inline_resources"] == []
    assert actual["blocks"][1]["inline_resources"] == []
    assert actual["blocks"][2]["inline_resources"] == []
    assert actual["blocks"][3]["inline_resources"] == []
    assert actual["blocks"][4]["inline_resources"] == [
        {
            "resource_id": "markdown-hostile:b4:r0",
            "kind": "image",
            "alt": "remote image",
            "destination": "https://remote.invalid/image.png",
            "title": None,
            "loadable": False,
            "placeholder": "[image: remote image]",
        }
    ]
    assert actual["blocks"][5]["inline_resources"] == [
        {
            "resource_id": "markdown-hostile:b5:r0",
            "kind": "image",
            "alt": "relative image",
            "destination": "./attachment.png",
            "title": None,
            "loadable": False,
            "placeholder": "[image: relative image]",
        }
    ]


def test_fixed_markdown_fixture_matches_source_hash_and_exact_ranges() -> None:
    path = FIXTURES / "markdown-blocks.md"
    expected = json.loads((FIXTURES / "markdown-blocks.expected.json").read_text())
    provenance = extract_markdown_provenance(
        path,
        document_id=expected["document_id"],
        sample_id="markdown-blocks",
    )
    actual = provenance.to_dict()
    _validate(actual)

    assert actual["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["status"] == "ready"
    assert actual["error"] is None
    _assert_expected_blocks(provenance, expected)
    _assert_pure_dto_fields(provenance, hostile=False)
    _assert_pure_metrics(provenance, expected, sample_id="markdown-blocks")
    assert [block["block_type"] for block in actual["blocks"]] == [
        "heading",
        "paragraph",
        "list",
        "table",
        "code",
    ]
    assert [block["locator"] for block in actual["blocks"]] == [
        {"start_line": 1, "end_line": 1},
        {"start_line": 3, "end_line": 3},
        {"start_line": 5, "end_line": 6},
        {"start_line": 8, "end_line": 10},
        {"start_line": 12, "end_line": 14},
    ]
    assert [(block["start"], block["end"]) for block in actual["blocks"]] == [
        (0, 23),
        (25, 121),
        (123, 159),
        (161, 215),
        (217, 247),
    ]
    assert all(block["page"] is None and block["page_end"] is None for block in actual["blocks"])


def test_hostile_fixture_only_marks_diagnostics_and_never_loads_images() -> None:
    provenance = extract_markdown_provenance(
        FIXTURES / "markdown-hostile.md",
        document_id="fixture-markdown-hostile",
        sample_id="markdown-hostile",
    )
    actual = provenance.to_dict()
    _validate(actual)
    expected = json.loads((FIXTURES / "markdown-hostile.expected.json").read_text())
    _assert_expected_blocks(provenance, expected)
    _assert_pure_dto_fields(provenance, hostile=True)
    assert actual["source_sha256"] == expected["source_sha256"]
    assert actual["status"] == expected["status"]
    assert actual["error"] == expected["error"]
    _assert_pure_metrics(provenance, expected, sample_id="markdown-hostile")
    assert provenance.status == "partial"
    assert provenance.error == "HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE"
    assert [block.ordinal for block in provenance.blocks] == list(range(6))
    assert [(block.start_line, block.end_line) for block in provenance.blocks] == [
        (1, 1),
        (3, 3),
        (5, 5),
        (7, 7),
        (9, 9),
        (11, 11),
    ]
    assert all(
        resource.loadable is False
        for block in provenance.blocks
        for resource in block.inline_resources
    )
    assert sum(len(block.inline_resources) for block in provenance.blocks) == 2
    assert any("NO_ACTIVE_CONTENT_EXECUTION" in block.diagnostics for block in provenance.blocks)


def test_all_required_block_boundaries_and_heading_paths() -> None:
    source = (
        "# Root\n\n"
        "Paragraph line one\nparagraph continuation\n\n"
        "- first\n  continuation\n  - nested\n- second\n\n"
        "| A | B |\n| --- | :---: |\n| one | two |\n\n"
        "```python\nprint('x')\n```\n\n"
        "> quote one\n> quote two\n\n"
        "---\n\n"
        "<section>\nhtml body\n</section>\n\n"
        "## Child\n\nchild paragraph\n"
    )
    provenance = extract_markdown_provenance(source, document_id="boundary")
    assert [block.block_type for block in provenance.blocks] == [
        "heading",
        "paragraph",
        "list",
        "table",
        "code",
        "blockquote",
        "horizontal_rule",
        "html",
        "heading",
        "paragraph",
    ]
    assert provenance.blocks[0].heading_path == ("Root",)
    assert provenance.blocks[1].heading_path == ("Root",)
    assert provenance.blocks[8].heading_path == ("Root", "Child")
    assert provenance.blocks[9].heading_path == ("Root", "Child")
    assert provenance.blocks[2].text == "- first\n  continuation\n  - nested\n- second"
    assert provenance.blocks[3].text == "| A | B |\n| --- | :---: |\n| one | two |"
    assert provenance.blocks[4].text == "```python\nprint('x')\n```"
    assert all(
        left.end <= right.start
        for left, right in zip(provenance.blocks, provenance.blocks[1:], strict=False)
    )


def test_list_lazy_quote_and_multiline_html_keep_one_block_range() -> None:
    source = (
        "- item\n\n"
        "  continuation after blank\n\n"
        "> quoted line\n"
        "lazy quote continuation\n\n"
        "<div>\n"
        "html body\n\n"
        "</div>\n"
    )
    provenance = extract_markdown_provenance(source, document_id="lazy-blocks")
    assert [block.block_type for block in provenance.blocks] == ["list", "blockquote", "html"]
    assert provenance.blocks[0].text == "- item\n\n  continuation after blank"
    assert provenance.blocks[1].text == "> quoted line\nlazy quote continuation"
    assert provenance.blocks[2].text == "<div>\nhtml body\n\n</div>"
    assert provenance.blocks[0].start_line == 1 and provenance.blocks[0].end_line == 3
    assert provenance.blocks[1].start_line == 5 and provenance.blocks[1].end_line == 6
    assert provenance.blocks[2].start_line == 8 and provenance.blocks[2].end_line == 11


def test_bom_crlf_cr_are_normalized_but_hash_uses_original_bytes() -> None:
    source = b"\xef\xbb\xbf# H\r\n\r\nalpha\rbeta\r\n"
    provenance = extract_markdown_provenance(source, document_id="line-endings")
    assert provenance.source_sha256 == hashlib.sha256(source).hexdigest()
    assert provenance.normalized_text == "# H\n\nalpha\nbeta\n"
    assert "\r" not in provenance.normalized_text
    assert provenance.line_count == 4
    assert provenance.blocks[0].start_line == 1
    assert provenance.blocks[0].end_line == 1
    assert provenance.blocks[1].start_line == 3
    assert provenance.blocks[1].end_line == 4
    _validate(provenance.to_dict())


@pytest.mark.parametrize("source", [b"\xff\xfe", b"# bad\x00nul\n"])
def test_invalid_utf8_and_nul_are_stable_invalid_encoding(source: bytes) -> None:
    with pytest.raises(MarkdownParseError, match="INVALID_ENCODING") as raised:
        extract_markdown_provenance(source)
    assert raised.value.code == "INVALID_ENCODING"
    assert str(raised.value) == "INVALID_ENCODING"


@pytest.mark.parametrize("source", [b"", b"\xef\xbb\xbf", b" \t\r\n\t "])
def test_empty_bom_only_and_whitespace_documents_are_rejected(source: bytes) -> None:
    with pytest.raises(MarkdownParseError, match="MARKDOWN_PARSE_FAILED") as raised:
        extract_markdown_provenance(source, document_id="empty")
    assert raised.value.code == "MARKDOWN_PARSE_FAILED"


def test_single_block_one_mib_boundary_is_exact() -> None:
    exact = "a" * markdown_module._MAX_MARKDOWN_BLOCK_BYTES
    provenance = extract_markdown_provenance(exact, document_id="one-mib")
    assert len(provenance.blocks) == 1
    assert len(provenance.blocks[0].text.encode("utf-8")) == 1 * 1024 * 1024

    with pytest.raises(MarkdownParseError, match="MARKDOWN_BLOCK_TOO_LARGE") as raised:
        extract_markdown_provenance(exact + "a", document_id="one-mib-plus-one")
    assert raised.value.code == "MARKDOWN_BLOCK_TOO_LARGE"


def test_stream_reader_accepts_50_mib_and_rejects_50_mib_plus_one(tmp_path: Path) -> None:
    class GeneratedStream:
        def __init__(self, total: int):
            self.remaining = total
            self.max_request = 0

        def read(self, size: int) -> bytes:
            self.max_request = max(self.max_request, size)
            count = min(size, self.remaining)
            self.remaining -= count
            return b"a" * count

    exact_stream = GeneratedStream(markdown_module._MAX_MARKDOWN_BYTES)
    exact = _read_source(exact_stream)
    assert len(exact) == markdown_module._MAX_MARKDOWN_BYTES
    assert exact_stream.max_request <= markdown_module._READ_CHUNK_BYTES

    full_source = b"\n\n".join([b"a" * 1_000_000] * 52 + [b"a" * 428_696])
    assert len(full_source) == markdown_module._MAX_MARKDOWN_BYTES
    accepted = extract_markdown_provenance(full_source, document_id="fifty-mib")
    assert len(accepted.blocks) == 53

    with pytest.raises(MarkdownParseError, match="PAYLOAD_TOO_LARGE") as raised:
        _read_source(GeneratedStream(markdown_module._MAX_MARKDOWN_BYTES + 1))
    assert raised.value.code == "PAYLOAD_TOO_LARGE"

    path = tmp_path / "over-limit.md"
    with path.open("wb") as stream:
        stream.write(b"a" * markdown_module._MAX_MARKDOWN_BYTES)
        stream.write(b"a")
    with pytest.raises(MarkdownParseError, match="PAYLOAD_TOO_LARGE") as raised:
        extract_markdown_provenance(path)
    assert raised.value.code == "PAYLOAD_TOO_LARGE"


def test_raw_string_reader_enforces_50_mib_limit() -> None:
    exact = "a" * markdown_module._MAX_MARKDOWN_BYTES
    assert len(_read_source(exact)) == markdown_module._MAX_MARKDOWN_BYTES
    del exact

    with pytest.raises(MarkdownParseError, match="PAYLOAD_TOO_LARGE") as raised:
        _read_source("a" * (markdown_module._MAX_MARKDOWN_BYTES + 1))
    assert raised.value.code == "PAYLOAD_TOO_LARGE"


def test_long_line_is_safe() -> None:
    long_line = "a" * 100_000
    provenance = extract_markdown_provenance(long_line, document_id="long-line")
    assert len(provenance.blocks) == 1
    assert provenance.blocks[0].start == 0
    assert provenance.blocks[0].end == len(long_line)


def test_block_limit_is_stable_and_exactly_200000(monkeypatch: pytest.MonkeyPatch) -> None:
    assert markdown_module._MAX_MARKDOWN_BLOCKS == 200_000
    monkeypatch.setattr(markdown_module, "_MAX_MARKDOWN_BLOCKS", 2)
    with pytest.raises(MarkdownParseError, match="MARKDOWN_BLOCK_LIMIT") as raised:
        extract_markdown_provenance("# one\n\n# two\n\n# three\n")
    assert raised.value.code == "MARKDOWN_BLOCK_LIMIT"


def test_image_metadata_is_independent_and_javascript_is_not_executed() -> None:
    source = "![alt](https://example.invalid/a.png)\n\n![local](./a.png)\n"
    provenance = extract_markdown_provenance(source, document_id="images")
    resources = [resource for block in provenance.blocks for resource in block.inline_resources]
    assert [resource.destination for resource in resources] == [
        "https://example.invalid/a.png",
        "./a.png",
    ]
    assert all(resource.loadable is False for resource in resources)
    assert all(resource.placeholder for resource in resources)
    assert provenance.status == "ready"

    hostile = extract_markdown_provenance("[x](javascript:alert(1))", document_id="js")
    assert hostile.status == "partial"
    assert "NO_ACTIVE_CONTENT_EXECUTION" in hostile.blocks[0].diagnostics


def test_hash_mismatch_is_stable_and_does_not_leak_source() -> None:
    with pytest.raises(MarkdownParseError, match="SOURCE_HASH_MISMATCH") as raised:
        extract_markdown_provenance("# H", source_sha256="0" * 64)
    assert raised.value.code == "SOURCE_HASH_MISMATCH"
    assert str(raised.value) == "SOURCE_HASH_MISMATCH"


def test_non_string_source_hash_is_stable() -> None:
    with pytest.raises(MarkdownParseError, match="SOURCE_HASH_INVALID") as raised:
        extract_markdown_provenance("# H", source_sha256=object())
    assert raised.value.code == "SOURCE_HASH_INVALID"


def test_schema_annotates_utf8_bytes_and_parser_rejects_multibyte_overflow() -> None:
    schema = json.loads(SCHEMA.read_text())
    text_schema = schema["$defs"]["block"]["properties"]["text"]
    assert text_schema["x-max-utf8-bytes"] == 1 * 1024 * 1024
    assert "maxLength" not in text_schema

    multilingual = "汉" * 600_000
    assert len(multilingual.encode("utf-8")) > 1 * 1024 * 1024
    with pytest.raises(MarkdownParseError, match="MARKDOWN_BLOCK_TOO_LARGE") as raised:
        extract_markdown_provenance(multilingual, document_id="multibyte-overflow")
    assert raised.value.code == "MARKDOWN_BLOCK_TOO_LARGE"

    instance = extract_markdown_provenance("# H", document_id="schema-codepoint")
    instance_dict = instance.to_dict()
    instance_dict["normalized_text"] = multilingual
    instance_dict["blocks"][0]["text"] = multilingual
    assert list(Draft202012Validator(schema).iter_errors(instance_dict)) == []
