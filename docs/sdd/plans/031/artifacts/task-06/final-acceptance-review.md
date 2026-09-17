# Spec031 Task06 最终验收评审

## 固定字段

- spec：031 — 动态模型路由与资源调度优化
- task：Task06 — 最终评审、回归、基准、部署与复盘
- 评审角色：跨端 tester/reviewer
- 执行模型：Luna high（临时执行）
- 评审时间：2026-09-17 16:29 CST
- 结论：**NO-GO**

## 验收结论

Task02 单实例条件、Task03 脱敏/owner/shadow、Task04 四项 P1、Task05 前端 UI 合同均可由交接报告及本次定向复核支持；Task05 本次合同集合为 `43 passed`，Node 语法和 Task09 fake-DOM 合同均通过，差异空白、敏感字段和冲突标记检查通过。

但最终验收不能签字通过：

1. 唯一全量 `.venv/bin/python -m pytest -q` 退出码为 1，结果为 `2534 passed, 4 failed, 5 warnings, 67 subtests`。4 个失败集中于既有 conversation compaction/evolution worker 的摘要、异常状态和异步完成断言；它们不在 Spec031 Task02–05 定向范围内，但不能被忽略。
2. Task02 审查提出的 P1 benchmark 证据缺口仍在：harness 未验证固定 JSON 响应内容，raw 未保存 ResourceProbe/可用内存、listener/备用端口和运行环境 provenance。因此只能维持单实例观察结论，不能把该 benchmark 作为质量门或多实例收益证据。

## 决策矩阵

| 门 | 结果 | 备注 |
|---|---|---|
| Task02 单实例 | GO（受 cap=1 约束） | 多实例仍 NO-GO；不得启动第二实例 |
| Task03 | GO | 值级脱敏、owner 隔离、shadow 不改生产选择；P2 留项不阻塞本 Task |
| Task04 | GO | 四项 P1 已关闭；保留控制面权限、runtime 接入等 P2 |
| Task05 | GO | 本次 `node --check`、Node 合同和 43 项前端 pytest 均通过 |
| 全量回归 | **NO-GO** | 4 failures，退出码 1 |
| 最终 Spec031 收口 | **NO-GO** | 全量失败及 Task02 provenance/quality P1 未清零 |

## 必须后续处理

- 由相应责任域处理或明确豁免 4 个全量失败，再重新执行唯一全量回归并记录真实退出码。
- 补齐 Task02 harness 的固定 JSON 内容校验及 raw provenance，或在最终记录中明确该门禁阻塞。
- 保持当前单实例、ResourceProbe cap=1 和多实例 NO-GO；不修改 Ollama。
- 运行时部署 smoke 由主 Agent 执行；本评审不代替其部署证据，也不将未独立执行的运行时检查记为本角色通过项。

