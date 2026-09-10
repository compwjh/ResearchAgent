# Spec018 Task03-D 后端独立评审

## 当前修复轮结论

**FUNCTIONAL GO（功能范围）。** 本轮复核确认上一轮两个 P0 已关闭：新论文导入会生成并
校验完整 canonical `KnowledgeDocument`，legacy `PaperRecord` 的默认计数/状态不会再
覆盖 canonical 状态；损坏 JSON 会阻止导入和写回，fsync 失败有回滚测试，`find_existing`
与 `record_id` 统一使用 canonical identity。

旧 upload route、非原子兼容写路径、目录 durability 和既有 `SIM105` 仍登记为后续
Task04/06 债务，不作为本轮功能 GO 的阻塞；本结论不等于 production cutover GO。

### 首轮结论（历史）

**NO-GO。** 首轮发现 Task03-C 的新导入路径仍会把新论文写成旧 `PaperRecord`，且
canonical 记录存在被旧默认字段回退的实际数据损失路径。本轮已逐项复核并关闭。

本轮仅读评审并运行临时目录测试；未修改业务代码、测试、schema、Task02 证据或真实
`data/kb`/Qdrant。

## 首轮 P0（已关闭）

### P0-1（已关闭）：新论文导入不是 canonical `KnowledgeDocument`

首轮代码证据（修复前）：

- `backend/app/knowledge_base/application.py:283-299` 的 `KnowledgeBasePaperImportAdapter`
  用 `new_record()` 创建 legacy `PaperRecord`，随后调用 legacy `upsert_paper()`。
- `backend/app/knowledge_base/infrastructure/store.py:128-155` 在没有同 ID 记录时直接
  `papers.append(payload)`；`PaperRecord.to_dict()` 只产生 `paper_id`、`uploaded_at` 等
  legacy 字段，不产生 `schema_version`、`document_id`、`source_sha256`、
  `source_hash_state` 或 `source_immutable`。
- 临时目录探针（注入 indexer、没有真实 Qdrant）输出：

  ```text
  keys=['authors', 'chunk_count', 'chunkers', 'conference_id', 'conference_name',
        'dblp_key', 'doi', 'error', 'file_name', 'import_source', 'page_count',
        'paper_id', 'source_url', 'status', 'stored_name', 'title', 'uploaded_at', 'year']
  schema_version=None
  document_id=None
  legacy_paper_id=<generated id>
  ```

这不是只读兼容问题：每个全新论文发现导入都会绕过 canonical schema，后续 migration
也不会自动包裹这个新记录。修复后已新增唯一的 canonical create-exclusive
application/store 写入口：生成新 `document_id`、计算当前原件 hash、写入
immutable/canonical 字段并按 schema 校验；legacy `upsert_paper` 不再作为新记录
fallback。

### P0-2（已关闭）：canonical 记录可被 legacy 默认值覆盖，造成元数据/状态回退

首轮 `store.py:139-150` 对 canonical 记录会把传入 `PaperRecord` 的 `page_count`、
`chunk_count`、`chunkers`、`status` 和 `error` 全量合并。临时目录探针先迁移一个
`page_count=10/chunk_count=5` 的 canonical 记录，再用默认计数为 0 的 legacy record
同 ID 更新，结果变为 `page_count=0/chunk_count=0`，v1 chunker 也从 indexed/5 回退为
indexing/0；`document_id` 和 source hash 虽仍在，但长期事实已丢失。

首轮要求 canonical 更新使用显式、按字段授权的 DTO/方法，只允许索引状态机真实产生的
更新；不能把 legacy record 的默认值当作 patch，也不能让 generic upsert 在 canonical
与 legacy 两种写模型之间自由降级。修复已满足该约束。

修复后 `store.py:175-181` 只合并论文 metadata，状态/计数由
`migration.py:314-328` 的 `patch_knowledge_document()` 显式更新；
`application.py:306-307` 先写 canonical document，新增导入不再走 legacy append。

## 后续债务（不阻塞本轮功能 GO）

### D1：旧 `/api/kb/upload` 仍绕过论文导入 port

`backend/app/api/routes_kb.py:107-131` 直接组合 `new_record`、`save_upload`、
`upsert_paper` 与 `index_paper_chunker`。这与 `CONTEXT.md` 的“application 是唯一受控
入口”不一致。现有 Task03 报告明确把它延期到 Task04，因此这里记录为 Task04 的交接
债务；在旧 route 关闭前不能宣称 production application/store 边界全部收口。

### D2：论文发现适配器仍调用 legacy Qdrant index/payload

`application.py:238-249` 的默认 indexer 调用 `index_paper_chunker`；
`infrastructure/index.py:124-148` 的 payload 仍以 `paper_id` 为身份，删除过滤也在
`index.py:156-180` 使用 `paper_id`。这不是“迁移旧 vectors”（migration.py 确实不读
Qdrant、不 embedding），但新导入的索引链仍不是 Task02A candidate port 的
`document_id`/provenance 协议。需要在 Task04/06 的索引切换矩阵中明确关闭或通过唯一
受控 port 适配，不能把当前 legacy index 当作最终 Spec018 生产路径；这是后续
Task04/06 生产债务，不影响本轮 metadata canonical 与 identity boundary 功能结论。

### D3：目录 fsync 与兼容写路径仍有生产 durability 债务

