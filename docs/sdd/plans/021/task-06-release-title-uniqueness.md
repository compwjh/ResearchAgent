> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`完成`

# Task06 释放已完成/失败/取消条目占用的唯一索引

## 状态与一句话目标

`完成`。把 `import_item_title` 部分唯一索引的占位范围收缩为**仅活跃态**，让已完成 / 失败 / 取消的条目不再阻塞同一论文的重新导入与重试；去重职责交给知识库既有 `find_existing`（`PAPER_ALREADY_EXISTS` / `existing`）。

## 背景与决策

- 现状索引（实测 DDL）：
  ```sql
  CREATE UNIQUE INDEX import_item_title ON paper_import_items(
      normalized_title, COALESCE(year, -2147483648), COALESCE(conference_id, X'00'))
  WHERE normalized_title IS NOT NULL
    AND state IN ('queued','downloading','waiting_login','validating','indexing','completed')
  ```
  即 `completed` 也占位 → 一篇已在别的批次成功导入的论文，既不能新建批次、也不能重试同批次的失败条目，只能回原批次操作；失败/取消本就不占位。
- 用户 2026-09-10 拍板：**释放**。
- 目标形态（WHERE 收缩为活跃态）：
  ```sql
  ... WHERE normalized_title IS NOT NULL
    AND state IN ('queued','downloading','waiting_login','validating','indexing')
  ```
- 释放后的去重链路：`backend/app/knowledge_base/application.py` 的 `import_paper` 会先 `find_existing(snapshot)`，命中即返回既有记录（`existing=True`）→ 导入结果表达为 `PAPER_ALREADY_EXISTS`（"论文已在知识库中"），不会重复入库。

## 数据、配置与接口

- **索引语义**：活跃态互斥保留；`completed` / `failed` / `cancelled` 释放。
- **错误语义**（不变，沿用 Task03）：活跃态冲突 → 409 `DUPLICATE_IMPORT`；终态不冲突，走正常导入流程。
- **迁移**：必须走 `paper_import_batch_store.py` 既有的 schema 版本机制（`paper_import_schema_meta` / `_ensure_schema` / 迁移步骤），
  在真实库上 drop 旧 index → 按新 WHERE 重建；**不得**删表重建、**不得**丢数据、**不得**绕过版本记录。

## 实施步骤与文件边界

**文件边界**：只改 `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`（迁移 + 索引定义）、必要时 `backend/app/paper_discovery/application/paper_import_batch_service.py`（确保结果表达），以及 `tests/` 下后端测试。**不得改 `frontend/**`**；不得改 CAS / 并发领用 / 租约语义。

1. **先写测试**（TDD，至少覆盖）：
   - 旧库形态 → 迁移后索引 WHERE 只含活跃态（断言 `sqlite_master.sql` 或行为等价物）；
   - 已完成条目**不再**阻止同论文新建批次；
   - 失败/取消条目**不再**阻止重试（`retry_item` / `retry_batch` 可重跑）；
   - 两个**活跃态**条目仍互斥（并发重复导入 → 409 `DUPLICATE_IMPORT`）；
   - 重新导入已入库论文 → 结果表达为 `existing` / `PAPER_ALREADY_EXISTS`，**不得**重复落盘（用 `data/kb/papers.json` 或注入的 port 断言只有一条）。
2. 在 store 中新增一次幂等的迁移步骤（**v1 → v2**，即 `SCHEMA_VERSION` 由 1 改为 2，只接受版本 1 与 2，不是 2→3），drop & create 索引。
3. 确认 `retry_item` / `retry_batch` / `create_batch` 在该形态下行为正确；若 `DUPLICATE_IMPORT` 捕获逻辑依赖旧假设，同步调整（例如改为只在活跃态冲突时映射）。
4. 保持既有 49+ 用例不回归。

## 子代理分派

- 角色：`backend-dev`（`Deepseek-V4.1-Flash`，32k）。
- 最小上下文：本文件 + spec-021 §边界最后两条与 §明确不做 + `paper_import_batch_store.py` 的 schema/迁移与索引定义段 + `paper_import_batch_service.py` 的 `create_batch`/`retry_batch`/`retry_item`。
- 单次范围：≤2 个代码文件、≤150 行；迁移与测试可各一轮。
- 回传：测试结果先行，日志路径必给。

## 边界与明确不做

- 不改 CAS / 并发领用 / 租约语义；不改其它索引与表结构。
- 不放弃活跃态互斥保护（并发重复导入仍须 409）。
- 不做"删除历史批次/条目"来腾位；不改 `frontend/**`；不改 KB 的 `find_existing` 语义。
- 不做自动重试、不做退避策略。

## 验收、风险与回滚

**验收**：
1. `cd /Users/wjh/ResearchAgent_codebuddy && .venv/bin/python -m pytest tests/test_paper_import_batch_api.py tests/test_paper_import_batch_service.py tests/test_paper_import.py -q`（基线 49 passed + 新增用例全过）。
2. `cd /Users/wjh/ResearchAgent_codebuddy && .venv/bin/python -m pytest -q`（全量，基线 819 passed + 新增，0 failed）。
3. `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`（无新增告警）。
4. **产品级（架构师已在 8123 实测，作为本任务验收）**：
   - 对"已在别的批次 `completed` 且已入库"的论文新建批次 → **200 `queued`**（不再是 409），轮询后 `completed`，item 复用既有 `paper_id`、`data/kb/papers.json` 中该论文**仍只有一条**（实测批次 `5e16a6de-7864-45f7-8913-b22554520e2a`：item `completed`、`paper_id=abe90779738541d387733e54fbffc4f0`、同名条目数 = 1）。
   - 同一候选**连续两次**提交 → 第 1 次 200、第 2 次 **409 `DUPLICATE_IMPORT`**（活跃态互斥保留）。
   - 真实库迁移：`paper_import_schema_meta.version` 由 1 变 2，`import_item_title` 的 WHERE 仅剩活跃态；重复执行幂等。

**风险**：迁移必须幂等且在真实库（`data/paper_search/state.sqlite3`）上可重复执行；索引重建失败要能安全回滚到迁移前版本，不得让 store 进入不可用状态。

**回滚**：回退本次 commit；若迁移已落库且需回退，按 store 版本机制提供反向迁移（drop 新 index → 重建旧 WHERE），并在回传中说明可执行命令。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、改动文件与行数、日志路径）。
