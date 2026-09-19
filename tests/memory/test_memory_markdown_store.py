"""spec-038 P1：L1 文件记忆层（MarkdownMemoryStore）契约测试。

覆盖：
- 快照预算截断（保留较新条目）
- 缺失文件容错（绝不抛异常、返回空串/仅有的内容）
- 并发追加不丢条目（多线程）
- project_id 路径遍历被拒
- 原子写（写入过程中不产生半截文件）
- pending 待确认流程
- USER.md 全量优先

全部离线可跑：不依赖 Ollama / reranker / 网络。
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from backend.app.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MarkdownMemoryStore:
    """每个用例独立的记忆目录，避免污染 data/memory。"""
    return MarkdownMemoryStore(tmp_path / "memory")


# --------------------------------------------------------------- 快照与预算


def test_snapshot_empty_when_no_files(store: MarkdownMemoryStore):
    """文件全缺失：返回空串，绝不抛异常。"""
    assert store.load_snapshot(project_id=None, max_chars=1000) == ""
    assert store.load_snapshot(project_id="proj-a", max_chars=1000) == ""


def test_snapshot_includes_user_memory_and_project(store: MarkdownMemoryStore):
    store.write_user("用户偏好：先给结论")
    store.append_memory(scope="global", project_id=None, content="全局事实 A")
    store.append_memory(scope="project", project_id="proj-a", content="项目事实 B")

    snapshot = store.load_snapshot(project_id="proj-a", max_chars=10_000)
    assert "用户偏好：先给结论" in snapshot
    assert "全局事实 A" in snapshot
    assert "项目事实 B" in snapshot


def test_snapshot_project_scoped_only_for_matching_project(store: MarkdownMemoryStore):
    store.append_memory(scope="project", project_id="proj-a", content="只属于 A")
    store.append_memory(scope="project", project_id="proj-b", content="只属于 B")

    snapshot = store.load_snapshot(project_id="proj-a", max_chars=10_000)
    assert "只属于 A" in snapshot
    assert "只属于 B" not in snapshot


def test_snapshot_keeps_user_in_full_over_budget(store: MarkdownMemoryStore):
    """USER.md 画像优先全量注入，即使据此已超预算。"""
    long_user = "U" * 500
    store.write_user(long_user)
    store.append_memory(scope="global", project_id=None, content="G" * 5000)

    snapshot = store.load_snapshot(project_id=None, max_chars=100)
    assert long_user in snapshot


def test_snapshot_truncates_keeping_newer_entries(store: MarkdownMemoryStore):
    """超预算时保留较新条目（条目按 `- ` 列表项切分，文件末尾为最新）。"""
    for index in range(60):
        store.append_memory(scope="global", project_id=None, content=f"条目{index:03d}-{'x' * 40}")

    snapshot = store.load_snapshot(project_id=None, max_chars=400)
    assert len(snapshot) <= 400
    # 最新的条目在，最旧的被丢弃
    assert "条目059" in snapshot
    assert "条目000" not in snapshot


def test_snapshot_never_raises_on_unreadable_file(store: MarkdownMemoryStore, monkeypatch):
    """底层读取抛异常时静默降级为空串，绝不向上传播。"""
    store.write_user("画像")

    def boom(*args, **kwargs):
        raise OSError("disk exploded")

    monkeypatch.setattr(Path, "read_text", boom)
    assert store.load_snapshot(project_id=None, max_chars=1000) == ""


# --------------------------------------------------------------- 追加与 scope


def test_append_global_and_project_land_in_different_files(store: MarkdownMemoryStore):
    store.append_memory(scope="global", project_id=None, content="G1")
    store.append_memory(scope="project", project_id="proj-a", content="P1")

    assert "G1" in (store.memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "P1" in (store.memory_dir / "projects" / "proj-a.md").read_text(encoding="utf-8")


def test_append_project_requires_project_id(store: MarkdownMemoryStore):
    with pytest.raises(ValueError):
        store.append_memory(scope="project", project_id=None, content="没有项目")


def test_append_rejects_unknown_scope(store: MarkdownMemoryStore):
    with pytest.raises(ValueError):
        store.append_memory(scope="whatever", project_id=None, content="x")


def test_append_creates_missing_directories(store: MarkdownMemoryStore):
    assert not store.memory_dir.exists()
    store.append_memory(scope="project", project_id="proj-new", content="C")
    assert (store.memory_dir / "projects" / "proj-new.md").is_file()


# --------------------------------------------------------------- 路径安全


@pytest.mark.parametrize(
    "bad_project_id",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "..",
        "a/../b",
        "a/b",
        "proj a",
        "proj.a",
        "..%2fetc",
        "proj-a\x00",
    ],
)
def test_project_id_path_traversal_is_rejected(store: MarkdownMemoryStore, bad_project_id: str):
    with pytest.raises(ValueError):
        store.append_memory(scope="project", project_id=bad_project_id, content="evil")
    with pytest.raises(ValueError):
        store.load_snapshot(project_id=bad_project_id, max_chars=100)


def test_empty_project_id_means_no_project_context(store: MarkdownMemoryStore):
    """空 project_id 等同「无项目上下文」，不算非法（不抛异常）。"""
    assert store.load_snapshot(project_id="", max_chars=100) == ""
    with pytest.raises(ValueError):
        # 但显式以 project scope 追加时必须给出有效 project_id
        store.append_memory(scope="project", project_id="", content="evil")


def test_project_id_write_stays_inside_projects_dir(store: MarkdownMemoryStore):
    store.append_memory(scope="project", project_id="ok_id-123", content="safe")
    target = (store.memory_dir / "projects" / "ok_id-123.md").resolve()
    assert target.parent == (store.memory_dir / "projects").resolve()
    assert target.is_file()


# --------------------------------------------------------------- 并发安全


def test_concurrent_appends_do_not_lose_entries(store: MarkdownMemoryStore):
    """多写者并发追加：条目数与写入次数一致（无交叉覆盖丢笔记）。"""
    writers, per_writer = 8, 25
    barrier = threading.Barrier(writers)
    errors: list[BaseException] = []

    def worker(writer_id: int) -> None:
        try:
            barrier.wait(timeout=10)
            for index in range(per_writer):
                store.append_memory(
                    scope="global", project_id=None, content=f"W{writer_id:02d}-{index:03d}"
                )
        except BaseException as error:  # pragma: no cover - 仅在并发缺陷时触发
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    text = (store.memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    entries = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(entries) == writers * per_writer
    for writer_id in range(writers):
        for index in range(per_writer):
            assert f"W{writer_id:02d}-{index:03d}" in text


# --------------------------------------------------------------- 原子写


def test_atomic_write_never_exposes_partial_file(store: MarkdownMemoryStore):
    """写入过程中，目标文件始终可完整解析（无半截文件）。"""
    store.append_memory(scope="global", project_id=None, content="初始条目")
    target = store.memory_dir / "MEMORY.md"

    stop = threading.Event()
    observed: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                observed.append(target.read_text(encoding="utf-8"))
            except FileNotFoundError:  # pragma: no cover - 原子替换不留空档
                observed.append("")

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for index in range(200):
            store.append_memory(scope="global", project_id=None, content=f"原子条目{index:03d}")
    finally:
        stop.set()
        thread.join(timeout=10)

    # 每次读到的快照都必须是「若干完整条目」，即每个非空行都形如 `- xxx`
    for snapshot in observed:
        for line in snapshot.splitlines():
            if line.strip():
                assert line.startswith("- "), repr(line)
    assert "原子条目199" in target.read_text(encoding="utf-8")


def test_temp_files_are_cleaned_up(store: MarkdownMemoryStore):
    for index in range(20):
        store.append_memory(scope="global", project_id=None, content=f"条目{index}")
    leftovers = [p for p in store.memory_dir.iterdir() if p.name.startswith(".tmp")]
    assert leftovers == []


# --------------------------------------------------------------- pending 待确认


def test_pending_roundtrip_and_resolution(store: MarkdownMemoryStore):
    assert store.list_pending() == []

    item_id = store.add_pending(content="可能是用户偏好", project_id=None)
    pending = store.list_pending()
    assert [item.item_id for item in pending] == [item_id]
    assert pending[0].content == "可能是用户偏好"
    assert pending[0].project_id is None

    store.resolve_pending(item_id, scope="project", project_id="proj-a")
    assert store.list_pending() == []
    assert "可能是用户偏好" in (
        store.memory_dir / "projects" / "proj-a.md"
    ).read_text(encoding="utf-8")


def test_resolve_pending_unknown_id_raises(store: MarkdownMemoryStore):
    with pytest.raises(KeyError):
        store.resolve_pending("nope", scope="global", project_id=None)


def test_pending_is_persisted_across_instances(tmp_path: Path):
    first = MarkdownMemoryStore(tmp_path / "memory")
    item_id = first.add_pending(content="跨实例可见", project_id="proj-a")
    second = MarkdownMemoryStore(tmp_path / "memory")
    assert [item.item_id for item in second.list_pending()] == [item_id]


def test_pending_rejects_path_traversal_project_id(store: MarkdownMemoryStore):
    with pytest.raises(ValueError):
        store.add_pending(content="x", project_id="../evil")


# --------------------------------------------------------------- 模块导出


def test_module_is_exported_from_memory_package():
    from backend.app import memory

    assert memory.MarkdownMemoryStore is MarkdownMemoryStore


def test_owner_id_helper_is_available_for_api_injection(store: MarkdownMemoryStore):
    """routes 层读取 USER.md 用的 fail-open helper：缺失文件返回空串。"""
    from backend.app.memory.markdown_store import read_user_memory_or_empty

    assert read_user_memory_or_empty(store) == ""
    store.write_user("画像内容")
    assert read_user_memory_or_empty(store) == "画像内容"

    def boom(*args, **kwargs):
        raise OSError("boom")

    broken = MarkdownMemoryStore(store.memory_dir)
    broken.write_user("画像内容")
    os_orig = Path.read_text
    try:
        Path.read_text = boom
        assert read_user_memory_or_empty(broken) == ""
    finally:
        Path.read_text = os_orig
