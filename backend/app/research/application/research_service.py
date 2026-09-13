"""Spec027 Research Task 应用服务层（Task03 第 4 批）。

职责边界（分层：api -> application -> infrastructure/store）：
- 本层是 Spec027 业务规则的**唯一入口**：api 只做 HTTP 语义与参数解析，输入归一、
  状态冲突判定、计划版本追加、后台启动与取消收尾一律落在这里。
- 数据访问只经 ``ResearchStore``，不写 SQL、不直连 ``research.infrastructure``；
  ``owner_id`` 一律由调用方传入，**不 import** ``backend.app.memory.repository``
  （沿用既有单 OWNER_ID 隔离范式，不引入新鉴权）。
- 后台执行只用本服务持有的 ``ThreadPoolExecutor``：不引入 Celery / asyncio 任务框架。
  页面关闭不取消任务，只有显式 ``cancel`` 才停止新节点；已在跑的节点由编排器在下一
  阶段读到终态后自行收尾（Spec027 §端点与事件接口）。

错误一律抛 ``ResearchServiceError(code, http_status, message)``，code 取自
``contracts.ERROR_CODES`` 稳定词表，供前端按码映射文案、不暴露内部细节。
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timezone

from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.planner import Planner
from backend.app.research.application.processing_projector import ProcessingStepProjector
from backend.app.research.domain.contracts import (
    ERROR_CODES,
    GOAL_MAX_CHARS,
    GOAL_MIN_CHARS,
    QUALITY_PROFILES,
    TARGET_PAPER_COUNT_RANGE,
    TASK_TERMINAL,
)
from backend.app.research.domain.models import (
    PreliminaryReport,
    ResearchEvent,
    ResearchPlan,
    ResearchTask,
)
from backend.app.research.domain.plan_validator import PlanRejected
from backend.app.research.domain.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)

# 视为「运行中」的状态：禁止移动项目、禁止删除、禁止补充范围（Spec027 §端点与事件接口）。
_RUNNING_LIKE = frozenset({"running", "planning"})

# 取消时需要一并收敛的 WorkItem 状态（queued -> cancelled 与 running -> cancelled 均合法，
# 已终态的跳过，终态不得回到 running/queued）。
_CANCELLABLE_ITEM_STATUSES = frozenset({"queued", "running"})

# draft 事件的 goal 摘要截断长度（安全 payload 不放大段原文）。
_GOAL_EXCERPT_CHARS = 120

# 后台线程池默认并发（文件 2 细则：max_workers=2，两个 Task 可同时推进）。
_DEFAULT_EXECUTOR_WORKERS = 2


def _utcnow() -> str:
    """当前 UTC 时间戳，格式与 research_store._utcnow 一致：`YYYY-MM-DDTHH:MM:SSZ`。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# 模块级 in-flight 集合：防止同一 task 被重复启动（进程内去重，不替代 DB 状态机）。
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: set[str] = set()


class ResearchServiceError(Exception):
    """服务层稳定错误：code 必须来自 ``contracts.ERROR_CODES``。"""

    def __init__(self, code: str, http_status: int = 400, message: str = ""):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown research error code: {code}")
        self.code = code
        self.http_status = int(http_status)
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)


