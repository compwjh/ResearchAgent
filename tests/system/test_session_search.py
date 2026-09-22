"""spec-038 P2 · L2 会话检索：FTS5 索引 + session_search 工具契约测试。

覆盖（对应 task 硬性要求）：
1. 中文查询能命中历史消息（messages 表）
2. 中文查询能命中 MD 记忆笔记（USER.md / MEMORY.md / projects/<id>.md）
3. 写入新记忆后立即可搜到（MD 侧同步）
4. FTS5 语法特殊字符（``"`` / ``*`` / ``-`` / ``:`` / 括号）不抛异常
5. 空查询 / 无结果返回空列表，不抛异常
6. ``session_search`` 工具在 registry 与 tool_service 可取到，且有真实执行适配器

全部离线可跑：不依赖 Ollama(11434) / reranker(11435) / 网络。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import MemoryRepository
from backend.app.memory.session_search import SessionSearchHit, SessionSearchIndex


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
def index(repo: MemoryRepository, memory_dir: Path) -> SessionSearchIndex:
    return SessionSearchIndex(repository=repo, memory_dir=memory_dir)


def _seed_message(repo: MemoryRepository, conversation_id: str, role: str, content: str) -> str:
    """造一条历史消息（直接写 messages 表，避免触碰 chat 编排）。"""
    import uuid

    message_id = uuid.uuid4().hex
    with repo.connection() as db:
        db.execute(
            "INSERT INTO messages(message_id, conversation_id, owner_id, parent_message_id, role,"
            " content, status, created_at) VALUES (?, ?, 'local-user', NULL, ?, ?, 'completed',"
            " '2026-01-01T00:00:00+00:00')",
            (message_id, conversation_id, role, content),
        )
    return message_id


@pytest.fixture()
def conversation(repo: MemoryRepository) -> str:
    return repo.create_conversation("local-user", title="会话检索").conversation_id


# ------------------------------------------------------------------ 1. 中文命中消息


def test_chinese_query_matches_message(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    """中文查询能命中历史消息（jieba 分词索引，非 trigram）。"""
    message_id = _seed_message(repo, conversation, "user", "我们决定用 SQLite FTS5 实现会话检索")
    index.index_message(message_id)

    hits = index.search("会话检索")
    assert [hit.ref_id for hit in hits] == [message_id]
    assert hits[0].source_kind == "message"
    assert hits[0].conversation_id == conversation
    assert hits[0].role == "user"
    assert "FTS5" in hits[0].content or "会话检索" in hits[0].content


def test_english_query_matches_message(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    """英文/数字混排查询同样命中（tokenize 覆盖 ascii 段）。"""
    message_id = _seed_message(repo, conversation, "assistant", "switched the index to FTS5 with jieba tokens")
    index.index_message(message_id)

    hits = index.search("fts5 jieba")
    assert [hit.ref_id for hit in hits] == [message_id]


def test_search_filters_by_conversation_id(index: SessionSearchIndex, repo: MemoryRepository):
    """给定 conversation_id 时只在该会话内检索。"""
    first = repo.create_conversation("local-user", title="A").conversation_id
    second = repo.create_conversation("local-user", title="B").conversation_id
    in_first = _seed_message(repo, first, "user", "缓存穿透的解决方案")
    in_second = _seed_message(repo, second, "user", "缓存穿透的另一种讨论")
    index.index_message(in_first)
    index.index_message(in_second)

    hits = index.search("缓存穿透", conversation_id=first)
    assert [hit.ref_id for hit in hits] == [in_first]


# ------------------------------------------------------------------ 2. 中文命中 MD 笔记


def test_chinese_query_matches_user_memory(index: SessionSearchIndex, memory_dir: Path):
    """中文查询能命中 USER.md（用户画像）。"""
    store = MarkdownMemoryStore(memory_dir)
    store.write_user("- 用户偏好：回答先给结论再给推导\n")
    index.reindex_memories()

    hits = index.search("结论")
    assert [hit.source_kind for hit in hits] == ["memory"]
    assert "先给结论" in hits[0].content


def test_chinese_query_matches_global_memory_and_project_note(index: SessionSearchIndex, memory_dir: Path):
    """全局 MEMORY.md 与 projects/<id>.md 都在索引范围内（只索引 messages 是错的）。"""
    store = MarkdownMemoryStore(memory_dir)
    store.append_memory(scope="global", project_id=None, content="项目统一用 UTC 存时间戳")
    store.append_memory(scope="project", project_id="proj-a", content="该项目有 12 万篇论文的语料")
    index.reindex_memories()

    global_hits = index.search("时间戳")
    assert [hit.source_kind for hit in global_hits] == ["memory"]
    assert "UTC" in global_hits[0].content

    project_hits = index.search("语料")
    assert [hit.source_kind for hit in project_hits] == ["memory"]
    assert "12 万篇" in project_hits[0].content
    # ref_id 是记忆根目录下的相对路径，可直接回读原文核对
    assert project_hits[0].ref_id == "projects/proj-a.md"
    assert global_hits[0].ref_id == "MEMORY.md"


def test_search_returns_both_sources_in_one_query(index: SessionSearchIndex, repo: MemoryRepository, memory_dir: Path, conversation: str):
    """同一查询词既能命中消息也能命中 MD 记忆（索引范围 = messages + MD）。"""
    message_id = _seed_message(repo, conversation, "user", "我们把向量库换成了 Qdrant")
    index.index_message(message_id)
    MarkdownMemoryStore(memory_dir).append_memory(scope="global", project_id=None, content="Qdrant 部署在本机 6333 端口")
    index.reindex_memories()

    hits = index.search("Qdrant")
    kinds = {hit.source_kind for hit in hits}
    assert kinds == {"message", "memory"}


# ------------------------------------------------------------------ 3. 写入后立即可搜


def test_new_memory_is_searchable_immediately(index: SessionSearchIndex, memory_dir: Path):
    """写入一条记忆 -> 立刻能搜到（MD 侧同步）。"""
    MarkdownMemoryStore(memory_dir).append_memory(
        scope="global", project_id=None, content="用户要求所有接口必须离线可测"
    )
    index.reindex_memories()
    assert len(index.search("离线可测")) == 1


def test_index_memory_document_upserts_in_place(index: SessionSearchIndex, memory_dir: Path):
    """同一 MD 文件重复索引时按 ref_id upsert（不产生重复命中）。"""
    store = MarkdownMemoryStore(memory_dir)
    store.write_user("- 偏好：中文回答\n")
    index.index_memory_document("USER.md")
    index.index_memory_document("USER.md")

    assert len(index.search("中文回答")) == 1


def test_reindex_memories_drops_stale_entries(index: SessionSearchIndex, memory_dir: Path):
    """MD 内容变更后 reindex 反映最新内容，旧内容不再命中。"""
    store = MarkdownMemoryStore(memory_dir)
    store.write_user("- 旧偏好：先给结论\n")
    index.reindex_memories()
    assert len(index.search("先给结论")) == 1

    store.write_user("- 新偏好：先给复现步骤\n")
    index.reindex_memories()
    assert index.search("先给结论") == []
    assert len(index.search("复现步骤")) == 1


# ------------------------------------------------------------------ 4. 特殊字符


@pytest.mark.parametrize(
    "query",
    [
        '"', "*", "-", ":", "^", "(", ")", "NEAR", "AND", "OR", "NOT", '"unclosed', "a*b", "-abc",
        "会话检索\"", "*会话*", "SELECT * FROM", "FTS5::", "中文 AND 英文",
    ],
)
def test_special_characters_do_not_raise(index: SessionSearchIndex, repo: MemoryRepository, conversation: str, query: str):
    """FTS5 语法特殊字符一律不抛异常（转义或降级为普通匹配）。"""
    _seed_message(repo, conversation, "user", "FTS5 查询语法包含 AND OR NOT NEAR 等操作符")
    index.reindex_all()
    hits = index.search(query)
    assert isinstance(hits, list)


def test_special_character_query_still_matches_plain_text(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    """含 ``-`` 的普通查询词仍应命中（降级为分词后的普通匹配，而非整串当作语法）。"""
    message_id = _seed_message(repo, conversation, "user", "端口 6333-6334 用于 Qdrant")
    index.index_message(message_id)
    assert [hit.ref_id for hit in index.search("6333-6334")] == [message_id]


# ------------------------------------------------------------------ 5. 空查询 / 无结果


def test_empty_query_returns_empty_list(index: SessionSearchIndex):
    assert index.search("") == []
    assert index.search("   ") == []


def test_no_result_returns_empty_list(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    _seed_message(repo, conversation, "user", "完全无关的内容")
    index.reindex_all()
    assert index.search("绝不存在的关键词组合xyzzy") == []


def test_limit_is_respected(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    for i in range(5):
        index.index_message(_seed_message(repo, conversation, "user", f"缓存穿透讨论第 {i} 篇"))
    hits = index.search("缓存穿透", limit=2)
    assert len(hits) == 2


def test_limit_is_clamped(index: SessionSearchIndex, repo: MemoryRepository, conversation: str):
    """非法 limit（0 / 负数 / 超大）被收敛到合理范围，不抛异常。"""
    index.index_message(_seed_message(repo, conversation, "user", "边界用例"))
    assert isinstance(index.search("边界用例", limit=0), list)
    assert isinstance(index.search("边界用例", limit=-3), list)
    assert 0 < len(index.search("边界用例", limit=10_000)) <= 100


# ------------------------------------------------------------------ 6. 工具注册


def test_session_search_registered_in_registry():
    from backend.app.skills.registry import build_default_tool_registry

    entries = {entry.name: entry for entry in build_default_tool_registry()}
    assert "session_search" in entries
    entry = entries["session_search"]
    assert entry.entry == "backend.app.memory.session_search.search_sessions"
    assert entry.parameters["required"] == ["query"]
    assert "query" in entry.parameters["properties"]


def test_session_search_available_through_tool_service(tmp_path: Path):
    from backend.app.skills.registry import build_default_tool_registry
    from backend.app.skills.tool_service import ToolRegistryService

    service = ToolRegistryService(
        registry=build_default_tool_registry(), state_path=tmp_path / "skill-state.json"
    )
    tool = service.get_tool("session_search")
    assert tool is not None and tool.enabled
    registered = service.get_tool_entry("session_search")
    assert registered is not None and registered.entry.endswith(".search_sessions")


def test_session_search_has_dispatch_adapter():
    """注册进 registry 还不够：必须有真实执行适配器，否则 Agent 调用即失败。"""
    from backend.app.skills.tool_dispatch import build_default_dispatch

    result = build_default_dispatch()("session_search", {"query": ""})
    # 空查询属于「可读错误或空结果」，但绝不允许是「未找到执行器」
    assert "未找到工具" not in (result.error or "")


def test_search_sessions_entrypoint_returns_readable_output(tmp_path: Path, monkeypatch):
    """模块级入口 search_sessions 返回模型可读文本（含来源标签与片段）。"""
    from backend.app.memory import session_search as module

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(module, "build_default_index", lambda: module.SessionSearchIndex(repository=repo, memory_dir=memory_dir))
    MarkdownMemoryStore(memory_dir).write_user("- 用户偏好：先给结论\n")
    module.SessionSearchIndex(repository=repo, memory_dir=memory_dir).reindex_memories()

    payload = module.search_sessions(query="结论")
    assert payload["ok"] is True
    assert payload["count"] >= 1
    assert "先给结论" in payload["output"]


def test_search_sessions_empty_query_does_not_raise(tmp_path: Path, monkeypatch):
    from backend.app.memory import session_search as module

    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(module, "build_default_index", lambda: module.SessionSearchIndex(repository=repo, memory_dir=tmp_path / "memory"))
    payload = module.search_sessions(query="   ")
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["hits"] == []


# ------------------------------------------------------------------ 数据类


def test_session_search_hit_shape():
    hit = SessionSearchHit(
        source_kind="message",
        ref_id="m1",
        conversation_id="c1",
        role="user",
        content="内容",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert hit.to_dict()["source_kind"] == "message"
    assert hit.to_dict()["ref_id"] == "m1"
