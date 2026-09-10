# Spec022 Task03 后端最终复审报告

## 结论

**GO**。此前 P1 阻塞已修复，Task03 后端可进入后续验收整合；本报告仅覆盖后端定向范围，不代表全量回归、前端验收或部署已完成。

## 严重级别汇总

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 未发现 P0 |
| P1 | 0 | 之前解绑历史边界阻塞已关闭 |
| P2 | 0 | 本次未发现新增 P2 |

## 最后 P1 复核：项目解绑与未绑定新消息

- 代码证据：`backend/app/memory/repository.py:323-340` 对所有 `project_changed`（包括 project→unbound）写入 `memory_binding_at`，不再把解绑 cutoff 置空。
- 代码证据：`backend/app/memory/repository.py:418-431` 在 `from_binding` 且存在 cutoff 时使用 `created_at > memory_binding_at`，因此解绑前的项目历史被排除，cutoff 后新增的未绑定消息仍可进入上下文。
- 测试证据：`tests/test_memory_repositories.py:196-207` 创建旧项目消息，确认解绑后断言上下文为空，再创建 cutoff 后的新未绑定消息并断言只有新消息可见。
- 独立只读探针：project→unbound 后输出 `project_id=None`、非空 `binding_at`、旧上下文为空；新增消息后仅新增消息出现在 `list_context_messages()` 中。
- 结论：**通过**。满足移动/解绑确认、旧项目上下文隔离和新未绑定消息可用的边界。

## 重点检查结论

| 检查项 | 结论 | 文件/行号证据 |
|---|---|---|
| schema v2 幂等迁移与旧 v1 数据兼容 | **通过** | `repository.py:92-121` 显式事务、版本读取、rollback/fail-closed；`176-203` v1→v2 迁移；测试覆盖真实 v1 升级与异常回滚。 |
| owner/project scope 隔离 | **通过** | recall 使用 owner+global/current project（`repository.py:490-503`）；evidence 校验 memory/conversation/message 项目（`563-585`）；跨项目测试通过。 |
| 全局优先级且当前指令不被覆盖 | **通过** | global→project 排序（`repository.py:490-503`）；项目指令在长期记忆前、当前问题最后（`conversation_service.py:59-70`）。 |
| 项目删除事务级联、全局记忆保留 | **通过** | 删除事务 `repository.py:253-256`；FK cascade、evidence message `SET NULL`（`135-195`）；测试验证 global 保留与 message_id 清理。 |
| 会话删除不联动记忆 | **通过** | `delete_conversation` 仅软删会话（`repository.py:353-356`）。 |
| 编辑版本化保留 superseded | **通过** | 内容编辑创建新 ID、旧记录 superseded、复制 evidence（`repository.py:505-534`）。 |
| 撤销语义 | **通过** | deleted→active undo，来源不物理删除（`repository.py:544-555`）。 |
| 会话绑定/移动确认 | **通过** | `confirm_move` 与 project→project/project→unbound cutoff（`repository.py:306-348`、`418-431`）；API schema 接受确认字段（`schemas.py:36-41`）。 |
| SSE 兼容与错误降级 | **通过定向范围** | meta/progress/memory/token/error/done 主路径和 advisory mark-used（`routes_conversations.py:98-181`）；GeneratorExit/finally 保存 interrupted（`182-205`）。 |

## 已复核的修复闭环

| 原阻塞 | 复审结果 |
|---|---|
| 迁移非原子、v1 兼容不足 | 已关闭；真实 legacy 升级和注入失败回滚测试通过。 |
| project→project 无确认、历史策略无效 | 已关闭；缺确认 409，from_binding/include_prior_history 行为有测试。 |
| project evidence 跨项目 | 已关闭；拒绝跨项目，允许同 owner global evidence。 |
| mark-used 阻断聊天 | 已关闭；失败发送 skipped/failed 并继续 done。 |
| GeneratorExit 遗留 streaming | 已关闭；finally 保存内容并置 interrupted。 |
| 删除项目后 global evidence 悬空 message_id | 已关闭；v2 FK 使用 `ON DELETE SET NULL`。 |
| scope/project 参数错误语义 | 已关闭；冲突 400、缺失/不存在项目 404。 |
| project→unbound 旧历史泄漏 | 已关闭；保留 cutoff，新增未绑定消息可装配。 |

## 测试命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/memory/repository.py backend/app/memory/models.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 0 | 20 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_api.py` | 0 | 16 passed |
| 补充只读探针：project→unbound cutoff 与 cutoff 后新消息 | 0 | 旧消息排除，新消息保留 |

按要求未运行全量 pytest、前端测试、部署或真实端到端演示。

## 风险

- 本轮后端定向范围无 P0/P1/P2 阻塞。
- 全量验收仍需由 tester 覆盖跨端用户旅程、前端契约及部署 smoke。
- 当前 prompt 仍以单一文本承载项目指令/长期记忆/当前问题；现有排序满足本 Task 契约，但后续可进一步结构化隔离不可信记忆文本。

## 主 Agent 后续动作

1. 采用本报告 GO 结论，继续前端评审与跨端验收整合。
2. 保留新增 cutoff、迁移回滚、evidence、mark-used 和断流测试，作为 Task03 收口回归。
3. 按 Spec022 流程在最终收口阶段执行全量回归、验收评审、部署和运行时 smoke；本次 backend-reviewer 不执行这些动作。

## 运行信息

- 评审角色：backend-reviewer
- 模型：临时 Luna high（按主 Agent 分派）
- 开始：2026-09-11 05:04:03（Asia/Shanghai）
- 结束：2026-09-11 05:06:00（Asia/Shanghai，报告写入时）
- 耗时：1 分 57 秒
- 模型 token 统计：运行时不可用
- 工具统计：运行时未提供精确计数；使用文件读取、只读检索、py_compile、pytest 与临时只读探针
- 进度日志：`.codebuddy/agent-logs/spec-022/task-03/backend-reviewer/20260911-044208.md`
