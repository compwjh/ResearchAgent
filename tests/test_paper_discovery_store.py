import sqlite3
import pytest
from backend.app.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
def test_store_seeds_reads_and_enforces_candidate_doi(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    assert len(store.list_conferences()) == 4
    session = SearchSession("search", "agent security", "2099-01-01T00:00:00Z")
    candidate = PaperCandidate("candidate", "search", "Paper", "ccs", "CCS", authors=["Ada"], doi="10/a")
    store.save_search(session, [candidate])
    assert store.get_candidates("search") == [candidate]
    with store._connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO paper_candidates(candidate_id,search_id,title,normalized_title,conference_id,conference_name,authors,pdf_access,retrieval_score,final_score,rank,doi) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("other", "search", "Other", "other", "ccs", "CCS", "[]", "unknown", 0, 0, 0, "10/a"))


def test_store_allows_stable_candidate_id_across_search_sessions(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    candidate = PaperCandidate("stable", "first", "Paper", "ccs", "CCS", doi="10/a")
    store.save_search(SearchSession("first", "security", "2099-01-01T00:00:00Z"), [candidate])

    same_paper = PaperCandidate("stable", "second", "Paper", "ccs", "CCS", doi="10/a")
    store.save_search(SearchSession("second", "security", "2099-01-01T00:00:00Z"), [same_paper])

    assert store.get_candidates("first")[0].candidate_id == "stable"
    assert store.get_candidates("second")[0].candidate_id == "stable"


def test_store_rejects_multiple_schema_metadata_rows(tmp_path):
    path = tmp_path / "state.sqlite3"
    PaperDiscoveryStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX schema_meta_singleton")
        connection.execute("INSERT INTO schema_meta(version) VALUES(1)")
    with pytest.raises(RuntimeError, match="exactly one row"):
        PaperDiscoveryStore(path)


def test_store_rejects_damaged_schema_metadata_table(tmp_path):
    path = tmp_path / "state.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_meta(bad TEXT)")
    with pytest.raises(RuntimeError, match="malformed schema_meta"):
        PaperDiscoveryStore(path)


def test_save_conference_explicit_transaction_is_committed(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    source = store.list_conferences()[0]
    source.enabled = False
    store.save_conference(source)
    assert next(item for item in store.list_conferences() if item.conference_id == source.conference_id).enabled is False
