"""Spec027 Research Task 领域层冻结常量。

本模块常量与 tests/test_spec027_runtime_contract.py 模块级常量逐字对齐，
改这里必须先改门禁测试（Task03+ 实现层只引用、不得自行扩展范围）。
"""

from __future__ import annotations

# 运行时注册的任务类型白名单（Planner 只能生成这五种）。
TASK_TYPE_WHITELIST = frozenset(
    {
        "search_catalog",
        "evaluate_papers",
        "check_coverage",
        "replan",
        "synthesize_preliminary_report",
    }
)

# 产品逻辑角色白名单（实例数与依赖由计划动态产生）。
ROLE_WHITELIST = frozenset(
    {
        "planner",
        "search-worker",
        "paper-evaluator",
        "research-critic",
        "synthesizer",
    }
)

# 稳定错误码词表（前端按 code 映射文案，不暴露内部细节）。
ERROR_CODES = frozenset(
    {
        "PLAN_VALIDATION_FAILED",
        "UNKNOWN_TASK_TYPE",
        "CYCLIC_DEPENDENCY",
        "BUDGET_EXCEEDED",
        "SOURCE_DEGRADED",
        "SOURCE_UNAVAILABLE",
        "MODEL_ESCALATED",
        "RESOURCE_PROBE_FAILED",
        "TASK_NOT_FOUND",
        "TASK_TERMINAL_CONFLICT",
        "TASK_RUNNING_CONFLICT",
        "INVALID_STATE_TRANSITION",
        "REPORT_NOT_READY",
    }
)

# 硬预算（Spec027 §Planner、Critic 与停止合同）。
BUDGET_CAPS = {
    "max_search_items": 12,  # 总搜索 WorkItem 最多 12 个
    "max_candidates": 100,  # 候选评估最多 100 篇
    "max_selected": 20,  # 最终入选最多 20 篇
    "max_replan_rounds": 2,  # 首轮 + 最多 2 次 Re-plan
}

# 五种 WorkItem 的冻结 Schema：参数允许列表、必填、依赖、并行性、预算承载字段。
WORKITEM_SCHEMAS = {
    "search_catalog": {
        "role": "search-worker",
        "parallel_allowed": True,
        "allowed_params": {"query", "facets", "sources", "max_results", "language"},
        "required_params": {"query"},
        "depends_on_task_types": [],
        "budget_field": "count",  # 计划内 search_catalog 数量计入 max_search_items
    },
    "evaluate_papers": {
        "role": "paper-evaluator",
        "parallel_allowed": False,
        "allowed_params": {"catalog_paper_ids", "relevance_threshold", "facets"},
        "required_params": {"catalog_paper_ids"},
        "depends_on_task_types": ["search_catalog"],  # fan-in
        "budget_field": "candidate_count",  # 候选篇数计入 max_candidates
    },
    "check_coverage": {
        "role": "research-critic",
        "parallel_allowed": False,
        "allowed_params": {"goal", "selected_paper_ids", "gap_threshold"},
        "required_params": {"goal"},
        "depends_on_task_types": ["evaluate_papers"],
        "budget_field": None,
    },
    "replan": {
        "role": "planner",
        "parallel_allowed": False,
        "allowed_params": {"rationale", "add_search_for_facets"},
        "required_params": {"rationale"},
        "depends_on_task_types": ["check_coverage"],
        "budget_field": None,
    },
    "synthesize_preliminary_report": {
        "role": "synthesizer",
        "parallel_allowed": False,
        "allowed_params": {"goal", "selected_paper_ids", "language", "evidence_level"},
        "required_params": {"goal", "selected_paper_ids"},
        "depends_on_task_types": ["check_coverage"],  # 跳过 replan 时直接合成
        "budget_field": "selected_count",  # 入选篇数计入 max_selected
    },
}

# ResearchTask 状态集合（暂停/恢复 defer 到 Spec028，故不含该态）。
TASK_STATUSES = frozenset(
    {
        "draft",
        "planning",
        "running",
        "waiting_approval",
        "partial",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    }
)

# ResearchTask 状态转移表（终态不得回到 running）。
TASK_TRANSITIONS = {
    "draft": {"planning"},
    "planning": {"running", "cancelled"},
    "running": {"waiting_approval", "partial", "completed", "failed", "cancelled", "interrupted"},
    "waiting_approval": {"running", "completed", "failed", "cancelled", "interrupted", "partial"},
    "partial": set(),
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "interrupted": set(),
}

# ResearchTask 终态集合。
TASK_TERMINAL = frozenset({"partial", "completed", "failed", "cancelled", "interrupted"})

# ResearchWorkItem 状态集合。
WORKITEM_STATUSES = frozenset(
    {"queued", "running", "completed", "failed", "cancelled", "interrupted"}
)

# ResearchWorkItem 状态转移表（终态不得回到 running 或 queued）。
WORKITEM_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "cancelled", "interrupted"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "interrupted": set(),
}

# ResearchWorkItem 终态集合。
WORKITEM_TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})

# ResearchPlan 状态集合。
PLAN_STATUSES = frozenset({"proposed", "active", "superseded", "completed", "rejected"})

