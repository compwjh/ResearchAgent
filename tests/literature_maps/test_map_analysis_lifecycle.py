from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from backend.app.chat.application.chat_runner import ChatRun
from backend.app.literature_maps.application.analysis import MapAnalysisService
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.memory.repository import MemoryRepository
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


class _InlineRecordingExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, function, *args, **kwargs):
        self.submissions.append((function, args, kwargs))
        return function(*args, **kwargs)


def _chat_run(content: str) -> ChatRun:
    run = ChatRun(route="direct", events=iter(()))
    run.result = OllamaChatResult(
        content=content,
        thinking="",
        timings=OllamaTimings(),
        timings_available=False,
        first_token_ms=0,
        client_wall_ms=0,
        completed_normally=True,
    )
    return run


def _map_with_abstract(store: LiteratureMapStore, owner_id: str = "owner-a"):
    item = store.create_map(owner_id, topic="fuzzing")
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-lifecycle",
        title="Lifecycle paper",
        abstract="A frozen abstract for lifecycle verification.",
    )
    store.add_nodes(item.map_id, owner_id, [node])
    return item, node


def test_stopped_analysis_rejects_late_chat_run_completion(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node = _map_with_abstract(store)
    entered_model = Event()
    release_model = Event()

    def runner(**_kwargs):
        entered_model.set()
        assert release_model.wait(timeout=5)
        return _chat_run("迟到的模型结果")

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    analysis, job, _created = service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="late-callback",
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.run_analysis_job, job.job_id, "owner-a")
        assert entered_model.wait(timeout=5)
        stopped = store.stop_job(job.job_id, item.map_id, "owner-a")
        assert stopped is not None
        assert stopped.status == "stopped"
        release_model.set()
        completed = future.result(timeout=5)

    assert completed is not None
    assert completed.status == "failed"
    assert completed.result is None
    assert completed.error["code"] == "MAP_ANALYSIS_STOPPED"
    assert store.get_analysis_job(analysis.analysis_id, item.map_id, "owner-a").status == "stopped"


def test_analysis_retry_reuses_version_and_idempotency_after_failure(tmp_path):
    store = LiteratureMapStore(tmp_path / "maps.sqlite3")
    item, node = _map_with_abstract(store)
    calls = {"count": 0}

    def runner(**_kwargs):
        calls["count"] += 1
        return _chat_run("") if calls["count"] == 1 else _chat_run("重试后的分析")

    service = MapAnalysisService(store=store, executor=None, model_runner=runner)
    first, job, created = service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="retryable-analysis",
    )
    assert created is True
    failed = service.run_analysis_job(job.job_id, "owner-a")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error["code"] == "MAP_MODEL_EMPTY"

    queued = store.retry_job(job.job_id, item.map_id, "owner-a")
    assert queued is not None
    assert queued.status == "queued"

    replay, replay_job, replay_created = service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="retryable-analysis",
    )
    assert replay_created is False
    assert replay.analysis_id == first.analysis_id
    assert replay.version == first.version == 1
    assert replay_job.job_id == job.job_id
    assert replay_job.status == "queued"

    recovered = service.run_analysis_job(job.job_id, "owner-a")
    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.result["summary"] == "重试后的分析"
    assert calls["count"] == 2

    second, second_job, second_created = service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="new-analysis-version",
    )
    assert second_created is True
    assert second.version == 2
    assert second.analysis_id != first.analysis_id
    assert second_job.job_id != job.job_id


def test_concurrent_conversation_reservation_across_sqlite_connections_uses_one_id(tmp_path):
    map_path = tmp_path / "maps.sqlite3"
    memory_path = tmp_path / "memory.sqlite3"
    first_store = LiteratureMapStore(map_path)
    first_memory = MemoryRepository(memory_path)
    project = first_memory.create_project("owner-a", "Fuzzing")
    item = first_store.create_map("owner-a", topic="fuzzing", project_id=project.project_id)
    node = MapPaper.new(
        item.map_id,
        semantic_scholar_id="s2-concurrent",
        title="Concurrent paper",
        abstract="A shared abstract.",
    )
    first_store.add_nodes(item.map_id, "owner-a", [node])

    second_store = LiteratureMapStore(map_path)
    second_memory = MemoryRepository(memory_path)
    services = (
        MapAnalysisService(store=first_store, executor=None, memory_repository=first_memory),
        MapAnalysisService(store=second_store, executor=None, memory_repository=second_memory),
    )
    start = Barrier(2)

    def create(service):
        start.wait(timeout=5)
        return service.create_conversation(
            item.map_id,
            node.node_id,
            "owner-a",
            evidence_level="abstract",
            idempotency_key="same-conversation",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, services))

    conversation_ids = {result["conversation_id"] for result in results}
    assert len(conversation_ids) == 1
    assert sorted(result["created"] for result in results) == [False, True]

    with first_store.connection() as db:
        binding_count = db.execute(
            "SELECT COUNT(*) FROM literature_map_conversation_bindings WHERE map_id=? AND idempotency_key=?",
            (item.map_id, "same-conversation"),
        ).fetchone()[0]
    with first_memory.connection() as db:
        conversation_count = db.execute(
            "SELECT COUNT(*) FROM conversations WHERE conversation_id=? AND owner_id=?",
            (next(iter(conversation_ids)), "owner-a"),
        ).fetchone()[0]
    assert binding_count == 1
    assert conversation_count == 1


