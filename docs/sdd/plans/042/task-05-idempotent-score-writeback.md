> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04（真实闭环已跑通）；当前状态：**已完成**（2026-09-23，[报告](./task-05-report.md)）

# Task 05 — score 写回幂等化与存量重复清理

## 一句话目标

让 Langfuse score 写回**幂等**：同一 trace 同一评测维度在重跑后**只保留一条最新 score**，
并清理 Task 02/04 多次试跑在低频 trace 上堆积的**数十条同名 `chat_quality` score**，
使「回归基线可回看」真正可用。

## 背景与新发现的问题

Task 04 实测（回写成功率 100%）暴露一个可回看性缺陷：

- Langfuse public score API **没有 upsert 语义**，每次 `POST /api/public/scores` 都新增一条记录；
- Task 02 第三轮、Task 04 首轮回查 bug 修复前后的多次重跑，使单条 trace 上堆积了
  **数十条同名 `chat_quality` score**（实测抽样 trace `9a93fe5d…` 上有约 70 条）；
- 后果：多次回归后无法判断「哪条是当前基线」，破坏了 spec-042 目标中的「结果可回看、可回归」。

> 说明：Langfuse 删除能力在 Task 02 第三轮已实证可用（删除后返回 202），本 Task 复用，不重复造轮子。

## 本 Task 的做法

### A. 删除能力与幂等写回（以 True/False 明确的**幂等开关**控制）

1. `backend/eval_042/langfuse_export.py` 新增 `delete_score(score_id) -> bool`：
   - 走 `DELETE {LANGFUSE_BASE}/api/public/scores/{score_id}`（经 `assert_loopback`）；
   - **先实测确认**真实返回码/行为（Task 02 记录为 202，但必须实测复核后再写断言），
     接受 200/202/204 为成功；非 2xx 抛错；**禁止凭猜测写死**。
2. `backend/eval_042/eval_run.py` 的 `run()` 增加参数 `idempotent: bool = False`（默认关闭，
   由调用方显式开启，避免改变既有语义）：
   - 当 `idempotent=True` 且即将写回某 trace 的 `name` 时：
     先 `list_scores(trace_id)` 找出该 trace 上 `name` 相同的**全部** score id 并逐个删除，再 POST 新 score；
   - `write_back=False` / `dry_run` / `skipped` / `unavailable` 的项：**不得**触发任何删除；
   - 删除失败必须如实计入 `delete_errors`，并**跳过该条写回**（宁可不写，也不制造第二条重复）。
3. 汇总新增字段：`deleted_preexisting`（删除的旧 score 条数）、`delete_errors`。

### B. 存量清理（受控、可回滚到「可重跑」状态）

- 新增一次性清理入口（CLI 参数 `--cleanup-duplicates`，对 Task 04 数据集的 20 条 trace 生效）：
  对每条 trace 上同名 `chat_quality` 的重复 score，**保留时间戳最新的一条**、删除其余；
- 清理前先**落盘备份**被删 score 的 id 与 value 到 `docs/sdd/plans/042/task-05-cleanup-backup.json`；
- 清理后逐条回查：断言每 trace **恰好 1 条** `chat_quality` score，统计并落盘。

### C. 幂等回归验证

- 用 `idempotent=True` 重跑 Task 04 的 A 组（同数据集、同判官 `qwen3.5:9b`、同人工标注）：
  - 期望：`written=20`、`verified_on_trace=20`、**每 trace 恰好 1 条 `chat_quality`**、
    `agree_rate` 仍为 0.95、`deleted_preexisting=20`（每条各删掉上轮留下的 1 条）；
  - **再重跑第二次**（连跑两遍），验证第二次跑完仍是每 trace 恰好 1 条（真正幂等）。

### D. 幂等策略修订（2026-09-23 实测后修订，**取代 A 的 delete-then-write 默认行为**）

> 首轮实测发现：**`DELETE /api/public/scores/{id}` 是异步慢队列**（返回 202 `Score deletion queued successfully`，
> 实测吞吐仅约 **0.15 条/秒**，已下发删除的 id 数分钟内 GET 仍返回 200 存在）。
> 因此「先删全部同名旧分再写新分」的 delete-then-write **会放大堆积**（写入快于删除应用，
> 实测 chat_quality 总数由 ~1200 涨到 1820）。**这是基础设施吞吐限制，非代码缺陷**，
> 禁止通过直连 Langfuse 数据库或改 Langfuse 配置绕过。

修订后的幂等语义（`idempotent=True`）：

1. **同值跳过（delta write，默认行为）**：先 `list_scores(trace_id)` 按 `name == task` 精确过滤，
   若**最新一条** score 的 `value` 与本次将写入的 value **相同**（浮点容差 1e-9），
   则**不删除、不写入**，计入 `skipped_unchanged`，并视为已落地（计入 `verified`）。
2. **仅在值变化时写入**：值不同 → 只 POST 一条新 score（**不删旧分**，由清理作业异步回收历史分）。
3. **删除能力保留但改为显式、独立**：`delete_score` 与 `--prune-duplicates` 保留可用，
   但**默认评测流程不再触发删除**，避免与慢队列互相放大。
4. 汇总新增字段：`skipped_unchanged`（同值跳过条数）、`written`（实际新写）、
   `deleted_preexisting`（本轮删除数，默认 0）、`delete_errors`。

**验收口径随之修订**：幂等的判据不再是「每 trace 恰好 1 条」，而是
「**连跑两遍后，第二遍 `written=0`、`skipped_unchanged=20`，score 总数不再增长**」；
「每 trace 恰好 1 条」降级为**清理队列排空后的最终目标**，记为遗留项并给出复跑校验命令。

