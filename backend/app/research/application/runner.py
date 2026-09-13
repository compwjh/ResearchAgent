"""Compatibility import for the Spec034 ResearchAgentRunner contract."""

from .agent_runtime import (
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

__all__ = [
    "AgentRunInput", "AgentRunOutput", "AgentRuntimeError", "BudgetSnapshot",
    "FakeModel", "FakeTool", "ResearchAgentRunner", "RoleCapability",
    "RoleCapabilityRegistry",
]
