# Task 03：定义通用文档、Manifest 与元数据迁移协议

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task02B `GO`；被依赖：Task04；当前状态：`已完成（功能门 GO；安全债务转 Task04/06）`

## 一句话目标

冻结 `KnowledgeDocument`、`SourceBlock`、`ChunkSnapshot`、`SourceAnchor` 和 `InspectionManifest`，并无损迁移现有 PDF 元数据与身份，不迁移旧向量。

## 当前证据

- 现有长期事实是 `papers.json`、PDF 原件、论文元数据和历史 `paper_id`。
- 旧 Qdrant vectors 与旧 manifest 已被重新定义为可丢弃派生数据。
- Task02A 提供 `SourceProvenanceBundle`，但按依赖边界不定义最终 manifest。

## 前置门禁

- Task02B 报告结论严格为 `GO`。
- Task02A 固定 bundle schema、实现契约和报告存在且 hash 可核对。

## 思维链（可审计执行设计）

1. 先冻结领域 DTO/schema，再迁移 JSON 元数据。
2. `document_id` 保留历史 `paper_id`；原件、时间和论文元数据不丢失。
3. 元数据迁移与 Qdrant 重建解耦：本 Task 不改旧 points、不 embedding、不切换 Collection。
4. 旧索引对应 hash 标记为未知；只有 Task06 新候选构建并验证成功后才写 `indexed_source_sha256=source_sha256`。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 内容 | 固定产物 |
|---|---|---|---|
| 03-A | Tech Lead | DTO/schema、`FinalizeBundleV1` 与 generation marker 冻结、CONTEXT、ADR | `knowledge-document.schema.json`、`inspection-manifest.schema.json`、`finalize-bundle.schema.json`、`index-generation.schema.json` |
| 03-B | backend-dev | `papers.json` 到文档元数据的 fail-closed、幂等迁移 | `migration-fixture-index.json`、`migration-report.md` |
| 03-C | backend-dev | application/store 身份边界与论文发现导入适配；旧索引只读识别 | `application-boundary-report.md` |
| 03-D | backend-tester + backend-reviewer + Tech Lead | 迁移回归、评审和交接 | `backend-review-report.md` |

## 固定 Prompt

```text
你是 Spec018 Task03 的 backend-dev。只读取 Spec018、Task02A/02B 交接物、当前 knowledge_base store/application 与 paper_discovery 导入入口、CONTEXT.md 和目标 ADR。允许修改分派清单点名的 backend 文件、对应后端测试、CONTEXT.md、ADR 与本 Task 固定产物；禁止修改 frontend、用户 data/kb、真实 Qdrant、旧 vectors、Task02 历史证据和 Git 历史。

保留所有既有 paper_id 作为 document_id，保留安全 stored basename、时间和论文元数据。元数据迁移必须 versioned、备份、fsync+os.replace、损坏输入 fail-closed 且重复运行无副作用。旧索引只记录 legacy_unknown，不做 payload-only migration，不要求 point/vector/fingerprint 不变，也不调用 embedding。原件缺失必须保留诊断并让后续全库 preflight 失败，不得删除记录。Task02A SourceProvenanceBundle 是唯一来源定位输入；本 Task 冻结唯一 InspectionManifest schema，以及包含 staged/live 相对路径、逐文件 hash、候选 fingerprint、bundle hash 的 FinalizeBundleV1 和最后写入的 index-generation commit marker。marker 写入前正常读取必须保持 INDEX_FINALIZE_REQUIRED。

原件是不可变对象：不提供同 ID 覆盖；删除后重新提交生成新 document_id，既有哈希去重语义保持不变。不得新建第二套索引、下载或导入实现。完成后运行定向 pytest，并返回固定结果字段、产物路径和主 Agent 后续动作。
```

## 子 Agent 必须返回

- 结果状态、摘要、改动文件。
- 迁移前后记录数、ID 集合、原件/论文元数据保持结果。
- 测试命令、退出码、数量、耗时。
- schema/fixture/report/CONTEXT/ADR 路径。
- 决策、风险阻塞和主 Agent 后续动作。

## 主 Agent 校验

- 迁移前后 `document_id == paper_id`，记录数、原件和论文元数据无损。
- Qdrant write、embedding 和旧 vector 读取迁移均为 0。
- 损坏 JSON 不被当成空库覆盖；重复迁移无新增或丢失。
- schema 不包含旧 snapshot/upgrade 状态。
- finalize bundle 覆盖全部 metadata/manifest，路径受控、hash 可复算；commit marker 永远最后写入。

## 实时监控

在线 Agent 正常运行时等待主动返回；仅在明确超时、错误、长期无返回或用户要求时读取日志。

## 测试与验收标准

- 缺原件、重复 ID、非法记录、无时区时间和中断写入均有稳定结果。
- Markdown 不被强制写入 `.pdf` 路径。
- 论文发现仍通过同一 KnowledgeDocument application 导入。
- 同 ID 原件覆盖接口不存在；删除再提交产生新 ID。

## 风险、停止条件与回滚

- 任一 ID、原件或论文元数据丢失立即停止。
- 迁移异常保留原文件和备份，不使用 reset/stash/clean。

## 产出物

- 领域协议、manifest/finalize/generation schema、元数据迁移、CONTEXT、ADR、测试与评审证据。

## 执行结果

- 03-A：`KnowledgeDocument`、`InspectionManifest`、`FinalizeBundleV1`、generation marker 四份 Draft 2020-12 schema，以及 `CONTEXT.md` 和 ADR 0001 已冻结；正负代表性实例通过。
- 03-B/03-C：完成 versioned、备份、原子替换、幂等、fail-closed 元数据迁移和 canonical application/store identity 边界；论文导入直接生成完整 `knowledge-document-v1`，无时区旧时间固定按 UTC 归一。
- `functional_verdict=PASS/GO`：定向测试 **30 passed**、KB+paper import **370 passed**、独立 tempfile 功能探针 **8/8**；四份 schema、py_compile 与 diff 检查通过，embedding/Qdrant 调用为 0。
- `debt_verdict=SECURITY_DEBT`：旧 `save_upload` 同 ID 覆盖和旧 route 交 Task04；unlink 失败一致性、生产目录 fsync durability 与生产切换门交 Task04/06，不阻塞本 Task 功能收口。
- 固定报告：`artifacts/task-03/migration-report.md`、`application-boundary-report.md`、`backend-test-report.md`、`backend-review-report.md`。

## 变更日志

- 2026-09-08：创建 Task，原计划兼容迁移旧 Qdrant payload。
- 2026-09-09：改为只迁移长期元数据与身份；旧向量不迁移，真实重建交由 Task06。
- 2026-09-09：完成协议、迁移与 application 边界；修复 canonical 状态回退、损坏 JSON 覆盖、无时区历史时间、fsync 失败回滚和空 ID，独立 tester/reviewer 签功能 GO。
