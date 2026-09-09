# Task 02B：重新验证来源锚点与候选重建协议（Go/No-Go）

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task02A 全部实现、测试和评审通过；被依赖：Task03；当前状态：`待执行`

## 一句话目标

只读消费 Task02A 正式实现和首轮固定证据，严格验证来源定位与候选 Collection 重建协议，并给出可审计的 `GO|NO-GO`。

## 当前证据

- 首轮 Task02 的 fixture、expected、schema 与 `NO-GO` 报告已冻结。
- Task02A-A～C 已完成；Task02A-D/E 待修订确认后执行。
- 真实用户索引只允许 Task06 在维护窗口操作，本 Task 禁止触碰。

## 前置门禁

- Task02A 的 `implementation-contract.md`、三份 candidate/topology/validation schema、`candidate-rebuild-report.md`、`backend-test-report.md` 和评审结论齐全。
- 首轮证据 SHA-256 与历史报告一致。

## 思维链（可审计执行设计）

1. 先冻结证据 revision/hash，防止通过改 fixture 获得假通过。
2. 用正式入口重放 PDF/Markdown block、chunk、anchor。
3. 用 FakeQdrant 独立覆盖 preflight、candidate build、validate、switch/finalize 与故障恢复。
4. 任何硬门失败即 `NO-GO`，不以条件通过或聊天解释放行。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 内容 | 输出 |
|---|---|---|---|
| 02B-A | backend-tester | 校验首轮 fixture/expected/schema hash 与 Task02A 交接物 | 报告“证据冻结”段 |
| 02B-B | backend-tester | 正式入口重放 PDF/Markdown、v1/v2 与 anchors | 报告“来源映射”段 |
| 02B-C | backend-tester | FakeQdrant 全库候选重建、验证、故障与恢复矩阵 | 报告“候选重建”段 |
| 02B-D | Tech Lead | 只读复核并签 `GO|NO-GO` | `artifacts/task-02b/source-anchor-revalidation-report.md` |

## 固定 Prompt

```text
你是 Spec018 Task02B 的 backend-tester。只读取 Spec018、Task02/02A/02B、首轮 artifacts/fixtures、Task02A 固定报告和被测生产入口。不得修改 backend、frontend、用户 data/kb、真实 Qdrant、首轮 fixture/expected/NO-GO 报告或 Git 历史；不得重新设计或放宽验收阈值。

先核对首轮证据 hash 与三份机器 schema。随后用正式入口重放全部固定样本，验证 PDF block bbox、Markdown 行号、v1 overlap、v2 跨页、多对多 anchors、page-null 和 hostile 后端安全。再使用 FakeQdrant 与临时目录验证：CandidateIndexPort 显式 destination/document_id 且正式 papers/metadata/source 零写；dry-run 全部写 spy 为 0；元数据权威集合与孤立文件报告；空库和缺失/损坏原件；全局 lock token/heartbeat/finally/stale recovery；v1+v2、dense+sparse 候选构建；规则降级拒绝；validation schema 与 fingerprint 复算；dense+sparse 查询；每个 switch/finalize 动作前后中断；intent/observed 收敛；cleanup_pending/删除超时/结果未知；首次 physical papers 到 alias；后续原子切换；resume-switch/finalize；完整 topology inventory/matrix 与 fail-closed。禁止触碰真实索引。

必须输出严格 GO 或 NO-GO。报告写入 docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md。返回：状态摘要、命令/退出码、样本 hash、映射率与 bbox/行号误差、候选验证计数/fingerprint、失败矩阵、GO/NO-GO、风险、主 Agent 动作、开始结束耗时和可用的模型/token/工具统计。
```

## 子 Agent 必须返回

- 严格 `GO|NO-GO` 与逐项依据。
- 读取的 revision、fixture/expected/schema hash。
- 测试命令、退出码、数量、耗时。
- 来源映射率、bbox 最大误差、Markdown 行号准确率。
- dry-run 写计数、候选/alias/finalize 状态与故障矩阵。
- 产物路径、风险阻塞和主 Agent 后续动作。

## 主 Agent 校验

- 报告未改写首轮证据，未接触真实 data/Qdrant。
- `GO` 覆盖所有固定硬门，不存在“条件通过”。
- 报告不引用旧 snapshot、upgrade、must_not 或自动首次打开协议。

## 实时监控

在线 Agent 正常运行时等待主动返回；仅在明确超时、错误、长期无返回或用户要求时读取对应日志。

## 测试与验收标准

- 正常 PDF block bbox 最大误差 ≤0.005；Markdown 行号 100%；期望 block/chunk/anchor 集合 100% 匹配。
- 新候选中每个正式 fixture 同时具有 v1/v2，point ID 唯一、chunk_index 无重复/缺口，dense/sparse 与 payload schema 完整。
- dry-run 无 embedding 和写操作；任一构建硬门失败不切换。
- CandidateIndexPort 对正式 `papers`、metadata、source 和 current-point delete 的写计数为 0。
- `switching/finalizing/cleanup_pending` 在每个动作前后中断后均按 intent+fresh topology 幂等收敛；未知拓扑不自动处理。
- candidate validation 由公开 builder 生成并复算，v2 `llm_used=true`，不接受报告手填关键值。

## 风险、停止条件与回滚

- 任一 hash 漂移、真实数据写入或阈值失败：立即 `NO-GO`，保持 Task03–07 阻塞。
- 本 Task 不产生需要回滚的业务数据。

## 产出物

- `docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md`

## 执行结果

待 Task02A-D/E 完成后填写。

## 变更日志

- 2026-09-08：创建 Task02B，最初包含旧索引快照恢复验收。
- 2026-09-09：经确认改为候选 Collection 全库重建协议验收，真实索引操作推迟到 Task06。
