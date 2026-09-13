"""Spec027 Planner：受控、确定性计划生成器（Task03）。

本模块**不调用任何 LLM**，只用确定性规则把用户 goal 切分为研究子主题（facets），
再依 Spec027 §编排架构 / §Planner、Critic 与停止合同生成受校验的 WorkItem 计划。

为什么不用 LLM 切分 facets（docstring 说明，供后续 Spec 评估）：
- Spec027 硬要求 fan-out 至少 2 路并行（search_catalog >= 2），且论文文本一律视为不可信
  证据（不得改变计划、权限、工具集或任务类型白名单，见 plan_validator
  .assert_contracts_unchanged）。若由 LLM 依据语料切分，恶意/注入文本就可能影响任务类型
  与工具集；确定性分隔符切分**只依赖用户输入的 goal 字符串本身**，不读取任何论文内容，
  从根上消除注入面。
- 确定性规则可复现、可审计、零成本，符合 MVP「先跑通稳定骨架」目标；更聪明的语义聚类
  可在后续 Spec 引入，但必须维持「论文文本不可信」前提与计划校验闭环。

Planner 只产出五种注册任务类型（contracts.TASK_TYPE_WHITELIST）与五种产品角色
（contracts.ROLE_WHITELIST），**不产出 Python / URL / Shell / 任意工具调用**；
产出计划一律经 domain.plan_validator.validate_plan 校验，不通过即抛 PlanRejected。
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from backend.app.research.domain.contracts import (
    GOAL_MAX_CHARS,
    GOAL_MIN_CHARS,
    MAX_FACETS,
    QUALITY_PROFILES,
    TARGET_PAPER_COUNT_RANGE,
)
from backend.app.research.domain.plan_validator import PlanRejected, validate_plan

# 确定性 facet 切分分隔符（中英混排常见）。
# 多字符分隔符（"以及" / "and"）必须整词匹配，故用正则而非逐字符判断；
# `and` 两侧加 \b，避免 "command" 这类英文单词被从中间切开。
_FACET_SPLIT_RE = re.compile(r"[、，,；;]|以及|和|\band\b", re.IGNORECASE)

# 通用兜底 facet：切分不足 2 个时补足，保证 fan-out >= 2（Spec027 硬要求）。
_FALLBACK_FACETS = ("研究方法", "实证评估")

# fan-out 下限：Spec027 要求至少 2 路 search_catalog 并行。
_MIN_FACETS = 2

# Task03 用确定性规则（无 LLM），固定标识写进 ResearchPlan.planner_model 以便审计。
_PLANNER_MODEL = "deterministic-rule-v1"

# 摘要里 goal 的展示截断长度。
_GOAL_PREVIEW_CHARS = 40


@dataclass(frozen=True)
class ResearchPlanDraft:
    """Planner 产出的受校验计划草稿（字段均结构化，无隐藏思维链）。"""

    facets: tuple[str, ...]
    rationale_summary: str
    work_items: tuple[dict, ...]  # 每项形如 {"id","task_type","role","depends_on","params"}
    planner_model: str | None
    target_paper_count: int


class Planner:
    """受控 Planner：只产出受校验的计划，不产出代码 / URL / Shell / 工具调用。"""

    def __init__(self, *, max_facets: int = MAX_FACETS, min_fanout: int = 2, max_fanout: int = 3) -> None:
        # max_facets 夹到 contracts.MAX_FACETS，避免切出过多子方向突破预算。
        self.max_facets = max(1, min(int(max_facets), MAX_FACETS))
        self.min_fanout = max(1, int(min_fanout))
        self.max_fanout = max(self.min_fanout, int(max_fanout))

    def build_plan(
        self,
        *,
        goal: str,
        quality_profile: str = "balanced",
        target_paper_count: int | None = None,
        language: str = "zh",
    ) -> ResearchPlanDraft:
        """生成受校验计划；任一校验不通过抛 PlanRejected(稳定错误码)。"""
        # 1) goal 归一化（NFC 避免同形字符绕过长度校验）+ 长度校验。
        normalized = unicodedata.normalize("NFC", goal).strip()
        if not (GOAL_MIN_CHARS <= len(normalized) <= GOAL_MAX_CHARS):
            raise PlanRejected("PLAN_VALIDATION_FAILED")

        # 2) quality_profile 白名单；target_paper_count 缺省取档位默认再夹到硬区间。
        if quality_profile not in QUALITY_PROFILES:
            raise PlanRejected("PLAN_VALIDATION_FAILED")
        if target_paper_count is None:
            target_paper_count = QUALITY_PROFILES[quality_profile]["target_paper_count"]
        low, high = TARGET_PAPER_COUNT_RANGE
        target_paper_count = max(low, min(int(target_paper_count), high))

        # 3) facets 确定性切分（为什么不用 LLM 见模块 docstring）。
        facets = self._split_facets(normalized)

        # 4) 生成 WorkItem（本批不做 replan，属 Task05）。
        work_items = self._build_work_items(facets, normalized, target_paper_count, language)

        # 5) 冻结校验器兜底：类型白名单 / 参数允许列表 / 角色 / 无环 / 预算。
        ok, code = validate_plan({"work_items": [dict(item) for item in work_items]})
        if not ok:
            raise PlanRejected(code or "PLAN_VALIDATION_FAILED")

        # 6) 面向用户的结构化摘要（goal 预览 + facet 数 + 目标篇数 + 档位），不保存隐藏思维链。
        return ResearchPlanDraft(
            facets=tuple(facets),
            rationale_summary=self._build_rationale(normalized, facets, target_paper_count, quality_profile),
            work_items=tuple(dict(item) for item in work_items),
            planner_model=_PLANNER_MODEL,
            target_paper_count=target_paper_count,
        )

    # ------------------------------------------------------------------ #
    # 内部：确定性切分与计划构造
    # ------------------------------------------------------------------ #

    def _split_facets(self, goal: str) -> list[str]:
        """按中英分隔符切分 goal 为 facets；去空、去重、保序，最多 max_facets 个。

        不足 2 个时用通用 facet 补足到 2 个——Spec027 硬要求 fan-out 至少 2 路并行
        （search_catalog >= 2），因此这里宁可补通用方向也不产出单路计划。
        """
        parts = [part.strip() for part in _FACET_SPLIT_RE.split(goal)]
        unique: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if part and part not in seen:
                seen.add(part)
                unique.append(part)
        for fallback in _FALLBACK_FACETS:
            if len(unique) >= _MIN_FACETS:
                break
            if fallback not in seen:
                seen.add(fallback)
                unique.append(fallback)
        return unique[: self.max_facets]

    def _build_work_items(
        self, facets: list[str], goal: str, target_paper_count: int, language: str
    ) -> list[dict]:
        """生成四类 WorkItem（search/evaluate/coverage/synthesize），不含 replan。

        - search_catalog × N：N = min(max(facet 数, min_fanout), max_fanout)，无依赖可并行；
        - evaluate_papers：依赖全部 search id，catalog_paper_ids 留空（运行时由编排器回填），
          空列表保证 Schema 必填校验通过；
        - check_coverage：依赖 e1；synthesize_preliminary_report：依赖 c1（本批跳过 replan）。
        """
        search_count = min(max(len(facets), self.min_fanout), self.max_fanout)
        per_search = math.ceil(target_paper_count / search_count) if search_count else target_paper_count
        items: list[dict] = []
        search_ids: list[str] = []
        for index in range(search_count):
            item_id = f"s{index + 1}"
            search_ids.append(item_id)
            facet = facets[index] if index < len(facets) else facets[-1]
            items.append(
                {
                    "id": item_id,
                    "task_type": "search_catalog",
                    "role": "search-worker",
                    "depends_on": [],
                    "params": {
                        "query": f"{goal} {facet}",
                        "facets": [facet],
                        "max_results": per_search,
                        "language": language,
                    },
                }
            )
        items.append(
            {
                "id": "e1",
                "task_type": "evaluate_papers",
                "role": "paper-evaluator",
                "depends_on": list(search_ids),
                "params": {
                    "catalog_paper_ids": [],
                    "relevance_threshold": 0.2,
                    "facets": list(facets),
                },
            }
        )
        items.append(
            {
                "id": "c1",
                "task_type": "check_coverage",
                "role": "research-critic",
                "depends_on": ["e1"],
                "params": {"goal": goal, "gap_threshold": 0.3},
            }
        )
        items.append(
            {
                "id": "syn",
                "task_type": "synthesize_preliminary_report",
                "role": "synthesizer",
                "depends_on": ["c1"],
                "params": {
                    "goal": goal,
                    "language": language,
                    "evidence_level": "catalog",
                },
            }
        )
        return items

    @staticmethod
    def _build_rationale(goal: str, facets: list[str], target: int, profile: str) -> str:
        """结构化摘要：只暴露可展示决策，不含隐藏思维链 / Prompt / 原始模型协议。"""
        preview = goal if len(goal) <= _GOAL_PREVIEW_CHARS else goal[: _GOAL_PREVIEW_CHARS - 3] + "..."
        return (
            f"已为研究目标「{preview}」生成受校验计划："
            f"切分 {len(facets)} 个子方向（{'、'.join(facets)}），"
            f"目标入选 {target} 篇，质量档位 {profile}。"
            f"计划含 {len(facets)} 路 search_catalog 并行检索、evaluate_papers 初筛、"
            f"check_coverage 覆盖审查与 synthesize_preliminary_report 合成；"
            f"证据等级 catalog（不下载全文）。"
        )
