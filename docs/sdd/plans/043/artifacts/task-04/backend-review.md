# Spec043 Task04 后端独立集中评审

日期：2026-10-20
角色：backend-reviewer（只读独立复审）
范围：`backend/**` Task04 实际 diff、`tests/literature_maps/**` 受影响测试、SQLite 精确 probe。
明确不做：不重审 Task03 已通过代码；不改业务代码/测试；不部署、不真实 provider 外呼、不读 `.env`、不跑全量回归。

> 文末“P1 修复集中复审”覆盖并 supersede 本文前段的历史初审 BLOCK；前段保留原始复现证据。

## 结论

**历史初审：BLOCK（四项 P1 已修复；最终以文末集中复审为准）**。

已有实现覆盖了 preview 持久化、后台 executor、checkpoint、跨连接恢复、CAS、owner 隔离、候选句柄校验、20/200 原子上限和 stop 晚回调保护；但以下 P1 会破坏 Task04 的核心合同，必须集中修复后再复审：

1. **P1：有 preview 时删除地图必失败。** `literature_map_previews.job_id` 外键指向 `literature_map_jobs`（`backend/app/literature_maps/infrastructure/store.py:249-265`），但 `delete_map` 在 `store.py:549-562` 先删 jobs，未删 previews；SQLite `foreign_keys=ON` 下实际得到 `sqlite3.IntegrityError: FOREIGN KEY constraint failed`，事务回滚，地图无法删除。该缺口同时阻断“删除地图不被旧作业复活”的完整合同。
2. **P1：不可重试失败可被 retry 重入队。** `service.py:291-305` 允许 `failed/partial/stopped` 作业直接进入重试，`service.py:300-303` 仅按 unit 名决定步骤，不过滤 `retryable`；`store.py:1024-1046` 也无 retryable 守卫。真实 SQLite probe 将 `SEMANTIC_SCHOLAR_INVALID_RESPONSE`（`retryable:false`）终结为 failed 后，`retry_job` 返回 `queued`，并保留该不可重试单元。违反接口“只补可重试失败和未完成单元”。
3. **P1：refresh 外呼预算可达 61，超过合同 60。** `service.py:477-503` 对 60 个已有 S2 ID 先做一次 `batch` metadata 请求，`service.py:527-557` 再以 `GRAPH_REQUEST_BUDGET=60` 做 60 次关系请求；同一 preview 实际为 1+60 次 provider 调用，且 preview job 未持久化 provider request count。应把 batch 也计入同一 job 预算，并在持久 checkpoint/job counts 中可观察。
4. **P1：restore 单节点会恢复指向仍被墓碑节点的边。** `store.py:836-842` 无条件插回 `removed_edges_json`；当 A、B 均被 remove、仅 restore A 时，SQLite 真实 probe 仍返回 A→B edge，而 B 仍 `removed=true`。应只恢复另一端仍 active 的边，并保留该边供显式 restore B 时再恢复；不得让图出现指向 removed 节点的关系。

上述问题不是 style 意见：第 1 项是可复现的 SQLite 完整操作失败，第 2/3 项直接突破 retry/预算安全边界，第 4 项破坏墓碑关系一致性。

## 逐项核查