class ResearchService:
    """Research Task 应用服务：创建/查询/反馈/取消/移动/删除与启动审计。"""

    def __init__(
        self,
        *,
        store,
        search_adapter=None,
        planner=None,
        probe=None,
        model_router=None,
        orchestrator=None,
        agent_runner=None,
        memory_repository=None,
        processing_projector: ProcessingStepProjector | None = None,
        executor=None,
    ) -> None:
        self._store = store
        # 检索出口由编排器持有；None 时编排器走 Spec015 CatalogSearchAdapter 惰性装配。
        self._search_adapter = search_adapter
        self._planner = planner or Planner()
        self._probe = probe
        self._model_router = model_router
        self._agent_runner = agent_runner
        self._processing_projector = processing_projector or (
            ProcessingStepProjector(store, memory_repository)
            if memory_repository is not None else None
        )
        # 编排器惰性构造：__init__ 不打网络（ResourceProbe 只在 arbitrate 时才读 Ollama）。
        self._orchestrator_instance = orchestrator
        self._executor = executor or ThreadPoolExecutor(
            max_workers=_DEFAULT_EXECUTOR_WORKERS, thread_name_prefix="research-task"
        )

    # ------------------------------------------------------------------ #
    # 创建与启动
    # ------------------------------------------------------------------ #

    def create_task(
        self,
        *,
        owner_id: str,
        goal: str,
        conversation_id: str,
        project_id: str | None = None,
        quality_profile: str = "balanced",
        target_paper_count: int | None = None,
        language: str = "zh",
        review_plan_first: bool = False,
    ) -> ResearchTask:
        """创建研究任务：draft 落库并发 draft 事件；随后按 review_plan_first 分流。

        - ``review_plan_first`` 为真：预建计划 v1（status=proposed）→ planning →
          waiting_approval，**不启动编排**，等 ``feedback(action="approve")`` 批准；
        - 否则：planning → 后台启动编排（返回的任务状态为 planning，后续由事件流推进）。

        非法输入（goal 长度、未知档位、篇数）一律 ``PLAN_VALIDATION_FAILED`` 400。

        契约（Spec027 §端点与事件接口 / §产品边界）：``project_id`` 的**存在性与归属校验**
        以及「未传则从会话继承项目」由调用方（api 层）完成后传入；本层只负责落库，
        因此不需要 import ``backend.app.memory.repository``（保持第 7-8 行分层约束）。
        """
        clean_goal = unicodedata.normalize("NFC", goal or "").strip()
        if not (GOAL_MIN_CHARS <= len(clean_goal) <= GOAL_MAX_CHARS):
            raise ResearchServiceError(
                "PLAN_VALIDATION_FAILED", 400, f"goal 长度需落在 {GOAL_MIN_CHARS}..{GOAL_MAX_CHARS} 个 Unicode 字符"
            )
        if quality_profile not in QUALITY_PROFILES:
            raise ResearchServiceError("PLAN_VALIDATION_FAILED", 400, f"未知质量档位 {quality_profile!r}")
        target = self._normalize_target_paper_count(target_paper_count, quality_profile)

        now = _utcnow()
        task = ResearchTask(
            research_task_id=uuid.uuid4().hex,
            owner_id=owner_id,
            project_id=project_id,
            conversation_id=conversation_id,
            goal=clean_goal,
            language=language or "zh",
            quality_profile=quality_profile,
            review_plan_first=bool(review_plan_first),
            target_paper_count=target,
            soft_budget_seconds=QUALITY_PROFILES[quality_profile]["soft_budget_seconds"],
            status="draft",
            current_plan_version=1,
            created_at=now,
            updated_at=now,
        )
        created = self._store.create_task(task)
        self._store.append_event(
            created.research_task_id,
            "task",
            {
                "status": "draft",
                "goal_excerpt": clean_goal[:_GOAL_EXCERPT_CHARS],
                "quality_profile": quality_profile,
                "target_paper_count": target,
                "review_plan_first": bool(review_plan_first),
            },
        )
        if review_plan_first:
            return self._prebuild_plan_and_wait(created, owner_id)
        planning = self._store.update_task_status(created.research_task_id, owner_id, "planning")
        self.start(created.research_task_id, owner_id)
        return planning

    def start(self, research_task_id: str, owner_id: str) -> bool:
        """后台启动编排；已在 in-flight 的任务返回 False（不重复启动），否则 True。

        后台线程内的异常不伪造成功：emit ``terminal`` 事件（status=interrupted）并尝试把
        任务置为 interrupted；状态机若拒绝（如已被取消/已终态）则忽略，终态绝不回到 running。
        """
        with _INFLIGHT_LOCK:
            if research_task_id in _INFLIGHT:
                return False
            _INFLIGHT.add(research_task_id)
        try:
            # A restart or idle period can leave a cross-database projection
            # marker without a new ResearchEvent.  One bounded pass here lets
            # the normal background lifecycle recover it without polling.
            self.drain_processing_projection_retries(research_task_id, owner_id)
            self._executor.submit(self._run_orchestration, research_task_id, owner_id)
        except Exception:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(research_task_id)
            raise
        return True

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get_task(self, research_task_id: str, owner_id: str) -> ResearchTask:
        """按 owner 读取任务；不存在（或不属于该 owner）抛 TASK_NOT_FOUND 404。"""
        task = self._store.get_task(research_task_id, owner_id)
        if task is None:
            raise ResearchServiceError("TASK_NOT_FOUND", 404, f"research task not found: {research_task_id}")
        return task

    def list_tasks(
        self,
        owner_id: str,
        *,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[ResearchTask], str | None]:
        """keyset 分页列出任务（委托 store）；非法游标由 store 抛 ValueError，api 层转 400。"""
        return self._store.list_tasks(owner_id, project_id=project_id, status=status, limit=limit, cursor=cursor)

    def list_events(
        self, research_task_id: str, owner_id: str, *, after_seq: int = 0, limit: int = 200
    ) -> list[ResearchEvent]:
        """列出事件（先校验归属）：不存在/不属于该 owner 抛 TASK_NOT_FOUND 404。"""
        self.get_task(research_task_id, owner_id)
        return self._store.list_events(research_task_id, after_seq=after_seq, limit=limit)

    def project_event_for_sse(self, event: ResearchEvent, owner_id: str) -> dict | None:
        """Project one durable event and return its incremental upsert envelope."""
        if self._processing_projector is None:
            return None
        session = self._store.get_session_by_task(event.research_task_id, owner_id)
        if session is None or not session.activity_message_id:
            return None
        try:
            step = self._processing_projector.project_event(
                session.activity_message_id,
                owner_id,
                event,
                research_session_id=session.research_session_id,
            )
        except Exception as exc:
            with suppress(Exception):
                self._store.mark_projection_retry(event.research_task_id, event.event_seq, str(exc))
            raise
        return self._processing_projector.as_sse_upsert(step)

    def drain_processing_projection_retries(self, research_task_id: str, owner_id: str) -> int:
        """Perform one bounded retry pass for a task's pending projections."""
        if self._processing_projector is None:
            return 0
        session = self._store.get_session_by_task(research_task_id, owner_id)
        if session is None or not session.activity_message_id:
            return 0
        try:
            return self._processing_projector.drain_pending(
                research_task_id, session.activity_message_id, owner_id,
                research_session_id=session.research_session_id,
            )
        except Exception:
            return 0

    def get_report(
        self, research_task_id: str, owner_id: str, *, plan_version: int | None = None
    ) -> PreliminaryReport:
        """读取报告（先校验归属）；plan_version 为 None 取最大版本；未生成抛 REPORT_NOT_READY 409。"""
        self.get_task(research_task_id, owner_id)
        report = self._store.get_report(research_task_id, plan_version)
        if report is None:
            raise ResearchServiceError("REPORT_NOT_READY", 409, f"report not ready: {research_task_id}")
        return report

    # ------------------------------------------------------------------ #
    # 取消 / 反馈 / 移动 / 删除
    # ------------------------------------------------------------------ #

    def cancel(self, research_task_id: str, owner_id: str) -> ResearchTask:
        """取消任务：任务置 cancelled，并把 queued/running 的 WorkItem 一并置 cancelled。

        语义（Spec027 §端点与事件接口）：页面关闭**不**取消任务，只有显式 cancel 才停止
        新增节点；已在跑的节点不强行杀死，由编排器下一阶段读到终态后自行收尾。已终态任务
        重复取消抛 TASK_TERMINAL_CONFLICT 409。
        """
        task = self.get_task(research_task_id, owner_id)
        if task.status in TASK_TERMINAL:
            raise ResearchServiceError("TASK_TERMINAL_CONFLICT", 409, f"task already terminal: {task.status}")
        try:
            updated = self._store.update_task_status(research_task_id, owner_id, "cancelled")
        except InvalidStateTransition as exc:
            raise ResearchServiceError("INVALID_STATE_TRANSITION", 409, f"{task.status} -> cancelled 非法") from exc
        for item in self._store.list_work_items(research_task_id):
            if item.status not in _CANCELLABLE_ITEM_STATUSES:
                continue
            # 并发下编排器可能刚把它推进到终态：转移非法就跳过，不覆盖既有终态。
            with suppress(InvalidStateTransition):
                self._store.update_work_item_status(item.work_item_id, "cancelled")
        self._store.append_event(research_task_id, "task", {"status": "cancelled"})
        self._store.append_event(research_task_id, "terminal", {"status": "cancelled"})
        return updated

    def feedback(
        self, research_task_id: str, owner_id: str, *, action: str | None = None, add_scope: str | None = None
    ) -> ResearchTask:
        """计划批准（``action="approve"``）或补充范围（追加新计划版本，不覆盖既有计划/证据）。

        - approve：仅 ``waiting_approval`` 可批准，转 running 并后台启动；否则
          INVALID_STATE_TRANSITION 409；
        - 补充范围：running/planning 抛 TASK_RUNNING_CONFLICT 409，终态抛
          TASK_TERMINAL_CONFLICT 409，其余状态追加 ``current_plan_version + 1``
          （status=proposed），继承上一版本 facets，不启动编排。
        """
        task = self.get_task(research_task_id, owner_id)
        if action == "approve":
            if task.status != "waiting_approval":
                raise ResearchServiceError(
                    "INVALID_STATE_TRANSITION", 409, f"approve 需要 waiting_approval，当前 {task.status}"
                )
            running = self._store.update_task_status(research_task_id, owner_id, "running")
            self._store.append_event(research_task_id, "task", {"status": "running", "reason": "plan_approved"})
            self.start(research_task_id, owner_id)
            return running

        scope = unicodedata.normalize("NFC", add_scope or "").strip()
        if not scope:
            raise ResearchServiceError("PLAN_VALIDATION_FAILED", 400, "feedback 需要 action 或非空 add_scope")
        if task.status in _RUNNING_LIKE:
            raise ResearchServiceError("TASK_RUNNING_CONFLICT", 409, f"task is {task.status}，无法补充范围")
        if task.status in TASK_TERMINAL:
            raise ResearchServiceError("TASK_TERMINAL_CONFLICT", 409, f"task already terminal: {task.status}")

        version = int(task.current_plan_version) + 1
        previous = self._store.get_current_plan(research_task_id)
        facets = self._parse_facets(previous.facets_json) if previous is not None else ()
        plan = ResearchPlan(
            research_task_id=research_task_id,
            version=version,
            planner_model=None,
            rationale_summary=f"补充研究范围：{scope}",
            facets_json=json.dumps(list(facets), ensure_ascii=False),
            status="proposed",
            created_at=_utcnow(),
        )
        self._store.create_plan(plan)
        updated = self._store.update_task(research_task_id, owner_id, current_plan_version=version)
        self._store.append_event(
            research_task_id,
            "plan",
            {"plan_version": version, "status": "proposed", "add_scope": scope},
        )
        return updated

    def patch_project(self, research_task_id: str, owner_id: str, project_id: str | None) -> ResearchTask:
        """移动/解绑项目归属；``project_id`` 为 None 表示解绑。running/planning 禁止移动。"""
        task = self.get_task(research_task_id, owner_id)
        if task.status in _RUNNING_LIKE:
            raise ResearchServiceError("TASK_RUNNING_CONFLICT", 409, f"task is {task.status}，禁止移动项目")
        updated = self._store.update_task(research_task_id, owner_id, project_id=project_id)
        self._store.append_event(research_task_id, "task", {"project_id": project_id})
        return updated

    def delete_task(self, research_task_id: str, owner_id: str) -> bool:
        """删除任务**私有数据**（计划/WorkItem/选集/报告/事件），不删 Spec015 目录与知识库。

        running/planning 禁止删除（TASK_RUNNING_CONFLICT 409）。
        """
        task = self.get_task(research_task_id, owner_id)
        if task.status in _RUNNING_LIKE:
            raise ResearchServiceError("TASK_RUNNING_CONFLICT", 409, f"task is {task.status}，禁止删除")
        return self._store.delete_task(research_task_id, owner_id)

    def delete_tasks_for_project(self, project_id: str, owner_id: str) -> int:
        """项目删除时级联删除该 owner 在该项目下的全部 Research Task 及其私有数据。

        Spec027 §持久化与并发：级联删除走应用层，不依赖 DB 外键 CASCADE（外键为 RESTRICT）。
        与 `delete_task` 的区别：这里**不做 running/planning 冲突拦截**——项目已被删除，
        遗留任务必须一并清理；store 在单事务内按子表→主表顺序删除，失败即整体回滚并向上抛。
        `project_id IS NULL` 的未绑定任务、其它项目/其它 owner 的任务均不受影响。
        """
        return self._store.delete_tasks_by_project(project_id, owner_id)

    # ------------------------------------------------------------------ #
    # 启动审计
    # ------------------------------------------------------------------ #

    def recover_interrupted(self) -> int:
        """Spec027 自有启动审计：把遗留 running 的 Task/WorkItem 收敛为 interrupted，返回收敛数。

        **刻意区别于 Spec015 ``reset_running_jobs`` 的 running→queued 重试语义**：027 崩溃后
        不重试（自动续跑/租约属 Spec028），直接收敛为终态 interrupted。
        """
        return self._store.mark_running_interrupted()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _orchestrator(self) -> Orchestrator:
        """惰性构造编排器（首次使用时才装配，不在 __init__ 打网络）。"""
        if self._orchestrator_instance is None:
            self._orchestrator_instance = Orchestrator(
                store=self._store,
                search_adapter=self._search_adapter,
                planner=self._planner,
                probe=self._probe,
                model_router=self._model_router,
                agent_runner=self._agent_runner,
                processing_projector=self._processing_projector,
            )
        return self._orchestrator_instance

    def _run_orchestration(self, research_task_id: str, owner_id: str) -> None:
        """线程池内的编排包装：兜住所有异常，落 interrupted 事件后从 in-flight 移除。

        原始异常**只落服务端日志**（含堆栈，供排障）；事件 payload 是经 SSE 原样推给前端的
        安全 payload，因此只写稳定错误码，绝不写 ``str(exc)``——后者可能带文件路径、SQL 片段
        或内部标识符（Spec027 §端点与事件接口：安全 payload 是白名单）。
        """
        try:
            self.drain_processing_projection_retries(research_task_id, owner_id)
            self._orchestrator().run(research_task_id, owner_id)
        except Exception:
            # 不伪造成功：先记日志再落事件（测试据「事件已落库」断言日志已发出）；状态机拒绝则忽略。
            logger.exception("research orchestration crashed: task=%s", research_task_id)
            with suppress(Exception):
                self._store.append_event(
                    research_task_id,
                    "terminal",
                    {
                        "status": "interrupted",
                        "reason": "orchestrator_crashed",
                        # 服务内部故障的**稳定码**（不是 027 冻结 13 码词表的成员，也不由
                        # `ResearchServiceError` 抛出，故不违反其 code 校验）；前端按
                        # 「未知码 -> 通用失败文案」兜底。原始异常文本不进事件。
                        "error_code": "INTERNAL_ERROR",
                    },
                )
            with suppress(InvalidStateTransition):
                self._store.update_task_status(research_task_id, owner_id, "interrupted")
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(research_task_id)

    def _prebuild_plan_and_wait(self, task: ResearchTask, owner_id: str) -> ResearchTask:
        """review_plan_first：预建计划 v1（proposed）→ planning → running → waiting_approval。

        状态链必须经 running：冻结的 ``TASK_TRANSITIONS`` 里 ``planning`` 只能到 ``running``，
        ``waiting_approval`` 也只能从 ``running`` 进入（contracts 与门禁测试对齐，不得改动）。
        语义不变——进入 waiting_approval 前**不启动编排、不产出任何 WorkItem 结果**，
        等 ``feedback(action="approve")`` 批准后才真正执行。
        """
        draft = self._build_plan_draft(task)
        self._store.create_plan(
            ResearchPlan(
                research_task_id=task.research_task_id,
                version=1,
                planner_model=draft.planner_model,
                rationale_summary=draft.rationale_summary,
                facets_json=json.dumps(list(draft.facets), ensure_ascii=False),
                status="proposed",
                created_at=_utcnow(),
            )
        )
        self._store.update_task_status(task.research_task_id, owner_id, "planning")
        self._store.append_event(task.research_task_id, "task", {"status": "planning"})
        self._store.update_task_status(task.research_task_id, owner_id, "running")
        self._store.append_event(task.research_task_id, "task", {"status": "running"})
        waiting = self._store.update_task_status(task.research_task_id, owner_id, "waiting_approval")
        self._store.append_event(
            task.research_task_id,
            "plan",
            {"plan_version": 1, "status": "proposed", "facets": list(draft.facets)},
        )
        self._store.append_event(task.research_task_id, "task", {"status": "waiting_approval"})
        return waiting

    def _build_plan_draft(self, task: ResearchTask):
        """调 Planner 生成受校验计划草稿；校验失败转 PLAN_VALIDATION_FAILED 400。"""
        try:
            return self._planner.build_plan(
                goal=task.goal,
                quality_profile=task.quality_profile,
                target_paper_count=task.target_paper_count,
                language=task.language,
            )
        except PlanRejected as exc:
            raise ResearchServiceError("PLAN_VALIDATION_FAILED", 400, str(exc)) from exc

    @staticmethod
    def _normalize_target_paper_count(target_paper_count: int | None, quality_profile: str) -> int:
        """篇数缺省取档位默认，再夹到 ``TARGET_PAPER_COUNT_RANGE``；非整数报 PLAN_VALIDATION_FAILED。"""
        if target_paper_count is None:
            return int(QUALITY_PROFILES[quality_profile]["target_paper_count"])
        try:
            value = int(target_paper_count)
        except (TypeError, ValueError) as exc:
            raise ResearchServiceError("PLAN_VALIDATION_FAILED", 400, "target_paper_count 必须是整数") from exc
        low, high = TARGET_PAPER_COUNT_RANGE
        return max(low, min(value, high))

    @staticmethod
    def _parse_facets(raw: str) -> tuple[str, ...]:
        """解析计划 facets_json；空值/非法 JSON/非 list 均返回空元组，不抛异常。"""
        if not raw:
            return ()
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if not isinstance(value, list):
            return ()
        return tuple(str(item) for item in value)
