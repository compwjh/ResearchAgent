# Spec018 Task06：批量补偿实现独立后端评审

## 复评结论（2026-09-10）

**批量补偿子门禁：GO（隔离环境）**。上次评审的两个 P1 已完成修复：

- `process_item()` / `resume_item()` 在 claim 后把持久化 attempt owner/token 传递到
  `import_candidate()`，再由它写入已有 `PaperImportRequest`；KB adapter 创建的
  capability 与 item 凭证一致。
- 默认 composition root 将同一个已注册的 `PaperImportPort.compensate_import`
  绑定到 batch service。

`cancel_batch()` 现在只更新每个 item 的当前 attempt，历史 attempt 保持不变；
snapshot 仍在创建时保存 canonical JSON + SHA-256，并在恢复及同进程复用前校验。

**Task06 总门禁仍为条件 GO / overall NO-GO**：browser、generation binding、全量
matrix 及生产切换尚未完成；本报告只批准本次 batch integration hardening 子范围。

## 原评审结论

**NO-GO（原结论，已由本次批量集成加固复评覆盖）**。

本轮实现的 SQLite 状态持久化、原子 claim、快照哈希及 API 脱敏边界基本成立；
但默认生产 composition root 没有注入补偿器，且批量编排没有把 SQLite claim 产生的
attempt owner/token 传入 `import_candidate`。真实单篇导入生成的 capability 因此无法
与批量 item 的 capability 校验对齐，失败后不能可靠进入可补偿闭环。这是 P1，必须
修复后才能把 `T-IMPORT-COMPENSATION` 标记为通过。

## 评审范围与证据

只读检查了当前未提交 diff 及其调用链：

- `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`
- `backend/app/paper_discovery/application/paper_import_batch_service.py`
- `backend/app/paper_discovery/domain/paper_import_batch.py`
- `backend/app/api/routes_paper.py`
- `backend/app/api/common.py`
- `backend/app/paper_discovery/application/paper_import.py`
- `backend/app/platform/ports.py`
- `backend/app/knowledge_base/application.py`
- `tests/test_paper_import_batch.py`

未运行真实服务、网络、Qdrant、生产数据或 `confirm-replace`。

## 已通过的局部检查

### 1. SQLite 事务、并发 claim 和 additive schema：局部 GO

- `paper_import_batch_store.py:113-173` 使用 `BEGIN IMMEDIATE`、WAL、foreign keys、
  busy timeout，并将锁错误转换为稳定错误码；批处理 claim 的 compare-and-set 位于
  `:707-732`，同一条目不能被两个进程同时从 `queued` 成功领取。
- `paper_import_items` 的新字段在 `:254-270` 采用缺列才 `ALTER TABLE` 的 additive
  migration；`paper_import_attempts` 使用 `UNIQUE(item_id, attempt_number)`（
  `:239-252`）保存 attempt 历史。
- `paper_import_batch_service.py:154-175` 对短暂 SQLite 锁做有限重试，未在锁内调用
  用户函数。

注意：schema 版本仍固定为 `1`（`paper_import_batch_store.py:35`），新表/字段的
  migration 没有独立版本号。当前兼容测试可通过，但后续 schema 演进需要补正式迁移
  版本，避免版本值无法表达实际结构。

### 2. lease owner 与 attempt owner/token：存储层 GO，端到端 NO-GO

- claim/resume 分别在 `paper_import_batch_store.py:707-759` 写入独立的
  `lease_owner`、`attempt_owner`、`attempt_token`，并新增 durable attempt 行。
- `PaperImportItem.to_dict()`（`paper_import_batch.py:124-133`）和 HTTP 白名单
  （`routes_paper.py:542-587`）不输出 token、capability、inode 或 lease owner。
- 精确 capability 比对位于 `paper_import_batch_store.py:571-598`，会校验 owner/token、
  document、stored name、source hash、dev/ino 和 destination collection。

上段是原评审发现，现已修复：`process_item()` 在
`paper_import_batch_service.py:539-563` 取得 claim 后，将 item 中的 attempt
owner/token 传给 `_import_one()`；`_import_one()` 在 `:379-410` 传给 importer。
`import_candidate()` 通过 `:350-371` 的扩展参数和 `:465-472` 的
`PaperImportRequest.replace()` 写入既有 port 请求，KB adapter 在
`knowledge_base/application.py:728-747` 因而使用同一对凭证。新增服务层和真实 KB
adapter 隔离集成测试覆盖了该链路。

### 3. 快照、hash、重启和 completed 防重跑：局部 GO

- 创建批次时将 canonical snapshot 与 SHA-256 写入 item（
  `paper_import_batch_service.py:266-298`）；重启后通过
  `paper_import_batch_service.py:300-362` 从 SQLite 恢复并验证。
