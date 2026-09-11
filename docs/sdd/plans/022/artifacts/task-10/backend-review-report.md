# Task10 后端评审报告

## 结论

**NO-GO（P0=0，P1=6，P2=2）**。

SQLite v6 的基本迁移、owner 条件、SystemRule 独立表、CRUD 边界和原文门禁主路径已经落地，Task10 定向测试本身通过；但 T1/T2/T3/T4 的关键契约仍有实现缺口，不能进入跨端验收或 Spec022 收口。

## 评审范围与依据

- 角色：backend-reviewer（临时 Luna high）；只评审 `backend/**` 与 Task10 后端测试，未修改业务代码或测试。
- 依据：Spec022、`task-10-system-rule-project-memory-navigation.md`、T1–T6 技术复审、Task10 后端实现/测试报告、当前实际 diff。
- 重点：v6 migration 幂等/事务/owner/Unicode/空启用；SystemRule 与 MemoryRecord 隔离；role-aware 四类用户可见入口与后台隔离；global 原文门禁；fail-closed、稳定错误和发送快照。

## P1 问题

### P1-1：会话 SSE 在规则未启用时绕过 role-aware 接缝

- 证据：`backend/app/api/routes_conversations.py:272-287` 先构造 `messages`，但只有 `system_rule.enabled and system_rule.content` 时才传给 `run_chat()`；否则退回 `run_chat(..., prompt=prompt)`。
- 后果：默认无启用规则的会话把项目指令、普通记忆、RAG、历史和当前问题拼成一个 user 文本；当前问题不再是独立 user role，T1 要求的 advisory/system 与 user 隔离只在启用规则时成立。
- 建议：所有会话请求都走唯一 `messages` 接缝；将平台固定规则、可选 SystemRule、advisory context 和独立当前问题按冻结顺序组装，不能用 enabled 分支决定是否 role-aware。

### P1-2：四类入口没有实现完整的固定 system 层，KB 还重复把当前问题放入 system

- 证据：`backend/app/chat/application/conversation_service.py:208-216` 只追加用户规则和 advisory，没有平台固定规则；`backend/app/api/routes_kb.py:985-993` 使用 `build_prompt(question, hits)`，而 `backend/app/knowledge_base/infrastructure/prompts.py:42-50` 把 `问题：{question}` 写入该 system 内容后又追加独立 user 消息。
- 后果：T1 冻结的“平台固定规则 → 用户 SystemRule → advisory → 独立 user”顺序未完整实现；KB 模型收到重复问题，且问题文本仍存在于 system 内容中，削弱 role 边界和 prompt 注入隔离。
- 建议：为 KB 构造不含当前问题的 system/advisory 内容；统一加入明确的平台固定 system 消息，再把问题仅放在末尾 user 消息。

### P1-3：global 原文门禁拒绝已冻结的合法 fixture

- 证据：`backend/app/chat/application/conversation_service.py:45-52` 要求中文文本同时命中 `记住/偏好/遵守/以后` 与 global marker；`所有对话都使用中文` 不含这些中文 memory marker。
- 行为探针：

  ```text
  全局记住：以后所有项目都遵守先给结论 -> True
  所有对话都使用中文 -> False   # T2 明确要求允许
  remember this as a global preference -> True
  make this a preference for every project -> True
  ```

- 后果：合法全局偏好会被当成 project/pending，worker 与人工 `save_global` 无法按 T2 保存 global。
- 建议：为“所有对话都使用中文”等全局偏好动作增加确定性规则，并把 T2 全部允许/拒绝 fixture 固化到 worker 与人工决策测试。

### P1-4：用户 SystemRule/完整 Prompt 会被观测层保存

- 证据：`backend/app/api/routes_chat.py:65,76-77,101-102`、`routes_article.py:125,135-136,151-152`、`routes_kb.py:992,1009-1011,1027-1029` 将含完整消息内容的 `prompt_messages` 传给观测；会话路径同样在 `routes_conversations.py:277-283` 传递完整消息。`backend/app/platform/observability/spans.py:170-205,225-234` 将消息内容格式化并写入 generation input。
- 后果：违反 Spec/T1“观测不得保存完整 Prompt，只记录脱敏 role 数量与状态”，用户规则、历史、项目指令和知识库内容可能进入观测存储。
- 建议：观测调用只接收脱敏的 role 数量、是否启用规则、状态和长度等元数据；不得把原始 `content` 传入保存 input。

### P1-5：会话 SystemRule 读取失败时，持久化失败本身失败会吞掉稳定 SSE 错误

