# Task03-C application/store identity boundary report

状态：`READY FOR REVIEW`（功能门）；Task04/Task06 的生产放行门仍按各自矩阵执行。

## 固定边界

- `backend.app.knowledge_base.application` 是知识库侧唯一的论文导入 composition
  入口，向论文发现只暴露 `PaperImportPort` 的稳定 DTO。
- `backend.app.paper_discovery.application.paper_import` 只解析候选、执行安全下载、
  调用 `PaperImportPort.find_existing/import_paper`；静态检查确认它不 import
  `knowledge_base.infrastructure`，不直接访问 store、index、Qdrant 或 embedding。
- metadata 迁移唯一入口为
  `backend.app.knowledge_base.infrastructure.migration.migrate_papers_json`，并由
  knowledge-base application re-export；它不进入索引/下载链路。

## 不可覆盖与补偿

`KnowledgeBasePaperImportAdapter` 对 server-owned basename 使用
`copy_source_exclusive`：目的文件以 `xb` 创建并 fsync，已存在目标不会被
`rename/replace/write_bytes` 覆盖，而是选择 `-2`, `-3` 等安全 basename。成功复制
后才移除受信任下载临时文件；索引失败通过注入的 deleter 和 owner 记录清理本次
资源。重复身份在下载前和导入锁内各检查一次，删除后再次提交由 `new_record()`
生成新 ID。`record_id()` 统一优先读取 canonical `document_id`，兼容旧
`paper_id`；`find_existing`、状态更新、路径解析和删除均复用该边界。对 canonical
记录调用 legacy `upsert_paper` 只合并非空论文描述字段；显式状态由 canonical patch
入口更新，不会删除 schema、hash、媒体类型或 `document_id`，因此不会降级回 legacy record。应用侧没有第二套下载或 Qdrant
写入实现。

新论文导入的顺序固定为：服务端生成 ID → exclusive source copy → 计算当前 source
hash → Draft 2020-12 校验并写入完整 canonical record → 执行注入的索引器。若 metadata
已经损坏，严格读取在 source 提交前失败，原 bytes 不变；若索引失败，只清理本次
owner 资源。canonical v1/v2 已有状态不会被 legacy 默认 `PaperRecord` 的 0 计数或
默认 chunker 覆盖。

## 机械验收

| 断言 | 证据 |
|---|---|
| 同名不同内容不覆盖 | `tests/test_kb_application_boundary.py::test_import_boundary_never_overwrites_existing_basename` |
| 新导入经唯一 port，临时源不泄漏 | `tests/test_kb_application_boundary.py::test_import_boundary_uses_create_exclusive_source_and_keeps_discovery_outside_kb` |
| 论文发现不越界 | `tests/test_kb_application_boundary.py::test_paper_discovery_orchestration_only_imports_the_port` |
| canonical 去重/状态/删除不降级 | `tests/test_kb_application_boundary.py::test_canonical_identity_dedup_status_and_delete_preserve_schema` |
| 损坏 metadata fail-closed、canonical/legacy 非空 ID | `tests/test_kb_application_boundary.py::test_corrupt_metadata_blocks_import_without_replacing_bytes`、`test_find_existing_legacy_record_returns_nonempty_paper_id` |
| 既有导入/失败补偿回归 | `tests/test_paper_import.py`（9 passed；与本报告边界测试合计 15 passed） |

## 生产门说明

本报告不宣称 Task04 的旧 upload route 已关闭，也不宣称 Task06 已连接或切换
真实 Qdrant。旧 route、`save_upload`/metadata legacy symbols、目录 fsync 错误和
candidate cutover 均保留给后续矩阵与 production-cutover 门；本 Task 的功能结论仅为
身份保持、源不可覆盖、论文发现适配和迁移不触碰向量。
