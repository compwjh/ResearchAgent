# Task 02A：生产级来源定位与旧索引安全升级基础

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：首轮 Task02 `NO-GO` 证据、修订版 Spec 重新通过需求/技术评审并由用户确认；被依赖：Task02B；当前状态：`实施中`

## 一句话目标

把首轮审计缺失的 PDF block provenance、Markdown 行块、可追踪 v1/v2 和旧索引可恢复升级实现为正式基础能力，不做测试目录中的一次性原型。

## 当前证据

- 首轮报告：`artifacts/task-02/source-anchor-feasibility-report.md`，结论为 `NO-GO`。
- 现有 `extract_pages_normalized` 只返回 `(page, text)`；现有 `Chunk` 没有来源块关系。
- 业务代码没有 Markdown parser/chunker。
- Qdrant 旧 point 可按文档和 chunker 读取，但原地索引会先删后写，失败时存在数据缺口。

## 前置门禁

- 本次自动重建修订的需求评审、技术评审均重新通过，用户再次确认 Spec。
- 首轮 fixture、expected JSON、schema 和 `NO-GO` 报告只读，不得覆盖或改写。
- 修改前记录目标文档旧 point 数、ID、payload/vector fingerprint 和原件 hash；测试只使用匿名 fixture/FakeQdrant。

## 思维链（预先设计的执行阶段与决策依据）

1. 先让 parser 产出同源 block DTO，再让 normalize、chunker、index 消费该 DTO；禁止事后用另一遍文本提取补 bbox。
2. PDF 首版只承诺 block bbox；line/word 是可选诊断，不能扩大硬门。
3. Markdown 解析为带精确行号的块，参数化复用 v1/v2，不创建第三套切片器。
4. 旧索引先完成全部计算，再保存恢复快照，最后进入短写窗口原地替换；任一版本失败恢复全部旧版本。
5. Task02A 只冻结并生成 `SourceProvenanceBundle`，不持久化 manifest；Task03 定义唯一 manifest schema，Task04 才负责持久化，避免反向依赖。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 目标 | 固定产物 |
|---|---|---|---|
| 02A-A | backend-dev | `PdfSourceProvenanceV1`、block bbox、同源 normalize 适配与固定样本测试 | `artifacts/task-02a/pdf-provenance-report.md` |
| 02A-B | backend-dev | Markdown block parser、行号/heading_path/block_type、UTF-8/BOM/NUL/CRLF 测试 | `artifacts/task-02a/markdown-provenance-report.md` |
| 02A-C | backend-dev | 参数化 v1/v2 消费来源块并生成 `SourceProvenanceBundle`；不定义/持久化 manifest | `artifacts/task-02a/source-provenance-bundle.schema.json`、`chunker-integration-report.md` |
| 02A-D1 | backend-dev | 冻结 `reindex-snapshot-v1` 并实现 point/payload/dense+sparse round-trip store | `artifacts/task-02a/reindex-snapshot.schema.json`、`snapshot-roundtrip-report.md` |
| 02A-D2 | backend-dev | 使用既有单线程 executor 的文档级 operation/claim、全部已有版本联合升级与启动恢复 | `artifacts/task-02a/legacy-upgrade-report.md` |
| 02A-D3 | backend-dev | application 包装现有 `hybrid_search`，对 active upgrade 文档施加 dense+sparse 共用 `must_not` | `artifacts/task-02a/retrieval-exclusion-report.md` |
| 02A-E | backend-tester + backend-reviewer + Tech Lead | 定向回归、故障注入、复用审计与交接签字 | `artifacts/task-02a/backend-test-report.md`、`backend-review-report.md`、`implementation-contract.md` |

如果执行者是本地 Ollama 模型，每个编码子任务最多修改 2 个代码文件、目标约 150 行；使用线上 Agent 时取消该资源限制，但仍须遵守分派清单中的文件范围和单一职责。

## 固定分派 Prompt