- 证据：`backend/app/api/routes_conversations.py:187-195` 捕获 `get_system_rule()` 异常后直接调用 `repo.update_message(...)`，该调用没有保护；若同一 SQLite 锁/损坏使 update 也失败，生成器在发送 `error`/`done` 前异常退出。
- 后果：T3 要求的稳定 `SYSTEM_RULE_UNAVAILABLE`、无 token、`done.status=failed` 不能得到保证；客户端可能只看到断流，且 assistant 状态仍为 pending/streaming。
- 建议：assistant 状态写入必须 best-effort、单独捕获异常；无论持久化是否成功，都发送稳定 error/done，且绝不能进入模型调用。

### P1-6：v6 结构校验不完整，能接受违反 DDL 契约的表

- 证据：`backend/app/memory/repository.py:451-459` 只核对列名、`owner_id` PK、`enabled` NOT NULL 和 CHECK；没有核对 `content`/`updated_at` 的 NOT NULL、默认值和类型。
- 行为探针：将 v6 表重建为 `updated_at TEXT`（可空）但保留现有检查条件后，`initialize()` 成功；插入 NULL 时间后 `get_system_rule()` 返回 `updated_at=None`，HTTP payload 会在 `.isoformat()` 处异常，而不是稳定 fail-closed。
- 后果：损坏 schema 未被启动迁移拒绝，违反 T4“结构校验”和 T3“无法确定状态时 fail-closed”。
- 建议：逐列核对类型、NOT NULL、默认值、PK、CHECK；校验失败统一回滚并抛 `SystemRuleUnavailableError`/启动 fail-closed。

## P2 问题

### P2-1：定向受影响后端回归存在可重复失败

- `tests/test_task10_backend.py`：4 passed。
- 合并受影响集合：53 passed，1 failed。
- 单独受影响集合 `tests/test_conversations_api.py tests/test_chat_route.py tests/test_task05_backend.py`：26 passed，1 failed。
- 失败：`tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse`，2 秒等待后 analysis job 仍为 `running`，违反测试对后台 job 终态的预期。该失败可能受本地异步 worker/外部 Ollama 环境影响，但在本次环境中重复出现，不能将受影响回归记为全绿。

### P2-2：role/fail-closed 覆盖证据不足

现有 Task10 自动测试仅直接断言 direct 路径的消息列表（`tests/test_task10_backend.py:55-67`）；没有对 LangGraph role payload、四类 HTTP/SSE 入口、后台分类/摘要/embedding/reranker 不注入，以及会话读取失败时“无 token + 稳定 error/done”建立自动契约。实现报告中的“人工 smoke”无法替代这些可重复证据。

## 已通过核对项

- v5→v6 使用逐语句 `BEGIN IMMEDIATE`/回滚，`CREATE TABLE IF NOT EXISTS` 可重复初始化；owner 主键、0/12,000/12,001 Unicode 长度、空启用、停用保留、DELETE 清空路径基本符合实现意图。
- SystemRule 使用独立 `SystemRule` 数据类和 `system_rules` 表，没有被 `MemoryRecord` 列表、召回、证据或计数 SQL 直接读取；API 不接受客户端 owner，统一使用服务端 `OWNER_ID`。
- worker 与人工决策路径均重新读取原始用户消息；普通绑定消息按发送时 project snapshot，未绑定普通消息保持 pending；`save_global` 对非明确 global 返回 `GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT`；系统规则表达拒绝自动写普通 MemoryRecord。
- `get_system_rule()` 读取异常会转为 `SystemRuleUnavailableError`，旧 chat、Agent chat 和 KB ask 在模型调用前有 `SYSTEM_RULE_UNAVAILABLE` 分支；这些分支仍需补齐会话持久化异常和完整入口自动测试。

## 精确验证

| 检查 | 命令 | 结果 |
|---|---|---|
| Task10 后端 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task10_backend.py --tb=short` | 退出码 0，4 passed |
| 受影响后端 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_conversations_api.py tests/test_chat_route.py tests/test_task05_backend.py --tb=short` | 退出码 1，26 passed / 1 failed |
| 合并受影响集合 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_task05_backend.py --tb=short` | 退出码 1，53 passed / 1 failed |
| 语法 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile ...`（Task10 后端改动文件） | 退出码 0 |
| 差异空白 | `git diff --check -- ...`（Task10 后端改动文件） | 退出码 0 |
| global fixture 探针 | `.venv/bin/python` 调用 `has_explicit_global_intent()` | 合法 fixture `所有对话都使用中文` 错误返回 False |
| schema 损坏探针 | 临时 SQLite：v6 表 `updated_at` 可空并插入 NULL | `initialize()` 错误接受，读取返回 `updated_at=None` |

## 后续动作

1. 先修复并补测 P1-1 至 P1-6，再重新提交 backend reviewer；在此之前不进入跨端 acceptance。
2. 为 T1/T3/T4/T2 增加可重复自动测试，尤其是 LangGraph、四入口、后台隔离、无 token fail-closed 和全部 global fixture。
3. 修复或解释 P2-1 的 analysis worker 终态回归后，重跑本报告列出的精确测试；Task08 阶段再运行全量回归、部署和运行时 smoke。

