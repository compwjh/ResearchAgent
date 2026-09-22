"""spec-038 P2 收尾接线 · 写入路径自动索引（end-to-end）契约测试。

P2 主体已提供 ``session_search`` 检索与索引能力，但索引只在显式调用
``index_message`` / ``reindex_memories`` 时更新，生产写入链路无人调用 → 新消息、
新记忆写进去后搜不到。本文件锁定「把索引挂到实际写入路径上」的端到端契约：

1. ``repository.create_message`` 写完消息**不手工索引**即可被 ``search_sessions`` 搜到；
2. ``repository.update_message`` 内容落定后同样自动更新索引；
3. ``MarkdownMemoryStore.append_memory`` / ``write_user`` 写完**不手工 reindex** 即可搜到；
4. ``MEMORY_FTS_ENABLED=false``：写入正常、索引不更新、检索不报错；
5. 索引模块内部抛异常时，消息/记忆**写入仍成功**（fail-open）；
6. ``search_sessions`` 检索消息时按 owner 过滤，MD 笔记无 owner 不受其约束。

全部离线可跑：不依赖 Ollama(11434) / reranker(11435) / 网络。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.memory import session_search as session_search_module
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository
from backend.app.memory.session_search import SessionSearchIndex
from backend.app.platform import config as platform_config

OWNER = "local-user"


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    """每个用例独立的记忆文件目录，避免污染 data/memory。"""
    target = tmp_path / "memory"
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture()
def repo(tmp_path: Path) -> MemoryRepository:
    """独立 sqlite 库；FTS5 虚表由基线 schema 建出。"""
    return MemoryRepository(tmp_path / "memory.sqlite3")


@pytest.fixture()
def wired(monkeypatch, repo: MemoryRepository, memory_dir: Path) -> SessionSearchIndex:
    """把写入钩子内部的索引工厂指向本用例的临时 index。

    生产侧钩子经 ``session_search.build_default_index`` 惰性构造索引；测试里统一
    替换该工厂，使钩子写入的虚表与测试断言读的是同一个 sqlite 库/记忆目录。
    """
    index = SessionSearchIndex(repository=repo, memory_dir=memory_dir)
    monkeypatch.setattr(
        session_search_module, "build_default_index", lambda *_a, **_k: index
    )
    return index


# ------------------------------------------------------------------ 1. 消息自动索引


def test_create_message_is_searchable_without_manual_index(wired, repo, memory_dir):
    """写入消息后不手工调 index，直接 search_sessions 能搜到（中文查询）。"""
    conversation_id = repo.create_conversation(OWNER, title="接线").conversation_id
    message = repo.create_message(
        conversation_id, OWNER, "user", "我们决定把搜索功能接到写入路径上", status="completed"
    )

    payload = session_search_module.search_sessions(query="写入路径")
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["hits"][0]["ref_id"] == message.message_id
    assert payload["hits"][0]["source_kind"] == "message"
    assert payload["hits"][0]["conversation_id"] == conversation_id


def test_update_message_content_reindexes(wired, repo):
    """消息内容落定（update_message）后自动更新索引，旧内容不再命中。"""
    conversation_id = repo.create_conversation(OWNER, title="更新").conversation_id
    placeholder = repo.create_message(conversation_id, OWNER, "assistant", "", status="pending")
    assert session_search_module.search_sessions(query="最终答复")["count"] == 0

    repo.update_message(placeholder.message_id, OWNER, content="最终答复是使用 FTS5", status="completed")

    payload = session_search_module.search_sessions(query="最终答复")
    assert payload["count"] == 1
    assert payload["hits"][0]["ref_id"] == placeholder.message_id


def test_message_status_update_without_content_does_not_break(wired, repo):
    """仅状态落定（无内容变更）也必须正常且可再索引。"""
    conversation_id = repo.create_conversation(OWNER, title="状态").conversation_id
    message = repo.create_message(conversation_id, OWNER, "assistant", "已经写入正文", status="pending")

    repo.update_message(message.message_id, OWNER, status="completed")
    assert session_search_module.search_sessions(query="正文")["count"] == 1


# ------------------------------------------------------------------ 2. MD 记忆自动索引


def test_append_memory_is_searchable_without_reindex(wired, repo, memory_dir):
    """写入记忆后不手工 reindex，直接能搜到（MD 侧同步钩子）。"""
    MarkdownMemoryStore(memory_dir).append_memory(
        scope="global", project_id=None, content="用户要求所有接口必须离线可测"
    )

    payload = session_search_module.search_sessions(query="离线可测")
    assert payload["count"] == 1
    assert payload["hits"][0]["source_kind"] == "memory"
    assert payload["hits"][0]["ref_id"] == "MEMORY.md"


def test_append_project_memory_is_searchable(wired, repo, memory_dir):
    """项目级记忆写入后同步索引到 projects/<id>.md。"""
    MarkdownMemoryStore(memory_dir).append_memory(
        scope="project", project_id="proj-a", content="该项目语料有 12 万篇论文"
    )

    payload = session_search_module.search_sessions(query="语料")
    assert payload["count"] == 1
    assert payload["hits"][0]["ref_id"] == "projects/proj-a.md"


def test_write_user_is_searchable(wired, repo, memory_dir):
    """``write_user``（用户画像整体写入）后同样可搜到。"""
    MarkdownMemoryStore(memory_dir).write_user("- 用户偏好：先给结论再给推导\n")

    payload = session_search_module.search_sessions(query="先给结论")
    assert payload["count"] == 1
    assert payload["hits"][0]["ref_id"] == "USER.md"


def test_resolve_pending_indexes_resolved_memory(wired, repo, memory_dir):
    """``resolve_pending`` 落定待确认项后，正式记忆可搜到。"""
    store = MarkdownMemoryStore(memory_dir)
    item_id = store.add_pending(content="用户希望默认关闭埋点", project_id=None)

    store.resolve_pending(item_id, scope="global", project_id=None)

    payload = session_search_module.search_sessions(query="默认关闭埋点")
    assert payload["count"] == 1
    assert payload["hits"][0]["source_kind"] == "memory"


# ------------------------------------------------------------------ 3. 开关关闭


def test_disabled_flag_keeps_writes_working_but_skips_index(monkeypatch, wired, repo, memory_dir):
    """MEMORY_FTS_ENABLED=false：写入正常、索引不更新、检索不报错。"""
    monkeypatch.setattr(platform_config, "MEMORY_FTS_ENABLED", False)

    conversation_id = repo.create_conversation(OWNER, title="开关").conversation_id
    message = repo.create_message(conversation_id, OWNER, "user", "关闭索引时仍然要能写入")
    assert message.content == "关闭索引时仍然要能写入"

    store = MarkdownMemoryStore(memory_dir)
    store.append_memory(scope="global", project_id=None, content="关闭索引时记忆也要写入")
    assert "关闭索引时记忆也要写入" in store.memory_path.read_text(encoding="utf-8")

    # 索引未更新 → 检索返回空结果，而不是抛异常
    payload = session_search_module.search_sessions(query="关闭索引")
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["hits"] == []


# ------------------------------------------------------------------ 4. fail-open


def test_message_write_survives_index_failure(monkeypatch, repo, memory_dir):
    """索引模块内部抛异常时，消息写入仍成功（fail-open）。"""

    def _boom(*_a, **_k):
        raise RuntimeError("索引爆炸")

    monkeypatch.setattr(session_search_module, "build_default_index", _boom)

    conversation_id = repo.create_conversation(OWNER, title="兜底").conversation_id
    message = repo.create_message(conversation_id, OWNER, "user", "索引失败也要写进去")
    assert message.message_id


def test_memory_write_survives_index_failure(monkeypatch, repo, memory_dir):
    """索引模块内部抛异常时，记忆写入仍成功（记忆是 L1 真相源，优先保写入）。"""

    def _boom(*_a, **_k):
        raise RuntimeError("索引爆炸")

    monkeypatch.setattr(session_search_module, "build_default_index", _boom)

    MarkdownMemoryStore(memory_dir).append_memory(scope="global", project_id=None, content="索引挂了也要落盘")
    store = MarkdownMemoryStore(memory_dir)
    assert "索引挂了也要落盘" in store.memory_path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ 5. owner 过滤


def test_search_filters_messages_by_owner(wired, repo):
    """检索消息时按 owner 过滤：他人会话的历史不得命中。"""
    conversation_a = repo.create_conversation("owner-a", title="A").conversation_id
    conversation_b = repo.create_conversation("owner-b", title="B").conversation_id
    repo.create_message(conversation_a, "owner-a", "user", "owner a 的缓存穿透方案")
    repo.create_message(conversation_b, "owner-b", "user", "owner b 的缓存穿透方案")

    hits_a = session_search_module.search_sessions(query="缓存穿透", owner_id="owner-a")["hits"]
    assert [hit["conversation_id"] for hit in hits_a] == [conversation_a]


def test_owner_filter_does_not_exclude_memory_notes(wired, repo, memory_dir):
    """MD 笔记没有 owner 概念：指定 owner 检索时仍能命中记忆笔记。"""
    MarkdownMemoryStore(memory_dir).write_user("- 用户偏好：中文回答\n")

    payload = session_search_module.search_sessions(query="中文回答", owner_id="owner-a")
    assert payload["count"] == 1
    assert payload["hits"][0]["source_kind"] == "memory"


def test_search_without_owner_still_works(wired, repo):
    """未显式给 owner 时检索照常工作（向后兼容既有调用）。"""
    conversation_id = repo.create_conversation(OWNER, title="兼容").conversation_id
    repo.create_message(conversation_id, OWNER, "user", "没有 owner 过滤也要能搜")
    assert session_search_module.search_sessions(query="owner 过滤")["count"] == 1
