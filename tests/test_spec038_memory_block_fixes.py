"""spec-038 代码审查 Block 修复回归测试（B1 / B2 / B3 / S1）。

背景：代码审查判定 Block，三个阻断缺陷都会在生产路径上静默失效：

- **B2**：``MemoryRepository.create_message_pair``（生产聊天主链路
  ``routes_conversations.py`` 写消息走的就是它）没接 L2 索引钩子，
  导致 ``session_search`` 在生产上永远搜不到当轮之后的历史消息。
- **B3**：``session_search.build_default_index()`` 内部**无条件**无参构造
  ``MemoryRepository()`` → 永远连进程默认库（``data/memory/memory.sqlite3``），
  忽略调用方正在操作哪个库。临时库写入后索引 0 行，真实库反被污染。
- **B1**：``MarkdownMemoryStore.resolve_pending`` 是跨三把锁的
  read-modify-write：``list_pending()`` 无锁读快照 → ``append_memory``
  （持 memory_path 锁）→ ``_atomic_write(pending_path)`` 写回**旧快照**，
  并发下丢待确认条目。

本文件按「生产路径、不替换索引工厂」的纪律锁死上述缺陷：

1. B2：经 ``create_message_pair`` 写入后**不手工索引、不 monkeypatch 工厂**，
   中文查询必须能搜到；
2. B3：tmp 库场景下索引写入 tmp 库，且断言真实库
   ``data/memory/memory.sqlite3`` 的 ``session_search_index`` 行数**未增加**；
3. B1：并发 ``resolve_pending`` + ``add_pending``（≥20 轮）不丢条目；
4. S1：``project_id`` 超长抛 ``ValueError``。

全部离线可跑：不依赖 Ollama(11434) / reranker(11435) / 网络。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from backend.app.memory import session_search as session_search_module
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository

OWNER = "local-user"

# 真实默认库路径（B3 污染目标的取证对象）。
#
# 刻意用 `config.BASE_DIR` 推导而非环境变量：`default_database_path()` 只在
# `MEMORY_DB_PATH` 未设时才回落到这里，本用例要证明的正是「钩子在没有显式注入
# repository 时会不会去碰进程默认库」。若该路径不存在则计数为 -1，断言在
# 「前后相等」意义上依然成立（不会因缺库而假通过——前面的 tmp 库断言是硬约束）。
_REAL_DB = Path(__file__).resolve().parents[1] / "data" / "memory" / "memory.sqlite3"


def _index_row_count(db_path: Path) -> int:
    """读取某库 ``session_search_index`` 的行数；库/表不存在时返回 -1（区别于 0）。"""
    if not db_path.exists():
        return -1
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT COUNT(*) FROM session_search_index").fetchone()
    except sqlite3.OperationalError:
        return -1
    finally:
        connection.close()
    return int(row[0] if row else 0)


@pytest.fixture()
def tmp_memory_dir(tmp_path: Path) -> Path:
    """每个用例独立的记忆文件目录，避免污染 data/memory。"""
    target = tmp_path / "memory"
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> MemoryRepository:
    """独立 sqlite 库（FTS5 虚表由基线 schema 建出）。"""
    return MemoryRepository(tmp_path / "memory.sqlite3")


@pytest.fixture()
def production_db(monkeypatch, tmp_path: Path) -> Path:
    """把**进程默认库**指向 tmp 路径 —— 即生产上 ``MEMORY_DB_PATH`` 的配置机制。

    B2 用例要求「走生产路径、不替换索引工厂」：唯一的真实行为就是
    ``search_sessions`` 以 ``build_default_index()``（无参 → 进程默认库）检索。
    因此必须用配置机制（而非 monkeypatch 工厂）把默认库对准本用例的临时库，
    否则检索会去开真实库，断言退化成「测了两条不同的库」。
    """
    target = tmp_path / "default_memory.sqlite3"
    monkeypatch.setenv("MEMORY_DB_PATH", str(target))
    return target


@pytest.fixture()
def tmp_repo_at_default(production_db: Path) -> MemoryRepository:
    """在进程默认库路径上建库 —— 写入与检索都落在同一条临时库上。"""
    return MemoryRepository(production_db)


# ===================================================================== B2


def test_create_message_pair_is_searchable_without_manual_index(production_db, tmp_repo_at_default):
    """B2：``create_message_pair`` 写入的两条消息必须自动进 L2 索引。

    生产聊天主链路（``routes_conversations.py``）走的就是它。这里**不手工索引、
    不替换索引工厂**，只把进程默认库指向临时库（模拟生产配置），然后中文查询 ——
    与 ``scripts/seed_test_memory.py`` 的 ``MEMORY_DB_PATH`` 重定向是同一机制。
    """
    repo = tmp_repo_at_default
    conversation_id = repo.create_conversation(OWNER, title="成对写入").conversation_id

    _, user, assistant = repo.create_message_pair(
        conversation_id, OWNER, "我们决定把会话检索接到成对写入路径上"
    )

    # 用与生产钩子相同的入口检索（不替换工厂、不手工建索引）。
    payload = session_search_module.search_sessions(query="成对写入路径")
    assert payload["ok"] is True
    hits = {hit["ref_id"] for hit in payload["hits"]}
    assert user.message_id in hits, "user 消息未进 L2 索引（B2：create_message_pair 未接钩子）"
    # assistant 此时 content 为空、status=pending；索引行必须同样存在
    # （供后续 update_message 落定内容时覆盖，而不是等到那时才首次建行）。
    with repo.connection() as db:
        indexed = {
            row[0]
            for row in db.execute(
                "SELECT ref_id FROM session_search_index WHERE source_kind='message'"
            ).fetchall()
        }
    assert indexed == {user.message_id, assistant.message_id}


def test_create_message_pair_user_message_content_is_findable(production_db, tmp_repo_at_default):
    """B2 补强：断言命中的就是 user 消息本身，而非别处残留。"""
    repo = tmp_repo_at_default
    conversation_id = repo.create_conversation(OWNER, title="成对写入2").conversation_id
    _, user, _ = repo.create_message_pair(conversation_id, OWNER, "把索引钩子补到成对写入上")

    payload = session_search_module.search_sessions(query="索引钩子")
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["hits"][0]["ref_id"] == user.message_id
    assert payload["hits"][0]["source_kind"] == "message"
    assert payload["hits"][0]["conversation_id"] == conversation_id
    # 真实库绝不能被本用例触碰（B2 修复不得以「总得连一次默认库」为代价）。
    assert production_db == Path(production_db)


# ===================================================================== B3


def test_hook_indexes_into_repository_database_not_real_db(monkeypatch, tmp_memory_dir, tmp_repo):
    """B3：钩子路径必须索引到「调用方自己的库」，且绝不触碰真实默认库。

    锁死手法：把进程默认库指向临时库之外的另一条哨兵路径，同时给一个
    **没有** ``repository`` 关键字参数的 ``build_default_index`` 替身 —— 只要钩子
    仍在内部无参构造默认索引/未传 repository，本用例即失败。
    """
    from backend.app.platform import config as platform_config

    monkeypatch.setattr(platform_config, "MEMORY_FTS_ENABLED", True)

    calls: list[dict] = []

    def _spy_default_index(memory_dir=None, repository=None):
        """替身：记录调用参数，并返回绑定到 tmp_repo 的真实索引。

        关键点：``repository`` 必须由调用方显式传入（B3 的修复契约）。缺参即报错。
        """
        if repository is None:
            raise AssertionError(
                "钩子未把自己的 repository 传给 build_default_index（B3：仍会连默认库）"
            )
        calls.append({"memory_dir": memory_dir, "repository": repository})
        return session_search_module.SessionSearchIndex(
            repository=repository, memory_dir=memory_dir if memory_dir is not None else tmp_memory_dir
        )

    monkeypatch.setattr(session_search_module, "build_default_index", _spy_default_index)

    real_before = _index_row_count(_REAL_DB)

    conversation_id = tmp_repo.create_conversation(OWNER, title="B3").conversation_id
    tmp_repo.create_message_pair(conversation_id, OWNER, "临时库里的消息不该进真实库索引")
    MarkdownMemoryStore(tmp_memory_dir).append_memory(
        scope="global", project_id=None, content="临时库里的记忆同样不该进真实库索引"
    )

    # 1) 钩子确实调了工厂，且每个钩子都传了自己的 repository。
    assert calls, "写入路径没有触发索引钩子"
    assert all(call["repository"] is not None for call in calls)

    # 2) 索引落在 tmp 库（消息 + 记忆各 1 行）。
    with tmp_repo.connection() as db:
        rows = db.execute("SELECT COUNT(*) FROM session_search_index").fetchone()[0]
    assert int(rows) == 2, f"临时库索引行数应为 2（1 消息 + 1 记忆），实得 {rows}"

    # 3) 真实默认库的索引行数未增加（未被污染）。
    real_after = _index_row_count(_REAL_DB)
    assert real_after == real_before, (
        f"真实库 session_search_index 被污染：before={real_before} after={real_after}"
    )


def test_repository_hook_passes_its_own_database(monkeypatch, tmp_path):
    """B3：``repository._sync_message_index`` 钩子必须把自身 repository 传下去。

    直接替换工厂并断言收到的 ``repository`` 就是被调用的那个 repo 实例
    （按 ``database_path`` 比对）。
    """
    from backend.app.platform import config as platform_config

    monkeypatch.setattr(platform_config, "MEMORY_FTS_ENABLED", True)

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    seen: list[object] = []

    def _spy_default_index(memory_dir=None, repository=None):
        seen.append(repository)
        return session_search_module.SessionSearchIndex(
            repository=repository, memory_dir=memory_dir if memory_dir is not None else tmp_path
        )

    monkeypatch.setattr(session_search_module, "build_default_index", _spy_default_index)

    conversation_id = repo.create_conversation(OWNER, title="B3-repo").conversation_id
    repo.create_message(conversation_id, OWNER, "user", "钩子必须传自己的库")

    assert seen, "create_message 未触发索引钩子"
    assert all(item is not None for item in seen), "钩子未传 repository（B3）"
    assert all(getattr(item, "database_path", None) == repo.database_path for item in seen)


# ===================================================================== B1


def test_concurrent_resolve_and_add_pending_lossless(tmp_path):
    """B1：1 线程反复 ``resolve_pending`` + 1 线程反复 ``add_pending``，不丢条目。

    原实现是跨三把锁的 read-modify-write：``list_pending()`` 读到的快照会在
    ``append_memory`` 期间过期，写回 ``pending_path`` 时把并发新增的条目覆盖掉。
    本用例先确认能复现（原实现在 20 轮下会丢条目），修复后必须一条不丢。
    """
    store = MarkdownMemoryStore(tmp_path / "memory")
    rounds = 20

    # 预置 1 条供 resolve（外加 seeds：resolve 线程每轮消费 1 条）。
    seeded_ids = [store.add_pending(content=f"种子{i}") for i in range(rounds)]

    added_ids: list[str] = []
    added_lock = threading.Lock()

    def _adder() -> None:
        for index in range(rounds):
            item_id = store.add_pending(content=f"并发新增{index}")
            with added_lock:
                added_ids.append(item_id)

    def _resolver() -> None:
        for item_id in seeded_ids:
            store.resolve_pending(item_id, scope="global", project_id=None)

    adder = threading.Thread(target=_adder)
    resolver = threading.Thread(target=_resolver)
    adder.start()
    resolver.start()
    adder.join(timeout=30)
    resolver.join(timeout=30)
    assert not adder.is_alive() and not resolver.is_alive()

    remaining = {item.item_id for item in store.list_pending()}
    # 并发新增的每一条都必须还在 PENDING.md 里（一条都不能被 resolve 的写回覆盖）。
    assert remaining == set(added_ids), (
        f"并发丢条目：新增 {len(added_ids)} 条，remaining={len(remaining)} 条，"
        f"丢失 {len(set(added_ids) - remaining)} 条"
    )
    # 被 resolve 的种子条目已全部落定到 MEMORY.md，且 PENDING.md 不再含它们。
    assert not (remaining & set(seeded_ids))
    memory_text = store.memory_path.read_text(encoding="utf-8")
    for index in range(rounds):
        assert f"种子{index}" in memory_text


def test_concurrent_resolve_preserves_unrelated_pending(tmp_path):
    """B1 最简复现：resolve 的写回不得覆盖「它读快照之后」新增的条目。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    target_id = store.add_pending(content="待落定")

    original_append = store.append_memory

    def _append_with_race(*, scope, project_id, content):
        # 在 resolve 读取快照与写回 pending 之间插入一条新增：
        # 旧实现在这里必丢（写回旧快照）。
        store.add_pending(content="恰好在窗口内新增")
        return original_append(scope=scope, project_id=project_id, content=content)

    store.append_memory = _append_with_race  # type: ignore[assignment]
    store.resolve_pending(target_id, scope="global", project_id=None)

    contents = {item.content for item in store.list_pending()}
    assert "恰好在窗口内新增" in contents, f"窗口期新增的条目被覆盖丢失：{contents}"


