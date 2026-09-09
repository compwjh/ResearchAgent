# Task 02A：生产级来源定位与全库候选重建基础

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：首轮 Task02 `NO-GO` 证据、全库替换修订重新通过评审并获用户确认；被依赖：Task02B；当前状态：`实施中（A–C 已完成；D 执行中；E 待 D）`

## 一句话目标

复用已完成的 PDF/Markdown provenance 与 `SourceProvenanceBundle`，补齐可验证但尚不操作真实用户索引的全库候选 Collection 重建基础。

## 当前证据

- 02A-A PDF provenance 已完成并提交，定向测试通过。
- 02A-B Markdown provenance 已完成并提交，定向测试通过。
- 02A-C `SourceProvenanceBundle`、v1/v2 anchors 与 page-null 消费已完成并提交，定向测试通过。
- 未提交的 `reindex-snapshot-v1` 代码、测试与报告已因需求改变废弃，不属于交付物。
- 当前正式索引与用户数据在本 Task 中保持只读。

## 前置门禁

- Spec 018 全库替换修订的需求/技术评审通过，且用户再次明确确认。
- 首轮 Task02 fixture、expected、schema 和 `NO-GO` 报告保持 hash 不变。
- D 阶段只能使用固定样本、FakeQdrant、临时目录和临时候选 Collection。
- 2026-09-09 独立需求评审与技术设计门通过，用户明确要求开始执行；本门禁已满足。

## 思维链（可审计执行设计）

1. 保留 A–C 已验证能力，不重写 parser、chunker 或 anchor 算法。
2. 把重建拆为 preflight、build、validate、switch、finalize 五个显式阶段。
3. Task02A 只实现可复用服务与维护命令，并模拟 switch；最终 manifest schema 尚未冻结，因此只输出临时 `SourceProvenanceBundle` 证据。
4. Task02B 使用首轮 fixture 和 FakeQdrant 独立裁决；真实元数据迁移由 Task03、manifest 由 Task04、真实全库切换由 Task06 负责。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 内容 | 固定产物 |
|---|---|---|---|
| 02A-A | backend-dev | PDF block provenance | `pdf-provenance-report.md`（已完成） |
| 02A-B | backend-dev | Markdown block provenance | `markdown-provenance-report.md`（已完成） |
| 02A-C | backend-dev | provenance-aware v1/v2 与 `SourceProvenanceBundle` | `source-provenance-bundle.schema.json`、`chunker-integration-report.md`（已完成） |
| 02A-D | backend-dev | CandidateIndexPort、全库 rebuild CLI/FSM、topology/validation schema、dry-run、候选 build/validate、模拟 alias/finalize/cleanup | `candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、`candidate-validation.schema.json`、`candidate-rebuild-report.md` |
| 02A-E | backend-tester + backend-reviewer + Tech Lead | 定向回归、故障注入、复用审计与交接签字 | `backend-test-report.md`、`backend-review-report.md`、`implementation-contract.md` |

## 02A-D 固定 Prompt

```text
你是 Spec018 Task02A-D 的 backend-dev。只读取 Spec018、本 Task、首轮 Task02 固定证据、已完成的 02A-A～C 交接物，以及现有 knowledge_base 的 parser/chunker/embed/index/config 入口。允许修改分派清单明确列出的 backend 文件、对应后端测试和本子任务报告；禁止修改 frontend、用户 data/kb、真实 Qdrant、首轮 fixture/expected/NO-GO 报告和 Git 历史；禁止 reset/stash/clean/push/merge。

实现非交互维护入口 `python -m backend.app.knowledge_base.rebuild_index` 及可复用服务。默认等价于 `--dry-run`；实际写入必须显式 `--confirm-replace`。本 Task 只能在 tempfile、FakeQdrant 和临时 Collection 上验证，严禁运行真实替换。先冻结 candidate-rebuild-run、topology-inventory、candidate-validation 三份机器 schema，再实现。

协议必须包含：元数据权威集合、孤立文件只报告、空库 `NO_DOCUMENTS_TO_REBUILD`、原件/哈希/解析/配置/模型/Qdrant preflight、create-exclusive 全局 lock 与显式 stale-lock recovery、`papers_rebuild_<run-id>`、每文档 v1+v2、dense+sparse、无规则降级、CandidateIndexPort 显式 destination/document_id 且零 metadata/delete-current 副作用、完整 validation、intent/observed FSM、首次物理 `papers` 到 alias 的模拟切换、后续 alias 原子更新、`switching/finalizing` 崩溃恢复、`cleanup_pending`、`--resume-switch`、`--resume-finalize`、`--cleanup-failed`、topology inventory/matrix、运行状态 JSON 与脱敏事件。dry-run 可解析和检查全部原件，但不得创建 runtime/lock、embedding、创建/删除/写 Collection 或修改 metadata/source/manifest。