```text
你是 Spec018 Task02A 的 backend-dev。先读取 Spec018、Task02 首轮 NO-GO 报告、本 Task 和当前子任务指定的最多量文件；不要扫描无关模块。你的产出必须是后续 Task03–07 直接复用的生产实现，不得在 tests 或临时目录建立第二套 parser、chunker、embedding、Qdrant 或索引流程。

实现约束：PDF 的规范化文本和 block bbox 必须来自同一个 PdfSourceProvenanceV1；首版硬门是 block，不要求 word。Markdown 输出精确 1-based 行范围并复用参数化 v1/v2。Task02A 只产出 SourceProvenanceBundle，不定义 manifest。旧 PDF 自动升级只重建已有可用版本；删除旧 points 前完成解析、v2 模型调用和 embedding，并保存符合 reindex-snapshot-v1 的 point/payload/dense+sparse vector。文档级 operation 必须使用现有单线程 executor，不能嵌套提交按 chunker 任务。v2 模型不可用或规则降级、写入失败、校验失败、进程恢复失败时恢复全部旧版本。application.hybrid_search 必须把 active upgrade IDs 作为同一个 must_not filter 传给 dense+sparse 两路。成功验证后删除快照；首次自动失败后仅允许手动重试。

只允许修改分派清单列出的 backend 文件、对应后端测试和本子任务报告。禁止修改 frontend、用户 data/kb、真实 Qdrant、首轮 fixture/expected/NO-GO 报告、Git 历史；禁止 reset/stash/clean/push/merge。必须运行分派指定的 pytest 和静态检查。

完成后的可观察状态：固定 fixture 可由正式实现生成预期 SourceProvenanceBundle；旧索引故障注入后 point ID/payload/dense+sparse vector/fingerprint 完整恢复；成功路径删除快照；并发首次打开只产生一个 operation；active upgrade 文档在 dense+sparse 两路均为零命中，恢复/完成后重新可召回。

把结果写入 docs/sdd/plans/018/artifacts/task-02a/<子任务报告>.md，日志写入 .codebuddy/agent-logs/spec-018/task-02a/backend-dev/<timestamp>.md。返回固定字段：结果状态与摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险与阻塞、主 Agent 后续动作、开始/结束/总耗时，以及可用的模型/token/工具统计。
```

## 子 Agent 必须返回

- 结果状态、摘要和对应 02A 子任务编号。
- 改动文件及每个文件的职责。
- 测试命令、退出码、通过/失败数量和故障注入结果。
- 首轮 fixture hash 是否保持不变。
- snapshot 前后 point ID、payload、vector、fingerprint 对照。
- dense/sparse 两路 query filter 与升级状态前后命中对照。
- 产物与层级日志路径、风险、阻塞和主 Agent 后续动作。
- 开始、结束、总耗时；可用时记录模型、token 和工具调用。

## 主 Agent 校验

- 确认正式 parser 是唯一事实源，生产代码没有二次文本抽取补坐标。
- 确认 Task02A 没有私自定义或持久化 manifest，只有版本化 SourceProvenanceBundle。
- 搜索是否新增第二套 embedding/Qdrant/index task 或第三套 Markdown chunker。
- 对成功、embedding 失败、v2 模型失败、删除后写入失败、验证失败和重启恢复逐项核对旧索引恢复。
- 确认首次自动失败后 GET 不会再次提交，只有手动 retry 可重试。
- 确认首轮 Task02 证据完全未改写，再签字放行 Task02B。

## 实时监控

- 日志固定写入 `.codebuddy/agent-logs/spec-018/task-02a/<role>/<timestamp>.md`。
- 主 Agent 根据子任务复杂度和最近进度自适应读取，不固定高频轮询。

## 测试与验收标准

- PDF 单栏、双栏、跨页 fixture 的 block 文本、ordinal、bbox 和 chunk anchors 精确匹配 expected；bbox 误差 ≤0.005。
- Markdown heading/paragraph/list/table/code/blockquote 块与行号 100% 匹配。
- v1 overlap 和 v2 跨页保留多对多 anchors；word 缺失不导致失败。
- 自动升级只覆盖已有版本；v2 模型失败不以规则降级结果替换旧 v2。
- 写入/验证/恢复期间普通 RAG 入口排除该文档，不召回半套 points；报告记录短暂不可检索窗口。
- dense/sparse 两路使用同一个 `must_not paper_id MatchAny`，升级状态结束后恢复命中，RRF/reranker 不接收被排除文档。
- snapshot schema 验证 float32 little-endian base64 dense、uint32/float32 little-endian sparse、canonical payload、逐点/总 hash、损坏/截断 fail-closed 和幂等恢复。
- 旧索引所有故障注入后可恢复；成功后快照删除，仅留脱敏摘要。
- 真实用户数据、Qdrant 和 Git 历史未被测试修改。

## 风险、停止条件与回滚

- 无法从同一 PDF DTO稳定得到 block 文本和 bbox：停止并回退 Spec，不进入 02B。
- 无法完整恢复 dense/sparse vector 或跨版本原子性：停止，不允许原地替换上线。
- 发现必须改变既有检索/RRF/reranker 语义：暂停并更新 Spec，不能顺手扩大范围。
- 代码回滚只撤销本 Task 改动；不得通过 reset、clean 或覆盖用户修改回滚。

## 产出物

- 生产级来源定位基础、旧索引升级与恢复实现、定向测试、固定 schema 和五份交接报告。

## 执行结果

待修订版 Spec 重新评审和用户确认后填写。

## 变更日志

- 2026-09-08：依据 Grill with Docs 决策创建；本轮只落盘文档，未执行代码任务。
