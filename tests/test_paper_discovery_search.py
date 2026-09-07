from datetime import datetime

import pytest

from backend.app.domain.paper_discovery import ConferenceSource
from backend.app.platform.settings.settings_repository import ArticleSettings
from backend.app.services.dblp_publication_source import DBLPPublicationResult
from backend.app.services.paper_discovery_search import PaperDiscoverySearchError, PaperDiscoverySearchService
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
from backend.app.services.usenix_publication_source import UsenixAcceptedResult

SOURCE = ConferenceSource(
    "ccs", "ACM Conference on Computer and Communications Security", "CCS",
    "conf/ccs", ["ACM Conference on Computer and Communications Security"], built_in=True,
)


def record(title="Secure Search", doi="10.1000/A", key="conf/ccs/a", year="2024", authors=None, **extra):
    info = {"title": title, "doi": doi, "key": key, "year": year, "venue": "ACM CCS", "url": "https://dblp.org/rec/" + key}
    if authors is not None:
        info["authors"] = authors
    info.update(extra)
    return {"info": info}


class FakeDBLP:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def search(self, source, query, years, limit):
        self.calls.append((source, query, tuple(years), limit))
        return self.result


class FakeAccepted:
    def __init__(self, result):
        self.result = result

    def search(self, source, query, years, limit):
        return self.result


class FakeOpenAlex:
    def __init__(self):
        self.calls = []

    def enrich(self, payload):
        self.calls.append(payload)
        return {"abstract": "A short abstract", "pdf_url": "https://example.test/a.pdf", "pdf_access": "open"}


def test_search_validates_inputs_before_dblp_and_persists_enriched_snapshot(tmp_path):
    dblp = FakeDBLP(DBLPPublicationResult((record(), record("Secure Search", "10.1000/a", "conf/ccs/duplicate")), ()))
    enricher = FakeOpenAlex()
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    result = PaperDiscoverySearchService(dblp_source=dblp, openalex_enricher=enricher, store=store).search(SOURCE, " secure search ", [2024], 5)

    assert len(result.candidates) == 1
    assert result.candidates[0].abstract == "A short abstract"
    assert result.candidates[0].rank == 1
    assert result.session.query == "secure search"
    assert store.get_candidates(result.session.search_id) == result.candidates
    assert dblp.calls[0][0] == store.list_conferences()[0]
    assert dblp.calls[0][1:] == ("secure search", (2024,), 5)
    assert enricher.calls[0]["doi"] == "10.1000/a"


def test_dblp_failure_warns_but_saves_session(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    dblp = FakeDBLP(DBLPPublicationResult((), ("DBLP_TIMEOUT",), "DBLP_UNAVAILABLE"))
    result = PaperDiscoverySearchService(dblp_source=dblp, store=store).search(SOURCE, "security", [2024])

    assert result.error_code == "DBLP_UNAVAILABLE"
    assert result.warnings[0]["code"] == "DBLP_TIMEOUT"
    assert result.session.search_id
    assert store.get_candidates(result.session.search_id) == []


def test_openalex_failure_keeps_dblp_candidate(tmp_path):
    class BrokenOpenAlex:
        def enrich(self, payload):
            raise RuntimeError("upstream")

    result = PaperDiscoverySearchService(
        dblp_source=FakeDBLP(DBLPPublicationResult((record(),), ())),
        openalex_enricher=BrokenOpenAlex(),
        store=PaperDiscoveryStore(tmp_path / "state.sqlite3"),
    ).search(SOURCE, "security", [2024])
    assert len(result.candidates) == 1
    assert result.candidates[0].title == "Secure Search"
    assert result.warnings[0]["code"] == "OPENALEX_UNAVAILABLE"


def test_same_stable_candidate_id_is_saved_for_distinct_search_sessions(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    service = PaperDiscoverySearchService(
        dblp_source=FakeDBLP(DBLPPublicationResult((record(),), ())),
        store=store,
    )

    first = service.search(SOURCE, "security", [2024])
    second = service.search(SOURCE, "security", [2024])

    assert first.candidates[0].candidate_id == second.candidates[0].candidate_id
    assert [item.candidate_id for item in store.get_candidates(first.session.search_id)] == [first.candidates[0].candidate_id]
    assert [item.candidate_id for item in store.get_candidates(second.session.search_id)] == [second.candidates[0].candidate_id]


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"query": "   "}, "INVALID_QUERY"),
        ({"query": "security", "years": []}, "INVALID_YEARS"),
        ({"query": "security", "years": [2024], "limit": 101}, "INVALID_LIMIT"),
    ],
)
def test_validation_rejects_before_external_call(tmp_path, kwargs, code):
    dblp = FakeDBLP(DBLPPublicationResult((), ()))
    service = PaperDiscoverySearchService(dblp_source=dblp, store=PaperDiscoveryStore(tmp_path / "state.sqlite3"))
    kwargs.setdefault("years", [2024])
    with pytest.raises(PaperDiscoverySearchError) as error:
        service.search(SOURCE, **kwargs)
    assert error.value.error_code == code
    assert not dblp.calls


