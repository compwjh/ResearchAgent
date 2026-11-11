> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`（2026-11-08 接手机器真实运行时验证）

# Task 04 — 评测结果可靠性：score 幂等 + 报告目录文件锁

## 状态与一句话目标

`已完成`。让评测可以重复跑、并行跑而不污染结果：同一 trace 重跑不产生重复 Langfuse score，
多进程共用输出目录不互相覆盖报告。

对应 spec 11 项中的 **08（能力补齐）**。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) F5；
  [045-evaluation-module-survey.md](../../notes/045-evaluation-module-survey.md) 第 2/5 节。
- **F5**：`backend/eval_042/langfuse_export.py:65-78` POST `/api/public/scores` 无幂等键、
  无「先查后写」，重跑同一 trace 产生重复 score；
  `spec-042:226` 把「避免重复写入」推给人工核对。
- `backend/eval_042/report.py:443-503` 用 `os.replace` 原子写单文件 + 有界回滚，
  但**无文件锁**：多进程共用 `--output-dir` 时回滚基于自己读到的快照，会覆盖对方已发布文件。
- 现有护栏：`offline_guard.py:199-218` 的 POST 不重试是刻意的
  （「未知写入结果必须交给上层报告为失败，不能自动重放造成重复 score」）；
  `tests/evaluation/test_offline_transport.py:95-510` 锁定「score POST 恰好一次且不重试」；
  `test_evaluation_report.py:41-351` 锁定双投影一致、写失败回滚、二次 replace 失败恢复 pair。
- 前置：task 02 已完成（真实 Langfuse 可写可查）。

## 数据、配置与接口

- 引入稳定的 score 去重标识（基于 `trace_id + task + report_version + name` 等确定性输入），
  在 POST 前做一次精确查询；命中即复用既有 `score_id`，不产生第二条。
- 幂等判定不得变成「先删后写」或「自动重放 POST」；POST 仍恰好一次。
- 报告输出目录加进程间文件锁（如 `fcntl.flock` 的 lockfile），
  覆盖 `report.json` 与 `report.md` 双文件投影 + 回滚全过程。
- `ReportWriter` 对外字段、schema_version `agent-evaluation-report-v1` 不变。

## 实施步骤与文件边界

1. 红测：重跑同一 trace 只产生一条 score；两个进程同时写同一 `--output-dir`
   结果文件不被互相覆盖；锁超时/持锁进程崩溃可恢复。
2. 在 `langfuse_export` 增加精确查询与幂等键；保持 exact-ID GET 校验
   （`:113-135`，404 视为尚未可见）与 6 次退避逻辑不变。
3. 在 `report.py` 的写入/回滚路径加文件锁，保持 `os.replace` 原子性与现有回滚语义。
4. 回归 `tests/evaluation/` 全量；在真实 Langfuse 上重跑两次同一 trace 验证 score 数量。

**文件边界**：`backend/eval_042/{langfuse_export,report,offline_guard}.py`、
`tests/evaluation/**`；**不碰** `backend/app/**`、`frontend/**`。

## 子代理分派

- 含 `.py` 改动 → 必须先 `Task(backend-dev)` 分派（`AGENTS.md:127,128`），
  主会话只编排与读回校验。
- 并发测试建议由 `Task(backend-tester)` 独立执行，避免与开发自证。
- 最小上下文：本 task 文档 + F5 路径行号 + 「POST 恰好一次」不可变契约。

## 边界与明确不做

- **不自动重放 POST**，不改变「未知写入结果由上层报告为失败」的既有决策。
- **不改** score 的 `name/value/traceId` 语义、不改 exact-ID 校验四字段
  （`id/traceId/name/value`）。
- 不做分数口径统一（P2）、不做人工标注（P2）、不新增业务端点。
- 不引入新的第三方依赖（文件锁用标准库）。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| score 幂等 | 真实 Langfuse 中同一 trace 重跑两次后 score 数量不增加（Q10 证据③） |
| 报告并发安全 | 双进程并发写后 `report.json/md` 均为同一版本、无半文件 |
| 契约不变 | `test_offline_transport` 与 `test_evaluation_report` 全绿 |
| 回滚 | 持锁进程崩溃后锁可释放，下次运行不阻塞 |

风险：精确查询增加一次 GET，若 Langfuse 延迟可见性导致查不到会误判为未写过；
须复用现有「404 = 尚未可见」的退避语义，不得因查询失败就重放 POST。
失败时回滚到任务 02 状态。

## 产出物、执行结果与变更日志

初始写「待执行后填写」。执行后回填：红绿测试输出、两次真实运行的 score ID 与数量、
并发测试命令与结果、改动文件清单、`spec-status-changelog.md` 条目。

## 接手机器执行结果（2026-11-08，真实运行时验证）

**状态：已完成。** 交接文档称「`post_score_idempotent` 未接入 runner」已过时：
只读核实 `backend/eval_042/runner.py:563` 已调用 `post_score_idempotent`，
`langfuse_export.py:170-216` 保留 `_DEFAULT_SCORE_WRITER` 兼容注入，
`report.py` 的 `fcntl.flock` 文件锁真实生成 `.report.writer.lock`。

真实证据（见 `runs/task-02/evidence.md` 第 5 节）：

```
第一次真实 CLI --export → scored=2 / written=2 / verified=2 / failed=0，scores totalItems=979
重跑（另一 --output-dir，同一批 trace）→ 同样 scored=2 / written=2，scores totalItems=979
delta=0，无任何新 eval042-* score
```

即幂等键在**真实 Langfuse**（非 mock）上生效。定向测试
`pytest tests/evaluation/ tests/observability/ tests/platform/ -q` → `214 passed, EXIT=0`。
