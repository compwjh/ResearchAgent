# Spec022 Task03 后端实现报告

## 结果状态/摘要

已完成（后端范围）。在 Task02 冻结的单一 `MemoryRepository`、SQLite 数据库和 SSE/chat adapter 上完成 Task03 管理与全局记忆增量：项目/会话生命周期操作、跨项目绑定约束、全局与项目记忆作用域召回、记忆治理和可追溯来源接口均已实现。

## 改动文件

- `backend/app/memory/repository.py`
- `backend/app/memory/models.py`
- `backend/app/chat/application/conversation_service.py`
- `backend/app/api/schemas.py`
- `backend/app/api/routes_conversations.py`
- `tests/test_memory_repositories.py`
- `tests/test_conversations_api.py`

## 接口/契约

- schema version 从 1 版本化扩展至 2；v1→v2 在同一连接显式事务中读取当前版本、执行真实结构迁移并统一 rollback/fail-closed；仍使用 `data/memory/memory.sqlite3`、WAL、事务和同一 repository。
- v2 持久化会话绑定切换时间/消息边界，并为 `memory_evidence.message_id` 增加 `ON DELETE SET NULL` 外键；旧 Task03 草稿标记为 v2 但缺列/FK 时会在启动事务内修复。
- 保留项目/会话既有 CRUD；增加稳定会话 `GET /api/conversations/{conversation_id}`、项目/会话 `POST .../{id}/restore`；PATCH 会话支持 `project_id=null` 解绑、跨项目移动和 `from_binding/include_prior_history`，服务端校验目标项目与 owner。
- `POST/GET/PATCH/DELETE /api/memories[/{memory_id}]` 支持 global/project scope、candidate/active/disabled/deleted 等治理状态；内容编辑创建新版本并设置 `supersedes_id`，旧记录保留 superseded 审计。
- 增加 `POST /api/memories/{id}/confirm`、`/undo`（及 `/restore` 别名）和 `GET /api/memories/{id}/evidence`（及 `/source` 别名）。
- 聊天显式声明 global（如“请记住我…全局”）才写全局记忆；未绑定会话不把项目经验静默升格全局；召回顺序为 global → 当前 project。

## 决策依据

- 复用 Task02 的 `Project/Conversation/Message/MemoryRecord/MemoryEvidence` 表和外键，不创建第二套 store；schema v2 通过显式迁移补齐绑定边界列、scope/status 索引及 message evidence 的 `ON DELETE SET NULL` 约束。
- 项目删除沿用单事务硬删除触发外键级联：项目会话、消息、processing steps、项目记忆随项目删除；global memory 的 `project_id` 为空而保留。会话删除仍软删除，不联动记忆。
- owner 由 API 的服务端 `OWNER_ID` 装配，repository 的证据写入额外校验 memory/conversation/message 同 owner，避免客户端跨 owner 关联。
- 跨项目移动已有消息必须携带 `confirm_move=true`；`from_binding` 只装配切换时间之后的消息，`include_prior_history` 仅在确认后允许。移动时解绑旧项目记忆 evidence，global evidence 仍可关联同 owner 会话。
- memory recall/mark-used 为 advisory；单条使用记录失败仅产生 skipped/failed 事件并继续 generation。流 generator 的 `GeneratorExit`/`finally` 保存已生成内容、置 assistant 为 interrupted 并记录失败处理步骤。
- 复审修复：解绑已有会话时将 `memory_binding_at` 更新为解绑 cutoff 而非清空；`from_binding` 因此不会重新装配解绑前项目消息，cutoff 后的未绑定新消息仍可正常聊天。

## 风险/阻塞

- 未实现自动候选抽取、摘要、项目文档、手机端或 Skill 修改，符合 Task03 明确不做。
- “撤销”采用治理状态恢复：删除先标为 `deleted`，`/undo` 恢复为 active；原始版本和 evidence 不被物理抹除。
- 模型/工具统计在当前子代理运行时不可用，报告按要求标记为 unavailable；未执行全量回归、部署或前端测试。
- 记忆召回读取异常会落盘 `memory_recall=failed` 并以空记忆继续普通聊天；项目明确指令在 prompt 中置于 global/project 记忆之前。

## 主 Agent 后续动作

- 运行 backend reviewer 检查事务、owner/project scope、迁移兼容性和 API 错误码。
- 与 frontend-dev 对齐 memory 列表/来源/确认/编辑/停用/删除/撤销端点。
- 汇总前后端验收后再按 Spec022 收口流程执行全量回归、部署和运行时 smoke。

## 测试与产物

- 精确测试报告：`docs/sdd/plans/022/artifacts/task-03/test-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-022/task-03/backend-dev/20260911-043143.md`

## 运行信息

- 开始：2026-09-11 04:31:43（Asia/Shanghai）
- 结束：2026-09-11 05:03:14（Asia/Shanghai）
- 总耗时：约 32 分钟（含 NO-GO 修复与复审修复）
- 模型：临时 Luna high（按主 Agent 分派）
- token 统计：当前子代理运行时不可用
- 工具统计：文件读取/补丁/命令执行；精确数量未由运行时提供