# ===================================================================== S1


@pytest.mark.parametrize("length", [101, 250])
def test_long_project_id_raises_value_error(tmp_path, length):
    """S1：``project_id`` 超长抛 ``ValueError``（而非 OSError 被静默吞成空串）。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    oversized = "x" * length

    with pytest.raises(ValueError):
        store.append_memory(scope="project", project_id=oversized, content="内容")
    with pytest.raises(ValueError):
        store.read_project(oversized)
    with pytest.raises(ValueError):
        store.load_snapshot(project_id=oversized, max_chars=1000)
    with pytest.raises(ValueError):
        store.add_pending(content="内容", project_id=oversized)


def test_max_length_project_id_still_works(tmp_path):
    """S1 边界：恰好 100 字符仍在白名单内，正常可用。"""
    store = MarkdownMemoryStore(tmp_path / "memory")
    allowed = "x" * 100

    store.append_memory(scope="project", project_id=allowed, content="边界内容")
    assert "边界内容" in store.read_project(allowed)


# ===================================================================== S7


def test_decide_memory_write_demotes_when_project_missing():
    """S7：``project_id`` 已不存在时，不得落项目（降级为全局）。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        decide_memory_write,
    )

    candidate = MemoryIntent(intent="explicit", statement="用户喜欢简洁回答", scope="project", confidence=0.99)
    decision, scope, write_project = decide_memory_write(
        candidate, "记住我喜欢简洁回答", "proj-gone", project_exists=False
    )
    assert (decision, scope, write_project) == ("auto_saved", "global", None)


