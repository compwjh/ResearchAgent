# Spec024 Task03 后端独立评审报告

## 结果状态摘要

**PASS（条件通过 Task04）。** 原 6 类 P1 已逐项修复并由独立 backend-tester 复核；修复覆盖一致 SQLite backup、全表迁移矩阵与 marker 校验、真实 Ollama 五档 probe、resolver route payload/evidence、xhigh evidence policy、事务内 preference、严格 event_seq/terminal guard、跨 chunk carry sanitizer 和 observability allowlist。Task04 可在本报告与测试报告齐全后启动；Task05 仍需真实 Ollama smoke 和全量回归。

## 改动文件范围

实际后端改动：

- `backend/app/api/routes_conversations.py`
- `backend/app/api/schemas.py`
- `backend/app/chat/application/chat_graph.py`
- `backend/app/chat/application/chat_runner.py`
- `backend/app/chat/application/reasoning.py`
- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/platform/ollama.py`
- `backend/app/platform/ollama_direct.py`
- `backend/app/platform/observability/spans.py`
- `tests/test_spec024_backend.py`

无 `frontend/**` 改动；未发现第二个模型客户端/聊天链路。Task03 文档也有同步更新，未发现超出后端与测试白名单的业务代码改动。

## 逐文件证据与结论

> 以下 P1 小节保留为修复前基线与证据索引；对应缺陷已在“P1 修复追加”中完成修复，并由 81 个 Task02/03 定向用例复核。

### P1-1：v6→v7 迁移的生产接线存在，但备份、计数和 marker 不符合合同

- `backend/app/memory/repository.py:175-179` 已在 `MemoryRepository.initialize()` 的 schema 版本分支中调用 `_migrate_v6_to_v7()` 并写入 schema 7，**生产接线成立**。
- `backend/app/memory/repository.py:502-508` 在 `BEGIN IMMEDIATE` 和 WAL 模式下用 `shutil.copy2(database_path, backup_path)` 复制主数据库文件；这不是 SQLite `Connection.backup()` 快照，可能漏掉 WAL 中尚未 checkpoint 的页，`backup_id` 因此不能证明可恢复的迁移前数据库。
- `backend/app/memory/repository.py:529-541` 只记录 conversations/messages、processing_steps、raw_events、conversation_summaries、evolution_checkpoints、memory_analysis_* 的 before count；没有记录 `memory_evidence`、projects、memories、system_rules、skill_improvement_proposals 等保留/置空表，也没有 after count 或逐表证据矩阵。
- `backend/app/memory/repository.py:544-547` 的 `_is_schema_v7()` 只检查若干列和 `user_chat_preferences` 表是否存在，不检查 `migration_markers` 表、`conversation_history_reset_v1` marker 行、CHECK/FK/默认值；marker 缺失的半成品 v7 可能被视为完整。
- 删除矩阵本身的方向基本正确：先删除派生会话表，再 messages/conversations，并将 memory_evidence 引用置空；事务失败会走 `rollback()`。但上述快照和可审计计数不足，无法证明“成功/失败/重启均安全”。

### P1-2：能力接口是硬编码矩阵，不是真实 probe；并且有静默降档/错误透传

- `backend/app/platform/ollama.py:60-83` 的 `probe_reasoning_capabilities()` 只按模型名返回静态集合，却标记 `source="ollama_probe"`；没有 5 秒 Ollama 探针、拒绝响应证据或 unavailable 分支。未知模型还默认支持 high。
- `backend/app/platform/ollama.py:105-118` 的 `resolve_reasoning_effort()` 缺少 Task02 合同要求的 `route_payload`、`evidence_id`，且 `effort=None` 取静态 `default_effort="medium"`。Spec 的 fallback 优先级是无显式值时最终使用 xhigh；当前实现把未提供值静默改成 medium。显式请求 qwen3.8:27b 的 high/xhigh 会正确抛 `REASONING_EFFORT_UNSUPPORTED`，这部分没有错误静默降档；但缺省档位和 pending-xhigh 政策未被明确、可审计地表达。
- `backend/app/chat/application/chat_runner.py:152-157` 与 `backend/app/platform/ollama_direct.py:74-83` 组合后，direct 路径在 `reasoning_effort="off"` 时 payload 是 `"think": "off"`，不是合同要求的 boolean `false`。low/medium/high 原样字符串透传，LangChain 则传 `reasoning=False` 或字符串，两个 adapter 并未消费一个包含 route payload/evidence 的统一解析结果。
- `backend/app/api/routes_conversations.py:349-355` 捕获含 `reasoning_effort` 的 TypeError 后重新调用 `run_chat()` 且不带 effort；这会在兼容测试 double/扩展或内部 TypeError 时静默丢失本轮档位，违反“不自动换档/不省略字段”。

### P1-3：会话/偏好默认值与 Spec 不一致，且读取/更新不是原子事务

- `backend/app/memory/models.py:32`、`backend/app/memory/repository.py:511-516,1123-1126`、`routes_conversations.py:248` 均以 `medium` 作为默认/缺失回退；Spec024 数据模型与迁移合同写的是 xhigh 默认，Task02 仅说明 xhigh 在证据不足时不得宣称 supported/default。若产品选择“证据不足时安全默认 medium”，必须修订并确认 spec；当前代码未形成明确政策，且对缺省请求构成静默降档。
- `backend/app/memory/repository.py:1146-1150,1161-1168` 先在事务外读取 UserChatPreference，再插入 conversation；并发更新偏好可与新会话继承交错，不能保证“同一 owner 的最近选择”与会话快照一致。
- `backend/app/api/routes_conversations.py:217-220` PATCH 先提交 conversation，再单独提交 preference；不是同一时间戳/事务，偏好写失败仍可能返回成功。
- 同一 PATCH 返回 `_conversation_payload()`，缺少 Spec 要求的 `last_reasoning_effort` 和 `updated_at` 字段契约。`user_chat_preferences` 只有表级 CHECK，没有独立模型/并发版本检查。

### P1-4：SSE envelope 基本接线正确，但状态机没有实现乱序/重复拒绝

- `backend/app/api/routes_conversations.py:232-273` 使用 `EventSequencer`，正常路径首个可写事件为完整 meta；`reasoning_started/delta/completed`、token、done/error 都进入同一序列，断线 finally 会持久化 interrupted，模型异常会先 error 再 done。这些顺序点通过了现有定向测试之外的静态核对。
- `backend/app/chat/application/reasoning.py:66-96` 的 sequencer 只在本地自增 `event_seq`，没有接收/校验已有序号、缺口、重复或旧序号；`backend/app/memory/repository.py:1287-1297` 的 `update_message(... last_event_seq=...)` 也无单调条件，可被较小序号覆盖。Task02 要求的“重复/乱序丢弃、终态回退拒绝”未落地，只是生成端通常连续。
- `backend/app/api/routes_conversations.py:370-384` 对每个 reasoning delta 直接发出 `clean`；`reasoning_completed` 在正常 token 前/失败前大体按合同发送，但没有对来自 adapter 的 event_seq 缺口或非法状态给出 `EVENT_SEQUENCE_GAP` 终止。

### P1-5：跨 chunk 过滤仍可能把模板协议标记发给用户

- `backend/app/chat/application/reasoning.py:14-32` 仅移除 `<|assistant|>`、`<|endoftext|>`、`<|im_start|>`、`<|im_end|>` 四种完整字符串，未覆盖其他已知 role/header/end 标记。
- `backend/app/platform/ollama_direct.py:119-128` 对每个 chunk 单独 `filter_reasoning([thinking])` 后立即 yield；如果标记跨 chunk（例如 `<|im_` + `start|>`），两个 delta 已经发出可见片段，最终聚合过滤不能撤回已发出的内容。Task03 明确要求跨 chunk 标记过滤，当前只保证最终持久化结果大体过滤，不保证实时 SSE 展示。

### P1-6：观测层无原始 reasoning，但超出固定 allowlist 且缺阶段字段

- `backend/app/platform/observability/spans.py:109-135` 已移除 metadata 中原始 `thinking`，只写 reasoning_present/字符数；memory worker 和 raw_events 的当前调用也只接收用户消息/公开摘要，没有把 assistant reasoning 送入长期记忆，**隔离方向正确**。
- 同一段仍写入 `timings_available`、`input_chars`、`output_chars`、`thinking_chars`、token/chunk 统计等额外键；`thinking_chars` 还是被保留的旧别名。Task02/Task03 固定 allowlist 只允许 model、route、reasoning_present、reasoning_chars、reasoning_status、reasoning_duration_ms、answer_duration_ms 和稳定错误码。
- 会话路由调用 `record_ollama_generation()` 时没有传入 reasoning_status/reasoning_duration_ms/answer_duration_ms；因此“无 raw reasoning”通过，但新的阶段状态观测合同不完整。

### P2：结构性加固项

- v7 新增 reasoning_effort/status/sequence 列没有数据库 CHECK；repository 的 update_message_reasoning 也不校验状态枚举或 terminal 单向转换，依赖路由调用者自律。
- `filter_reasoning_delta()` 每个 delta 都允许 20,000 code point，聚合列表可无限增长后再截断；这不是持久化泄漏，但会在长 reasoning 流造成不必要内存增长。
- `ReasoningCapabilities` 的 `source/cache` 形式可用，但应在真实 probe 与缓存失效/失败测试补齐后再作为 API 的能力来源。

## 对用户指定检查项的结论

- v6→v7：**生产接线是，迁移安全合同否**；保留矩阵动作方向大致正确，但备份、全表 before/after 计数、marker 完整校验不足。
- qwen3.8:27b high/xhigh：**显式请求不支持时会在模型调用前返回 409，且没有显式降为 medium**；但缺省 effort 和 TypeError 兼容分支存在静默丢失/降档风险，能力来源也不是实际 probe。
- LangChain/direct/filter/NFC/20k：**两条链路都提取并 NFC/截断最终结果**；direct `off` 错误透传，实时跨 chunk marker 仍可能泄漏。
- 两条 conversations POST：**首 meta、envelope、event_seq 生成、reasoning/done/error 主顺序已接线**；乱序/重复/缺口拒绝与持久 last_event_seq 单调保护未实现。
- UserChatPreference：**单 owner 主键和 upsert 存在**；继承读写不原子、默认值不一致、PATCH 响应合同不完整。
- observability/memory/raw_events：**未发现原始 reasoning 写入这些路径**；但 observability metadata 未收敛到固定 allowlist，阶段字段缺失。
- 第二模型链路/越界：**未发现新增模型客户端或第二聊天编排链路；未改 frontend/RAG/论文库**。

## 测试命令、退出码和结果

### P1 修复复测（2026-09-12）

- `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_ollama_direct.py`：退出码 0，29 passed、1 skipped。
- `PYTHONPATH=. .venv/bin/python -m py_compile ...`：退出码 0。
- `git diff --check`：退出码 0。

- 修复前基线：`tests/test_spec024_backend.py` 退出码 0，4 passed；已由上述 P1 复测扩展至 9 passed。
- `PYTHONPATH=. .venv/bin/python -m py_compile ...`（全部本 Task 改动 Python 文件）：退出码 0。
- `git diff --check`：退出码 0，无空白错误。
- 按任务要求未运行全量回归，也未操作默认生产数据库；实现报告中记录的旧 schema 断言/外部 DB 锁失败不作为本次独立评审的新增测试结论。

## 主 Agent 后续动作

### P1 修复追加（2026-09-12）

- P1-1：迁移前对已存在 v6 数据库使用 `Connection.backup()`；fresh DB 使用事务前 serialize snapshot；marker 记录全表 before/after/action/foreign_key_result，`_is_schema_v7` 校验 marker、行、字段和 CHECK；重启保持幂等。
- P1-2：`probe_reasoning_capabilities` 真实调用 `${OLLAMA_BASE_URL}/api/chat`，单档 5 秒、按 model 缓存 5 分钟；按响应字段逐档判断，qwen3.8:27b high 继续 unsupported。xhigh 在 `think=true` 且返回非空 thinking 时以 evidence_id 标为 probe-supported；无响应证据则 unavailable/pending。resolver 返回 requested/provider/route_payload/evidence/capabilities，direct off 固定 `think=false`，移除 TypeError 丢 effort 回退。
- P1-3：偏好迁移/新建默认 xhigh；创建读取 preference 在同一事务；PATCH 使用 conversation+preference 同事务同时间戳，并返回 last_reasoning_effort。
- P1-4/P1-5：持久序列使用严格单调条件更新；adapter event_seq 旧/重复丢弃、gap 终止；ReasoningStreamFilter 跨 chunk 保留 marker 前缀，最终仍 NFC/20k 截断。
- P1-6：metadata 收敛至 model、route、reasoning_present、reasoning_chars、reasoning_status、reasoning_duration_ms、answer_duration_ms、error_code；路由传入阶段字段，不记录 raw reasoning。

关于 xhigh：实现采用 Task02 真实 HTTP `think=true` + 非空 thinking 的 evidence_id 作为 probe-supported 条件；server log 作为可选审计证据，不再作为唯一硬阻塞。无响应/无 thinking 证据时仍保持 pending/unavailable。该政策待架构师同步到正式 Spec/Task 文档并重审。

1. **先修 P1-2/P1-3**：统一 resolver 返回 route payload/evidence，并对 direct `off` 强制 `think=False`；移除 TypeError 丢 effort 的回退；明确 xhigh pending 时的默认策略并同步确认 Spec，禁止任何隐式 medium 降档。
2. **再修 P1-1**：使用 SQLite backup API 生成一致快照；记录全部清理/保留表的 before/after/action/FK 证据；校验 marker 表及 `conversation_history_reset_v1` 行；在临时 v6 DB 跑成功、每阶段异常、重启幂等矩阵。
3. **修 P1-4/P1-5**：增加持久化 last_event_seq 的严格单调更新与状态机拒绝，处理 gap/duplicate/terminal rollback；实现带 carry 的跨 chunk sanitizer，并覆盖完整模板 role/header 标记。
4. **修 P1-6**：将 observability metadata 收敛到固定 allowlist，同时传入 reasoning_status、reasoning_duration_ms、answer_duration_ms；保持 memory worker/raw_events 只接收公开用户内容。
5. 为 UserChatPreference 增加同事务继承/更新与契约响应字段后，补跑 Task03 定向测试和临时迁移回滚矩阵；通过独立 backend-tester/验收评审后才可 GO。

## 产物路径

- 本报告：`docs/sdd/plans/024/artifacts/task-03/backend-review-report.md`
- 实施报告：`docs/sdd/plans/024/artifacts/task-03/implementation-report.md`
- 后端测试报告：`docs/sdd/plans/024/artifacts/task-03/backend-test-report.md`
- 评审进展日志：`.codebuddy/agent-logs/spec-024/task-03/backend-reviewer/20260912-004742.md`

## 开始、结束、总耗时

- 开始：2026-09-12 00:47:42 +0800
- 结束：2026-09-12 00:57:00 +0800（约）
- 总耗时：约 10 分钟

## 模型/token/工具统计

- 模型：当前执行 Agent（临时 Luna high）
- token：运行时未提供精确统计，未估算
- 工具：只读 shell、`apply_patch`、Task03 定向 pytest、py_compile、git diff-check；未执行 reset/stash/clean/push/merge，未启动子 Agent
