# Spec034 Task03 后端复审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task03 — 会话意图、Deep Research Skill 与 Intake
- reviewer：backend-reviewer（当前执行 Agent）
- review_base：当前工作树相对 `1879fb3` 的实际差异；Task03 路由差异同时与 `7030f9f` 对照
- review_scope：主消息流、Intake coordinator、Skill/Tool Registry 复用、Task02 ResearchStore、错误/幂等/owner 边界；只读复审
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=1（仅既有 Ruff 基线诊断）

## 结论

GO。针对上一轮 5 项 P1 的复审均通过，且新增合同测试覆盖了关键回归路径。活跃 Session 冲突会通过 `intake` SSE 返回 `modify_current`、`cancel_then_new`、`new_conversation` 三选一，助手消息保持 `completed`；ResearchStore/Skill/Intake 故障下普通消息继续既有 `_message_stream`；用户/助手消息先持久化再执行模型与推理能力预检，模型失败保留用户消息并发出真实错误；Skill 激活固定为 `deep-research-orchestration` 并复用既有 Skill/Tool Registry 做启用和声明工具校验；项目文档关联清除失败返回稳定 503 且不删除项目。

复审新增的历史投影也通过：只对 assistant 消息读取其 owner 过滤后的 `research_intake` processing step，普通消息不附加 Intake，投影白名单不包含 Skill 正文。未发现新的 P0/P1，也未发现与 Spec027/022/023 重复实现或破坏既有主消息流的 Task03 缺陷。

## 复审证据

### 已关闭的上一轮 P1

1. **冲突 SSE 三选一：已修复**
   - 位置：`backend/app/api/routes_conversations.py:767-789`；结果由 `backend/app/research/application/intake.py:295-309` 产生。
   - `_intake_stream` 先处理 `active_conflict`，发送 `intake` 事件及三个 choice，并将助手更新为 `completed`；不会再被同时存在的冲突 `error` 提前序列化为 failed。
   - 合同测试：`tests/test_spec034_task03_contract.py:173-193`，实际消费生成器并断言三种 choice 与助手状态。

2. **普通聊天故障回退：已修复**
   - 位置：`backend/app/api/routes_conversations.py:932-967`。
   - Coordinator 异常时，明确/含糊研究请求返回可重试 `INTAKE_UNAVAILABLE`；普通请求持久化 `research_intake=failed` 诊断步骤后继续既有 `_message_stream`，不把研究依赖故障伪装为模型失败。
   - 合同测试：`tests/test_spec034_task03_contract.py:217-244`，注入损坏 coordinator 并断言原始聊天流和用户消息仍存在。

3. **消息先落库：已修复**
   - 位置：`backend/app/api/routes_conversations.py:875-913`。
   - `create_conversation_messages/create_message_pair` 先原子创建 user/assistant 占位，之后才调用 `_validate_model` 与 `_resolve_request_effort`；预检的 HTTPException 通过 `_failed_message_stream` 更新 assistant 并发真实错误 SSE。
   - 合同测试：`tests/test_spec034_task03_contract.py:196-215`，模型预检失败后断言会话与用户消息仍可读取。

4. **Skill/Tool 目标锁定与启用校验：已修复**
   - 位置：`backend/app/research/application/intake.py:117-174`；装配位置 `backend/app/api/routes_conversations.py:72-83`。
   - `activate_skill` 只接受固定 `deep-research-orchestration`；先读取 summary 并检查 Skill enabled，再读取正文；对 frontmatter 声明的每个 Tool 查询既有 `ToolRegistryService`，要求存在且 enabled，缺少 Registry 或非法声明 fail-closed。路由复用现有 `build_default_tool_registry()` 和 `SkillRegistryService`，未创建第二套注册表。
   - 结果含 `skill_id/name/version/content_hash` 快照标识；真实 Skill 的 `tools: []` 与 Task03 的 Intake capability 边界一致，不把搜索/下载 Tool 偷渡进会话层。
   - 合同测试：`tests/test_spec034_task03_contract.py:152-170`，覆盖固定目标和未知声明 Tool 拒绝。

