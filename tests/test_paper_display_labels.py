"""论文展示名：简称提取与「年份_会议刊物名称_{简称}」拼装。"""

from backend.app.research.application.paper_display import (
    PaperDisplayResolver,
    display_label,
    short_name,
)


def test_short_name_prefers_braced_prefix():
    assert short_name("{SecSMT}: Securing {SMT} Processors against {Contention-Based} Covert Channels") == "SecSMT"


def test_short_name_prefers_quoted_prefix():
    assert short_name('"How Do You Not Lose Friends?": Synthesizing a Design Space') == "How Do You Not Lose Friends?"


def test_short_name_falls_back_to_full_title():
    title = "An Audit of Facebook's Political Ad Policy Enforcement"
    assert short_name(title) == title


def test_short_name_handles_blank():
    assert short_name("") == ""
    assert short_name(None) == ""


def test_display_label_skips_missing_parts():
    assert display_label(2022, "USENIX Security", "SecSMT") == "2022_USENIX Security_SecSMT"
    assert display_label(None, "USENIX Security", "SecSMT") == "USENIX Security_SecSMT"
    assert display_label(2022, "", "SecSMT") == "2022_SecSMT"
    assert display_label(None, "", "") == ""


def test_resolver_returns_empty_projection_for_unknown_id():
    class _NoStore:
        def _connect(self):
            raise RuntimeError("no db")

    resolver = PaperDisplayResolver(_NoStore())
    record = resolver.resolve("unknown-id")
    assert record["paper_id"] == "unknown-id"
    assert record["display_label"] == ""


def test_resolver_reads_candidate_row_and_builds_label():
    class _Row:
        def __init__(self, values):
            self._values = values

        def __getitem__(self, index):
            return self._values[index]

    class _Cursor:
        description = [("title",), ("year",), ("conference_id",), ("conference_name",)]

        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _Conn:
        def __init__(self, rows):
            self._rows = rows

        def execute(self, _sql, _params):
            return _Cursor(self._rows)

        def close(self):
            return None

    class _Store:
        def __init__(self, rows):
            self._rows = rows

        def _connect(self):
            return _Conn(self._rows)

    rows = [("  {SecSMT}: Securing SMT  ", 2022, "usenix-security", "")]
    resolver = PaperDisplayResolver(_Store(rows))
    record = resolver.resolve("c1dc0e43cad8a4a3")
    assert record["short_name"] == "SecSMT"
    assert record["venue"] == "USENIX Security"
    assert record["display_label"] == "2022_USENIX Security_SecSMT"


def test_resolve_many_deduplicates():
    class _NoStore:
        def _connect(self):
            raise RuntimeError("no db")

    resolver = PaperDisplayResolver(_NoStore())
    result = resolver.resolve_many(["a", "a", " b ", "", None])
    assert sorted(result) == ["a", "b"]
