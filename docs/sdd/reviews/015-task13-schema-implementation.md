# Spec015 Task13 — Schema v2 迁移实现文档

- 文件：`backend/app/services/paper_discovery_store.py`、`backend/app/domain/paper_discovery.py`
- 生成时间：2026-09-05 10:17 CST
- scope：仅 `paper_discovery_store.py` 的缩进与单例索引容错（本轮聚焦修复）；`domain/paper_discovery.py` 未改动。

## 1. 实际生效的 schema_version

- 常量 `SCHEMA_VERSION = 2`（`paper_discovery_store.py:27`）。
- 迁移判定：`__init__` 中 `current = self._current_schema_version(...)`，当 `(current or 1) < SCHEMA_VERSION` 时执行 `_migrate_to_v2`：
  - 全新库 `_current_schema_version` 返回 `None` → `1 < 2` → 触发迁移并写入 version=2。
  - v1 库（无 schema_meta 行或 version=1）→ 触发迁移。
  - 已 v2 → 不重复迁移（幂等）。

## 2. 七张新增表（均由 `_migrate_to_v2` 以 `IF NOT EXISTS` 创建）

1. `source_fetch_units`（:147）
2. `catalog_papers`（:170）
3. `catalog_source_records`（:194）
4. `search_jobs`（:207）
5. `search_source_progress`（:225）
6. `search_events`（:241）
7. `search_results`（:253）

v1 既有表 `conference_sources`/`search_sessions`/`paper_candidates` 在 `_initialize_v1` 中保留并升级，语义不变。

## 3. 迁移事务设计（对应 C-1）

- 单事务：所有建表语句与版本号写入都发生在 `__init__` 的同一个显式 `connection.execute("BEGIN")` … `connection.commit()` 内。
- 先迁移后升版本号：`_migrate_to_v2` 先创建七张表，再由 `_validate_schema_meta` 在尾部把 `schema_meta.version` 写入/更新为 `SCHEMA_VERSION(=2)`。
- 幂等：所有 DDL 均为 `CREATE TABLE/INDEX IF NOT EXISTS`；`_migrate_source_fields` 用 `PRAGMA table_info` 判列存在后再 `ALTER ADD COLUMN`；`_seed` 用 `ON CONFLICT DO NOTHING`；版本号写入走 INSERT/UPDATE 分支。
- 失败回滚：任一语句抛异常时事务不 commit，`_connect()` 退出时回滚，schema 与版本号保持一致（不会出现“表建了一半而 version=2”）。

## 4. 外键 ON DELETE RESTRICT 决策（对应 C-3）

- v2 新增表的外键统一使用 `ON DELETE RESTRICT`（:197、:199、:227、:244、:255、:257），以保留来源证据与冻结结果，不级联删除。
- v1 既有 `paper_candidates.search_id → search_sessions` 仍为 `ON DELETE CASCADE`（:83、:342），本轮未改 v1 语义。

## 5. metadata_hash / index_status 行为

- `catalog_papers` 维护 `metadata_hash` 与 `index_status`。
- `upsert_catalog_paper` 语义：读取现有 `metadata_hash`，若与新 hash 相同则不写行、`updated_at` 不动、返回 `False`；若不同（或原行不存在）则写入并置 `index_status='pending'`（即需要重新索引），返回 `True`。该判断保证仅当内容变化时才失效索引，且 `'pending'` 合法落于 catalog_papers 的 CHECK(pending/indexed/failed) 约束内。

## 6. 本轮聚焦修复点（非重写）

- 缩进：`_current_schema_version`（原 110–129 行）方法体统一为 8/12/16 空格；`upsert_catalog_paper` docstring 起始行 9→8。修复后整文件 `py_compile` 通过。
- 单例索引容错：`_initialize_v1` 中 `CREATE UNIQUE INDEX ... schema_meta_singleton ON schema_meta((1))` 改为 try/except `IntegrityError`（best-effort）。原因：`test_store_rejects_multiple_schema_metadata_rows` 先 `DROP INDEX schema_meta_singleton` 再插入第二行，重建 store 时该 CREATE 直接抛 IntegrityError，使 `_current_schema_version` 的“exactly one row”检测不可达；容错后多行表交由 `_current_schema_version` 抛出 `RuntimeError("...expected exactly one row")` 并由事务回滚，恢复基线行为。

## 7. 验证命令与退出码

```
$ .venv/bin/python -m py_compile backend/app/domain/paper_discovery.py backend/app/services/paper_discovery_store.py
exit=0

$ .venv/bin/python -m pytest -q tests/test_paper_discovery_store.py
.....
5 passed in 0.06s
exit=0
```

测试计数：5 passed（`test_store_seeds_reads_and_enforces_candidate_doi`、`test_store_allows_stable_candidate_id_across_search_sessions`、`test_store_rejects_multiple_schema_metadata_rows`、`test_store_rejects_damaged_schema_metadata_table`、`test_save_conference_explicit_transaction_is_committed`）。

## 8. 遗留风险与子任务 C 待办

- 并发/租约：`lease_owner`/`lease_expires_at` 字段已建，但并发抢占续租逻辑与测试留待子任务 C。
- 冻结分页：`search_jobs`/`search_results` 的冻结分页与游标语义测试待子任务 C。
- 本轮未做 git 操作；未改动 v1 表语义、未新建连接层、未联网、未触碰 Spec017。
