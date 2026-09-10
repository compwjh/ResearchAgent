# Spec022 Task04 后端测试报告

## 结果

**PASS（后端定向范围，针对 reviewer NO-GO 已补修）**。Task04 新增的 raw 事件追加幂等、Map/Reduce checkpoint 失败恢复、会话互斥、证据门禁、scope 隔离、预算裁剪和 superseded 链，以及 Task02/03 受影响路径均通过。

## 命令与退出码

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Python 语法 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py` | 0；通过 |
| Task04 + Task02/03 精确后端回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 0；33 passed |
| Task03/Task02 旧聊天兼容回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_api.py` | 0；50 passed，1 warning |
| Diff 空白检查 | `git diff --check` | 0；通过 |

## 覆盖项

- Raw 事件只追加；相同 idempotency key 返回首条事件，payload 不被后写入覆盖。
- schema v1→v3 迁移保持原子性、WAL 与既有 Task03 v2 兼容；新表由同一 repository 管理。
- Map/Reduce 按 batch size 分批；每批保存游标/state；注入失败后 checkpoint 为 failed，重启新 repository 可继续并只生成一条摘要。
- 同一 session mutex 第二次获取失败；重复完成 checkpoint 不重复处理。
- 候选始终 `candidate`；无 evidence 的 `promote_memory` 被拒绝；有 evidence 后允许升格；project 不会自动改为 global。
- user correction 可建立 `supersedes_id` 链；候选未升格时旧记忆仍 active，升格事务内旧记录转 superseded。
- owner/project 召回隔离；global 与当前 project 记忆按独立字符预算，summary 另有预算，`token_budget` 可限制摘要预算。
- 聊天 SSE 追加 `user_message`/明确记忆/纠正/上下文压力/工具失败 Raw 事件；摘要读取/使用记录异常仍以失败/空上下文继续生成，旧 `meta/progress/memory/token/error/done` 路径回归通过。
- malformed v3 表启动即 fail-closed；跨 session message/cursor 反例被拒绝；stale running checkpoint 可接管并恢复；1001 条事件全量消费且边界完整记录。
- `MemoryEvolutionWorker` wiring 测试证明消息后 eventually checkpoint/summary/candidate；worker 失败不影响 SSE done；候选/evidence 原子回滚；无匹配摘要返回空；当前 user prompt 只出现一次。
- worker 初始化/扫描抛错时记录 warning 但不阻塞聊天；新增测试验证 SSE 仍返回 `done=completed` 且 durable Raw event 已落盘，正向 wiring 测试验证消息后最终生成 checkpoint/summary/candidate。

## 未执行/阻塞

- 未运行全量 pytest、前端契约/浏览器测试、部署和最终跨端验收；这些属于主 Agent 与 Task08 收口。
- 本轮无后端测试阻塞。pytest 仅有既有 Starlette deprecation warning，不影响退出码；未运行全量 pytest、前端测试、部署或最终跨端验收。

## 产物路径与运行信息

- 实现报告：`docs/sdd/plans/022/artifacts/task-04/implementation-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-022/task-04/backend-dev/20260911-task04.md`
- 初轮开始：2026-09-11 05:32（Asia/Shanghai，约）
- 修复轮结束：2026-09-11 05:57（Asia/Shanghai）
- 最终复审修复结束：2026-09-11 06:05（Asia/Shanghai）
- 累计总耗时：约 25 分钟
- 模型：临时 Luna high（按主 Agent 分派）
- token/工具精确统计：运行时不可用；实际使用 py_compile、pytest、diff check 与文件读取/补丁工具