| 合同项 | 结果 | 代码/证据 |
|---|---|---|
| preview 不改节点集、候选为服务端持久快照 | **GO** | `service.py:349-410,441-475`；9 项精准测试通过，preview 创建后节点集保持为空 |
| topic/references/citations/refresh 计算与持久 job | **GO（限 fake provider）** | `service.py:412-557`；executor 先落盘 queued preview/job，计算后写入 candidates/diff/warnings；未做真实 provider E2E |
| 后台 executor、checkpoint、跨连接重启恢复 | **GO（限 fake provider）** | `service.py:241-254,412-434`、`store.py:1004-1115`；不同 `LiteratureMapStore` 连接上先 claim 为 running，再 `recover()`，结果为 `recover_count=1`、preview/job/checkpoint 均 completed |
| CAS、owner guard、同 key 幂等 | **GO** | `store.py:716-803,811-865`；并发两个 apply 仅 1 成功、另 1 `revision conflict`；owner-b 读取返回 `LookupError`；重复 key 返回原句柄 |
| 输入候选伪造禁止 | **GO** | API body 只接收 `selected_candidate_ids`（`routes_literature_maps.py:83-88`）；服务端对 preview 快照 ID、already_present、removed 校验（`service.py:575-599`）；伪造 ID 得 `INVALID_PREVIEW_CANDIDATE` 且节点数仍 0 |
| 每批 20、总量 200、事务原子 | **GO** | `store.py:750-757`；21 个候选得 `PREVIEW_BATCH_LIMIT` 且 0 节点，200 active 时再加 1 得 `MAP_NODE_LIMIT` 且仍 200 节点 |
| refresh metadata/关系 diff 不直接改图 | **GO（关系删除 diff 需后续明确）** | `service.py:477-557` 只读节点/边并生成 diff，apply 才写；现有测试确认 metadata diff、位置/group/document/download 保持；实现只记录关系 added，未证明/实现有效 provider 响应下的 removed diff，不得把当前实现宣称为完整关系刷新 |
| remove/restore 墓碑、布局/分组/document 保留 | **BLOCK（边一致性）** | 节点字段保留且自动补缺对 removed candidate 拒绝；但 restore 会插回指向仍 removed 节点的边，见 P1-4 |
| stop 与晚回调 | **GO** | `store.py:1048-1068`、`complete_preview:680-694`；stop 后直接调用 preview worker，preview 仍 queued、job stopped、无 checkpoint 写入 |
| delete 与晚回调 | **BLOCK** | `delete_map:549-562` 与 preview/job FK 顺序导致 P1-1，未达到合同 |
| retry 只补可重试失败、保留 60 预算 | **BLOCK** | retry 无 `retryable` 过滤（P1-2）；refresh 1+60 外呼（P1-3） |

## 精确验证

### 受影响领域测试

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | 9 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 99 passed |
| `.venv/bin/python -m ruff check backend/app/literature_maps backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | All checks passed |
| `git diff --check` | 0 | passed（backend 实际 diff） |

### 独立 SQLite probe

命令：

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/task04_backend_review_probe.py
```

命令退出码 **0**；该 probe 只用临时 SQLite 和确定性 fake provider，不代表真实 API E2E。关键输出：

```text
CAS_OWNER ... 1 个 ok(revision=1)、1 个 ValueError:revision conflict、nodes=1、owner-b LookupError
RESTART ... recover_count=1、preview=completed、job=completed、checkpoint=completed
DELETE ... IntegrityError:FOREIGN KEY constraint failed
STOP_CALLBACK ... stop_status=stopped、map_status=stopped、preview=queued、job=stopped、checkpoint=None
RETRY ... accepted=True、status=queued、retryable=False 的 INVALID_RESPONSE 仍在 failed_units
BUDGET ... batch_calls=1、graph_calls=60、total_provider_calls=61
TOMBSTONE ... restored_removed=False、layout/group/document 保留、edges_after_restoring_only_source=1（target 仍 removed）
CANDIDATE_LIMITS ... forged=INVALID_PREVIEW_CANDIDATE、too_many=PREVIEW_BATCH_LIMIT、over_capacity=MAP_NODE_LIMIT，节点数分别 0/0/200
```

## 最小修复方向

- 删除地图：在同一 SQLite 写事务中先删除/归档 preview（以及其 job 依赖），再删 job；保留 owner/deleted guard，使晚 worker 对 stopped/deleted 地图 no-op。补 queued/running preview 的 DELETE API probe。
- retry：从 `failed_units` 仅选 `retryable=true` 或明确未完成单元；没有可重试单元时返回稳定冲突，不得把 `retryable=false` 的 provider invalid/budget/歧义失败重入队。保留成功 checkpoint，不重做成功单元。
- refresh：把 metadata batch 纳入 60 预算，预算不足时写稳定 warning/partial；将实际 provider request count 与 checkpoint/job counts 一起持久化并可 GET 观察。
- restore：只恢复两端都 active 的 saved edge；另一端仍墓碑时保持边不在活动图，待对端显式 restore 后再按保存 provenance 恢复。