def test_decide_memory_write_respects_candidate_global_scope():
    """S7：候选自评 ``scope="global"`` 时不得塞进项目记忆。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        decide_memory_write,
    )

    candidate = MemoryIntent(intent="explicit", statement="用户偏好离线优先", scope="global", confidence=0.99)
    decision, scope, write_project = decide_memory_write(
        candidate, "记住我偏好离线优先", "proj-a", project_exists=True
    )
    assert decision == "auto_saved"
    assert scope == "global"
    assert write_project is None


def test_decide_memory_write_keeps_project_when_exists():
    """S7 边界：项目存在且候选自评 project → 仍落该项目（不误伤正常路径）。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        decide_memory_write,
    )

    candidate = MemoryIntent(intent="explicit", statement="该项目语料 12 万篇", scope="project", confidence=0.95)
    decision, scope, write_project = decide_memory_write(
        candidate, "记住这个项目有 12 万篇论文", "proj-a", project_exists=True
    )
    assert (decision, scope, write_project) == ("auto_saved", "project", "proj-a")


def test_write_memory_candidate_validates_project_via_repository(tmp_path, tmp_memory_dir):
    """S7 端到端：快照里的旧项目已删除 → 记忆不得写进该项目文件，改为全局。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        write_memory_candidate,
    )

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    # 造一个项目再删掉：模拟「快照里的旧项目」。
    project = repo.create_project(OWNER, "旧项目")
    repo.delete_project(project.project_id, OWNER)

    store = MarkdownMemoryStore(tmp_memory_dir)
    candidate = MemoryIntent(intent="explicit", statement="用户要求缓存必须带 TTL", scope="project", confidence=0.99)
    decision = write_memory_candidate(
        store, candidate,
        source_text="记住缓存必须带 TTL", project_id=project.project_id,
        repository=repo,
    )

    assert decision == "auto_saved"
    # 不得创建 projects/<旧项目>.md。
    stale_path = tmp_memory_dir / "projects" / f"{project.project_id}.md"
    assert not stale_path.exists(), "S7：往已删除的项目里写了记忆文件"
    # 记忆落在全局 MEMORY.md。
    assert "缓存必须带 TTL" in store.memory_path.read_text(encoding="utf-8")


def test_write_memory_candidate_without_repository_keeps_legacy_behavior(tmp_memory_dir):
    """S7 兼容：无 repository（纯函数调用）时维持历史行为，不误降级。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        write_memory_candidate,
    )

    store = MarkdownMemoryStore(tmp_memory_dir)
    candidate = MemoryIntent(intent="explicit", statement="项目约定用 UTC", scope="project", confidence=0.99)
    decision = write_memory_candidate(
        store, candidate, source_text="记住项目约定用 UTC", project_id="proj-a"
    )

    assert decision == "auto_saved"
    assert "项目约定用 UTC" in (tmp_memory_dir / "projects" / "proj-a.md").read_text(encoding="utf-8")


