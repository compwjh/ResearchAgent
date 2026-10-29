# Task 05 报告 — score 写回幂等化与存量重复清理

> 角色：backend-dev（hy3）｜关联 spec-042 / task-05-idempotent-score-writeback.md
> 产物目录：`backend/eval_042/**`、`docs/sdd/plans/042/task-05-*`

## 1. 删除接口实测返回码（步骤 5，真实 loopback）

- 用 `post_score(name="task05_probe_delete_check")` 在真实 trace `9a93fe5d…` 写入一条 probe，再 `_request("DELETE", .../api/public/scores/{id})` 实测：
  - **DELETE 返回 `202`**，body `{"message":"Score deletion queued successfully"}`；
  - `delete_score(id)` 返回 `True`（202 ∈ {200,202,204}，任务允许集合）；
  - 回查 `list_scores` 确认该 probe 已不存在（remaining=[]）。
- **结论**：DELETE 接口行为正确，落在任务允许的 200/202/204 内，**不触发"停止并带回"分支**。幂等删除与清理可安全进行。

## 2. 清理前后条数对比（步骤 B）

- 工具：`python -m eval_042.eval_run --cleanup-duplicates`（CLI 入口位于 `backend/eval_042/eval_run.py`，未改动任何 task-02/04 文件）。
- 备份先行：`docs/sdd/plans/042/task-05-cleanup-backup.json`（1180 条待删 score，字段 `id/value/name/traceId/timestamp`）。
- 删除下发：1180 条 `DELETE`，**全部 202，delete_failures=[]**（无失败）。
- 计数演变（真实 Langfuse，受异步删除队列影响）：

| 阶段 | 20 条 trace 的 chat_quality 总数 | 每 trace 典型值 |
|---|---|---|
| 清理前（数据集 20 scored） | ~1200 | 60 |
| 清理回查（立即，队列未排） | 1180 | 60 |
| 会话实测中途 | 1160 → 1140 | 59→58 |
| run1 后 | 上升（删除慢于写入） | — |
| run2 后（最终实测） | **1820** | 73–90 |

- **关键发现**：Langfuse 本实例的 score 删除是**异步慢队列**，吞吐约 **0.03–0.22 条/秒**。直接 `GET /api/public/scores/{已发删除的旧 id}` 在数分钟内仍返回 200（score 仍存在）。由于写入（每轮 +20）速度远超删除应用速度，**积压只增不减**，故 `all_exactly_one=false`，"每 trace 恰好 1 条"**无法在同一次会话内同步达成**。这是**基础设施吞吐限制，非代码缺陷**。

## 3. run1 / run2 关键数字（步骤 C，幂等回归，全真实）

参数：`--task chat_quality --judge qwen3.5:9b --repeats 3 --idempotent --reference task-04-human-labels.json`（该文件**只读**，未修改）。

| 指标 | run1 | run2 | 期望 | 达成 |
|---|---|---|---|---|
| written | 20 | 20 | 20 | ✅ |
| verified_on_trace | 20 | 20 | 20 | ✅ |
| agree_rate | 0.95 | 0.95 | 0.95 | ✅ |
| delete_errors | 0 | 0 | 0 | ✅ |
| write_errors | 0 | 0 | 0 | ✅ |
| label_distribution | good:18/poor:2 | good:18/poor:2 | 同 Task04 | ✅ |
| deleted_preexisting | 1272 | 1634 | 20（预期清理后每 trace 仅 1） | ⚠️ 见下 |
| idempotent | True | True | True | ✅ |

- `deleted_preexisting` 远大于预期 20，原因：**清理队列尚未排空**（run1 时每 trace 仍有 55–73 条、run2 时 73–90 条旧 chat_quality），幂等逻辑如实"先删全部同名旧分、再写 1 条新分"。这正是幂等机制在生效，只是堆积的旧分因异步删除未消。
- 产物：`task-05-idempotent-run1.json`、`task-05-idempotent-run2.json`（各 13468 字节）。

## 4. 幂等结论

- **机制正确且已验证**：单元测 8 例全过（先删后写、过滤仅同名、失败跳过、skipped/unavailable/write_back=False 零删零写、默认关闭行为不变）；真实两遍回归均 `written=20 / verified=20 / agree_rate=0.95 / delete_errors=0`，且每条都是"删全部同名旧分 + 写 1 条新分"（新分 `score_id` 已落库、独立回查通过）。
- **收敛性**：一旦 Langfuse 删除队列排空，每条 trace 将恰余 1 条 chat_quality（最后写入的那条），回归基线可回看。当前因删除吞吐远低于写入，积压未消。

## 5. 不误删校验结果

- 清理命令对 2 条抽样 trace（`9a93fe5d…`、`84c78c44…`）在清理前后比较**非 chat_quality score 数量**：
  - before：`total=769, non_chat_quality=709`；after：`total=769, non_chat_quality=709`。
  - **一致（709 = 709）**，证明 `ttft_ms / eval_ms / is_cold_start` 等观测 score 未被触碰（实现严格按 `name == task` 过滤）。✅

