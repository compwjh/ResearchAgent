from dataclasses import dataclass

import pytest

from backend.app.services.paper_import_identity import (
    build_paper_filename,
    build_paper_identity,
    canonical_doi,
    deduplicate_candidates,
    filename_for_candidate,
    identity_keys_for_candidate,
    paper_identity_keys,
    unique_paper_filename,
)


def test_filename_keeps_unicode_and_uses_server_conference_component():
    name = build_paper_filename(2025, "IEEE S&P", "隐私/保护: A Secure\nSystem")
    assert name == "2025-IEEE-S-P-隐私-保护-A-Secure-System.pdf"
    assert "/" not in name and "\\" not in name


@pytest.mark.parametrize("title", ["", "///***", "\x00\x01\t"])
def test_empty_or_illegal_title_has_safe_fallback(title):
    name = build_paper_filename(None, "CCS", title)
    assert name == "UnknownYear-CCS-Untitled.pdf"


def test_reserved_component_is_not_emitted_as_reserved_name():
    name = build_paper_filename(2025, "CCS", "CON")
    assert name.rsplit("-", 1)[-1].casefold() != "con.pdf"
    assert name.endswith(".pdf")


def test_only_title_is_truncated_and_filename_is_bounded():
    name = build_paper_filename(2025, "CCS", "标题" * 300)
    assert len(name) == 180
    assert name.startswith("2025-CCS-")


def test_tiny_limit_rejects_without_truncating_server_prefix():
    with pytest.raises(ValueError):
        build_paper_filename(2025, "A very long server conference", "Title", max_length=10)


def test_doi_prefix_variants_share_identity():
    values = [
        "10.1000/ABC.",
        "doi: 10.1000/abc",
        "https://doi.org/10.1000/ABC",
        "http://dx.doi.org/10.1000/abc",
    ]
    assert {canonical_doi(value) for value in values} == {"10.1000/abc"}
    assert paper_identity_keys(doi=values[0]) == {"doi:10.1000/abc"}
    assert canonical_doi("https://evil.example/paper.pdf") == ""


def test_identity_supports_dblp_and_scoped_title_fallback():
    identity = build_paper_identity(
        dblp_key="CONF/CCS/Paper",
        title="Résumé: Same-Title",
        year="2024",
        conference_id="CCS",
        conference_name="attacker supplied display name",
    )
    assert identity.dblp_key == "conf/ccs/paper"
    assert "key:conf/ccs/paper:2024:ccs" in identity.keys
    assert "title:resumesametitle:2024:ccs" in identity.keys
    assert identity_keys_for_candidate({
        "title": "Résumé: Same-Title", "year": 2024, "conference_id": "CCS",
        "conference_name": "evil", "article_url": "https://evil.example/x.pdf",
    }) == {"title:resumesametitle:2024:ccs"}


@dataclass
class Candidate:
    title: str
    year: int
    conference_id: str
    doi: str = ""
    dblp_key: str = ""


def test_deduplicate_candidates_uses_identity_not_display_title_or_urls():
    first = Candidate("First display title", 2024, "ccs", doi="doi:10.1/X")
    same_doi = Candidate("Completely different display title", 2024, "ccs", doi="https://doi.org/10.1/x")
    same_title = {"title": "Same", "year": 2024, "conference_id": "ccs", "article_url": "https://a/x"}
    same_title_again = {"title": "Same!", "year": "2024", "conference_id": "CCS", "article_url": "https://b/y"}
    unique = deduplicate_candidates([first, same_doi, same_title, same_title_again])
    assert unique == [first, same_title]


def test_different_dois_do_not_collapse_only_because_display_title_matches():
    first = {"title": "Same", "year": 2024, "conference_id": "ccs", "doi": "10.1/first"}
    second = {"title": "Same", "year": 2024, "conference_id": "ccs", "doi": "10.1/second"}
    assert deduplicate_candidates([first, second]) == [first, second]


def test_missing_doi_does_not_collapse_into_doi_record_by_title():
    with_doi = {"title": "Same", "year": 2024, "conference_id": "ccs", "doi": "10.1/first"}
    without_doi = {"title": "Same", "year": 2024, "conference_id": "ccs"}
    assert deduplicate_candidates([with_doi, without_doi]) == [with_doi, without_doi]


def test_collision_gets_stable_identity_suffix_and_is_bounded():
    identity = build_paper_identity(doi="10.1234/second", title="Same", year=2025, conference_id="ccs")
    first = build_paper_filename(2025, "CCS", "Same")
    result = unique_paper_filename(2025, "CCS", "Same", identity=identity, existing_names=[first], max_length=40)
    repeat = unique_paper_filename(2025, "CCS", "Same", identity=identity, existing_names=[first], max_length=40)
    assert result == repeat
    assert result != first
    assert len(result) <= 40
    assert result.endswith(".pdf")


def test_candidate_filename_uses_explicit_server_name_and_ignores_untrusted_fields():
    candidate = {
        "title": "A Paper",
        "year": 2025,
        "conference_id": "ccs",
        "conference_name": "../../evil",
        "article_url": "file:///etc/passwd",
        "pdf_url": "https://evil.example/x.pdf",
    }
    assert filename_for_candidate(candidate, "CCS") == "2025-CCS-A-Paper.pdf"