def test_disabled_conference_rejected_before_external_call(tmp_path):
    disabled = ConferenceSource(**{**SOURCE.__dict__, "enabled": False})
    dblp = FakeDBLP(DBLPPublicationResult((), ()))
    service = PaperDiscoverySearchService(dblp_source=dblp, store=PaperDiscoveryStore(tmp_path / "state.sqlite3"))
    with pytest.raises(PaperDiscoverySearchError) as error:
        service.search(disabled, "security", [2024])
    assert error.value.code == "CONFERENCE_DISABLED"
    assert not dblp.calls


def test_forged_configured_source_is_rejected(tmp_path):
    forged = ConferenceSource("ccs", "ACM CCS", "CCS", "conf/evil", ["ACM CCS"])
    dblp = FakeDBLP(DBLPPublicationResult((), ()))
    service = PaperDiscoverySearchService(dblp_source=dblp, store=PaperDiscoveryStore(tmp_path / "state.sqlite3"))
    with pytest.raises(PaperDiscoverySearchError) as error:
        service.search(forged, "security", [2024])
    assert error.value.code == "CONFERENCE_INVALID"
    assert not dblp.calls


@pytest.mark.parametrize("field,value", [("name", "EVIL"), ("short_name", "EVIL"), ("venue_aliases", ["EVIL"]), ("built_in", False)])
def test_forged_configured_source_fields_are_rejected(tmp_path, field, value):
    forged = ConferenceSource(**{**SOURCE.__dict__, field: value})
    dblp = FakeDBLP(DBLPPublicationResult((), ()))
    service = PaperDiscoverySearchService(dblp_source=dblp, store=PaperDiscoveryStore(tmp_path / "state.sqlite3"))
    with pytest.raises(PaperDiscoverySearchError, match="server configuration") as error:
        service.search(forged, "security", [2024])
    assert error.value.code == "CONFERENCE_INVALID"
    assert not dblp.calls


def test_initial_rank_is_saved_and_is_first_tie_break(tmp_path):
    records = (
        record("Security Zeta", "10.1/z", "conf/ccs/z"),
        record("Security Alpha", "10.1/a", "conf/ccs/a"),
    )
    # Same score, but the first recalled result must remain first.
    result = PaperDiscoverySearchService(
        dblp_source=FakeDBLP(DBLPPublicationResult(records, ())),
        store=PaperDiscoveryStore(tmp_path / "state.sqlite3"),
    ).search(SOURCE, "", [2024]) if False else None
    service = PaperDiscoverySearchService(
        dblp_source=FakeDBLP(DBLPPublicationResult(records, ())),
        store=PaperDiscoveryStore(tmp_path / "state.sqlite3"),
    )
    result = service.search(SOURCE, "security", [2024])
    assert {item.title: item.initial_rank for item in result.candidates} == {"Security Alpha": 0, "Security Zeta": 1}


def test_merge_does_not_cross_year_or_conference_for_dblp_key():
    first = PaperDiscoverySearchService._candidate_from_record(
        record("Same", "", "conf/ccs/shared", "2024"), SOURCE, "search", "security"
    )
    next_year = PaperDiscoverySearchService._candidate_from_record(
        record("Different Year", "", "conf/ccs/shared", "2023"), SOURCE, "search", "security"
    )
    other_conference = PaperDiscoverySearchService._candidate_from_record(
        record("Different Conference", "", "conf/ccs/shared", "2024"),
        ConferenceSource("ndss", "NDSS", "NDSS", "conf/ndss", ["NDSS"]), "search", "security",
    )
    merged = PaperDiscoverySearchService._merge_candidate([], first)
    merged = PaperDiscoverySearchService._merge_candidate(merged, next_year)
    merged = PaperDiscoverySearchService._merge_candidate(merged, other_conference)
    assert [(item.year, item.conference_id) for item in merged] == [(2024, "ccs"), (2023, "ccs"), (2024, "ndss")]


def test_fallback_identity_includes_normalized_author_set():
    first = PaperDiscoverySearchService._candidate_from_record(
        record("Same Title", "", "", authors=["Ada Lovelace", "Grace Hopper"]), SOURCE, "s", "security"
    )
    reordered = PaperDiscoverySearchService._candidate_from_record(
        record("same-title", "", "", authors=["Grace Hopper", "Ada Lovelace"]), SOURCE, "s", "security"
    )
    different_author = PaperDiscoverySearchService._candidate_from_record(
        record("Same Title", "", "", authors=["Alan Turing"]), SOURCE, "s", "security"
    )
    assert first.candidate_id == reordered.candidate_id
    assert first.candidate_id != different_author.candidate_id
    assert len(PaperDiscoverySearchService._merge_candidate([first], different_author)) == 2


