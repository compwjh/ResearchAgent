"""研究计划校验（纯 Python，无 IO）。

与 tests/test_spec027_runtime_contract.py 门禁实现同构；返回 (ok, error_code)，
ok 为 True 时 error_code 为 None。判定顺序严格固定为：
  ① 所有 item 的 task_type 不在白名单 -> UNKNOWN_TASK_TYPE
  ② 参数 key 越权或缺失必填 -> PLAN_VALIDATION_FAILED
  ③ role 不在 ROLE_WHITELIST -> PLAN_VALIDATION_FAILED
  ④ 有环 -> CYCLIC_DEPENDENCY
  ⑤ 超预算 -> BUDGET_EXCEEDED
"""

from __future__ import annotations

from typing import Any, Optional

from .contracts import (
    BUDGET_CAPS,
    ROLE_WHITELIST,
    TASK_TYPE_WHITELIST,
    WORKITEM_SCHEMAS,
)


class PlanRejected(Exception):
    """计划被拒绝时抛出的异常；code 为稳定错误码。"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def has_cycle(items: list[dict]) -> bool:
    """三色 DFS 检测依赖环；只认 items 内部 id，引用不存在的 id 视为无边。"""
    by_id = {it.get("id"): it for it in items if it.get("id") is not None}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[Any, int] = dict.fromkeys(by_id, WHITE)

    def dfs(nid: Any) -> bool:
        color[nid] = GRAY
        node = by_id.get(nid)
        if node is not None:
            for dep in node.get("depends_on", []) or []:
                if dep not in by_id:
                    continue
                if color.get(dep) == GRAY:
                    return True
                if color.get(dep) == WHITE and dfs(dep):
                    return True
        color[nid] = BLACK
        return False

    return any(color[nid] == WHITE and dfs(nid) for nid in by_id)


def check_budget(items: list[dict]) -> Optional[str]:
    """超预算返回 'BUDGET_EXCEEDED'，否则 None。

    预算口径：search_catalog 数量 > max_search_items；
    evaluate_papers 的 catalog_paper_ids 长度累计 > max_candidates；
    synthesize_preliminary_report 的 selected_paper_ids 长度 > max_selected。
    """
    search_count = sum(1 for it in items if it.get("task_type") == "search_catalog")
    if search_count > BUDGET_CAPS["max_search_items"]:
        return "BUDGET_EXCEEDED"

    candidates = 0
    for it in items:
        if it.get("task_type") == "evaluate_papers":
            params = it.get("params") or {}
            candidates += len(params.get("catalog_paper_ids") or [])
    if candidates > BUDGET_CAPS["max_candidates"]:
        return "BUDGET_EXCEEDED"

    for it in items:
        if it.get("task_type") == "synthesize_preliminary_report":
            params = it.get("params") or {}
            sel = len(params.get("selected_paper_ids") or [])
            if sel > BUDGET_CAPS["max_selected"]:
                return "BUDGET_EXCEEDED"

    return None


def validate_work_item(item: dict) -> Optional[str]:
    """校验单个 WorkItem；返回错误码或 None。

    顺序：task_type 白名单 -> 参数允许列表/必填 -> role 白名单。
    """
    task_type = item.get("task_type")
    if task_type not in TASK_TYPE_WHITELIST:
        return "UNKNOWN_TASK_TYPE"
    schema = WORKITEM_SCHEMAS[task_type]
    params = item.get("params") or {}
    for key in params:
        if key not in schema["allowed_params"]:
            return "PLAN_VALIDATION_FAILED"
    for req in schema["required_params"]:
        if req not in params:
            return "PLAN_VALIDATION_FAILED"
    if item.get("role") not in ROLE_WHITELIST:
        return "PLAN_VALIDATION_FAILED"
    return None


def validate_plan(plan: dict) -> tuple[bool, Optional[str]]:
    """校验整个研究计划；返回 (ok, error_code)。"""
    items = plan.get("work_items")
    if not isinstance(items, list):
        return False, "PLAN_VALIDATION_FAILED"

    # ① task_type 白名单
    for it in items:
        if it.get("task_type") not in TASK_TYPE_WHITELIST:
            return False, "UNKNOWN_TASK_TYPE"

    # ② 参数 key 越权或缺失必填
    for it in items:
        task_type = it.get("task_type")
        schema = WORKITEM_SCHEMAS.get(task_type)
        if schema is None:
            # ① 已对未知 task_type 返回，这里仅为防御性短路
            continue
        params = it.get("params") or {}
        for key in params:
            if key not in schema["allowed_params"]:
                return False, "PLAN_VALIDATION_FAILED"
        for req in schema["required_params"]:
            if req not in params:
                return False, "PLAN_VALIDATION_FAILED"

    # ③ role 白名单
    for it in items:
        if it.get("role") not in ROLE_WHITELIST:
            return False, "PLAN_VALIDATION_FAILED"

    # ④ 依赖环
    if has_cycle(items):
        return False, "CYCLIC_DEPENDENCY"

    # ⑤ 预算
    code = check_budget(items)
    if code:
        return False, code

    return True, None


def assert_contracts_unchanged(paper_text: str) -> None:
    """固化「论文文本不可信」断言（Spec027 实现锚点）。

    paper_text 为不可信输入，本函数不对它做任何处理，仅断言冻结的
    TASK_TYPE_WHITELIST / ROLE_WHITELIST 仍是长度为 5 的冻结集合——
    即论文内容不得改变计划、权限、工具集或任务类型白名单。
    """
    assert len(TASK_TYPE_WHITELIST) == 5, "TASK_TYPE_WHITELIST 被篡改"
    assert len(ROLE_WHITELIST) == 5, "ROLE_WHITELIST 被篡改"
