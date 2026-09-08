# Task 02B：使用正式实现重新验证来源锚点（Go/No-Go）

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task02A 全部实现、测试和评审通过；被依赖：Task03；当前状态：`待执行`

## 一句话目标

只读消费 Task02A 的正式实现和首轮匿名 fixture，重新给出可审计的 `GO|NO-GO`，不通过聊天摘要或放宽阈值绕过首轮问题。

## 当前证据

- 首轮报告结论为 `NO-GO`，固定路径为 `artifacts/task-02/source-anchor-feasibility-report.md`。
- 首轮 fixture、expected JSON、schema 和 hash 已提交，必须作为不可变基线。
- Task02A 计划补齐正式 block provenance、Markdown parser 和旧索引恢复能力。

## 前置门禁

- `artifacts/task-02a/implementation-contract.md`、各实现报告、测试报告和评审报告全部存在且结论通过。
- 首轮 fixture/expected SHA-256 与 `fixture-index.json` 一致。
- 本 Task 不修改业务代码、用户数据、真实 Qdrant 或首轮报告。

## 思维链（预先设计的执行阶段与决策依据）

1. 先验证交接物和 hash，避免针对被修改的样本“通过”。
2. 再用正式生产入口重放 PDF/Markdown，不接受测试专用 parser。
3. 分开验证来源映射、旧索引升级恢复和 hostile 后端安全。
4. 浏览器 PDF.js 零网络证据明确留给 Task05，本 Task 不再形成循环依赖。
5. 任一硬门失败即 `NO-GO`，不能以 conditional pass 放行 Task03。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 范围 | 固定产物 |
|---|---|---|---|
| 02B-A | backend-tester | 校验首轮 fixture/expected/schema hash 与 Task02A 交接物 | 报告“证据冻结”段 |
| 02B-B | backend-tester | 正式入口重放 PDF/Markdown block/chunk/anchor | 报告“映射结果”段 |
| 02B-C | backend-tester | FakeQdrant 成功/失败/中断恢复、并发与仅手动重试 | 报告“升级恢复”段 |
| 02B-D | Tech Lead | 只读核验全部证据并签 `GO|NO-GO` | `artifacts/task-02b/source-anchor-revalidation-report.md` |

## 固定分派 Prompt

```text
你是 Spec018 Task02B 的 backend-tester。只读取 Spec018、Task02/02A/02B、首轮 artifacts/fixtures、Task02A 固定报告和被测生产入口。不得修改 backend、frontend、用户 data/kb、真实 Qdrant、首轮 fixture/expected/NO-GO 报告或 Git 历史；不得重新设计实现。

使用正式生产入口重放全部固定样本，验证 PDF block bbox、Markdown 行号、v1 overlap、v2 跨页和多对多 anchors。word 信息只作诊断，不是硬门。Hostile PDF 只验证后端不执行脚本/表单/附件/远程资源；真实浏览器零网络证据留给 Task05。使用 FakeQdrant 验证旧索引已有版本全部升级、预计算后短写入、完整 point/payload/dense+sparse vector 快照、故障恢复、成功删除快照、并发单任务，以及首次失败后仅手动重试。禁止触碰真实索引。

必须输出严格 GO 或 NO-GO。固定报告写入 docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md；日志写入 .codebuddy/agent-logs/spec-018/task-02b/backend-tester/<timestamp>.md。返回：状态摘要、命令/退出码、样本 hash、映射率与 bbox/行号误差、快照恢复前后 fingerprint、失败样本、GO/NO-GO、风险、主 Agent 动作、开始结束耗时和可用的模型/token/工具统计。
```

## 子 Agent 必须返回

- 严格 `GO|NO-GO` 和逐硬门证据。
- fixture/expected/schema/实现 revision 的 SHA-256。
- 测试命令、退出码、结果和故障注入矩阵。
- block/chunk/anchor 数、映射率、partial 原因、bbox 最大误差和 Markdown 行号精度。
- point ID、payload、dense/sparse vector、fingerprint 恢复对照。
- 产物/日志路径、风险、阻塞、主 Agent 后续动作和耗时。

## 主 Agent 校验

- 确认报告调用生产入口，未以测试原型代替。
- 确认首轮证据 hash 未变化，真实 data/kb/Qdrant 未变化。
- 确认 word 不再误作硬门，hostile 浏览器门清晰移交 Task05。
- 只有报告为严格 `GO` 且字段完整，才更新 Task03 为可执行。

## 实时监控

- 日志固定写入 `.codebuddy/agent-logs/spec-018/task-02b/<role>/<timestamp>.md`；按预计阶段自适应读取。

## 测试与验收标准

- 正常 PDF expected block/chunk/anchor 集合 100% 匹配，bbox 最大误差 ≤0.005。
- Markdown block/行号 100% 匹配；v1/v2 保留真实来源关系。
- `partial` 可提交但必须有覆盖率、未映射数量和稳定原因；零映射不得通过。
- 所有旧索引故障注入恢复到相同 point/payload/vector/fingerprint。
- Hostile 后端解析无网络、无活动内容执行；浏览器证据作为 Task05 必验项记录在 handoff。

## 风险、停止条件与回滚

- 任一硬门失败立即写 `NO-GO`，Spec 保持/退回 `待确认`，Task03–07 停止。
- 报告缺 hash、命令、退出码或恢复证据视为 `NO-GO`。
- 本 Task 只写报告与日志；删除未提交的派生报告即可回滚，不改固定历史证据。

## 产出物

- `docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md`。

## 执行结果

待 Task02A 完成后填写。

## 变更日志

- 2026-09-08：依据 Grill with Docs 决策创建；本轮只落盘文档，未执行验证。
