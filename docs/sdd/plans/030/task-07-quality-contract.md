# Task 07：内容质量合同与运行路径审计

关联：Spec 030；[内容质量合同](./2026-10-29-report-quality-contract.md)；[Grilling](./2026-10-29-report-quality-grilling.md)；[运行时审计](./2026-10-29-report-runtime-audit.md)。
状态：合同已按 Gate 2 REQ-01 / TECH-01..05 修订，待原独立评审者复审；产品范围已确认，Task 02–06 仍为已完成历史任务。

## 目标与边界

冻结 2026-10-29 内容充分性修订的可实现合同和真正的主报告路径；在合同评审通过前不实现代码、不重开 Spec042、不重跑历史报告、不写数据库、不启动/部署服务。

架构师负责合同与来源核对；主会话负责评审裁决。只读核对 AgentRunner、矩阵/报告渲染、ResearchReport、Artifact、版本分配及现有路由。使用运行审计中的两份样本作为基线：Task 83592… 的 1,435 Unicode 字符 Artifact、Task fc836… 的 7,649 Unicode 字符目录卡片、每份五条引用、两条 canonical /reports/1 均 404。它们不是 CJK 计数样本，也不能证明 deterministic fallback 被触发；Artifact run ID 和 worker completed 事件不能证明模型输出通过校验。

## 冻结决策

- 接受合同文件中的 report_content、quality_validation、generation 字段；沿现有 report_json 存储，无 SQL migration。
- report_version 在一次合成开始时分配一次，贯穿 AgentRun 输出、ResearchReport、Artifact、会话消息、通知和下载；plan_version 独立表示计划/矩阵版本。
- 自然语言 ResearchSession → ResearchAgentRunner → synthesizer WorkItem 是正式报告生成主路径。仅通过同一质量门禁的模型合成输出可发布；目录卡片 fallback 和没有 report_content 的纯矩阵渲染均为草稿。
- session-backed 的 `POST /api/research-tasks/{id}/reports` 当前实际同步调用 `ReportGenerationService.generate` 的矩阵 renderer，不启动 AgentRunner；实现方案是在此既有 POST 接缝分流到现有 `synthesize_preliminary_report` task_type/role 和 Runner。completed WorkItem 不回退；后续 report_version 新建同类型 WorkItem row，由 `ResearchService` 现有 executor 执行 report-only Orchestrator 分支，不重开 ResearchTask、不增加 endpoint/type/队列/executor/Runner。无 session 的旧矩阵调用保留同步语义，但明确为 draft。
- 版本通过 `ResearchStore` 内单个 `BEGIN IMMEDIATE` 事务完成 request-key 查询、跨 ResearchReport/Artifact 取 max+1、插入 `status=generating` 的 report reservation。`next_report_version()` 只是读取，不用于预留。report_json 的 reservation/generation 状态在 generating 时可条件推进，终态不可变；现有 report/version 唯一约束承担并发仲裁，无 migration。
- 接口冻结：请求 body 原样保留；可选 UUID `Idempotency-Key` 区分重复请求/主动重试；session-backed POST 202 返回 generating 状态与质量/发布字段；GET 仍读任一版本/格式；未发布版本从 artifact list/download 隐藏。重复 key/重启续用同 reservation 与 WorkItem checkpoint，不改 revision/call/elapsed。
- 合同冻结 report_content、quality_validation、generation 的对象字段/枚举/数量/长度/JSON 字节上限及计数来源。Machine validation 只证明结构、选集和证据 ID/来源等级映射、计数、预算与版本一致；Task10 的人工 rubric 独立判断论文分析忠实度、比较质量、综合推断、摘要/全文边界和重复填充。

## 交付与验证

本 Task 交付物是合同文件和本审计计划；独立审查者核对字段、状态、路径、旧版兼容与来源链接。审查通过条件：

1. 两份 runtime 样本被明确标为有限样本，报告根因未定；candidate_id 与 KB document_id 不匹配不等于没有全文。
2. 报告和 Artifact 的 report_version 由同一原子 reservation 生成；重复 POST、进程重启及各持久化切点可复用同一版本，fallback/model accepted 由结构化运行结果可核验。
3. 有界 schema 与 1,500 CJK、五篇逐篇分析、一项跨论文比较、三条受支持发现、Evidence→paper/source-level 映射及 40/160 per-run、160/640 task loop/call、5,400 秒软上限均有机器验收条件；语义 rubric 另由 Task10 人工复核。
4. 没有要求重写 Task02–06 或扩大 Spec042。

不运行服务或 GET session detail/events 作为“无写探测”：已知前者可能 reconciliation，后者会 drain projection retries。Task10 的真实 E2E 必须使用新鲜实体并记录这些调用可能有的状态推进。

## 回滚、风险与下一步

本 Task 是文档审计，无业务回滚。审计显示当前样本 Artifact 可读而 canonical 报告 404；不得据此称任一特定短报告由 AgentRunner fallback 造成，也不得从 AgentRun-shaped ID 推断模型输出被接受。Task08 补齐原子 reservation、结构化 output disposition、同版本恢复与 artifact 发布过滤。主会话等原独立评审者解除 Gate2 BLOCK 后再安排 Task08。

2026-10-29执行状态：已完成合同门；用户确认，独立需求/技术最终GO，实际实现验证仍由后续Task负责。
