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
import socket
import threading
from dataclasses import dataclass
from typing import Optional

from backend.app.chat.application.chat_runner import run_chat
from backend.app.chat.application.token_budget import estimate_tokens
from backend.app.memory.markdown_store import MarkdownMemoryStore
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.config import (
    CHAT_SUMMARY_BUDGET_CHARS,
    CHAT_TOOL_OUTPUT_KEEP_RECENT,
    COMPACTION_FLUSH_TIMEOUT,
    COMPACTION_SUMMARY_MODE,
    COMPACTION_SUMMARY_TIMEOUT,
    FLUSH_MEMORIES_ENABLED,
    MEMORY_ANALYSIS_MODEL,
)
from backend.app.platform.observability import record_event
from backend.app.platform.observability.safe import safe_call

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


# ---- LLM 重构式摘要（spec-038 P3）----

# 传给压缩模型的重构指令：只做「信息守恒的重写」，不做新的推理/评论。
_LLM_SUMMARY_PROMPT = (
    "你是会话上下文压缩器。把下面这段对话历史**重构**成一份供后续对话复用的简明摘要。"
    "要求：1) 保留用户指令与约束、已达成的决策与结论、关键实体（文件/URL/标识符/数值）；"
    "2) 合并重复、丢弃寒暄与无关细节；3) 不要引入原文没有的信息，不要评论，不要输出思维过程；"
    "4) 用中文分点输出，直接给摘要正文。\n\n对话历史：\n"
)

# 单条消息在提示里注入的上限，避免把提示本身撑爆。
_LLM_SOURCE_PER_MESSAGE_CHARS = 4000


def _summary_stats(messages) -> tuple[str, int, int, str]:
    """计算源文本统计（char_count / est_tokens / content_hash）。

    规则摘要与 LLM 摘要共用同一统计口径：被覆盖源文本的字符数与估算 token 数，
    保证两条路径写入 ``conversation_segments`` 的字段语义一致、可复现校验一致。
    """
    ordered = sorted(messages, key=_message_key)
    source_text = "\n".join((message.content or "") for message in ordered)
    return source_text, len(source_text), estimate_tokens(source_text), hashlib.sha256(
        source_text.encode("utf-8")
    ).hexdigest()


