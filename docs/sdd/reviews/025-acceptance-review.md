# Spec 025 验收评审

> 验收方式：**代行，非独立评审**（hy3 子代理分派连续触发 429 限流，由主会话架构师汇总单端评审与运行时证据）。
> 组成：后端评审 GO（`025-backend-review.md`）+ 前端评审 GO（`025-frontend-review.md`）+ 测试与运行时 smoke。

## 结论：通过

## 验收清单对照（Spec025「验收方式」）

| 验收项 | 结果 | 证据 |
|---|---|---|
| `estimate_tokens` 换算与除零 | 通过 | `tests/test_spec025_token_budget.py`（9 passed） |
| 阈值边界 0.79 不触发 / 0.80 触发 | 通过 | `tests/test_spec025_context_usage_api.py` |
| job 去重与 409 | 通过 | 同上去重/409 用例；运行时二次压缩生成新 job |
| 失败回退 | 通过 | 自动入队失败不影响回答用例；worker 异常收敛为 `failed` |
| `messages` 不变（append-only） | 通过 | 运行时 smoke：压缩前后均为 30 条 |
| 跨项目隔离 | 通过 | `tests/test_spec025_compaction_store.py` |
| dry-run 与真实装配一致性（历史段 + 记忆/摘要段口径） | 通过 | 同源函数；`test_spec025_context_usage_api.py` |
| 迁移可重复执行且幂等 | 通过 | 连续两次初始化 + `_is_task025_schema` 校验 |
| 前端契约（新 class 存在、`?v=` 递增、无 innerHTML、按钮 in-flight） | 通过 | `tests/test_frontend_spec025_context_meter.py`（12 passed） |
| 真实 smoke | 部分通过（见限制） | 端点/worker/装配链路 smoke 通过；真实对话路径因本机 Ollama 无可用模型未覆盖 |

## 测试与回归

- 全量回归：`python -m pytest tests/ -q` → **1345 passed / 1 skipped / 47 subtests passed**，退出码 1（唯一失败为存量问题）。
- 存量失败：`tests/test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it`，已用 `git stash` 在干净树复现，与本次改动无关。
- 新增测试 4 个文件共 40 项：`test_spec025_token_budget.py`(9)、`test_spec025_compaction_store.py`(7)、`test_spec025_context_compaction.py`(14)、`test_spec025_context_usage_api.py`(10)，另加前端契约 `test_frontend_spec025_context_meter.py`(12)。

## 运行时验证（已部署）

- 服务：http://127.0.0.1:8000（`deploy/start.sh -d`，PID 见 `deploy/run.pid`，日志 `deploy/run.log`），`/api/health` 与 `/` 均 200。
- 静态资源：`/assets/app.js?v=34`、`/assets/styles.css?v=34` 均为 200 且含新增逻辑/样式。
- 端点 smoke：
  - `GET /api/conversations/{id}/context-usage` → `{used_tokens:641, budget_tokens:8000, ratio:0.0801, segment_count:0, compaction_status:"idle"}`
  - `POST /api/conversations/{id}/compactions` → `{job_id, status:"queued", trigger:"manual"}` → 终态 `done`，`segment_count` 0→1，摘要为三段式（【指令与约束】/【决策与结论】/【关键实体】）
  - 压缩后消息条数仍为 30（`messages` append-only 成立）
  - 二次压缩：新建 job，因无新增消息而 `done` 且不写空段
  - 不存在会话 → 404
- 前端：`/assets/app.js?v=34` 含 `/context-usage` 与 `/compactions` 调用；首页含 `context-compact-button`。

## 限制与后续

- 本机 Ollama 无可用模型（`curl /api/tags` 为空），"长会话使占比达到 80% 触发自动压缩"的真实端到端路径无法验证，只能由构造阈值的自动化测试覆盖。Ollama 可用后需补一次真实对话 smoke。
- P1 两项见 `025-backend-review.md`（历史预算常量命名、409 统一），不阻塞收口。
