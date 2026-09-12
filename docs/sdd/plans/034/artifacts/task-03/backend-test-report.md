# Spec034 Task03 后端验收报告

## 结论

**GO（后端验收通过）**。Task03 合同、conversations、Skill/Tool Registry 定向测试，目标文件编译检查，以及六类隔离临时存储运行时探针均通过。

保留项为既有 Ruff 基线诊断：扩展目标文件集共 19 个（`routes_conversations.py` 5 个、`memory/repository.py` 14 个），Task03 新增 `intake.py` 与合同测试专项 Ruff 通过；无 P0/P1 阻塞。

本轮未修改业务代码、测试代码或 Spec，未 commit/push/merge/reset/stash/clean。

## 验收范围

- 明确/含糊/普通意图分流，ResearchSession/Intake 创建与冲突三选一。
- 普通聊天在 Intake 依赖故障时 fallback，并写入可诊断的 `research_intake=failed` 步骤。
- 消息/助手占位先落库，模型预检失败后保留用户消息并返回真实错误。
- `deep-research-orchestration` Skill 固定目标、摘要→启用检查→全文激活，以及声明 Tool 的 enabled 校验。
- 项目文档关联清除失败的稳定 503 错误路径和项目保留。

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task03_contract.py tests/test_conversations_api.py` | 0 | **26 passed**（2.25s） |
| `.venv/bin/python -m pytest -q tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py` | 0 | **78 passed，6 subtests passed**（9.82s） |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py backend/app/api/routes_research.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/research/application/intake.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task03_contract.py tests/test_conversations_api.py` | 0 | 通过 |
| `git diff --check 1879fb3 --` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/application/intake.py tests/test_spec034_task03_contract.py --output-format concise` | 0 | 新增 Intake/合同测试专项通过 |
| `.venv/bin/ruff check backend/app/api/routes_conversations.py backend/app/api/routes_research.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/research/application/intake.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task03_contract.py tests/test_conversations_api.py --output-format concise` | 1 | 19 个既有基线诊断；无新增 Task03 诊断 |

## 运行时探针

使用 `TemporaryDirectory` 创建隔离的 MemoryRepository、ResearchStore 和 SkillRegistry，命令为：

```bash
TMPDIR=/private/tmp .venv/bin/python - <<'PY'
# 运行六类断言探针并输出 PASS 行
PY
```

退出码：**0**。通过项目如下：

1. 明确研究请求进入 Intake，主题/目标/时间范围全部提取；含糊“查一下”只返回 clarification，不创建 Session。
2. 同会话第二个明确研究请求返回 `active_conflict`，包含 `modify_current`、`cancel_then_new`、`new_conversation` 三个 choice，已有 Session 不被覆盖。
3. 普通聊天在 Coordinator 抛出故障时继续原模型流，并持久化 `research_intake` failed 诊断步骤。
4. 模型预检失败后，用户消息和助手占位已存在，SSE 返回 `MODEL_UNAVAILABLE`。
5. 只能激活固定 `deep-research-orchestration`；Skill 声明未知/未启用 Tool 时 fail-closed，返回 `CAPABILITY_NOT_AUTHORIZED`。
6. 项目文档关联清除失败返回 HTTP 503 / `DOCUMENT_ASSOCIATION_FAILED`，项目仍保留。

普通聊天 fallback 探针会由路由记录预期的 `logger.exception` traceback；该日志是故障诊断，探针 SSE、消息持久化和处理步骤断言均通过。

## 阻塞与遗留

- **无 P0/P1 阻塞；验收 GO。**
- P2：扩展目标文件 Ruff 共 19 个既有诊断：`routes_conversations.py:51,535,599,632,683` 及 `memory/repository.py:661,676,696,710,1044-1048`。Task03 新增 `intake.py` 和合同测试无 Ruff 诊断；不在本 Task03 范围修复无关技术债。
- 未运行全量 pytest，遵循 Task03 后端定向验收边界。

## 进展日志

`.codebuddy/agent-logs/spec-034/task-03/backend-tester/20260913-052900.md`