## 评审元数据

- 评审时间：2026-09-11（Asia/Shanghai）
- 评审日志：`.codebuddy/agent-logs/spec-022/task-10/backend-reviewer/20260911-review.md`
- 业务代码改动：无
- 最终签字：backend-reviewer（**NO-GO**）

---

## 第二轮复审（P1-1 至 P1-6 整改后）

### 结论

**GO（P0=0，P1=0，P2=2）**。

上一轮六项 P1 均已在实际 diff 中完成修复，且用户指定的后端精确测试本轮全绿。允许进入跨端 acceptance；不等同于 Spec022 已完成，仍需按收口流程执行跨端验收、全量回归、部署和运行时 smoke。

### P1 逐项复核

1. **P1-1 role-aware 会话：已修复。** `backend/app/api/routes_conversations.py:270-281` 无条件通过 `compose_chat_messages()` 和 `run_chat(..., messages=messages)`；`backend/app/chat/application/chat_runner.py:33-45` 固定加入 platform system、可选 SystemRule/advisory、历史 role，当前问题独立为最后 user。新增 `tests/test_task10_backend.py:76-80` 覆盖无规则会话。
2. **P1-2 固定 system 与 KB 问题隔离：已修复。** `chat_runner.py:28-45` 提供稳定平台 system；`routes_kb.py:63-76,998-1008` 使用只含证据的 `_kb_evidence_advisory()`，当前问题只在最后 user；`tests/test_task10_backend.py:83-88` 与 `tests/test_kb_ask_trace.py:90-103` 均断言 system 内容不含当前问题。
3. **P1-3 global fixture：已修复。** `conversation_service.py:44-52` 增加“所有对话都/所有项目都”等动作表达；`tests/test_task10_backend.py:48-58` 覆盖允许 fixture 和拒绝项（含 `所有对话都使用中文`、`全局搜索这篇论文`、`所有对话都不要保存`）。绑定/未绑定 worker 与人工决策仍以原文门禁为授权依据。
4. **P1-4 观测脱敏：已修复。** 四个用户可见入口传入 `redact_prompt_messages()`；`backend/app/platform/observability/spans.py:170-182,240-255` 在观测 seam 再次强制清空 content，仅保留 role、数量、字符统计和规则启用状态。`tests/test_task10_backend.py:100-110`、`tests/test_chat_route.py:143-169`、`tests/test_kb_ask_trace.py:86-103` 覆盖脱敏。
5. **P1-5 fail-closed best-effort：已修复。** `routes_conversations.py:187-199` 对 assistant failed 持久化单独捕获异常，并始终输出 `meta → error(code=SYSTEM_RULE_UNAVAILABLE) → done(status=failed)`；补充行为探针确认即使 `update_message()` 也失败仍无模型调用、无 token、稳定错误事件。
6. **P1-6 v6 损坏表逐列校验：已修复。** `repository.py:457-477` 校验列集合、类型、NOT NULL、默认值、PK 和 CHECK；`repository.py:164-173,480-501` 仅修复明确的历史 nullable-PK 形状，其余损坏 fail-closed。补测可空 `updated_at`/错误类型表会拒绝启动；`tests/test_task10_backend.py:90-97` 覆盖损坏表。

### 第二轮验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 用户指定精确后端集合 | `./.venv/bin/python -m pytest -q tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_task05_backend.py` | 退出码 0，64 passed |
| 语法 | `./.venv/bin/python -m py_compile`（Task10 后端改动文件） | 退出码 0 |
| 差异空白 | `git diff --check` | 退出码 0 |
| 会话 fail-closed 探针 | `get_system_rule()` 与失败持久化同时抛错 | 稳定 error/done failed，无 token，模型未调用 |
| v6 损坏 schema 探针 | 可空 `updated_at` 的近似 v6 表 | `MemoryRepository` 拒绝启动并 fail-closed |

### P2 保留项

1. **后台 analysis worker 时序性 flaky（P2）。** 更新报告记录过组合运行中 `test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse` 的 `running` 状态，但该用例独立重跑通过；本轮用户指定组合命令 64 项全绿。建议在收口阶段继续观察，不阻断本轮 backend GO。
2. **入口覆盖仍有少量测试空白（P2）。** 已有 direct、无规则会话、KB、观测和损坏 schema 自动断言，但四个 HTTP/SSE 入口分别模拟 SystemRule 读取失败、后台分类/摘要/embedding/reranker 明确不含规则的矩阵仍主要依赖静态核对与人工 smoke。建议在最终验收前补齐，不构成当前已确认的 P1。

### 第二轮签字

- 评审时间：2026-09-11（Asia/Shanghai）
- 精确测试：64 passed
- 评审日志：`.codebuddy/agent-logs/spec-022/task-10/backend-reviewer/20260911-review.md`
- 业务代码改动：无
- 最终结论：backend-reviewer **GO**
