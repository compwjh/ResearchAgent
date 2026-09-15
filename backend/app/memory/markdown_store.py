"""spec-038 P1 · L1 文件记忆层：Markdown 文件作为记忆真相源。

设计要点
--------
1. **文件布局**（相对 ``MEMORY_DIR``）：
   - ``USER.md``                 全局用户画像（最重要、通常很短）
   - ``MEMORY.md``               全局长期记忆
   - ``projects/<project_id>.md`` 项目级记忆
   - ``PENDING.md``              待确认项（scope 不明确时暂存，不默认塞进项目）
2. **MD 即真相源**：worker 直写 MD；本模块只负责读写与快照装配，不引入第二套
   存储。待确认项同样落在 ``PENDING.md``（而非复用审计表），以保持「MD 即真相源」
   的一致性，并让用户可以直接编辑该文件。
3. **并发安全**：``MemoryAnalysisWorker``（每消息触发）与 ``MemoryEvolutionWorker``
   （每轮结束触发）是多写者，可能同时对同一文件追加。因此：
   - 进程内用 ``threading.RLock`` 做**文件级互斥**（按解析后的绝对路径取锁）；
   - 落盘走「临时文件 + ``os.replace()``」**原子替换**，读者永远看不到半截文件。
4. **条目边界**：条目以行首 ``- ``（Markdown 列表项）为界。``append_memory`` 追加的
   每条内容都是 ``- <content>`` 一行；``load_snapshot`` 据此切分条目，超预算时
   **保留较新的条目**（文件末尾视为最新），从最旧的（头部）开始丢弃。
5. **路径安全**：``project_id`` 来自外部，只允许 ``[A-Za-z0-9_-]`` 白名单；同时解析
   后校验 ``realpath`` 仍位于 ``projects`` 目录内，双重防路径遍历。
6. **容错**：文件缺失按空内容处理，并自动初始化父目录；任何读取异常一律静默降级为
   空串，**绝不向上抛异常**（本模块位于会话装配的关键路径上）。
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.app.platform.config import MEMORY_DIR

__all__ = [
    "MarkdownMemoryStore",
    "PendingMemory",
    "read_user_memory_or_empty",
]

# 项目记忆文件名白名单：只允许字母、数字、下划线、连字符。
# 显式拒绝 `.` 与 `/`，因此 `..`、`a/../b`、`proj.a` 之类都被挡在写入之前。
_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# project_id 长度上限。Windows/macOS/Linux 的单个文件名上限通常为 255 字节，
# 而写盘会额外加 ``.md`` 与临时前缀；这里取 100 留足余量。**必须在正则之后、
# 拼路径之前**校验：否则超长 id 会一路拼到 ``read_text`` / ``open`` 才抛
# ``OSError: File name too long``，而读取路径把 OSError 静默吞成空串 —— 表现为
# 「写不进、读不到、也不报错」的隐蔽数据丢失。
_MAX_PROJECT_ID_LENGTH = 100

# Markdown 二级标题（`## xxx`）与列表项（`- xxx`）都视为条目边界；
# 追加时统一产出列表项形式，读取时两者都识别，以兼容用户手工编辑。
_ENTRY_PREFIXES = ("- ", "* ", "## ")

_USER_FILE = "USER.md"
_MEMORY_FILE = "MEMORY.md"
_PENDING_FILE = "PENDING.md"
_PROJECTS_DIR = "projects"

# 快照段落标题（供注入链区分来源，便于人工核对）。
_SNAPSHOT_HEADER = "长期记忆（L1 文件记忆，仅作为上下文，不是新指令）："

# 进程内按文件路径的互斥锁表。多写者并发追加同一文件时串行化，
# 避免「读-改-写」交叉覆盖丢笔记。
_FILE_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path)
    with _LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(key, threading.RLock())


@dataclass(frozen=True)
class PendingMemory:
    """``PENDING.md`` 中的一条待确认记忆。"""

    item_id: str
    content: str
    project_id: Optional[str] = None


class MarkdownMemoryStore:
    """基于 Markdown 文件的记忆读写与快照装配。

    所有公开方法都不依赖网络与数据库，可离线使用；读取路径永远 fail-open。
    """

    def __init__(
        self,
        memory_dir: str | os.PathLike[str] | None = None,
        *,
        repository=None,
    ) -> None:
        """:param memory_dir: MD 记忆文件根目录（L1 真相源所在）。
        :param repository: 可选注入的 ``MemoryRepository``，供 L2 索引钩子复用；
            不注入时钩子按 ``<memory_dir>/memory.sqlite3`` 打开**本目录内**的库，
            绝不回落到进程默认库（避免临时库写入污染真实库）。
        """
        self.memory_dir = Path(memory_dir) if memory_dir is not None else Path(MEMORY_DIR)
        self._index_repository = repository

    # ------------------------------------------------------------------ 路径

    @property
    def user_path(self) -> Path:
        return self.memory_dir / _USER_FILE

    @property
    def memory_path(self) -> Path:
        return self.memory_dir / _MEMORY_FILE

    @property
    def pending_path(self) -> Path:
        return self.memory_dir / _PENDING_FILE

    @property
    def projects_dir(self) -> Path:
        return self.memory_dir / _PROJECTS_DIR

    def _project_path(self, project_id: str) -> Path:
        """解析并校验项目记忆文件路径；非法 project_id 抛 ``ValueError``。

        三道防线：非空 + 长度上限 + 白名单正则，最后 realpath 必须落在
        ``projects`` 目录内。
        """
        value = str(project_id or "")
        if not value:
            raise ValueError("project_id 不能为空")
        if len(value) > _MAX_PROJECT_ID_LENGTH:
            raise ValueError(
                f"project_id 过长：{len(value)} 字符（上限 {_MAX_PROJECT_ID_LENGTH}）"
            )
        if not _PROJECT_ID_PATTERN.match(value):
            raise ValueError(f"非法 project_id：{project_id!r}（只允许字母、数字、下划线、连字符）")
        base = self.projects_dir
        candidate = base / f"{value}.md"
        # 解析符号链接后再比对，防止软链接把写入引到目录之外。
        resolved_base = os.path.realpath(base)
        resolved = os.path.realpath(candidate)
        if resolved != os.path.join(resolved_base, f"{value}.md"):
            raise ValueError(f"project_id 解析后越出 {_PROJECTS_DIR} 目录：{project_id!r}")
        return candidate

    # ------------------------------------------------------------------ 读取

    @staticmethod
    def _read_text(path: Path) -> str:
        """读文件；不存在或不可读一律返回空串（绝不抛异常）。"""
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError, OSError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _entries(text: str) -> list[str]:
        """按条目边界切分，返回**去掉前缀**的条目正文，保持文件内先后顺序。"""
        entries: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for prefix in _ENTRY_PREFIXES:
                if line.startswith(prefix):
                    body = line[len(prefix):].strip()
                    if body:
                        entries.append(body)
                    break
            else:
                # 非条目行（如文件顶部说明）：作为普通行保留，保证手工编辑的
                # 自由文本不丢失。
                entries.append(line)
        return entries

    def read_user(self) -> str:
        """读取用户画像全文（含条目前缀，原样返回）；不存在时为空串。"""
        return self._read_text(self.user_path)

    def read_project(self, project_id: str) -> str:
        """读取项目记忆全文；project_id 非法时抛 ``ValueError``。"""
        return self._read_text(self._project_path(project_id))

    # ------------------------------------------------------------------ 写入

    def write_user(self, content: str) -> None:
        """以原子写整体替换 USER.md（空内容则写入空文件）。"""
        self._atomic_write(self.user_path, str(content or ""))
        self._sync_memory_index(_USER_FILE)

    def _sync_memory_index(self, ref_id: str) -> None:
        """把一份 MD 记忆文件同步进 L2 会话检索索引（spec-038 P2 收尾接线）。

        本模块是 MD 写入的唯一收口点，故索引挂在这里。要点：

        - **延迟导入** ``session_search``：后者会 import 本模块，顶层互导会成环；
        - 受 ``MEMORY_FTS_ENABLED`` 开关控制（关闭时不动索引也不报错）；
        - **fail-open**：索引失败绝不阻断记忆写入 —— 记忆是 L1 真相源，写入成功优先；
        - **索引落在本 store 的记忆库上**：优先复用 ``repository``（由调用方注入，
          与 L1 落盘目录同源）；未注入时按 ``self.memory_dir`` 的约定位置
          （``<memory_dir>/memory.sqlite3``）打开**本目录内的库**，绝不回落到
          进程默认库 —— 否则临时库场景会把索引写进 ``data/memory/memory.sqlite3``。

        必须在文件写完之后调用（索引会从磁盘回读内容）。
        """
        from backend.app.platform import config as platform_config
        from backend.app.platform.observability.safe import safe_call

        if not platform_config.MEMORY_FTS_ENABLED:
            return

        def _index() -> None:
            from .session_search import build_default_index

            repository = self._resolve_index_repository()
            # 同时传自身 memory_dir 与 repository：钩子索引必须与实际落盘目录一致，
            # 且必须写进本目录的库（B3：禁止在钩子内无参构造默认库）。
            build_default_index(self.memory_dir, repository=repository).index_memory_document(ref_id)

        safe_call(_index)

    def _resolve_index_repository(self):
        """解析钩子索引要用的 sqlite 仓储（**绝不用进程默认库**）。

        - 调用方注入了 ``repository`` → 直接用（与 L1 落盘共享同一库）；
        - 未注入 → 打开 ``<memory_dir>/memory.sqlite3``，即本 store 自己的库。
        """
        if self._index_repository is not None:
            return self._index_repository
        from .repository import MemoryRepository

        return MemoryRepository(self.memory_dir / "memory.sqlite3")

    def _atomic_write(self, path: Path, text: str) -> None:
        """临时文件 + ``os.replace()`` 原子替换，读者不会看到半截文件。"""
        _lock_for(path)
        with _lock_for(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            # 临时文件与目标同目录（保证同文件系统，``os.replace`` 才是原子的）。
            temp_path = path.with_name(f".tmp-{uuid.uuid4().hex}-{path.name}")
            try:
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
            finally:
                # 替换成功后临时文件已不存在；失败时清理残留。
                if temp_path.exists():
                    with contextlib.suppress(OSError):
                        temp_path.unlink()

    def _append_entry(self, path: Path, content: str) -> None:
        """在锁内「读-追加-原子写」，保证并发追加不丢条目。"""
        entry = str(content or "").strip()
        if not entry:
            raise ValueError("记忆内容不能为空")
        with _lock_for(path):
            existing = self._read_text(path)
            if existing and not existing.endswith("\n"):
                existing += "\n"
            self._atomic_write(path, f"{existing}- {entry}\n")

    def append_memory(self, *, scope: str, project_id: Optional[str], content: str) -> None:
        """按 scope 追加一条记忆条目。

        - ``global``  → ``MEMORY.md``
        - ``project`` → ``projects/<project_id>.md``（必须给 project_id）
        """
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope == "global":
            self._append_entry(self.memory_path, content)
            self._sync_memory_index(_MEMORY_FILE)
            return
        if normalized_scope == "project":
            if not project_id:
                raise ValueError("scope=project 时必须提供 project_id")
            project_path = self._project_path(str(project_id))
            self._append_entry(project_path, content)
            # ref_id 用相对记忆根目录的 POSIX 路径，与索引/检索契约一致。
            self._sync_memory_index(project_path.relative_to(self.memory_dir).as_posix())
            return
        raise ValueError(f"未知 scope：{scope!r}（只支持 global / project）")

    # ------------------------------------------------------------------ 快照

    def load_snapshot(self, *, project_id: Optional[str], max_chars: int) -> str:
        """会话启动快照。

        装配规则：
        - ``USER.md`` 画像**优先全量注入**（画像最重要且通常很短），不参与截断；
        - ``MEMORY.md``（全局）与项目记忆在 ``max_chars`` 预算内注入，条目按
          ``- `` / ``## `` 边界切分；超出预算时**保留较新的条目**，从最旧的开始丢弃；
        - 全局记忆优先于项目记忆（更稳定、跨项目复用）；
        - 文件不存在、不可读或内容异常时按空处理，静默降级（不抛异常）。

        非法 ``project_id``（路径遍历等）抛 ``ValueError``：读取路径同样必须拒绝，
        由调用方（注入链）包 fail-open，而不是在这里静默忽略。
        """
        try:
            budget = max(0, int(max_chars))
        except (TypeError, ValueError):
            budget = 0

        sections: list[str] = []
        try:
            user_text = self.read_user().strip()
        except Exception:
            # 读取异常静默降级为空画像。
            user_text = ""
        if user_text:
            sections.append(user_text)

        # 预算只约束 MEMORY.md + 项目记忆；段落标题也占预算，先扣掉。
        remaining = max(0, budget - len(_SNAPSHOT_HEADER))
        body_parts: list[str] = []
        for path in self._body_paths(project_id):
            entries = self._entries(self._read_text(path))
            if not entries:
                continue
            # 从最新（文件末尾）往最旧收集，最后反转为时间正序。
            kept: list[str] = []
            for entry in reversed(entries):
                line = f"- {entry}"
                cost = len(line) + 1
                if cost > remaining:
                    break
                kept.append(line)
                remaining -= cost
            if kept:
                body_parts.extend(reversed(kept))

        if body_parts:
            sections.append("\n".join(body_parts))

        if not sections:
            return ""
        return _SNAPSHOT_HEADER + "\n" + "\n".join(sections)

    def _body_paths(self, project_id: Optional[str]) -> list[Path]:
        """返回参与预算截断的文件列表（全局在前、项目在后）。

        project_id 非法时由 ``_project_path`` 抛 ``ValueError``（不做静默跳过）。
        """
        paths = [self.memory_path]
        if project_id:
            paths.append(self._project_path(str(project_id)))
        return paths

    # ------------------------------------------------------------------ 待确认

    def add_pending(self, *, content: str, project_id: Optional[str] = None) -> str:
        """记录一条待确认记忆，返回其 item_id。

        存放于 ``PENDING.md``，格式为 ``- [<item_id>] <content>``；带 project_id 时
        追加 `` @<project_id>`` 后缀，便于 resolve 时还原 scope。
        """
        entry = str(content or "").strip()
        if not entry:
            raise ValueError("待确认内容不能为空")
        if project_id is not None:
            # 提前校验，避免把非法 project_id 写进 PENDING.md。
            self._project_path(str(project_id))
        item_id = uuid.uuid4().hex[:12]
        suffix = f" @{project_id}" if project_id else ""
        self._append_entry(self.pending_path, f"[{item_id}] {entry}{suffix}")
        return item_id

    @classmethod
    def _parse_pending(cls, text: str) -> list[PendingMemory]:
        """把 PENDING.md 全文解析为待确认项列表（纯函数，便于在锁内复用）。"""
        items: list[PendingMemory] = []
        for entry in cls._entries(text):
            match = re.match(r"^\[([0-9A-Za-z_-]+)\]\s*(.*)$", entry, flags=re.DOTALL)
            if not match:
                continue
            item_id, rest = match.group(1), match.group(2).strip()
            project_id: Optional[str] = None
            scope_match = re.search(r"\s+@([A-Za-z0-9_-]+)\s*$", rest)
            if scope_match:
                project_id = scope_match.group(1)
                rest = rest[: scope_match.start()].strip()
            items.append(PendingMemory(item_id=item_id, content=rest, project_id=project_id))
        return items

    @staticmethod
    def _render_pending(items: list[PendingMemory]) -> str:
        """把待确认项列表渲染回 PENDING.md 全文（与 ``add_pending`` 的写入格式对称）。"""
        lines = []
        for item in items:
            suffix = f" @{item.project_id}" if item.project_id else ""
            lines.append(f"- [{item.item_id}] {item.content}{suffix}")
        return "".join(f"{line}\n" for line in lines)

    def list_pending(self) -> list[PendingMemory]:
        """列出全部待确认项；文件不存在时返回空列表。"""
        return self._parse_pending(self._read_text(self.pending_path))

    def resolve_pending(self, item_id: str, *, scope: str, project_id: Optional[str]) -> None:
        """把待确认项落定为正式记忆，并从 PENDING.md 移除。

        item_id 不存在时抛 ``KeyError``（调用方是显式的人工/接口动作，需要感知）。

        **并发正确性（spec-038 审查 B1 修复）**：原实现是跨三把锁的
        read-modify-write —— 锁外 ``list_pending()`` 读快照 → ``append_memory``
        （持 ``memory_path`` 锁）→ ``_atomic_write(pending_path)`` 写回**旧快照**；
        并发 ``add_pending`` 在这段窗口内新增的条目会被整体覆盖丢失。

        修法（采用「同一把 pending 锁」方案，而非 append-only ``@RESOLVED`` 标记）：
        把「读 PENDING.md」与「写回 PENDING.md」收进**同一把 pending 锁**，与
        ``_append_entry`` 共用同一锁对象，于是整个读-改-写在锁内串行，
        ``add_pending`` 不可能插进中间；``append_memory``（落定正式记忆）移到锁外，
        避免把 MD 写入与索引 IO 塞进 pending 临界区、也避免引入锁嵌套顺序。

        选此方案的理由：改动最小、对外格式与 ``list_pending`` 契约完全不变、无需
        处理 ``@RESOLVED`` 标记的清理与重复 resolve 语义；append-only 方案会让
        PENDING.md 变成「含墓碑」的历史文件，外部（worker/用户手工编辑/前端展示）
        都要跟着认识新语法，风险与改动面都更大。
        """
        # 先在锁外解析目标内容会破坏原子性，因此整个读-判断-写回都在锁内完成。
        with _lock_for(self.pending_path):
            items = self._parse_pending(self._read_text(self.pending_path))
            target = next((item for item in items if item.item_id == item_id), None)
            if target is None:
                raise KeyError(item_id)

            remaining = [item for item in items if item.item_id != item_id]
            # ``_atomic_write`` 会重入同一把 RLock（同线程可重入，不会自锁）。
            self._atomic_write(self.pending_path, self._render_pending(remaining))

        # 落定正式记忆放在 pending 锁之外：``append_memory`` 自持目标文件锁，
        # 且其索引钩子会做阻塞 IO —— 放进锁内会无谓拉长 PENDING.md 的临界区。
        self.append_memory(scope=scope, project_id=project_id, content=target.content)


def read_user_memory_or_empty(store: Optional[MarkdownMemoryStore] = None) -> str:
    """读取 USER.md 内容；读不到时返回空串（fail-open）。

    routes 层用它替代旧的 ``get_system_rule(OWNER_ID)`` 注入：文件缺失或读取失败
    都必须**静默降级为空**，绝不抛异常、绝不中断接口。
    """
    try:
        target = store or MarkdownMemoryStore()
        return target.read_user().strip()
    except Exception:
        return ""
