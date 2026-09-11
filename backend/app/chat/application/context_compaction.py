"""Spec025 Task03 第二阶段：规则化分段摘要生成器 + 异步压缩 worker。

- :func:`build_rule_summary`：不调用模型的三段式启发式摘要，输出稳定可复现，
  便于单测与 ``content_hash`` 校验。
- :class:`CompactionWorker`：复用 ``conversation_service.py`` 的
  ``threading + queue.Queue`` daemon worker 范式；入队即冻结 ``[from, to]`` 窗口，
  worker 只处理冻结窗口内消息，异常收敛为 ``failed`` 且线程不退出。
- 所有 DB 访问经 ``MemoryRepository``；本模块不触碰 ``messages`` 表写操作，
  不引入第二套 worker / 装配函数 / token 估算。
"""

from __future__ import annotations

import contextlib
import hashlib
import queue
import re
import threading
from dataclasses import dataclass
from typing import Optional

from backend.app.chat.application.token_budget import estimate_tokens
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.config import CHAT_SUMMARY_BUDGET_CHARS

# ---- 规则化摘要生成器常量 ----

# 用户指令与约束：命中这些词的句子整句保留。
_CONSTRAINT_WORDS = ("必须", "不要", "禁止", "只能", "至少")
# 已定决策与结论：命中这些词的句子整句保留。
_DECISION_WORDS = ("决定", "结论", "采用", "已确认", "因此")

_SENT_SPLIT = re.compile(r"(?<=[。！？!?])")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

# 关键实体提取（确定性正则，按优先级匹配并排除 URL 内部重叠）。
_URL_RE = re.compile(r"https?://[^\s，。；、]+")
_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|[\\/]|\.\.?[\\/])[^\s，。；、]*(?:[\\/][^\s，。；、]+)+")
_FILE_RE = re.compile(r"\b[\w\-./]+\.[A-Za-z]{1,8}\b")
_IDENT_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b")
_NUM_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d+(?:\.\d+)?(?:\s*(?:%|个|条|次|元|秒|倍|字符|tokens?|gb|mb|kb|tb))?\b"
)


def _first_paragraph(text: str) -> str:
    """取首个非空自然段（按空行切分）。"""
    for part in _PARAGRAPH_SPLIT.split(text or ""):
        paragraph = part.strip()
        if paragraph:
            return paragraph
    return ""


def _sentences(paragraph: str) -> list[str]:
    return [sentence.strip() for sentence in _SENT_SPLIT.split(paragraph) if sentence.strip()]


def _keep_sentences(paragraph: str, words) -> list[str]:
    """保留命中关键词的句子（整句）。"""
    kept = []
    for sentence in _sentences(paragraph):
        if any(word in sentence for word in words):
            kept.append(sentence)
    return kept


def _message_key(message) -> tuple:
    return (message.created_at, message.message_id)


def _extract_entities(messages) -> "dict[str, str]":
    """从窗口消息提取关键实体（URL/路径/文件名/标识符/数值），去重并附 message_id 指针。

    返回 ``{实体文本: 首次出现的 message_id}``，保持首次出现顺序（插入序 = 可追溯）。
    """
    seen: dict[str, str] = {}
    for message in messages:
        text = message.content or ""
        message_id = message.message_id
        urls = list(_URL_RE.finditer(text))
        url_spans = {(match.start(), match.end()) for match in urls}
        for match in urls:
            seen.setdefault(match.group(0), message_id)

        def _inside(span, url_spans=url_spans):
            start, end = span
            return any(s <= start and end <= e for (s, e) in url_spans)

        for pattern in (_PATH_RE, _FILE_RE, _IDENT_RE, _NUM_RE):
            for match in pattern.finditer(text):
                if _inside((match.start(), match.end())):
                    continue
                seen.setdefault(match.group(0).strip(), message_id)
    return seen


def _section(title: str, body: str, per: int) -> str:
    """组装单段，超长截断并加省略标记。"""
    if len(body) > per:
        body = body[:per] + "…"
    return f"{title}\n{body}"