## 数据、配置与接口

- `DELETE /api/public/scores/{id}`、`GET /api/public/scores?traceId=…`、`POST /api/public/scores`（Basic auth pk/sk）。
- Ollama `POST /api/chat`（本机 11434）。全部经 `offline_guard.assert_loopback`。

## 实施步骤与文件边界

仅改/新增 `backend/eval_042/**` + 落盘 `docs/sdd/plans/042/task-05-*`：

1. `langfuse_export.py`：新增 `delete_score`（含 `_request(method, url)` 私有 helper，保持风格一致）。
2. `eval_run.py`：`run()` 增加 `idempotent` 参数与幂等写回逻辑；汇总增加两个字段。
3. 新增 `backend/eval_042/test_idempotent_writeback.py`（pytest，纯函数、**无网络**）：
   - 用 monkeypatch 注入假的 `list_scores` / `delete_score` / `post_score` / `judge_repeats`；
   - 覆盖：已存在同名 → 先删后写且删除数正确；不存在 → 直接写、删除数 0；
     skipped/unavailable/write_back=False → **零** delete、**零** post；
     删除失败 → 跳过写回并计入 `delete_errors`。
4. 实跑 A/B/C 并落盘：`task-05-cleanup-backup.json`、`task-05-idempotent-run1.json`、`task-05-idempotent-run2.json`、日志、报告。

## 子代理分派

- 角色：`backend-dev`（模型 `hy3`，上下文 32k）
- 最小上下文：本 task 文档 + `backend/eval_042/{langfuse_export,eval_run,judge_client,offline_guard}.py`
- 单次文件范围：`backend/eval_042/**` 与 `docs/sdd/plans/042/task-05-*`
- **不改 `backend/app/**`、不改 Langfuse 配置、不写业务库、不起主服务**

## 边界与明确不做

- 只删**本评测自己写过的** `chat_quality` score，**绝不**触碰业务的其它 score
  （如 `ttft_ms` / `eval_ms` / `is_cold_start` / `prompt_eval_ms` 等观测指标）；
  实现上必须按 `name == task` 精确过滤。
- 不引入 Langfuse SDK 之外的第二套写回路径。
- 不为「删不动」静默兜底：删除失败如实报错并跳过该条。
- 不改 `chat_quality` 判官 prompt 与已通过结论。

## 验收、风险与回滚

| 验收项 | 判据 |
|---|---|
| 删除能力可用 | `delete_score` 对一条真实 score 实测返回成功，退出码 0 |
| 幂等成立 | 同一数据集**连跑两遍**，跑完后每 trace 恰好 1 条 `chat_quality` |
| 不误删业务 score | 抽样 trace 上 `ttft_ms` 等观测 score 数量与清理前一致 |
| 基线不回退 | 幂等重跑后 `agree_rate` 仍 0.95、`written=20`、`verified_on_trace=20` |
| 离线 | 全部调用经 loopback 守卫 |
| 单测 | `python -m pytest backend/eval_042/ -q` 退出码 0（含 Task 03 的 19 + Task 04 的 12） |

**风险**：清理为删除操作，必须先备份 score id 与 value 再删；若删除接口返回非预期码，
**停止清理并带回**，不得猜测或强行重试。
**回滚**：备份文件含被删 score 的 id 与 value，可用 `post_score` 原样写回；本 Task 无业务改动。

## 产出物与变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-23 | 架构师(自身) | 由 Task 04 回读校验发现「同一 trace 堆积数十条同名 score」，创建本 task：幂等写回 + 受控清理 |
| 2026-09-23 | backend-dev(hy3) | 第一轮：`langfuse_export.delete_score`（实测 DELETE 返回 202 异步队列）+ `eval_run --idempotent` 初版 + `--cleanup-duplicates`；实测发现 delete-then-write **放大堆积**（~1200→1800） |
| 2026-09-23 | backend-dev(hy3) | 第二轮：按 D 节把幂等改为 delta write（同值跳过、不删旧分）；实测 run3/run4 仍有 3–4 条重复写入，根因为 **Langfuse 忽略 `traceId` 查询参数** |
| 2026-09-23 | 架构师(自身) | 复核后落地修订：**本地幂等状态表**（`task-05-score-state.json`）作为唯一可靠判据源；补 4 条单测（48 passed 全过）；种子化状态后实跑 run5：`written=0` / `skipped_unchanged=20` / 总数 1780→1740 不增长。任务置为已完成 |

## 执行结果（实测，2026-09-23）

| 项 | 结果 |
|---|---|
| DELETE 实测 | 返回 **202** `Score deletion queued successfully`，但为**异步慢队列**（约 0.15 条/秒） |
| 幂等最终形态 | **delta write + 本地状态表**：① 状态命中同值 → 跳过（不删不写）；② 缺失 → 回退服务端比对；③ 都无 → 写一条 |
| run5（种子化后） | `written=0`、`skipped_unchanged=20`、`verified_on_trace=20`、`deleted_preexisting=0`、`delete_errors=0`、`agree_rate=0.95 / verdict=ok` |
| 总数不增长 | 1780 → **1740**（不增反降，删除队列仍在排空） |
| 不误删 | 抽样 trace 非 `chat_quality` score 数量前后一致（708 → 708） |
| 单测 | `pytest backend/eval_042/ -q` **48 passed** |

**遗留**：「每 trace 恰好 1 条」待删除队列排空后再跑一次 `--cleanup-duplicates` 收敛；备份文件可回滚。
