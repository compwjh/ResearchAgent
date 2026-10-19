# Spec 016 Task 06 独立评审与 Task 08 迁移格式裁决

- 日期：2026-10-15
- 评审者：final_architect；角色：architect；模型：gpt-6-luna xhigh
- 范围：Task06 Prompt/result/metrics、失败与中断恢复 lineage、owner/lease、journal 化 Git 提交和重建后的 terminal result 查询；另对 Task08 legacy 迁移数据形状作架构裁决。只读评审；未运行测试，未修改生产代码。
- 结论：**FAIL — 发现 1 项 P1 状态一致性缺陷。** 其余已审的 lineage、owner/lease、journal/CAS 与 result 路径未发现 P0/P1。未运行测试；这不是 Task06 动态 QA 收口、Task09 整体验收或 CodeBuddy 本地验收。

## 阻塞级别

- P0：无。
- P1：1 项，见下文。
- P2：无。

## 复核依据

### P1 — status 未按 Task06 failed-source 证明计算恢复资格

[`catalog_status.py`](../../../scripts/sdd_tasks/catalog_status.py#L111) 只对最新 `abandoned` run 进入恢复校验。最新 `failed` run 直接返回无恢复原因，因此其 observation、recovery decision、owner/lease closure、source tip 与当前 workspace 未经证明时，pending Task 仍可能出现在 `eligible`。反方向上，failed run 派生的 abandoned retry child 虽由 [`newcli_claim.py`](../../../scripts/sdd_tasks/newcli_claim.py#L128) 先通过 `failed_retry_origin` 分类、再由 [`resolve_failed_source`](../../../scripts/sdd_tasks/failed_selection.py#L34) 严格证明并可由 `next` 领取，`status` 却把它送入 Task05 的泛型 [`load_recovery_snapshot`](../../../scripts/sdd_tasks/catalog_status.py#L133)，并将合法 lineage 报为 `recovery_invalid:RECOVERY_SOURCE_INVALID`、列入 `waiting`。这同时产生 failed source 假阳性与合法 failed-derived recovery 假阴性，破坏 Spec016 对 `status` 可执行/等待列表的接口含义；损坏 failed source 还可能使真实 `next` 在领取前失败。

冻结 Task06 协议要求 `claim_next` 仅消费最新未消费 run，并对 failed source 核验 observation、decision、身份和恢复 tip（[`TASK-PROTOCOL.md`](../TASK-PROTOCOL.md#L326)）。修复应局限于 `catalog_status.py`：最新 `failed` 以及由 `failed_retry_origin` 证明为 failed-derived 的最新 `abandoned` run，调用现有 `resolve_failed_source` 并映射为 `recovery_ready:<kind>`；证明失败时列入 `recovery_invalid:<stable code>` 并留在 waiting。无 failed ancestor 的普通 Task05 abandoned run 继续使用既有 generic strict loader，不放宽任一 source loader。此评审未改生产代码；修复与其动态回归等待独立工具域 QA 完成后再安排。

### Lineage、消费和基线

冻结协议要求只选最新且未消费的恢复来源；failed partial 的每次 child 都必须指向 immediate source、复制原始 before snapshot，并验证 source 链和文档提交 tip。代码在 [`failed_lineage.py`](../../../scripts/sdd_tasks/failed_lineage.py#L53) 校验每个 source 恰有一个消费者，在 [`failed_lineage.py`](../../../scripts/sdd_tasks/failed_lineage.py#L76) 逐段验证状态、attempt 顺序、snapshot 一致性及恢复事件；[`failed_lineage.py`](../../../scripts/sdd_tasks/failed_lineage.py#L236) 再要求 source 为最新 abandoned attempt 且尚未消费。活动 child 在 [`active_failed_recovery.py`](../../../scripts/sdd_tasks/active_failed_recovery.py#L43) 绑定到紧邻的 failed/abandoned source、原始 base 和 attempt；[`active_failed_recovery.py`](../../../scripts/sdd_tasks/active_failed_recovery.py#L204) 校验唯一消费、owner、lease 与 source proof。claim 在同一事务写 run、lease、workspace snapshot 和 recovery_claim，见 [`selection.py`](../../../scripts/sdd_tasks/selection.py#L116) 与 [`selection.py`](../../../scripts/sdd_tasks/selection.py#L201)。这些检查与 [`TASK-PROTOCOL.md`](../TASK-PROTOCOL.md#L317) 的 frozen contract 相符。

### Owner 与 lease

[`run_owner.py`](../../../scripts/sdd_tasks/run_owner.py#L16) 从持久账本核验 executor/PID/host/process-start/token、owner 存活、lease 有效期和 canonical Task/hash/mirrors。过期恢复由 [`leases.py`](../../../scripts/sdd_tasks/leases.py#L202) 在 `BEGIN IMMEDIATE` 内重核 owner 已死、lease 过期和 workspace decision，再关闭 lease 并写恢复事件；它不清理 worktree。`complete`/`fail` 经 [`completion_service.py`](../../../scripts/sdd_tasks/completion_service.py#L295) 先核验 owner，再执行真实 validation runner 与结果/工作区重验。公开 `result` 不要求 owner，但只读 canonical summary，符合协议的 terminal-result 边界，见 [`result_query.py`](../../../scripts/sdd_tasks/result_query.py#L29)。

### 精确提交与 crash recovery

[`completion_prepare.py`](../../../scripts/sdd_tasks/completion_prepare.py#L37) 绑定 canonical Task、claim、原始 baseline、最终 workspace 和 expected docs；成功提交包含允许变化路径，failed/blocked 只纳入 summary 与被状态更新的镜像。Journal schema 固定字段、单向阶段及目标路径集合，见 [`journal_schema.py`](../../../scripts/sdd_tasks/journal_schema.py#L21)。[`git_candidate_index.py`](../../../scripts/sdd_tasks/git_candidate_index.py#L84) 从独立临时 index 构建候选 tree，并逐项对 expected mode/blob/path；[`git_candidate_cas.py`](../../../scripts/sdd_tasks/git_candidate_cas.py#L120) 用 expected-old ref CAS；[`git_reconciliation_index.py`](../../../scripts/sdd_tasks/git_reconciliation_index.py#L553) 只在 HEAD、lock inode/image、目标 entries 和其他 index entries 均匹配时原子安装 index。最后 [`ledger_finalize.py`](../../../scripts/sdd_tasks/ledger_finalize.py#L446) 在 DB CAS 中写终态、Task 状态、lease 和 artifacts。恢复按 durable journal phase 重放，不从自由文本推断成功/失败。

### 指标与结果

[`metrics.py`](../../../scripts/sdd_tasks/metrics.py#L42) 导出固定 schema，缺失 token/tool/change 值为空并带 source；terminal 指标先读取校验后的 summary。[`result_query.py`](../../../scripts/sdd_tasks/result_query.py#L29) 限定结果路径、schema、run/task/hash 绑定并执行敏感内容扫描；runtime `result.json` 不作为结果事实源。

## 已有验证证据（本评审未重跑）

- [Task06 failed retry/结果验证记录](../plans/016/artifacts/task06-result-metrics-tests.md) 记录真实 child owner `os._exit(86)` 后 CLI recover、next 领取 immediate abandoned source、CLI complete、rebuild 后保留三条 run 并返回 `NO_TASK`。该项是报告中记录的测试结果，不是本评审者本轮执行。
- [Task06 journal 验证记录](../plans/016/artifacts/task06-journal-validation.md) 记录文档写入、CAS、SQLite commit、部分 index 写入和 index rename 等中断点的独立进程恢复证据，并明确其边界为进程退出实验而非断电实验。
- [Task06 index reconciliation QA](../plans/016/artifacts/task06-index-reconciliation-tests.md) 记录 staged outsider 保留、锁/image 冲突拒绝和索引安装重放检查。
- [Task06 owner/events QA](../plans/016/artifacts/task06-owner-events-tests.md) 记录真实 owner 身份与 PID reuse/远端 host/过期 lease 等拒绝用例，以及事件事务和 JSONL 幂等行为。

## Task08 legacy 迁移格式裁决（不代表 Task08 已验收）

Task08 audit 的 31 项分类为 22 `completed`、7 `partial`、1 `pending`、1 `migration_unverified`（[审计矩阵](../plans/016/artifacts/legacy-task-audit.md#L9)）。冻结结果导入器只认 `sdd-run-result/v1` 的精确字段与 UUID，并要求真实 `started_at`、`ended_at`、duration 和匹配的 `sdd-run-meta/v1`；scanner 仅扫描 `docs/sdd/runs/` 且要求与 Task 绑定的规范路径（[`result_schema.py`](../../../scripts/sdd_tasks/result_schema.py#L81)、[`summaries.py`](../../../scripts/sdd_tasks/summaries.py#L81)、[`summaries.py`](../../../scripts/sdd_tasks/summaries.py#L126)）。现有 legacy 证据没有这些统一运行事实（审计矩阵 `unknown_metrics` 全 null），因此不得构造 UUID、开始/结束时间、duration、模型或伪造 TaskRun。

Task08 §B 要求 `provenance=legacy` 摘要、保留未知指标、部分项建立清晰剩余工作、已知待执行项保持 pending；这些要求不需要扩展结果 schema。最小一致形式是在 `docs/sdd/plans/016/artifacts/legacy-summaries.md` 保存独立的 legacy evidence summary：每 Task 记录 `provenance=legacy`、分类/状态事实、审计证据路径与 `unknown_metrics` 全 null，并明示“非 Run / 不导入 SQLite”；不放入 `docs/sdd/runs/`，不使用 `sdd-run-result:v1` marker。rebuild 仅重建 Task metadata 状态；历史 TaskRun 没有可信输入时就不生成。

迁移状态裁决：22 个已核实完成项写 `status=completed,migration_state=verified`；7 个部分完成项保留全部旧正文和证据，原 Task 不得标 completed，应以 `blocked` 表示其完整原范围未完成，并创建/修订各自有明确剩余 scope、验收和解除条件的 remainder Task。已核实分类的 partial 不应再标 `migration_state=unverified`；新 remainder Task 的执行状态须由真实依赖/门禁控制。唯一已知 pending 项（Spec015 Task04）按 Task08 原文保持 `status=pending`，补全 schema/Prompt/allowed paths/依赖，`migration_state=verified`；为避免该项被 `next` 自动领取，给它一个 schema 合规、当前未满足的 Spec-qualified activation gate，待明确人工开放后再通过证据关闭 gate。唯一 `migration_unverified` 项保留 `migration_state=unverified` 和具体解除条件；它的 Task status 仍用实际受支持的 `pending` 或 `blocked` 值，不把迁移分类伪装成新 Task status。故将其余 9 项一律设成 `blocked + migration_state=unverified` 虽然 fail-closed，但会错误表达已核实的 8 项迁移不确定性，并使 pending 项偏离 Task08 明定的 `pending` 语义。

只同步既有 Task 权威状态与 Task 状态行、各 Spec 任务表、对应 plans README 的状态镜像；不得为了消除任务行差异而改变 Spec013/014/015 顶层状态或扩大 Task15–17 的 USENIX-only 完成范围。此处仅裁决迁移数据形状与状态映射；Task08 的写入、逐 Spec doctor/rebuild/status、Task09 独立验收均未在本次评审执行或签收。

## 验收边界

本评审发现的 P1 必须修复并由独立工具域 QA 覆盖后，才能重新签 Task06。Task07/08/09 结果、ResearchAgent 业务全量回归与 Task09 review 尚不在本签字范围。真实 CodeBuddy 留本地进行，A6 与 Task02 不可标为通过；本评审不代表 Spec016 完成。