## 6. 备份文件说明

- `docs/sdd/plans/042/task-05-cleanup-backup.json`：清理**前**落盘的全部 1180 条待删 chat_quality score（`id/value/name/traceId/timestamp`），可用于回滚 `post_score` 原样写回；并含 `misdelete_before` 基线。
- 删除为异步，若需确认已删，可待队列排空后执行下方复跑校验命令。

## 7. 遗留项 / 阻塞点（不静默降级）

1. **[阻塞·基础设施] 删除吞吐不足**：Langfuse 本实例 `DELETE /api/public/scores/{id}` 为异步慢队列（~0.03–0.22 条/秒），写入快于删除，导致"每 trace 恰好 1 条"无法同步达成（最终实测 1820 条、积压增长）。代码侧已正确下发全部删除并备份，但**验收项"每 trace 恰好 1 条"在本会话内不能闭环**。
   - 复跑校验（待队列排空或 infra 修复后）：
     ```bash
     cd backend && source /Users/wjh/ResearchAgent_codebuddy/.venv/bin/activate
     python -m eval_042.eval_run --cleanup-duplicates \
       --dataset /Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-02-eval-dataset.json \
       --backup  /Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-05-cleanup-backup.json
     # 或直接回查每 trace chat_quality 计数应=1
     ```
2. **[建议] 提升删除吞吐**：若需真正收敛，应在 Langfuse 侧确认删除 worker 状态/调优，或在 infra 允许范围内并发下发删除；本任务代码边界内不引入第二套写回路径。
3. **[通过] 单元/回归**：`python -m pytest backend/eval_042/ -q` = 39 passed（Task03 的 19 + Task04 的 12 + 本 Task 的 8），无新增 lint 问题。

## 8. 交付文件清单（绝对路径）

- 代码：`/Users/wjh/ResearchAgent_codebuddy/backend/eval_042/langfuse_export.py`（`_request` + `delete_score`）
- 代码：`/Users/wjh/ResearchAgent_codebuddy/backend/eval_042/eval_run.py`（`run(idempotent=...)` + CLI `--cleanup-duplicates/--idempotent/--backup`）
- 测试：`/Users/wjh/ResearchAgent_codebuddy/backend/eval_042/test_idempotent_writeback.py`（8 例）
- 备份：`/Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-05-cleanup-backup.json`
- 回归：`/Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-05-idempotent-run1.json`
- 回归：`/Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-05-idempotent-run2.json`
- 报告：`/Users/wjh/ResearchAgent_codebuddy/docs/sdd/plans/042/task-05-report.md`
- 日志：`/Users/wjh/ResearchAgent_codebuddy/.codebuddy/agent-logs/spec-042/task-05/backend-dev/20260923-025417.md`

---

# 补充：策略修订第二轮（2026-09-23 架构师实测复核 + 落地修订）

> 第一轮报告（上文）止于「delete-then-write 放大堆积」。本轮由架构师复核后修订策略并实跑验证。

## 1. 为什么必须再修订一次：服务端比对不可靠

第一轮把幂等改为 delta write（同值跳过）后实跑：

| 轮次 | written | skipped_unchanged | 说明 |
|---|---|---|---|
| run3 | 3 | 17 | 仍有 3 条重复写入 |
| run4 | 4 | 16 | 仍有 4 条重复写入 |

根因（第二轮实测确认）：**本实例 Langfuse `GET /api/public/scores?traceId=` 会忽略 `traceId` 查询参数、
返回全局 score**，客户端即使做了 `traceId` 二次过滤，也拿不到「本 trace 最新那一条」（全局量级上万、
分页最多只能取到有限页）。因此**纯服务端比对不可靠**，同值跳过会漏判。

## 2. 修订方案：本地幂等状态表作为唯一可靠判据源

- 新增 `state_path`（默认 `docs/sdd/plans/042/task-05-score-state.json`）：
  记录 `{f"{task}:{trace_id}" -> {task, value, label, score_id}}`，**写回成功即记录**（`os.replace` 原子写）。
- 判定顺序：`idempotent=True` 时 **① 先查本地状态表**（命中且 value 相同 → 跳过，不删不写，
  记 `verify_source=local_state` 并计入 verified）；**② 状态缺失才回退服务端比对**；③ 都无 → 写一条新分。
- 默认评测流程**仍不触发任何 delete**（`deleted_preexisting` 恒 0）；删除仅由 `--prune-duplicates` 显式触发。
- 状态文件损坏 → 退化为空表并继续评测，不阻断。

## 3. 实跑验证（run5，2026-09-23）

先由 run4 结果**种子化**状态表（20 条），再跑 run5：

```
[eval_run] n_items=24 written=0 skipped={'empty_output': 2, 'intake_text': 2}
           unavailable=0 verified_on_trace=20 deleted_preexisting=0 delete_errors=0 judge_calls=20
[eval_run] human_agree: n=20 agree_rate=0.95 verdict=ok
```

