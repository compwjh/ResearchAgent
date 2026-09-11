# Spec 030 — 跨论文证据矩阵与深度研究报告

## 状态

**当前状态：待确认**

## 一句话目标

把 Research Task 已确认的目录、摘要和全文证据组织成可追溯的跨论文比较矩阵，并生成标明证据来源、冲突、局限和覆盖缺口的深度研究报告。

## 背景与依赖

- Spec027 只产出初步报告，Spec029 才能提供可定位全文证据。
- 长报告必须先形成结构化 Claim/Evidence，再合成正文，不能让模型凭长上下文一次生成不可追溯结论。
- 本 Spec 依赖 Spec027；全文能力启用时依赖 Spec029，但仍允许对仅有摘要的任务生成降级报告。

## 数据模型

| 实体 | 关键字段 | 约束 |
|---|---|---|
| ResearchClaim | claim_id、task_id、topic、statement、confidence、status | 每个结论独立记录 |
| ClaimEvidence | claim_id、paper_id、evidence_level、chunk_id/page、quote_digest、stance | supports / contradicts / contextual |
| ComparisonDimension | id、label、definition、order | 由计划确认，版本内稳定 |
| PaperComparisonCell | paper_id、dimension_id、summary、evidence_ids | 无证据时为空，不猜测 |
| ResearchReport | task_id、plan_version、report_version、markdown、status | 只读、版本不可覆盖 |
| CitationManifest | report_id、citation_no、paper_id、evidence_ids | 与报告编号一一对应 |

## 接口与产物

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST /api/research-tasks/{id}/evidence-matrix | dimensions 可选 | 202 WorkItem | 409 证据不足/任务状态 |
| GET /api/research-tasks/{id}/evidence-matrix | plan_version | 结构化矩阵与缺口 | 404 |
| POST /api/research-tasks/{id}/reports | outline/profile | 202 报告生成 | 409 matrix 未就绪 |
| GET /api/research-tasks/{id}/reports/{version} | format=html/markdown/json | 只读报告或下载 | 404；406 |

- 报告语言默认跟随研究任务；标题和正式论文名称保留原文。
- Markdown 是权威可移植产物，HTML 由同一结构渲染，JSON 提供引用 manifest；不做富文本编辑。
- 每条主要结论至少引用一条 evidence；仅标题级候选不得进入方法/结果比较。

## 边界与失败场景

- 多论文互相矛盾、证据等级不同、同一切片支持多个 Claim、引用文档删除、报告生成中断。
- 模型输出必须通过 Claim/Evidence Schema 和 citation manifest 校验；不存在的论文、页码或 chunk 直接拒绝。
- 证据不足时保留空单元格并列入 limitations，不使用常识补齐论文事实。
- 新报告版本引用旧证据时保留来源；不得覆盖旧报告历史。

## 明确不做

- 不做多人协同编辑、富文本编辑、自动投稿或参考文献格式全集。
- 不重新实现全文检索、embedding 或 reranker。
- 不把报告全部自动写入长期记忆。

## 验收方式

- 固定相互支持/冲突/缺失证据样本生成矩阵，所有单元格可追溯。
- 报告每个主要 Claim 的 citation manifest 可回查论文与证据等级。
- Markdown、HTML、JSON 三种视图语义一致；恶意论文文本不能注入界面或改变 Agent 权限。
- 最终 Task 执行一次全量回归、浏览器验收、部署和复盘。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充查看矩阵、生成报告、展开引用和下载 Markdown/JSON 的旅程。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Claim/Evidence 与报告边界 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 报告阅读旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 可追溯性与引用评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 分端开发 Agent | 证据、报告和界面实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 引用与导出验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec030 | 本文件 | — | 完成 |
| 02 | 冻结 Claim/Evidence 与报告协议 | [`task-02-evidence-report-contract.md`](../plans/030/task-02-evidence-report-contract.md) | Spec027；全文场景依赖029 | 待执行 |
| 03 | 实现证据矩阵与校验 | [`task-03-evidence-matrix.md`](../plans/030/task-03-evidence-matrix.md) | 02 | 待执行 |
| 04 | 实现报告生成、版本和导出 | [`task-04-report-generation-export.md`](../plans/030/task-04-report-generation-export.md) | 03 | 待执行 |
| 05 | 实现报告工作台与引用交互 | [`task-05-report-workspace-ui.md`](../plans/030/task-05-report-workspace-ui.md) | 04 | 待执行 |
| 06 | 最终评审、回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/030/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/030-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/030-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/030-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建证据矩阵和深度报告 Spec |
