# Task 02：验证来源锚点可行性（Go/No-Go）

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task 01、上一版 Spec 已确认；被依赖：Task02A；当前状态：`已完成（NO-GO，历史证据）`

## 一句话目标

用固定 PDF、Markdown 和既有 Qdrant payload 证明文本块级双向映射可达，并冻结不能满足时的停止条件。

## 当前证据

- `Chunk` 现有字段只有 text/page/page_end/section/chunk_index。
- PDF 由 PyMuPDF 提取清洗，前端尚未集成 PDF.js。
- v1 存在 overlap，v2 允许跨页；来源关系天然是多对多。

## 前置门禁

- 需求与技术评审通过，Spec 状态为已确认。
- 只使用匿名固定样本，不读取或提交用户私人论文内容。
- 原型产物写入测试临时目录或本 Task 的脱敏证据文档，不改业务数据。

## 执行阶段与观察点

1. 构造一份多段落/双栏 PDF 与一份含标题、列表、表格、代码块的 Markdown。
2. 对 v1 重叠、v2 跨页切片建立顺序文本对齐，记录一对多和多对多覆盖率。
3. 验证 PDF 坐标归一化后可在不同缩放比例稳定覆盖同一文本块。
4. 验证从 Qdrant 读取实际 payload 可生成 `index_fingerprint`，不调用 embedding。
5. 固定 `ready/partial/failed` 判定和无法映射时的用户可见状态。

## 子 Agent 分派

- 角色：架构师进行技术裁决；backend-tester 执行固定样本验证。
- 最小上下文：Spec 018、本 Task、knowledge_base 的 parse/chunkers/index/retrieve。
- 允许修改：`tests/fixtures/kb/**`、本 Task 执行结果；业务代码禁止。

## 可交接子任务与固定产物（P0-7）

Task 02 必须按以下顺序交接，不允许把多个阶段合并成一次不可审计的长任务。该 Task 不需要本地 27B 修改业务代码；若为验证增加临时探针，也最多新增 2 个 fixture/探针文件、约 150 行，并在报告中列出路径与退出码。

| 子任务 | 执行者/上下文 | 输入与范围 | 固定输出 |
|---|---|---|---|
| 02-A fixture freeze | `backend-tester` / `qwen3.5:9b` / 32k | 只生成匿名 PDF/Markdown 原件、expected JSON、README；禁止用户数据与 Qdrant 写入 | `docs/sdd/fixtures/spec-018/` 下固定样本及 `docs/sdd/plans/018/artifacts/task-02/fixture-index.json` |
| 02-B provenance/mapping probe | `backend-tester` / `qwen3.5:9b` / 32k | 读取 02-A fixture、既有 parser/chunker 与只读 payload；记录 provenance、坐标、映射和 no-embedding spy | `docs/sdd/plans/018/artifacts/task-02/provenance-dto.schema.json` 与同目录报告草稿 |
| 02-C Go/No-Go audit | Tech Lead（自身）/ 128k | 只读 02-A/02-B 产物及命令证据，逐项核对硬门 | `docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md`，结论只允许 `GO`/`NO-GO` |
| 02-D handoff closure | Tech Lead（自身）/ 最低 64k；最终 Gate 128k | 只读 02-A～02-C 固定产物，补齐报告交接清单并签字；不得修改 fixture、业务代码或放宽阈值 | 在 `source-anchor-feasibility-report.md` 追加交接段，确认字段/哈希/命令/退出码齐全及 Task 03 放行/阻塞 |

报告必须逐样本记录 `sample_id`、原件/expected/schema SHA-256、git revision、parser/provenance/normalize/mapping 版本、命令/退出码、页数/列数/rotation、block/line/word 统计、映射率、重复文本 tie-break、bbox 最大/中位误差、Markdown 行号、Qdrant point 数/ID/fingerprint、embedding/切分/upsert/delete 调用次数、失败码和结论。`fixture-index.json` 必须列出每项相对路径、SHA-256、媒体类型、期望状态与阈值，供 Task 03 只读消费。

