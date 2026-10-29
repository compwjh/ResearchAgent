# Spec 030 Task 08 Runtime 私有结构化正文入口

日期：2026-10-29  
角色：Backend Dev  
范围：`AgentRuntime` 的 opt-in `report_quality_context` 输入与 `report_content` 输出校验。

## 实现

- 在 [agent_runtime.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:191) 增加 `report-quality-v1` marker 校验：stage、revision、计划/报告版本、5–64 个唯一选中论文、维度和 evidence 摘录；targeted revision 必须携带合法 prior body、revision 1–2 和唯一固定 failure codes。未知字段、自由文本反馈、越界版本和未知 evidence level 均以 `REPORT_CONTEXT_INVALID` 失败，并且不调用模型。
- opt-in 时只向模型暴露 `report_version` 与已收窄的质量上下文。其余 WorkItem 字段（例如 catalog candidates、matrix context、URL、路径和任意字段）留在服务端。经验证的 excerpt 可标为 catalog、abstract 或 fulltext；locator/document/chunk 元数据不会进入模型输入。
- prompt 根据 evidence_review、comparison、drafting、targeted_revision 阶段分别要求结构性审阅或最终正文目标。早期阶段不要求 1,500 个 CJK 字符或最终 3 条受支持结论；drafting 和 targeted_revision 才提示最终目标。模型不计算正文字符数或 output hash。
- 质量路径的 synthesizer 输出必须带结构完整的 `research-report-content-v1` 正文，并且 `report_version` 必须与 WorkItem 一致。paper/evidence/dimension 引用须在当前允许集内，evidence 与其 paper 引用关系也会校验。无正文最终返回 `REPORT_CONTENT_REQUIRED`；不接受只靠目录 sections 完成。
- 对 drafting/targeted_revision，每条 comparison/finding 的 Evidence 映射必须覆盖至少两篇不同论文，沿用 `report_quality.validate_report_content` 的 `len(mapped) >= 2` 规则；声明两篇但证据实际只映射到一篇时，分别以 `INSUFFICIENT_COMPARISONS` / `INSUFFICIENT_SUPPORTED_FINDINGS` 触发安全重试。evidence_review/comparison 只校验结构与引用允许集，不提前执行最终跨论文支持门槛。targeted_revision 可携带 undercovered prior 继续修订，但仅当 failure_codes 明确包含对应不足码；新输出仍必须修复覆盖。
- 正文结构复用 `report_quality._validate_report_shape`。运行时不调用最终质量门禁，因此不会在 evidence_review/comparison 阶段提前执行字数、有效论文数、有效比较数或受支持发现数检查。现有 output digest 在校验和服务器绑定后照常重算。
- 未提供 `report_quality_context` 的旧 synthesizer 路径保持兼容，仍可省略 `report_content`。

## 定向验证

以下命令在该工作树执行，退出码均为 0：

| 命令 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_report_content_runtime.py` | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/agent_runtime.py tests/research/test_report_content_runtime.py` | `All checks passed!` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py tests/research/test_report_quality_context.py tests/research/test_agent_runtime_contract.py` | `86 passed in 1.12s` |

覆盖包括缺失正文 typed failure、早期短正文/延后支持门槛、模型输入隔离、fulltext 等级保留且不传 locator、未知 evidence level、evidence/paper/dimension 越界重试、伪多论文 comparison/finding 拒绝、匹配失败码时 prior 修复、报告版本绑定、修订上下文约束，以及旧 synthesizer 兼容。

## 后续接入边界

- 上游 Orchestrator/WorkItem 构造器需从已批准 selection、当前计划维度和服务器验证过的 Evidence 对象构造 `work_item_input.report_quality_context`。其 `report_version` 必须等于 `work_item_input.report_version`；若提供 `matrix_context`，其 `plan_version` 必须与 marker 一致。
- Runtime 只校验 marker 的结构、边界和引用归属；它不能证明 excerpt 确由 `EvidenceMatrixService` 验证。因此上游仍须执行 Evidence/全文 provenance 校验，且不得把模型或用户自报摘录当成服务器批准事实。
- Runtime 的报告质量输出仍沿用既有 synthesizer envelope，`report_content` 是结构化正文，`output_hash` 由服务器计算。Orchestrator、ResearchStore、ReportSynthesis/API 尚未接收此正文、生成质量 verdict、形成 canonical report/artifacts 或处理发布状态；这些连接不属于本 Task。
- 本次未运行全量测试、真实模型调用、部署或 API E2E；它们不在本 Task 的验证范围内。

## 变更文件

- `backend/app/research/application/agent_runtime.py`
- `tests/research/test_report_content_runtime.py`（在复用前代理遗留测试基础上补充版本、paper/reference 和修订上下文用例）
- 本交接说明

## 进展日志

- `.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-160000.md`