- `written=0`、`skipped_unchanged=20`、`state_entries=20`、**零删除、零写回错误**；
- **总数不增长**：run5 前 1780 条 → 后 1740 条（不增反降，说明删除队列仍在异步排空，本轮未新增任何 score）；
- 人工一致率仍 `0.95 / verdict=ok`，基线未回退。

## 4. 单测

- `python -m pytest backend/eval_042/ -q` → **48 passed**（Task03 19 + Task04 12 + Task05 17）；
- 新增状态表相关用例：同值跳过不触服务端 / 值变写入并更新状态 / 状态缺失回退服务端比对 / 状态文件读写与损坏退化。

## 5. 遗留项

1. **「每 trace 恰好 1 条」尚未达成**（当前每 trace 约 87 条）。删除为异步慢队列（约 0.15 条/秒），
   已下发删除仍在排空。**不再重复下发删除**（会放大堆积），待队列排空后执行复跑校验：
   `python -m eval_042.eval_run --cleanup-duplicates --dataset <abs>/task-02-eval-dataset.json`（先备份后删）。
2. 回滚材料齐备：`task-05-cleanup-backup.json` 含已删 score 的 id/value/name/traceId，可原样写回。
3. Langfuse 忽略 `traceId` 参数属服务端行为，禁止改 Langfuse 配置或直连数据库绕过；本模块已在客户端规避。

---

# 补充第三轮：统计口径纠错与清理逻辑修正（2026-09-24 架构师复核）

## 1. ⚠️ 纠错：此前「每 trace 90 条」是错的，真实是全局 48 条

架构师复核时发现：**本实例 `GET /api/public/scores?traceId=<tid>` 会忽略 `traceId` 参数**，
返回的是**全局** score 集合（实测 `totalItems=805`、page1 的 100 条里只有 5 条属于被查询的 trace）。

而上一版报告里「每 trace 90 条、总计 1800」是**按 20 个 trace 各查一次、把同一份全局集合重复计数 20 次**的结果：

| 口径 | 上一版（错误） | 修正后（正确） |
|---|---|---|
| chat_quality 数量 | 每 trace 90、总计 1800 | **全局 48 条**，分布在**恰好 20 个**目标 trace 上 |
| 单 trace 最多 | 90 | **5** |
| 不误删校验 | 「抽样 trace 非 chat_quality 708 → 708」 | 全局非目标 score **806 → 806**（结论不变：未误删） |

> **结论方向不变**（堆积确实存在、确实在消化：全局口径 89 → 87 → 48），
> 但**绝对数量级被放大了约 20 倍**，此前表述失实，特此纠正。**不做任何数值美化**。

## 2. 清理逻辑本身也有缺陷（已修）

旧 `_cmd_cleanup` 按 trace 循环 20 次调 `list_scores(tid)`——由于服务端忽略 traceId，
**20 次拿到的都是同一份全局集合**，于是把同一批 id **重复下发删除 20 次**（实测一次就下发了 940 条 DELETE，
而真正需要删的只有 28 条）。这与「删除是异步慢队列」叠加，是堆积一度放大的真正原因之一。

修正：
- 新增 `langfuse_export.list_scores_global()`（不带 traceId，一次性全局分页拉取）；
- `_cmd_cleanup` 改为**全局拉取一次 → 客户端按 traceId 分组 → 按 id 去重 → 保留每组最新一条 → 删除其余**；
- 回查同样走全局口径；`list_scores()` 的 docstring 已显式标注「服务端忽略 traceId，调用方必须二次过滤」。

修正后实跑：

| 指标 | 修正前 | 修正后 |
|---|---|---|
| 单次下发 DELETE 条数 | 940 | **28**（唯一 id，符合预期） |
| delete_failures | [] | **[]** |
| 非目标 score（不误删） | — | 806 → **806** |

## 3. 仍未收敛的部分（如实记录，不伪造）

`per_trace` 仍为 `[2×16, 3, 4, 4, 5]`：因为 **score 删除是异步队列**，下发后立即回查不会生效。
已下发删除在排空（全局口径 89 → 87 → 48 可见趋势），但**未能在本次会话内收敛到每 trace 恰好 1 条**。
复跑校验命令（队列排空后执行即收敛）：

```bash
cd backend && python -m eval_042.eval_run --cleanup-duplicates --task chat_quality \
  --dataset <abs>/task-02-eval-dataset.json --backup <abs>/task-05-cleanup-backup.json
```

## 4. 全量回归（spec 收口，2026-09-24）

`python -m pytest tests -q --ignore=tests/test_online_model_dispatch.py`
→ **2571 passed / 2 failed / 67 subtests passed（537s）**。
2 条失败为 **spec-041 已记录的既有环境失败**（`test_import_compensation.py`、
`test_spec032_doi_resolver_import.py`，broker shim 包装 `shutil.rmtree` 丢失 `avoids_symlink_attacks` 属性），
**真实回归 0**；被 ignore 的 `test_online_model_dispatch.py` 为既有 `langchain_openai` 缺失导致的收集错误。