## 交接门禁

- 只有 02-C 为 `GO`，且三个固定产物均存在、可校验、无未填写字段，Task 03 才能启动。
- 任一阈值失败、调用次数非 0、expected 集合不一致或 hostile fixture 有非本地网络请求，必须写 `NO-GO`，将本 Task 标为 `阻塞/需修订`，Spec 保持/退回 `待确认`，停止 Task 03–07；不得把失败降级成普通风险。
- 下游只读取上述固定路径，不以聊天摘要或临时终端输出作为交接依据。

### 固定 Prompt

```text
你是 Spec018 的 backend-tester。只读取 Spec018、Task02 和 knowledge_base 中 parse/chunkers/index/retrieve 四类相关实现。使用匿名固定 PDF/Markdown 样本验证：PDF 文本块坐标、Markdown 行块、v1 overlap、v2 跨页、Qdrant 实际 payload 指纹和多对多来源锚点。不得修改业务代码、用户 data/kb、Qdrant 或 Git 历史；不得调用 embedding。测试产物仅可写 tests/fixtures/kb 或 Task02 执行结果。返回：结果状态、样本、命令与退出码、映射率、一对多/多对多证据、失败样本、Go/No-Go、风险、开始结束与耗时。
```

## 主 Agent 校验

- 读回全部样本和结果，确认没有使用用户文档。
- 对照现有真实 payload 字段，不接受凭空假设的坐标或字符 offset。
- 若不能稳定达到块级双向定位，标记 No-Go 并停止 Task 03。

## 实时监控

- 查看对应 Agent 的进展日志；仅在预计阶段完成后读取，不固定高频轮询。

## 测试与验收

- 固定文本块全部可稳定定位；故意制造的不匹配进入 `partial`。
- 重叠和跨页关系没有被压成一对一。
- 全程未调用 embedding、未修改 Qdrant、未写用户数据。

## 风险、停止与回滚

- PDF 文本提取顺序与视觉顺序不可可靠对齐：No-Go，回到 Spec 缩小精度。
- 原型仅使用临时/fixture 文件，删除新增 fixture 即回滚。

## 产出物

- 固定样本、可执行验证、脱敏可行性结论。

## 执行结果

已完成 02-A→02-B→02-C→02-D 只读核验，严格结论：`NO-GO`。本 Task 已作为历史审计闭合，不能改写为通过；Task03 不放行。固定产物：`docs/sdd/fixtures/spec-018/`、`docs/sdd/plans/018/artifacts/task-02/fixture-index.json`、`provenance-dto.schema.json`、`source-anchor-feasibility-report.md`。后续由 Task02A 实现正式基础，再由 Task02B 产生独立的新 Go/No-Go 报告。

## 变更日志

- 2026-09-08：架构师创建 Task。
- 2026-09-08：根据 P0-7 拆为 02-A fixture、02-B provenance/mapping、02-C Tech Lead Go/No-Go；冻结三个交接产物、字段、SHA-256 与停止门禁。
- 2026-09-08：P0-7 最终小修订增加 02-D handoff closure，明确 Tech Lead 单步最低 64k、最终 Gate 128k，交接只读固定 artifacts，不修改实现。
- 2026-09-08：backend-tester 完成 02-A→02-D；匿名样本 oracle、bbox 重投影、Markdown 行号 oracle、Qdrant duplicate/gap 与 no-embedding guard 通过，但现有 parser 缺少同源 PDF provenance DTO、业务缺少 Markdown parser/chunker，hostile 网络未实测；严格裁决 `NO-GO`，Task03 阻塞。
- 2026-09-08：根据 Grill with Docs 决策将本 Task 闭合为不可改写的历史 `NO-GO`；新增 Task02A 生产实现与 Task02B 重新验证，Task03 改依赖 02B `GO`。