def llm_available(timeout: float = 1.0) -> bool:
    """廉价探测 Ollama 是否可达（TCP 连接，不做 HTTP 请求）。

    目的：模型不可达时，``run_chat``（langchain 链路）可能要重试数十秒才失败。
    压缩/flush 都跑在后台线程上，必须**快速失败**：先做一次 <1s 的端口探测，
    不可达就直接走规则摘要 / 跳过 flush，而不是傻等超时。

    返回 True 表示「端口可连」（不代表模型存在）；任何异常都视为不可达。
    """
    try:
        from urllib.parse import urlparse

        from backend.app.platform.config import OLLAMA_BASE_URL

        parsed = urlparse(OLLAMA_BASE_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 11434
        with socket.create_connection((host, port), timeout=max(0.1, float(timeout))):
            return True
    except Exception:  # noqa: BLE001 — 探测失败即视为不可达
        return False


def _run_bounded(func, *, timeout: float):
    """在**独立线程**中执行并限时等待，超时即放弃（抛 ``TimeoutError``）。

    用途：``context_compaction`` 全程运行在后台 daemon 线程/装配链上，「模型调用」
    必须**有界**——否则 Ollama 不可达时可能长时间阻塞。超时后放弃结果（调用方 fail-open），
    被放弃的线程仍会自然结束（daemon，不阻止进程退出）。
    """
    result: dict = {}

    def _target():
        try:
            result["value"] = func()
        except BaseException as error:  # noqa: BLE001 — 由调用线程统一处理
            result["error"] = error

    worker = threading.Thread(target=_target, name="compaction-bounded-call", daemon=True)
    worker.start()
    worker.join(timeout=max(0.01, float(timeout)))
    if worker.is_alive():
        raise TimeoutError(f"调用超过 {timeout}s 未返回")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def build_llm_summary(messages, summary_char_budget) -> tuple[str, int, int, str]:
    """调用小模型生成**重构式**摘要（不回落；失败即抛异常，由调用方决定降级）。

    复用 ``run_chat``（同一条模型调用链路，不引入第二套 Ollama 客户端），
    ``think=False``（分类/压缩类调用必须关闭思维链）。超时由
    ``COMPACTION_SUMMARY_TIMEOUT`` 约束，通过 ``run_chat`` 的同步调用返回后取 token 事件。

    :returns: 与 :func:`build_rule_summary` 同构的 ``(summary_text, char_count, est_tokens, content_hash)``。
      其中 char_count / est_tokens / content_hash 仍描述**源文本**（统计口径不随生成器变化）。
    """
    source_text, char_count, est_tokens, content_hash = _summary_stats(messages)
    if not source_text.strip():
        return "", char_count, est_tokens, content_hash
    ordered = sorted(messages, key=_message_key)
    rendered = "\n".join(
        f"{getattr(message, 'role', 'unknown')}: {(message.content or '')[:_LLM_SOURCE_PER_MESSAGE_CHARS]}"
        for message in ordered
    )
    selected_model = (MEMORY_ANALYSIS_MODEL or "").strip() or MEMORY_ANALYSIS_MODEL
    # 限时调用：超时抛 TimeoutError → 由 build_compaction_summary 回落规则摘要。
    run = _run_bounded(
        lambda: run_chat(
            rendered,
            selected_model,
            prompt=_LLM_SUMMARY_PROMPT + rendered,
            think=False,
        ),
        timeout=COMPACTION_SUMMARY_TIMEOUT,
    )
    output = "".join(
        str(event.get("content") or "")
        for event in (run.events or [])
        if event.get("type") == "token"
    ).strip()
    if not output:
        raise RuntimeError("LLM 摘要输出为空")
    # 超预算时按字符截断，保持与规则摘要一致的「不超预算」契约。
    budget = max(0, int(summary_char_budget))
    if budget and len(output) > budget:
        output = output[:budget] + "…"
    return output, char_count, est_tokens, content_hash


def build_compaction_summary(messages, summary_char_budget) -> tuple[str, int, int, str]:
    """按 ``COMPACTION_SUMMARY_MODE`` 选择摘要生成器，LLM 失败时回落规则摘要。

    - ``mode="llm"``：先试 :func:`build_llm_summary`；任何异常（含 Ollama 不可达、
      超时、输出为空）都**回落** :func:`build_rule_summary`，并用既有
      ``safe_call(record_event, ...)`` 记录 ``degraded_reason``（观测失败不影响业务）。
    - 其它值（含 ``"rule"``）：直接走规则摘要，不触网。

    fail-open 是本函数的硬契约：压缩是后台任务，绝不能因为模型不可用而失败或阻塞。
    """
    mode = str(COMPACTION_SUMMARY_MODE or "").strip().lower()
    if mode != "llm":
        return build_rule_summary(messages, summary_char_budget)
    if not llm_available():
        # 快速失败：模型端口不可达，不浪费一次可能重试数十秒的调用。
        safe_call(
            record_event,
            name="compaction_summary_degraded",
            metadata={"degraded_reason": "llm_unreachable", "mode": mode},
        )
        return build_rule_summary(messages, summary_char_budget)
    try:
        return build_llm_summary(messages, summary_char_budget)
    except Exception as error:  # noqa: BLE001 — LLM 不可用必须降级，绝不冒泡
        result = build_rule_summary(messages, summary_char_budget)
        safe_call(
            record_event,
            name="compaction_summary_degraded",
            metadata={
                "degraded_reason": f"{type(error).__name__}: {error}"[:300],
                "mode": mode,
                "timeout_seconds": COMPACTION_SUMMARY_TIMEOUT,
                "model": MEMORY_ANALYSIS_MODEL,
            },
        )
        return result


def collapse_tool_outputs(steps, *, keep_recent: Optional[int] = None) -> str:
    """把处理步骤渲染为「最近 N 步原文 + 更早步骤结构化塌缩」的一段文本。

    塌缩格式：``- <kind>/<label> [<status>]：<首行摘要（<=120 字符）>``。
    最近 ``keep_recent`` 步保留原文摘要（不截断）。无步骤时返回空串。

    这是 spec-038 P3 的「预裁剪」：压缩/装配前把冗余的工具输出压成可读的一行，
    既保住可追溯性（保留工具名与状态），又大幅降低 token 占用。
    """
    if not steps:
        return ""
    keep = CHAT_TOOL_OUTPUT_KEEP_RECENT if keep_recent is None else max(0, int(keep_recent))
    ordered = list(steps)
    older = ordered[:-keep] if keep else ordered
    recent = ordered[-keep:] if keep else []
    lines: list[str] = []
    for step in older:
        lines.append(f"- {_collapsed_step_line(step)}")
    for step in recent:
        body = str(getattr(step, "summary", "") or "").strip()
        label = getattr(step, "label", "") or getattr(step, "kind", "")
        status = getattr(step, "status", "")
        lines.append(f"- {label} [{status}]: {body}" if body else f"- {label} [{status}]")
    return "\n".join(lines)


def _collapsed_step_line(step) -> str:
    """把单步塌缩为一行：工具名 + 参数/摘要首行（截断），不含状态之外的细节。"""
    kind = str(getattr(step, "kind", "") or "")
    label = str(getattr(step, "label", "") or "")
    status = str(getattr(step, "status", "") or "")
    summary = " ".join(str(getattr(step, "summary", "") or "").split())
    head = summary[:120] + ("…" if len(summary) > 120 else "")
    name = f"{kind}/{label}".strip("/") or "step"
    return f"{name} [{status}]：{head}" if head else f"{name} [{status}]"


# ---- flush_memories：压缩前把重要信息写入 L1（spec-038 P3）----


def flush_memories(
    messages,
    *,
    project_id: Optional[str],
    owner_id: str = OWNER_ID,
    store: Optional[MarkdownMemoryStore] = None,
    extractor=None,
    repository: Optional[MemoryRepository] = None,
) -> int:
    """压缩**之前**调用：把窗口内消息里的长期记忆写入 L1（MD 真相源）。

    复用 ``MemoryAnalysisWorker`` 的同一条分类链路（``classify_memory_intent`` +
    ``decide_memory_write``），**不新建第二套抽取实现**。按置信度分级：

    - 高置信度（explicit 且 confidence ≥ 阈值且 scope 明确）→ 直写 ``MEMORY.md`` / ``projects/<id>.md``；
    - 其余（ambiguous / 低置信度）→ 写 ``PENDING.md`` 待确认，**不默认塞进项目记忆**。

    硬契约（fail-open）：``FLUSH_MEMORIES_ENABLED`` 为假时直接跳过；任何异常
    （分类器不可达、MD 写入失败等）都被吞掉并返回已写入条数，**绝不阻断压缩**。

    :returns: 成功写入（正式记忆 + 待确认）的条数。
    """
    if not FLUSH_MEMORIES_ENABLED:
        return 0
    # 延迟导入：conversation_service 顶层依赖本模块的常量，顶层互导会成环。
    from backend.app.chat.application.conversation_service import (
        extract_memory_candidates,
        write_memory_candidate,
    )

    # 快速失败：分类链路依赖模型；端口不可达时直接跳过，不做数十秒重试。
    # 显式传入 extractor（测试/复用缝）时不做该探测，交由调用方负责。
    if extractor is None and not llm_available():
        safe_call(
            record_event,
            name="flush_memories_skipped",
            metadata={"degraded_reason": "llm_unreachable"},
        )
        return 0

    target_store = store or MarkdownMemoryStore()
    written = 0

    def _extract_and_write() -> int:
        count = 0
        user_texts = [
            message.content
            for message in sorted(messages, key=_message_key)
            if getattr(message, "role", None) == "user" and (message.content or "").strip()
        ]
        for candidate, source_text in extract_memory_candidates(
            user_texts, project_id=project_id, classify=extractor
        ):
            # 唯一写入出口：置信度分级（高置信度直写 MD / 否则 pending），内部 fail-open。
            # spec-038 S7：传入 repository + owner 供 project_id 存在性校验，避免写进已失效的项目。
            write_memory_candidate(
                target_store, candidate, source_text=source_text, project_id=project_id,
                repository=repository, owner_id=owner_id,
            )
            count += 1
        return count

    try:
        # 限时执行：抽取链路会调用模型（无界等待会拖死压缩 worker）。
        # 超时/异常都 fail-open：放弃本次 flush，压缩照常进行。
        written = _run_bounded(_extract_and_write, timeout=COMPACTION_FLUSH_TIMEOUT) or 0
    except Exception as error:  # noqa: BLE001 — flush 绝不阻断压缩/装配
        with contextlib.suppress(Exception):
            safe_call(
                record_event,
                name="flush_memories_failed",
                metadata={"degraded_reason": f"{type(error).__name__}: {error}"[:300]},
            )
    return written


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

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        owner_id: str = OWNER_ID,
        poll_interval: float = 0.05,
        memory_store: Optional[MarkdownMemoryStore] = None,
    ) -> None:
        self.repository = repository
        self.owner_id = owner_id
        self.poll_interval = max(0.01, float(poll_interval))
        # L1 真相源：flush_memories 写入目标；缺省用进程默认 MEMORY_DIR。
        self.memory_store = memory_store or MarkdownMemoryStore()
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

    def _dispatch_flush(self, window, request: _CompactionRequest) -> None:
        """把 flush_memories 甩到独立 daemon 线程执行，**绝不阻塞压缩**。

        压缩是后台任务，而 flush 依赖模型（Ollama 不可达时 ``classify_memory_intent``
        可能重试数十秒）。若同步等待，压缩段写入会被拖住。这里只做 dispatch：
        - 线程 daemon，进程退出不阻塞；
        - flush 内部自带 ``COMPACTION_FLUSH_TIMEOUT`` 限时 + 全量 fail-open；
        - dispatch 本身异常也吞掉（压缩优先级更高）。
        """
        if not FLUSH_MEMORIES_ENABLED:
            return
        snapshot = list(window)

        def _flush():
            with contextlib.suppress(Exception):
                flush_memories(
                    snapshot,
                    project_id=request.project_id,
                    owner_id=request.owner_id,
                    store=self.memory_store,
                    repository=self.repository,
                )

        with contextlib.suppress(Exception):
            threading.Thread(target=_flush, name="compaction-flush", daemon=True).start()

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
            # spec-038 P3：压缩前挂载 flush_memories —— 给 Agent 一次把重要信息写入 L1 的机会。
            # 硬约束「flush 失败不得阻断压缩」：抽取链路会调用模型（不可达时可能长时间重试），
            # 因此这里**不阻塞等待** flush 完成，而是交给独立 daemon 线程执行；flush 内部另有
            # COMPACTION_FLUSH_TIMEOUT 限时与全量 fail-open。压缩主流程只做 dispatch，立即继续。
            self._dispatch_flush(window, request)
            summary_text, char_count, est_tokens, content_hash = build_compaction_summary(window, CHAT_SUMMARY_BUDGET_CHARS)
            generator = "llm" if str(COMPACTION_SUMMARY_MODE or "").strip().lower() == "llm" else "rule"
            segments = self.repository.list_conversation_segments(
                request.conversation_id, request.owner_id, request.project_id
            )
            seq = (max((segment.seq for segment in segments), default=0)) + 1
            self.repository.append_conversation_segment(
                request.conversation_id, request.owner_id, request.project_id, seq,
                request.from_message_id, request.to_message_id,
                char_count, est_tokens, content_hash, summary_text,
                generator=generator,
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
