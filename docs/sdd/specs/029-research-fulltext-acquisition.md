# Spec 029 — Research Task 全文获取与知识库联动

## 状态

**当前状态：实施中（等待 Spec028 调度合同）**

## 一句话目标

让用户确认 Research Task 的论文清单后，系统复用既有安全下载、批量导入和知识库索引能力获取全文，并把报告证据从目录/摘要升级为可定位的全文切片。

## 背景与复用硬约束

- Spec027 只使用目录和摘要，不能据此声称完成全文分析。
- 必须复用 Spec015/021 的下载、SSRF、PDF 校验、批量导入、租约、重试和状态机，以及 Spec018 的文档/切片定位和 Spec011/012/014 的知识库检索链。
- 禁止新建第二套下载器、浏览器登录、PDF parser、chunker、Qdrant Collection 或导入表。

## 数据模型

| 实体 | 关键字段 | 约束 |
|---|---|---|
| AcquisitionApproval | task_id、selection_version、paper_ids、status | 用户可增删候选后一次确认 |
| ResearchDocumentLink | task_id、catalog_paper_id、document_id、import_item_id | 只保存引用，不复制 KB 文档 |
| EvidenceUpgrade | claim_id、from_level、to_level、chunk_ids、status | fulltext 必须有可定位切片 |
| AcquisitionEvent | paper_id、phase、status、error_code | 映射既有导入状态，不创造平行状态机 |

## 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST /api/research-tasks/{id}/acquisition-preview | plan_version | 已存在/待下载/需登录/不可用清单 | 409 报告未就绪 |
| POST /api/research-tasks/{id}/acquisitions | selection_version、paper_ids、idempotency_key | 202 + 既有 batch 引用 | 400；409；424 |
| GET /api/research-tasks/{id}/acquisitions | cursor | 每篇映射状态 | 404 |
| POST /api/research-tasks/{id}/evidence-upgrade | document_ids | 202 + WorkItem | 409 索引未完成 |

## 用户行为

- 系统展示入选论文清单和“已有知识库/可公开下载/需要登录/来源不可用”。
- 用户可增删论文，一次确认后进入既有批量导入；未确认绝不下载。
- 登录仍由用户在既有 Playwright 会话完成，Agent 不接触凭据。
- 全文索引完成后，Research Task 使用现有 RAG 召回切片，并在报告中标注全文证据与页码。

## 边界与失败场景

- 重复确认、部分论文已经存在、同名/DOI 去重、登录等待、下载失败、无效 PDF、索引失败和取消。
- 单篇失败不回滚已成功论文；报告保持 partial 并显示可执行重试。
- 论文被知识库删除后对应全文证据降为 unavailable，不删除报告历史文字。
- 项目/任务删除不级联删除共享知识库文档。

## 明确不做

- 不自动下载未确认论文，不绕过付费墙、验证码或登录。
- 不修改既有 chunker、embedding、reranker 和知识库 Collection 语义。
- 不扩展新会议来源，不实现报告编辑器。

## 验收方式

- 固定样本验证候选增删、审批幂等、已有文档复用、批量导入映射和单篇失败补偿。
- 真实导入至少一篇公开 PDF，完成全文索引并把一条摘要级证据升级为可定位切片。
- 下载安全、导入恢复和知识库相关回归必须通过；最终 Task 才跑全量回归。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充候选确认、登录等待、失败重试和证据升级旅程。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 复用边界和证据语义 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 导入确认旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 安全与复用审计 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 分端开发 Agent | 接线与定向验证 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 导入/KB 验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec029 | 本文件 | — | 完成 |
| 02 | 复用审计与全文证据协议门 | [`task-02-reuse-and-evidence-gate.md`](../plans/029/task-02-reuse-and-evidence-gate.md) | Spec027/028、确认、双评审 | 待执行 |
| 03 | 接通候选确认与既有批量导入 | [`task-03-acquisition-approval-import.md`](../plans/029/task-03-acquisition-approval-import.md) | 02 | 待执行 |
| 04 | 接通全文 RAG 与证据升级 | [`task-04-fulltext-evidence-upgrade.md`](../plans/029/task-04-fulltext-evidence-upgrade.md) | 03 | 待执行 |
| 05 | 实现导入进度与失败恢复界面 | [`task-05-acquisition-progress-ui.md`](../plans/029/task-05-acquisition-progress-ui.md) | 03、04 | 待执行 |
| 06 | 最终评审、回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/029/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/029-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/029-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/029-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建全文获取、导入复用与证据升级 Spec |
