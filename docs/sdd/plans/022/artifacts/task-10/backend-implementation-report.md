# Task10 后端实现报告

## 结果摘要

已完成后端范围：SQLite v5→v6 独立 `system_rules`、SystemRule CRUD、发送时快照与 `SYSTEM_RULE_UNAVAILABLE` fail-closed、原文 global scope 门禁、绑定项目 project-first、未绑定待确认、以及四类用户可见模型入口的 role-aware 载荷接缝。SystemRule 不进入 MemoryRecord、召回、证据或计数。

## 实际改动文件

- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/chat/application/conversation_service.py`
- `backend/app/chat/application/chat_runner.py`
- `backend/app/chat/application/chat_graph.py`
- `backend/app/platform/ollama_direct.py`（本轮未需改动；复用现有 messages 接口）
- `backend/app/api/schemas.py`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/routes_chat.py`
- `backend/app/api/routes_article.py`
- `backend/app/api/routes_kb.py`
- `backend/app/platform/observability/spans.py`
- `backend/app/platform/observability/__init__.py`
- `tests/test_task10_backend.py`

未新增业务文件。未修改 frontend、论文下载/知识库存储、Task ledger、分类器或队列。

## T1–T4 实现决策

- `run_chat(..., messages=...)` 是唯一 role-aware 接缝；direct 路径将消息列表原样交给既有 `chat_direct_stream`，LangGraph graph 同样消费消息列表。无论用户规则是否启用，入口均保持独立 platform/advisory `system` 与当前 `user`。
- `MemoryRepository.get_system_rule()` 只按服务端 owner 查询；不存在记录返回空 disabled 快照。SQLite 异常统一转 `SystemRuleUnavailableError`，各用户可见入口在首个模型调用前以稳定 code 失败关闭。
- `system_rules.owner_id` 为主键；内容按 Python Unicode code point 校验 0–12,000，超长不截断；PUT 超长 400、空内容启用 409、停用保留内容、DELETE 清空并停用。
- 原始消息 `has_explicit_global_intent()` 是 global 唯一授权信号；“记住我喜欢……”和“设为系统规则”均不能升格 global。绑定消息强制项目快照，未绑定普通意图保持 pending；人工 `save_global` 重复执行同一门禁并返回 `GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT`。
- 系统规则启用时会话 SSE 记录一次 `system_rule` 已完成步骤；后台分类/摘要/embedding/reranker 不接收用户规则。

## 固定分派 Prompt（原样）

角色：`backend-dev`；模型：临时 Luna high；只读文件：`docs/sdd/ROLE-ONBOARDING.md`、Spec022、Task10 计划、Task09 后端实现/评审、Task10 技术复审、现有 memory/chat/API/adapter 与相关测试；允许修改：`backend/**` 与 Task10 后端测试，预期白名单为 `backend/app/memory/{models.py,repository.py}`、`backend/app/chat/application/{conversation_service.py,chat_runner.py,chat_graph.py}`、`backend/app/platform/ollama_direct.py`、`backend/app/api/{schemas.py,routes_conversations.py,routes_chat.py,routes_article.py,routes_kb.py}`；禁止操作：frontend、论文下载/知识库/Task ledger、第二套模型客户端/队列/分类器；完成状态：已完成；验证命令：精确 Task10 pytest、受影响后端 pytest、py_compile、git diff --check；报告路径：`docs/sdd/plans/022/artifacts/task-10/backend-implementation-report.md` 与 `test-report.md`；固定回传字段：结果摘要、改动文件、命令/退出码/结果、产物路径、决策依据、风险阻塞、主 Agent 后续动作、开始结束总耗时和模型/工具统计。

## 风险与阻塞

- 系统 Python 缺少 FastAPI；使用 `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest` 完成定向验证。
- 既有旧测试断言 v5 版本号，Task10 迁移后应更新为 v6；该旧断言不代表实现回退。
- Task10 后端未执行全量回归、部署或跨端 smoke，按计划由主 Agent/Task08 收口。

## Reviewer P1 修复追加

- 会话 SSE 无论规则启用状态均通过 `run_chat(messages=...)`，消息固定包含稳定平台 system、可选用户规则/advisory system、历史 role 和独立当前 user。
- KB advisory 改为仅含检索证据，不复制当前问题；KB、普通聊天、Agent、会话均使用稳定平台 system。
- global fixture 增加“所有对话都使用中文”“所有项目都遵守先给结论”等动作表达，并保留正反例门禁测试。
- 观测新增脱敏 `redact_prompt_messages()` 与 `prompt_observation_metadata()`；调用和观测 seam 均不保存完整 prompt，仅保留角色、数量和字符统计。
- 会话读取 SystemRule 失败时 assistant 状态更新改为 best-effort，始终发 `meta → error(SYSTEM_RULE_UNAVAILABLE) → done(failed)`，不发 token。
- v6 结构校验逐列核对类型、NOT NULL、默认值、PK 与 CHECK；损坏表初始化抛出 `SystemRuleUnavailableError`（RuntimeError 子类）并 fail-closed。

## 主 Agent 后续动作

请运行 Task10 后端 reviewer 对 owner 隔离、迁移结构校验、scope 门禁、四入口角色载荷与 fail-closed 进行复审；汇总前后端验收后再执行全量回归和部署 smoke。

## 时间与统计

- 开始：2026-09-11 16:50 +0800
- 结束：2026-09-11 17:04 +0800
- 总耗时：约 14 分钟
- 模型/工具：临时 Luna high；`apply_patch`、文件读取、Python/pytest、py_compile、SQLite smoke；运行时 token 计数不可得。
