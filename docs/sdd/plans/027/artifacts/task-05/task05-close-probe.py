"""Spec027 Task05 close probe: fixed route/adapter seams plus honest Ollama probe.

This is an evidence-only probe. It never writes to production data, never starts
Ollama, and uses a temporary PaperDiscoveryStore for the fixed CatalogSearchGraph
path. A failed Ollama request is printed as blocked rather than treated as pass.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from backend.app.paper_discovery.application.catalog_search_graph import CatalogRagAdapter
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.platform.config import OLLAMA_BASE_URL
from backend.app.platform.ollama import get_available_models
from backend.app.platform.ollama_direct import chat_direct
from backend.app.research.application.model_router import ModelRouter
from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter


class _FailingQdrant:
    def query_points(self, **kwargs):
        raise RuntimeError("fixed sample qdrant unavailable")


class _FixedAcceptedSource:
    store = None

    def sync_usenix_units(self, *args, **kwargs):
        return SimpleNamespace(status="completed", error_code=None, paper_count=0, waiting=())


def main() -> None:
    print(f"OLLAMA_BASE_URL={OLLAMA_BASE_URL}")
    try:
        print(f"ollama_tags=success models={get_available_models()}")
    except Exception as exc:
        print(f"ollama_tags=blocked {type(exc).__name__}: {exc}")

    calls = []

    def fixed_invoke(model):
        calls.append(model)
        return model == "qwen3.8:27b-mlx", {"model": model}

    router = ModelRouter(available_models_provider=lambda: ["qwen3.5:9b", "qwen3.8:27b-mlx"])
    choice, _value, events = router.execute(
        role="search-worker", task_type="search_catalog", invoke=fixed_invoke
    )
    print(f"fixed_router_choice={choice.tier}/{choice.model}")
    print(f"fixed_router_calls={calls}")
    print(f"fixed_router_events={events}")

    try:
        result = chat_direct(
            [{"role": "user", "content": "Reply exactly OK."}],
            "qwen3.5:9b",
            timeout=3,
            think=False,
            options={"num_predict": 1},
        )
        print(f"ollama_chat=success content={result.content!r} done={result.completed_normally}")
    except Exception as exc:
        print(f"ollama_chat=blocked {type(exc).__name__}: {exc}")

    with TemporaryDirectory(prefix="spec027-task05-") as temp_dir:
        store = PaperDiscoveryStore(Path(temp_dir) / "paper-search.sqlite3")
        rag = CatalogRagAdapter(client=_FailingQdrant(), reranker=None)
        degraded = CatalogSearchAdapter(store=store, rag=rag).search(query="security")
        print(f"adapter_no_sources={degraded}")

        paper = CatalogPaper(
            "fixed-catalog-1", "usenix-security", 2024, "Security Research",
            "security research", abstract="catalog abstract", metadata_hash="hash",
        )
        store.upsert_catalog_paper(paper)
        store.mark_catalog_indexed(paper.catalog_paper_id)
        wired = CatalogSearchAdapter(
            store=store,
            rag=CatalogRagAdapter(client=_FailingQdrant(), reranker=None),
            accepted_source=_FixedAcceptedSource(),
            dblp_source=None,
        ).search(query="security", max_results=5)
        print(f"adapter_fixed_source={wired}")


if __name__ == "__main__":
    main()
