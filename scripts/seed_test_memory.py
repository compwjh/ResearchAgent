#!/usr/bin/env python
"""spec-038 收尾 · 记忆层测试数据 seed 脚本（一键重造，离线可跑）。

用途
----
spec-038 把记忆层改造为对齐 Hermes 的三层模型，并**重置了记忆库 schema 基线**
（无生产数据，已删库重建）。本脚本按**新逻辑**重新生成一套覆盖三层的测试数据，
便于本地联调与回归：

- **L1（真相源，Markdown）**：``data/memory/`` 下的 ``USER.md`` / ``MEMORY.md`` /
  ``projects/<project_id>.md`` / ``PENDING.md``；
- **L2（检索，FTS5）**：往记忆库建会话与中英文混排消息，并重建索引，使
  ``session_search`` 立刻可搜；
- **L3（压缩）**：由 ``CompactionWorker`` 在生产链路按需触发，本脚本不直接造
  segment（压缩段依赖真实对话长度，离线硬造无意义）。

设计约束
--------
1. **复用优先（禁止第二套实现）**：L1 写文件一律走 ``MarkdownMemoryStore``，
   L2 建库/索引一律走 ``MemoryRepository`` + ``SessionSearchIndex``；本脚本不复制
   任何文件读写、分词或 SQL 逻辑。
2. **幂等**：``--reset``（默认开启）先清空目标目录内的记忆文件与记忆库再重建，
   可重复执行而不产生重复条目。
3. **可指定路径**：默认目标为配置的 ``MEMORY_DIR``（仓库内 ``data/memory/``，已被
   .gitignore 忽略）；``--target`` 可指向临时目录，避免误操作污染真实数据。
4. **离线**：全程不调用 Ollama(11434) / reranker(11435) / 网络；中文分词用项目内
   既有实现（jieba，本地词典）。
5. **不触碰其他在建工作**：不写 ``tests/fixtures/ccs/`` 等 CCS 抓取相关文件。

用法
----
::

    # 造到临时目录（推荐：不影响真实数据）
    .venv/bin/python scripts/seed_test_memory.py --target /tmp/seed-memory

    # 重造真实本地联调目录（data/memory 已在 .gitignore 中）
    .venv/bin/python scripts/seed_test_memory.py --target data/memory

    # 只看会做什么，不落盘
    .venv/bin/python scripts/seed_test_memory.py --target /tmp/seed-memory --dry-run

    .venv/bin/python scripts/seed_test_memory.py --help
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
from pathlib import Path

# 允许以 `python scripts/seed_test_memory.py` 直接执行：把仓库根加入 sys.path，
# 否则 `import backend...` 会失败（backend 是仓库根的包）。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.memory.markdown_store import MarkdownMemoryStore  # noqa: E402
from backend.app.memory.repository import OWNER_ID, MemoryRepository  # noqa: E402
from backend.app.memory.session_search import SessionSearchIndex  # noqa: E402
from backend.app.platform.config import MEMORY_DIR  # noqa: E402

__all__ = ["build_arg_parser", "seed_memory", "main"]

# ---------------------------------------------------------------- 示例内容（无敏感信息）
# 全部为占位文本；不写入任何真实个人信息。

_USER_PROFILE = """# 用户画像（示例数据，seed 脚本生成）

