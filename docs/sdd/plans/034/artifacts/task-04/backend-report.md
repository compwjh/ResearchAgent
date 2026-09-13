# Spec034 Task04 后端交付报告

状态：后端实现及 backend-review 6 项 P1、复审剩余 P1/P2 修复完成；backend-reviewer/backend-tester 已 GO，Task04 双端验收完成。

执行元数据：2026-09-13（Asia/Shanghai），约 30 分钟；执行模型为当前执行 Agent 自身（主 Agent 指定本轮 Luna high）；未使用网络、子 Agent、commit/push/merge/reset/stash/clean。

## 改动文件

- `backend/app/research/application/plan_authoring.py`：新增 `ResearchPlanOutput`、JSON Schema、output hash、无 CoT/URL/Shell/Python 的安全校验与既有 WorkItem DAG/预算语义校验。
- `backend/app/research/application/approval_service.py`：新增 Session 计划生成与六类统一命令 service；复用 ResearchStore、MemoryRepository、Skill Registry、Tool Registry；按钮/自然语言可共用 `command`/`execute_command`。
- `backend/app/research/domain/models.py`：新增 `ResearchSessionPlan`（Task 创建前可持久化的不可变版本实体）。
- `backend/app/research/domain/contracts.py`：允许所有非终态 Session 进入 `cancelled`。
- `backend/app/research/infrastructure/research_store.py`：v3 加性迁移 `research_session_plans`、`research_command_results`、`research_activity_outbox`、`research_plan_activations`；owner-scoped 计划/审批/命令幂等读写与可恢复 activation 锚点，并提供 task→session 解析。
- `backend/app/memory/repository.py`：增加 activity idempotency key 列与唯一索引；提供 activity message 创建/查询，跨库重试不重复 assistant message。
- `backend/app/api/routes_research.py`：Task detail 增加 `research_session_id`、当前/历史 Session plan 与 approval 安全白名单投影；无 Session 的历史 Task 保留原计划投影。
- `backend/app/research/application/entry.py`：受控导出计划 Schema/验证符号。
- `backend/app/api/routes_research.py`、`backend/app/api/routes.py`：新增 Session detail、计划写入和 `POST /api/research-sessions/{id}/commands` 适配。
- `tests/test_spec034_task04_contract.py`：Task04 合同测试扩展至 14 项，覆盖 activation/outbox/message 故障重试、递归 scope 安全策略与 Task detail 投影。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | 106 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/research/application/plan_authoring.py backend/app/research/application/approval_service.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py backend/app/api/routes_research.py backend/app/api/routes.py tests/test_spec034_task04_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check [Task04 改动文件] --output-format concise` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py` | 0 | 14 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_skill_registry.py tests/test_tool_registry.py` | 0 | 84 passed，6 subtests passed |
| `python -m py_compile [本轮后端改动文件]` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/memory/repository.py ...` | 1 | memory/repository.py 暴露 14 条既有基线告警；本轮新增研究文件聚焦 Ruff 通过，未扩大范围 |

## 关键决策

- 既有 `research_plans` 强制绑定 ResearchTask，不能承载批准前计划；因此新增 Session 计划表，旧 ResearchPlan/Spec027 路径保持兼容。
- `approve_plan` 是唯一创建 ResearchTask、WorkItem 和 activity assistant message 的命令；批准前 Session 无 Task。
- 命令响应落在独立 `research_command_results` 唯一键表，避免把命令重放伪装成第二个 Approval；相同幂等键返回第一次响应。
- 能力批准只接受已注册、启用、Skill 声明范围内的 Tool；禁用/未知/Shell/Python/任意 URL 均 fail-closed。无 AgentRunner、搜索、报告实现。
- 同一版本的第二个审批窗口在首个决策后返回 `APPROVAL_CONFLICT`；旧版本计划与待审批在结构性修订时标记 `superseded`。
- 计划 output hash 对去除 `output_hash` 后的规范 JSON 计算；输出字段拒绝 CoT、Prompt、可执行能力和 URL。

