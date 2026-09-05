# Spec015 Task13 — 仓储行为（schema v2）实现文档

- 文件：`backend/app/services/paper_discovery_store.py`（子任务C 增量位于 768–871 行）、`tests/test_paper_discovery_store.py`
- 实现：`junior-dev`（`qwen3.8:27b-mlx`）；本文档由**主 Agent 代行**撰写（纯文档，无代码改动，符合代行例外条件）
- 日期：2026-09-05 ｜ 依赖：子任务B 的 schema v2 迁移（见 `015-task13-schema-implementation.md`）

## 1. 仓储方法清单（子任务C 增量）

| 方法 | 语义 |
|---|---|
| `acquire_fetch_unit(fetch_unit_id, owner, lease_seconds, now=None) -> bool` | **原子领取**：单条条件 `UPDATE ... WHERE fetch_unit_id=? AND (lease_owner IS NULL OR lease_expires_at < now)`，以 `cursor.rowcount > 0` 判定成功 |
| `renew_lease(...)` | 仅当前持有人在租约**未过期**时可续租 |
| `release_lease(..., status='completed')` | 仅持有人可释放，清空 `lease_owner`/`lease_expires_at` |
| `get_search_results_page(search_id, page, page_size=10)` | `ORDER BY rank LIMIT/OFFSET`，1-based 固定分页（默认每页 10 条） |
| `_add_seconds(...)` | RFC3339 UTC 时间加减（辅助，复用 `_utcnow()` 格式） |

子任务B 已实现并沿用：`save_fetch_unit` / `get_fetch_unit` / `upsert_catalog_paper` / `get_catalog_paper` / `save_source_record` / `create_search_job` / `save_source_progress` / `append_search_event` / `save_search_result` / `get_search_results`。

## 2. 原子领取与并发正确性（核心）

领取判定被压缩为**一条** UPDATE 语句，条件谓词 `lease_owner IS NULL OR lease_expires_at < now`：

- 未领取 → 可领取；
- 租约已过期（`lease_expires_at < now`）→ 任何 owner 可重新领取（**租约恢复**）；
- 租约仍有效 → 其他 owner 一律被拒绝。

**正确性来源**：SQLite 在 WAL 下对写事务串行化，配合 `busy_timeout=5000`；单条 UPDATE 的 `WHERE` 在获得写锁后依据**已提交的最新状态**重新求值，因此并发连接中只有一个能满足谓词，其余 `rowcount=0`。刻意**不**采用 SELECT-then-UPDATE（那会在"检查"与"写入"之间引入竞态）。时间比较基于 RFC3339 UTC 字符串的字典序，与实际时序一致。

## 3. 冻结结果与固定分页

- **不可改写**：`save_search_result` 使用 `ON CONFLICT(search_id, catalog_paper_id) DO NOTHING`，重复写入不覆盖既有冻结结果。
- **固定分页**：`get_search_results_page` 仅按 `rank` 排序（`ORDER BY rank`），`LIMIT/OFFSET` 取页，page 为 1-based、默认每页 10 条。21 条结果下页 1/2/3 = **10/10/1**，且重复读取顺序一致。

## 4. 来源证据可追溯

`save_source_record` 以 `(source_kind, source_key)` 唯一约束写入 `catalog_source_records`，保留 `raw_metadata_json` 原始元数据，外键 `ON DELETE RESTRICT`（C-3），来源证据不会被级联删除。

## 5. 缺陷修复（子任务B 遗留，本轮暴露并修复）

`upsert_catalog_paper` 第 593 行原为 `changed = existing is None`，导致「行已存在且 `metadata_hash` 变化」时，虽执行了 UPDATE（置 `index_status='pending'`）却返回 `False`，违反「哈希变化需重新索引」的验收语义。

已改为：

```python
changed = existing is None or existing[0] != paper.metadata_hash
```

由新增用例 `test_upsert_catalog_paper_metadata_hash_semantics` 覆盖。该缺陷正是由补齐测试所暴露，印证「测试补齐是本切片必要环节」。

## 6. 验证结果

| 命令 | 结果 | 退出码 |
|---|---|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_store.py` | **10 passed** | 0 |
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import.py` | **22 passed**（旧导入仓储回归） | 0 |
| `git diff --check -- backend/app/services/paper_discovery_store.py` | 干净 | 0 |

新增 5 个用例：

- `test_upsert_catalog_paper_metadata_hash_semantics` — 哈希不变不更新 `updated_at` 且返回 False；变化置 `pending` 并返回 True
- `test_acquire_fetch_unit_atomic_single_winner_across_10_rounds` — 并发领取**连续 10 轮**，每轮唯一 owner
- `test_acquire_fetch_unit_expired_lease_can_be_recovered` — 租约过期后可被其他 owner 恢复领取
- `test_get_search_results_page_freezes_21_rows` — 21 条结果分页 10/10/1
- `test_save_source_record_is_traceable` — 按 `(source_kind, source_key)` 取回 `raw_metadata_json`

## 7. 主 Agent 回填校验（Task13 文档第 96–103 行）

以一次性脚本（置于 `/tmp`，已清理，未进仓库）在临时目录构造 v1 数据库后升级，结果：

1. v2 七张表全部创建：**True**
2. v1 四张表原地保留：**True**
3. `schema_meta` 升为 2：**True**
4. 旧数据保留（legacy 会议 `ccs-legacy`、候选 `c-legacy` 均存在）：**True**
5. 重复打开（幂等）：version 仍为 2，无异常
6. 迁移中断（注入 `_migrate_to_v2` 抛错）：`source_fetch_units` **未残留**（事务回滚）、version 仍为 1 → **失败不留半张表**

## 8. 遗留风险与后续

- 并发领取已在**单进程多线程**下验证 10 轮；跨进程场景依赖 WAL + busy_timeout，尚未做多进程压测。
- kb collection 参数化（缺口 G-1 / 约束 C-4）属后续任务（Task14+），本任务未涉及。
- 本任务未新增 HTTP 路由、未联网、未创建 Qdrant collection（C-5）；未复用导入批任务状态机语义（C-2）。
