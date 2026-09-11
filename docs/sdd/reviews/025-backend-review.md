# Spec 025 后端评审（backend/**）

> 评审方式：**代行，非独立评审**（hy3 子代理分派连续触发 429 限流，由主会话架构师按评审清单逐项核对）。

## 结论：GO

实现覆盖 Spec025 全部后端边界，未发现 P0；P1 两项均为可选增强，不阻塞。

## P0

无。

## P1（可选增强，不阻塞）

- **P1-1** `history_budget_chars` 仍为字面 6000（`conversation_service.py` 装配函数默认参数），未提升为 `CHAT_HISTORY_BUDGET_CHARS` 命名常量。当前与 `CHAT_RAG_BUDGET_CHARS` 同值，语义无歧义；若后续两者需要独立调参，再补常量。
- **P1-2** 手动压缩端点先用 `get_latest_compaction_job` 做快速 409 判断，再入队；真正的去重仍由 DB 部分唯一索引保证（`create_compaction_job` 冲突返回 None）。极端并发下第二个请求可能返回 200 并复用既有 job（不会重复压缩、不会双写段），建议后续把 `enqueue` 冲突返回改为 `None` 以统一为 409。

## 逐项核对表

| 重点 | 结论 | 依据 |
|---|---|---|
| 迁移幂等 / fail-closed / 不 bump 版本号 | 通过。`_migrate_v6_to_task025` 全 `IF NOT EXISTS`，挂在既有迁移链事务内；`SCHEMA_VERSION` 仍为 6 | `repository.py:198-215,635-733`；`tests/test_spec025_compaction_store.py` 连续两次初始化用例 |
| `_is_task025_schema` 校验强度 | 通过。逐列校验字段 + 主键 + `idx_conversation_segments_seq` 唯一索引 + 部分唯一索引 `WHERE status IN ('queued','running')` | `repository.py:658-733` |
| job 并发领用（regression-guard #6） | 通过。单条 INSERT + 捕获 `IntegrityError`，无"先 SELECT 判重再 INSERT" | `repository.py` `create_compaction_job`；`context_compaction.py:208-230` |
| worker 异常收敛 / 线程不死 | 通过。`_process` 内部收敛为 `failed`，`_run` 外层再兜底；`_queued` 在 `finally` 中 discard，不泄漏 | `context_compaction.py:292-313` |
| 入队冻结窗口 | 通过。`from_message_id` 取 `next_segment_start_message`，`to_message_id` 取入队时刻最后一条，随请求入队 | `context_compaction.py:214-228`；冻结窗口用例 |
| `messages` append-only | 通过。全部路径无 UPDATE/DELETE；运行时 smoke 压缩后 30 条消息条数不变 | `context_compaction.py` 全文；smoke `messages_preserved: 30` |
| 无段时逐字符等价回退 | 通过。`_build_history_section` 无段分支保留 `prior[-20:]`/每条 2000/总预算截断 | `conversation_service.py:_build_history_section`；`test_compose_no_segment_byte_identical_to_status_quo` |
| 有段时 raw ≤ CHAT_RECENT_RAW_MESSAGES、不重复 | 通过。以最后被采用段的 `to_message_id` 为分界点，raw 只取严格晚于该点的消息且最多 N 条；装不下时从最旧段丢弃 | `conversation_service.py:_build_history_section`；`test_compose_with_segment_injects_summary_raw_capped_no_duplicate` |
| dry-run 同源且不含 RAG | 通过。`compute_context_usage` 复用同一 `compose_chat_prompt`，`rag_hits=None`，不调模型、无副作用；`budget<=0` 时 ratio 钳到 1.0 | `routes_conversations.py:71-110`；`test_spec025_context_usage_api.py` |
| 80% 自动触发不阻塞 | 通过。装配后计算 ratio，`>= CHAT_COMPACT_TRIGGER_RATIO` 才入队，整段包 `try/except` 只记日志 | `routes_conversations.py:323-333`；自动入队失败不影响回答用例 |
| 端点错误码与风格 | 通过。404 `CONVERSATION_NOT_FOUND`、409 `COMPACTION_IN_PROGRESS`、500 `COMPACTION_ENQUEUE_FAILED`，与既有错误体一致 | `routes_conversations.py:454-479`；运行时 curl 验证 404 |
| 无重复实现 | 通过。换算只在 `token_budget.py`；装配只在 `compose_chat_prompt`；worker 复用既有 threading+queue 范式 | 全仓 grep |
| 跨项目隔离 | 通过。段读写都带 `owner_id/conversation_id/project_id`，未绑定项目时严格 `project_id IS NULL` | `repository.py` `list_conversation_segments`；跨 owner/跨项目隔离用例 |

## 测试与运行时证据

- 新增测试：`tests/test_spec025_token_budget.py`（9）、`tests/test_spec025_compaction_store.py`（7）、`tests/test_spec025_context_compaction.py`（14）、`tests/test_spec025_context_usage_api.py`（10）。
- 全量回归：`python -m pytest tests/ -q` → **1345 passed / 1 skipped / 47 subtests**，唯一失败 `test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it` 已用 `git stash` 在干净树复现，属存量失败。
- 运行时 smoke（端口 8000，Ollama 无可用模型，只验证端点与压缩链路）：`context-usage` 返回 `used_tokens=641 / budget=8000 / ratio=0.0801`；手动压缩 job `queued → done`，`segment_count` 0→1，摘要为三段式；压缩后消息条数仍为 30；二次压缩生成新 job 且因无新消息而 `done` 不写空段；不存在的会话返回 404。
