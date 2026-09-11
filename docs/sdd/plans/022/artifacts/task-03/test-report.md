# Spec022 Task03 后端测试报告

## 结果状态/摘要

通过（后端定向范围，含 NO-GO 与复审修复）。Task03 新增管理、global/project 记忆作用域、召回优先级、版本化编辑、删除撤销、级联删除、全局 SSE 召回、真实 v1→v2 迁移回滚、移动/解绑确认与历史边界、evidence 越界、advisory mark-used、断流和 scope 错误测试均通过；Task02 原有 memory/conversation 流程和旧聊天入口兼容回归通过。

## 命令与结果

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Python 语法 | `python -m py_compile backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py` | 0；通过 |
| Task03/Task02 精确后端回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 0；20 passed |
| 旧聊天兼容回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_api.py` | 0；16 passed |

## 覆盖项

- global/project 记忆创建、owner 隔离与 global 优先于 project 的召回顺序。
- 内容编辑生成新 memory ID、旧版本 superseded、证据保留；candidate 确认、删除与撤销恢复。
- 删除项目级联会话/消息/项目记忆并保留 global memory；单会话删除不联动记忆。
- API 项目/会话移动、历史策略、稳定 GET URL、归档恢复，以及 memory CRUD/action/source 端点。
- 未绑定会话的明确 global 写入与后续全局 recall；Task02 项目记忆隔离及旧 `/api/chat`、`/api/agent/run` 回归。
- 项目明确指令在 prompt 中高于长期记忆；记忆召回失败路径保留 failed processing step 并允许聊天继续（代码路径检查）。
- v1 数据库真实升级至 v2；注入迁移异常保持 schema version=1 且无半成品列；message evidence 在项目删除后 message_id 置 NULL。
- 跨项目移动无确认返回 409，确认后 from_binding 隔离旧历史、include_prior_history 可装配旧历史；跨项目 evidence 被拒绝，global evidence 允许同 owner 会话。
- mark_memory_used 注入失败不阻断 SSE done；关闭 generator 后 assistant=interrupted 且有稳定 generation failed step。
- 解绑已有会话后 `project_id=null` 且 `memory_binding_at` 保留 cutoff，旧项目消息不再进入上下文；cutoff 后未绑定新消息可正常装配。

## 未执行/阻塞

- 未运行全量 pytest、前端静态/浏览器测试、部署和真实端到端演示；这些属于主 Agent/后续验收阶段。
- 当前无测试阻塞；模型/token/工具精确统计由子代理运行时不可用。

## 主 Agent 后续动作

- 交给 backend-reviewer 做一次后端安全/事务/迁移评审；如发现 P0/P1，回到本 Task 定向修复后复测。
- 与前端端点契约整合，最后由 tester 执行 Spec022 验收矩阵。

## 产物路径与运行信息

- 实现报告：`docs/sdd/plans/022/artifacts/task-03/implementation-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-022/task-03/backend-dev/20260911-043143.md`
- 开始：2026-09-11 04:31:43（Asia/Shanghai）
- 结束：2026-09-11 05:03:14（Asia/Shanghai）
- 总耗时：约 32 分钟（含 NO-GO 与复审修复）
- 模型：临时 Luna high（按主 Agent 分派）
- token 统计：当前子代理运行时不可用
- 工具统计：pytest/py_compile/读取/补丁；精确数量未由运行时提供