- 研究者，关注机器学习系统与检索增强生成方向
- 偏好中文回复，术语可保留英文原文
- 写作风格：先给结论，再列证据；避免冗长客套
- 常用工具链：FastAPI + SQLite + 本地向量检索
"""

_GLOBAL_MEMORIES: tuple[str, ...] = (
    "用户偏好用 markdown 表格对比方案，而不是长段落罗列。",
    "项目统一使用 UTC 存储时间戳，展示层再转本地时区。",
    "讨论检索质量的默认指标是召回率与 MRR，先看召回。",
    "回答里引用外部结论时，需要标注来源链接。",
    "本地模型推理不可用时，应降级到规则实现并明确告知。",
)

# 项目级记忆（体现「项目记忆不进全局」：只在 projects/<id>.md，不进 MEMORY.md）。
_PROJECT_MEMORIES: dict[str, tuple[str, ...]] = {
    "proj-alpha": (
        "alpha 项目使用 jieba 做中文分词，检索侧复用同一实现。",
        "alpha 的记忆库 schema 基线为 v8，无增量迁移链。",
    ),
    "proj-beta": (
        "beta 项目的数据抓取需要遵守来源站点的 robots 策略。",
    ),
}

_PENDING_ITEMS: tuple[tuple[str, str | None], ...] = (
    ("用户似乎更看重检索速度而非极致精度，待确认。", None),
    ("是否把项目级快照注入到跨项目会话，待确认。", "proj-alpha"),
)

# L2 会话与消息：中英文混排 + user/assistant 两种 role。
_SEED_CONVERSATION_TITLE = "seed 示例会话：记忆层联调"
_SEED_MESSAGES: tuple[tuple[str, str], ...] = (
    ("user", "帮我确认一下记忆层重构后，中文检索还能命中历史对话吗？"),
    ("assistant", "可以。FTS5 索引复用 jieba 分词，写入后会自动同步，中文关键词能直接命中。"),
    ("user", "How does the memory layer split L1 / L2 / L3 responsibilities?"),
    ("assistant", "L1 是 Markdown 真相源，L2 是 FTS5 检索索引，L3 负责上下文压缩。"),
    ("user", "顺便记一下：项目的记忆不要混进全局画像里。"),
    ("assistant", "已按 scope 区分：global 写 MEMORY.md，project 写 projects/<id>.md。"),
)

# 用于验证 L2 可检索的中文关键词（应能命中上面的消息或记忆笔记）。
_VERIFY_QUERY = "记忆层"


def build_arg_parser() -> argparse.ArgumentParser:
    """构造命令行解析器（中文帮助）。"""
    parser = argparse.ArgumentParser(
        prog="seed_test_memory.py",
        description="按 spec-038 新逻辑重造记忆层测试数据（L1 文件 + L2 会话检索），离线可跑。",
        epilog="示例：python scripts/seed_test_memory.py --target /tmp/seed-memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        default=None,
        type=Path,
        help=f"记忆数据目标目录（默认：配置的 MEMORY_DIR = {MEMORY_DIR}）。建议传临时目录以免污染真实数据。",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=True,
        help="先清空目标目录内的记忆文件与记忆库再重建，保证幂等（默认开启）。",
    )
    parser.add_argument(
        "--no-reset",
        dest="reset",
        action="store_false",
        help="不清空，直接在既有数据上追加（不幂等，仅调试用）。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要写入的内容与目标路径，不实际落盘。",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只输出最终汇总，不打印细节。",
    )
    return parser


def _reset_target(target: Path) -> list[str]:
    """清空目标目录内的记忆文件与记忆库，返回被移除的相对路径列表。

    只删除本脚本负责的产物：``USER.md`` / ``MEMORY.md`` / ``PENDING.md`` /
    ``projects/`` / ``memory.sqlite3``（含 WAL 边文件）。目标目录本身保留。
    """
    removed: list[str] = []
    candidates = (
        target / "USER.md",
        target / "MEMORY.md",
        target / "PENDING.md",
        target / "memory.sqlite3",
        target / "memory.sqlite3-wal",
        target / "memory.sqlite3-shm",
    )
    for path in candidates:
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    projects_dir = target / "projects"
    if projects_dir.is_dir():
        shutil.rmtree(projects_dir)
        removed.append("projects/")
    return removed


@contextlib.contextmanager
def _scoped_default_db(target: Path):
    """把进程默认记忆库路径临时指向目标目录的 ``memory.sqlite3``。

    为什么需要：``MarkdownMemoryStore`` 在写入后会通过 ``build_default_index()`` →
    ``MemoryRepository()`` 维护 L2 索引，而后者读环境变量 ``MEMORY_DB_PATH``（缺省
    落到仓库内 ``data/memory/memory.sqlite3``）。若不在脚本内重定向，写 L1 时的钩子
    索引会去打开**真实默认库**（当前可能是旧基线残留而 fail-closed 报错刷屏），
    既污染输出又违背「只写 --target」的约定。

    作用域内重定向、退出时还原，保证脚本不影响同进程其他逻辑（测试亦如此）。
    """
    previous = os.environ.get("MEMORY_DB_PATH")
    os.environ["MEMORY_DB_PATH"] = str(target / "memory.sqlite3")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MEMORY_DB_PATH", None)
        else:
            os.environ["MEMORY_DB_PATH"] = previous


def seed_memory(
    *,
    target_dir: Path | str | None = None,
    reset: bool = True,
    dry_run: bool = False,
    quiet: bool = False,
) -> dict:
    """按 spec-038 新逻辑生成三层测试数据，返回汇总统计。

    :param target_dir: 目标目录；``None`` 时用配置的 ``MEMORY_DIR``。
    :param reset: 是否先清空目标目录内的记忆文件与记忆库（保证幂等）。
    :param dry_run: 只规划不落盘。
    :param quiet: 只返回统计，不打印细节。
    :returns: ``{target, memories, projects, pending, conversations, messages,
        search_query, search_hits, reset_removed}``
    """
    base = Path(target_dir) if target_dir is not None else Path(MEMORY_DIR)
    target = base.expanduser().resolve()

    summary: dict = {
        "target": str(target),
        "reset_removed": [],
        "memories": 0,
        "projects": 0,
        "pending": 0,
        "conversations": 0,
        "messages": 0,
        "search_query": _VERIFY_QUERY,
        "search_hits": 0,
    }

    if dry_run:
        if not quiet:
            print(f"[dry-run] 目标目录：{target}")
            print(f"[dry-run] 将写入 L1：USER.md / MEMORY.md（{len(_GLOBAL_MEMORIES)} 条）/ "
                  f"PENDING.md（{len(_PENDING_ITEMS)} 条）/ projects/*.md（{len(_PROJECT_MEMORIES)} 个）")
            print(f"[dry-run] 将写入 L2：1 个会话 + {len(_SEED_MESSAGES)} 条消息，并重建 FTS5 索引")
        summary["memories"] = len(_GLOBAL_MEMORIES)
        summary["projects"] = len(_PROJECT_MEMORIES)
        summary["pending"] = len(_PENDING_ITEMS)
        summary["messages"] = len(_SEED_MESSAGES)
        summary["conversations"] = 1
        return summary

    target.mkdir(parents=True, exist_ok=True)
    if reset:
        summary["reset_removed"] = _reset_target(target)

    # 全程把进程默认记忆库重定向到目标目录：写 L1 时的钩子索引、以及下方 L2 建库，
    # 都落在 --target 内，绝不触碰真实 data/memory。
    with _scoped_default_db(target):
        # -------------------------------------------------------- L1：Markdown 真相源
        store = MarkdownMemoryStore(target)
        store.write_user(_USER_PROFILE)
        for text in _GLOBAL_MEMORIES:
            store.append_memory(scope="global", project_id=None, content=text)
        for project_id, texts in _PROJECT_MEMORIES.items():
            for text in texts:
                store.append_memory(scope="project", project_id=project_id, content=text)
        for content, project_id in _PENDING_ITEMS:
            store.add_pending(content=content, project_id=project_id)

        summary["memories"] = len(_GLOBAL_MEMORIES)
        summary["projects"] = len(_PROJECT_MEMORIES)
        summary["pending"] = len(_PENDING_ITEMS)

        # -------------------------------------------------------- L2：会话 + 消息 + 索引
        repo = MemoryRepository(target / "memory.sqlite3")
        conversation = repo.create_conversation(OWNER_ID, project_id=None, title=_SEED_CONVERSATION_TITLE)
        for role, content in _SEED_MESSAGES:
            repo.create_message(
                conversation.conversation_id,
                OWNER_ID,
                role,
                content,
                status="completed",
            )
        summary["conversations"] = 1
        summary["messages"] = len(_SEED_MESSAGES)

        # 全量重建索引：MD 侧文件是本脚本直接写的，需 reindex 后才稳定可见
        # （append_memory 已增量同步，但 reindex 保证「消息 + 记忆」两侧一致）。
        index = SessionSearchIndex(repository=repo, memory_dir=target)
        index.reindex_all(OWNER_ID)

        # -------------------------------------------------------- L2 可检索性验证
        hits = index.search(_VERIFY_QUERY, limit=10)
        summary["search_hits"] = len(hits)

    if not quiet:
        print(f"目标目录：{target}")
        if summary["reset_removed"]:
            print(f"  reset 已清理：{', '.join(summary['reset_removed'])}")
        print(f"L1 全局记忆：{summary['memories']} 条 → {target / 'MEMORY.md'}")
        print(f"L1 项目记忆：{summary['projects']} 个项目 → {target / 'projects'}")
        print(f"L1 待确认项：{summary['pending']} 条 → {target / 'PENDING.md'}")
        print(f"L1 用户画像：1 份 → {target / 'USER.md'}")
        print(f"L2 会话：{summary['conversations']} 个；消息：{summary['messages']} 条 → {target / 'memory.sqlite3'}")
        print(f"L2 检索验证：搜「{_VERIFY_QUERY}」命中 {summary['search_hits']} 条")
        for position, hit in enumerate(hits[:3], start=1):
            snippet = hit.content.strip().replace("\n", " ")[:60]
            print(f"    {position}. [{hit.source_kind}] {snippet}")

    return summary


def main(argv: list[str] | None = None) -> int:
    """命令行入口；返回进程退出码（0 成功，1 检索验证失败）。"""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    summary = seed_memory(
        target_dir=args.target,
        reset=args.reset,
        dry_run=args.dry_run,
        quiet=args.quiet,
    )

    if args.dry_run:
        return 0

    if summary["search_hits"] < 1:
        print(
            f"错误：L2 检索验证失败——搜「{summary['search_query']}」未命中任何记录。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