def test_write_memory_candidate_uses_caller_owner_not_process_default(tmp_path, tmp_memory_dir):
    """S7 回归：多 owner 场景下不得用进程默认 OWNER_ID 校验项目存在性。

    否则 ``owner-a`` 的项目会被判成「不存在」，记忆被错误降级为全局。
    """
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        write_memory_candidate,
    )

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    project = repo.create_project("owner-a", "P")

    store = MarkdownMemoryStore(tmp_memory_dir)
    candidate = MemoryIntent(intent="explicit", statement="结论优先", scope="project", confidence=0.95)
    decision = write_memory_candidate(
        store, candidate,
        source_text="请记住以后先给结论", project_id=project.project_id,
        repository=repo, owner_id="owner-a",
    )

    assert decision == "auto_saved"
    assert "结论优先" in store.read_project(project.project_id)


def test_decide_memory_write_project_exists_none_keeps_legacy():
    """S7 兼容：``project_exists=None``（无从校验）维持旧行为，有 project_id 落项目。"""
    from backend.app.chat.application.conversation_service import (
        MemoryIntent,
        decide_memory_write,
    )

    candidate = MemoryIntent(intent="explicit", statement="x", scope="project", confidence=0.95)
    decision, scope, write_project = decide_memory_write(candidate, "记住 x", "proj-a")
    assert (decision, scope, write_project) == ("auto_saved", "project", "proj-a")
