> 关联：[spec-040](../../specs/040-research-runtime-retry-and-online-fallback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05；当前状态：`已完成`

# Task 06：评审、回归、部署与复盘

## 一句话目标

通过定向失败注入、真实 API E2E 和最终全量回归，确认退避与线上回退可观测、可恢复且不泄露敏感信息。

## 实施边界

- Task 阶段只跑受影响测试；Spec 收口才跑全量回归。
- 必须使用当前部署版本记录真实请求、事件、最终状态和人工验收步骤。
- 不 push、不合并 main、不改无关 Spec 的未提交修改。

## 子 Agent 分派

测试角色使用 `qwen3.5:9b`，读取 Spec040、Task02–05 报告和部署文档；只运行测试、写验收报告，不修改业务代码。评审/部署由主 Agent 按项目门禁执行，报告写入 `docs/sdd/reviews/040-acceptance-review.md`。

## 验收标准

- 并发资源竞争自动恢复；本地失败→线上回退成功和关闭回退两条路径均有证据。
- 取消、权限错误、证据越界不会被重试或换模型。
- 全量回归、部署 health/ready、API E2E 和人工验收案例通过；失败则 Spec 保持阻塞。

## 执行结果

已完成。真实部署地址为 `http://127.0.0.1:8500`，部署与脱敏 API 证据见
`artifacts/spec040-api-e2e-20260920T1813+0800.md`；人工验收步骤见
`artifacts/spec040-manual-acceptance.md`。全量回归：`2684 passed, 3 skipped, 67
subtests passed`。DeepSeek 模型别名从 Provider 拒绝的 `Deepseek-V4.1-Flash` 修正为
`deepseek-flash` 后，最小 Provider 探针 HTTP 200。准备度矩阵为 10/10；Qdrant warmup
failed 已标注为非 Spec040 的后续问题。

## 收口复盘

- 配置项必须以 Provider 实际支持的模型名为准，不能只验证 Key 存在；本轮由真实探针发现并修正别名。
- `runtime_observability` 只返回稳定错误码、重试计数、时间和 Provider 别名，避免把 Prompt、凭据或模型原文带入 API。
- 旧测试在开发者 `.env` 开启线上回退时会受环境影响；历史四次重试合同显式关闭回退后保持确定性。
- 全量回归仍放在 Spec 收口，Task 阶段继续只跑受影响测试。