Task02A 不定义或持久化最终 InspectionManifest；只复用 SourceProvenanceBundle。不得实现 point/vector snapshot、LegacyUpgradeStore、逐文档 must_not、首次打开自动升级或旧索引回滚。完成后运行定向 pytest 和静态检查，并返回：结果状态和摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险阻塞、主 Agent 后续动作、开始/结束/总耗时，以及可用的模型/token/工具统计。
```

## 子 Agent 必须返回

- 结果状态、02A 子任务编号和摘要。
- 改动文件及每个文件的职责。
- 测试命令、退出码、通过数量和耗时。
- dry-run 写操作计数；build/validate/switch/finalize 状态轨迹。
- 候选名称、文档/point 计数、dense/sparse 维度和 fingerprint。
- 故障矩阵、清理/恢复结果、风险与主 Agent 后续动作。
- 日志与固定产物路径；可用时记录模型、token 和工具调用统计。

## 主 Agent 校验

- `git diff` 不含真实用户数据、旧 D1 快照实现或首轮证据改写。
- dry-run 的 embedding、Qdrant write、metadata write 均为 0。
- CandidateIndexPort 不得隐式使用 `KB_COLLECTION`/`paper_id` 或调用带 metadata/delete 副作用的 `index_paper_chunker()`；所有目标 Collection 与 `document_id` 必须显式传入。
- 构建失败只删除本次未验证候选；已验证候选的 switch/finalize 可幂等恢复。
- 未知 alias/Collection 拓扑 fail-closed，不自动猜测或删除。
- `switching/finalizing/cleanup_pending` 的每个动作前后都有可恢复 intent/observed，FakeQdrant 覆盖动作前后中断。
- 02A 没有定义最终 manifest，也没有引入第二套 parser/chunker/embed/index。

## 实时监控

在线 Agent 正常运行时等待主动返回，不轮询日志。只有明确超时、错误、长期无返回或用户要求时，才读取 `.codebuddy/agent-logs/spec-018/task-02a/` 的对应日志诊断。

## 测试与验收

- 固定 PDF/Markdown fixture 可通过正式入口生成预期 bundle。
- FakeQdrant 覆盖首次物理 Collection 切 alias、后续 alias 更新、alias 失败、finalize 失败、构建失败、中断残留、并发锁和拓扑歧义。
- dry-run 覆盖两个并发 dry-run、dry-run 与 confirm 竞态、全部写 spy 为 0；真实命令锁覆盖 token、heartbeat、异常释放、崩溃残留和显式 `--recover-stale-lock`。
- cleanup 覆盖删除超时/结果未知/幂等重试；已验证候选不可 cleanup。
- 每文档 v1/v2 均至少一个 chunk；point ID 唯一且 chunk_index 无重复/缺口；dense/sparse 维度、payload、anchors、hash 和 fingerprint 正确。
- 受控 dense 与 sparse 查询均命中候选。

## 风险、停止条件与回滚

- 任何路径触碰真实 `data/kb` 或真实 Qdrant：立即停止并报告。
- 需要最终 manifest schema 才能继续：停止，不得在 Task02A 私自定义；交由 Task03。
- 本 Task 的回滚仅删除临时测试候选和临时运行状态，不修改用户原件、元数据或正式索引。

## 产出物

- 已完成的 production provenance/bundle 实现。
- 候选重建服务与 CLI、三份机器 schema、定向测试、固定报告和实现交接契约。

## 执行结果

- 02A-A～C：已完成并分别提交。
- 02A-D/E：待修订版 Spec 重新评审和用户确认后执行。

## 变更日志

- 2026-09-08：创建 Task02A，最初采用逐 point/vector 快照和自动升级设计。
- 2026-09-09：A–C 完成并通过定向评审。
- 2026-09-09：用户确认旧索引可丢弃；经 Grill with Docs 将 D 改为候选 Collection 全库重建协议，废弃未提交快照草稿，暂停等待重新评审和确认。
