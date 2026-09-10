# Spec022 Task04 后端最终复审报告

## 结论

**GO（后端范围）**。最后一项 P1 已关闭：消息入口对 worker 启动/恢复扫描采用 best-effort，异常只记录 warning，不影响 `StreamingResponse`；流结束仍会再次尝试 durable enqueue。当前未发现 P0/P1 阻断项。本报告只覆盖 Task04 后端及受影响的 Task02/03 后端兼容路径，不代替全量回归、跨端验收或部署验证。

## 严重级别汇总

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 未发现 P0 |
| P1 | 0 | 无阻断项 |
| P2 | 1 | worker 当前在首条消息入口启动；若无新请求，重启后的 durable work 会等待下一次触发 |

## 本轮最终复核

### worker 初始化/扫描异常不阻塞 SSE（已关闭 P1）

- `backend/app/api/routes_conversations.py:265-272` 将 `get_memory_evolution_worker(repo)` 包在 `try/except` 中；启动或恢复扫描异常只写 warning 并继续返回 `StreamingResponse`。
- `backend/app/api/routes_conversations.py:229-234` 在流结束的 `finally` 中再次执行 `enqueue_session`，同样 best-effort；因此异步整理异常不会改变聊天主链的 `done` 状态。
- `tests/test_conversations_api.py:200-214` 注入 worker 初始化异常，验证 HTTP 200、`done=completed`，并验证 durable Raw event 已落盘。
- 独立边界探针将 `MemoryEvolutionWorker.start` 替换为抛出 `RuntimeError("scan failure")`，实际结果为 `200 done completed`；另以 spy worker 验证流结束调用 enqueue 一次且传入正确 `conversation_id`。

## 需求与代码证据

| 检查项 | 当前证据 | 复核结论 |
|---|---|---|
| v3 完整结构 fail-closed | `backend/app/memory/repository.py:127-137、268-314` 在事务内验证三张 v3 表、必需列、FK 删除规则、唯一约束和关键索引；不完整 v3 启动失败并回滚 | 通过 |
| Raw append-only / 幂等 | `repository.py:704-730` 仅提供追加读取面；`UNIQUE(owner_id, conversation_id, idempotency_key)` 重复 key 返回原事件，未提供业务 update/delete | 通过 |
| Raw message/cursor 归属 | `repository.py:713-746` 校验 message 的 owner/conversation，`after` cursor 同时限定 owner/conversation；跨会话反例拒绝 | 通过 |
| v2→v3 原子、兼容、失败回滚 | `repository.py:108-137、224-265` 在 `BEGIN IMMEDIATE` 中迁移、写版本并最终验证；异常 rollback 后 fail-closed；既有 v1/v2 兼容路径保留 | 通过 |
| Map/Reduce checkpoint 恢复 | `conversation_service.py:158-201` 按 after cursor 分页、每批保存 cursor/state，Reduce 后 upsert 单会话摘要；失败 checkpoint 可再次 claim | 通过 |
| stale lease 接管 | `repository.py:818-846` 对超过 300 秒的 running lease 做带旧 `updated_at` 条件的原子接管，保留进度并递增 attempts | 通过 |
| 1001+ 分页完整性 | `conversation_service.py:158-168` 每页最多 1000、按 event cursor 继续；state 记录首/末 event ID 与完整输入计数；测试覆盖 1001 条 | 通过 |
| 同 session 互斥 / 失败重试 | `conversation_service.py:94-114、170-208` 使用进程内 session mutex；worker `conversation_service.py:244-264` 吞掉处理异常，checkpoint 留 failed，后续启动/显式 enqueue 可重试 | 通过 |
| worker 真实接线 | `routes_conversations.py:265-273` 启动 worker，`:229-234` 流结束 enqueue；正向 API 测试验证 eventually checkpoint、summary、candidate；处理/初始化失败均不阻塞 SSE | 通过 |
| candidate evidence 门禁与原子性 | `conversation_service.py:130-156` 只从有合规事件的候选路径创建；`repository.py:544-565` memory+evidence 同事务；`repository.py:679-698` 无 evidence 不得 promote | 通过 |
| project 不自动升 global / correction supersedes | `conversation_service.py:137-156` project candidate 保持当前 project；correction 选择同 scope active 记录作为 supersedes；`repository.py:694-697` 升格时事务性标旧记录 superseded | 通过 |
| 无匹配摘要为空 | `repository.py:781-800` query 有 terms 时只保留匹配摘要，不回退注入全部摘要 | 通过 |
| history 不重复当前消息 | `routes_conversations.py:187-193` 组装 history 时排除当前 user message，`compose_chat_prompt()` 再追加一次；测试验证唯一出现 | 通过 |
| global/project/当前指令隔离与独立预算 | `repository.py:606-619、864-875` 只召回 owner 的 global+当前 project，memory/summary 各自预算；`conversation_service.py:72-83` 项目指令与当前问题不被摘要裁剪挤掉 | 通过 |
| 失败降级 / 单 store / 旧兼容 | `routes_conversations.py:107-112、157-182、229-234` Raw、召回、使用记录、enqueue 均为 advisory；仍复用单一 `MemoryRepository`/SQLite，无外部队列；旧 chat/API/SSE 路径回归通过 | 通过 |

## 测试与静态检查

| 检查 | 命令 | 结果 |
|---|---|---|
| Task04 精确范围 | `./.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 退出码 0；**34 passed in 1.75s** |
| Task04 + 受影响旧后端兼容 | `./.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_api.py` | 退出码 0；**50 passed in 5.22s** |
| Python 语法 | `./.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py` | 退出码 0 |
| Diff 空白检查 | `git diff --check` | 退出码 0 |
| 初始化/扫描异常探针 | 注入 `MemoryEvolutionWorker.start` 抛错后调用消息 API | HTTP 200，末帧 `done=completed` |
| 真实 enqueue 探针 | 注入 spy worker，消费完整消息流 | enqueue 调用 1 次，conversation ID 与 `meta` 一致 |

未运行全量 pytest、前端测试、部署或最终跨端 smoke，符合本角色的 Task04 后端评审边界。

## P2 风险与主 Agent 后续动作

1. **P2 生命周期提示**：`MemoryEvolutionWorker` 当前由 `routes_conversations.py:265-266` 在消息入口启动；没有新消息时，重启后的 raw/retry work 要等下一次请求才触发扫描。可在应用 lifespan 增加 best-effort 启动，但不应把该可选整理路径变成聊天启动硬依赖。
2. 主 Agent 可据本报告放行 Task04 后端，继续跨端验收；Spec 收口阶段仍需按门禁执行全量回归、验收和部署 smoke。
3. 后续若扩大到模型化摘要，继续保持 checkpoint、Raw event 和单一 SQLite store 契约，不保存隐藏思维链或引入第二队列/store。

## 运行信息

- 评审角色：backend-reviewer
- 模型：临时 Luna high（按主 Agent 分派）
- 本轮开始：2026-09-11 05:58:30（Asia/Shanghai）
- 本轮结束：2026-09-11 06:08:43（Asia/Shanghai）
- 本轮耗时：约 10 分 13 秒
- 模型 token 统计：运行时不可用
- 工具统计：运行时未提供精确计数；使用定向文件读取、只读检索、pytest、py_compile、git diff check、临时 SQLite 及初始化/扫描/enqueue 边界探针
- 进展日志：`.codebuddy/agent-logs/spec-022/task-04/backend-reviewer/20260911-054455.md`
