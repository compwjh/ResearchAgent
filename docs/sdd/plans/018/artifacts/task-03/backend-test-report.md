# Spec018 Task03-D backend-tester report

## 修复轮最新结论（2026-09-09 17:37–17:41 +0800）

**functional_verdict: PASS**。

上一轮功能阻塞已由当前实现和独立临时目录探针关闭：新导入产生完整 `knowledge-document-v1`；损坏 JSON 的写入/导入路径返回 `METADATA_INVALID` 且原 bytes 不变；canonical upsert 保留 status、双 chunker 状态、source/schema/document identity；post-replace directory-fsync 失败恢复原 metadata、保留 backup，恢复后可成功迁移并再次幂等；`find_existing` 对 malformed 无 ID 记录跳过，对 canonical 记录只返回非空 ID；naive UTC、缺 source、正常删除/路径、重复导入、四份 schema 正负实例及零 embedding/Qdrant 调用均通过。

**debt_verdict: SECURITY_DEBT（不阻塞本轮 functional gate）**。

按本轮授权，旧 `save_upload` 同 ID 覆盖、unlink 失败后 metadata/source 不一致，以及 `copy_source_exclusive` 吞掉生产目录 fsync 异常仍单列为 security debt；它们不改变本轮 functional verdict，但在 production cutover 前仍必须由后续安全任务关闭。

- 执行模型：`gpt-5.6-luna xhigh`（本轮临时授权）。
- 当前定向回归：`30 passed`；KB + paper import 全回归：`370 passed, 5 warnings, 29 subtests passed`。
- 独立临时目录最终断言：8/8 功能组通过；另有实际 application import 的完整 canonical schema 独立断言通过。
- 临时探针未访问真实 data/Qdrant，未修改业务代码、fixture 或测试协议。

## 首轮结论（历史，修复前）

**FAIL**。

- `functional_verdict`: **FAIL**
- 本报告覆盖 Task03 的 legacy `papers.json` → canonical 文档迁移、KB store/application 边界、论文导入路径及四份契约 schema。未访问真实 data/Qdrant，未修改业务代码、fixture 或测试协议。
- 执行模型：`gpt-5.6-luna xhigh`（本轮临时授权）。
- 执行时间：2026-09-09 17:21:03–17:26:40 +0800。

迁移的正常路径、schema 实例和多数拒绝路径通过，但发现一个会在元数据写入异常后留下已替换数据的 P0，以及多个会导致数据丢失或违反不可变原件/状态契约的 P0/P1。因此不能签字放行 Task03。

## 已通过的检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 四份 schema 自身可编译、正实例可验证、负实例被拒绝 | PASS | `knowledge-document.schema.json`、`inspection-manifest.schema.json`、`finalize-bundle.schema.json`、`index-generation.schema.json`；`Draft202012Validator.check_schema` 与正/负实例均完成 |
| 正常 migration 的 canonical 字段、source hash 状态、只读备份 | PASS | `backend/app/knowledge_base/infrastructure/migration.py:261-325`；备份 mode `0444`，缺源记录保留并标记 `SOURCE_MISSING` |
| 正常 migration 幂等 | PASS | 第二次返回 `already_migrated=True`，原 canonical 内容不改；另有 `tests/test_kb_metadata_migration.py` 覆盖 |
| migration 输入损坏/非 list/非 object/重复 ID/unsafe ID/unknown field/unsafe stored name | PASS | 均得到 `MIGRATION_INPUT_INVALID`，原 metadata bytes 保留，未创建伪备份 |
| naive timestamp 的 UTC 语义 | PASS | `UTC`、`Pacific/Kiritimati`、`America/Los_Angeles` 三个 TZ 矩阵均得到 `2026-01-01T00:00:00+00:00` |
| 同名不同内容导入隔离 | PASS | 原 `same.pdf` 保持旧 bytes，新内容落到 `same-2.pdf`；重复 identity 在下载前被识别 |
| migration 路径无 embedding/Qdrant 调用 | PASS | `migration.py` 无相关导入；临时探针调用计数为 0。应用导入测试使用显式 no-op indexer，未触碰真实服务 |
| FinalizeBundle/marker 正负 schema 实例 | PASS（schema 级） | 合法实例 0 errors；unsafe path、错误 alias 等负实例被拒绝。Task03 未宣称已实现 Task04/06 的 runtime finalize |

## 阻塞问题

### P0 — migration 的 post-replace fsync 失败会留下已替换 metadata