5. **项目删除稳定错误：已修复**
   - 位置：`backend/app/api/routes_conversations.py:249-259`。
   - 文档关联清除和 Spec027 研究级联删除异常均绑定为 `error`，返回稳定 503 错误体；清除失败在 `_repo().delete_project` 前 fail-closed，项目保留。
   - 合同测试：`tests/test_spec034_task03_contract.py:247-260`，注入关联清除失败并断言 `DOCUMENT_ASSOCIATION_FAILED`。

6. **历史 Intake 投影与安全边界：已修复**
   - 位置：`backend/app/api/routes_conversations.py:104-193,196-255,1193-1202`。
   - `_intake_stream` 将字段、阻塞项、choice、研究 Session 摘要和 Skill snapshot 元数据写入既有 `research_intake` processing step；不写入 Skill body。历史消息仅对 assistant 查询同 owner 的 processing step，并通过 schema/status、字段名、choice ID、Skill ID 白名单过滤，再同时提供兼容的 `intake`/`research_intake` 字段。
   - 普通消息没有 `research_intake` detail，不会被误标记；跨 owner 的消息/步骤由既有 owner 过滤和 `list_processing_steps` join 拒绝读取。合同测试：`tests/test_spec034_task03_contract.py:264-310`，覆盖刷新恢复、普通消息无 Intake、字段 provenance 和正文不泄露。

### 其他合同核对

- `ResearchIntakeCoordinator` 只创建/恢复 `ResearchSession`、Draft 和 IntakeField，不创建 ResearchTask、AgentRun、计划、搜索或报告；研究写入经 Task02 `ResearchStore`，会话写入经既有 `MemoryRepository`。
- `topic/objective/time_range` 仍是唯一计划前阻塞字段；默认字段带 `source/confidence/confirmation_status/updated_by_message_id`，重复同一 `message_id` 不重复创建 Session 或重写 provenance；跨消息 follow-up 可恢复并补齐 Draft。
- 普通、含糊和明确意图路径保持既有约定；含糊请求只澄清，普通请求无研究 Session；真实 Skill 文档明确不执行搜索、下载、导入、模型运行，也不授权 Shell/Python/任意公网 URL。
- API 请求仍使用既有 `ConversationMessageRequest` 的 Pydantic 字段约束，Intake 两个结构化 capability 在 `intake.py:39-91` 有明确 input/output JSON Schema。
- 未见新增独立 Skill/Tool 管理、研究执行器或替代 Spec027/022/023 的实现；路由只做组合、分流和 SSE 投影。
- 历史投影只保留 UI 所需安全摘要（字段值、来源、置信度、确认状态、Session ID、Skill snapshot 标识），不回传完整 Skill body、Prompt 或隐藏内容。

## P2

### P2-01：改动目标文件仍有既有 Ruff 基线告警

- `.venv/bin/ruff` 可用。Task03 后端目标集（`routes_conversations.py`、`intake.py`、合同测试）有 5 个 `routes_conversations.py` 既有基线诊断；`intake.py` 与合同测试无诊断。未发现本轮历史投影改动引入的新诊断。
- `intake.py` 与 `tests/test_spec034_task03_contract.py` 单独 Ruff 通过。
- 最小建议：后续独立 lint 清理中处理基线告警；不阻塞本 Task03 评审结论。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py tests/test_conversations_api.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | 106 passed，6 subtests passed，11.82s |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py backend/app/research/application/intake.py tests/test_spec034_task03_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/api/routes_conversations.py backend/app/research/application/intake.py tests/test_spec034_task03_contract.py --output-format concise` | 1 | 5 个既有 `routes_conversations.py` 基线诊断；`intake.py` 与合同测试无诊断 |
| `git diff --check 1879fb3 --` | 0 | 通过 |

## 复审边界

- 本次仅读取代码、测试和文档并更新本报告；未修改业务代码、Spec 或状态台账，未 commit/push/merge/reset/stash/clean。
- Ruff 退出码 1 由基线告警造成；不存在新的 Task03 P0/P1 lint 回归。
