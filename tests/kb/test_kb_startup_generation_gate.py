import inspect
from datetime import datetime, timedelta, timezone

from backend.app import main
from backend.app.api import common
from backend.app.paper_discovery.domain.paper_discovery import SearchJob
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


def test_startup_does_not_run_legacy_fixed_collection_mutations():
    source = inspect.getsource(main.lifespan)
    assert "mark_interrupted_on_startup" not in source
    assert "backfill_chunker_defaults" not in source
    assert "index_paper" not in source
    assert "delete_paper" not in source
    assert "create_alias" not in source


def test_generation_gate_is_checked_without_mutating_index(monkeypatch):
    calls = []

    class ProbeFinalizeStore:
        def __init__(self, root):
            calls.append(("init", root))

        def require_generation(self):
            calls.append(("require_generation",))
            raise RuntimeError("INDEX_REBUILD_REQUIRED")

    monkeypatch.setattr(main, "FinalizeBundleStore", ProbeFinalizeStore)
    monkeypatch.setattr(main, "recover_paper_catalog_searches", lambda: 0)

    async def run_lifespan():
        async with main.lifespan(main.app):
            assert calls[-1][0] == "require_generation"

    import asyncio

    asyncio.run(run_lifespan())
    assert [call[0] for call in calls] == ["init", "require_generation"]


def test_startup_exercises_real_catalog_recovery_without_kb_persistent_writes(tmp_path, monkeypatch):
    """The catalog recovery transaction is real; the KB generation gate is read-only."""
    catalog_path = tmp_path / "paper-search.sqlite3"
    catalog = PaperDiscoveryStore(database_path=catalog_path)
    catalog.create_search_job(SearchJob(
        search_id="search-recovery",
        query="security",
        status="running",
        created_at="2026-09-10T00:00:00Z",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    ))
    submitted = []
    monkeypatch.setattr(common, "_paper_store", lambda: catalog)
    monkeypatch.setattr(common, "submit_paper_catalog_search", submitted.append)
    kb_dir = tmp_path / "data" / "kb"
    monkeypatch.setattr(main, "KB_DIR", kb_dir)
    assert not kb_dir.exists()

    import asyncio

    async def run_lifespan():
        async with main.lifespan(main.app):
            recovered = catalog.get_search_job("search-recovery")
            assert recovered is not None
            assert recovered.status == "queued"
            assert submitted == ["search-recovery"]

    asyncio.run(run_lifespan())
    assert not kb_dir.exists()
    assert catalog_path.exists()
