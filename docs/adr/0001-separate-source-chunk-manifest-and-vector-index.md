# ADR 0001：分离原件、检查清单与向量索引

- 状态：已接受（Spec018 Task03-A，2026-09-09）
- 范围：知识文档身份、来源定位、manifest 持久化与全库候选索引切换

## 背景

历史系统把 `paper_id`、PDF 原件、`papers.json` 与 Qdrant payload 作为一条上传/索引链路。
旧 points 没有可靠的 PDF bbox、Markdown 行范围或同源 parser provenance；旧索引也不能
证明其 source hash。Inspection UI 若从旧 points 猜测来源，会把派生数据误当作事实，并在
升级或失败恢复时产生不可审计的部分状态。

## 决策

1. `KnowledgeDocument` 保存原件和长期元数据，身份字段 `document_id` 等于历史
   `paper_id` 原值；原件一旦提交即 `source_immutable=true`，禁止同 ID 覆盖。
2. `SourceProvenanceBundle` 是 Task02A 的唯一来源交接物；Task03 定义唯一
   `InspectionManifest`，并将其作为可删除、可重建的派生 artifact。manifest 不保存旧向量
   快照，也不能由 Qdrant payload 旁路生成。
3. Qdrant 只承担检索索引。旧 collection/vector/payload 可丢弃；Task06 从原件、metadata、
   正式 parser/chunker/embedding 构建候选，验证 v1/v2、dense/sparse、payload、anchors
   和 fingerprint 后再切换 alias。
4. 当前 source hash 与索引构建时 hash 分离：旧数据固定为
   `source_hash_state=legacy_unknown`、`indexed_source_sha256=null`；仅新候选完成前后
   双 hash 检查并 finalize 后才转为 `verified`。
5. manifest 物理布局固定为
   `data/kb/manifests/<document-id>/<chunker>.json`；run-level finalize bundle 固定
   staged/live 相对路径和逐文件 SHA-256；最后写入 `data/kb/index-generation.json`。
   marker 是正常读取的最后 commit gate，任何缺失、损坏或不匹配都 fail-closed 为
   `INDEX_FINALIZE_REQUIRED`。

## Frozen contracts

- `knowledge-document.schema.json`：`knowledge-document-v1`，根及嵌套对象封闭；状态、
  source hash state、immutable source、v1/v2 chunker state 和论文元数据字段固定。
- `inspection-manifest.schema.json`：`inspection-manifest-v1`，固定 source blocks、真实
  chunk snapshots、multi-anchor 关系、mapping/parser/chunker/payload fingerprint、分页
  所需计数与 partial/unmapped 诊断；Markdown page fields 固定 null。
- `finalize-bundle.schema.json`：`finalize-bundle-v1`，固定候选 fingerprint、staged/live
  相对路径、逐文件 hash、obsolete manifest 清单和 canonical bundle hash。
- `index-generation.schema.json`：`index-generation-v1`，固定 run/alias/bundle/collection/
  metadata/manifests digest 与带时区 commit 时间。

四份 schema 使用 Draft 2020-12、`additionalProperties:false`；JSON Schema 的扩展注解
（如字节容量和写入顺序）不能替代运行时容量、fsync、原子替换和 hash 校验。

## 提交与恢复规则

Finalize 严格按 staged → schema/hash → fsync → bundle → live atomic replace → live hash
复核 → obsolete cleanup → generation marker 的顺序执行。alias 切换后但 marker 未提交
时进入 `finalize_pending`，正常 API 保持关闭；`resume-finalize` 必须使用同一 run、同一
bundle 和新鲜 topology，拒绝从旧状态猜测或复活 snapshot。

## 取舍与后果

- 保留旧 `paper_id` 避免引用断裂，但 canonical 名称统一为 `document_id`；兼容转换只能
  在 application 边界完成，不能保留第二套长期业务实现。
- 不迁移旧 vectors 减少伪 provenance 和逐 point 恢复复杂度，但首次真实切换需要完整重建
  和维护窗口；这项成本由 Task06 明确承担。
- manifest 可重建且有 256 MiB/数量上限，检查接口必须分页；原件和 metadata 是长期事实，
  tombstone/claim 负责删除与崩溃恢复的可审计性。