- 证据：`backend/app/knowledge_base/infrastructure/migration.py:231-245`，`os.replace(temp_path, path)` 在 `migration.py:240` 先执行，目录 fsync 在 `:241` 才执行；异常只清理临时文件，未恢复旧 metadata。
- 复现：临时目录中将第二次 `_fsync_directory` 注入 `OSError`（第一次备份 fsync 成功）；调用返回 `MIGRATION_WRITE_FAILED`，但输出为 `original_preserved=False`，canonical metadata 已经替换，备份仍存在。
- 影响：报告“写失败”与磁盘实际状态不一致；中断/崩溃后无法保证原文件和 backup 的无损关系，违反 Spec018 `:164` 及 Task03 迁移要求。
- 建议：采用可恢复的两阶段提交/备份交换协议；post-replace durability 失败时必须回滚到原 bytes（并 fsync），或把“替换成功但 durability 未确认”作为明确可恢复状态，禁止继续向应用暴露 canonical 成功状态。加入 fsync 注入测试，断言原 metadata、backup 和可恢复状态。

### P0 — 损坏 metadata 被当成空库，后续导入可覆盖原始数据

- 证据：`backend/app/knowledge_base/infrastructure/store.py:96-115`，`load_papers` 捕获 JSON/OSError 后直接返回 `[]`；`backend/app/knowledge_base/application.py:128-157` 的 `upsert_paper` 随后可保存新 list。
- 复现：将 `papers.json` 写成 `bad`，用 no-op indexer 运行 application import，结果为 `INDEXED`，metadata 被改写为数组；没有稳定的 `METADATA_INVALID`/`MIGRATION_INPUT_INVALID` 拒绝。
- 影响：损坏文件会被静默解释为空库，导入可能覆盖不可恢复的旧 metadata，违反“损坏输入 fail closed”。
- 建议：读取错误必须抛出稳定、脱敏错误码并阻断所有 upsert/import/delete；首次初始化只能通过显式 `allow_missing` seam；为 JSON 损坏、非 list、截断文件补充 write-spy/bytes 保留测试。

### P0/P1 — 显式 `paper_id` 的上传会覆盖不可变原件

- 证据：`backend/app/knowledge_base/infrastructure/store.py:214-226`，`save_upload` 直接对 `papers/{identifier}.pdf` 调用 `write_bytes`。
- 复现：同一临时 `paper_id='same'` 先写 `one`，再写 `two`，第二次返回成功且目标 bytes 为 `two`（输出：`SAVE_UPLOAD_SAME_ID True b'two'`）。
- 影响：违反 Spec018 同 ID 不覆盖、删除后须以新 document ID 重新提交；旧 source 被不可逆替换。Task03 application 报告将旧 upload 闭环留给后续 Task，但本验收把它列为当前不可变原件债务，必须在进入可用状态前明确关闭或显式阻塞。
- 建议：同 ID 目标存在时稳定拒绝；所有上传统一走 exclusive-create/immutable source service，不允许 `write_bytes` 覆盖；补 concurrent same-ID 和中断恢复测试。

### P1 — `find_existing` 可返回空 ID

- 证据：`backend/app/knowledge_base/application.py:212-223`，匹配 identity 后无非空 ID 校验，直接返回 `record_id(record)`。
- 复现：canonical-looking record 仅含 `title/year/conference_id/status`，没有 `paper_id`/`document_id`；`find_existing` 返回 `PortImportResult.paper_id == ''`。
- 影响：下游可能把空 ID 当作已存在对象，破坏去重、状态更新和路径解析，违背 Task03-D 的“canonical find_existing 非空 ID”。
- 建议：canonical record 必须要求非空 `document_id`；legacy record 必须要求安全非空 `paper_id`。不满足时稳定 fail closed 或跳过并记录脱敏错误，不得返回空结果。

### P1 — 删除先删 metadata，忽略原件 unlink 失败

- 证据：`backend/app/knowledge_base/infrastructure/store.py:196-211`，`:204` 先保存剩余 metadata，`:206-210` 的 `unlink` 异常被吞掉。
- 复现：注入目标 `unlink` 抛 `OSError`，`remove_paper` 仍返回 `True`，metadata 变为 `[]`，原件仍存在（输出：`REMOVE_UNLINK True source_exists True meta []`）。
- 影响：产生 metadata/source 不一致；后续同名路径、重试和审计无法判定真实状态。
- 建议：删除采用可恢复状态机或先做可验证的原件操作，再提交 metadata；unlink 失败必须返回稳定错误并保留记录/cleanup 状态，不能报告成功。