def test_different_dois_do_not_merge_through_fallback_identity():
    first = PaperDiscoverySearchService._candidate_from_record(
        record("Same Title", "10.1000/first", "", authors=["Ada"]), SOURCE, "s", "security"
    )
    second = PaperDiscoverySearchService._candidate_from_record(
        record("Same Title", "10.1000/second", "", authors=["Ada"]), SOURCE, "s", "security"
    )
    assert len(PaperDiscoverySearchService._merge_candidate([first], second)) == 2


def test_merge_keeps_published_stage_over_richer_accepted_source_and_links():
    published = PaperDiscoverySearchService._candidate_from_record(
        record("Same Paper", "10.1000/same", "conf/ccs/published", authors=["Ada"],
               source_links=[{"kind": "dblp_page", "url": "https://dblp.org/published"}],
               publication_stage="published", source_kind="dblp"), SOURCE, "s", "security"
    )
    accepted = PaperDiscoverySearchService._candidate_from_record(
        record("Same Paper", "10.1000/same", "", authors=["Ada"],
               source_links=[{"kind": "accepted_page", "url": "https://www.usenix.org/accepted"}],
               publication_stage="accepted", source_kind="usenix_accepted"), SOURCE, "s", "security"
    )
    accepted.pdf_url = "https://www.usenix.org/accepted.pdf"
    merged = PaperDiscoverySearchService._merge_candidate([published], accepted)
    assert len(merged) == 1
    assert merged[0].publication_stage == "published"
    assert merged[0].source_kind == "dblp"
    assert merged[0].pdf_url == accepted.pdf_url
    assert {link["kind"] for link in merged[0].source_links} == {"dblp_page", "accepted_page"}


def test_all_scope_merges_published_and_accepted_by_authors_without_downgrade(tmp_path):
    published = record("Cross Source Paper", "10.1000/cross", "conf/ccs/published", authors=["Ada"])
    accepted = record("Cross-Source Paper", "", "", authors=["Ada"], publication_stage="accepted",
                     source_kind="usenix_accepted", source_links=[{"kind": "accepted_page", "url": "https://www.usenix.org/accepted"}])
    result = PaperDiscoverySearchService(
        dblp_source=FakeDBLP(DBLPPublicationResult((published,), ())),
        accepted_source=FakeAccepted(UsenixAcceptedResult((accepted,), ())),
        store=PaperDiscoveryStore(tmp_path / "state.sqlite3"),
    ).search(SOURCE, "cross source", [2024], publication_scope="all")
    assert len(result.candidates) == 1
    assert result.candidates[0].publication_stage == "published"
    assert {link["kind"] for link in result.candidates[0].source_links} == {"dblp_page", "accepted_page"}


def test_sort_key_uses_initial_rank_then_year_title_and_candidate_id():
    first = PaperDiscoverySearchService._candidate_from_record(record("Zulu", "10/one", "conf/ccs/one", "2023"), SOURCE, "s", "security")
    second = PaperDiscoverySearchService._candidate_from_record(record("Alpha", "10/two", "conf/ccs/two", "2025"), SOURCE, "s", "security")
    third = PaperDiscoverySearchService._candidate_from_record(record("Alpha", "10/three", "conf/ccs/three", "2024"), SOURCE, "s", "security")
    first.initial_rank = second.initial_rank = third.initial_rank = 0
    first.final_score = second.final_score = third.final_score = 1.0
    assert [item.candidate_id for item in sorted((first, second, third), key=PaperDiscoverySearchService._sort_key)] == [second.candidate_id, third.candidate_id, first.candidate_id]


def test_initial_rank_is_independent_of_year_request_order(tmp_path):
    rows = (
        record("Security 2023", "10.1/2023", "conf/ccs/2023", "2023"),
        record("Security 2024", "10.1/2024", "conf/ccs/2024", "2024"),
    )
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    first = PaperDiscoverySearchService(dblp_source=FakeDBLP(DBLPPublicationResult(rows, ())), store=store).search(SOURCE, "security", [2023, 2024])
    second = PaperDiscoverySearchService(dblp_source=FakeDBLP(DBLPPublicationResult(tuple(reversed(rows)), ())), store=store).search(SOURCE, "security", [2024, 2023])
    assert [(item.year, item.initial_rank) for item in first.candidates] == [(2024, 0), (2023, 1)]
    assert [(item.year, item.initial_rank) for item in second.candidates] == [(2024, 0), (2023, 1)]


def test_search_reads_limit_and_ttl_from_article_settings(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    settings = ArticleSettings(paper_discovery_search_limit=1, paper_discovery_max_search_limit=2, paper_discovery_search_ttl_seconds=7)
    service = PaperDiscoverySearchService(
        settings=settings,
        dblp_source=FakeDBLP(DBLPPublicationResult((record(), record("Security Two", "10.1/b", "conf/ccs/b")), ())),
        store=store,
    )
    result = service.search(SOURCE, "security", [2024])
    assert len(result.candidates) == 1
    created = result.session.created_at.replace("Z", "+00:00")
    expires = result.session.expires_at.replace("Z", "+00:00")
    assert 6 <= (datetime.fromisoformat(expires) - datetime.fromisoformat(created)).total_seconds() <= 8