# 质量档位：目标篇数与软预算（秒）。
QUALITY_PROFILES = {
    "speed": {"target_paper_count": 8, "soft_budget_seconds": 600},
    "balanced": {"target_paper_count": 12, "soft_budget_seconds": 1500},
    "quality": {"target_paper_count": 20, "soft_budget_seconds": 2700},
}

DEFAULT_TARGET_PAPER_COUNT = 12
TARGET_PAPER_COUNT_RANGE = (1, 20)
GOAL_MIN_CHARS = 1
GOAL_MAX_CHARS = 4000

# ResearchEvent 事件类型白名单。
EVENT_TYPES = frozenset(
    {"task", "plan", "worker", "model", "coverage", "report", "terminal"}
)

# Spec034 session/runtime contracts.  Keep these values in one module so
# stores, services and API adapters cannot silently grow independent enums.
SESSION_STATUSES = frozenset(
    {
        "intake_pending", "plan_generating", "plan_pending_approval", "queued",
        "running", "waiting_approval", "interrupted", "partial", "completed",
        "failed", "cancelled",
    }
)
SESSION_TERMINAL = frozenset({"interrupted", "partial", "completed", "failed", "cancelled"})
SESSION_TRANSITIONS = {
    "intake_pending": {"plan_generating", "cancelled"},
    "plan_generating": {"plan_pending_approval", "cancelled"},
    "plan_pending_approval": {"queued", "intake_pending", "cancelled"},
    "queued": {"running", "cancelled"},
    "running": {"waiting_approval", "partial", "completed", "failed", "cancelled", "interrupted"},
    "waiting_approval": {"running", "cancelled"},
    "interrupted": set(), "partial": set(), "completed": set(), "failed": set(), "cancelled": set(),
}

INTAKE_STATUSES = frozenset({"collecting", "complete", "superseded", "cancelled"})
INTAKE_TRANSITIONS = {
    "collecting": {"complete", "cancelled"},
    "complete": {"superseded", "cancelled"},
    "superseded": set(), "cancelled": set(),
}
INTAKE_FIELDS = frozenset({"topic", "objective", "time_range", "language", "sources", "depth", "output", "citations", "constraints"})
INTAKE_SOURCES = frozenset({"user_explicit", "context_inferred", "system_default"})
INTAKE_CONFIRMATION_STATUSES = frozenset({"unconfirmed", "confirmed", "not_required"})

APPROVAL_KINDS = frozenset({"plan", "capability_override", "resource_extension"})
APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected", "cancelled", "superseded"})
APPROVAL_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled", "superseded"},
    "approved": set(), "rejected": set(), "cancelled": set(), "superseded": set(),
}
AGENT_ROLES = frozenset({"planner", "search_worker", "paper_evaluator", "research_critic", "synthesizer"})
AGENT_RUN_STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled", "interrupted", "limit_reached"})
AGENT_RUN_TRANSITIONS = {
    "queued": {"running"},
    "running": {"completed", "failed", "cancelled", "interrupted", "limit_reached"},
    "completed": set(), "failed": set(), "cancelled": set(), "interrupted": set(), "limit_reached": set(),
}
ARTIFACT_TYPES = frozenset({"markdown", "html", "citation_manifest", "intermediate"})
NOTIFICATION_KINDS = frozenset({"completed", "partial", "failed", "waiting_approval", "interrupted"})
NOTIFICATION_STATUSES = frozenset({"unread", "read"})
PROCESSING_NODE_TYPES = frozenset({"phase", "agent", "skill", "tool", "operation"})

# Verbose aliases are part of the Task02 public contract.
RESEARCH_SESSION_STATUSES = SESSION_STATUSES
RESEARCH_SESSION_TERMINAL = SESSION_TERMINAL
RESEARCH_INTAKE_STATUSES = INTAKE_STATUSES
APPROVAL_REQUEST_STATUSES = APPROVAL_STATUSES
AGENT_RUN_STATUSES_V2 = AGENT_RUN_STATUSES

RESEARCH_SESSION_ERROR_CODES = frozenset(
    {
        "RESEARCH_SESSION_NOT_FOUND", "RESEARCH_SESSION_ACTIVE_CONFLICT", "INTAKE_INCOMPLETE",
        "PLAN_VERSION_STALE", "APPROVAL_STALE", "APPROVAL_CONFLICT", "SKILL_DISABLED",
        "CAPABILITY_NOT_AUTHORIZED", "AGENT_OUTPUT_INVALID", "MODEL_LOOP_LIMIT_REACHED",
        "TOOL_CALL_LIMIT_REACHED", "TASK_MODEL_LIMIT_REACHED", "TASK_TIME_LIMIT_REACHED",
        "TRACE_PROJECTION_FAILED", "ARTIFACT_NOT_READY", "MODEL_UNAVAILABLE",
    }
)

# 证据等级（全集）。
EVIDENCE_LEVELS = frozenset({"catalog", "abstract", "fulltext"})

# Spec027 只产生前两种证据（不下载/分析全文）。
SPEC027_EVIDENCE_LEVELS = frozenset({"catalog", "abstract"})

# 资源探针至少保留的系统余量。
RESOURCE_MARGIN_FRACTION = 0.20

# 规范化的研究子主题（facets）上限。
MAX_FACETS = 8