- `get_snapshot()` 对篡改、非法 JSON 和缺少关键字段返回
  `SNAPSHOT_REBUILD_REQUIRED`（`paper_import_batch_store.py:514-530`）。
- `process_item()` 只能 claim `queued`（`paper_import_batch_store.py:717-722`），
  `ITEM_COMPLETED` 没有可用 transition，隔离测试验证 completed 不重跑。

剩余风险：`_snapshots` 仍保留一个进程内副本（
`paper_import_batch_service.py:148-151`、`:320-335`），虽有 SQLite hash 校验，执行时
  对同一 candidate 优先采用内存对象。建议重启/恢复路径统一只使用已验证的 SQLite
  snapshot，或对内存副本再次 canonical hash 校验，以减少同进程 stale object 风险。

### 4. retry/cancel/expired 补偿顺序：逻辑方向正确，真实闭环 NO-GO

- retry 前调用 `_compensate_item()`（`paper_import_batch_service.py:545-560`、
  `:562-572`），未知结果不会被当作成功；cancel 和 expired recovery 也尝试补偿
  （`:601-633`）。
- store 在 failure/cancel/expired 且已有 capability 时标记 `cleanup_pending`
  （`paper_import_batch_store.py:777-877`），compensation 完成要求 exact capability
  （`:571-598`）。

上段是原评审发现，现已修复：`_compensate_item()` 仍在
`paper_import_batch_service.py:492-517` 严格处理未知补偿结果，而默认构造
`backend/app/api/common.py:185-212` 已将同一已注册 port 的
`compensate_import` 注入 batch service。真实 adapter + SQLite batch 集成测试验证了
索引失败、capability 持久化、补偿及 retry 闭环。

原评审指出的 `cancel_batch()` 历史审计问题已修复。当前
`paper_import_batch_store.py:840-858` 通过关联 item 的当前 `attempt_count` 只更新
当前 attempt，历史 attempt 保持原状态。

## API 与越界检查

- `routes_paper.py:542-587` 明确构造批量响应，未见 token、capability、inode 或
  lease owner 泄漏；`routes_paper.py:500-523` 将稳定错误码映射为固定消息。
- 现有批量路由通过服务端搜索 snapshot 解析 candidate（
  `routes_paper.py:635-656`、`:686-703`），没有在 API 输入中接受可执行 capability。
- 当前 diff 未触碰真实 Qdrant、网络抓取或 `confirm-replace`，未发现越界生产操作。

## 验证命令

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch.py tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | 33 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_import_compensation.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | 41 passed |
| `.venv/bin/ruff check backend/app/api/routes_paper.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/domain/paper_import_batch.py backend/app/paper_discovery/infrastructure/paper_import_batch_store.py tests/test_paper_import_batch.py` | 0 | passed |

补充复评命令：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python -m py_compile`（批量加固涉及实现与测试文件） | 0 | 通过 |

第二组回归测试结束时测试框架输出了 Langfuse exporter 连接本机
`127.0.0.1:3000` 失败的 warning；没有启动或访问项目服务、Qdrant、远程网络或生产
数据，该 warning 不影响测试退出码。

这些是隔离/回归验证，不等价于 Task06 的全量生产门禁；`T-PAPER-IMPORT`、真实
`T-IMPORT-COMPENSATION`、browser 和 generation binding 仍未闭合。

## P0-P2 清单与建议（复评后）

### P1（已关闭）

1. 已关闭：batch service → `import_candidate` → `PaperImportRequest` 复用既有 port
   传递 claim attempt owner/token；成功、失败和异常路径使用同一 capability 凭证。
2. 已关闭：默认 composition root 已绑定真实 `PaperImportPort.compensate_import`，
   并有真实 adapter + SQLite batch 隔离集成测试。

### P2（应修复）

1. 已关闭：`cancel_batch()` 只更新每个 item 的当前 attempt，不覆盖历史 attempt。
2. 为新增表/列补可演进的 schema migration version，或在文档中明确 v1 之后的迁移
   策略；当前固定 `SCHEMA_VERSION=1` 只能支持本轮结构。
3. 重启与执行路径避免未经 hash 再验证的进程内 snapshot 优先级，增加 stale-memory
   regression test。

### P0

未发现 P0。

## 后续条件与复评边界

- P1 已满足；本次使用默认 composition 相关代码路径与临时目录/假 indexer，禁止
  真实 Qdrant）跑通：单篇成功、索引失败、source/metadata/vector 部分失败、retry、
  cancel、expired/restart、owner/token mismatch、completed 不重跑。
- 仍需重新运行 Task06 exact matrix，并由独立 tester 记录退出码、耗时和结果路径；
  本复评不替代 browser、generation binding 与全量验收。
- matrix 的 inventory hash/digest 在最终 diff 后重新生成；本报告不得被视为 GO 签字。

评审日志：本报告即为独立 backend-reviewer 评审产物；未修改业务代码。