## P1 修复轮（backend-review 六项）

- P1-01：ResearchStore schema marker 升至 v3；旧 v2 数据库重开会在同一事务中补建 Task04 表，重复初始化幂等。
- P1-02：新增 `cancel_session_research` 单事务 CAS，planning/running Task 与 queued/running WorkItem 一并收敛 cancelled，不再吞掉非预期状态异常。
- P1-03：author 阶段解析 capabilities，要求注册且 enabled、Skill 声明范围内；保存 Skill/Tool name/version/schema content hash/entry/side-effect 与 resource limits 快照；approve_plan scope 仅允许当前版本/hash。
- P1-04：activity Saga 通过研究库 outbox 记录 pending/failed/completed；MemoryRepository 异常返回可重试 `SOURCE_UNAVAILABLE`，同幂等键重试不重复 Task/WorkItem/activity。
- P1-05：command result 身份绑定 owner + session + command + subject_version；版本先校验，跨 Session/命令返回 conflict，旧版本返回 stale。
- P1-06：计划校验补充非空唯一 WorkItem ID、依赖存在性、DAG 深度 ≤3、嵌入 URL/Prompt/CoT/执行能力及有界 section schema 拒绝。

## 复审剩余问题修复

- Activation 锚点：`research_plan_activations` 绑定 owner/session/subject_version/command key，使用确定性 Task ID；ResearchStore 的 `activate_plan` 在一个幂等事务内创建/恢复 Task、ResearchPlan、WorkItem 和 outbox，事务失败整体回滚，同 key 重试只补齐缺失记录，不产生第二个 Task/WorkItem，并把不可用错误稳定映射为 `SOURCE_UNAVAILABLE`。
- Activity 幂等：MemoryRepository 以 owner+conversation+activity key 唯一创建/查询 assistant message；outbox 或 Session link 更新失败时，重试复用既有消息并补偿 link。
- Scope 安全：command service 复用计划输出的递归校验，拒绝 casefold 后的 Prompt/CoT/chain-of-thought/执行键与 URL-like 值，并对六类命令施加显式顶层 allowlist。
- Task detail 投影：通过 ResearchStore owner-scoped task→session 解析复用 Session plan/approval 表；approval 只返回 request id、kind/status/version、requested/approved scope 与时间字段，不暴露幂等键或内部字段。

本轮实际验证：Task04 单测 `14 passed`；Task04 + Task02/03/Skill/Tool 定向回归 `84 passed，6 subtests passed`；py_compile、研究文件聚焦 Ruff、git diff-check 均退出码 0。MemoryRepository 聚焦 Ruff 退出码 1，报告保留 14 条既有基线告警。

## 风险/阻塞

- 计划/Task/Approval 与 MemoryRepository activity message 仍是跨库 Saga；研究库 activation/outbox 和 Memory activity key 已提供可重试锚点，但跨进程协调仍需上层调度器持续重放失败 outbox。
- `ResearchTask` 历史状态集合没有 `queued`，批准后以 `planning` 表示已激活但未启动；Session 使用规范的 `queued`，AgentRunner 启动留给 Task05。
- 计划生成 Skill 文件（`.agents/skills/research-plan-authoring/SKILL.md`）位于 backend-dev 明确禁止修改的范围之外，未在本分支代写；请主 Agent 按 Task04 范围补齐该领域 Skill（只描述研究计划编排，不写研发流程）。

## 主 Agent 后续动作

1. 复核 `ResearchSessionPlan` 字段与前端卡片契约，确认是否需要由主 Agent 落盘 `research-plan-authoring` Skill。
2. 运行 backend-reviewer/backend-tester，重点检查 activation/outbox 可恢复性、Memory activity 唯一键、CAS 原子性、能力快照字段及错误体。
3. 若评审通过，再由主 Agent 汇总 Task04 双端报告并更新任务状态台账；不要在本报告阶段标记 Spec034 完成。

进展日志：`.codebuddy/agent-logs/spec-034/task-04/backend-dev/20260913-000001.md`（含本轮步骤 11 起复审记录）
