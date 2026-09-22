# Spec032 需求评审

## 评审元数据

- 评审者：Spec032 Task14 review-regression 子 Agent
- 角色：需求/验收范围复核（临时 Luna high）
- 模型：Luna high
- 分派方式：主 Agent 直接分派
- 依据：`docs/sdd/specs/032-research-source-expansion.md`、`docs/sdd/plans/032/task-14-review-regression-deploy.md`、Task06–13 artifacts/reports 与当前工作树 diff

## 结论

**打回（收口阻塞，P1）。** 目标、来源边界、明确不做和失败语义总体清楚，但规格的“产品使用步骤”仍是占位文字，且新来源虽写入 Planner 输入边界，实际 Research Worker 仍只有 USENIX/DBLP 路径。当前不能把 IEEE S&P/CCS/NDSS 的真实选择、覆盖、导入和失败队列视为可操作验收场景。

## 事实依据

1. Spec032 的“产品使用步骤”仍写为“本版确认后由产品经理补充”，没有来源选择→同步进度→批准导入→待处理修复→新报告版本的可执行步骤映射；Task12 artifact 只能证明前端静态契约，不能替代 spec 内的产品旅程。
2. Task07 明确 CCS/NDSS 2021–2025 为 NO-GO，IEEE S&P 只验证 2024；这符合诚实失败原则，但与 Task14 的“四会议逐年覆盖”目标之间仍存在未闭环验收差距。
3. `planner.py:83-107` 接受新来源 ID，`search_catalog_adapter.py:95-96` 却拒绝除 `usenix|dblp|all` 外的 source scope；这使产品选择无法抵达对应来源 Worker。

## 必须补齐

- 在 Spec032 的“产品使用步骤”中写入可执行的用户旅程，并逐步链接 Task12/Task14 验收证据。
- 明确区分“已验证覆盖”“未验证/NO-GO”“运行时接入但未完成真实 smoke”，不得用参数范围替代证据。
- 修复新来源 Planner→Skill→`paper_discovery` 的实际接线，并新增每个已支持来源的选择/失败契约测试。

在上述事项完成、重新评审前，需求门禁不通过。
