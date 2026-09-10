# ResearchAgent 领域上下文：Spec018

本文件是 Spec018 的术语、身份和持久化边界事实源。JSON DTO 的机器契约分别位于
`docs/sdd/plans/018/artifacts/task-03/`；所有对象均使用 Draft 2020-12、根对象及
嵌套对象 `additionalProperties: false`。实现不得用旧论文命名或旧 Qdrant payload
推断新协议。

## 领域对象与身份

- `KnowledgeDocument` 是不可变原件及其长期元数据。`document_id` 永远保留历史
  `paper_id` 原值；迁移版本为 `018-document-v1`，不得重新生成 ID。`file_name` 只用于
  展示，`stored_name` 是服务端控制的 basename，不能成为调用方路径。
- `SourceProvenanceBundle` 是 Task02A 的纯 parser/chunker 交接物，不是 manifest；它
  只被 Task03 的 manifest builder 消费。Task02A 不定义、不持久化 `InspectionManifest`。
- `InspectionManifest` 是按文档与 chunker 生成的可删除派生清单，包含 source blocks、
  实际 chunk snapshots、anchors、版本 fingerprint 和映射状态；它不是向量快照。
- Qdrant collection/alias 是检索派生数据。旧 points、旧 payload、旧 vectors 不迁移、
  不恢复、不得用来补造 provenance。全库候选验证成功后才允许由 Task06 切换。

## 版本与固定产物

| 对象 | schema version | 固定产物/用途 |
|---|---|---|
| KnowledgeDocument | `knowledge-document-v1` | `data/kb/papers.json` 中的 canonical metadata record |
| InspectionManifest | `inspection-manifest-v1` | `data/kb/manifests/<document-id>/<chunker>.json` |
| FinalizeBundleV1 | `finalize-bundle-v1` | `.sdd/runtime/spec-018/rebuild/<run-id>/finalize/bundle.json` |
| generation marker | `index-generation-v1` | `data/kb/index-generation.json`，最后提交的 commit marker |

`chunker` 仅允许 `v1`/`v2`；`mapping_algorithm_version` 固定初始值
`source-anchor-v1`；payload 版本固定为 `qdrant-payload-v1`。schema 中的 hash 均为
小写 SHA-256 十六进制字符串。所有相对路径由 schema 固定在受控根目录，禁止绝对路径、
`..`、路径分隔符逃逸和调用方自定义 live 位置。

## Hash、旧数据与 source 生命周期

- `source_sha256` 只表示当前原件字节；`indexed_source_sha256` 只有同一新候选在
  hash-before/hash-after 双检并完成 finalize 后才可写入。
- 旧记录无法证明历史 embedding 的来源时必须是
  `source_hash_state=legacy_unknown` 且 `indexed_source_sha256=null`；不得把迁移时
  第一次计算的当前 hash 冒充旧索引 hash。hash 不一致使用 `mismatch`，fail-closed。
- `source_immutable=true` 是 canonical metadata 的硬字段。上传采用 create-exclusive，
  不提供同 ID 覆盖、PUT/PATCH 或原位修改；删除完成后重新提交产生新 ID。原件、metadata
  和论文元数据是长期事实，manifest 与 Qdrant 是可删除重建的派生数据。
- manifest claim 位于 manifest 同目录，删除使用 tombstone；任何 partial delete 或
  Qdrant 不可用都不能以成功 200 掩盖，恢复必须继续使用同一 owner/run 证据。

## Manifest 与 finalize 顺序

`InspectionManifest` 的 physical layout 固定为
`data/kb/manifests/<validated-document-id>/<chunker>.json`。单文档上限为
200,000 blocks、100,000 chunks、400,000 anchors、256 MiB JSON；Markdown chunk 的
`page/page_end` 永远是 null，PDF 使用 1-based page 和 0..1 bbox。

`FinalizeBundleV1` 只登记候选 collection fingerprint、metadata staged file、每个
manifest 的 staged/live 相对路径与 hash，以及要清理的旧派生 manifests。canonical
bundle hash 是去掉 `bundle_sha256` 后按键排序、无空白、UTF-8 JSON 的 SHA-256。

不可改变的提交顺序为：

1. 在 `.sdd/runtime/spec-018/rebuild/<run-id>/finalize/` 生成所有 staged metadata/manifest；
2. Draft 2020-12 校验、逐文件 hash 校验；
3. 文件及目录 `fsync`；
4. 写入并重新读取验证 FinalizeBundle；
5. 以同目录临时文件 + `fsync` + `os.replace` 原子替换 live metadata/manifest；
6. 重新计算全部 live hash；
7. 只清理 bundle 明列且未被当前 alias 引用的 obsolete manifests；
8. 最后原子写入 `data/kb/index-generation.json`，目录 `fsync`，再读回校验 marker。

正常 API/health 只有 alias、live metadata、live manifests、FinalizeBundle 和最后
generation marker 相互匹配时开放；marker 缺失、损坏或任一 hash/fingerprint 不匹配
统一返回 `INDEX_FINALIZE_REQUIRED`。`resume-finalize` 只能消费同一 run 的已验证 bundle，
不得从旧 manifest 或 state 猜测完成态。

## 责任边界

- application 是知识库对外唯一受控入口；routes 与 paper discovery 只能依赖 application，
  不得直接调用 store/index/tasks/parse 等 infrastructure。
- Task03-A 只冻结 schema、CONTEXT 和 ADR；Task03-B 负责 metadata fail-closed/idempotent
  migration；Task03-C 负责 application/import boundary；Task04 才实现 manifest store/API；
  Task06 才能在停服维护窗口执行真实 Qdrant 全库替换。
- Task02B 的功能 GO 允许进入 Task03–05，但不授予真实 Qdrant、`--confirm-replace`、
  alias 切换或旧 collection 删除权限；这些仍受 Task06 production gate 约束。