### P1 — canonical upsert 会重置既有 chunker 状态

- 证据：`backend/app/knowledge_base/infrastructure/store.py:128-157`，`:143-149` 将传入 `PaperRecord.to_dict()` 的 `chunkers` 整体写回 canonical record。
- 复现：迁移后的 canonical record 中 v1 为 `indexed`、v2 为 `pending`；用默认 legacy `PaperRecord` 做状态更新后观测到 `v1=indexing`、`v2=pending`。schema/document_id/source hash 仍保留，因此本项不是字段丢失而是状态回退/覆盖。
- 影响：状态更新可能抹掉另一版本的真实进度，影响重试、幂等和任务恢复。
- 建议：legacy update 只允许显式更新目标版本/状态；未提供的 chunker 保留原值，禁止用默认 `PaperRecord` 的全量 `chunkers` 覆盖 canonical 状态。

### 已知但未重复列为新增 P0 的债务

`backend/app/knowledge_base/infrastructure/store.py:229-261` 的 `copy_source_exclusive` 对目录 fsync `OSError` 仍按已知 Task06 security debt 吞掉。它不是本轮新发现，但与不可变原件 durability 有关；在生产切换前必须由 Task06 关闭或明确禁止 production cutover。

## 其他边界结果

- canonical upsert 的 `schema_version`、`document_id`、`source_sha256` 等身份/来源字段在本次探针中保留；`indexed_source_sha256` 的 null 状态也未被伪造改写。上述 chunker 状态覆盖仍使整体边界不通过。
- `resolve_paper_path` 对正常 basename 和明显 `../` 路径的临时检查通过；这不抵消删除失败及同 ID 覆盖问题。
- 真实 runtime FinalizeBundle 的写入顺序、marker last、generation marker 和 alias 切换属于后续任务；本轮只完成四份 schema 的正负验证，不能将 schema PASS 解释成 runtime PASS。
- 代码静态检查：`ruff check` 退出码 1，共 7 个已有问题（`application.py`/`paper_import.py` 的 SIM105，`tests/test_paper_import.py` 的 I001）；不改变上述 P0/P1 判定，但应在合并前清理或记录基线。

## 验证命令与结果

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_metadata_migration.py tests/test_kb_application_boundary.py tests/test_paper_import.py` | 0 | `26 passed in 0.57s` |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 0 | `366 passed, 5 warnings, 29 subtests passed in 22.28s`；期间有 OTEL 向 `127.0.0.1:3000` 的瞬时导出错误，但不影响 pytest 退出码 |
| 临时目录/Fake/no-op probes（schema、migration、TZ、fsync 注入、损坏 metadata、find_existing、unlink、same-ID upload、same-name import） | 0 | 通过项与阻塞复现见上文；未访问真实 data/Qdrant |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/migration.py backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_kb_metadata_migration.py tests/test_kb_application_boundary.py tests/test_paper_import.py` | 1 | 7 个 lint 问题 |

## 主 Agent 后续动作

1. 先修复 migration post-replace fsync 的 rollback/durability 协议和 corrupted metadata fail-closed；这两项关闭前不得将 Task03 标为通过。
2. 强制 `find_existing` 非空 canonical ID；修复删除的原件/metadata 一致性；保护既有 chunker 状态。
3. 在上传闭环（Task04 或明确的 Task03 交接）中禁止 same-ID overwrite，并补 concurrent/interruption 测试；保留不可变原件的安全债务标记。
4. 重跑本报告命令、临时故障注入和 KB+paper import 回归，再交由 backend-reviewer 复核。不要用现有 26/366 通过替代上述针对性证据。

## 交接

- 报告：`docs/sdd/plans/018/artifacts/task-03/backend-test-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-03/backend-tester/20260909-172103.md`
- 本轮未修改业务代码、fixture、真实 data、真实 Qdrant 或 Git 历史。

## 修复轮逐项复测证据

### 功能项：PASS

