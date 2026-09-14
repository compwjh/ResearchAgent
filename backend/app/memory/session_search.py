"""spec-038 P2 · L2 会话检索：FTS5 索引 + ``session_search`` 工具入口。

背景
----
在此之前，全库没有会话历史检索能力；唯一的「检索」是 Python 子串过滤**且发生在
SQL LIMIT 之后**（``repository.list_recall_summaries``），等于把候选集截断后才过滤。
本模块补齐 Hermes 记忆层的第 2 层（L2 会话检索）：

1. **FTS5 虚表** ``session_search_index``（在 ``migration`` 基线中建出）统一索引
   **历史消息** 与 **MD 记忆笔记** 两类来源。索引范围刻意包含 MD：只索引 messages
   是错的 —— Agent 需要一次检索同时翻旧对话与自己的笔记。
2. 索引列存 ``embed.tokenize`` 分词后空格连接的文本，查询侧走同一函数，
   **优先复用项目唯一的中文分词实现**（jieba），不新建第二套。
3. 同步走**显式写入函数**而非 SQL 触发器（MD 在文件系统、分词在 Python，触发器做不到）；
   ``reindex_all`` 负责全量重建。

安全与健壮性
------------
FTS5 的 ``MATCH`` 语法对 ``"`` ``*`` ``-`` ``:`` ``^`` ``(`` ``)`` 以及
``AND`` / ``OR`` / ``NOT`` / ``NEAR`` 操作符敏感，直接拼接用户输入会抛
``sqlite3.OperationalError``。这里的处理：每个 token 先剥离非字母数字与中文的字符，
再用双引号包成 **FTS5 字符串字面量**，token 之间以 ``AND`` 连接。于是
- 操作符关键字被引号降级为普通词（``"near"`` 不再触发 NEAR 语法）；
- 连字符不再被解析成列名（``6333-6334`` 分词后是单个 token，仍能命中）；
- 清洗后 token 全为空（如查询就是 ``"``）→ 直接返回空结果，绝不进 SQL。

所有失败路径一律降级为「空结果 / 可读错误」，**绝不向上抛异常**（本模块位于
Agent 工具调用链上）。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from backend.app.knowledge_base.infrastructure.embed import tokenize
from backend.app.memory.markdown_store import MarkdownMemoryStore

logger = logging.getLogger(__name__)

__all__ = [
    "SessionSearchHit",
    "SessionSearchIndex",
    "build_default_index",
    "default_owner_id",
    "search_sessions",
]

# 索引来源标签（对外契约，前端/模型可据此区分「旧对话」与「记忆笔记」）。
SOURCE_MESSAGE = "message"
SOURCE_MEMORY = "memory"

# 单次检索的返回上限与默认值（与 kb_search 的 top_k 上限保持同一量级）。
DEFAULT_LIMIT = 10
MAX_LIMIT = 100

# 返回给模型的单条片段字符上限：够定位内容又不撑爆上下文。
SNIPPET_CHARS = 400

# token 清洗：只保留 ASCII 字母数字与 CJK 汉字。FTS5 的语法字符（" * - : ^ 括号）
# 全部被剥掉，从而不可能进入 MATCH 表达式。
_TOKEN_SAFE_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


@dataclass(frozen=True)
class SessionSearchHit:
    """一条检索命中。

    ``source_kind`` 取 ``message`` / ``memory``；``ref_id`` 对应 messages 表的
    ``message_id`` 或 MD 文件的仓库相对路径（如 ``USER.md``）。
    """

    source_kind: str
    ref_id: str
    content: str
    conversation_id: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def index_tokens(text: str) -> list[str]:
    """把文本切成可安全进入 FTS5 的 token 列表（清洗 + 小写）。

    复用 ``embed.tokenize``（jieba 中文分词 + 英文按词），再剥掉 FTS5 语法字符。
    返回值可能为空（纯符号输入），调用方必须按「空查询」处理。
    """
    tokens: list[str] = []
    for token in tokenize(text or ""):
        cleaned = _TOKEN_SAFE_PATTERN.sub("", str(token).lower())
        if cleaned:
            tokens.append(cleaned)
    return tokens


def build_match_expression(query: str, match_mode: str = "and") -> str:
    """把用户查询编译为 FTS5 ``MATCH`` 表达式；无可检索 token 时返回空串。

    每个 token 以双引号包成字符串字面量 —— 这是让 ``and`` / ``near`` 等操作符
    关键字与连字符失效的关键，避免语法错误与列名误解析。

    ``match_mode`` 控制 token 间的连接关系：
    - ``"and"``（默认）：要求行同时包含全部 token，适合精确短语 / 短关键词查询；
    - ``"or"``：命中任一 token 即可（按 bm25 排序），适合把自然语言问句当作召回
      查询 —— 跨会话历史不可能与当前问句逐词重合，必须用 OR 才能翻出旧账。
    """
    tokens = index_tokens(query)
    if not tokens:
        return ""
    joiner = " OR " if match_mode == "or" else " AND "
    return joiner.join(f'"{token}"' for token in tokens)


class SessionSearchIndex:
    """``session_search_index`` 的读写门面（消息侧 + MD 侧）。

    ``repository`` 提供 sqlite 连接（含 FTS5 虚表）；``memory_dir`` 指定 MD 记忆
    根目录，两者都可注入，便于离线单测。
    """

    def __init__(self, *, repository, memory_dir: str | os.PathLike[str] | None = None) -> None:
        self._repo = repository
        self._memory_dir = Path(memory_dir) if memory_dir is not None else None
        self._memory_store = MarkdownMemoryStore(self._memory_dir)

    # ------------------------------------------------------------------ 写入

    def index_message(self, message_id: str) -> bool:
        """把单条消息写入索引（幂等 upsert）。消息不存在时返回 False。"""
        with self._repo.connection() as db:
            row = db.execute(
                "SELECT message_id, conversation_id, owner_id, role, content, created_at"
                " FROM messages WHERE message_id=?",
                (message_id,),
            ).fetchone()
        if row is None:
            return False
        self._upsert(
            ref_id=row["message_id"],
            source_kind=SOURCE_MESSAGE,
            owner_id=row["owner_id"],
            content=row["content"] or "",
            conversation_id=row["conversation_id"],
            role=row["role"],
            created_at=row["created_at"],
        )
        return True

    def index_memory_document(self, ref_id: str) -> None:
        """把一份 MD 记忆文件写入索引（幂等 upsert；文件不存在则视为空内容）。

        ``ref_id`` 为记忆根目录下的相对路径，如 ``USER.md`` / ``projects/proj-a.md``。
        """
        absolute = self._memory_store.memory_dir / ref_id
        if _is_pending(absolute):
            # 待确认项不是正式记忆，不参与检索（避免半成品笔记污染召回）。
            return
        try:
            content = absolute.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        self._upsert(
            ref_id=ref_id,
            source_kind=SOURCE_MEMORY,
            owner_id=None,
            content=content,
            conversation_id=None,
            role=None,
            created_at=None,
        )

    def _upsert(
        self,
        *,
        ref_id: str,
        source_kind: str,
        owner_id: Optional[str],
        content: str,
        conversation_id: Optional[str],
        role: Optional[str],
        created_at: Optional[str],
    ) -> None:
        """按 ``(source_kind, ref_id)`` 覆盖写入索引行。

        FTS5 虚表没有主键，``INSERT OR REPLACE`` 不生效，因此用
        「DELETE 旧行 + INSERT 新行」两条语句在同一事务内完成 upsert（幂等）。
        """
        index_text = " ".join(index_tokens(content))
        with self._repo.transaction() as db:
            db.execute(
                "DELETE FROM session_search_index WHERE source_kind=? AND ref_id=?",
                (source_kind, ref_id),
            )
            # 索引文本为空（如空文件）时仍插入一行，保证「文件被清空」后旧内容不再命中
            # （DELETE 已生效），且 reindex 前后行数稳定。
            db.execute(
                "INSERT INTO session_search_index"
                "(index_text, content, source_kind, ref_id, conversation_id, owner_id, role, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (index_text, content, source_kind, ref_id, conversation_id, owner_id, role, created_at),
            )

    # ------------------------------------------------------------------ 重建

    def iter_memory_documents(self) -> list[str]:
        """列出参与索引的 MD 记忆文件（相对记忆根目录的 POSIX 路径）。

        顺序稳定（排序后返回），便于测试与全量重建的可复现性。
        """
        base = self._memory_store.memory_dir
        documents: list[str] = []
        if not base.exists():
            return documents
        for path in sorted(base.rglob("*.md")):
            if not path.is_file() or path.name.startswith(".tmp-") or _is_pending(path):
                continue
            documents.append(path.relative_to(base).as_posix())
        return documents

    def reindex_all(self, owner_id: Optional[str] = None) -> dict:
        """全量重建索引：清空后重放全部消息与 MD 记忆文件。

        MD 文件可能在外部被直接编辑（用户可手工改 ``MEMORY.md``），此时增量同步
        无从触发，只能靠本方法重建。返回 ``{messages, memories}`` 计数。
        """
        with self._repo.connection() as db:
            params: list[object] = []
            clause = ""
            if owner_id:
                clause = " WHERE owner_id=?"
                params.append(owner_id)
            message_ids = [
                row["message_id"]
                for row in db.execute(f"SELECT message_id FROM messages{clause}", params).fetchall()
            ]

        with self._repo.transaction() as db:
            db.execute("DELETE FROM session_search_index")

        for message_id in message_ids:
            self.index_message(message_id)
        memories = self.reindex_memories()
        return {"messages": len(message_ids), "memories": memories}

    def reindex_memories(self) -> int:
        """只重建 MD 记忆侧索引，返回索引的文档数。"""
        documents = self.iter_memory_documents()
        for ref_id in documents:
            self.index_memory_document(ref_id)
        return len(documents)

    # ------------------------------------------------------------------ 查询

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        conversation_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        match_mode: str = "and",
    ) -> list[SessionSearchHit]:
        """检索历史消息与 MD 记忆笔记，按相关度返回命中列表。

        - 空查询 / 无可检索 token → ``[]``；
        - 任何 SQL 异常（含 FTS5 语法问题）→ 记日志后降级为 ``[]``，**不向上抛**；
        - ``conversation_id`` 给定时只在该会话的消息内检索（MD 记忆不受其约束）；
        - ``owner_id`` 给定时只返回该 owner 的消息；MD 笔记没有 owner 概念
          （索引行 owner_id 为 NULL），因此不受其约束（``OR owner_id IS NULL``）。
        """
        expression = build_match_expression(query, match_mode=match_mode)
        if not expression:
            return []

        top_n = _clamp_limit(limit)
        sql = (
            "SELECT source_kind, ref_id, content, conversation_id, role, created_at"
            " FROM session_search_index WHERE index_text MATCH ?"
        )
        params: list[object] = [expression]
        if conversation_id:
            # 会话过滤允许命中「该会话的消息」或「不隶属会话的 MD 记忆」。
            sql += " AND (conversation_id=? OR conversation_id IS NULL)"
            params.append(conversation_id)
        if owner_id:
            # owner 过滤同样放行 MD 记忆（owner_id IS NULL）：MD 属于单用户全局笔记。
            sql += " AND (owner_id=? OR owner_id IS NULL)"
            params.append(owner_id)
        sql += " ORDER BY bm25(session_search_index) LIMIT ?"
        params.append(top_n)

        try:
            with self._repo.connection() as db:
                rows = db.execute(sql, params).fetchall()
        except Exception:  # 兜底：检索失败绝不打断 Agent 回合
            logger.warning("session_search 检索失败，降级为空结果：query=%r", query, exc_info=True)
            return []
        return [
            SessionSearchHit(
                source_kind=row["source_kind"],
                ref_id=row["ref_id"],
                content=row["content"] or "",
                conversation_id=row["conversation_id"],
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


def _is_pending(path: Path) -> bool:
    """待确认项（PENDING.md 及其临时文件）不参与检索。"""
    return path.name == "PENDING.md"


def _clamp_limit(limit: object) -> int:
    """把 limit 收敛到 ``[1, MAX_LIMIT]``；非法值回退默认值。"""
    try:
        value = int(limit)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if value <= 0:
        return DEFAULT_LIMIT
    return min(value, MAX_LIMIT)


# ---------------------------------------------------------------------- 工具入口


def build_default_index(
    memory_dir: str | os.PathLike[str] | None = None,
    repository=None,
) -> SessionSearchIndex:
    """构造进程默认索引（惰性建库路径，供 ``session_search`` 工具与写入钩子使用）。

    :param memory_dir: MD 记忆根目录。写入钩子必须传入自身 store 的目录，保证
        「钩子索引」与「实际落盘」指向同一处；缺省时用配置的 ``MEMORY_DIR``。
    :param repository: 索引所用的 sqlite 仓储。**写入钩子必须传入自身 repository**
        （``MemoryRepository`` 实例），否则索引会落到进程默认库
        （``default_database_path()`` → 环境变量 ``MEMORY_DB_PATH`` 或
        ``data/memory/memory.sqlite3``），从而在调用方操作临时库时污染真实库。
        缺省为 ``None`` 时才惰性构造**进程默认**仓储 —— **仅限显式管理入口**
        （如 ``scripts/seed_test_memory.py`` 这类「就是要操作默认库」的场景）
        与 ``session_search`` 工具的无参检索调用；任何写入钩子都不得依赖该缺省。
    """
    from backend.app.platform.config import MEMORY_DIR

    if repository is None:
        # 显式管理入口 / 无参检索工具：允许回落到进程默认库。
        # 写入钩子（``MemoryRepository._sync_message_index``、
        # ``MarkdownMemoryStore._sync_memory_index``）**禁止**走到这里。
        from backend.app.memory.repository import MemoryRepository

        try:
            repository = MemoryRepository()
        except Exception:  # 建库失败（权限/磁盘）时降级为无索引
            logger.warning("session_search 无法打开记忆库，检索将返回空结果", exc_info=True)
            repository = None
    return SessionSearchIndex(repository=repository, memory_dir=memory_dir if memory_dir is not None else MEMORY_DIR)


def default_owner_id() -> Optional[str]:
    """当前进程默认 owner（单用户场景）。

    写入钩子与检索入口都以它作为 owner 归属；读取失败时返回 ``None``（不过滤），
    保证任何异常都不会让检索链断掉。
    """
    try:
        from backend.app.memory.repository import OWNER_ID

        return OWNER_ID
    except Exception:  # pragma: no cover - 仅防御导入/环境异常
        logger.warning("无法解析默认 owner，检索将不做 owner 过滤", exc_info=True)
        return None


def _format_hit(hit: SessionSearchHit, index: int) -> str:
    """把一条命中渲染成模型可读文本（含来源标签，便于引用）。"""
    if hit.source_kind == SOURCE_MEMORY:
        label = f"[记忆笔记 {hit.ref_id}]"
    else:
        role = hit.role or "?"
        conversation = hit.conversation_id or "?"
        label = f"[历史对话 {conversation} / {role} / {hit.ref_id[:8]}]"
    snippet = hit.content.strip().replace("\n", " ")[:SNIPPET_CHARS]
    return f"{index}. {label} {snippet}"


def search_sessions(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    conversation_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    index: Optional[SessionSearchIndex] = None,
    match_mode: str = "and",
) -> dict:
    """``session_search`` 工具的执行入口（复用既有索引实现，不新建第二套）。

    返回 ``{ok, count, output, hits, error}``：``ok`` 恒为 True —— 检索无结果是
    正常情况而非失败，可读提示写在 ``output`` 里，便于回灌模型继续对话。
    任何异常都收敛为「空结果 + 可读提示」，绝不抛出。

    ``owner_id`` 缺省时回退到当前进程默认 owner（单用户），从而「检索消息按 owner
    过滤」在生产链路上真实生效；MD 笔记不受 owner 约束。
    """
    try:
        target = index or build_default_index()
    except Exception:
        logger.warning("session_search 索引不可用", exc_info=True)
        return {"ok": True, "count": 0, "output": "会话检索暂不可用，无法读取历史记录。", "hits": [], "error": "INDEX_UNAVAILABLE"}

    try:
        hits = target.search(
            query,
            limit=limit,
            conversation_id=conversation_id,
            owner_id=owner_id if owner_id is not None else default_owner_id(),
            match_mode=match_mode,
        )
    except Exception:
        logger.warning("session_search 执行失败", exc_info=True)
        return {"ok": True, "count": 0, "output": "会话检索失败，请稍后重试。", "hits": [], "error": "SEARCH_FAILED"}

    if not (query or "").strip():
        return {"ok": True, "count": 0, "output": "未提供检索词：请给出要查找的关键词。", "hits": []}
    if not hits:
        return {"ok": True, "count": 0, "output": f"没有找到与「{query}」相关的历史对话或记忆笔记。", "hits": []}

    lines = [f"检索到 {len(hits)} 条与「{query}」相关的记录："]
    lines.extend(_format_hit(hit, position) for position, hit in enumerate(hits, start=1))
    return {
        "ok": True,
        "count": len(hits),
        "output": "\n".join(lines),
        "hits": [hit.to_dict() for hit in hits],
    }