def build_rule_summary(messages, summary_char_budget) -> tuple[str, int, int, str]:
    """对冻结窗口消息生成三段式规则摘要（generator='rule'，不调用模型）。

    按 ``(created_at, message_id)`` 顺序扫描：

    1. ``【指令与约束】``：每条 user 消息首个自然段中命中约束词的句子。
    2. ``【决策与结论】``：每条 assistant 消息首个自然段中命中决策词的句子。
    3. ``【关键实体】``：提取的实体，每条附 ``[message_id]`` 指针，去重。

    每段字符上限取 ``summary_char_budget // 3``，超出截断并加 ``…``。

    :returns: ``(summary_text, char_count, est_tokens, content_hash)``。
      ``char_count`` / ``est_tokens`` 为**被覆盖源文本**的字符数与估算 token 数
      （直接喂给 ``conversation_segments`` 的 ``char_count`` / ``est_tokens``）；
      ``content_hash`` 为源文本拼接的 sha256，用于可复现校验。
    """
    ordered = sorted(messages, key=_message_key)
    source_text = "\n".join((message.content or "") for message in ordered)
    char_count = len(source_text)
    est_tokens = estimate_tokens(source_text)
    content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    per = max(0, int(summary_char_budget)) // 3

    instructions: list[str] = []
    for message in ordered:
        if getattr(message, "role", None) == "user":
            instructions.extend(_keep_sentences(_first_paragraph(message.content), _CONSTRAINT_WORDS))

    decisions: list[str] = []
    for message in ordered:
        if getattr(message, "role", None) == "assistant":
            decisions.extend(_keep_sentences(_first_paragraph(message.content), _DECISION_WORDS))

    entities = _extract_entities(ordered)

    sections: list[str] = []
    if instructions:
        sections.append(_section("【指令与约束】", "\n".join(instructions), per))
    if decisions:
        sections.append(_section("【决策与结论】", "\n".join(decisions), per))
    if entities:
        body = "\n".join(f"- {text} [{message_id}]" for text, message_id in entities.items())
        sections.append(_section("【关键实体】", body, per))

    summary_text = "\n\n".join(sections)
    return summary_text, char_count, est_tokens, content_hash


# ---- 异步压缩 worker ----

@dataclass
class _CompactionRequest:
    """入队即冻结的压缩请求（窗口在入队时计算，绝不推迟到 worker）。"""

    conversation_id: str
    owner_id: str
    project_id: Optional[str]
    trigger: str
    job_id: str
    from_message_id: str
    to_message_id: str


