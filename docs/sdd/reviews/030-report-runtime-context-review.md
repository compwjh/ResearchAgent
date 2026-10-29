# Spec030 Task08 Runtime/context 后端评审

日期：2026-10-29  
范围：`agent_runtime.py`、`orchestrator.py` 与 `test_report_content_runtime.py`、`test_report_quality_context.py` 当前未提交差异。只读评审；未改业务代码或测试。

## 结论

**BLOCK** — 发现 1 项 HIGH 级合同缺口：Runtime 会接受只映射到单篇论文的跨论文比较/综合发现，尽管内容声明至少两篇论文。该结果会以成功的 AgentRuntime 输出继续流转，违背当前报告证据映射约束。

上下文 Builder 的可信来源边界总体符合要求：候选集合与任务持久选集、冻结搜索快照、当前 task/plan ClaimEvidence 相绑定；全文行必须通过同一 task 的 EvidenceUpgrade 与 document/chunk provenance 校验；没有安全矩阵 cell summary 时不把 locator 文本转发。Runtime 仅传显式 allowlist，缺少 `report_quality_context` 的旧 synthesizer 路径仍保持兼容。上述判断均基于实现代码，不依赖交接描述。

## 问题

### [HIGH] 跨论文比较/发现未要求引用实际覆盖两篇论文

**文件：** [agent_runtime.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:213)

`_validate_report_quality_references` 只检查 comparison/finding 声明的 `paper_ids` 属于选集，并逐个确认引用 Evidence 映射到声明集合中的某篇论文；它没有确认引用映射后的不同 `paper_id` 数至少为 2。因此，结构上声明了 `paper-1` 和 `paper-2`、但所有 `evidence_ids` 实际只映射到 `paper-1` 的比较或综合发现会通过 Runtime 校验。相同缺口也会被用于 targeted revision 的 prior 内容校验。

这与计划要求的“比较和发现的每个 Evidence ID 必须映射到声明集合中的至少两个不同 paper_id”不符。最终质量校验器已经显式使用 `len(mapped) >= 2`，但 AgentRuntime 在此之前会接受该候选输出为 `completed`，所以仅依靠后续门禁不能替代本层引用契约校验。

**修复方向：** 对每个 comparison/finding 计算引用 Evidence 映射到的不同论文集合，并要求集合大小至少为 2；可复用最终质量校验器的逻辑，避免两处规则漂移。添加单篇实际来源、声明两篇论文的 comparison 与 finding 用例，确认 Runtime 拒绝或要求修正。

## 验证

- 命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py tests/research/test_report_quality_context.py`
- 结果：退出码 0；`21 passed in 0.76s`。
- 未运行全量测试、模型调用、服务部署或 API E2E。

## Review Summary

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | block |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **BLOCK** — 1 HIGH issue must be resolved before this Task can pass review.

 
## Runtime 修复复审（2026-10-29）

**复审结论：PASS（原 BLOCK 项已关闭）。** 首次评审中的 BLOCK 与 HIGH 问题记录保留在上文；本节记录 Runtime 修复后的独立复审结果。

### 复审范围与结果

修复在 _validate_report_quality_references 增加了基于真实 Evidence ID 映射计算不同来源论文数的门槛；drafting 和 targeted_revision 输出要求每个 comparison/finding 至少覆盖两篇实际论文。evidence_review/comparison 阶段延后这一最终支持门槛，仍校验 Evidence/paper/dimension 引用归属。targeted_revision prior 只有在 failure_codes 含对应不足码时才允许 undercovered comparison/finding；缺失或越界 Evidence 仍拒绝。见 [agent_runtime.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:191)。

- 定向测试：/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py，退出码 0，19 passed in 0.60s。
- 独立 helper 探针：drafting 对单论文来源返回 INSUFFICIENT_COMPARISONS；early stage 延后门槛；匹配 failure code 的 targeted prior 可保留 undercoverage；unknown Evidence 即使有豁免仍返回 INVALID_EVIDENCE_REFERENCE。结果 PASS。
- 旧 synthesizer 缺少 report_quality_context 时的兼容用例包含在定向测试中并通过。
- 未运行全量测试、模型调用或部署。

因此，首次评审报告的原 BLOCK 是历史首次结论；按本次复审，Runtime 跨论文证据覆盖问题已修复，当前该 Runtime 范围通过。
