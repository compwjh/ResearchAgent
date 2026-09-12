# Spec034 Task03 后端交付报告

状态：后端实现及 6 项 P1 修复完成；backend-reviewer/backend-tester 已 GO，跨端 Task03 验收已完成。

执行元数据：开始约 2026-09-13 05:28（Asia/Shanghai），结束约 2026-09-13 05:38（Asia/Shanghai），总耗时约 10 分钟；执行模型为当前执行 Agent 自身（本轮临时 Luna high 由主 Agent 指定）；使用 shell、apply_patch、pytest、py_compile、ruff；未使用网络、未 commit/push/merge/reset/stash/clean。

## 改动文件

- `.agents/skills/deep-research-orchestration/SKILL.md`：新增领域编排 Skill，不包含研发流程。
- `backend/app/research/application/intake.py`：新增 `ResearchIntakeCoordinator`、意图分类、两阶段 Skill 激活、Intake 字段抽取/持久化、默认值和冲突结果；复用现有 SkillRegistryService 与 ResearchStore。
- `backend/app/api/routes_conversations.py`：在现有 messages 主路径接入 Intake SSE；普通聊天保留原流，异常保存用户消息并返回稳定错误；将 Intake 安全投影写入既有 `processing_steps.detail_json`，消息查询按 owner 恢复并白名单过滤。
- `tests/test_spec034_task03_contract.py`：新增明确/含糊/普通请求、Skill 激活、阻塞字段、默认值、重复消息、活跃冲突及刷新恢复合同。
- `tests/test_conversations_api.py`：更新模型失败后消息仍持久化的既有回归断言。

## 验证

| 命令 | 退出码 | 通过数/结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py` | 0 | 12 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py tests/test_conversations_api.py` | 0 | 21 passed |
| `.venv/bin/python -m pytest -q tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | 78 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/research/application/intake.py backend/app/api/routes_conversations.py tests/test_spec034_task03_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/application/intake.py tests/test_spec034_task03_contract.py --output-format concise` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## P1-06 历史 Intake 投影修复轮（2026-09-13）

消息查询接口不再依赖内存中的 `IntakeResult` 或新建存储：`_intake_stream` 将 `status/fields/missing/choices/question/skill/session` 的脱敏快照持久化为既有 MemoryRepository processing step 的 `detail_json`，`GET /conversations/{id}/messages` 以消息 owner 约束读取，过滤未知状态、字段、choice 和 Skill 正文，并同时提供兼容的 `intake`/`research_intake` 键。普通消息没有 Intake 详情时不添加任何 Intake 字段。

本轮验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py tests/test_conversations_api.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | 106 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py tests/test_spec034_task03_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/api/routes_conversations.py tests/test_spec034_task03_contract.py` | 1 | 5 个 HEAD 已存在的基线诊断，无本轮新增诊断 |
| `git diff --check` | 0 | 通过 |

开始时间约 2026-09-13 05:28，结束时间约 06:20（Asia/Shanghai），本 Task 累计总耗时约 52 分钟。

## 决策

- 只在明确深度研究意图下创建 Session；“查一下”等含糊请求只追问，普通聊天不触发。
- `topic/objective/time_range` 是唯一阻塞字段；语言、来源、深度、输出、引用、约束使用可见系统默认值，并保留 source/confidence/confirmation_status/message_id。
- 激活流程先读摘要并检查 enabled，再加载全文；注册能力输入/输出 JSON Schema 固定在 `intake.py`，不新建 Tool/Skill Registry。
- 会话层不创建 ResearchTask、AgentRun、计划、搜索或报告；同会话新明确研究请求返回 `modify_current`、`cancel_then_new`、`new_conversation` 三选一。

## 风险与阻塞

- 尚未完成 backend-reviewer/backend-tester/跨端验收，故 Spec034/Task03 不标记完成。
- 模型不可用的真实 Planner/AgentRun 路径属于后续 Task；本批 Intake 不伪造模型成功，Coordinator 装配异常会保留用户消息并返回失败事件。
- 聚焦 Ruff 通过；未声称全量 Ruff 无基线告警。

## 主 Agent 后续动作

1. 运行 backend-reviewer 与 backend-tester，重点检查主会话流、跨库 owner 校验、重复消息和模型失败语义。
2. 补齐前端 Intake 展示后做跨端 smoke；确认不创建 ResearchTask/AgentRun。
3. 评审/验收通过后再将 Task03 状态台账更新为已完成并进入 Task04。

## P1 修复轮（2026-09-13）

backend-review 的 5 项 P1 已完成：

- Active Session 冲突以可交互 `intake` SSE 返回三种选择，助手消息保持 `completed`，不覆盖 Session。
- Coordinator/ResearchStore/Skill Registry 异常对普通聊天降级为原模型流，并持久化 `research_intake=failed` 诊断步骤；研究形状请求返回可重试错误。
- 消息/助手占位先写入 MemoryRepository，再执行模型与推理能力预检；失败返回真实错误 SSE，用户消息保留。
- Skill 激活固定 `deep-research-orchestration`，并校验声明 Tool 在既有 ToolRegistry 中存在且 enabled；返回 `skill_id/name/version/content_hash` 快照标识。
- 修复项目文档关联清除异常路径的未定义 `error`，恢复稳定 `DOCUMENT_ASSOCIATION_FAILED` 503 错误体。

修复轮验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py tests/test_conversations_api.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | 104 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py backend/app/research/application/intake.py tests/test_spec034_task03_contract.py tests/test_conversations_api.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/api/routes_conversations.py backend/app/research/application/intake.py tests/test_spec034_task03_contract.py tests/test_conversations_api.py --output-format concise` | 1 | 5 个既有基线诊断，无新增 P1/F821 |
| `git diff --check` | 0 | 通过 |