def test_map_deletion_keeps_confirmed_binding_snapshot_and_cleans_analysis_rows(tmp_path):
    map_path = tmp_path / "maps.sqlite3"
    memory_path = tmp_path / "memory.sqlite3"
    store = LiteratureMapStore(map_path)
    memory = MemoryRepository(memory_path)
    item, node = _map_with_abstract(store)
    service = MapAnalysisService(store=store, executor=None, memory_repository=memory)

    analysis, _job, _created = service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="deleted-map-analysis",
    )
    conversation = service.create_conversation(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="deleted-map-conversation",
    )
    binding = store.get_conversation_binding(conversation["conversation_id"], "owner-a")
    assert binding is not None
    assert store.delete_map(item.map_id, "owner-a") is True

    with store.connection() as db:
        analysis_count = db.execute(
            "SELECT COUNT(*) FROM literature_map_analyses WHERE analysis_id=?",
            (analysis.analysis_id,),
        ).fetchone()[0]
        binding_count = db.execute(
            "SELECT COUNT(*) FROM literature_map_conversation_bindings WHERE binding_id=?",
            (binding.binding_id,),
        ).fetchone()[0]
    assert analysis_count == 0
    assert binding_count == 1

    preserved = store.get_conversation_binding(conversation["conversation_id"], "owner-a")
    assert preserved is not None
    context = service.conversation_context(preserved, "owner-a", None)
    assert context["visible_document_ids"] == []
    assert context["context"]["title"] == "Lifecycle paper"
    assert context["context"]["abstract"] == "A frozen abstract for lifecycle verification."


def test_analysis_recovery_after_service_rebuild_runs_once_without_graph_mutation(tmp_path):
    database_path = tmp_path / "maps.sqlite3"
    first_store = LiteratureMapStore(database_path)
    item, node = _map_with_abstract(first_store)
    first_service = MapAnalysisService(store=first_store, executor=None)
    analysis, job, _created = first_service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="recover-once",
    )
    claimed = first_store.claim_analysis_job(job.job_id, item.map_id, "owner-a")
    assert claimed is not None
    assert first_store.get_analysis(analysis.analysis_id, item.map_id, "owner-a").status == "running"

    rebuilt_store = LiteratureMapStore(database_path)
    map_before = rebuilt_store.get_map(item.map_id, "owner-a").to_dict()
    nodes_before = [value.to_dict() for value in rebuilt_store.list_nodes(item.map_id, "owner-a")]
    edges_before = [value.to_dict() for value in rebuilt_store.list_edges(item.map_id, "owner-a")]

    graph_executor = _InlineRecordingExecutor()
    graph_service = LiteratureMapService(store=rebuilt_store, client=object(), executor=graph_executor)
    graph_service.recover("owner-a")
    assert graph_executor.submissions == []

    model_calls = []

    def runner(**_kwargs):
        model_calls.append(True)
        return _chat_run("重建后的分析")

    analysis_executor = _InlineRecordingExecutor()
    rebuilt_service = MapAnalysisService(
        store=rebuilt_store,
        executor=analysis_executor,
        model_runner=runner,
    )
    assert rebuilt_service.recover("owner-a") == 1
    assert len(analysis_executor.submissions) == 1
    assert len(model_calls) == 1

    # A second recovery pass sees the completed durable job and cannot replay it.
    assert rebuilt_service.recover("owner-a") == 0
    assert len(analysis_executor.submissions) == 1
    assert len(model_calls) == 1

    recovered = rebuilt_store.get_analysis(analysis.analysis_id, item.map_id, "owner-a")
    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.analysis_id == analysis.analysis_id
    assert recovered.version == analysis.version == 1
    assert recovered.result["summary"] == "重建后的分析"

    replay, replay_job, replay_created = rebuilt_service.request_analysis(
        item.map_id,
        node.node_id,
        "owner-a",
        evidence_level="abstract",
        idempotency_key="recover-once",
    )
    assert replay_created is False
    assert replay.analysis_id == analysis.analysis_id
    assert replay.version == analysis.version
    assert replay_job.job_id == job.job_id

    assert rebuilt_store.get_map(item.map_id, "owner-a").to_dict() == map_before
    assert [value.to_dict() for value in rebuilt_store.list_nodes(item.map_id, "owner-a")] == nodes_before
    assert [value.to_dict() for value in rebuilt_store.list_edges(item.map_id, "owner-a")] == edges_before
