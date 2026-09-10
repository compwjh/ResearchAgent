import sqlite3
import threading

import pytest

from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    CatalogSourceRecord,
    PaperCandidate,
    SearchJob,
    SearchResult,
    SearchSession,
    SourceFetchUnit,
)
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


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


# --- Spec015 Task13 子任务C：v2 仓储方法测试（仅追加，不改动既有 5 个用例） ----------

def _make_catalog_paper(paper_id, metadata_hash="h1", conference_id="ccs", title="Paper"):
    return CatalogPaper(
        catalog_paper_id=paper_id,
        conference_id=conference_id,
        year=2099,
        title=title,
        normalized_title=title.lower(),
        authors=["Ada"],
        metadata_hash=metadata_hash,
    )


def test_upsert_catalog_paper_metadata_hash_semantics(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    t0 = "2099-01-01T00:00:00Z"
    t1 = "2099-01-02T00:00:00Z"
    t2 = "2099-01-03T00:00:00Z"
    t3 = "2099-01-04T00:00:00Z"

    # 首次写入：新行，返回 True，index_status='pending'。
    assert store.upsert_catalog_paper(_make_catalog_paper("p1", "h1"), now=t0) is True
    row = store.get_catalog_paper("p1")
    assert row.metadata_hash == "h1"
    assert row.index_status == "pending"
    assert row.updated_at == t0

    # 同一 hash 重复写入：不更新 updated_at，返回 False。
    assert store.upsert_catalog_paper(_make_catalog_paper("p1", "h1"), now=t1) is False
    after_same = store.get_catalog_paper("p1")
    assert after_same.updated_at == t0
    assert after_same.metadata_hash == "h1"
    assert after_same.index_status == "pending"

    # 不同 hash：写入并把 index_status 重置为 'pending'，返回 True。
    assert store.upsert_catalog_paper(_make_catalog_paper("p1", "h2"), now=t2) is True
    after_diff = store.get_catalog_paper("p1")
    assert after_diff.metadata_hash == "h2"
    assert after_diff.index_status == "pending"
    assert after_diff.updated_at == t2

    # 再次同 hash（h2）保持不更新。
    assert store.upsert_catalog_paper(_make_catalog_paper("p1", "h2"), now=t3) is False
    assert store.get_catalog_paper("p1").updated_at == t2


def test_acquire_fetch_unit_atomic_single_winner_across_10_rounds(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    # 主实例创建 schema 与 fetch unit（lease_owner 初始为 NULL）。
    main = PaperDiscoveryStore(db_path)
    unit = SourceFetchUnit("unit-1", "usenix", "usenix-security", 2099, "cycle1-accepted")
    main.save_fetch_unit(unit, now="2099-01-01T00:00:00Z")

    owners = 3
    now = "2099-01-15T00:00:00Z"
     # 顺序创建各线程的独立 store 实例：__init__ 含建表 DDL，必须顺序执行以避免锁竞争
     # 与 barrier 死锁；acquire 阶段每线程使用自己的实例/连接。
    worker_stores = [PaperDiscoveryStore(db_path) for _ in range(owners)]
    for _ in range(10):
        # 每轮重置该 unit 为可领取状态（lease_owner/lease_expires_at 置 NULL）。
        with main._connect() as connection:
            connection.execute(
                "UPDATE source_fetch_units SET lease_owner=NULL, lease_expires_at=NULL "
                "WHERE fetch_unit_id=?", ("unit-1",)
            )
        results = [False] * owners
        barrier = threading.Barrier(owners)
        def worker(index, store):
            barrier.wait()
            results[index] = store.acquire_fetch_unit("unit-1", f"owner-{index}", 30, now=now)
        threads = [
            threading.Thread(target=worker, args=(i, store))
            for i, store in enumerate(worker_stores)
           ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for ok in results if ok) == 1


def test_acquire_fetch_unit_expired_lease_can_be_recovered(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    store = PaperDiscoveryStore(db_path)
    store.save_fetch_unit(
        SourceFetchUnit("unit-x", "dblp", "ccs", 2099, "y2099"),
        now="2099-01-01T00:00:00Z",
    )
    # owner A 成功领取。
    assert store.acquire_fetch_unit("unit-x", "owner-A", 30, now="2099-01-01T00:00:00Z") is True

    # 把租约到期时间回拨到过去，使 A 的租约视为过期。
    with store._connect() as connection:
        connection.execute(
            "UPDATE source_fetch_units SET lease_expires_at=? WHERE fetch_unit_id=?",
            ("2098-01-01T00:00:00Z", "unit-x"),
        )
    # 过期后 owner B 可重新领取。
    assert store.acquire_fetch_unit("unit-x", "owner-B", 30, now="2099-02-01T00:00:00Z") is True
    unit = store.get_fetch_unit("unit-x")
    assert unit.lease_owner == "owner-B"


def test_get_search_results_page_freezes_21_rows(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    store.create_search_job(
        SearchJob("s1", "agent security", total_results=21,
                  expires_at="2099-12-31T00:00:00Z", created_at="2099-01-01T00:00:00Z"),
    )
    for rank in range(1, 22):
        store.upsert_catalog_paper(
            _make_catalog_paper(f"cat-{rank}", title=f"Paper {rank}"),
            now="2099-01-01T00:00:00Z",
        )
    for rank in range(1, 22):
        store.save_search_result(
            SearchResult(
                "s1", f"cat-{rank}", rank, retrieval_score=float(rank),
                rerank_score=None, final_score=float(rank),
                snapshot={"rank": rank}, created_at="2099-01-01T00:00:00Z",
            ),
        )

    page1 = store.get_search_results_page("s1", 1)
    page2 = store.get_search_results_page("s1", 2)
    page3 = store.get_search_results_page("s1", 3)
    assert [r.rank for r in page1] == list(range(1, 11))
    assert [r.rank for r in page2] == list(range(11, 21))
    assert [r.rank for r in page3] == [21]

    # 同一页两次读取顺序一致（基于 rank 冻结）。
    reread = store.get_search_results_page("s1", 1)
    assert [r.rank for r in reread] == [r.rank for r in page1]


def test_save_source_record_is_traceable(tmp_path):
    import json
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    store.upsert_catalog_paper(_make_catalog_paper("p9"), now="2099-01-01T00:00:00Z")
    store.save_fetch_unit(
        SourceFetchUnit("fu-9", "usenix", "usenix-security", 2099, "cycle1-accepted"),
        now="2099-01-01T00:00:00Z",
    )
    store.save_source_record(
        CatalogSourceRecord(
            source_record_id="sr-9",
            catalog_paper_id="p9",
            fetch_unit_id="fu-9",
            source_kind="usenix",
            source_key="usenix//cycle1-accepted",
            raw_metadata={"title": "Raw Paper", "venue": "USENIX"},
            observed_at="2099-01-01T00:00:00Z",
        ),
    )
    with store._connect() as connection:
        row = connection.execute(
            "SELECT raw_metadata_json FROM catalog_source_records "
            "WHERE source_kind=? AND source_key=?",
            ("usenix", "usenix//cycle1-accepted"),
        ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == {"title": "Raw Paper", "venue": "USENIX"}
