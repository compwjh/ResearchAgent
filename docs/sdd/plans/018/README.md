# Spec 018 执行计划：知识文档切片检查器

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md)
> 当前状态：`实施中`。2026-09-09 全库索引替换修订已完成 Grill with Docs 共同理解确认，独立需求评审与技术设计门均通过，用户明确要求开始执行；当前仅放行 Task02A-D，Task02B `GO` 前不得进入 Task03–07。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02（历史）](./task-02-validate-source-anchor-feasibility.md) | 首轮来源锚点可行性审计 | 01 | 已完成（`NO-GO`，证据只读） |
| [02A](./task-02a-production-provenance-foundation.md) | 生产级 provenance 与全库候选重建基础 | 修订版 Spec 已确认 | 已完成（功能门 GO；生产切换门留至 Task06） |
| [02B](./task-02b-revalidate-source-anchor-feasibility.md) | 用正式实现重新验证来源锚点与候选重建协议 | 02A | 已完成（功能 GO；生产切换债务留至 Task06） |
| [03](./task-03-document-contract-and-migration.md) | 定义通用文档、manifest 与元数据迁移协议 | 02B `GO` | 已完成（功能门 GO；安全债务转 Task04/06） |
| [04](./task-04-backend-document-inspection-api.md) | 实现后端文档、manifest 与检查接口 | 03 | 已完成（功能门 GO；生产债务留至 Task06） |
| [05](./task-05-frontend-chunk-inspector.md) | 实现前端双栏切片检查器 | 04 | 已完成（功能门；Task06 生产门待执行） |
| [06](./task-06-legacy-backfill-and-resilience.md) | 执行真实全库索引替换、恢复与性能验收 | 04、05 | 待执行 |
| [07](./task-07-review-acceptance-deploy-retro.md) | 独立验收、部署和复盘 | 06 | 待执行 |

## 当前路线

1. 保留 Task02 首轮 `NO-GO`、fixture、expected 和 schema，禁止改写历史证据。
2. 保留已提交并通过评审的 Task02A-A～C：PDF provenance、Markdown provenance、`SourceProvenanceBundle` 与来源锚点。
3. 废弃未提交的 `reindex-snapshot-v1`、逐 point 恢复、首次打开自动升级、检索期 `must_not` 和 `LegacyUpgradeStore` 设计。
4. Task02A-D 实现可复用的全库候选重建服务与非交互维护命令，但只在固定样本、FakeQdrant 和临时候选 Collection 上验证；不操作真实用户索引。
5. Task02B 给出严格 `GO|NO-GO`。只有 `GO` 才放行 Task03–07。
6. Task03 迁移元数据并冻结唯一 manifest schema；Task04 实现 manifest 和接口；Task06 才在停服维护窗口执行真实全库重建与 alias 切换。

## 全库替换硬约束

- 旧 Qdrant vectors 和旧 manifest 是可删除派生数据；PDF/Markdown 原件、元数据、文档 ID 和时间是长期事实。
- 正式元数据是重建范围的权威来源；元数据缺原件则全局失败，孤立文件只报告、不导入、不删除。
- 每个文档必须同时成功生成 v1、v2、dense 和 sparse；v2 模型不可用或规则降级均失败。
- 先创建 `papers_rebuild_<run-id>`，验证通过后才切换稳定 alias `papers`；首次切换失败保留候选并保持停服，不恢复旧 Collection。
- 默认命令只 dry-run；真实替换必须显式 `--confirm-replace`。不自动停止服务，不在首次打开、启动或普通请求中隐式重建。
- 全局只允许一个 rebuild lock；构建失败删除不完整候选并从头再来。只有已验证候选的 switch/finalize 可以幂等恢复。
- 候选写入必须显式传入 destination Collection 与 `document_id`，不得调用会写固定 `papers`、更新 metadata 或删除当前 points 的隐式入口。
- 每个破坏性动作必须先持久化 intent、执行后持久化 observed；`switching`、`finalizing`、`cleanup_pending` 均以状态和 topology 双重校验恢复。
- Task03/04 必须提供 run-level finalize bundle；Task06 只有写入并验证 `data/kb/index-generation.json` commit marker 后才能恢复正常服务。
- `finalize_pending` 或拓扑不明确时禁止正常启动；不得自动猜测、删除或切换。
- 原件不可原位修改；删除后重新提交生成新 `document_id`。哈希只用于去重和完整性校验。

## 固定交接物

| Task | 固定产物 | 放行门槛 |
|---|---|---|
| 02A | `artifacts/task-02a/implementation-contract.md`、`source-provenance-bundle.schema.json`、`candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、`candidate-validation.schema.json`、`candidate-rebuild-report.md`、`backend-test-report.md` | A–C 历史结果保留；D 的 Port/FSM/dry-run/build/validate/switch/finalize/cleanup 模拟与 E 评审通过 |
| 02B | `artifacts/task-02b/source-anchor-revalidation-report.md` | fixture hash 不变；来源映射、候选验证、故障矩阵均通过；结论严格为 `GO` |
| 03 | `artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`migration-fixture-index.json`、`migration-report.md` | 元数据/ID/原件无损，旧向量不迁移，损坏输入 fail-closed |
| 04 | `artifacts/task-04/api-schema.json`、`upload-closure-matrix.json`、`api-fixture-index.json`、`backend-contract-report.md` | 检查路径不 embedding；旧 route/symbol 全关闭；`INDEX_REBUILD_REQUIRED` 与 immutable source 契约通过 |
| 05 | `artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md`、`frontend-test-final-report.md`、`frontend-review-final-report.md` | PDF/Markdown 安全渲染、双向定位、桌面/窄屏与真实 hostile fixture 通过；生产 worker 加固和 Task06 另行验收 |
| 06 | `artifacts/task-06/full-index-rebuild-report.md`、`resilience-performance-report.md` | 真实候选验证、alias、manifest finalize、重启和查询通过 |
| 07 | `reviews/018-acceptance-review.md`、复盘和部署证据 | 独立验收、全量回归、运行时验证和本地提交完成 |

## 分派约束

- 下游只读取已命名的 Spec、Task 和固定交接物，不依赖聊天摘要。
- 使用本地 Ollama 时，每个开发子任务最多修改 2 个代码文件、目标约 150 行；线上 Agent 不受该资源上限，但仍受文件白名单与单一职责约束。
- 任何代码实现必须分派相应 dev；评审与测试必须由独立 reviewer/tester 执行。
- 不重复实现 parser、chunker、embedding、Qdrant、下载、安全校验或论文导入。
- 在线子 Agent 正常运行时等待其主动返回；只在明确超时、错误、长期无返回或用户要求时诊断日志。

## 变更日志

- 2026-09-08：创建 Task 02–07，并在首轮 Task02 `NO-GO` 后增加 Task02A/02B。
- 2026-09-08：曾采用逐 point/vector 快照、首次打开自动升级与恢复旧索引方案；历史评审和证据保留。
- 2026-09-09：用户确认旧索引可全部丢弃。经 Grill with Docs 确认改为候选 Collection 全库重建、显式维护命令、alias 切换和 Task06 真实执行；旧 D1 未提交草稿废弃，Spec 退回待确认并重新评审。
