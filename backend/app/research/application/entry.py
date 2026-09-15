"""Research 限界上下文的**唯一受控应用出口**（Spec027 Task03 第 4 批）。

静态边界规则禁止 `api` 直连任何上下文的 `infrastructure`，但 `api` 的组合装配
（构造 store、检索适配器、资源探针、模型路由、Planner、编排器与服务）确实需要一
批基础设施符号。本模块即这些符号的**唯一受控出口**：`api` 一律从本模块导入，
不得再直接 import `research.infrastructure.*`。

与 `paper_discovery/application/entry.py`、知识库侧保持一致：导出集中在显式
`__all__`，便于审计与逐步收窄。本模块**只做导入与工厂，不新增业务逻辑**：
- 工厂一律模块级缓存（`functools.lru_cache`），且**不在模块顶层实例化**——
  import 本模块既不创建 SQLite 文件，也不发起任何网络请求；
- `CatalogSearchAdapter()` 的 Spec015 真实数据源由 `CatalogSourceFactory` 在**首次检索时**惰性装配
  （见其 docstring），故此处不会创建目录库或发起网络请求。
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.platform.bootstrap import get_provider
from backend.app.platform.config import BASE_DIR, KB_DIR
from backend.app.platform.ollama import ResourceProbe
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRunOutput,
    AgentRuntimeError,
    BudgetSnapshot,
    FakeModel,
    FakeTool,
    ResearchAgentRunner,
    RoleCapability,
    RoleCapabilityRegistry,
)
from backend.app.research.application.acquisition import (
    ResearchAcquisitionError,
    ResearchAcquisitionService,
)
from backend.app.research.application.model_router import ModelRouter
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.plan_authoring import (
    RESEARCH_PLAN_OUTPUT_SCHEMA,
    ResearchPlanOutput,
    validate_research_plan_output,
)
from backend.app.research.application.planner import Planner
from backend.app.research.application.processing_projector import ProcessingStepProjector
from backend.app.research.application.report_synthesis import (
    REPORT_SYNTHESIS_OUTPUT_SCHEMA,
    ReportDeliveryService,
    ReportSynthesisError,
    ReportSynthesisOutput,
    ReportSynthesizer,
    ResearchNotificationService,
    SynthesisResult,
    render_markdown_html,
    validate_report_synthesis_output,
)
from backend.app.research.application.research_service import (
    ResearchService,
    ResearchServiceError,
)
from backend.app.research.application.search_catalog_adapter import (
    CatalogSearchAdapter,
    CatalogSourceBundle,
    CatalogSourceFactory,
    CoverageCritic,
    PaperEvaluator,
    SearchWorker,
    map_catalog_tool_args,
    map_detail_tool_args,
    map_download_tool_args,
)
from backend.app.research.domain.models import (
    AcquisitionApproval,
    AcquisitionEvent,
    EvidenceUpgrade,
    PreliminaryReport,
    ResearchDocumentLink,
    ResearchEvent,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchSessionPlan,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import (
    ResearchStore,
    default_database_path,
)
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.service import SkillRegistryService
from backend.app.skills.tool_service import ToolRegistryService

__all__ = [
    # 持久化（唯一受控出口，api 不得直连 research.infrastructure）
    "ResearchStore",
    "ResearchAcquisitionError",
    "ResearchAcquisitionService",
    # 服务层与稳定错误
    "ResearchService",
    "ResearchServiceError",
    # 应用层协作对象
    "Planner",
    "ResearchPlanOutput",
    "RESEARCH_PLAN_OUTPUT_SCHEMA",
    "validate_research_plan_output",
    "Orchestrator",
    "CatalogSearchAdapter",
    "CatalogSourceBundle",
    "CatalogSourceFactory",
    "SearchWorker",
    "PaperEvaluator",
    "CoverageCritic",
    "map_catalog_tool_args",
    "map_detail_tool_args",
    "map_download_tool_args",
    "AgentRunInput",
    "AgentRunOutput",
    "AgentRuntimeError",
    "BudgetSnapshot",
    "FakeModel",
    "FakeTool",
    "ResearchAgentRunner",
    "ProcessingStepProjector",
    "REPORT_SYNTHESIS_OUTPUT_SCHEMA",
    "ReportSynthesisOutput",
    "ReportSynthesisError",
    "ReportSynthesizer",
    "ReportDeliveryService",
    "ResearchNotificationService",
    "SynthesisResult",
    "render_markdown_html",
    "validate_report_synthesis_output",
    "RoleCapability",
    "RoleCapabilityRegistry",
    # 领域实体（api 只做序列化，不新增语义）
    "ResearchTask",
    "ResearchPlan",
    "ResearchSessionPlan",
    "ResearchWorkItem",
    "ResearchEvent",
    "ResearchPaperSelection",
    "PreliminaryReport",
    "AcquisitionApproval",
    "ResearchDocumentLink",
    "EvidenceUpgrade",
    "AcquisitionEvent",
    # 工厂
    "build_research_store",
    "build_research_service",
]


@lru_cache(maxsize=1)
def build_research_store() -> ResearchStore:
    """构造（并缓存）ResearchStore；库路径由 `RESEARCH_DB_PATH` 环境变量决定。

    路径解析复用 `research_store.default_database_path()`：环境变量优先，否则
    `BASE_DIR/data/research/research.sqlite3`（独立库，整体删除即回滚，不动 Spec015/022）。
    """
    return ResearchStore(database_path=default_database_path())


@lru_cache(maxsize=1)
def build_research_service() -> ResearchService:
    """构造（并缓存）ResearchService：装配 store、检索适配器、探针、路由与 Planner。

    检索未传 source：`CatalogSearchAdapter` 会在首次 `search()` 时由
    `CatalogSourceFactory` 惰性装配 Spec015 数据源，因此这里不会创建目录库或发起网络请求。
    """
    store = build_research_store()
    try:
        memory_repository = get_provider("memory_repository")
    except KeyError:
        from backend.app.memory.repository import MemoryRepository

        memory_repository = MemoryRepository()
    processing_projector = ProcessingStepProjector(store, memory_repository)
    probe = ResourceProbe()
    router = ModelRouter()
    state_path = KB_DIR / "skill-state.json"
    skill_registry = SkillRegistryService(BASE_DIR / ".agents" / "skills", state_path)
    tool_registry = ToolRegistryService(build_default_tool_registry(), state_path)
    return ResearchService(
        store=store,
        search_adapter=CatalogSearchAdapter(),
        probe=probe,
        model_router=router,
        agent_runner=ResearchAgentRunner(
            store=store,
            model_router=router,
            resource_probe=probe,
            capability_registry=RoleCapabilityRegistry(
                skill_registry=skill_registry, tool_registry=tool_registry
            ),
        ),
        planner=Planner(),
        memory_repository=memory_repository,
        processing_projector=processing_projector,
    )