修复前曾存在 `os.replace()` 后目录 fsync 失败仍留下新 metadata 的问题。当前
`migration.py:359-387` 在 replace 后 fsync 失败时尝试恢复旧 bytes，并由
`tests/test_kb_metadata_migration.py::test_post_replace_directory_fsync_failure_rolls_back_and_retry_is_deterministic`
覆盖，功能探针对第二次目录 fsync 注入 `OSError` 后确认回滚：

```text
error=MIGRATION_WRITE_FAILED
metadata_is_original=True
metadata_schema=None
backup_matches_original=True
```

当前 tempfile 功能语义已验证为保留原 metadata、保留 backup、可重试；但
`_restore_bytes()` 的最终 fallback 仍是 best-effort，且 `store.save_papers()` 仍是
兼容路径的直接 `write_text`，因此继续登记为 Task06 production durability 债务。

另外，`store.py:246-255` 的 `copy_source_exclusive()` 吞掉目录 fsync `OSError`，导入
报告也将其列为 Task06 安全债务；在 production cutover 前必须明确是否允许成功返回。

### D4：迁移入口没有进程级读-变换-备份-替换互斥

`migration.py:273-316` 没有与其它 migration 调用共享锁。两个进程可同时读同一 legacy
输入、竞争创建 backup 并分别替换 metadata；backup conflict 只能覆盖部分竞态，不能
保证结果是单一输入快照。至少应使用受控 runtime lock，或把并发冲突统一转为稳定的
fail-closed 错误并补 tempfile 并发测试；该项不阻塞当前单进程功能验收。

## 已确认通过的部分

- `migration.py` 只读 legacy JSON/受控原件目录，不读取旧 Qdrant points、不调用
  embedding；`source_hash_state=legacy_unknown` 与 `indexed_source_sha256=null` 的
  迁移语义与当前 schema 一致。缺原件记录保留为 `SOURCE_MISSING`，没有误删。
- ID、basename、重复记录、损坏 JSON、无时区时间（固定解释为 UTC）、备份和中断
  replace 均有临时目录测试；Markdown 保留 markdown media/path 语义。
- `paper_discovery/application/paper_import.py` 只依赖 `PaperImportPort`，没有直接
  import knowledge-base infrastructure；这一条边界测试通过。
- `candidate_rebuild.py:528-549` 能把 canonical/legacy 读取统一成 `document_id`，
  candidate payload 使用 `document_id`；与修复后的 application/store identity 规则一致。
- `application.py:216-231` 的 `find_existing()` 读取严格 metadata 并统一使用
  `record_id()`；canonical 同时存在 `document_id`/legacy 字段时优先 canonical，legacy
  记录则回退 `paper_id`。损坏 JSON 的导入保护由
  `tests/test_kb_application_boundary.py::test_corrupt_metadata_blocks_import_without_replacing_bytes`
  覆盖。
- `application.py:290-312` 通过 `build_import_knowledge_document()` 与
  `write_import_knowledge_document()` 创建新 canonical record；新导入记录经
  `Draft202012Validator` 校验，临时探针确认 `document_id == result.paper_id`、无
  `paper_id`、source hash/immutable 字段齐全。
- 四份 Task03 schema 均通过 `Draft202012Validator.check_schema`；FinalizeBundle 的
  staged/live 路径、逐文件 hash 与 generation marker 最后写入顺序已在 schema/CONTEXT/
  ADR 中冻结。Task03-B/C 本轮没有 FinalizeBundle runtime finalizer；该实现应由后续
  Task04/Task06 交接，不应把 schema 冻结误报为生产 finalize 已完成。

## 验证命令与退出码

| 验证 | 命令 | 结果 |
|---|---|---|
| Task03 修复轮定向回归 | `.venv/bin/python -m pytest -q tests/test_kb_metadata_migration.py tests/test_kb_application_boundary.py tests/test_paper_import.py` | `30 passed`，exit `0` |
| KB/paper-import 全量回归 | `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | `370 passed, 29 subtests`，exit `0`；有 5 个已知 DeprecationWarning 及 telemetry 连接重试日志 |
| Python 编译 | `.venv/bin/python -m py_compile ...`（本报告涉及 migration/store/index/application 与新增测试） | exit `0` |
| 四份 schema | `Draft202012Validator.check_schema` 扫描 `docs/sdd/plans/018/artifacts/task-03/*.schema.json` | 4/4 OK，exit `0` |
| ruff | `.venv/bin/ruff check`（上述后端实现与新增测试） | 6 个既有 `SIM105`，exit `1`；登记为后续债务 |
| diff 空白检查 | `git diff --check`（Task03 改动范围） | exit `0` |

## 主 Agent 后续动作

1. 将本轮 `FUNCTIONAL GO` 交给主 Agent，进入 Task04；保留新导入 canonical schema、
   canonical 状态保护、损坏 JSON 和 fsync 回滚证据。
2. 按 Task04 交接矩阵关闭旧 `/api/kb/upload` 直写路径，决定 legacy index 是明确只读
   兼容还是经受控 port 迁移到最终 `document_id` 协议。
3. Task06 再收口 `_restore_bytes()` fallback、`save_papers()` 原子写、目录 fsync 与
   migration 进程级互斥；6 个 `SIM105` 可一并清理。
4. FinalizeBundle/marker-last 的 runtime 实现仍交由 Task04/Task06；在此之前保持
   `INDEX_FINALIZE_REQUIRED` 生产门，不连接真实 Qdrant、不迁移旧 vectors。
