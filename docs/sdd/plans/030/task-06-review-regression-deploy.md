# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`已完成`

## 一句话目标

证明所有主要结论均可追溯、三种报告格式一致，并完成唯一全量回归、部署和复盘。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec030、全部 Task 报告和 diff。
允许修改：reviews/030-*.md、plans/030/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止扩大报告编辑/投稿范围、伪造证据、push/merge/reset/stash/clean。
验证：固定冲突矩阵、逐 Claim 引用回查、三格式、XSS、浏览器、唯一全量回归、部署。
完成状态：三评审与签字齐全，Spec/Task/台账同步。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 任一孤立 Claim、错引或格式语义漂移均阻塞。
- 产出评审、验收、复盘和部署证据；执行结果已落盘至 [`artifacts/task-06/acceptance-audit.md`](./artifacts/task-06/acceptance-audit.md)。
- 收口结论：`PASS`。报告错误出口改用稳定异常文本，矩阵未就绪映射为 409，未知报告读取为 404，非法格式为 406。
- 全量回归：`.venv/bin/python -m pytest -q` 退出码 0，`2504 passed, 1 skipped, 67 subtests passed, 5 warnings`，耗时 232.53 秒。
- 静态门禁：`node --check frontend/research-tasks.js`、指定后端 `py_compile`、`git diff --check` 均退出码 0。
- 运行时：`PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 启动成功；health/root=200，矩阵未知任务=404、未知报告=404、非法格式=406；服务日志确认请求命中并在 smoke 后停止。

## 变更日志

- 2026-09-12：创建最终收口 Task。
- 2026-09-17：Task06 唯一全量回归和运行时/浏览器 smoke 完成；固定矩阵与三格式合同通过，但发现报告错误响应 P1（`EvidenceReportError.message` 缺失导致未知报告 500），验收阻塞，等待主 Agent 修复后重跑收口。
- 2026-09-17：修复报告路由错误文本与矩阵未就绪状态映射；旧 Spec034 样式版本断言通过兼容标记保留；后端复核 PASS、全量回归和部署 smoke 全部通过，Task06 完成。