## 后续边界

Task04 只有在上述 P1 修复、追加真实 SQLite 精确 probe 和独立复审通过后，才能交给 backend-tester/真实 API 门禁。当前 99 项地图域测试通过不能替代这些未覆盖的持久化竞态；本报告也不把 fake provider/内部调用当作真实 E2E，不改变 Task03 既有结论。

**最终裁定：BLOCK。**

---

## P1 修复集中复审（2026-10-20）

本节为本轮集中复审的最终裁定，范围严格限定为前述四项 P1：preview/job 删除顺序、retryable 过滤与稳定 409、refresh 共享持久 60 预算、restore 双端 active 守卫；不扩大到其它 style/关系 diff 完整性，也不重审 Task03。

### 实际代码核查与逐项结论

| P1 | 结果 | 实际实现与证据 |
|---|---|---|
| 有 preview 时删除地图 | **GO** | `store.py:549-566` 在同一事务中先删 `literature_map_previews`（line 561），再删其 FK 依赖的 jobs（line 562），并先标记 map deleted/stopped；独立 SQLite probe 删除 queued preview 后两表均为 0。 |
| retry 只重试可重试单元 | **GO** | `service.py:291-303` 只保留 `retryable is True`，全不可重试固定 `MAP_NO_RETRYABLE_UNITS`；`store.py:1040-1065` 同步拒绝全不可重试持久作业；`routes_literature_maps.py:108-110` 映射为 HTTP 409 且保留稳定 error code。精准 API 测试覆盖 exact 409；restart/retry probe 跨重开 store 验证预算耗尽后的全 false 作业拒绝重试。 |
| refresh 共享 60 provider 请求预算 | **GO** | `service.py:490-503` metadata batch 计入 `provider_request_count`，`service.py:543-550` 关系调用共用同一计数并在达到 60 时写 `MAP_GRAPH_BUDGET_EXCEEDED`；60 节点 probe 观察 batch=1、graph=59、总数=60，重开 SQLite 后 job count 仍为 60。 |
| restore 只恢复双方 active 的关系 | **GO** | `store.py:842-858` 恢复前计算 `active_node_ids`，任一端仍墓碑则跳过插边；两节点先 remove，重开 SQLite 后仅 restore source 无边，随后显式 restore target 恢复恰好一条原边。 |

### 重启、重试与持久预算 probe

命令：

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/task04_p1_fix_probe.py
```

退出码 **0**，输出摘要：

```text
DELETE_RESTORE ok preview_job_deleted=1 edge_waited_for_both_active=1
REFRESH_BUDGET ok batch=1 graph=59 durable_count=60 warning=1
RESTART_RETRY ok preview_checkpoint=completed requests=21->41->60 calls_after_budget=0
TASK04_P1_PROBE PASS
```

该 probe 使用临时真实 SQLite、多次重新打开 `LiteratureMapStore` 和确定性 fake provider；未进行真实 provider 外呼、PDF 下载、部署或生产数据操作。`RESTART_RETRY` 的 21→41→60 是持久 `job.counts.provider_request_count`，最后一次预算耗尽后 provider graph 调用数不再增加；在下一次运行把仅剩失败单元归为不可重试并拒绝 retry。

### 本轮验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_store.py` | 0 | 42 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 104 passed |
| `.venv/bin/python -m ruff check backend/app/literature_maps backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_store.py` | 0 | All checks passed |

### 最终集中裁定

**GO（仅针对本轮四项 P1 修复）。** 未发现新的 P0/P1 阻塞；Task04 后端可进入后续 backend-tester/真实 API 门禁。此 GO 不等同于 Task04 最终验收或 Spec043 收口签字：真实 provider/API、部署 smoke、跨端验收以及前段报告明确的非本轮范围仍按主会话门禁处理。
