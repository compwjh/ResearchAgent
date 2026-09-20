"""快照刷新必须能补齐「不在原会话里」的选集论文。

多 Search Worker 扇出时，研究任务只持久化了其中一个 search_id，而用户确认的选集
可能来自另一个 worker 的快照。刷新器若只复制原会话的候选，刷新完仍然
CANDIDATE_NOT_FOUND。因为 candidate_id 是内容派生的（同一篇论文在任意会话下元数据
一致），可以从其它会话把缺失的行补进新快照。
"""

from pathlib import Path

import pytest

from backend.app.api import common
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.api.routes_research import _search_snapshot_refresher


def _candidate(candidate_id: str, search_id: str, rank: int = 1) -> PaperCandidate:
    return PaperCandidate(
        candidate_id=candidate_id, search_id=search_id, title=f"Title {candidate_id}",
        conference_id="usenix-security", conference_name="USENIX Security Symposium",
        year=2022, rank=rank, initial_rank=rank, normalized_title=candidate_id,
    )


def _store(tmp_path: Path) -> PaperDiscoveryStore:
    return PaperDiscoveryStore(tmp_path / "paper_search.sqlite3")


def _session(search_id: str, query: str = "access control") -> SearchSession:
    return SearchSession(search_id=search_id, query=query, expires_at="2020-01-01T00:00:00Z",
                         created_at="2020-01-01T00:00:00Z")


def _refresher(store, monkeypatch):
    monkeypatch.setattr(common, "_paper_store", lambda: store)
    return _search_snapshot_refresher()


def test_missing_papers_are_backfilled_from_other_sessions(tmp_path: Path, monkeypatch):
    """原会话只含 a；选集还有 b、c（来自另一个 worker 的会话）。"""
    store = _store(tmp_path)
    store.save_search(_session("search-old"), [_candidate("paper-a", "search-old")])
    store.save_search(_session("search-other"), [
        _candidate("paper-b", "search-other"),
        _candidate("paper-c", "search-other"),
    ])

    refreshed = _refresher(store, monkeypatch)(
        "search-old", ["paper-a", "paper-b", "paper-c"]
    )

    assert refreshed and refreshed != "search-old"
    ids = {item.candidate_id for item in store.get_candidates(refreshed)}
    assert ids == {"paper-a", "paper-b", "paper-c"}
    # 补齐的行必须挂在新句柄下，导入桥才会认。
    assert all(item.search_id == refreshed for item in store.get_candidates(refreshed))


def test_backfill_keeps_original_snapshot_rows(tmp_path: Path, monkeypatch):
    """刷新不能丢掉原快照里没被选中的论文（导入桥按快照解析）。"""
    store = _store(tmp_path)
    store.save_search(_session("search-old"), [
        _candidate("paper-a", "search-old", 1),
        _candidate("paper-z", "search-old", 2),
    ])
    store.save_search(_session("search-other"), [_candidate("paper-b", "search-other")])

    refreshed = _refresher(store, monkeypatch)("search-old", ["paper-a", "paper-b"])

    ids = {item.candidate_id for item in store.get_candidates(refreshed)}
    assert ids == {"paper-a", "paper-z", "paper-b"}


def test_refresh_returns_none_when_no_wanted_paper_is_known(tmp_path: Path, monkeypatch):
    """连一篇都补不齐时不返回句柄：那只会换来一次必然失败的建批次。"""
    store = _store(tmp_path)
    store.save_search(_session("search-old"), [_candidate("paper-a", "search-old")])

    assert _refresher(store, monkeypatch)("search-old", ["paper-x", "paper-y"]) is None


def test_refresh_without_session_backfills_from_any_session(tmp_path: Path, monkeypatch):
    """连原会话都没有（只剩一个孤立的 search_id）时，仍能靠补齐重建句柄。"""
    store = _store(tmp_path)
    store.save_search(_session("search-other"), [
        _candidate("paper-b", "search-other"),
        _candidate("paper-c", "search-other"),
    ])

    refreshed = _refresher(store, monkeypatch)("search-ghost", ["paper-b", "paper-c"])

    assert refreshed
    assert {item.candidate_id for item in store.get_candidates(refreshed)} == {"paper-b", "paper-c"}


def test_get_candidates_by_ids_deduplicates_across_sessions(tmp_path: Path):
    store = _store(tmp_path)
    store.save_search(_session("s1"), [_candidate("paper-a", "s1", 1)])
    store.save_search(_session("s2"), [_candidate("paper-a", "s2", 2)])

    found = store.get_candidates_by_ids(["paper-a"])

    assert len(found) == 1
    assert found[0].candidate_id == "paper-a"


def test_get_candidates_by_ids_ignores_unknown_ids(tmp_path: Path):
    store = _store(tmp_path)
    store.save_search(_session("s1"), [_candidate("paper-a", "s1")])

    assert store.get_candidates_by_ids(["paper-a", "paper-nope"]) [0].candidate_id == "paper-a"
    assert store.get_candidates_by_ids([]) == []
