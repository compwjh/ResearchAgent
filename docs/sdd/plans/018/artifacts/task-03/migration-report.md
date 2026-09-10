# Task03-B metadata migration report

状态：`READY FOR REVIEW`（功能路径）

## 范围与结果

`backend.app.knowledge_base.infrastructure.migration.migrate_papers_json` 是
唯一的 `papers.json` → `KnowledgeDocument` 迁移入口。它只读取 legacy JSON 和
受控 `papers_dir`，不读取旧 Qdrant points、不写 Collection、不调用 embedding。
`paper_id` 原值成为 `document_id`；安全 `stored_name` 保留，未提供时按原媒体后缀
生成服务端 basename。论文标题、作者、年份、会议、DOI、DBLP、来源 URL 均保留。历史
store 曾写入无时区 `uploaded_at`；迁移按固定 UTC 解释并写入 `created_at` 的
`+00:00`，不读取主机当前时区，因此结果确定且幂等。已有带时区字符串保持原值。

当前原件存在时计算其字节 SHA-256，但迁移后的索引关系仍为
`source_hash_state=legacy_unknown` 与 `indexed_source_sha256=null`。原件缺失的
记录不被删除：保留 `document_id`，写入 `status=failed`、`error=SOURCE_MISSING`
和 `source_sha256=null`，交给后续全库 preflight fail-closed。该 null 是“当前字节
不存在”的明确状态，不是旧索引 hash 的替代值。

论文发现新导入现在先由同一 application/store 边界创建完整
`knowledge-document-v1` 记录（包括 `document_id`、schema/migration、媒体类型、
当前 source hash、immutable、created_at 和双版本 chunker 状态），再进入索引；后续
legacy `upsert_paper` 仅作为兼容故障注入/状态桥接，canonical 记录不会降级。
实际 canonical 状态只由显式 `patch_knowledge_document` 更新；legacy upsert 仅保留
非空论文描述字段，绝不写回 status/error/page/chunk/chunker 默认值。

## 原子性与失败语义

- 默认拒绝缺失输入；只有显式 `allow_missing=True` 的首次初始化才写入空集合。
- JSON 解码失败、根类型非 list、记录非 object、重复/不安全 ID、格式错误时间、
  未知字段和不安全 basename 均返回稳定 `MIGRATION_INPUT_INVALID`，不会把空列表写回。
- 首次写入前在同目录创建只读备份
  `papers.json.pre-018-document-v1.bak`；备份冲突返回
  `MIGRATION_BACKUP_CONFLICT`。输出通过同目录临时文件 → flush/fsync → `os.replace`
  → 目录 fsync。写入异常返回 `MIGRATION_WRITE_FAILED`，原文件与备份保留。
- 已迁移记录先通过 Draft 2020-12 schema 校验，重复调用只返回
  `already_migrated=true`，不重写 metadata。
- 所有 metadata 写路径使用严格读取：损坏 JSON、非 list 或非法记录返回
  `METADATA_INVALID`/`METADATA_NOT_MIGRATED`，不会把受控读取 API 的空列表当成可写空库。
- 如果 `os.replace` 已完成但目录 fsync 失败，保存逻辑用原始 bytes 做恢复替换并返回
  `MIGRATION_WRITE_FAILED`；备份保留，移除故障注入后可再次运行并得到同一 canonical 结果。

## 验证证据

| 项目 | 命令 | 结果 |
|---|---|---|
| 迁移与 schema | `.venv/bin/python -m pytest -q tests/test_kb_metadata_migration.py` | 15 passed, exit 0 |
| application/store 边界 + 论文导入回归 | `.venv/bin/python -m pytest -q tests/test_kb_application_boundary.py tests/test_paper_import.py` | 15 passed, exit 0 |
| KB + paper-import 全量回归 | `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 370 passed, 29 subtests, exit 0 |
| 全部 Task03 fixture 目录 | `docs/sdd/plans/018/artifacts/task-03/migration-fixture-index.json` | 临时 fixture；Qdrant/embedding 0 |

## 明确遗留风险

现有旧 `/api/kb/upload` 与旧 `save_upload/upsert_paper` 仍由 Task04 的 upload-closure
矩阵逐项关闭；本 Task 不触碰其真实用户数据。导入适配器已经使用
`copy_source_exclusive`（`xb` + 文件 fsync，目标已存在即拒绝/换安全 basename），
但 Task06 仍需复核目录 fsync 错误的 cutover 处置。该安全债务不改变本轮“不可覆盖、
可补偿、元数据不丢失”的功能结论。