class CompactionWorker:
    """后台压缩 worker：请求路径只 enqueue，worker 线程消费队列生成段并落库。

    复用 ``MemoryEvolutionWorker`` / ``MemoryAnalysisWorker`` 的 daemon 范式与单例风格。
    队列去重只是减少无效唤醒；唯一可靠的去重在 ``conversation_compaction_jobs``
    的部分唯一索引（``create_compaction_job`` 原子领用）。
    """

    def __init__(self, repository: MemoryRepository, *, owner_id: str = OWNER_ID, poll_interval: float = 0.05) -> None:
        self.repository = repository
        self.owner_id = owner_id
        self.poll_interval = max(0.01, float(poll_interval))
        self._queue: "queue.Queue[_CompactionRequest]" = queue.Queue()
        self._queued: set[str] = set()
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "CompactionWorker":
        with self._guard:
            if self._thread and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="context-compaction", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1)

    def enqueue(self, conversation_id: str, owner_id: str, project_id: Optional[str], trigger: str, *, est_tokens_before: Optional[int] = None):
        """原子领用 job 并冻结窗口，返回 job（已存在非终态 job 时返回既有 job）。

        ① ``create_compaction_job`` 原子领用：返回 None 表示已有非终态 job，直接返回既有 job，不重复入队。
        ② 领用成功即冻结窗口：``from_message_id`` 取 ``next_segment_start_message``，
           ``to_message_id`` 取入队时刻该会话最后一条消息；两者随请求入队，worker 不再重算。
        """
        job = self.repository.create_compaction_job(
            conversation_id, owner_id, trigger=trigger, est_tokens_before=est_tokens_before
        )
        if job is None:
            # 已有非终态 job：返回既有 job，不重复入队。
            return self.repository.get_latest_compaction_job(conversation_id, owner_id)
        from_message_id = self.repository.next_segment_start_message(conversation_id, owner_id)
        to_message_id = self._last_message_id(conversation_id, owner_id)
        if from_message_id is None or to_message_id is None:
            # 空会话 / 无消息可摘要：直接 done，不写空段。
            self.repository.finish_compaction_job(job.job_id, owner_id, status="done")
            return job
        with self._guard:
            if conversation_id in self._queued:
                return job
            self._queued.add(conversation_id)
            self._queue.put(
                _CompactionRequest(
                    conversation_id, owner_id, project_id, trigger, job.job_id,
                    from_message_id, to_message_id,
                )
            )
        return job

    def _last_message_id(self, conversation_id: str, owner_id: str) -> Optional[str]:
        """入队时刻该会话最后一条消息（DESC 序，batch[0] 即最新）。"""
        batch, _ = self.repository.list_messages(conversation_id, owner_id, limit=1, target_chars=100_000)
        if not batch:
            return None
        return batch[0].message_id

    def _collect_messages(self, conversation_id: str, owner_id: str) -> list:
        """分页取回会话全部消息并按 (created_at, message_id) 升序排序。"""
        messages: list = []
        before = None
        while True:
            batch, cursor = self.repository.list_messages(
                conversation_id, owner_id, before=before, target_chars=100_000, limit=50
            )
            if not batch:
                break
            messages.extend(batch)
            if cursor is None:
                break
            before = cursor
        messages.sort(key=_message_key)
        return messages

    def _process(self, request: _CompactionRequest) -> None:
        """处理单个冻结窗口请求：生成段 → 写表 → 置 done；异常收敛为 failed。"""
        try:
            job = self.repository.get_compaction_job(request.job_id, request.owner_id)
            if job is None or job.status != "queued":
                return
            from_message = self.repository.get_message(request.from_message_id, request.owner_id)
            to_message = self.repository.get_message(request.to_message_id, request.owner_id)
            if from_message is None or to_message is None:
                self.repository.finish_compaction_job(request.job_id, request.owner_id, status="done")
                return
            from_key = _message_key(from_message)
            to_key = _message_key(to_message)
            if from_key > to_key:
                self.repository.finish_compaction_job(request.job_id, request.owner_id, status="done")
                return
            window = [
                message for message in self._collect_messages(request.conversation_id, request.owner_id)
                if from_key <= _message_key(message) <= to_key
            ]
            if not window:
                self.repository.finish_compaction_job(request.job_id, request.owner_id, status="done")
                return
            summary_text, char_count, est_tokens, content_hash = build_rule_summary(window, CHAT_SUMMARY_BUDGET_CHARS)
            segments = self.repository.list_conversation_segments(
                request.conversation_id, request.owner_id, request.project_id
            )
            seq = (max((segment.seq for segment in segments), default=0)) + 1
            self.repository.append_conversation_segment(
                request.conversation_id, request.owner_id, request.project_id, seq,
                request.from_message_id, request.to_message_id,
                char_count, est_tokens, content_hash, summary_text,
            )
            self.repository.finish_compaction_job(
                request.job_id, request.owner_id, status="done", est_tokens_after=est_tokens
            )
        except Exception as error:  # noqa: BLE001 — worker 永不退出
            with contextlib.suppress(Exception):
                self.repository.finish_compaction_job(
                    request.job_id, request.owner_id, status="failed", error=str(error)[:500]
                )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                request = self._queue.get(timeout=self.poll_interval)
            except queue.Empty:
                continue
            try:
                self._process(request)
            except Exception:  # noqa: BLE001 — 任何异常都不得让线程退出
                pass
            finally:
                with self._guard:
                    self._queued.discard(request.conversation_id)
                self._queue.task_done()


_COMPACTION_WORKERS: dict[str, CompactionWorker] = {}
_COMPACTION_GUARD = threading.Lock()


def get_compaction_worker(repository: MemoryRepository) -> CompactionWorker:
    """按数据库路径返回（并启动）单例 worker。"""
    key = str(repository.database_path.resolve())
    with _COMPACTION_GUARD:
        worker = _COMPACTION_WORKERS.setdefault(key, CompactionWorker(repository))
    return worker.start()
