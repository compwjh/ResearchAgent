# Task 03：定义通用文档协议与迁移

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task02B Go；被依赖：Task 04；当前状态：`待执行`

## 一句话目标

建立 KnowledgeDocument、SourceBlock、ChunkSnapshot、SourceAnchor 与 InspectionManifest 的稳定协议，并无损迁移现有 PDF 元数据和 ID。

## 当前证据

- 元数据当前位于 `data/kb/papers.json`，原件默认位于 `data/kb/papers/`。
- 论文发现导入会写入同一知识库并携带可选论文元数据。
- 身份/元数据迁移本身不能重新生成 ID 或修改向量；旧索引 provenance 升级由 Task02A 的唯一恢复式重建流程负责。

## 前置门禁

- Task02B 结论为 Go。
- 记录迁移前元数据摘要、原件清单和 Qdrant point 数量；不得提交用户数据。

## 执行阶段与决策依据

1. 创建/更新根 `CONTEXT.md`，只记录项目领域词，不写通用技术术语。
2. 创建 ADR，说明原件、检查清单和向量索引分离的原因与后果。
3. 只读消费 Task02A 的 `SourceProvenanceBundle` schema，定义唯一 manifest schema version 1；不得反向修改已通过的 parser/chunker 语义。
4. 实现幂等迁移：保留现有 ID、时间、论文元数据、路径解析和 chunker 状态。
5. 更新论文发现导入与知识库 application 的边界契约，不允许跨域直写基础设施。

## 子 Agent 分派

- 代码角色：backend-dev；评审：backend-reviewer。
- 最小上下文：Spec/Task、现有 store/application、论文导入 application、Task02 历史证据及 Task02A/02B 交接物。
- 允许修改：`backend/**`、对应后端测试、`CONTEXT.md`、单个 ADR、本 Task 结果。

## 可交接子任务与固定产物（P0-7）

Task 03 按协议先行、迁移后行、边界最后评审的顺序执行。每个 `backend-dev`/`backend-reviewer` 本地 27B 子任务只接收 dispatch manifest 中列出的最多 2 个代码文件，目标改动约 150 行；超出即暂停、冻结当前 schema 并拆分，不得跨子任务顺手修改未列文件。

| 子任务 | 执行者/上下文 | 允许范围 | 固定输出/交接条件 |
|---|---|---|---|
| 03-A DTO/schema freeze | Tech Lead（自身）/ 128k；可由 `backend-dev` 27B 仅补 schema/测试文件 | 以 Task02A `SourceProvenanceBundle` 为输入定义 KnowledgeDocument、唯一 manifest schema、版本和迁移 fixture；禁止修改 02A schema | `docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`；`docs/sdd/fixtures/spec-018/migration/` 的 fixture-index |
| 03-B JSON migration | `backend-dev` / `qwen3.8:27b-mlx` / 32k | 最多 2 个已点名 backend 文件 + 对应测试；versioned backup、fsync/replace、fail-closed、idempotency | `docs/sdd/plans/018/artifacts/task-03/migration-report.md`，含记录/ID/stored basename/时间/元数据/hash/备份路径前后对照 |
| 03-C Qdrant payload/application boundary | `backend-dev` / `qwen3.8:27b-mlx` / 32k | 最多 2 个已点名 backend 文件 + 对应测试；双读、payload-only、point/vector/fingerprint 不变 | `docs/sdd/plans/018/artifacts/task-03/qdrant-migration-report.md` 与兼容读取 fixture；review 前冻结 application 入口 |
| 03-D review and handoff | `backend-reviewer` / `qwen3.8:27b-mlx` / 32k；Tech Lead 签字 | 只评 03-A～03-C 固定产物和 diff，不补实现 | `docs/sdd/plans/018/artifacts/task-03/backend-review-report.md`；通过后才可进入 Task 04 |

任何迁移输入损坏、缺 ID、重复/缺号、hash 不可证明或 point/vector/数量/fingerprint 改变，立即停止该子任务并写稳定诊断；不得猜测、覆盖或标记 `ready`。下游只读取上述 schema、fixture-index 和报告，不依赖聊天摘要。

### 固定 Prompt

```text
你是 Spec018 的 backend-dev。基于 Task02B 的 Go 结论定义通用知识文档与检查清单协议，保留所有既有 paper_id 值作为 document_id。身份/元数据迁移不得重新 embedding、删除原件或伪造元数据；旧索引升级只能复用 Task02A 的唯一恢复式流程。先复用现有知识库 store/application 和论文发现导入入口，不得新建第二套索引或下载实现。只修改 backend、对应后端测试、CONTEXT.md、指定 ADR 和本 Task 结果。必须验证旧 JSON、旧 stored_name、论文导入元数据、重复迁移、迁移中断与回滚。返回固定字段：状态摘要、改动文件、测试命令/退出码/结果、产物、决策依据、风险阻塞、主 Agent 动作、开始结束耗时、可用的模型/token/工具统计。
```

## 主 Agent 校验

- 对比迁移前后 ID、记录数、路径和 Qdrant point 数量。
- 搜索是否出现第二套 embedding/Qdrant/download 实现。
- 读回 CONTEXT/ADR，确认术语与 Spec 一致。

## 测试与验收

- 旧数据幂等迁移，重复执行无新增、无丢失。
- Markdown 新记录不再被强迫使用 `.pdf` 路径。
- 论文发现导入仍能关联同一知识文档。

## 风险、停止与回滚

- 任何 ID、原件或向量数量异常立即停止；保留迁移前文件，禁止覆盖式回滚。

## 产出物

- 领域协议、迁移实现与测试、CONTEXT、ADR、迁移证据。

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-08：架构师创建 Task。
- 2026-09-08：根据 P0-7 拆为 03-A DTO/schema、03-B JSON migration、03-C Qdrant/application、03-D review；冻结 schema、fixture、迁移报告路径及本地 27B ≤2 文件/约 150 行约束。
- 2026-09-08：P0-7 最终小修订确认 03-A～03-D 必须串行只读交接，Tech Lead 交接复核最低 64k、最终 Gate 128k；缺少固定 artifacts 或报告不得进入 Task 04。