1. **canonical 新导入完整 schema**：`build_import_knowledge_document` + `write_import_knowledge_document` 产生的记录通过 `knowledge-document.schema.json`；另外通过真实 `KnowledgeBasePaperImportAdapter.import_paper` 生成记录，再对落盘 JSON 做完整 Draft 2020-12 校验，required 字段、`document_id`、`source_sha256`、`source_immutable` 均存在且合法。
2. **损坏 JSON fail closed**：`save_papers`、`upsert_paper` 和 application import 均使用严格读取；对 `b"{broken"` 返回 `METADATA_INVALID`，原 bytes 保持不变，trusted source 也未被移动/删除。
3. **canonical upsert 保真**：legacy `PaperRecord` 更新不再写回默认 status/chunkers；验证了 canonical 的顶层 status、v1/v2 chunker、schema/migration/document identity、source hash、`indexed_source_sha256` 和 `source_hash_state` 均保持不变；显式 `patch_knowledge_document` 也保持 chunker 与 identity。
4. **fsync-after-replace 恢复和重试**：注入第二次目录 fsync `OSError`，入口返回 `MIGRATION_WRITE_FAILED`；metadata 恢复为 original bytes，backup 仍为 original bytes。恢复真实 fsync 后迁移成功，随后第二次调用返回 `already_migrated=True` 且 bytes 不变。
5. **`find_existing` 非空 ID**：没有 `paper_id/document_id` 的 identity-match 记录被跳过；有效 canonical 记录返回非空 `document_id`。本项使用独立 malformed/canonical metadata 文件复测，避免把 legacy malformed 文件误当作可写 canonical store。
6. **UTC、缺 source、删除/路径、重复导入**：`UTC`、`Pacific/Kiritimati`、`America/Los_Angeles` 下 naive timestamp 均固定为 `+00:00`；缺 source 保留记录并为 `failed/SOURCE_MISSING/null hash`；正常删除同时移除 metadata/source，basename/path fallback 在 papers 目录内；重复 identity 返回既有非空 ID、第二个 trusted source 保留，indexer 只调用一次。
7. **schema 正负实例**：knowledge document、inspection manifest、finalize bundle、index-generation 四份 schema 均 `check_schema` 通过；每份合法实例接受、空 ID/错误 alias 等负实例拒绝。
8. **embedding/Qdrant = 0**：临时 import 使用 no-op indexer，并将应用层 `get_client`、`embed_texts`、`encode_sparse` 替换为 fail-fast spy；完整导入及重复导入均未触发这些路径，indexer 仅首次导入调用一次。

### Security debt：保留但不阻塞本轮功能门

- `backend/app/knowledge_base/infrastructure/store.py:245-257`：显式 `paper_id` 的旧 `save_upload` 仍以 `write_bytes` 覆盖同 ID 原件（探针结果 `target_same=True`, bytes 从 `one` 变为 `two`）。
- `backend/app/knowledge_base/infrastructure/store.py:227-242`：`remove_paper` 仍先保存 metadata，并吞掉原件 `unlink` 的 `OSError`；故障探针仍得到 `returned=True`, `source_exists=True`, `meta=[]`。
- `backend/app/knowledge_base/infrastructure/store.py:260-287`：`copy_source_exclusive` 的目录 fsync 异常仍按 Task06 约定记录为 production durability debt。

这些债务不影响本轮 `functional_verdict=PASS`，但应保持 `production_cutover_verdict=FAIL/DEFERRED`，直至安全任务完成并有故障注入证据。

## 修复轮命令与退出码

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_metadata_migration.py tests/test_kb_application_boundary.py tests/test_paper_import.py` | 0 | `30 passed in 0.85s` |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 0 | `370 passed, 5 warnings, 29 subtests passed in 22.59s`；OTEL exporter 对 `127.0.0.1:3000` 的连接失败为环境噪音，不影响 pytest 结果 |
| 修复轮 tempfile/Fake/no-op 定向探针（8 功能组） | 0（最终逐项复测） | 8/8 通过；包含 fsync 注入、损坏 JSON、schema、UTC、缺 source、重复导入、删除/path、零 embedding/Qdrant |
| malformed `find_existing` 与独立 canonical metadata focused probe | 0 | malformed identity 不返回空 ID；canonical identity 返回非空 ID |
| 实际 application import 后对落盘 JSON 做完整 knowledge-document schema 校验 | 0 | PASS |

首次合并探针曾因将 malformed legacy metadata 复用于 canonical writer 而产生 1 个 harness-level 失败；未归因于业务实现，随后使用独立 metadata 文件重跑该断言并退出码 0。该信息保留以避免把探针修正过程误报为业务回归。

## 修复轮交接

- 最新报告仍在：`docs/sdd/plans/018/artifacts/task-03/backend-test-report.md`
- 本轮日志：`.codebuddy/agent-logs/spec-018/task-03/backend-tester/20260909-173733.md`
- 功能结论：**PASS，可放行 Task03 功能门并进入下一阶段评审**。
- 安全/生产切换结论：**DEFERRED，不得把本轮 functional PASS 解读为 production cutover PASS**；保留上述 security debt 给 Task04/Task06。
